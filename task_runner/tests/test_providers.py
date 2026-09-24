"""Provider routing scenarios: deterministic, no paid model calls."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from helpers import EngineCase, RepoCase, done
from taskrunner import agents, workflow
from test_headless import result
from test_findings import review, finding, resolution

ONE = '''
[[task]]
id="make"
type="implement"
prompt="Make the file"
outputs=["src/a"]
fallback_agents=["backup"]
complexity="high"
gate=["test -f src/a"]
'''


class Routing(EngineCase):
    HEADER = EngineCase.HEADER + '''read_only_args=["--read-only"]
[agents.backup]
argv=[{python!r}, {agent!r}]
read_only_args=["--read-only"]
model="backup-model"
'''

    def quota_patch(self, predicate):
        original = agents.CommandAgent.run
        calls = []
        def run(agent, prompt, **kwargs):
            answer = original(agent, prompt, **kwargs)
            if kwargs['env'].get('TASK_RUNNER_RUN') != 'doctor':
                calls.append((agent.name, kwargs['model'], kwargs['session_id'], kwargs['read_only']))
                if predicate(agent, prompt, kwargs, calls):
                    answer.status, answer.error = agents.QUOTA, 'usage_limit_reached'
                    answer.session_id = 'old-provider-session'
            return answer
        self.addCleanup(patch.stopall)
        patch.object(agents.CommandAgent, 'run', run).start()
        return calls

    def test_partial_work_survives_quota_in_one_attempt(self):
        """Given saved work and quota, fallback completes it without a new task attempt."""
        self.workflow(ONE)
        self.script([{'write': {'src/a': 'retained'}, 'answer': done()}, {'answer': done()}])
        calls = self.quota_patch(lambda a, p, kw, c: a.name == 'fake')
        self.assertEqual(self.start(), 0, self.output)
        st = self.the_run().state['tasks']['make']
        self.assertEqual(st['attempts_used'], 1)
        self.assertEqual(st['selected_provider'], 'backup')
        self.assertEqual(calls, [('fake', '', None, False), ('backup', 'backup-model', None, False)])
        self.assertEqual(Path(self.root, 'src/a').read_text(), 'retained')
        self.assertIn('Provider handoff', self.prompt(2))
        self.assertEqual(self.the_run().state['spend']['unpriced']['calls'], 2 + 8) # two calls plus two doctor profiles
        self.check_invariants()

    def test_exhaustion_retains_candidate_and_attempt_allowance(self):
        self.workflow(ONE)
        self.script([{'write': {'src/a': 'retained'}, 'answer': done()}, {'answer': done()}])
        self.quota_patch(lambda *args: True)
        self.assertEqual(self.start(), 2, self.output)
        run = self.the_run()
        self.assertIn('no qualified available fallback', run.state['stop_reason'])
        self.assertEqual(run.state['tasks']['make']['attempts_used'], 0)
        self.assertEqual(Path(self.root, 'src/a').read_text(), 'retained')
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.resume(), 2)
        self.assertEqual(self.calls(), 2) # cooldown prevents repeated calls

    def test_protocol_failure_does_not_switch(self):
        self.workflow(ONE)
        self.script([{'stdout': 'invalid'}] * 3 + [{'write': {'src/a': 'ok'}, 'answer': done()}])
        calls = self.quota_patch(lambda *args: False)
        self.assertEqual(self.start(), 0, self.output)
        self.assertTrue(all(c[0] == 'fake' for c in calls))
        self.assertNotIn('provider_history', self.the_run().state['tasks']['make'])
        self.check_invariants()

    def test_reviewer_switch_retains_read_only_and_identity(self):
        tasks = ONE.replace('fallback_agents=["backup"]', '') + '''
[[task]]
id="reviewer"
type="code-review"
perspective="principal-engineer"
reviews="make"
fallback_agents=["backup"]
'''
        self.workflow(tasks)
        self.script({'make': [{'write': {'src/a': 'ok'}, 'answer': done()}],
                     'reviewer': [{'answer': review()}, {'answer': review()}]})
        calls = self.quota_patch(lambda a, p, kw, c: kw['read_only'] and a.name == 'fake')
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual([c[0] for c in calls], ['fake', 'fake', 'backup'])
        self.assertTrue(calls[-1][3])
        ledger = self.read_json('make', 'findings.json')
        self.assertIn('reviewer', ledger['reviewers'])
        self.check_invariants()

    def test_resume_after_recorded_quota_and_selection_crashes(self):
        class Killed(BaseException):
            pass
        for point in ('provider:outcome-recorded', 'provider:selection-recorded'):
            with self.subTest(point=point):
                self.setUp()
                self.workflow(ONE)
                self.script([{'write': {'src/a': 'retained'}, 'answer': done()}, {'answer': done()}])
                calls = self.quota_patch(lambda a, p, kw, c: a.name == 'fake')
                def crash(where):
                    if where == point:
                        raise Killed()
                self.cli.CRASH = crash
                with self.assertRaises(Killed):
                    self.start()
                self.cli.CRASH = None
                self.assertEqual(self.resume(), 0, self.output)
                self.assertEqual([c[0] for c in calls], ['fake', 'backup'])
                self.assertEqual(self.the_run().state['tasks']['make']['attempts_used'], 1)
                self.check_invariants()
                patch.stopall()

    def test_unqualified_fallback_is_not_dispatched(self):
        from taskrunner import qualification
        original = qualification.qualify
        def qualify(name, *args, **kwargs):
            entry = original(name, *args, **kwargs)
            if name == 'backup':
                entry['capabilities'] = []
            return entry
        self.workflow(ONE)
        self.script([{'write': {'src/a': 'retained'}, 'answer': done()}])
        calls = self.quota_patch(lambda *args: True)
        with patch.object(qualification, 'qualify', qualify):
            self.assertEqual(self.start(), 2, self.output)
        self.assertEqual(len(calls), 1)
        self.assertIn('no qualified available fallback', self.output)

    def test_fallback_budget_is_reserved_before_dispatch(self):
        self.workflow(ONE, defaults='run_budget_usd=1\nbudget_usd=2')
        self.script([{'write': {'src/a': 'retained'}, 'answer': done()}])
        calls = self.quota_patch(lambda *args: True)
        with patch.object(agents.CommandAgent, 'reports_cost', property(lambda a: a.name == 'backup')):
            self.assertEqual(self.start(), 2, self.output)
        self.assertEqual(len(calls), 1)
        self.assertIn('budget cannot cover', self.output)
        self.assertEqual(self.the_run().state['tasks']['make']['attempts_used'], 0)

    def test_reviewer_fallback_preserves_open_findings(self):
        tasks = ONE.replace('fallback_agents=["backup"]', '') + """
