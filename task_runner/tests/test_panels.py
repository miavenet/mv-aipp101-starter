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

    def test_rejected_review_answers_are_summarised_for_the_owner(self):
        """run: rejected review answers are summarised for the owner (RUN-18)"""
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [{'answer': review([finding()])}],
                     b: [{'answer': self.COLLIDING}] * 3})
        self.assertEqual(self.start(), 255, self.output)
        self.assertEqual((self.count(a), self.count(b)), (1, 3))
        run = self.the_run()
        self.assertEqual(run.state['tasks']['make']['status'], 'blocked')
        self.assertEqual(self.ledger()['findings'], [])      # nothing below reached the ledger
        with open(self.task_file('make', 'STATUS.md')) as fh:
            status = fh.read()
        self.assertIn('## Rejected review answers', status)
        self.assertIn('Not applied. Nothing below is in the ledger and none of it changed '
                      'acceptance. Read it before you retry: the concerns in it may be real.',
                      status)
        self.assertEqual(status.count('  - blocking: Fix this'), 3)
        self.assertEqual(status.count("  Rejected because: resolutions must cover exactly this "
                                      "reviewer's open blocking findings, each once: required none,"
                                      " so resolutions must be []; supplied 'make/PE-1'. A new "
                                      "finding belongs in findings only, never in resolutions"), 3)
        for n in (1, 2, 3):
            self.assertIn(f'- **{b}**, round 1, try {n} — claimed verdict `block`, 1 finding:',
                          status)
            inv = os.path.relpath(self.task_file(b, 'round-1', f'invocation-{n}'), run.path)
            self.assertIn(f'  Answer: `{inv}/last-message.txt`', status)
            with open(os.path.join(run.path, inv, 'last-message.txt')) as fh:
                self.assertTrue(fh.read())
        self.check_invariants()

    def test_rejected_answers_are_redacted_and_bounded(self):
        """run: rejected answers are redacted and bounded (RUN-20)"""
        from taskrunner import proc
        a, b = self.setup_panel()
        self.script({'make': [GOOD], a: [PASS], b: [PASS]})
        self.assertEqual(self.start(), 0, self.output)
        eng = self.coordinator()
        token = 'sk-ant-' + 'a' * 40
        structured = {'verdict': 'block', 'summary': 's', 'resolutions': None,
                      'findings': [dict(finding(), title=token + '\n\t' + 'x' * 500)]}
        job = {'task': a, 'round': 1, 'tries': 2, 'invocation': None}
        eng.note_rejected_answer(job, 'make', status='protocol-error',
                                 error='answer.resolutions must be a JSON array, not null',
                                 structured=structured)
        eng.save()
        title = eng.st('make')['rejected_reviews'][0]['findings'][0]['title']
        self.assertIn(proc.REDACTED.decode(), title)
        self.assertNotIn(token, title)
        self.assertEqual(len(title), 121)
        self.assertTrue(title.endswith('…'))
        for control in ('\n', '\t'):
            self.assertNotIn(control, title)
        with open(self.task_file('make', 'STATUS.md')) as fh:
            before = fh.read()
        self.assertIn(f'  - blocking: {title}', before)
        self.assertNotIn(token, before)
        self.assertEqual(self.runner('status', 'latest', '--rebuild', '-C', self.root), 0,
                         self.output)
        with open(self.task_file('make', 'STATUS.md')) as fh:
            self.assertEqual(fh.read(), before)
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

    def events(self):
        with open(os.path.join(self.the_run().path, 'events.jsonl'), encoding='utf-8') as fh:
            return [json.loads(line) for line in fh]

    def test_meaningless_resolution_is_dropped_and_the_finding_is_kept(self):
        """fnd: a meaningless resolution is dropped, the finding is kept (FND-21)"""
        a, b = self.setup_panel()
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        fixed = dict(finding='make/PE-1', action='fixed', note='Fixed')
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=[fixed])}],
                     a: [{'answer': by_title}, {'answer': review(resolutions=[resolution()])}],
                     b: [PASS, PASS]})
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(self.count(a), 2)
        self.assertFalse(os.path.exists(self.task_file(a, 'round-1', 'invocation-2')))
        with open(self.task_file('make', 'attempt-2', 'feedback.md')) as fh:
            self.assertIn('make/PE-1', fh.read())
        ledger = self.ledger()
        self.assertEqual([(f['id'], f['status']) for f in ledger['findings']], [('make/PE-1', 'resolved')])
        self.assertEqual(self.read_json(a, 'round-1', 'verdict.json')['result']['verdict'], 'block')
        self.assertNotIn('rejected_reviews', self.the_run().state['tasks']['make'])
        self.check_invariants()

    def test_a_repair_is_recorded_where_it_can_be_audited(self):
        """fnd: a repair is recorded where it can be audited (FND-25, event and verdict.json)"""
        a, b = self.setup_panel()
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        fixed = dict(finding='make/PE-1', action='fixed', note='Fixed')
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=[fixed])}],
                     a: [{'answer': by_title}, {'answer': review(resolutions=[resolution()])}],
                     b: [PASS, PASS]})
        self.assertEqual(self.start(), 0, self.output)
        ledger = self.ledger()
        self.assertEqual([h['event'] for h in ledger['findings'][0]['history']],
                         ['raised', 'repair', 'response', 'resolution'])
        self.assertEqual(ledger['findings'][0]['history'][1],
                         {'event': 'repair', 'round': 1, 'answer': 1,
                          'kind': 'dropped_resolutions', 'dropped': ['Fix this']})
        repairs = [e for e in self.events() if e['event'] == 'review-repair']
        self.assertEqual(len(repairs), 1)
        self.assertEqual({k: repairs[0][k] for k in ('task', 'producer', 'round', 'kind', 'dropped')},
                         {'task': a, 'producer': 'make', 'round': 1, 'kind': 'dropped_resolutions', 'dropped': 1})
        result = self.read_json(a, 'round-1', 'verdict.json')['result']
        self.assertEqual(result['repair'], {'kind': 'dropped_resolutions',
                                            'dropped': [{'finding': 'Fix this', 'status': 'unresolved'}],
                                            'why': 'the round required no resolutions and no entry named '
                                                   'a finding in the ledger'})
        self.assertEqual(result['answer']['resolutions'], by_title['resolutions'])
        self.check_invariants()

    REPAIRED = ('1 meaningless `resolutions` entry was dropped and the answer was applied. The '
                'entries named no finding in the ledger, and the round required none. '
                'See findings.json.')

    def test_a_repair_is_recorded_in_the_producers_status(self):
        """fnd: a repair is recorded where it can be audited (FND-25, the STATUS line)"""
        a, b = self.setup_panel()
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        fixed = dict(finding='make/PE-1', action='fixed', note='Fixed')
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=[fixed])}],
                     a: [{'answer': by_title}, {'answer': review(resolutions=[resolution()])}],
                     b: [PASS, PASS]})
        self.assertEqual(self.start(), 0, self.output)
        with open(self.task_file('make', 'STATUS.md')) as fh:
            status = fh.read()
        self.assertIn('## Repaired review answers', status)
        self.assertEqual(status.count(f'- **{a}**, round 1: {self.REPAIRED}'), 1)
        self.assertNotIn('## Rejected review answers', status)
        self.check_invariants()

    def test_a_second_repair_after_a_retry_keeps_its_own_line(self):
        """fnd: a repair is recorded where it can be audited (FND-25, a repeated repair)

        `retry` supersedes the open findings and clears the reviewers' rounds, so an identical
        answer repaired again on an identical candidate is round 1 for the second time. The two
        answers stay two lines because the `repair` event carries its own discriminator."""
        a, b = self.setup_panel(ONE.replace('gate=', 'max_attempts=1\ngate='))
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        self.script({'make': [GOOD, GOOD], a: [{'answer': by_title}, {'answer': by_title}],
                     b: [PASS, PASS]})
        self.assertEqual(self.start(), 255, self.output)
        self.assertEqual(self.runner('retry', 'latest', 'make', '-C', self.root), 0, self.output)
        self.assertEqual(self.resume(), 255, self.output)
        ledger = self.ledger()
        self.assertEqual([(f['id'], f['status']) for f in ledger['findings']],
                         [('make/PE-1', 'superseded'), ('make/PE-2', 'open')])
        repairs = [h for f in ledger['findings'] for h in f['history'] if h['event'] == 'repair']
        self.assertEqual([(h['round'], h['answer'], h['dropped']) for h in repairs],
                         [(1, 1, ['Fix this']), (1, 2, ['Fix this'])])
        self.assertEqual(len([e for e in self.events() if e['event'] == 'review-repair']), 2)
        with open(self.task_file('make', 'STATUS.md')) as fh:
            status = fh.read()
        self.assertEqual(status.count(f'- **{a}**, round 1: {self.REPAIRED}'), 2)
        self.check_invariants()

    def repair_lines(self, ledger):
        """The rendered "Repaired review answers" entries of a producer holding this ledger."""
        from taskrunner import record
        t = {'status': 'blocked', 'kind': 'produce', 'type': 'implement', 'reason': '',
             'commit': '', 'ledger': ledger}
        status = record.render_task_status('make', t, self.side, 'run')
        return [line for line in status.splitlines() if line.startswith('- **')]

    def test_the_findings_of_one_repaired_answer_are_one_line(self):
        """fnd: a repair is recorded where it can be audited (FND-25, one answer, one line)"""
        from taskrunner import findings as ledgers
        from test_findings import R
        junk = [dict(finding='Fix this', status='unresolved', note='n')]
        two = review([finding(), dict(finding(), title='Fix that')], resolutions=junk)
        ledger = ledgers.apply_review(ledgers.empty('make'), R, two, 'C1', {})[0]
        one_line = [f'- **{R["id"]}**, round 1: {self.REPAIRED}']
        self.assertEqual(self.repair_lines(ledger), one_line)
        # The line belongs to the answer, not to its findings: a response, a resolution and a
        # retry are all ordinary transitions of the findings and leave it exactly as it was.
        responses = [dict(finding=f'make/PE-{n}', action='fixed', note='Fixed') for n in (1, 2)]
        ledger = ledgers.respond(ledger, done(responses=responses), 2)
        ledger = ledgers.apply_review(ledger, R, review(resolutions=[resolution('make/PE-1'),
                                                                     resolution('make/PE-2')]), 'C2', {})[0]
        self.assertEqual([f['status'] for f in ledger['findings']], ['resolved', 'resolved'])
        self.assertEqual(self.repair_lines(ledger), one_line)
        self.assertEqual(self.repair_lines(ledgers.restart(ledger)), one_line)

    def test_a_repair_survives_a_colliding_sibling_that_retries_once(self):
        """fnd: a repair is recorded once, not once per pass (FND-25, retry-success)"""
        a, b = self.setup_panel()
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        responses = [dict(finding='make/'+code+'-1', action='fixed', note='Fixed') for code in ('PE', 'SC')]
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=responses)}],
                     a: [{'answer': by_title}, {'answer': review(resolutions=[resolution()])}],
                     b: [{'answer': self.COLLIDING},
                         {'answer': review([finding()]), 'match': self.COLLISION},
                         {'answer': review(resolutions=[resolution('make/SC-1')])}]})
        self.assertEqual(self.start(), 0, self.output)  # PE's repair restarts nothing; SC's own retry does
        self.assertEqual((self.count(a), self.count(b)), (2, 3))
        ledger = self.ledger()
        self.assertEqual([f['id'] for f in ledger['findings']], ['make/PE-1', 'make/SC-1'])
        self.assertEqual([h['event'] for h in ledger['findings'][0]['history']],
                         ['raised', 'repair', 'response', 'resolution'])
        repairs = [e for e in self.events() if e['event'] == 'review-repair']
        self.assertEqual(len(repairs), 1)
        self.assertEqual(self.read_json(a, 'round-1', 'verdict.json')['result']['repair']['kind'],
                         'dropped_resolutions')
        self.check_invariants()

    def test_a_repair_is_not_published_when_a_colliding_sibling_exhausts_its_tries(self):
        """fnd: a repair is not published when a colliding sibling exhausts its tries (FND-25, retry-exhaustion)"""
        a, b = self.setup_panel()
        by_title = review([finding()], resolutions=[dict(finding='Fix this', status='unresolved', note='n')])
        self.script({'make': [GOOD], a: [{'answer': by_title}], b: [{'answer': self.COLLIDING}] * 3})
        self.assertEqual(self.start(), 255, self.output)
        self.assertEqual((self.count(a), self.count(b)), (1, 3))
        state = self.the_run().state['tasks']['make']
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state.get('ledger', {}).get('findings', []), [])
        self.assertEqual(len(state['rejected_reviews']), 3)
        self.assertEqual([e for e in self.events() if e['event'] == 'review-repair'], [])
        self.check_invariants()

    def test_a_repair_never_produces_a_pass_and_the_rejections_are_summarised(self):
        """fnd: a repair never produces a pass (FND-24, the owner's summary)"""
        a, b = self.setup_panel()
        junk = review(resolutions=[dict(finding='looks fine to me', status='resolved', note='n')],
                      verdict='pass')
        self.script({'make': [GOOD], a: [{'answer': junk}]*3, b: [PASS]})
        self.assertEqual(self.start(), 255, self.output)
        self.assertEqual(self.count(a), 3)
        state = self.the_run().state['tasks']['make']
        self.assertEqual(state['status'], 'blocked')
        self.assertIn('required none, so resolutions must be []', state['reason'])
        entries = state['rejected_reviews']
        self.assertEqual([(e['try'], e['verdict'], e['findings']) for e in entries],
                         [(1, 'pass', []), (2, 'pass', []), (3, 'pass', [])])
        self.assertEqual(state.get('ledger', {}).get('findings', []), [])
        self.check_invariants()

    def test_valid_answers_are_untouched_by_the_repair(self):
        """fnd: valid answers are untouched (FND-26)"""
        a, b = self.setup_panel()
        responses = [dict(finding='make/'+code+'-1', action='fixed', note='Fixed') for code in ('PE', 'SC')]
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=responses)}],
                     a: [{'answer': review([finding()])}, {'answer': review(resolutions=[resolution()])}],
                     b: [{'answer': review([finding()])}, {'answer': review(resolutions=[resolution('make/SC-1')])}]})
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual((self.count('make'), self.count(a), self.count(b)), (2, 2, 2))
        state = self.the_run().state['tasks']['make']
        self.assertEqual(state['attempts_used'], 2)
        self.assertNotIn('rejected_reviews', state)
        for f in self.ledger()['findings']:
            self.assertEqual([h['event'] for h in f['history']], ['raised', 'response', 'resolution'])
        self.assertEqual([e for e in self.events() if e['event'] in ('review-repair', 'review-answer-rejected')], [])
        for rid in (a, b):
            for n in (1, 2):
                self.assertNotIn('repair', self.read_json(rid, f'round-{n}', 'verdict.json')['result'])
        self.check_invariants()

    COLLIDING = review([finding()], resolutions=[dict(finding='make/PE-1', status='unresolved', note='n')])
    COLLISION = "required none, so resolutions must be \\[\\]; supplied 'make/PE-1'"

    def collision(self, a, b, run_no=0):
        """PE raises make/PE-1; SC, beside it, blocks and names that id as a resolution. At collection
        the id does not exist yet, so SC is repaired; at final application it does, so SC is refused."""
        if run_no:
            self.git_out('checkout', 'main')
            for tid in ('make', a, b):
                counter = self.script_path+'.'+tid+'.counter'
                if os.path.exists(counter): os.unlink(counter)
        responses = [dict(finding='make/'+code+'-1', action='fixed', note='Fixed') for code in ('PE', 'SC')]
        self.script({'make': [GOOD, {'write': {'src/a': 'better\n'}, 'answer': done(responses=responses)}],
                     a: [{'answer': review([finding()])}, {'answer': review(resolutions=[resolution()])}],
                     b: [{'answer': self.COLLIDING},
                         {'answer': review([finding()]), 'match': self.COLLISION},
                         {'answer': review(resolutions=[resolution('make/SC-1')])}]})

    def collided(self, a, b):
        run = self.the_run(); state = run.state['tasks']['make']
        return self.ledger(), state['status'], state['rejected_reviews'], (
            self.count('make'), self.count(a), self.count(b))

    def test_repair_eligibility_is_decided_by_the_ledger_that_applies_it(self):
        """fnd: repair eligibility is decided by the ledger that applies it (FND-27)"""
        a, b = self.setup_panel()
        self.collision(a, b)
        self.assertEqual(self.start(), 0, self.output)  # no exception escapes the engine
        ledger, status, entries, counts = self.collided(a, b)
        self.assertEqual(status, 'accepted')
        self.assertEqual(counts, (2, 2, 3))  # SC re-called once, inside its existing tries
        self.assertEqual([f['id'] for f in ledger['findings']], ['make/PE-1', 'make/SC-1'])
        self.assertEqual(ledger['next_ids'], {'PE': 1, 'SC': 1})
        with open(self.task_file(b, 'round-1', 'invocation-2', 'prompt.md')) as fh:
            self.assertIn("supplied 'make/PE-1'", fh.read())
        first = os.path.relpath(self.task_file(b, 'round-1', 'invocation-1'), self.the_run().path)
        self.assertEqual([(e['reviewer'], e['try'], e['invocation']) for e in entries], [(b, 1, first)])
        self.assertIn("supplied 'make/PE-1'", entries[0]['error'])
        self.assertEqual(self.read_json(b, 'round-1', 'invocation-1', 'outcome.json')['status'],
                         'protocol-error')
        self.check_invariants()
        # The same run, killed at panel:applied and resumed, reaches the same ledger.
        class Killed(Exception): pass
        kills = []
        def crash(point):
            if point == 'panel:applied' and not kills:
                kills.append(point); raise Killed()
        self.collision(a, b, run_no=1)
        self.cli.CRASH = crash
        with self.assertRaises(Killed): self.start()
        self.cli.CRASH = None
        self.assertEqual([f['id'] for f in self.ledger()['findings']], ['make/PE-1', 'make/SC-1'])
        self.assertEqual(self.resume(), 0, self.output)
        again = self.collided(a, b)
        self.assertEqual(again[:2], (ledger, status))
        self.assertEqual([(e['reviewer'], e['try']) for e in again[2]], [(b, 1)])
        self.assertEqual(again[3], counts)
        self.check_invariants()

    def test_a_coordinator_rejection_survives_replay_exactly_once(self):
        """fnd: a coordinator rejection survives replay exactly once (FND-29)"""
        from unittest import mock
        from taskrunner import panels
        a, b = self.setup_panel()
        self.collision(a, b)
        self.assertEqual(self.start(), 0, self.output)
        uninterrupted = self.collided(a, b)
        self.collision(a, b, run_no=1)
        class Killed(Exception): pass
        original, calls = panels.Panels.reject_answer, []
        def killed_before_save(eng, job, producer_id, **kwargs):
            calls.append(dict(job))
            if len(calls) == 1:  # the coordinator's refusal: collection accepted SC's answer
                with mock.patch.object(eng, 'save', side_effect=Killed):
                    return original(eng, job, producer_id, **kwargs)
            return original(eng, job, producer_id, **kwargs)
        with mock.patch.object(panels.Panels, 'reject_answer', killed_before_save):
            with self.assertRaises(Killed): self.start()
            self.assertEqual(self.resume(), 0, self.output)
        self.assertEqual(len(calls), 2)
        self.assertEqual([(c['task'], c['tries'], c['result']['status']) for c in calls],
                         [(b, 1, 'ok'), (b, 1, 'ok')])
        ledger, status, entries, counts = self.collided(a, b)
        run = self.the_run()
        first = os.path.relpath(self.task_file(b, 'round-1', 'invocation-1'), run.path)
        self.assertEqual([(e['reviewer'], e['try'], e['invocation']) for e in entries], [(b, 1, first)])
        self.assertEqual([f['id'] for f in ledger['findings']], ['make/PE-1', 'make/SC-1'])
        self.assertEqual(ledger['next_ids'], {'PE': 1, 'SC': 1})
        self.assertEqual((ledger, status, counts), (uninterrupted[0], uninterrupted[1], uninterrupted[3]))
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
