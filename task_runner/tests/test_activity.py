"""Native hook routing, concurrent invocations, and passive telemetry contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import helpers
from taskrunner import activity, qualification

ROOT = Path(__file__).resolve().parents[2]


class Activity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fire(self, kind, directory, task, payload):
        directory.mkdir(exist_ok=True)
        env = activity.prepare(kind, str(ROOT), directory,
            dict(os.environ, TASK_RUNNER_RUN='test-run', TASK_RUNNER_TASK=task))
        script = (ROOT / '.claude/hooks/log-hook.py' if kind == 'claude' else ROOT / '.codex/statusline.py')
        argv = [sys.executable, '-S', '-E', str(script)] + (['--hook'] if kind == 'codex' else [])
        result = subprocess.run(argv, input=json.dumps(payload), text=True, capture_output=True, env=env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        return activity.read_events(directory / 'hooks')

    def test_native_loggers_correlate_and_redact_independent_invocations(self):
        payload = {'hook_event_name':'PreToolUse','session_id':'session','tool_name':'Bash',
                   'tool_input':{'api_key':'private-value', 'command':'echo ok'}}
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda kind:self.fire(kind,self.root/kind,kind,payload), ('claude','codex')))
        for kind, rows in zip(('claude','codex'), results):
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['task_runner']['task'], kind)
            self.assertEqual(rows[0]['task_runner']['run'], 'test-run')
            self.assertNotIn('private-value', json.dumps(rows))
            self.assertEqual((self.root/kind/'hooks/hooks.jsonl').stat().st_mode & 0o777,0o600)
        self.assertIn('claude PreToolUse', activity.render(self.root, 'claude'))
        self.assertNotIn('codex PreToolUse', activity.render(self.root, 'claude'))

    def test_empty_and_partial_logs_do_not_claim_inactivity_or_success(self):
        inv=self.root/'inv';inv.mkdir()
        activity.prepare('codex',str(ROOT),inv,{})
        self.assertIn('No hook or exec-stream events observed',activity.render(self.root))
        (inv/'hooks/hooks.jsonl').write_text('{"event":"Stop","timestamp":"1"}\n{"event":')
        self.assertEqual(len(activity.read_events(inv/'hooks')),1)
        self.assertIn('observational only',activity.render(self.root))

    def test_hook_changes_invalidate_qualification(self):
        folder=self.root/'.claude/hooks';folder.mkdir(parents=True)
        script=folder/'log-hook.py';script.write_text('# first')
        profile={'kind':'claude','argv':[sys.executable]}
        first=qualification.fingerprint(profile,'m',False,str(self.root))[0]
        script.write_text('# revised')
        self.assertNotEqual(first,qualification.fingerprint(profile,'m',False,str(self.root))[0])

    def test_codex_logger_failure_is_passive(self):
        target=self.root/'not-a-directory';target.write_text('x')
        result=subprocess.run([sys.executable,str(ROOT/'.codex/statusline.py'),'--hook'],input='{}',
            text=True,capture_output=True,env=dict(os.environ,CODEX_HOOK_LOG=str(target/'log')))
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'',''))

    def test_exec_stream_records_tool_command_without_claiming_native_hook(self):
        inv=self.root/'exec';inv.mkdir()
        env=activity.prepare('codex',str(ROOT),inv,dict(os.environ,TASK_RUNNER_TASK='tool-task'))
        telemetry=activity.CodexTelemetry(str(ROOT),env)
        telemetry.feed(b'{"type":"thread.started","thread_id":"abc"}\n')
        telemetry.feed(b'{"type":"item.completed","item":{"type":"command_execution","id":"1","command":"python3 test.py","exit_code":0}}\n')
        rows=activity.read_events(inv/'hooks')
        self.assertEqual(rows[-1]['payload']['source'],'codex-exec-stream')
        self.assertEqual(rows[-1]['session_id'],'abc')
        self.assertEqual(rows[-1]['hook_event_name'],'ExecStream.item.completed')
        self.assertIn('python3 test.py',activity.render(self.root))
