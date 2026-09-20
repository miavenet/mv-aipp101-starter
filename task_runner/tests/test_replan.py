"""RUN-04..06/12..15 and REC-11: freeze definitions and reopen using resumable reverts."""
import json
import os
from pathlib import Path
from helpers import EngineCase, done
from taskrunner import record

A='''
[[task]]
id="a"
type="produce"
prompt="Write a"
outputs=["a.txt"]
gate=["test -s a.txt"]
'''
B='''
[[task]]
id="b"
type="produce"
prompt="Write b"
needs=["a"]
outputs=["b.txt"]
gate=["test -s b.txt"]
'''
H='''
[[task]]
id="human"
type="human"
'''


def writes(path,text='old\n'):
    return {'write':{path:text},'answer':done()}


class Replan(EngineCase):
    def revised(self, tasks):
        text=self.HEADER.format(defaults='',python=os.sys.executable,
                               agent=os.path.join(os.path.dirname(__file__),'fake_agent.py')).replace("'",'"')
        text=text.replace('name = "demo"','name = "demo"\nroot = '+json.dumps(self.root))
        path=Path(self.side,'revised.toml');path.write_text(text+tasks)
        return str(path)

    def replan(self,path,*extra):
        return self.runner('replan','latest','--workflow',path,'-C',self.root,*extra)

    def test_add_task_and_edit_pending_task_records_before_and_after(self):
        self.workflow(H+A.replace('id="a"','id="a"\nneeds=["human"]'))
        self.script([writes('a.txt'),writes('b.txt')])
        self.assertEqual(self.start(),255,self.output)
        path=self.revised(H+A.replace('id="a"','id="a"\nneeds=["human"]').replace('Write a','Revised brief')+B)
        self.assertEqual(self.replan(path),0,self.output)
        replans=Path(self.the_run().path,'replans','001')
        self.assertTrue((replans/'before'/'workflow.expanded.json').is_file())
        self.assertTrue((replans/'after'/'workflow.expanded.json').is_file())
        self.assertEqual(self.runner('approve','latest','human','-C',self.root),0,self.output)
        self.assertEqual(self.resume(),0,self.output)
        self.assertIn('Revised brief',self.prompt(1));self.check_invariants()

    def test_accepted_change_requires_reopen_and_reverts_downstream_artifacts(self):
        self.workflow(A+B);self.script([writes('a.txt'),writes('b.txt')])
        self.assertEqual(self.start(),0,self.output)
        oldhead=self.git_out('rev-parse','HEAD')
        path=self.revised(A.replace('a.txt','new-a.txt')+B)
        self.assertEqual(self.replan(path),2,self.output)
        self.assertIn('--reopen',self.output)
        self.assertEqual(self.git_out('rev-parse','HEAD'),oldhead)
        self.assertEqual(self.replan(path,'--reopen','a'),0,self.output)
        self.assertEqual((self.status('a'),self.status('b')),('pending','pending'))
        self.assertFalse(Path(self.root,'a.txt').exists());self.assertFalse(Path(self.root,'b.txt').exists())
        self.assertIn(oldhead,self.git_out('rev-list','HEAD'))
        self.script([writes('new-a.txt','new\n'),writes('b.txt','rebuilt\n')])
        self.assertEqual(self.resume(),0,self.output)
        self.assertFalse(Path(self.root,'a.txt').exists());self.check_invariants()

    def test_frozen_brief_and_moved_workflow_do_not_change_resume(self):
        brief=Path(self.side,'brief.md');brief.write_text('Original brief marker')
        tasks=H+A.replace('prompt="Write a"','prompt_file='+json.dumps(str(brief))+'\nneeds=["human"]')
        self.wf_path=self.revised(tasks)
        self.script([writes('a.txt')]);self.assertEqual(self.start(),255,self.output)
        Path(self.wf_path).rename(Path(self.side,'moved.toml'))
        brief.write_text('Changed source brief')
        self.assertEqual(self.runner('approve','latest','human','-C',self.root),0,self.output)
        self.assertEqual(self.resume(),0,self.output)
        self.assertIn('Original brief marker',self.prompt(1))
        self.assertNotIn('Changed source brief',self.prompt(1));self.check_invariants()

    def test_replan_cannot_change_root_or_active_candidate(self):
        self.workflow(A+H.replace('type="human"','type="human"\nverifies="a"'))
        self.script([writes('a.txt')]);self.assertEqual(self.start(),255,self.output)
        self.assertEqual(self.replan(self.revised(A)),2,self.output)
        self.assertIn('holds the work tree',self.output);self.check_invariants()

    def test_reopen_crash_after_revert_commit_resumes_without_duplicate_reverts(self):
        self.workflow(A+B);self.script([writes('a.txt'),writes('b.txt')]);self.assertEqual(self.start(),0,self.output)
        path=self.revised(A.replace('Write a','New a')+B)
        class Killed(Exception):pass
        def crash(point):
            if point=='revert:1:committed':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.replan(path,'--reopen','a')
        self.cli.CRASH=None
        self.script([writes('a.txt','new\n'),writes('b.txt','new\n')])
        self.assertEqual(self.resume(),0,self.output)
        subjects=self.git_out('log','--format=%s','main..HEAD').splitlines()
        self.assertEqual(sum(s.startswith('Revert ') for s in subjects),2)
        self.check_invariants()

    def test_replan_crash_after_definition_copy_is_idempotent(self):
        self.workflow(H);self.script([writes('a.txt')]);self.assertEqual(self.start(),255,self.output)
        path=self.revised(H+A)
        class Killed(Exception):pass
        def crash(point):
            if point=='replan:definitions-installed':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.replan(path)
        self.cli.CRASH=None
        self.assertEqual(self.resume(),255,self.output)  # standalone human still waits; independent a runs
        self.assertEqual(self.status('a'),'accepted')
        self.assertEqual(self.the_run().state['intents'],[]);self.check_invariants()

    def test_committed_definition_edits_allowed_but_unrelated_changes_refused(self):
        self.workflow(H);self.script([writes('a.txt')]);self.assertEqual(self.start(),255,self.output)
        self.write('wf.toml',Path(self.wf_path).read_text()+A)
        self.commit()
        self.assertEqual(self.runner('replan','latest','-C',self.root),0,self.output)
        self.write('README.md','unrelated\n');self.commit()
        self.assertEqual(self.runner('replan','latest','-C',self.root),2,self.output)
        self.assertIn('more than workflow definitions',self.output)

    def test_reopen_conflict_stops_before_other_reverts(self):
        from unittest.mock import patch
        from taskrunner import gitops
        self.workflow(A+B);self.script([writes('a.txt'),writes('b.txt')]);self.assertEqual(self.start(),0,self.output)
        original=gitops.Git.revert_commits
        def conflict(git,commits,op_id,run_id,since,crash):
            raise gitops.RevertConflict(commits[0],'deliberate conflict')
        tip=self.git_out('rev-parse','HEAD')
        with patch.object(gitops.Git,'revert_commits',conflict):
            self.assertEqual(self.replan(self.revised(A+B),'--reopen','a'),2,self.output)
        self.assertIn('conflicts',self.output)
        self.assertEqual(self.git_out('rev-parse','HEAD'),tip)
        self.assertEqual(self.status('a'),'accepted')
        self.assertEqual(len(self.the_run().state['intents']),1)

    def test_changed_agent_profile_requires_reopen_of_accepted_work(self):
        self.workflow(A);self.script([writes('a.txt')]);self.assertEqual(self.start(),0,self.output)
        path=Path(self.revised(A));path.write_text(path.read_text().replace('[agents.fake]', '[agents.fake]\nmodel="changed-profile"'))
        self.assertEqual(self.replan(str(path)),2,self.output)
        self.assertIn('--reopen',self.output)
        self.assertEqual(self.status('a'),'accepted')

    def test_external_commit_during_interrupted_replan_is_refused(self):
        self.workflow(A);self.script([writes('a.txt')]);self.assertEqual(self.start(),0,self.output)
        class Killed(Exception):pass
        def crash(point):
            if point=='replan:intent-recorded':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.replan(self.revised(A),'--reopen','a')
        self.cli.CRASH=None
        self.write('foreign.txt','unexpected\n');self.commit()
        tip=self.git_out('rev-parse','HEAD')
        self.assertEqual(self.resume(),2,self.output)
        self.assertIn('branch changed during replan',self.output)
        self.assertEqual(self.git_out('rev-parse','HEAD'),tip)

    def test_interrupted_replan_rejects_changed_frozen_definition(self):
        self.workflow(H);self.script([]);self.assertEqual(self.start(),255,self.output)
        class Killed(Exception):pass
        def crash(point):
            if point=='replan:intent-recorded':raise Killed()
        self.cli.CRASH=crash
        with self.assertRaises(Killed):self.replan(self.revised(H+A))
        self.cli.CRASH=None
        staged=Path(self.the_run().path,'replans','001','after','workflow.expanded.json')
        staged.write_text(staged.read_text().replace('Write a','Tampered brief'))
        self.assertEqual(self.resume(),2,self.output)
        self.assertIn('was changed',self.output)
        self.assertFalse(Path(self.root,'a.txt').exists())