[[task]]
id="reviewer"
type="code-review"
perspective="principal-engineer"
reviews="make"
fallback_agents=["backup"]
"""
        self.workflow(tasks)
        response = dict(finding='make/PE-1', action='fixed', note='Fixed')
        self.script({'make': [{'write': {'src/a': 'bad'}, 'answer': done()},
                             {'write': {'src/a': 'good'}, 'answer': done(responses=[response])}],
                     'reviewer': [{'answer': review([finding(location='src/a:1')])},
                                  {'answer': review(resolutions=[resolution()])},
                                  {'answer': review(resolutions=[resolution()])}]})
        self.quota_patch(lambda a, p, kw, c: a.name == 'fake' and kw['read_only']
                         and sum(x[3] for x in c) == 2)
        self.assertEqual(self.start(), 0, self.output)
        ledger = self.read_json('make', 'findings.json')
        self.assertEqual(ledger['findings'][0]['status'], 'resolved')
        self.assertEqual([e['event'] for e in ledger['findings'][0]['history']],
                         ['raised', 'response', 'resolution'])
        self.check_invariants()

    def test_qualification_quota_skips_remaining_probes_and_uses_fallback(self):
        self.workflow(ONE)
        self.script([{'write': {'src/a': 'ok'}, 'answer': done()}])
        original = agents.CommandAgent.run
        primary_calls = []
        def run(agent, prompt, **kwargs):
            answer = original(agent, prompt, **kwargs)
            if agent.name == 'fake':
                primary_calls.append(kwargs['env'].get('TASK_RUNNER_RUN'))
                answer.status, answer.error = agents.QUOTA, 'usage_limit_reached'
            return answer
        with patch.object(agents.CommandAgent, 'run', run):
            self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(primary_calls, ['doctor'])
        self.assertEqual(self.the_run().state['tasks']['make']['selected_provider'], 'backup')
        self.check_invariants()

    def test_complexity_model_is_qualified_and_dispatched(self):
        self.workflow(ONE.replace('[[task]]', '[model_policy.high]\ncommand="complex-model"\n[[task]]', 1))
        self.script([{'write': {'src/a': 'ok'}, 'answer': done()}, {'answer': done()}])
        calls = self.quota_patch(lambda a, p, kw, c: a.name == 'fake')
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual([c[1] for c in calls], ['complex-model', 'complex-model'])
        report = json.loads(Path(self.the_run().path, 'qualification.json').read_text())
        self.assertTrue(all(e['metadata']['model'] == 'complex-model' for e in report['profiles'].values()))

    def failure_patch(self, status, error, predicate):
        """Make the fake agent's answer a provider failure of `status` whenever `predicate` says."""
        original = agents.CommandAgent.run
        calls = []
        def run(agent, prompt, **kwargs):
            answer = original(agent, prompt, **kwargs)
            if kwargs['env'].get('TASK_RUNNER_RUN') != 'doctor':
                calls.append((agent.name, kwargs['read_only']))
                if predicate(agent, prompt, kwargs, calls):
                    answer.status, answer.error, answer.structured = status, error, None
            return answer
        self.addCleanup(patch.stopall)
        patch.object(agents.CommandAgent, 'run', run).start()
        return calls

    def review_events(self):
        with open(os.path.join(self.the_run().path, 'events.jsonl'), encoding='utf-8') as fh:
            events = [json.loads(line) for line in fh if line.strip()]
        return [e['status'] for e in events if e['event'] == 'review-call']

    REVIEWED = ONE.replace('fallback_agents=["backup"]', '') + '''
[[task]]
id="reviewer"
type="code-review"
perspective="principal-engineer"
reviews="make"
fallback_agents=["backup"]
'''

    def test_reviewer_transient_failure_is_retried_then_falls_back(self):
        """prov: a reviewer call that fails at the provider (PROV-11): retried, then the fallback"""
        self.workflow(self.REVIEWED)
        self.script({'make': [{'write': {'src/a': 'ok'}, 'answer': done()}],
                     'reviewer': [{'answer': review()}] * 3})
        calls = self.failure_patch(agents.TRANSIENT, 'Selected model is at capacity',
                                   lambda a, p, kw, c: kw['read_only'] and a.name == 'fake')
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual([c[0] for c in calls], ['fake', 'fake', 'fake', 'backup'])
        self.assertEqual(self.status('make'), 'accepted')
        self.assertEqual(self.status('reviewer'), 'accepted')
        self.assertEqual(self.review_events(), ['transient', 'transient', 'ok'])
        self.check_invariants()

    def test_reviewer_timeout_is_retried_like_a_provider_failure(self):
        """prov: a reviewer call that runs past its time limit (PROV-12) is not the panel's answer"""
        self.workflow(self.REVIEWED.replace('fallback_agents=["backup"]\n', ''))
        self.script({'make': [{'write': {'src/a': 'ok'}, 'answer': done()}],
                     'reviewer': [{'answer': review()}] * 3})
        calls = self.failure_patch(agents.TIMED_OUT, 'the call ran past its time limit',
                                   lambda a, p, kw, c: kw['read_only'] and len(c) == 2)
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual([c[0] for c in calls], ['fake', 'fake', 'fake'])
        self.assertEqual(self.status('reviewer'), 'accepted')
        self.check_invariants()

    def test_reviewer_failing_three_times_still_blocks(self):
        self.workflow(self.REVIEWED.replace('fallback_agents=["backup"]\n', ''))
        self.script({'make': [{'write': {'src/a': 'ok'}, 'answer': done()}],
                     'reviewer': [{'answer': review()}] * 3})
        self.failure_patch(agents.TRANSIENT, 'overloaded', lambda a, p, kw, c: kw['read_only'])
        self.assertEqual(self.start(), 255, self.output)
        self.assertEqual(self.status('make'), 'blocked')
        self.assertIn('review panel could not produce valid answers', self.output)

    def test_producer_transient_failure_uses_no_attempt(self):
        """prov: a producer call that fails at the provider (PROV-13): retried without an attempt"""
        self.workflow(ONE)
        self.script([{'write': {'src/a': 'ok'}, 'answer': done()}] * 3)
        calls = self.failure_patch(agents.TRANSIENT, 'API Error: 529 overloaded_error',
                                   lambda a, p, kw, c: a.name == 'fake')
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual([c[0] for c in calls], ['fake', 'fake', 'backup'])
        st = self.the_run().state['tasks']['make']
        self.assertEqual(st['attempts_used'], 1)
        self.assertEqual(st['status'], 'accepted')
        self.check_invariants()

    def test_producer_transient_failure_without_fallback_stops_the_run(self):
        self.workflow(ONE.replace('fallback_agents=["backup"]\n', ''))
        self.script([{'write': {'src/a': 'ok'}, 'answer': done()}] * 3)
        self.failure_patch(agents.TRANSIENT, 'at capacity', lambda a, p, kw, c: True)
        self.assertEqual(self.start(), 2, self.output)
        self.assertIn('the provider kept failing', self.output)
        self.assertIn('No attempt was used', self.output)
        self.assertEqual(self.the_run().state['tasks']['make']['attempts_used'], 0)
        self.assertEqual(self.resume(), 2)                       # still failing: still no attempt
        self.assertEqual(self.the_run().state['tasks']['make']['attempts_used'], 0)

    def test_transient_and_unreachable_classification(self):
        codex = agents.make('codex', {'kind': 'codex'})
        r = codex.interpret(result(b'{"type":"turn.failed","error":{"message":"Selected model is at capacity. Please try a different model."}}', code=1))
        self.assertEqual(r.status, agents.TRANSIENT)
        claude = agents.make('claude', {'kind': 'claude'})
        envelope = {'type': 'result', 'subtype': 'success', 'is_error': True, 'usage': {},
                    'result': "API Error: Can't reach the API server \u2014 check your internet or DNS (ENOTFOUND)"}
        self.assertEqual(claude.interpret(result(json.dumps(envelope).encode(), code=1)).status, agents.ENVIRONMENT)
        envelope['result'] = 'API Error: 529 {"type":"error","error":{"type":"overloaded_error"}}'
        self.assertEqual(claude.interpret(result(json.dumps(envelope).encode(), code=1)).status, agents.TRANSIENT)
        self.assertFalse(agents.transient_error('the test suite failed: connection handling is wrong'))
        self.assertTrue(agents.network_error("API Error: Can't reach the API server (ENOTFOUND)"))
        self.assertFalse(agents.network_error('invalid api key'))
        self.assertFalse(agents.network_error('sandbox failed to start'))


class ModelPolicy(RepoCase):
    def config(self, extra='', primary='codex', profile='kind="claude"\nmodel="fable"'):
        return self.load('''name="routing"
[model_policy.high]
codex="gpt-6-astra"
claude="fable"
[model_policy.mechanical]
claude="sonnet"
[agents.backup]
''' + profile + '\n[[task]]\nid="a"\ntype="implement"\nprompt="p"\noutputs=["x"]\ngate=["true"]\nagent="'+primary+'"\nfallback_agents=["backup"]\n' + extra)

    def test_normalized_policy_and_explicit_override(self):
        wf = self.config('complexity="high"')
        self.assertLoads(wf)
        self.assertEqual(wf.tasks[0]['provider_models'], {'codex': 'gpt-6-astra', 'backup': 'fable'})
        wf = self.config('complexity="high"\nmodel="gpt-5.6-sol"')
        self.assertLoads(wf)
        self.assertEqual(wf.tasks[0]['provider_models'], {'codex': 'gpt-5.6-sol', 'backup': 'fable'})
        wf = self.config('complexity="mechanical"', primary='claude')
        self.assertLoads(wf)
        self.assertEqual(wf.tasks[0]['provider_models']['claude'], 'sonnet')

    def test_reject_unknown_complexity_duplicate_and_wider_permissions(self):
        self.assertError(self.config('complexity="magic"'), 'complexity')
        self.assertError(self.config(primary='backup'), 'unique')
        self.assertError(self.config(profile='kind="claude"\nmodel="fable"\npermission_mode="bypassPermissions"'), 'widen')

class QuotaClassification(RepoCase):
    def test_codex_error_channel_only(self):
        a = agents.make('codex', {'kind': 'codex'})
        r = a.interpret(result(b'{"type":"turn.failed","error":{"code":"usage_limit_reached"}}', code=1))
        self.assertEqual(r.status, agents.QUOTA)
        r = a.interpret(result(b'{"type":"turn.failed","error":{"message":"ordinary failure"}}'))
        self.assertEqual(r.status, agents.AGENT_ERROR)
        r = a.interpret(result(b'{"type":"item.completed","item":{"type":"command_execution","exit_code":1,"aggregated_output":"usage_limit_reached"}}'))
        self.assertNotEqual(r.status, agents.QUOTA)

    def test_claude_quota_terminal_result(self):
        a = agents.make('claude', {'kind': 'claude'})
        envelope = {'type':'result','subtype':'error_during_execution','is_error':True,
                    'result':"You've hit your limit",'total_cost_usd':.1,'usage':{'output_tokens':5}}
        for code in (0, 1):
            r=a.interpret(result(json.dumps(envelope).encode(), code=code))
            self.assertEqual(r.status, agents.QUOTA)
            self.assertEqual(r.cost_usd, .1)
            self.assertEqual(r.usage['tokens_out'], 5)
        envelope.update(is_error=False, subtype='success', result=json.dumps(done("You've hit your limit")))
        self.assertEqual(a.interpret(result(json.dumps(envelope).encode())).status, agents.OK)
