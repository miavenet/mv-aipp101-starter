"""One producer transaction, end to end, with the scripted agent: acceptance and rework (ACC),
freezing and protection (FRZ), failure and the DAG (FAIL), and resuming from disk (RUN-03, RUN-12).

Every test ends with `check_invariants`: every accepted commit is exactly the verified candidate,
and nothing else is in the tree when a transaction ends."""

import hashlib
import json
import os
import subprocess
import sys
import unittest

from helpers import RUNNER, EngineCase, done, git

from taskrunner import agents, prompts, validate

ONE = '''
[[task]]
id = "make"
type = "implement"
prompt = "Make src/a.txt say good."
outputs = ["src/a.txt"]
gate = ["grep -q good src/a.txt"]
'''
GOOD = {"write": {"src/a.txt": "good\n"}, "answer": done()}
BAD = {"write": {"src/a.txt": "bad\n"}, "answer": done()}


def bad(n):
    return {"write": {"src/a.txt": f"bad {n}\n"}, "answer": done()}


class Acceptance(EngineCase):
    def test_agent_report_is_never_acceptance(self):
        """acc: agent report is never acceptance (ACC-01)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate ="))
        self.script([{"write": {"src/a.txt": "bad\n"}, "answer": done("All done and tested.")}])
        self.assertEqual(self.start(), 2)
        self.assertEqual(self.status("make"), "failed")
        self.assertEqual(self.git_out("log", "--oneline", "main..HEAD"), "")
        self.check_invariants()

    def test_output_contract(self):
        """acc: output contract (ACC-02)"""
        self.write("old/legacy.txt", "x\n")
        self.workflow('''
[[task]]
id = "make"
type = "implement"
prompt = "p"
outputs = ["src/a.txt", "src/b.txt"]
writes = ["src/**", "old/**"]
removes = ["old/legacy.txt"]
gate = ["true"]
''')
        self.script([{"write": {"src/a.txt": ""}, "answer": done()},
                     {"write": {"src/a.txt": "a\n", "src/b.txt": "b\n"}, "remove": ["old/legacy.txt"],
                      "answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        feedback = self.prompt(2)
        self.assertIn("the declared output src/a.txt is empty", feedback)
        self.assertIn("the declared output src/b.txt does not exist", feedback)
        self.assertIn("old/legacy.txt must not exist afterwards", feedback)
        self.assertFalse(os.path.exists(os.path.join(self.root, "old/legacy.txt")))
        self.check_invariants()

    def test_gates_before_reviews(self):
        """acc: gates before reviews (ACC-03; the reviewer half arrives with stage 5)"""
        self.workflow(ONE.replace("grep -q good src/a.txt",
                                  "grep -q good src/a.txt || { echo MARKER-7731; exit 1; }"))
        self.script([BAD, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("MARKER-7731", self.prompt(2))
        self.assertIn("did not pass", self.prompt(2))
        self.assertTrue(os.path.exists(self.task_file("make", "attempt-2", "feedback.md")))
        self.check_invariants()

    def test_no_progress_needs_an_unchanged_tree(self):
        """acc: no-progress needs an unchanged tree (ACC-04)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 5\ngate ="))
        self.script([BAD, BAD, GOOD])
        self.assertEqual(self.start(), 2)
        self.assertEqual(self.calls(), 2)
        self.assertIn("no progress", self.the_run().state["tasks"]["make"]["reason"])
        self.check_invariants()

        # The same failure after a real change is not "no progress": the attempt limit applies.
        self.script([bad(1), bad(2), bad(3), bad(4), bad(5), GOOD])
        self.assertEqual(self.runner("retry", "latest", "make", "-C", self.root), 0, self.output)
        self.assertEqual(self.resume(), 2)
        self.assertEqual(self.calls(), 5)
        self.assertIn("5 attempts used", self.the_run().state["tasks"]["make"]["reason"])
        self.check_invariants()

    def test_rework_continues_the_session(self):
        """acc: rework continues the session (ACC-06)"""
        class Sessions(agents.CommandAgent):
            def capabilities(self):
                return super().capabilities() | {"resume"}

            def interpret(self, res):
                result = super().interpret(res)
                result.session_id = "session-1"
                return result

        self.addCleanup(agents.REGISTRY.__setitem__, "command", agents.CommandAgent)
        agents.REGISTRY["command"] = Sessions
        self.workflow(ONE)
        self.script([BAD, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("Make src/a.txt say good.", self.prompt(1))
        self.assertNotIn("Make src/a.txt say good.", self.prompt(2))      # only the feedback
        self.assertIn("did not pass", self.prompt(2))
        argv = self.read_json("make", "attempt-2", "invocation-1", "argv.json")
        self.assertEqual(argv["session_id"], "session-1")
        self.check_invariants()

    def test_rework_without_resume(self):
        """acc: rework without resume (ACC-21)"""
        self.workflow(ONE)
        self.script([BAD, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        second = self.prompt(2)
        self.assertIn("Make src/a.txt say good.", second)                # the full prompt again
        self.assertIn("Your previous attempt was not accepted", second)   # plus the feedback
        argv = self.read_json("make", "attempt-2", "invocation-1", "argv.json")
        self.assertIsNone(argv["session_id"])
        self.check_invariants()

    def test_broken_session_is_abandoned(self):
        """acc: broken session is abandoned (ACC-07)"""
        self.workflow(ONE.replace("gate =", "timeout_min = 0.02\ngate ="))
        self.script([{"exit": 3}, {"hang": True}, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("ended with an error", self.prompt(2))
        self.assertIn("Make src/a.txt say good.", self.prompt(2))
        self.assertIn("ran past its time limit", self.prompt(3))
        outcome = self.read_json("make", "attempt-2", "invocation-1", "outcome.json")
        self.assertEqual(outcome["status"], "timed-out")
        self.assertIsNone(self.read_json("make", "attempt-3", "invocation-1", "argv.json")["session_id"])
        self.check_invariants()

    def test_attempts_bounded_by_gates(self):
        """acc: attempts bounded by gates (ACC-08)"""
        self.workflow(ONE)
        self.script([bad(1), bad(2), bad(3), GOOD])
        self.assertEqual(self.start(), 2)
        self.assertEqual((self.status("make"), self.calls()), ("failed", 3))
        self.check_invariants()

    def test_blocked_is_a_legal_answer(self):
        """acc: blocked is a legal answer (ACC-10)"""
        self.workflow(ONE)
        self.script([{"answer": {"outcome": "blocked", "summary": "", "responses": [],
                                 "blocked_reason": "The gate greps a file the brief forbids."}}])
        self.assertEqual(self.start(), 255)
        st = self.the_run().state["tasks"]["make"]
        self.assertEqual(st["status"], "blocked")
        self.assertIn("The gate greps a file the brief forbids.", st["reason"])
        self.check_invariants()

    def test_invalid_answers_are_protocol_retries(self):
        """A prose answer is retried at most twice in fresh invocation directories, and uses no
        producer attempt (A6)."""
        self.workflow(ONE)
        self.script([{"write": {"src/a.txt": "good\n"}, "raw_answer": "I think it went well."},
                     {"answer": {"outcome": "done"}},
                     {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(self.the_run().state["tasks"]["make"]["attempts_used"], 1)
        for n in (1, 2, 3):
            self.assertTrue(os.path.isdir(self.task_file("make", "attempt-1", f"invocation-{n}")))
        self.assertEqual(self.read_json("make", "attempt-1", "result.json")["agent_calls"], 3)
        self.check_invariants()

    def test_verifying_check(self):
        """acc: verifying check (ACC-11)"""
        self.workflow(ONE + '''
[[task]]
id = "words"
type = "check"
verifies = "make"
read_only = true
run = ["grep -q 'very good' src/a.txt || { echo NEEDS-VERY; exit 1; }"]
''')
        self.script([GOOD, {"write": {"src/a.txt": "very good\n"}, "answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("NEEDS-VERY", self.prompt(2))
        self.assertEqual(self.status("words"), "accepted")
        self.check_invariants()

    def test_human_rejection(self):
        """acc: human rejection (ACC-12)"""
        self.workflow(ONE + '[[task]]\nid = "look"\ntype = "human"\nverifies = "make"\n')
        self.script([GOOD, {"write": {"src/a.txt": "good, and polite\n"}, "answer": done()}])
        self.assertEqual(self.start(), 255)
        self.check_invariants()
        self.assertEqual(self.runner("reject", "latest", "look", "-m", "Say it politely.",
                                     "-C", self.root), 0, self.output)
        self.assertEqual(self.resume(), 255)
        self.assertIn("Say it politely.", self.prompt(2))
        self.assertEqual(self.runner("approve", "latest", "look", "-C", self.root), 0)
        self.assertEqual(self.resume(), 0, self.output)
        self.assertEqual(self.read_json("look", "decision.json")["decision"], "approve")
        self.assertEqual(self.calls(), 2)                 # approval repeats no work
        self.check_invariants()

    def test_undeclared_writes_are_reverted(self):
        """acc: undeclared writes are reverted (ACC-13)"""
        self.workflow(ONE)
        self.script([{"write": {"src/a.txt": "good\n", "NOTES.md": "scratch\n"}, "answer": done()},
                     {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertFalse(os.path.exists(os.path.join(self.root, "NOTES.md")))
        self.assertIn("NOTES.md: it is outside this task's `writes`", self.prompt(2))
        reverted = self.read_json("make", "attempt-1", "reverted.json")
        self.assertEqual([r["path"] for r in reverted], ["NOTES.md"])
        self.assertEqual(self.git_out("show", "--name-only", "--format=", "HEAD"), "src/a.txt")
        self.check_invariants()

    def test_gates_must_not_change_the_candidate(self):
        """acc: gates must not change the candidate (ACC-14)"""
        self.workflow(ONE.replace('gate = ["grep -q good src/a.txt"]',
                                  'max_attempts = 1\ngate = ["echo rewritten > src/a.txt; echo x > litter.log"]'))
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        verification = self.read_json("make", "attempt-1", "verification.json")
        self.assertEqual(verification["results"][0]["result"], "void")
        self.assertEqual(sorted(verification["results"][0]["changed_the_tree"]),
                         ["litter.log", "src/a.txt"])
        cause = self.the_run().state["tasks"]["make"]["last_cause"]
        self.assertIn("echo rewritten > src/a.txt", cause)
        self.assertIn("litter.log", cause)
        self.check_invariants()

    def test_checks_must_not_change_the_candidate(self):
        """acc: checks must not change the candidate (ACC-15)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate =") + '''
[[task]]
id = "fmt"
type = "check"
verifies = "make"
run = ["echo formatted >> src/a.txt"]
''')
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        self.assertIn("src/a.txt", self.the_run().state["tasks"]["make"]["last_cause"])
        with open(self.task_file("make", "failed.patch")) as fh:
            self.assertNotIn("formatted", fh.read())      # the patch holds the author's work only
        self.check_invariants()

    def test_commit_exactly_the_verified_candidate(self):
        """acc: commit exactly the verified candidate (ACC-16)"""
        self.workflow(ONE + '[[task]]\nid = "c"\ntype = "check"\nverifies = "make"\n'
                      'read_only = true\nrun = ["true"]\n')
        self.script([BAD, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        st = self.the_run().state["tasks"]["make"]
        verification = self.read_json("make", "attempt-2", "verification.json")
        self.assertEqual([r["verifier"] for r in verification["results"]], ["gate:1", "c"])
        self.assertEqual({r["candidate"] for r in verification["results"]}, {st["candidate"]})
        self.assertTrue(all(len(r["config_sha256"]) == 64 for r in verification["results"]))
        self.assertEqual(self.git_out("rev-parse", "HEAD^{tree}"), st["candidate"])
        self.assertEqual(self.git_out("rev-list", "--count", "main..HEAD"), "1")    # GIT-02
        body = self.git_out("log", "-1", "--format=%B")
        self.assertIn(f"Run: {self.the_run().state['run_id']}", body)
        self.assertIn("Task: make", body)
        self.check_invariants()

    def test_deletions_and_empty_files(self):
        """acc: deletions and empty files (ACC-17)"""
        self.write("legacy/mod.py", "x = 1\n")
        self.workflow('''
[[task]]
id = "make"
type = "implement"
prompt = "p"
outputs = [{ path = "pkg/__init__.py", may_be_empty = true }]
writes = ["pkg/**", "legacy/**"]
removes = ["legacy/**"]
gate = ['test -z "$(ls legacy 2>/dev/null)"']
''')
        self.script([{"write": {"pkg/__init__.py": ""}, "remove": ["legacy/mod.py"],
                      "answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.check_invariants()

    def test_work_must_be_visible_to_git(self):
        """acc: work must be visible to git (ACC-18)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate ="))
        self.script([{"write": {".gitignore": "src/\n", "src/a.txt": "good\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        cause = self.the_run().state["tasks"]["make"]["last_cause"]
        self.assertIn(".gitignore: it is protected", cause)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))
        self.check_invariants()

    def test_a_task_that_owns_gitignore_cannot_hide_its_output(self):
        """acc: work must be visible to git (ACC-18, the task owns .gitignore)"""
        self.workflow(ONE.replace('gate =', 'writes = ["src/**", ".gitignore"]\n'
                                  'max_attempts = 1\ngate ='))
        self.script([{"write": {".gitignore": "src/\n", "src/a.txt": "good\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        self.assertIn("src/a.txt is now ignored by git",
                      self.the_run().state["tasks"]["make"]["last_cause"])
        self.check_invariants()

    def test_standalone_verifiers(self):
        """acc: standalone verifiers (ACC-19)"""
        self.workflow(ONE + '''
[[task]]
id = "lint"
type = "check"
needs = ["make"]
read_only = true
run = ["false"]
[[task]]
id = "after"
type = "human"
needs = ["lint"]
''')
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        state = self.the_run().state["tasks"]
        self.assertEqual((state["lint"]["status"], state["after"]["status"]), ("failed", "skipped"))
        self.assertIn("'lint' is failed", state["after"]["reason"])
        self.check_invariants()

    def test_standalone_human_rejection(self):
        """acc: standalone verifiers (ACC-19, the human half)"""
        self.workflow(ONE + '[[task]]\nid = "signoff"\ntype = "human"\nneeds = ["make"]\n'
                      '[[task]]\nid = "later"\ntype = "check"\nneeds = ["signoff"]\nrun = ["true"]\n')
        self.script([GOOD])
        self.assertEqual(self.start(), 255)
        self.assertIsNone(self.the_run().state["active_producer"])       # it holds nothing
        self.assertEqual(self.runner("reject", "latest", "signoff", "-m", "Not this quarter.",
                                     "-C", self.root), 0)
        self.assertEqual(self.resume(), 255)
        state = self.the_run().state["tasks"]
        self.assertEqual((state["signoff"]["status"], state["later"]["status"]),
                         ("blocked", "skipped"))
        self.assertEqual(self.read_json("signoff", "decision.json")["note"], "Not this quarter.")
        self.check_invariants()

    def test_destructive_verifiers_are_restored(self):
        """acc: destructive verifiers are restored (ACC-20)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate =") + '''
[[task]]
id = "mutants"
type = "check"
verifies = "make"
restores = true
run = ["echo mutated > src/a.txt; sleep 30"]
''', defaults="gate_timeout_min = 0.01")
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        results = self.read_json("make", "attempt-1", "verification.json")["results"]
        self.assertEqual((results[1]["result"], results[1]["runs"][0]["result"]), ("fail", "timeout"))
        self.assertEqual(results[1]["changed_the_tree"], ["src/a.txt"])
        self.assertNotIn("changed the candidate", self.the_run().state["tasks"]["make"]["reason"])
        with open(self.task_file("make", "failed.patch")) as fh:
            self.assertNotIn("mutated", fh.read())
        self.check_invariants()

    def test_a_destructive_verifier_that_passes(self):
        """acc: destructive verifiers are restored (ACC-20, the passing case)"""
        self.workflow(ONE + '[[task]]\nid = "mutants"\ntype = "check"\nverifies = "make"\n'
                      'restores = true\nrun = ["echo mutated > src/a.txt"]\n')
        self.script([GOOD])
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(self.git_out("show", "HEAD:src/a.txt"), "good")
        self.check_invariants()

    def test_what_a_rework_prompt_holds(self):
        """acc: what a rework prompt holds (ACC-22; findings arrive with stage 5, so this is the
        composition and the validator, which the engine already uses)"""
        answered = [{"id": "make/PE-1", "severity": "blocking", "title": "Off by one",
                     "response": "fixed: bounds corrected"},
                    {"id": "make/SC-1", "severity": "blocking", "title": "Wrong field width",
                     "response": "fixed"}]
        text = prompts.feedback_text({"cause_title": "`ctest` did not pass", "cause": "FAILED t3",
                                      "needing": [], "info": answered}, 60000)
        self.assertIn("FAILED t3", text)
        self.assertIn("For information, no response needed", text)
        self.assertIn("make/PE-1", text)
        self.assertNotIn("Findings that need a response", text)
        self.assertEqual(validate.check_produce(done(), needing_response=[]), [])
        errors = validate.check_produce(done(), needing_response=["make/PE-2"])
        self.assertIn("no entry for finding make/PE-2", errors[0])
        twice = done(responses=[{"finding": "make/PE-1", "action": "fixed", "note": "again"}])
        self.assertIn("not listed as needing a response", validate.check_produce(twice, [])[0])


class Freezing(EngineCase):
    TWO = '''
[[task]]
id = "a"
type = "implement"
prompt = "Make a."
outputs = ["src/a.txt"]
gate = ["grep -q good src/a.txt"]
[[task]]
id = "b"
type = "implement"
prompt = "Make b."
needs = ["a"]
outputs = ["src/b.txt"]
{b_extra}
gate = ["true"]
'''

    def test_protected_files(self):
        """frz: protected files (FRZ-01)"""
        self.write("docs/spec/x.md", "spec\n")
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**", "docs/**"]'),
                      defaults='protected = ["docs/spec/**"]')
        self.script([{"write": {"src/a.txt": "good\n", "docs/spec/x.md": "edited\n",
                                "docs/spec/new.md": "new\n"}, "answer": done()},
                     {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        with open(os.path.join(self.root, "docs/spec/x.md")) as fh:
            self.assertEqual(fh.read(), "spec\n")
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs/spec/new.md")))
        self.assertIn("docs/spec/x.md: it is protected", self.prompt(2))
        self.assertIn("docs/spec/new.md: it is protected", self.prompt(2))
        self.check_invariants()

    def test_accepted_outputs_are_frozen(self):
        """frz: accepted outputs are frozen (FRZ-02)"""
        self.workflow(self.TWO.format(b_extra=""))
        self.script([{"write": {"src/a.txt": "good\n"}, "answer": done("A is made.")},
                     {"write": {"src/b.txt": "b\n", "src/a.txt": "good, but edited by b\n"},
                      "answer": done()},
                     {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("frozen output of accepted task 'a'", self.prompt(3))
        self.assertEqual(self.git_out("show", "HEAD:src/a.txt"), "good")
        self.assertIn("A is made.", self.prompt(2))              # inputs: the upstream summary
        self.assertIn("src/a.txt", self.prompt(2))
        self.check_invariants()

    def test_explicit_claim(self):
        """frz: explicit claim (FRZ-03)"""
        self.workflow(self.TWO.format(b_extra='writes = ["src/b.txt", "src/a.txt"]'))
        self.script([{"write": {"src/a.txt": "good\n"}, "answer": done()},
                     {"write": {"src/b.txt": "b\n", "src/a.txt": "good, extended by b\n"},
                      "answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertEqual(self.git_out("show", "HEAD:src/a.txt"), "good, extended by b")
        with open(self.task_file("b", "attempt-1", "changes.diff")) as fh:
            self.assertIn("src/a.txt", fh.read())
        self.check_invariants()

    def test_checked_after_gates(self):
        """frz: checked after gates (FRZ-04)"""
        self.write("docs/spec/x.md", "spec\n")
        self.workflow(ONE.replace('gate = ["grep -q good src/a.txt"]',
                                  'max_attempts = 1\ngate = ["echo hacked > docs/spec/x.md"]'),
                      defaults='protected = ["docs/spec/**"]')
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        with open(os.path.join(self.root, "docs/spec/x.md")) as fh:
            self.assertEqual(fh.read(), "spec\n")
        self.assertIn("docs/spec/x.md", self.the_run().state["tasks"]["make"]["last_cause"])
        self.check_invariants()

    def test_claims_re_run_the_gates_they_touch(self):
        """frz: claims re-run the gates they touch (FRZ-05)"""
        self.workflow(self.TWO.format(b_extra='writes = ["src/b.txt", "src/a.txt"]\nmax_attempts = 1'))
        self.script([{"write": {"src/a.txt": "good\n"}, "answer": done()},
                     {"write": {"src/b.txt": "b\n", "src/a.txt": "broken by b\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        results = self.read_json("b", "attempt-1", "verification.json")["results"]
        self.assertEqual([(r["verifier"], r["result"]) for r in results],
                         [("gate:1", "pass"), ("regression:a:gate:1", "fail")])
        self.assertEqual(self.status("b"), "failed")
        self.assertEqual(self.git_out("show", "HEAD:src/a.txt"), "good")
        self.check_invariants()

    def test_stale_acceptance_is_shown(self):
        """frz: stale acceptance is shown (FRZ-06)"""
        self.workflow('''
[[task]]
id = "a"
type = "design"
prompt = "Write a."
outputs = ["docs/a.md"]
gate = ["test -s docs/a.md"]
[[task]]
id = "c"
type = "design"
prompt = "Write c from a."
needs = ["a"]
outputs = ["docs/c.md"]
[[task]]
id = "c-ok"
type = "human"
verifies = "c"
[[task]]
id = "b"
type = "design"
prompt = "Revise a."
needs = ["a", "c"]
outputs = ["docs/b.md"]
writes = ["docs/b.md", "docs/a.md"]
gate = ["true"]
''')
        self.script([{"write": {"docs/a.md": "v1\n"}, "answer": done()},
                     {"write": {"docs/c.md": "from v1\n"}, "answer": done()},
                     {"write": {"docs/b.md": "b\n", "docs/a.md": "v2\n"}, "answer": done()}])
        self.assertEqual(self.start(), 255)
        self.assertEqual(self.runner("approve", "latest", "c-ok", "-C", self.root), 0)
        self.assertEqual(self.resume(), 0, self.output)
        stale = self.the_run().state["tasks"]["c"]["stale"]
        self.assertEqual([(s["file"], s["by"]) for s in stale], [("docs/a.md", "b")])
        self.assertNotEqual(stale[0]["was"], stale[0]["now"])
        self.assertNotIn("stale", self.the_run().state["tasks"]["a"])      # a has a gate: re-run
        verifiers = [r["verifier"] for r in
                     self.read_json("b", "attempt-1", "verification.json")["results"]]
        self.assertIn("regression:a:gate:1", verifiers)
        with open(os.path.join(self.the_run().path, "STATUS.md")) as fh:
            status = fh.read()
        self.assertIn("accepted (stale)", status)
        self.assertIn("older version of docs/a.md", status)
        self.check_invariants()

    def test_the_record_protects_itself(self):
        """frz: the record protects itself (FRZ-07)"""
        self.workflow(ONE)
        self.script([{"write": {"src/a.txt": "good\n"},
                      "run": ["for f in .runs/demo/*/state.json; do echo tampered >> $f; done"],
                      "answer": done()}])
        self.assertEqual(self.start(), 2)
        st = self.the_run().state["tasks"]["make"]
        self.assertEqual(st["status"], "failed")
        self.assertIn("the run record was changed", st["reason"])
        self.assertIn("state.json", st["reason"])
        self.check_invariants()

    def test_a_gate_cannot_rewrite_a_finished_result(self):
        """frz: the record protects itself (FRZ-07, a decision-bearing file of a finished
        directory, changed by a gate)"""
        self.workflow(ONE + '[[task]]\nid = "second"\ntype = "implement"\nprompt = "p"\n'
                      'needs = ["make"]\noutputs = ["src/b.txt"]\nmax_attempts = 1\n'
                      'gate = ["for f in .runs/demo/*/tasks/010-make/attempt-1/verification.json; '
                      'do echo {} > $f; done"]\n')
        self.script([GOOD, {"write": {"src/b.txt": "b\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        st = self.the_run().state["tasks"]["second"]
        self.assertIn("the run record was changed", st["reason"])
        self.assertIn("verification.json", st["reason"])

    def test_protection_cannot_be_narrowed(self):
        """frz: protection cannot be narrowed (FRZ-08)"""
        self.write("docs/spec/x.md", "spec\n")
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**", "docs/**"]\nprotected = []'),
                      defaults='protected = ["docs/spec/**"]')
        self.script([{"write": {"src/a.txt": "good\n", "docs/spec/x.md": "edited\n"},
                      "answer": done()}, {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("docs/spec/x.md: it is protected", self.prompt(2))
        self.check_invariants()

    def test_the_record_is_exported_only_where_needed(self):
        """frz: the record is exported only where needed (FRZ-09); run: environment (RUN-09)"""
        env = os.path.join(self.side, "env")
        self.workflow(f'''
[[task]]
id = "make"
type = "implement"
prompt = "p"
outputs = ["src/a.txt"]
gate = ["env > {env}.gate"]
[[task]]
id = "report"
type = "summarize"
prompt = "Summarise."
needs = ["make"]
outputs = ["docs/report.md"]
gate = ["true"]
''')
        self.script([{"write": {"src/a.txt": "good\n"}, "run": [f"env > {env}.make"],
                      "answer": done()},
                     {"write": {"docs/report.md": "r\n"}, "run": [f"env > {env}.report"],
                      "answer": done()}])
        os.environ["ANTHROPIC_API_KEY"] = "not-for-gates"
        self.assertEqual(self.start(), 0, self.output)
        seen = {}
        for who in ("make", "report", "gate"):
            with open(f"{env}.{who}") as fh:
                seen[who] = dict(l.rstrip("\n").split("=", 1) for l in fh if "=" in l)
        run = self.the_run()
        for who, task in (("make", "make"), ("report", "report"), ("gate", "make")):
            self.assertEqual(seen[who]["TASK_RUNNER_RUN"], run.state["run_id"])
            self.assertEqual(seen[who]["TASK_RUNNER_TASK"], task)
        self.assertEqual(seen["report"]["TASK_RUNNER_RUN_DIR"], run.path)
        self.assertNotIn("TASK_RUNNER_RUN_DIR", seen["make"])
        self.assertNotIn("TASK_RUNNER_RUN_DIR", seen["gate"])
        self.assertIn("ANTHROPIC_API_KEY", seen["make"])
        self.assertNotIn("ANTHROPIC_API_KEY", seen["gate"])       # gates never see agent credentials
        self.check_invariants()

    def test_files_a_gate_executes_are_protected(self):
        """frz: files a gate executes are protected (FRZ-10)"""
        self.write("tools/check.py", "import sys\nsys.exit(0 if 'good' in open('src/a.txt').read() else 1)\n")
        self.workflow(ONE.replace('gate = ["grep -q good src/a.txt"]',
                                  'writes = ["src/**", "tools/**"]\ngate = ["python3 tools/check.py"]'))
        self.script([{"write": {"src/a.txt": "bad\n", "tools/check.py": "import sys\nsys.exit(0)\n"},
                      "answer": done()}, GOOD])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("tools/check.py: it is protected", self.prompt(2))
        self.assertEqual(self.git_out("show", "--name-only", "--format=", "HEAD"), "src/a.txt")
        self.check_invariants()

    def test_an_embedded_repository_is_removed_early(self):
        """git: unsupported entries are removed early (GIT-11, through the engine)"""
        self.workflow(ONE)
        self.script([{"write": {"src/a.txt": "good\n"},
                      "run": ["git init -q src/nested", "git init -q src/vendored && cd src/vendored "
                              "&& git -c user.email=a@b -c user.name=n commit -q --allow-empty -m x"],
                      "answer": done()}, {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("embedded git repository at 'src/nested'", self.prompt(2))
        self.assertIn("src/vendored", self.prompt(2))
        self.assertFalse(os.path.exists(os.path.join(self.root, "src/nested")))
        self.check_invariants()

    def test_a_link_out_of_the_repository_is_not_accepted(self):
        """A symbolic link inside `writes` that points outside the repository is put back (B3)."""
        self.workflow(ONE.replace('outputs = ["src/a.txt"]',
                                  'outputs = ["src/a.txt"]\nwrites = ["src/**"]'))
        self.script([{"write": {"src/a.txt": "good\n"}, "symlink": {"src/escape": self.side},
                      "answer": done()}, {"answer": done()}])
        self.assertEqual(self.start(), 0, self.output)
        self.assertIn("src/escape: it is a symbolic link that points outside", self.prompt(2))
        self.assertFalse(os.path.lexists(os.path.join(self.root, "src/escape")))
        self.check_invariants()


class Failure(EngineCase):
    def test_work_is_set_aside(self):
        """fail: work is set aside (FAIL-01)"""
        self.write("src/keep.txt", "keep\n")
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**"]\nmax_attempts = 1'))
        self.script([{"write": {"src/a.txt": "bad\n", "src/keep.txt": "changed\n",
                                "src/deep/er/new.txt": "n\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        with open(self.task_file("make", "failed.patch")) as fh:
            patch = fh.read()
        for path in ("src/a.txt", "src/keep.txt", "src/deep/er/new.txt"):
            self.assertIn(path, patch)
        with open(os.path.join(self.root, "src/keep.txt")) as fh:
            self.assertEqual(fh.read(), "keep\n")
        self.assertFalse(os.path.exists(os.path.join(self.root, "src/deep")))     # GIT-16
        self.check_invariants()

    def test_restore_by_type_and_mode(self):
        """fail: restore by type and mode (FAIL-02, through the engine)"""
        self.write("src/run.sh", "#!/bin/sh\n")
        os.chmod(os.path.join(self.root, "src/run.sh"), 0o755)
        self.write("src/f.txt", "file\n")
        self.write("src/data.bin", "old\n")
        os.symlink("f.txt", os.path.join(self.root, "src/link"))
        outside = os.path.join(self.side, "victim.txt")
        with open(outside, "w") as fh:
            fh.write("untouched\n")
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**"]\nmax_attempts = 1'))
        self.script([{"write": {"src/a.txt": "bad\n", "src/with space\nand newline.txt": "odd\n"},
                      "run": ["chmod 644 src/run.sh", "rm src/f.txt && mkdir src/f.txt && "
                              "echo inner > src/f.txt/inner", f"rm src/link && ln -s {outside} src/link",
                              "printf '\\000\\001\\002' > src/data.bin"],
                      "answer": done()}])
        self.assertEqual(self.start(), 2)
        self.assertTrue(os.access(os.path.join(self.root, "src/run.sh"), os.X_OK))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "src/f.txt")))
        self.assertEqual(os.readlink(os.path.join(self.root, "src/link")), "f.txt")
        with open(outside) as fh:
            self.assertEqual(fh.read(), "untouched\n")
        self.check_invariants()

    def test_other_branches_continue(self):
        """fail: other branches continue (FAIL-03)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate =") + '''
[[task]]
id = "after"
type = "implement"
prompt = "p"
needs = ["make"]
outputs = ["src/after.txt"]
gate = ["true"]
[[task]]
id = "after-check"
type = "check"
verifies = "after"
run = ["true"]
[[task]]
id = "other"
type = "implement"
prompt = "Independent."
outputs = ["other/o.txt"]
gate = ["true"]
''')
        self.script([BAD, {"match": "Independent", "write": {"other/o.txt": "o\n"},
                           "answer": done()}])
        self.assertEqual(self.start(), 2)
        state = self.the_run().state["tasks"]
        self.assertEqual({k: v["status"] for k, v in state.items()},
                         {"make": "failed", "after": "skipped", "after-check": "skipped",
                          "other": "accepted"})
        self.assertIn("'make' is failed", state["after"]["reason"])
        self.assertIn("'after' is skipped", state["after-check"]["reason"])
        self.check_invariants()

    def test_retry(self):
        """fail: retry (FAIL-04); rec: attempt numbers are never reused (REC-07, through the engine)"""
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**"]\nmax_attempts = 1')
                      + '[[task]]\nid = "after"\ntype = "check"\nneeds = ["make"]\nrun = ["true"]\n')
        self.script([{"write": {"src/a.txt": "bad\n", "src/notes.txt": "kept work\n"},
                      "answer": done()}])
        self.assertEqual(self.start(), 2)
        self.assertEqual(self.status("after"), "skipped")

        # With the patch: the base still matches, so the work is put back and attempts restart.
        self.script([{"match": "set aside and is back in place",
                      "write": {"src/a.txt": "good\n"}, "answer": done()}])
        self.assertEqual(self.runner("retry", "latest", "make", "--apply-patch", "-C", self.root),
                         0, self.output)
        self.assertEqual(self.status("after"), "pending")
        self.assertEqual(self.resume(), 0, self.output)
        self.assertEqual(self.git_out("show", "HEAD:src/notes.txt"), "kept work")
        self.assertTrue(os.path.isdir(self.task_file("make", "attempt-2")))
        self.assertFalse(os.path.exists(self.task_file("make", "attempt-2", "..", "attempt-1",
                                                       "prompt.md.changed")))
        self.check_invariants()

    def test_retry_refuses_a_patch_whose_base_moved(self):
        """fail: retry (FAIL-04, the refusal)"""
        self.workflow(ONE.replace("gate =", "max_attempts = 1\ngate =") + '''
[[task]]
id = "other"
type = "implement"
prompt = "Independent."
outputs = ["other/o.txt"]
gate = ["true"]
''')
        self.script([BAD, {"write": {"other/o.txt": "o\n"}, "answer": done()}])
        self.assertEqual(self.start(), 2)
        self.assertEqual(self.runner("retry", "latest", "make", "--apply-patch", "-C", self.root), 2)
        self.assertIn("other work was accepted since", self.output)
        self.assertEqual(self.status("make"), "failed")
        self.assertEqual(self.runner("retry", "latest", "other", "-C", self.root), 2)   # accepted
        self.script([GOOD])
        self.assertEqual(self.runner("retry", "latest", "make", "-C", self.root), 0)
        self.assertEqual(self.resume(), 0, self.output)
        self.assertNotIn("set aside and is back", self.prompt(1))         # a clean start
        self.check_invariants()

    def test_environment_failures_use_no_attempts(self):
        """FAIL-06: a missing binary is rejected before any producer attempt or run exists."""
        self.workflow(ONE.replace('type = "implement"', 'type = "implement"\nagent = "ghost"')
                      + '[agents.ghost]\nargv = ["/nonexistent/agent-binary"]\n')
        self.assertEqual(self.start(), 2)
        self.assertIn("/nonexistent/agent-binary", self.output)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".runs", "demo")))

    def test_recovery_artifacts_are_complete_and_pinned(self):
        """fail: recovery artifacts are complete and pinned (FAIL-07)"""
        self.workflow(ONE.replace('outputs = ["src/a.txt"]', 'outputs = ["src/a.txt"]\n'
                                  'writes = ["src/**"]\nmax_attempts = 1'),
                      defaults="diff_cap_bytes = 200")
        big = "".join(f"line {n}\n" for n in range(400))
        self.script([{"write": {"src/a.txt": "bad\n", "src/big.txt": big},
                      "run": ["head -c 2048 /dev/urandom > src/blob.bin"], "answer": done()}])
        self.assertEqual(self.start(), 2)
        with open(self.task_file("make", "attempt-1", "changes.diff")) as fh:
            self.assertIn("[diff truncated", fh.read())
        run = self.the_run()
        st = run.state["tasks"]["make"]
        git(self.root, "gc", "-q", "--prune=now")
        ref = f"refs/task-runner/{run.name}/make/set-aside"
        self.assertEqual(self.git_out("cat-file", "-t", ref), "tree")
        git(self.root, "apply", "--check", self.task_file("make", "failed.patch"))
        git(self.root, "apply", self.task_file("make", "failed.patch"))
        git(self.root, "add", "-A")
        self.assertEqual(self.git_out("write-tree"), self.git_out("rev-parse", ref))
        git(self.root, "reset", "-q", "--hard")
        self.assertEqual(st["status"], "failed")


def tree_digest(path):
    digest = hashlib.sha256()
    for dirpath, dirnames, files in os.walk(path):
        dirnames.sort()
        for name in sorted(f for f in files if f not in ("index.json", "STATUS.md")):
            with open(os.path.join(dirpath, name), "rb") as fh:
                digest.update(os.path.relpath(os.path.join(dirpath, name), path).encode() + b"\0"
                              + fh.read())
    return digest.hexdigest()


class Killed(Exception):
    pass


class Resume(EngineCase):
    WF = ONE + '''
[[task]]
id = "words"
type = "check"
verifies = "make"
read_only = true
run = ["true"]
[[task]]
id = "doomed"
type = "implement"
prompt = "This one fails."
needs = ["make"]
outputs = ["src/d.txt"]
max_attempts = 1
gate = ["false"]
'''
    POINTS = ["state:before-rename", "agent:running", "attempt:after-agent", "verify:after-command",
              "commit:intent-recorded", "commit:after-commit-object", "commit:after-update-ref",
              "commit:before-outcome", "set-aside:before-restore", "restore:after-removals"]

    def kill_at(self, point, nth=1):
        seen = {"n": 0}

        def hook(where):
            if where == point:
                seen["n"] += 1
                if seen["n"] == nth:
                    raise Killed(where)
        self.cli.CRASH = hook

    def test_resume_from_disk(self):
        """run: resume from disk (RUN-03): killed at each of these points, `resume` continues and
        no finished attempt directory is changed"""
        for point in self.POINTS:
            with self.subTest(point=point):
                self.setUp()
                self.workflow(self.WF)
                steps = [BAD, GOOD, GOOD, {"write": {"src/d.txt": "d\n"}, "answer": done()},
                         {"write": {"src/d.txt": "d\n"}, "answer": done()}]
                self.script(steps)
                self.kill_at(point, nth=3 if point == "state:before-rename" else 1)
                with self.assertRaises(Killed):
                    self.start()
                finished = {}
                for tid in ("make", "doomed"):
                    tdir = self.the_run().task_dir(tid)
                    for name in os.listdir(tdir):
                        full = os.path.join(tdir, name)
                        if name.startswith("attempt-") and os.path.exists(
                                os.path.join(full, "verification.json")):
                            finished[full] = tree_digest(full)
                self.cli.CRASH = None
                self.assertEqual(self.resume(), 2, self.output)      # `doomed` fails by design
                state = self.the_run().state["tasks"]
                self.assertEqual((state["make"]["status"], state["words"]["status"],
                                  state["doomed"]["status"]), ("accepted", "accepted", "failed"),
                                 self.output)
                self.assertEqual(self.git_out("rev-list", "--count", "main..HEAD"), "1")
                for path, digest in finished.items():
                    self.assertEqual(tree_digest(path), digest, path)
                self.check_invariants()
                self.doCleanups()

    def test_a_real_kill(self):
        """run: resume from disk (RUN-03, with the process really gone: exit without cleanup)"""
        self.workflow(ONE)
        self.script([GOOD, GOOD])
        env = dict(os.environ, TASK_RUNNER_CRASH_AT="commit:after-update-ref")
        res = subprocess.run([sys.executable, RUNNER, "start", self.wf_path], env=env,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 70, res.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.root, ".runs", "lock")))   # a stale lock
        res = subprocess.run([sys.executable, RUNNER, "resume", "-C", self.root],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("the commit had been made", res.stdout)
        self.assertEqual(self.calls(), 1)                          # the author is not run again
        self.assertEqual(self.git_out("rev-list", "--count", "main..HEAD"), "1")
        self.check_invariants()

    def test_external_changes_while_paused(self):
        """run: external changes while paused (RUN-12)"""
        self.workflow(ONE + '[[task]]\nid = "look"\ntype = "human"\nverifies = "make"\n')
        self.script([GOOD])
        self.assertEqual(self.start(), 255)
        self.runner("approve", "latest", "look", "-C", self.root)
        self.write("src/a.txt", "good, but someone edited it while the run waited\n")
        self.assertEqual(self.resume(), 2)
        self.assertIn("reconciliation error", self.output)
        self.assertIn("the work tree changed: src/a.txt", self.output)
        self.assertEqual(self.status("make"), "waiting_human")
        self.write("src/a.txt", "good\n")

        self.write("elsewhere.txt", "x\n")
        git(self.root, "add", "elsewhere.txt")
        git(self.root, "commit", "-q", "-m", "someone commits on the run branch", "elsewhere.txt")
        self.assertEqual(self.resume(), 2)
        self.assertIn("the branch tip changed", self.output)

    def test_resume_on_the_wrong_branch(self):
        self.workflow(ONE + '[[task]]\nid = "look"\ntype = "human"\nneeds = ["make"]\n')
        self.script([GOOD])
        self.assertEqual(self.start(), 255)
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(self.resume(), 2)
        self.assertIn("is checked out", self.output)

    def test_interrupted_standalone_check_restores_before_retry(self):
        self.workflow('[[task]]\nid = "check"\ntype = "check"\nrestores = true\n'
                      'run = ["echo changed > README.md"]\n' + ONE)
        self.script([GOOD])
        # Interrupt after the command has returned but before its tree is restored.
        from taskrunner import checks
        original = checks.run_commands
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise Killed("after command")
        from unittest.mock import patch
        with patch.object(checks, "run_commands", interrupted):
            with self.assertRaises(Killed):
                self.start()
        self.assertEqual(self.status("check"), "running")
        self.assertEqual(self.resume(), 0, self.output)
        self.assertEqual(self.git_out("show", "HEAD:README.md"), "scratch")
        self.check_invariants()

    def test_reviews_wait_for_stage_5(self):
        self.workflow(ONE.replace("gate =", 'reviewers = ["principal-engineer"]\ngate ='))
        self.script([GOOD])
        self.assertEqual(self.start(), 2)
        self.assertIn("reviews arrive in stage 5", self.output)
        self.assertEqual(self.calls(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".runs")))



if __name__ == "__main__":
    unittest.main()
