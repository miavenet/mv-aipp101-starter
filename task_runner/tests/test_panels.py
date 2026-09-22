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

    def review_job(self, run, rid):
        return next(j for j in run.state['tasks']['make']['panel']['jobs'] if j['task'] == rid)

    def quota_on(self, rid, calls):
        """The listed calls of reviewer `rid` report the provider's quota, which refunds their try."""
        from unittest import mock
        from taskrunner import agents
        original, seen = agents.CommandAgent.run, []
        def run(agent, prompt, **kwargs):
            answer = original(agent, prompt, **kwargs)
            if kwargs['env'].get('TASK_RUNNER_TASK') == rid:
                seen.append(rid)
                if len(seen) in calls:
                    answer.status, answer.error = agents.QUOTA, 'usage_limit_reached'
            return answer
        patcher = mock.patch.object(agents.CommandAgent, 'run', run)
        patcher.start(); self.addCleanup(patcher.stop)

    def upgrade(self):
        """Make the saved state look like one written before job['invocation'] existed."""
        run = self.the_run()
        for job in run.state['tasks']['make']['panel']['jobs']:
            job.pop('invocation', None)
        run.save()

    def test_answer_refused_at_final_application_is_still_a_rejected_answer(self):
        """fnd: an answer refused at final application is still a rejected answer (FND-28)"""
        from taskrunner import agents, record
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [{'answer': review([finding()])}]*3, b: [PASS]})
        diagnostic = ("resolutions must cover exactly this reviewer's open blocking findings, each "
                      "once: required none, so resolutions must be []; supplied 'make/SC-1'")
        class Killed(Exception): pass
        def crash(point):
            if point == 'panel:batch-recorded': raise Killed()
        self.cli.CRASH = crash
        before = None
        for n in (1, 2, 3):
            with self.assertRaises(Killed):
                self.start() if n == 1 else self.resume()
            eng = self.coordinator()
            if before is None:
                before = record.dump_json(eng.ledger('make'))
            job = self.review_job(eng.run, a)
            # Collection accepted the answer; the coordinator's final application refuses it.
            self.assertEqual((job['result']['status'], job['tries']), ('ok', n))
            eng.reject_answer(job, 'make', status=agents.PROTOCOL_ERROR, error=diagnostic,
                              structured=job['result']['answer'])
        self.cli.CRASH = None
        self.assertEqual(self.resume(), 255, self.output)
        self.assertEqual((self.count(a), self.count(b), self.count('make')), (3, 1, 1))
        state = self.the_run().state['tasks']['make']
        self.assertEqual(state['status'], 'blocked')
        self.assertIn(diagnostic, state['reason'])
        self.assertNotIn('interrupted calls exhausted protocol retries', state['reason'])
        entries = state['rejected_reviews']
        self.assertEqual([e['try'] for e in entries], [1, 2, 3])
        for n, entry in enumerate(entries, 1):
            inv = self.task_file(a, 'round-1', f'invocation-{n}')
            self.assertEqual(entry['invocation'], os.path.relpath(inv, self.the_run().path))
            self.assertEqual(entry['verdict'], 'block')
            self.assertEqual([f['title'] for f in entry['findings']], ['Fix this'])
            outcome = self.read_json(a, 'round-1', f'invocation-{n}', 'outcome.json')
            self.assertEqual((outcome['status'], outcome['error']), ('protocol-error', diagnostic))
        with open(self.task_file(a, 'round-1', 'invocation-2', 'prompt.md')) as fh:
            self.assertIn(diagnostic, fh.read())
        self.assertEqual(record.dump_json(state['ledger']), before)
        self.check_invariants()

    def test_panel_checkpointed_before_this_change_is_resumed_with_its_answers(self):
        """run: a panel checkpointed before this change is resumed with its answers (RUN-26)"""
        a, b = self.setup_panel()
        malformed = {'answer': {'verdict': 'block', 'summary': 's', 'resolutions': None,
                                'findings': [finding()]}}
        # Call 1 hits the quota (try refunded), call 2 is malformed, call 3 is the next try.
        self.script({'make': [GOOD], a: [PASS, malformed, PASS], b: [PASS]})
        self.quota_on(a, {1, 3})
        self.assertEqual(self.start(), 2, self.output)
        run = self.the_run(); run.state.pop('provider_quota', None); run.save()
        class Killed(Exception): pass
        def crash(point):
            if point == 'panel:outcomes-recorded': raise Killed()
        self.cli.CRASH = crash
        with self.assertRaises(Killed): self.resume()
        self.cli.CRASH = None
        run = self.the_run()
        job = self.review_job(run, a)
        self.assertEqual(job['tries'], 1)
        self.assertIn('raw_outcome', job)
        self.upgrade()
        first = self.task_file(a, 'round-1', 'invocation-1', 'outcome.json')
        with open(first, 'rb') as fh: quota_bytes = fh.read()
        ledger = self.read_json('make', 'findings.json') if os.path.exists(
            self.task_file('make', 'findings.json')) else None
        self.assertEqual(self.resume(), 2, self.output)  # the next try hits the quota again
        run = self.the_run(); state = run.state['tasks']['make']
        second = os.path.relpath(self.task_file(a, 'round-1', 'invocation-2'), run.path)
        entries = state['rejected_reviews']
        self.assertEqual([(e['invocation'], e['try']) for e in entries], [(second, 1)])
        self.assertEqual([f['title'] for f in entries[0]['findings']], ['Fix this'])
        self.assertEqual(self.read_json(a, 'round-1', 'invocation-2', 'outcome.json')['status'],
                         'protocol-error')
        with open(first, 'rb') as fh: self.assertEqual(fh.read(), quota_bytes)
        self.assertNotIn('invocation-1', json.dumps(state['rejected_reviews']))
        job = self.review_job(run, a)
        self.assertEqual(job['tries'], 1)
        self.assertEqual(job['invocation'],
                         os.path.relpath(self.task_file(a, 'round-1', 'invocation-3'), run.path))
        self.assertEqual(self.count(a), 3)
        self.assertEqual(state.get('ledger', {}).get('findings', []), [])
        if ledger is not None:
            self.assertEqual(self.read_json('make', 'findings.json'), ledger)
        self.check_invariants()

    def test_recovered_invocation_survives_a_crash_before_the_rejection_is_saved(self):
        """run: a panel checkpointed before this change is resumed with its answers (RUN-26, adopted then killed)"""
        from unittest import mock
        from taskrunner import panels
        a, b = self.setup_panel()
        # Adapter-valid, so the ledger check refuses it and its outcome.json is rewritten from ok.
        self.script({'make': [GOOD], a: [{'answer': review([finding()], verdict='pass')}, PASS],
                     b: [PASS]})
        self.quota_on(a, {2})
        class Killed(Exception): pass
        def crash(point):
            if point == 'panel:outcomes-recorded': raise Killed()
        self.cli.CRASH = crash
        with self.assertRaises(Killed): self.start()
        self.cli.CRASH = None
        self.upgrade()
        original, calls = panels.Panels.reject_answer, []
        def killed_before_save(eng, job, producer_id, **kwargs):
            calls.append(dict(job))
            if len(calls) == 1:
                with mock.patch.object(eng, 'save', side_effect=Killed):
                    return original(eng, job, producer_id, **kwargs)
            return original(eng, job, producer_id, **kwargs)
        with mock.patch.object(panels.Panels, 'reject_answer', killed_before_save):
            with self.assertRaises(Killed): self.resume()
            self.assertEqual(self.resume(), 2, self.output)  # the next try hits the quota
        run = self.the_run()
        first = os.path.relpath(self.task_file(a, 'round-1', 'invocation-1'), run.path)
        self.assertEqual([c['invocation'] for c in calls], [first, first])
        entries = run.state['tasks']['make']['rejected_reviews']
        self.assertEqual([(e['invocation'], e['try']) for e in entries], [(first, 1)])
        outcome = self.read_json(a, 'round-1', 'invocation-1', 'outcome.json')
        self.assertEqual(outcome['status'], 'protocol-error')
        self.assertIn('verdict disagrees with ledger', outcome['error'])

    def refused_recovery(self, variant):
        """RUN-27's sequence for one kind of refusal: the highest-numbered invocation's
        outcome.json is `absent`, or present and `mismatched` with the persisted raw_outcome."""
        from unittest import mock
        from taskrunner import panels
        malformed = {'answer': {'verdict': 'block', 'summary': 's', 'resolutions': None,
                                'findings': [finding()]}}
        a, b = self.setup_panel()
        self.quota_on(a, {2})
        self.script({'make': [GOOD], a: [malformed, PASS], b: [PASS]})
        class Killed(Exception): pass
        def crash(point):
            if point == 'panel:outcomes-recorded': raise Killed()
        self.cli.CRASH = crash
        with self.assertRaises(Killed): self.start()
        self.cli.CRASH = None
        self.upgrade()
        outcome = self.task_file(a, 'round-1', 'invocation-1', 'outcome.json')
        if variant == 'absent':
            os.unlink(outcome)
        else:
            written = self.read_json(a, 'round-1', 'invocation-1', 'outcome.json')
            with open(outcome, 'wb') as fh:
                fh.write(json.dumps(dict(written, seconds=written['seconds'] + 1)).encode())
            with open(outcome, 'rb') as fh: kept = fh.read()
        # Killed once after the summary was appended and before it was saved: replay.
        original, calls = panels.Panels.reject_answer, []
        def killed_before_save(eng, job, producer_id, **kwargs):
            calls.append(dict(job))
            if len(calls) == 1:
                with mock.patch.object(eng, 'save', side_effect=Killed):
                    return original(eng, job, producer_id, **kwargs)
            return original(eng, job, producer_id, **kwargs)
        with mock.patch.object(panels.Panels, 'reject_answer', killed_before_save):
            with self.assertRaises(Killed): self.resume()
            self.assertEqual(self.resume(), 2, self.output)  # the next try hits the quota
        self.assertEqual(len(calls), 2)
        self.assertEqual([c['invocation'] for c in calls], [None, None])
        self.assertTrue(all('raw_outcome' not in c for c in calls))
        run = self.the_run(); state = run.state['tasks']['make']
        entries = state['rejected_reviews']
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]['invocation'])
        self.assertEqual(entries[0]['verdict'], 'block')
        self.assertEqual([f['title'] for f in entries[0]['findings']], ['Fix this'])
        self.assertIn('resolutions', entries[0]['error'])
        if variant == 'absent':
            self.assertFalse(os.path.exists(outcome))
        else:
            with open(outcome, 'rb') as fh: self.assertEqual(fh.read(), kept)
        job = self.review_job(run, a)
        self.assertEqual(job['invocation'],
            os.path.relpath(self.task_file(a, 'round-1', 'invocation-2'), run.path))
        self.assertEqual(self.read_json(a, 'round-1', 'invocation-2', 'outcome.json')['status'],
                         'quota')

    def test_refused_recovery_stays_refused_through_the_rejection(self):
        """run: a refused recovery stays refused through the rejection (RUN-27)"""
        self.refused_recovery('mismatched')

    def test_refused_recovery_stays_refused_through_the_rejection_when_outcome_is_absent(self):
        """run: a refused recovery stays refused through the rejection (RUN-27, outcome absent)"""
        self.refused_recovery('absent')

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
