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
