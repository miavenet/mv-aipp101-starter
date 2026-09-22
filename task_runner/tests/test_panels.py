"""Stage 5 panels through the CLI with real subprocesses in scratch repositories."""
import json
import os
from helpers import EngineCase, done
from test_findings import finding, review, resolution
from taskrunner import engine, gitops

ONE='''
[[task]]
id="make"
type="implement"
prompt="Make the work"
outputs=["src/a"]
gate=["test -f src/a"]
reviewers=["principal-engineer", "spec-compliance"]
'''
GOOD={'write':{'src/a':'good\n'},'answer':done()}
PASS={'answer':review()}


class Panels(EngineCase):
    HEADER = EngineCase.HEADER + 'read_only_args = ["--read-only"]\n'
    def setup_panel(self, text=ONE, defaults=''):
        self.workflow(text, defaults=defaults)
        from taskrunner import workflow
        wf=workflow.load(self.wf_path)
        self.assertEqual(wf.errors,[])
        self.reviewers=[t['id'] for t in wf.tasks if t['kind']=='review']
        return self.reviewers

    def ledger(self):
        return self.read_json('make','findings.json')

    def count(self, tid):
        try:
            with open(self.script_path+'.'+tid+'.counter') as fh:
                return int(fh.read())
        except FileNotFoundError:
            return 0

    def review_prompt(self,rid,round_no=1):
        with open(self.task_file(rid,f'round-{round_no}','prompt.md')) as fh:
            return fh.read()

    def test_parallel_panel_passes_and_commits_candidate(self):
        a,b=self.setup_panel()
        self.script({'make':[GOOD], a:[dict(PASS,sleep_s=.05)], b:[PASS]})
        self.assertEqual(self.start(),0,self.output)
        self.assertEqual([self.status(t) for t in ('make',a,b)],['accepted']*3)
        self.assertEqual(self.ledger()['reviewers'][a]['round'],1)
        self.assertIn('Full review',self.review_prompt(a))
        self.check_invariants()

    def test_consolidated_rework_and_ledger_verdict(self):
        a,b=self.setup_panel()
        responses=[dict(finding='make/'+code+'-1',action='fixed',note='Fixed') for code in ('PE','SC')]
        self.script({'make':[GOOD,{'write':{'src/a':'better\n'},'answer':done(responses=responses)}],
                     a:[{'answer':review([finding()])},{'answer':review(resolutions=[resolution()])}],
                     b:[{'answer':review([finding()])},{'answer':review(resolutions=[resolution('make/SC-1')])}]})
        self.assertEqual(self.start(),0,self.output)
        self.assertEqual(self.count('make'),2)
        self.assertEqual([f['status'] for f in self.ledger()['findings']],['resolved','resolved'])
        with open(self.task_file('make','attempt-2','feedback.md')) as fh:
            feedback=fh.read()
        self.assertIn('make/PE-1',feedback);self.assertIn('make/SC-1',feedback)
        self.assertIn('Judge only the fix',self.review_prompt(a,2))
        self.assertIn('Fixed',self.review_prompt(a,2))
        self.check_invariants()

    def test_protocol_retries_and_blocked_panel(self):
        a,b=self.setup_panel()
        self.script({'make':[GOOD],a:[{'raw_answer':'prose'}]*3,b:[PASS]})
        self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.count(a),3)
        self.assertEqual(self.count('make'),1)
        self.assertEqual(self.ledger()['findings'],[])
        self.assertEqual(self.status(a),'objected');self.assertEqual(self.status(b),'accepted')
        for n in (1,2,3):
            self.assertTrue(os.path.isdir(self.task_file(a,'round-1',f'invocation-{n}')))
        self.check_invariants()

    def test_protocol_retry_receives_diagnostic_and_keeps_real_blocker(self):
        a, b = self.setup_panel()
        invalid = review([finding()], verdict='pass')
        self.script({'make': [GOOD, {'answer': done(responses=[dict(
            finding='make/PE-1', action='fixed', note='Fixed')])}],
            a: [{'answer': invalid},
                {'answer': review([finding()]), 'match': 'verdict disagrees with ledger: expected block'},
                {'answer': review(resolutions=[resolution()])}], b: [PASS, PASS]})
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(self.count(a), 3)
        self.assertEqual(self.count('make'), 2)
        with open(self.task_file(a, 'round-1', 'invocation-2', 'prompt.md')) as fh:
            self.assertIn('verdict disagrees with ledger: expected block', fh.read())
        self.assertEqual(self.ledger()['findings'][0]['status'], 'resolved')
        self.check_invariants()

    def test_escalation_holds_tree_and_advisory_resolution_does_not_rerun(self):
        a,b=self.setup_panel()
        disputed=dict(finding='make/PE-1',action='disputed',note='This is intentional')
        self.script({'make':[GOOD,{'answer':done(responses=[disputed])}],
                     a:[{'answer':review([finding()])},{'answer':review(resolutions=[resolution(status='unresolved')])}],
                     b:[PASS,PASS]})
        self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.status('make'),'waiting_human');self.check_invariants()
        self.assertEqual(self.runner('resolve','latest','make/PE-1','--as','advisory','-C',self.root),0,self.output)
        self.assertEqual(self.resume(),0,self.output)
        self.assertEqual(self.count('make'),2);self.assertEqual(self.count(a),2)
        self.assertEqual(self.ledger()['findings'][0]['status'],'noted');self.check_invariants()

    def test_reviewer_write_fails_and_restores(self):
        a,b=self.setup_panel()
        self.script({'make':[GOOD],a:[dict(PASS,write={'src/a':'tampered\n'})],b:[PASS]})
        self.assertEqual(self.start(),2,self.output)
        self.assertIn('reviewer changed',self.the_run().state['tasks']['make']['reason'])
        self.check_invariants()

    def test_first_review_after_failed_gate_is_full(self):
        a,b=self.setup_panel()
        self.script({'make':[{'answer':done()},GOOD],a:[PASS],b:[PASS]})
        self.assertEqual(self.start(),0,self.output)
        self.assertEqual(self.ledger()['reviewers'][a]['round'],1)
        self.assertIn('Full review',self.review_prompt(a));self.check_invariants()

    def test_attempt_limit_lists_findings_and_retry_supersedes(self):
        a,b=self.setup_panel(ONE.replace('gate=', 'max_attempts=1\ngate='))
        self.script({'make':[GOOD,GOOD],a:[{'answer':review([finding()])},PASS],b:[PASS,PASS]})
        self.assertEqual(self.start(),255,self.output)
        with open(os.path.join(self.the_run().path,'STATUS.md')) as fh:
            self.assertIn('make/PE-1',fh.read())
        self.assertEqual(self.runner('retry','latest','make','-C',self.root),0,self.output)
        self.assertEqual(self.resume(),0,self.output)
        self.assertEqual(self.ledger()['findings'][0]['status'],'superseded')
        self.assertIn('Full review',self.review_prompt(a,2));self.check_invariants()

    def test_read_only_check_that_writes_is_demoted_without_new_attempt(self):
        a,b=self.setup_panel(ONE+'''
[[task]]
id="check"
type="check"
verifies="make"
read_only=true
restores=false
run=["echo litter > src/litter"]
''')
        self.script({'make':[GOOD],a:[PASS,PASS],b:[PASS,PASS]})
        # The demoted writer still litters, so verification sends work back and eventually fails.
        self.assertEqual(self.start(),2,self.output)
        self.assertTrue(self.the_run().state['tasks']['check']['demoted'])
        self.assertTrue(self.read_json(a,'round-1','verdict.json')['void'])
        self.check_invariants()

    def test_upheld_dispute_requires_rework_and_cannot_be_disputed_again(self):
        a,b=self.setup_panel()
        dispute=dict(finding='make/PE-1',action='disputed',note='intentional')
        fixed=dict(finding='make/PE-1',action='fixed',note='changed as directed')
        self.script({'make':[GOOD,{'answer':done(responses=[dispute])},
                             {'answer':done(responses=[dispute])},
                             {'write':{'src/a':'fixed\n'},'answer':done(responses=[fixed])}],
                     a:[{'answer':review([finding()])},
                        {'answer':review(resolutions=[resolution(status='unresolved')])},
                        {'answer':review(resolutions=[resolution()])}], b:[PASS,PASS,PASS]})
        self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.runner('resolve','latest','make/PE-1','--as','upheld','-C',self.root),0,self.output)
        self.assertEqual(self.resume(),0,self.output)
        self.assertEqual(self.count('make'),4)  # the rejected dispute was only a protocol retry
        self.assertEqual(self.the_run().state['tasks']['make']['attempts_used'],3)
        self.assertEqual(self.ledger()['findings'][0]['status'],'resolved');self.check_invariants()

    def test_diff_spans_intervening_gate_failure_and_answer_is_not_required_twice(self):
        a,b=self.setup_panel(ONE.replace('gate=["test -f src/a"]',
                                        'max_attempts=4\ngate=["grep -q good src/a"]'))
        fixed=dict(finding='make/PE-1',action='fixed',note='fixed before gate failed')
        self.script({'make':[GOOD,{'write':{'src/a':'bad\n'},'answer':done(responses=[fixed])},
                             {'write':{'src/a':'good changed\n'},'answer':done()}],
                     a:[{'answer':review([finding()])},{'answer':review(resolutions=[resolution()])}],
                     b:[PASS,PASS]})
        self.assertEqual(self.start(),0,self.output)
        first=self.read_json(a,'round-1','verdict.json')['candidate']
        second=self.read_json(a,'round-2','verdict.json')
        self.assertEqual(second['base'],first)
        self.assertIn('fixed before gate failed',self.review_prompt(a,2))
        self.assertEqual(self.count(a),2);self.check_invariants()

    def test_passed_reviewer_never_mode_skips_later_rounds(self):
        text=ONE.replace('"spec-compliance"]','{ perspective="spec-compliance", recheck_passed="never" }]')
        a,b=self.setup_panel(text)
        fixed=dict(finding='make/PE-1',action='fixed',note='fixed')
        self.script({'make':[GOOD,{'answer':done(responses=[fixed])}],
                     a:[{'answer':review([finding()])},{'answer':review(resolutions=[resolution()])}],b:[PASS]})
        self.assertEqual(self.start(),0,self.output)
        self.assertEqual(self.count(b),1);self.assertEqual(self.count(a),2);self.check_invariants()

    def test_crash_after_panel_application_resumes_without_duplicate_findings_or_calls(self):
        a,b=self.setup_panel()
        self.script({'make':[GOOD],a:[PASS],b:[PASS]})
        class Killed(Exception):pass
        def crash(point):
            if point=='panel:applied':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.start()
        self.cli.CRASH=None
        before=self.ledger()
        self.assertEqual(self.resume(),0,self.output)
        self.assertEqual(self.ledger(),before)
        self.assertEqual((self.count('make'),self.count(a),self.count(b)),(1,1,1));self.check_invariants()

    def test_panel_findings_cap_blocks_without_truncation(self):
        a,b=self.setup_panel(defaults='findings_cap_bytes=30')
        self.script({'make':[GOOD],a:[{'answer':review([finding()])}],b:[PASS]})
        self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.count('make'),1)
        self.assertIn('None is dropped',self.the_run().state['tasks']['make']['reason'])
        self.check_invariants()

    def test_parallel_limit_and_completion_order_do_not_change_ledger_or_feedback(self):
        import threading
        import time
        from taskrunner import agents, validate
        text=ONE.replace('"spec-compliance"]','"spec-compliance", "devops"]')
        ids=self.setup_panel(text,defaults='max_parallel=2')
        lock=threading.Lock(); active=0; peak=0; finished=[]; reverse=False
        class Observed(agents.CommandAgent):
            def run(agent,prompt,**kwargs):
                nonlocal active,peak
                is_review=kwargs['schema']==validate.REVIEW
                rid=kwargs['env'].get('TASK_RUNNER_TASK')
                if is_review:
                    with lock:active+=1;peak=max(peak,active)
                    position=ids.index(rid)
                    time.sleep(.15 if (position==0) != reverse else .01)
                try:return super().run(prompt,**kwargs)
                finally:
                    if is_review:
                        with lock:active-=1;finished.append(rid)
        self.addCleanup(agents.REGISTRY.__setitem__,'command',agents.CommandAgent)
        agents.REGISTRY['command']=Observed
        outputs=[]
        for run_no in range(2):
            reverse=bool(run_no)
            if run_no:self.git_out('checkout','main')
            steps={'make':[GOOD,{'answer':done(responses=[
                dict(finding='make/'+code+'-1',action='fixed',note='fixed') for code in ('PE','SC','DO')])}]}
            for rid,code in zip(ids,('PE','SC','DO')):
                steps[rid]=[{'answer':review([finding()])},
                            {'answer':review(resolutions=[resolution('make/'+code+'-1')])}]
                counter=self.script_path+'.'+rid+'.counter'
                if os.path.exists(counter):os.unlink(counter)
            counter=self.script_path+'.make.counter'
            if os.path.exists(counter):os.unlink(counter)
            self.script(steps)
            self.assertEqual(self.start(),0,self.output)
            with open(self.task_file('make','attempt-2','feedback.md')) as fh:feedback=fh.read()
            outputs.append((self.ledger(),feedback))
            self.check_invariants()
        self.assertEqual(peak,2)
        self.assertNotEqual(finished[0],finished[6])
        self.assertEqual(outputs[0],outputs[1])

    def test_unrelated_producer_cannot_observe_rejected_helper(self):
        text=ONE.replace('gate=', 'max_attempts=1\ngate=')+'''
[[task]]
id="other"
type="produce"
prompt="Independent work"
outputs=["other"]
gate=["test ! -f src/a"]
'''
        a,b=self.setup_panel(text)
        self.script({'make':[GOOD],a:[{'answer':review([finding()])}],b:[PASS],
                     'other':[{'write':{'other':'independent\n'},'answer':done()}]})
        self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.status('other'),'accepted')
        self.assertNotIn('src/a',self.git_out('ls-tree','-r','--name-only','HEAD'))
        self.check_invariants()

    def test_crash_after_outcome_accounting_does_not_repeat_review(self):
        a,b=self.setup_panel()
        self.script({'make':[GOOD],a:[PASS],b:[PASS]})
        class Killed(Exception):pass
        def crash(point):
            if point=='panel:outcomes-recorded':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.start()
        self.cli.CRASH=None
        spend=self.the_run().state['spend']
        self.assertEqual(self.resume(),0,self.output)
        self.assertEqual((self.count(a),self.count(b)),(1,1))
        self.assertEqual(self.the_run().state['spend'],spend);self.check_invariants()

    def coordinator(self):
        return engine.Engine(self.the_run(), gitops.Git(self.root))

    def test_invocation_records_the_outcome_that_was_used(self):
        """run: the invocation records the outcome that was used (RUN-21)"""
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [PASS], b: [PASS]})
        self.assertEqual(self.start(), 0, self.output)
        before = self.read_json(a, 'round-1', 'invocation-1', 'outcome.json')
        self.assertEqual(before['status'], 'ok')
        eng = self.coordinator()
        inv = os.path.relpath(self.task_file(a, 'round-1', 'invocation-1'), eng.run.path)
        diagnostic = ("resolutions must cover exactly this reviewer's open blocking findings, "
                     "each once: required none, so resolutions must be []; supplied 'x'")
        job = {'task': a, 'round': 1, 'tries': 1, 'invocation': inv}
        eng.note_rejected_answer(job, 'make', status='protocol-error', error=diagnostic,
                                 structured=review(resolutions=[resolution('x')]))
        after = self.read_json(a, 'round-1', 'invocation-1', 'outcome.json')
        self.assertEqual(after['status'], 'protocol-error')
        self.assertEqual(after['error'], diagnostic)
        self.assertEqual(after['seconds'], before['seconds'])
        self.check_invariants()

    def test_malformed_sibling_field_does_not_hide_a_readable_finding(self):
        """run: a malformed sibling field does not hide a readable finding (RUN-22)"""
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [PASS], b: [PASS]})
        self.assertEqual(self.start(), 0, self.output)
        eng = self.coordinator()
        structured = {'verdict': 'block', 'summary': 'ok', 'resolutions': None,
                     'findings': [finding(), dict(finding(), title='second issue', severity='advisory')]}
        job = {'task': a, 'round': 1, 'tries': 1, 'invocation': None}
        eng.note_rejected_answer(job, 'make', status='protocol-error',
                                 error="answer.resolutions must be a JSON array, not null",
                                 structured=structured)
        entry = eng.st('make')['rejected_reviews'][0]
        self.assertEqual(entry['verdict'], 'block')
        self.assertEqual([f['title'] for f in entry['findings']], ['Fix this', 'second issue'])
        self.assertEqual(entry['unreadable_findings'], 0)
        self.check_invariants()

    def test_no_rejected_answer_or_title_is_omitted(self):
        """run: no rejected answer or title is omitted (RUN-23)"""
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [PASS], b: [PASS]})
        self.assertEqual(self.start(), 0, self.output)
        eng = self.coordinator()
        many_findings = [dict(finding(), title=f'issue {n}') for n in range(11)]
        job = {'task': a, 'round': 1, 'tries': 1, 'invocation': None}
        eng.note_rejected_answer(job, 'make', status='protocol-error', error='e',
                                 structured={'verdict': 'block', 'summary': 's', 'resolutions': [],
                                             'findings': many_findings})
        entry = eng.st('make')['rejected_reviews'][0]
        self.assertEqual(len(entry['findings']), 11)
        self.assertEqual([f['title'] for f in entry['findings']], [f'issue {n}' for n in range(11)])
        for n in range(1, 21):
            job = {'task': f'reviewer-{n % 7}', 'round': n, 'tries': 1, 'invocation': None}
            eng.note_rejected_answer(job, 'make', status='protocol-error', error=f'e{n}',
                                     structured={'verdict': 'pass', 'summary': 's',
                                                 'resolutions': [], 'findings': []})
        self.assertEqual(len(eng.st('make')['rejected_reviews']), 21)
        self.check_invariants()

    def test_unreadable_finding_entries_are_counted_not_guessed(self):
        """run: unreadable finding entries are counted, not guessed (RUN-25)"""
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [PASS], b: [PASS]})
        self.assertEqual(self.start(), 0, self.output)
        eng = self.coordinator()
        mixed = [finding(), 'a bare string', {'detail': 'no title here'},
                dict(finding(), title='severity is unreadable', severity=7)]
        job = {'task': a, 'round': 1, 'tries': 1, 'invocation': None}
        eng.note_rejected_answer(job, 'make', status='protocol-error', error='e',
                                 structured={'verdict': 'block', 'summary': 's', 'resolutions': [],
                                             'findings': mixed})
        entry = eng.st('make')['rejected_reviews'][0]
        self.assertEqual([f['title'] for f in entry['findings']],
                         ['Fix this', 'severity is unreadable'])
        self.assertEqual([f['severity'] for f in entry['findings']], ['blocking', 'unknown'])
        self.assertEqual(entry['unreadable_findings'], 2)
        self.check_invariants()

    def test_reader_detects_ledger_tampering(self):
        from taskrunner import agents,validate
        a,b=self.setup_panel()
        self.script({'make':[GOOD],a:[PASS],b:[PASS]})
        outer=self
        class Tamper(agents.CommandAgent):
            def run(agent,prompt,**kwargs):
                if kwargs['schema']==validate.REVIEW:
                    with open(outer.task_file('make','findings.json'),'w') as fh:fh.write('{}')
                return super().run(prompt,**kwargs)
        self.addCleanup(agents.REGISTRY.__setitem__,'command',agents.CommandAgent)
        agents.REGISTRY['command']=Tamper
        self.assertEqual(self.start(),2,self.output)
        self.assertIn('record was changed',self.the_run().state['tasks']['make']['reason'])
        self.check_invariants()
