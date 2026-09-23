"""Observed capabilities and their durable cache. Probes run only in scratch repositories.

The profile, model, read-only mode, binary contents/version and host identity form the cache key.
An answer or event claiming tool use grants no capability: each probe has its own observed effect.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import tempfile
import uuid

from . import agents, gitops, proc, record, validate, activity

PROBE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["value"],
                "properties": {"value": {"type": "string"}}}
CACHE_VERSION = 2
CAPABILITIES = ("answer", "read", "execute", "write", "resume", "boundary")


def host_identity():
    try:
        machine = Path('/etc/machine-id').read_text().strip()
    except OSError:
        machine = platform.node()
    return hashlib.sha256((machine + '|' + platform.system() + '|' + platform.release()
                           + '|' + platform.machine()).encode()).hexdigest()


def effective_profile(profile, root):
    profile = dict(profile)
    argv = list(profile.get('argv') or [profile['kind']])
    for n, arg in enumerate(argv):
        path = os.path.join(root, arg)
        if os.path.isfile(path):
            argv[n] = os.path.abspath(path)
    profile['argv'] = argv
    return profile


def fingerprint(profile, model, read_only, root):
    profile = effective_profile(profile, root)
    argv = profile['argv']
    binary = shutil.which(argv[0]) or argv[0]
    files = {}
    for arg in [binary] + argv[1:]:
        if os.path.isfile(arg):
            files[os.path.realpath(arg)] = record.sha256_file(arg)
    version = 'command (identified by executable and argument-file hashes)'
    if profile['kind'] in ('claude', 'codex'):
        try:
            res = subprocess.run(argv + ['--version'], stdin=subprocess.DEVNULL,
                                 capture_output=True, timeout=5, check=False)
            version = proc.redact((res.stdout + res.stderr)[:4000]).decode('utf-8', errors='replace')
        except (OSError, subprocess.TimeoutExpired) as exc:
            version = str(exc)
    config_hashes = {}
    candidates = []
    if profile['kind'] == 'codex':
        if not profile.get('ignore_user_config'):
            candidates.append(Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))) / 'config.toml')
        candidates.append(Path(root)/'.codex'/'config.toml')
    elif profile['kind'] == 'claude':
        if not profile.get('ignore_user_config'):
            candidates.append(Path.home()/'.claude'/'settings.json')
        candidates.extend([Path(root)/'.claude'/'settings.json', Path(root)/'.claude'/'settings.local.json'])
    candidates.extend(activity.assets(root, profile["kind"]))
    for path in candidates:
        if path.is_file():
            config_hashes[str(path)] = record.sha256_file(path)
    metadata = {'cache_version': CACHE_VERSION, 'profile': profile, 'model': model,
                'read_only': read_only, 'host': host_identity(), 'version': version, 'root': os.path.abspath(root),
                'binaries': files, 'config_hashes': config_hashes, 'capabilities': list(CAPABILITIES),
                'adapter_sha256': record.sha256_file(agents.__file__),
                'observer_sha256': record.sha256_file(activity.__file__)}
    key = hashlib.sha256(record.dump_json(metadata)).hexdigest()
    return key, metadata


def empty_spend():
    return {'known_usd': 0.0, 'unpriced': {'calls': 0, 'unknown_calls': 0,
                                        'tokens_in': 0, 'tokens_out': 0}}


def add_spend(spend, result):
    if result.cost_usd is not None:
        spend['known_usd'] += result.cost_usd
    elif result.status != agents.ENVIRONMENT:
        unpriced = spend['unpriced']
        unpriced['calls'] += 1
        unpriced['unknown_calls'] += not bool(result.usage)
        unpriced['tokens_in'] += result.usage.get('tokens_in', 0)
        unpriced['tokens_out'] += result.usage.get('tokens_out', 0)


def qualify(name, metadata, directory, timeout_s=60, budget_usd=1):
    profile, model, read_only = metadata['profile'], metadata['model'], metadata['read_only']
    agent = agents.make(name, profile)
    capabilities, probes = [], {}
    spend = empty_spend()
    os.makedirs(directory)
    with tempfile.TemporaryDirectory(prefix='task-runner-doctor-') as tmp:
        root = Path(tmp)
        # Qualify with the workflow's project settings as well as the inherited user settings.
        # Store only hashes in metadata; configuration contents never enter logs or prompts.
        project = Path(metadata['root'])
        for source in activity.assets(project, profile['kind']):
            relative = source.relative_to(project)
            if source.is_file():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'init', '-q', tmp], check=True)
        sequence = 0
        unavailable = None

        def call(probe, instruction, *, session_id=None, **data):
            nonlocal sequence, unavailable
            if unavailable is not None:
                return agents.AgentResult(unavailable[0],
                    error="not probed after provider failure: " + unavailable[1]), None
            sequence += 1
            inv = os.path.join(directory, f'invocation-{sequence}')
            os.mkdir(inv)
            prompt = json.dumps({'task_runner_probe': probe, 'instruction': instruction,
                                 'answer_format': {'value': 'string'}, **data})
            record.write_durable(os.path.join(inv, 'prompt.md'), prompt.encode())
            result = agent.run(prompt, cwd=tmp, invocation_dir=inv, schema=PROBE_SCHEMA,
                               session_id=session_id, model=model, timeout_s=timeout_s,
                               budget_usd=budget_usd, read_only=read_only,
                               env=agents.agent_env(os.environ, 'doctor', name))
            add_spend(spend, result)
            if result.status in (agents.ENVIRONMENT, agents.QUOTA):
                unavailable = result.status, result.error
            record.write_durable(os.path.join(inv, 'outcome.json'), record.dump_json(result.outcome()))
            valid = result.status == agents.OK and not validate.check_shape(result.structured, PROBE_SCHEMA)
            return result, result.structured['value'] if valid else None

        def observe(cap, result, passed):
            probes[cap] = {'passed': bool(passed), 'status': result.status, 'error': result.error}
            if passed:
                capabilities.append(cap)

        nonce = secrets.token_hex(24)
        first, value = call('answer', 'Return exactly the value below. Remember it for a later turn.', value=nonce)
        observe('answer', first, value == nonce)
        # Do not repeatedly call a broken environment. No untested capability is granted.
        if first.status not in (agents.ENVIRONMENT, agents.QUOTA):
            secret = secrets.token_hex(24)
            (root / 'read-probe.txt').write_text(secret)
            result, value = call('read', 'Read the file and return its exact contents as value.', path='read-probe.txt')
            observe('read', result, value == secret)
            data, key = secrets.token_hex(32), secrets.token_hex(16)
            (root / 'execute-input.txt').write_text(data)
            (root / 'execute-probe.py').write_text(
                'import hashlib, pathlib\n'
                'data = pathlib.Path("execute-input.txt").read_bytes()\n'
                f'pathlib.Path("execute-result.txt").write_text(hashlib.sha256(data).hexdigest()+":"+{key!r})\n')
            result, value = call('execute', 'Run python3 execute-probe.py. Return value done.', command='python3 execute-probe.py')
            expected = hashlib.sha256(data.encode()).hexdigest() + ':' + key
            observe('execute', result, result.status == agents.OK and _read(root / 'execute-result.txt') == expected)
            if not read_only:
                nonce_write = secrets.token_hex(24)
                result, value = call('write', 'Write exactly the UTF-8 bytes of contents to path, with no trailing newline '
                                     'or other extra bytes. Verify the file bytes before returning value done.',
                                     path='write-probe.txt', contents=nonce_write)
                observe('write', result, result.status == agents.OK and _read(root / 'write-probe.txt') == nonce_write)
            if first.session_id and 'resume' in agent.capabilities():
                result, value = call('resume', 'Return the value you were asked to remember in the first turn.',
                                     session_id=first.session_id)
                observe('resume', result, value == nonce)
            if read_only:
                sentinel = secrets.token_hex(24)
                (root / 'sentinel.txt').write_text(sentinel)
                sentinel_mode = (root / 'sentinel.txt').stat().st_mode
                result, value = call('boundary', 'Attempt to replace sentinel.txt with CHANGED using your tools. '
                                     'If denied, report value denied. Do not merely say it is read-only.',
                                     path='sentinel.txt', contents='CHANGED')
                observe('boundary', result, result.status == agents.OK and _read(root / 'sentinel.txt') == sentinel
                        and (root / 'sentinel.txt').stat().st_mode == sentinel_mode)
    observed = sorted({str(row.get('event') or row.get('hook_event_name'))
                       for inv in Path(directory).glob('invocation-*')
                       for row in activity.read_events(inv / 'hooks', 1000)})
    result = {'capabilities': capabilities, 'probes': probes, 'spend': spend, 'metadata': metadata,
              'observed_activity': observed,
              'directory': directory, 'orphan_detection': 'strong' if platform.system() == 'Linux' else 'weaker (ps fallback)'}
    if profile['kind'] == 'claude' and not observed:
        cause, message = activity.diagnose_claude_silence(metadata['root'])
        result['activity_cause'] = {'cause': cause, 'message': message}
    return result


def _read(path):
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_text()
    except (OSError, UnicodeError):
        return None


def required(task, profile):
    if task['kind'] == 'review' and profile.get('review_mode') == 'provided_context':
        return {'answer'}
    return {'answer'} | set(task.get('requires', [])) | ({'boundary'} if task['kind'] == 'review' else set())


def check_workflow(wf, force=False, locked=False):
    runs = record.ensure_runs_dir(gitops.Git(wf.root).top)
    if locked:
        return _check_workflow(wf, force)
    with record.Lock(runs).acquire('doctor'):
        return _check_workflow(wf, force)


def _check_workflow(wf, force=False):
    git = gitops.Git(wf.root)
    runs = record.ensure_runs_dir(git.top)
    cache_path = os.path.join(runs, 'qualification-cache.json')
    try:
        cache = record.read_json(cache_path)
    except (OSError, ValueError):
        cache = {'entries': {}}
    report = {'profiles': {}, 'tasks': {}, 'problems': [], 'spend': empty_spend()}
    report_dir = os.path.join(runs, 'doctor', str(uuid.uuid4()))
    from .providers import model_for
    for task in wf.tasks:
        if task['kind'] not in ('produce', 'review'):
            continue
        problems = []
        usable = False
        for name in [task['agent']] + task.get('fallback_agents', []):
            profile = wf.agents[name]
            model = model_for(task, name, wf.agents)
            key, metadata = fingerprint(profile, model, task['kind'] == 'review', wf.root)
            if key not in report['profiles']:
                prior = cache['entries'].get(key)
                cached = bool(not force and prior and not any(
                    probe.get('status') == agents.QUOTA for probe in prior['probes'].values()))
                entry = cache['entries'].get(key) if cached else qualify(
                    name, metadata, os.path.join(report_dir, key),
                    timeout_s=min(60, task['timeout_min'] * 60), budget_usd=min(1, task['budget_usd']))
                if not cached:
                    cache['entries'][key] = entry
                    report['spend']['known_usd'] += entry['spend']['known_usd']
                    for field, value in entry['spend']['unpriced'].items():
                        report['spend']['unpriced'][field] += value
                report['profiles'][key] = dict(entry, cached=cached)
            entry = report['profiles'][key]
            if name == task['agent']:
                report['tasks'][task['id']] = key
            report.setdefault('alternatives', {}).setdefault(task['id'], {})[name] = key
            missing = required(task, profile) - set(entry['capabilities'])
            if missing:
                cause = '; '.join(p['error'] for p in entry['probes'].values() if p.get('error'))
                problems.append(f"'{task['type']}' needs {', '.join(sorted(missing))}; profile '{name}' "
                                          f"is qualified for {', '.join(entry['capabilities']) or 'nothing'}"
                                          + (f": {cause}" if cause else ''))
            usable = usable or not missing
        if not usable:
            report['problems'].extend(problems)
    record.write_durable(cache_path, proc.redact(record.dump_json(cache)))
    record.write_durable(os.path.join(runs, 'qualification.json'), proc.redact(record.dump_json(report)))
    return report


def attach_run(run, report):
    run.write_decision(os.path.join(run.path, 'qualification.json'), report)
    for tid, key in report['tasks'].items():
        entry = report['profiles'][key]
        run.state['tasks'][tid]['qualification_key'] = key
        run.state['tasks'][tid]['qualified'] = entry['capabilities']
        run.state['tasks'][tid]['provider_qualifications'] = {
            name: {'key': candidate, 'capabilities': report['profiles'][candidate]['capabilities']}
            for name, candidate in report.get('alternatives', {}).get(tid, {}).items()}

    run.state['spend']['known_usd'] += report['spend']['known_usd']
    for key, value in report['spend']['unpriced'].items():
        run.state['spend']['unpriced'][key] += value
    info = run.info
    info['agents'] = {key: entry['metadata'] for key, entry in report['profiles'].items()}
    record.write_durable(os.path.join(run.path, 'run.json'), record.dump_json(info))
    run.save()


def invalidate(run, task_id):
    key = run.state['tasks'][task_id].get('qualification_key')
    if not key:
        return
    path = os.path.join(record.runs_dir_for(run.info['git_toplevel']), 'qualification-cache.json')
    try:
        cache = record.read_json(path)
    except (OSError, ValueError):
        return
    cache['entries'].pop(key, None)
    record.write_durable(path, record.dump_json(cache))
    run.state['tasks'][task_id]['qualified'] = []
    run.state['needs_qualification'] = True
    run.save()
