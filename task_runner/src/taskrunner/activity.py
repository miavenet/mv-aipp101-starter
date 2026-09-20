"""Route native hook telemetry to each invocation; observations never decide acceptance."""
from collections import deque
import json
import os
import subprocess
import sys
from pathlib import Path

from . import proc, record


def assets(root, kind):
    root = Path(root)
    if kind not in ("claude", "codex"):
        return []
    relative = (['.claude/settings.json', '.claude/settings.local.json', '.claude/hooks/log-hook.py']
                if kind == 'claude' else ['.codex/config.toml', '.codex/hooks.json', '.codex/statusline.py',
                                         '.claude/hooks/log-hook.py'])
    return [root / p for p in relative if (root / p).is_file()]


def prepare(kind, cwd, invocation_dir, env):
    directory = Path(invocation_dir).resolve()
    logs = directory / 'hooks'
    logs.mkdir(mode=0o700)
    updated = dict(env)
    updated.update(HOOK_LOG_DIR=str(logs), CODEX_HOOK_LOG=str(logs / 'hooks.jsonl'),
                   TASK_RUNNER_INVOCATION=str(directory), TASK_RUNNER_AGENT_KIND=kind)
    sources = {str(p): record.sha256_file(p) for p in assets(cwd, kind)}
    record.write_durable(directory / 'activity.json', record.dump_json({
        'agent_kind': kind, 'run': env.get('TASK_RUNNER_RUN'), 'task': env.get('TASK_RUNNER_TASK'),
        'invocation': str(directory), 'hook_log': 'hooks/hooks.jsonl', 'sources': sources,
        'note': 'Native hooks are observational. Empty logs mean no events observed, not inactivity. '
                'Inspect stderr for hook trust/configuration warnings; Codex stdout.log also has tool events.'}))
    return updated


def read_events(directory, limit=20):
    """Bound retained memory; tolerate async partial lines and malformed external telemetry."""
    rows = deque(maxlen=limit)
    paths = [Path(directory) / 'hooks.jsonl.1', Path(directory) / 'hooks.jsonl']
    for path in paths:
        try:
            with path.open() as source:
                for line in source:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            pass
    return list(rows)


def render(run_path, task=None, limit=20):
    observations = []
    invocations = []
    for metadata in Path(run_path).rglob('activity.json'):
        try:
            info = record.read_json(metadata)
        except (OSError, ValueError):
            continue
        if task and info.get('task') != task:
            continue
        invocations.append(info)
        for row in read_events(metadata.parent / 'hooks', limit):
            stamp = str(row.get('ts') or row.get('timestamp') or '')
            event = row.get('event') or row.get('hook_event_name') or 'unknown'
            summary = row.get('result') or row.get('payload', {}).get('summary') or row.get('tool_name') or ''
            summary = ' '.join(str(summary).split())[:300]
            observations.append((stamp, f"{stamp} {info.get('task', '?')} {event} {summary}"))
    lines = [f"Agent activity: {len(invocations)} invocation(s); observational only."]
    lines.extend(text for _, text in sorted(observations)[-limit:])
    if not observations:
        lines.append('No hook or exec-stream events observed. Check invocation activity.json, stderr.log, and stdout.log.')
    return proc.redact(('\n'.join(lines)+'\n').encode()).decode()


class CodexTelemetry:
    """Use the existing passive logger for exec events when native hooks are absent.

    These rows retain an explicit exec-stream origin: they never pretend to be native hooks.
    """
    def __init__(self, cwd, env):
        self.env = env
        # Execute only the logger shipped beside this runner, never an arbitrary target-repo script.
        self.logger = Path(__file__).resolve().parents[3] / '.codex/statusline.py'
        self.session_id = None

    def feed(self, data):
        for line in data.splitlines():
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    continue
                if event.get('type') not in {'thread.started', 'turn.started', 'turn.completed',
                                              'turn.failed', 'error', 'item.started', 'item.completed'}:
                    continue
                if event.get('type') == 'thread.started':
                    self.session_id = event.get('thread_id')
                item = event.get('item') if isinstance(event.get('item'), dict) else {}
                payload = {'hook_event_name': 'ExecStream.' + str(event.get('type', 'unknown')),
                           'source': 'codex-exec-stream', 'session_id': self.session_id,
                           'tool_name': item.get('type'), 'tool_use_id': item.get('id'),
                           'summary': item.get('command') or item.get('text') or event.get('type'),
                           'event': event}
                subprocess.run([sys.executable, '-S', '-E', str(self.logger), '--hook'],
                               input=json.dumps(payload).encode(), env=self.env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=3, check=False)
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass
