"""BUD-01..05 and FAIL-05: reservations, unpriced calls and durable budget pauses."""
import copy
import json
import os
from unittest.mock import patch
from helpers import EngineCase, done
from test_panels import ONE, GOOD, PASS
from taskrunner import agents, budgets, record, workflow


class Priced(agents.CommandAgent):
    reports_cost = True

    def interpret(self, res):
        result=super().interpret(res)
        result.cost_usd=0.0 if result.structured and 'value' in result.structured else 1.0
        return result


class Budgets(EngineCase):
    HEADER = EngineCase.HEADER + 'read_only_args = ["--read-only"]\n'

    def setup_budget(self, amount, tasks=ONE):
        self.workflow(tasks,defaults=f'run_budget_usd={amount}\nbudget_usd=5')
        reviewers=[t['id'] for t in workflow.load(self.wf_path).tasks if t['kind']=='review']
        self.script({'make':[GOOD],**{rid:[PASS] for rid in reviewers}})
        self.addCleanup(agents.REGISTRY.__setitem__,'command',agents.CommandAgent)
        agents.REGISTRY['command']=Priced
        return reviewers

    def count(self,tid):
        try:
            with open(self.script_path+'.'+tid+'.counter') as fh:return int(fh.read())
        except FileNotFoundError:return 0

    def test_reservations_prevent_dispatch_and_resume_preserves_completed_review(self):
        a,b=self.setup_budget(6)
        self.assertEqual(self.start(),2,self.output)
        run=self.the_run()
        self.assertEqual(run.state['status'],'stopped')
        self.assertEqual(run.state['active_producer'],'make')
        self.assertEqual((self.count('make'),self.count(a),self.count(b)),(1,1,0))
        self.assertEqual(run.state['spend']['known_usd'],2)
        self.assertEqual(run.state['spend']['reserved_usd'],0)
        self.check_invariants()
        self.assertEqual(self.resume('--add-budget','20'),0,self.output)
        self.assertEqual((self.count('make'),self.count(a),self.count(b)),(1,1,1))
        self.assertEqual(self.the_run().state['run_budget_usd'],26)
        with open(os.path.join(run.path,'events.jsonl')) as fh:
            self.assertIn('budget-added',fh.read())
        self.check_invariants()

    def test_one_dollar_remaining_starts_no_five_dollar_review(self):
        a,b=self.setup_budget(5)
        original = Priced.interpret
        def four_dollar_author(agent, res):
            result = original(agent, res)
            if result.structured and 'outcome' in result.structured:
                result.cost_usd = 4
            return result
        with patch.object(Priced, 'interpret', four_dollar_author):
            self.assertEqual(self.start(),2,self.output)
        self.assertEqual((self.count(a),self.count(b)),(0,0))
        self.assertEqual(self.the_run().state['spend']['known_usd'],4)
        self.check_invariants()

    def test_budget_before_first_producer_call_uses_no_attempt(self):
        self.setup_budget(1)
        self.assertEqual(self.start(),2,self.output)
        st=self.the_run().state['tasks']['make']
        self.assertEqual(st['attempts_used'],0)
        self.assertEqual(self.count('make'),0)
        self.assertEqual(self.resume('--add-budget','20'),0,self.output)
        self.assertEqual(self.the_run().state['tasks']['make']['attempts'],1)
        self.check_invariants()

    def test_budget_increase_requires_unchanged_paused_tree(self):
        self.setup_budget(5)
        self.assertEqual(self.start(),2,self.output)
        self.write('src/a','changed by owner\n')
        self.assertEqual(self.resume('--add-budget','20'),2,self.output)
        self.assertIn('work tree changed',self.output)
        self.assertEqual(self.the_run().state['run_budget_usd'],5)
        for amount in ('-1','nan','inf'):
            self.assertEqual(self.resume('--add-budget',amount),2)

    def test_interrupted_call_releases_reservation_as_unknown_usage(self):
        self.setup_budget(20)
        class Killed(Exception):pass
        def crash(point):
            if point=='agent:running':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.start()
        run=self.the_run()
        self.assertEqual(run.state['spend']['reserved_usd'],5)
        from taskrunner import gitops
        record.reconcile(run,gitops.Git(self.root),stop_orphans=True,grace_s=.1)
        self.assertEqual(run.state['spend']['reserved_usd'],0)
        self.assertEqual(run.state['spend']['unpriced']['unknown_calls'],1)
        record.reconcile(run,gitops.Git(self.root))
        self.assertEqual(run.state['spend']['unpriced']['unknown_calls'],1)

    def test_interrupted_call_with_a_provider_record_is_not_unknown_usage(self):
        """bud: the usage of an interrupted call is read from the provider's record (G4, BUD-07)"""
        self.setup_budget(20)
        class Killed(Exception):pass
        def crash(point):
            if point=='agent:running':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.start()
        run=self.the_run()
        it=next(i for i in run.state['intents'] if i['kind']=='agent')
        self.assertEqual(it['agent_kind'],'command')
        from taskrunner import gitops
        with patch.object(agents,'partial_usage',return_value={'tokens_in':1234,'tokens_out':56}) as reader:
            lines=record.reconcile(run,gitops.Git(self.root),stop_orphans=True,grace_s=.1)
        self.assertEqual(reader.call_args.args[0],'command')
        self.assertAlmostEqual(reader.call_args.args[2],agents._epoch(it['at']))
        unpriced=run.state['spend']['unpriced']
        self.assertEqual((unpriced['unknown_calls'],unpriced['tokens_in'],unpriced['tokens_out']),(0,1234,56))
        self.assertEqual(run.state['spend']['reserved_usd'],0)
        self.assertTrue(any('it had used 1234 tokens in, 56 out' in l for l in lines),lines)
        outcome=record.read_json(os.path.join(run.path,it['invocation_dir'],'outcome.json'))
        self.assertEqual((outcome['status'],outcome['usage_source']),('interrupted','provider-record'))
        self.cli.CRASH=None
        self.assertEqual(self.resume(),0,self.output)
        self.check_invariants()

    def test_unpriced_usage_is_not_invented_dollars(self):
        self.workflow(ONE.replace('reviewers=["principal-engineer", "spec-compliance"]',''))
        self.script([GOOD])
        self.assertEqual(self.start(),0,self.output)
        state=self.the_run().state
        self.assertEqual(state['spend']['known_usd'],0)
        self.assertGreaterEqual(state['spend']['unpriced']['calls'],1)  # includes doctor probes
        state=copy.deepcopy(state)
        budgets.settle(state,'make',0,agents.AgentResult(agents.OK,usage={'tokens_in':17,'tokens_out':3}))
        self.assertEqual(state['spend']['known_usd'],0)
        self.assertEqual(state['spend']['unpriced']['tokens_in'],17)

    def test_validate_warns_that_dollar_limits_do_not_bind_on_command_agents(self):
        self.workflow(ONE)
        wf=workflow.load(self.wf_path)
        self.assertTrue(any('dollar limits do not bind' in w for w in wf.warnings))
        for amount in ('nan','inf','-1','0'):
            self.workflow(ONE,defaults=f'run_budget_usd={amount}')
            self.assertTrue(any('finite and greater than zero' in e for e in workflow.load(self.wf_path).errors))


class Metered(agents.CommandAgent):
    """Reports no dollar cost, like Codex, but reports usage: 1000 tokens in and 100 out per call."""

    def interpret(self, res):
        result=super().interpret(res)
        result.usage={'tokens_in':1000,'tokens_out':100}
        return result


class TokenCap(EngineCase):
    HEADER = EngineCase.HEADER + 'read_only_args = ["--read-only"]\n'

    PROBES = 8 * 1100   # doctor's qualification probes are charged to the run too (BUD-03)

    def setup_cap(self, cap, tasks=ONE):
        self.workflow(tasks,defaults=f'run_budget_tokens={cap + self.PROBES}')
        reviewers=[t['id'] for t in workflow.load(self.wf_path).tasks if t['kind']=='review']
        self.script({'make':[GOOD],**{rid:[PASS] for rid in reviewers}})
        self.addCleanup(agents.REGISTRY.__setitem__,'command',agents.CommandAgent)
        agents.REGISTRY['command']=Metered
        return reviewers

    def used(self):
        unpriced=self.the_run().state['spend']['unpriced']
        return unpriced['tokens_in']+unpriced['tokens_out']

    def test_token_cap_stops_before_the_next_call_and_resume_adds_tokens(self):
        """bud: a token cap for agents that report no cost (BUD-06)"""
        a,b=self.setup_cap(1000)
        self.assertEqual(self.start(),2,self.output)                 # the producer's call crossed the line
        run=self.the_run()
        self.assertEqual(run.state['status'],'stopped')
        self.assertTrue(run.state['stop_reason'].startswith('the token cap'),run.state['stop_reason'])
        self.assertIn(f'{1100 + self.PROBES} of {1000 + self.PROBES} tokens',self.output)
        self.assertIn('runner resume --add-tokens N',self.output)
        self.assertEqual(self.status(a),'pending')
        self.assertEqual(self.status(b),'pending')
        self.assertEqual(run.state['spend']['known_usd'],0)          # no invented dollars
        with open(os.path.join(run.path,'STATUS.md')) as fh:
            status=fh.read()
        self.assertIn(f'cap {1000 + self.PROBES} tokens',status)
        self.assertIn('--add-tokens N',status)
        self.assertNotIn('--add-budget',status)
        self.check_invariants()
        self.assertEqual(self.resume(),2,self.output)                # nothing added: stops again at once
        self.assertEqual(self.resume('--add-tokens','5000'),0,self.output)
        self.assertEqual(self.the_run().state['run_budget_tokens'],6000 + self.PROBES)
        self.assertEqual(self.status('make'),'accepted')
        with open(os.path.join(run.path,'events.jsonl')) as fh:
            events=[json.loads(l) for l in fh if l.strip()]
        added=[e for e in events if e['event']=='budget-added']
        self.assertEqual(added[0]['amount_tokens'],5000)
        self.assertEqual(added[0]['budget_tokens'],6000 + self.PROBES)
        self.assertEqual(self.the_run().state['spend']['known_usd'],0)
        self.check_invariants()

    def test_the_cap_is_a_stop_line_reviews_that_fit_start_together(self):
        a,b=self.setup_cap(1500)
        self.assertEqual(self.start(),0,self.output)                 # 1100 < 1500 when the batch starts
        self.assertEqual(self.used(),3300 + self.PROBES)
        self.assertEqual(self.status('make'),'accepted')

    def test_no_cap_means_no_stop_and_nothing_to_add_to(self):
        self.setup_cap(-self.PROBES, ONE + '[[task]]\nid="look"\ntype="human"\nverifies="make"\n')
        self.assertEqual(self.start(),255,self.output)               # run_budget_tokens = 0: waits on the person
        self.assertEqual(self.used(),3300 + self.PROBES)
        self.assertEqual(self.resume('--add-tokens','5'),2)
        self.assertIn('no token cap',self.output)
        self.assertEqual(self.resume('--add-tokens','-1'),2)

    def test_validate_checks_the_cap_and_names_it_in_the_warning(self):
        self.workflow(ONE,defaults='run_budget_tokens=-1')
        self.assertTrue(any("'run_budget_tokens' must be 0 (no cap) or more" in e
                            for e in workflow.load(self.wf_path).errors))
        self.workflow(ONE,defaults='run_budget_tokens=2.5')
        self.assertTrue(any("'run_budget_tokens' must be" in e for e in workflow.load(self.wf_path).errors))
        self.workflow(ONE,defaults='run_budget_tokens=200000')
        warnings=workflow.load(self.wf_path).warnings
        self.assertTrue(any('stops the run once 200000 tokens' in w for w in warnings),warnings)
        self.workflow(ONE)
        self.assertTrue(any('set run_budget_tokens to cap' in w for w in workflow.load(self.wf_path).warnings))
