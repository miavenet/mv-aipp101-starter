"""Out-of-band qualification and gate preflight (PRE-01 to PRE-08). No model calls."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from helpers import EngineCase, RepoCase, done, run_cli
from taskrunner import activity, agents, gitops, preflight, qualification, record

PROBE_AGENT = str(Path(__file__).with_name('probe_agent.py'))
TASK = '[[task]]\nid="make"\ntype="implement"\nprompt="p"\noutputs=["out.txt"]\ngate=["true"]\n'

class Qualification(RepoCase):
    def workflow(self, agent=PROBE_AGENT, tasks=TASK, **profile):
        extra = ''.join(f'{key} = {json.dumps(value)}\n' for key, value in profile.items())
        return self.load('name="probe"\n[defaults]\nagent="probe"\n[agents.probe]\n'
                         + f'argv = [{json.dumps(sys.executable)}, {json.dumps(agent)}]\n' + extra + tasks)

    def test_observed_effects_and_cache(self):
        wf = self.workflow()
        self.assertLoads(wf)
        report = qualification.check_workflow(wf)
        self.assertEqual(report['problems'], [])
        entry = next(iter(report['profiles'].values()))
        self.assertEqual(set(entry['capabilities']), {'answer', 'read', 'execute', 'write'})
        self.assertFalse(entry['cached'])
        self.assertEqual(entry['spend']['unpriced']['calls'], 4)
        with patch.object(agents.CommandAgent, 'run', side_effect=AssertionError('cache called agent')):
            cached = qualification.check_workflow(wf)
        self.assertTrue(next(iter(cached['profiles'].values()))['cached'])
        self.assertEqual(cached['spend']['unpriced']['calls'], 0)
        refreshed = qualification.check_workflow(wf, force=True)
        self.assertFalse(next(iter(refreshed['profiles'].values()))['cached'])
        self.assertTrue(Path(self.root, '.runs', 'qualification.json').is_file())

    def test_a_greeting_and_fabricated_execution_are_not_capabilities(self):
        script = self.write('liar.py', '''import json, pathlib, sys
p=json.load(sys.stdin)
if p['task_runner_probe']=='execute': pathlib.Path('execute-result.txt').write_text('wrong digest')
print(json.dumps({'value':p.get('value','I did it')}))
''')
        wf = self.workflow(script)
        report = qualification.check_workflow(wf)
        caps = next(iter(report['profiles'].values()))['capabilities']
        self.assertEqual(caps, ['answer'])
        self.assertTrue(report['problems'])
        self.commit()
        res = run_cli('start', wf.workflow_file)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn('needs', res.stderr)
        self.assertFalse(Path(self.root, '.runs', 'probe').exists())

    def test_profile_binary_model_and_host_change_the_cache_key(self):
        wf = self.workflow()
        p = wf.agents['probe']
        first, meta = qualification.fingerprint(p, 'm', False, self.root)
        self.assertNotEqual(first, qualification.fingerprint(p, 'm2', False, self.root)[0])
        self.assertNotEqual(first, qualification.fingerprint(p, 'm', True, self.root)[0])
        self.assertNotEqual(first, qualification.fingerprint(dict(p, extra_args=['--flag']), 'm', False, self.root)[0])
        with patch.object(qualification, 'host_identity', return_value='other host'):
            self.assertNotEqual(first, qualification.fingerprint(p, 'm', False, self.root)[0])
        agent = self.write('agent.py', 'print(1)')
        p = dict(p, argv=[sys.executable, agent])
        old = qualification.fingerprint(p, '', False, self.root)[0]
        self.write('agent.py', 'print(2)')
        self.assertNotEqual(old, qualification.fingerprint(p, '', False, self.root)[0])

    def test_boundary_is_observed_in_the_read_only_profile(self):
        wf = self.workflow(read_only_args=['--read-only'])
        key, meta = qualification.fingerprint(wf.agents['probe'], '', True, self.root)
        directory = os.path.join(self.root, 'qualification')
        good = qualification.qualify('probe', meta, directory)
        self.assertIn('boundary', good['capabilities'])
        meta['profile']['read_only_args'] = []
        bad = qualification.qualify('probe', meta, directory + '-bad')
        self.assertNotIn('boundary', bad['capabilities'])

    def test_provided_context_requires_only_answer(self):
        task = {'kind':'review','requires':['read','execute']}
        self.assertEqual(qualification.required(task, {'review_mode':'provided_context'}), {'answer'})
        self.assertEqual(qualification.required(task, {}), {'answer','read','execute','boundary'})

    def test_resume_uses_the_explicit_session_and_old_value(self):
        class Resumable(agents.CommandAgent):
            def capabilities(self):
                return super().capabilities() | {'resume'}
            def interpret(self, result):
                answer = super().interpret(result)
                answer.session_id = 'explicit-session'
                return answer
        wf = self.workflow()
        with patch.dict(agents.REGISTRY, command=Resumable):
            report = qualification.check_workflow(wf)
        self.assertIn('resume', next(iter(report['profiles'].values()))['capabilities'])

    def test_probes_stop_after_an_environment_failure(self):
        wf = self.workflow()
        original = agents.CommandAgent.run
        calls = []
        def sandbox_failure(agent, prompt, **kwargs):
            probe = json.loads(prompt)['task_runner_probe']
            calls.append(probe)
            if probe == 'answer':
                return original(agent, prompt, **kwargs)
            return agents.AgentResult(agents.ENVIRONMENT, error='sandbox failed to start')
        with patch.object(agents.CommandAgent, 'run', sandbox_failure):
            report = qualification.check_workflow(wf)
        self.assertEqual(calls, ['answer', 'read'])
        self.assertEqual(next(iter(report['profiles'].values()))['capabilities'], ['answer'])

    def test_doctor_cli_is_model_free_for_command_profiles(self):
        wf = self.workflow()
        self.commit()
        first = run_cli('doctor', wf.workflow_file)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn('answer, read, execute, write', first.stdout)
        second = run_cli('doctor', wf.workflow_file)
        self.assertIn('(cached)', second.stdout)

    def test_doctor_names_the_detected_cause_of_claude_silence(self):
        wf = self.workflow(kind='claude')
        self.commit()
        with patch.dict(agents.REGISTRY, claude=agents.CommandAgent):
            report = qualification.check_workflow(wf)
        entry = next(iter(report['profiles'].values()))
        self.assertEqual(entry['observed_activity'], [])
        self.assertEqual(entry['activity_cause'], {'cause': activity.NO_HOOKS,
            'message': activity.diagnose_claude_silence(self.root)[1]})
        import contextlib
        import io
        from taskrunner import cli
        out = io.StringIO()
        with patch.dict(agents.REGISTRY, claude=agents.CommandAgent), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['doctor', wf.workflow_file]), 0)
        self.assertIn('observed activity: none; the work tree has no .claude/settings.json', out.getvalue())

    def test_check_workflow_survives_malformed_project_hook_settings(self):
        wf = self.workflow(kind='claude')
        os.makedirs(os.path.join(self.root, '.claude'), exist_ok=True)
        with open(os.path.join(self.root, '.claude', 'settings.json'), 'w') as fh:
            fh.write('{"hooks": ' + '[' * 10000 + ']' * 10000 + '}')
        self.commit()
        with patch.dict(agents.REGISTRY, claude=agents.CommandAgent):
            report = qualification.check_workflow(wf)
        entry = next(iter(report['profiles'].values()))
        self.assertEqual(entry['activity_cause']['cause'], activity.INSPECTION_FAILED)
        self.assertEqual(report['problems'], [])

class Invalidation(EngineCase):
    def test_environment_failure_discards_cached_qualification(self):
        self.workflow(TASK)
        self.script([{'write':{'out.txt':'done'},'answer':done()}])
        original = agents.CommandAgent.run
        def broken(agent, prompt, **kwargs):
            if 'task_runner_probe' in prompt:
                return original(agent, prompt, **kwargs)
            return agents.AgentResult(agents.ENVIRONMENT, error='sandbox failed to start')
        with patch.object(agents.CommandAgent, 'run', broken):
            self.assertEqual(self.start(), 2, self.output)
        run = self.the_run()
        key = run.state['tasks']['make']['qualification_key']
        cache = record.read_json(os.path.join(self.root, '.runs', 'qualification-cache.json'))
        self.assertNotIn(key, cache['entries'])
        self.assertEqual(run.state['tasks']['make']['attempts_used'], 0)
        self.assertTrue(run.state['needs_qualification'])
        self.assertEqual(self.resume(), 0, self.output)
        self.check_invariants()

class GatePreflight(RepoCase):
    def workflow(self, gates, checks=''):
        wf = self.load('name="gates"\n[[task]]\nid="make"\ntype="implement"\n'
                       'prompt="p"\noutputs=["out.txt"]\ngate=[' + ','.join(gates) + ']\n' + checks)
        self.assertLoads(wf)
        self.commit()
        return wf

    def test_new_and_invariant_gates(self):
        wf = self.workflow(['"true"', '{run="echo intended; exit 1",new=true,fail_pattern="intended"}',
                            '{run="true",new=true,fail_pattern="intended"}'])
        report = preflight.check_gates(wf)
        self.assertEqual([r['result'] for r in report['results']], ['pass','fail','objection'])
        self.assertTrue(report['results'][1]['fails_as_intended'])
        self.assertFalse(report['ok'])

    def test_the_same_command_is_checked_once(self):
        wf = self.workflow(['"true"', '"true"', '{run="true",new=true,fail_pattern="x"}'],
                           '[[task]]\nid="also"\ntype="implement"\nprompt="p"\noutputs=["b.txt"]\ngate=["true"]\n')
        report = preflight.check_gates(wf)
        self.assertEqual([(r['id'], r['result'], r.get('same_as')) for r in report['results']],
                         [('make:gate:1', 'pass', None), ('make:gate:2', 'pass', 'make:gate:1'),
                          ('make:gate:3', 'objection', None), ('also:gate:1', 'pass', 'make:gate:1')])
        logs = [f for f in os.listdir(report['directory']) if f.endswith('.log')]
        self.assertEqual(len(logs), 2)                 # `new` gates are always run on their own

    def test_wrong_failures_are_errors(self):
        wf = self.workflow(['{run="nonexistent-command-xyz",new=true,fail_pattern="missing"}',
                            '{run="exit 126",new=true,fail_pattern="."}',
                            '{run="echo ModuleNotFoundError; exit 1",new=true,fail_pattern="expected assertion"}'])
        report = preflight.check_gates(wf)
        self.assertEqual([r['result'] for r in report['results']], ['error'] * 3)

    def test_litter_is_reported_and_original_tree_untouched(self):
        wf = self.workflow(['"echo bad > README.md; echo stray > junk.txt"', '"grep -qx scratch README.md"'])
        original = Path(self.root, 'README.md').read_bytes()
        report = preflight.check_gates(wf)
        self.assertEqual(report['results'][0]['result'], 'error')
        self.assertIn('junk.txt', ' '.join(report['results'][0]['changed_paths']))
        self.assertEqual(report['results'][1]['result'], 'pass')
        self.assertEqual(Path(self.root, 'README.md').read_bytes(), original)
        self.assertFalse(Path(self.root, 'junk.txt').exists())
        self.assertTrue(gitops.Git(self.root).is_clean())

    def test_timeout_is_an_error(self):
        wf = self.workflow(['{run="sleep 60",new=true,fail_pattern="."}'])
        wf.tasks[0]['gate_timeout_min'] = .001
        self.assertEqual(preflight.check_gates(wf)['results'][0]['result'], 'error')

    def test_check_gates_runs_standalone_checks_too(self):
        wf = self.workflow(['"true"'], '[[task]]\nid="check"\ntype="check"\nrun=["true"]\n')
        result = run_cli('check-gates', wf.workflow_file)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('check:check:1: pass', result.stdout)

if __name__ == '__main__':
    unittest.main()
