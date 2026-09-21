"""The run record: creation, durable state, intents and reconciliation, the lock, derived files.

Scenarios REC-01 to REC-13, REC-16 (REC-11 at primitive level is in test_gitops), RUN-07, RUN-08, RUN-11,
RUN-16, and the record half of FRZ-07. Each crash test stops the runner at an injected point,
then reconciles, as `resume` will.
"""

import json
import os
import signal
import subprocess
import sys
import time
import unittest

from helpers import RepoCase, git

from taskrunner import gitops, record, workflow

WORKFLOW = """
name = "demo"
[[task]]
id = "design"
type = "design"
prompt_file = "briefs/d.md"
outputs = ["docs/d.md"]
reviewers = ["principal-engineer", "spec-compliance"]
[[task]]
id = "implement"
type = "implement"
needs = ["design"]
outputs = ["src/**"]
gate = ["true"]
[[task]]
id = "signoff"
type = "human"
needs = ["implement"]
"""


class Crash(Exception):
    pass


def crash_at(name):
    def hook(point):
        if point == name:
            raise Crash(point)
    return hook


class RunCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.write("briefs/d.md", "Design it.\n")
        self.wf_path = self.write("wf.toml", WORKFLOW)
        self.commit()
        self.wf = workflow.load(self.wf_path)
        self.assertEqual(self.wf.errors, [])
        self.g = gitops.Git(self.root)
        self.g.create_and_checkout_run_branch("run/demo-test")
        self.run_ = record.Run.create(self.wf, self.g, "run/demo-test", "main")

    def reload(self):
        return record.Run.load(self.run_.path)

    def candidate(self, rel="docs/d.md", text="the design\n"):
        base = self.g.snapshot(self.run_.index_file)
        self.write(rel, text)
        cand = self.g.snapshot(self.run_.index_file)
        return base, cand, [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]

    def commit_intent(self, cand, paths):
        return self.run_.begin("commit", task="design", attempt=1, parent=self.g.head(),
                               candidate=cand, paths=paths, subject="Design the thing")

    def tree_files(self, top):
        out = {}
        for dirpath, _dirs, files in os.walk(top):
            for f in files:
                with open(os.path.join(dirpath, f), "rb") as fh:
                    out[os.path.relpath(os.path.join(dirpath, f), top)] = fh.read()
        return out


class Heartbeat(RunCase):
    """rec: STATUS.md shows what is in flight and how long, refreshed without a state change"""

    def status(self):
        with open(os.path.join(self.run_.path, "STATUS.md")) as fh:
            return fh.read()

    def test_in_flight_calls_show_their_age(self):
        import datetime
        self.run_.state["status"] = "running"
        op = self.run_.begin("agent", task="design", invocation_dir="tasks/010-design/attempt-1/invocation-1")
        began = self.run_.intent(op)["at"]
        self.run_.regenerate()
        text = self.status()                                          # deterministic: no clock in it
        self.assertIn("## In flight", text)
        self.assertIn(f"**design**: agent call, started {began[11:19]} UTC", text)
        self.assertNotIn("running for", text)
        state_before = record.read_json(os.path.join(self.run_.path, "state.json"))
        later = datetime.datetime.strptime(began, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=14, seconds=5)
        self.assertTrue(self.run_.refresh_status(now=later))
        text = self.status()
        self.assertIn("running for 14 min 05 s", text)
        self.assertIn(f"As of {later.strftime('%H:%M:%S')} UTC", text)
        self.assertEqual(record.read_json(os.path.join(self.run_.path, "state.json")), state_before)
        self.assertFalse(os.path.exists(os.path.join(self.run_.path, "STATUS.md.beat")))
        self.run_.finish(op, status="ok")
        self.run_.regenerate()
        self.assertNotIn("## In flight", self.status())

    def test_a_beat_never_raises(self):
        self.run_.state["status"] = "running"
        self.run_.state["intents"].append({"op": "x", "kind": "agent", "at": "not a time"})
        self.assertFalse(self.run_.refresh_status())


class BranchDisposition(RunCase):
    """rec: STATUS.md of a finished run says where its branch went, observed from git"""

    def finish(self):
        self.write("docs/d.md", "the design\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "design")
        self.run_.state["tasks"]["design"]["commit"] = self.g.head()
        for t in self.run_.state["tasks"].values():
            t["status"] = "accepted"
        self.run_.state["status"] = "done"
        self.run_.save()
        self.run_.regenerate()

    def status(self):
        with open(os.path.join(self.run_.path, "STATUS.md")) as fh:
            return fh.read()

    def test_unmerged_then_merged(self):
        self.finish()
        self.assertIn("Not merged: `main` does not contain", self.status())
        self.assertIn("merging it is your call", self.status())
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--ff-only", "run/demo-test")
        self.assertIn("Not merged", self.status())               # nothing regenerated it yet
        self.reload().regenerate()
        self.assertIn("Merged: the last accepted commit", self.status())
        self.assertIn("is in `main`.", self.status())             # no upstream: no push remark
        self.assertNotIn("your call", self.status())

    def test_an_unfinished_run_says_nothing_about_merging(self):
        self.run_.regenerate()
        self.assertNotIn("erged", self.status())


class Creation(RunCase):
    def test_layout(self):
        p = self.run_.path
        runs = os.path.join(self.root, ".runs")
        with open(os.path.join(runs, ".gitignore")) as fh:
            self.assertEqual(fh.read(), "*\n")
        with open(os.path.join(runs, "README.md")) as fh:
            self.assertIn("state.json", fh.read())
        self.assertRegex(os.path.basename(p), r"^demo-\d{8}T\d{6}Z-[0-9a-f]{8}$")
        with open(os.path.join(runs, "demo", "latest")) as fh:
            self.assertEqual(fh.read().strip(), os.path.basename(p))
        info = record.read_json(os.path.join(p, "run.json"))
        self.assertTrue(os.path.basename(p).endswith(info["run_id"][:8]))
        self.assertEqual((info["workflow"], info["branch"], info["original_branch"]),
                         ("demo", "run/demo-test", "main"))
        self.assertEqual(info["workflow_file"], self.wf_path)
        self.assertEqual(info["root"], self.root)
        self.assertEqual(set(info["spend"]), {"known_usd", "reserved_usd", "unpriced"})
        self.assertEqual(sorted(n for n in os.listdir(os.path.join(p, "tasks")) if n != "index.json"),
                         ["010-design", "011-design.review.principal-engineer",
                          "012-design.review.spec-compliance", "020-implement", "030-signoff"])
        with open(os.path.join(p, "workflow.toml")) as fh:
            self.assertEqual(fh.read(), WORKFLOW)
        with open(os.path.join(p, "briefs", "design.md")) as fh:
            self.assertEqual(fh.read(), "Design it.\n")
        self.assertEqual(sorted(os.listdir(os.path.join(p, "library", "types"))),
                         ["design-review.toml", "design.toml", "implement.toml", "index.json"])
        self.assertEqual(sorted(os.listdir(os.path.join(p, "library", "personas"))),
                         ["index.json", "principal-engineer.toml", "spec-compliance.toml"])
        expanded = record.read_json(os.path.join(p, "workflow.expanded.json"))
        self.assertEqual(len(expanded["tasks"]), 5)
        self.assertTrue(self.g.is_clean())                      # the record ignores itself

    def test_frozen_copies_do_not_follow_later_edits(self):
        self.write("briefs/d.md", "edited later\n")
        with open(os.path.join(self.run_.path, "briefs", "design.md")) as fh:
            self.assertEqual(fh.read(), "Design it.\n")


class DurableState(RunCase):
    def test_durable_state(self):
        """rec: durable state (REC-06)"""
        self.run_.set_status("design", "running")
        self.run_.save()
        self.run_.set_status("design", "accepted")
        self.run_.crash = crash_at("state:before-rename")
        with self.assertRaises(Crash):
            self.run_.save()
        self.assertTrue(os.path.exists(os.path.join(self.run_.path, "state.json.tmp")))
        again = self.reload()
        self.assertEqual(again.state["tasks"]["design"]["status"], "running")
        again.set_status("design", "verifying")
        again.save()                                            # the leftover does not get in the way
        self.assertEqual(self.reload().state["tasks"]["design"]["status"], "verifying")

    def test_intents_have_unique_ids_and_are_logged(self):
        a = self.run_.begin("pin", name="x", object="1" * 40)
        b = self.run_.begin("pin", name="y", object="1" * 40)
        self.assertNotEqual(a, b)
        self.assertEqual([i["op"] for i in self.reload().state["intents"]], [a, b])
        self.run_.finish(a, ref="x")
        self.assertEqual([i["op"] for i in self.reload().state["intents"]], [b])
        with open(os.path.join(self.run_.path, "events.jsonl")) as fh:
            events = [json.loads(line) for line in fh]
        self.assertEqual([e["event"] for e in events][-3:], ["intent", "intent", "outcome"])

    def test_attempt_numbers_are_never_reused(self):
        """rec: attempt numbers are never reused (REC-07, record level)"""
        n1, d1 = self.run_.new_attempt("design")
        n2, d2 = self.run_.new_attempt("design")
        self.assertEqual((n1, n2), (1, 2))
        with open(os.path.join(d2, "result.json"), "w") as fh:
            fh.write("{}")
        self.run_.state["tasks"]["design"]["attempts"] = 0       # what `retry` does to the counter
        n3, d3 = self.run_.new_attempt("design")
        self.assertEqual(n3, 3)
        self.assertEqual(os.listdir(d3), [])
        with open(os.path.join(d2, "result.json")) as fh:
            self.assertEqual(fh.read(), "{}")
        i1, p1 = self.run_.new_invocation(d3)
        i2, p2 = self.run_.new_invocation(d3)
        self.assertEqual((i1, i2), (1, 2))
        self.assertEqual(os.listdir(p2), [])                     # created exclusively: nothing stale
        r1, _ = self.run_.new_round("design.review.principal-engineer")
        self.assertEqual(r1, 1)


class Integrity(RunCase):
    def test_the_record_protects_itself(self):
        """frz: the record protects itself (FRZ-07, record level: detection; failing the job is
        the engine's)."""
        _n, adir = self.run_.new_attempt("design")
        result = os.path.join(adir, "result.json")
        with open(result, "w") as fh:
            fh.write('{"outcome": "done"}')
        findings = os.path.join(self.run_.task_dir("design"), "findings.json")
        self.run_.write_decision(findings, {"producer": "design", "findings": []})
        self.assertEqual(self.run_.close_directory(adir),
                         ["tasks/010-design/attempt-1/result.json"])

        guard = self.run_.integrity_begin()
        self.assertEqual(self.run_.integrity_end(guard), [])

        guard = self.run_.integrity_begin()
        with open(findings, "w") as fh:
            fh.write('{"producer": "design", "findings": [], "tidied": true}')
        self.assertEqual(self.run_.integrity_end(guard), ["tasks/010-design/findings.json was changed"])
        self.run_.write_decision(findings, {"producer": "design", "findings": []})

        guard = self.run_.integrity_begin()
        state = os.path.join(self.run_.path, "state.json")
        with open(state, "a") as fh:
            fh.write(" ")
        os.unlink(result)
        self.assertEqual(self.run_.integrity_end(guard),
                         ["tasks/010-design/attempt-1/result.json was removed",
                          "state.json was changed"])

    def test_a_run_can_be_deleted(self):
        """run: a run can be deleted (RUN-16)"""
        _n, adir = self.run_.new_attempt("design")
        _i, inv = self.run_.new_invocation(adir)
        with open(os.path.join(inv, "outcome.json"), "w") as fh:
            fh.write("{}")
        self.run_.close_directory(adir)
        self.run_.regenerate()
        for dirpath, _dirs, _files in os.walk(self.run_.path):
            self.assertTrue(os.access(dirpath, os.W_OK), dirpath)
        subprocess.run(["rm", "-rf", self.run_.path], check=True)
        self.assertFalse(os.path.exists(self.run_.path))
        with open(record.__file__) as fh:
            self.assertNotIn("chmod", fh.read())


class DerivedFiles(RunCase):
    def populate(self):
        _n, adir = self.run_.new_attempt("design")
        _i, inv = self.run_.new_invocation(adir)
        for d, name in ((adir, "prompt.md"), (adir, "result.json"), (inv, "stdout.log"),
                        (inv, "outcome.json")):
            with open(os.path.join(d, name), "w") as fh:
                fh.write("x")
        self.run_.set_status("design", "blocked", "the agent said the brief contradicts the spec")
        self.run_.set_status("implement", "skipped", "upstream blocked")
        self.run_.state["status"] = "needs_human"
        self.run_.save()
        self.run_.regenerate()

    def derived(self):
        return {k: v for k, v in self.tree_files(self.run_.path).items()
                if os.path.basename(k) in ("STATUS.md", "index.json")}

    def test_derived_files_are_derived(self):
        """run: derived files are derived (RUN-08)"""
        self.populate()
        before = self.derived()
        self.assertGreater(len(before), 8)
        for rel in before:
            os.unlink(os.path.join(self.run_.path, rel))
        self.reload().regenerate()
        self.assertEqual(self.derived(), before)

    def test_self_describing(self):
        """run: self-describing (RUN-11)"""
        self.populate()
        for dirpath, dirnames, filenames in os.walk(self.run_.path):
            index = record.read_json(os.path.join(dirpath, "index.json"))
            listed = set(index["files"])
            actual = set(filenames) | {d + "/" for d in dirnames}
            self.assertEqual(listed, actual, dirpath)
            self.assertTrue(index["about"], dirpath)
        top = record.read_json(os.path.join(self.run_.path, "index.json"))
        self.assertIn("single source of truth", top["files"]["state.json"])
        attempt = record.read_json(os.path.join(self.run_.task_dir("design"), "attempt-1",
                                                "index.json"))
        self.assertEqual(attempt["path"], "tasks/010-design/attempt-1")
        self.assertTrue(all(attempt["files"].values()))

    def test_status_says_what_happened(self):
        self.populate()
        with open(os.path.join(self.run_.path, "STATUS.md")) as fh:
            text = fh.read()
        self.assertIn("needs a person", text)
        self.assertIn("| 010 | design | design | blocked | 1 |", text)
        self.assertIn("skipped (upstream blocked)", text)
        self.assertIn("**design** is blocked: the agent said the brief contradicts the spec", text)
        info = record.read_json(os.path.join(self.run_.path, "run.json"))
        self.assertEqual(info["status"], "needs_human")


class Locking(RepoCase):
    def setUp(self):
        super().setUp()
        self.runs = record.ensure_runs_dir(self.root)

    def test_lock(self):
        """run: lock (RUN-07)"""
        first = record.Lock(self.runs).acquire("run-1")
        with self.assertRaises(record.LockHeld) as ctx:
            record.Lock(self.runs).acquire("run-2")
        self.assertIn("run-1", str(ctx.exception))
        first.release()
        record.Lock(self.runs).acquire("run-2").release()

    def test_process_identity_is_not_a_pid(self):
        """rec: process identity is not a pid (REC-08)"""
        mine = record.process_identity(os.getpid())
        stale = dict(mine, start_ticks=mine["start_ticks"] - 1)     # same pid, another process
        with open(os.path.join(self.runs, "lock"), "wb") as fh:
            fh.write(record.dump_json({"run_id": "dead-run", "process": stale}))
        self.assertTrue(record.is_alive(mine))
        self.assertFalse(record.is_alive(stale))
        lock = record.Lock(self.runs).acquire("run-3")
        self.assertEqual(lock.holder()["run_id"], "run-3")
        lock.release()

    def test_boot_id_is_part_of_process_identity(self):
        """rec: boot id is part of process identity (REC-13)"""
        mine = record.process_identity(os.getpid())
        self.assertTrue(mine["boot_id"])
        rebooted = dict(mine, boot_id="00000000-0000-0000-0000-000000000000")
        self.assertFalse(record.is_alive(rebooted))
        with open(os.path.join(self.runs, "lock"), "wb") as fh:
            fh.write(record.dump_json({"run_id": "before-reboot", "process": rebooted}))
        record.Lock(self.runs).acquire("after-reboot").release()

    def test_the_command_name_may_hold_parentheses(self):
        script = self.write("odd) name (x", "#!/bin/sh\nsleep 30\n")
        os.chmod(script, 0o755)
        child = subprocess.Popen([script], start_new_session=True)
        try:
            time.sleep(0.1)
            ident = record.process_identity(child.pid)
            self.assertIsInstance(ident["start_ticks"], int)
            self.assertEqual(ident["pgid"], child.pid)
        finally:
            child.kill()
            child.wait()
        self.assertIsNone(record.process_identity(child.pid))

    def test_an_unreadable_lock_is_held(self):
        with open(os.path.join(self.runs, "lock"), "w") as fh:
            fh.write("")
        with self.assertRaises(record.LockHeld):
            record.Lock(self.runs).acquire("run-4")


class CommitRecovery(RunCase):
    def test_intent_without_effect(self):
        """rec: intent without effect (REC-01)"""
        _base, cand, paths = self.candidate()
        tip = self.g.head()
        op = self.commit_intent(cand, paths)
        # killed here: the intent is on disk, the commit is not made
        run = self.reload()
        done = record.reconcile(run, self.g)
        self.assertEqual(len(done), 1)
        self.assertEqual(self.g.head() != tip, True)
        self.assertEqual(int(gitops._text(self.g.run("rev-list", "--count", f"{tip}..HEAD").stdout)), 1)
        self.assertTrue(self.g.find_operation(self.g.head(), op))
        st = self.reload().state
        self.assertEqual(st["tasks"]["design"]["status"], "accepted")
        self.assertEqual(st["tasks"]["design"]["commit"], self.g.head())
        self.assertEqual(st["intents"], [])
        commit_json = record.read_json(os.path.join(run.task_dir("design"), "commit.json"))
        self.assertEqual(commit_json["files"], ["docs/d.md"])

    def test_intent_without_effect_but_the_tree_changed(self):
        _base, cand, paths = self.candidate()
        self.commit_intent(cand, paths)
        self.write("docs/d.md", "someone edited the candidate\n")
        with self.assertRaises(record.ReconcileError):
            record.reconcile(self.reload(), self.g)

    def test_effect_without_outcome(self):
        """rec: effect without outcome (REC-02)"""
        _base, cand, paths = self.candidate()
        parent = self.g.head()
        op = self.commit_intent(cand, paths)
        with self.assertRaises(Crash):
            self.g.commit_candidate(cand, paths, "Design the thing", self.run_.state["run_id"],
                                    "design", op, parent, crash=crash_at("commit:after-index-sync"))
        tip = self.g.head()
        self.assertNotEqual(tip, parent)
        record.reconcile(self.reload(), self.g)
        self.assertEqual(self.g.head(), tip)                     # no second commit
        st = self.reload().state
        self.assertEqual((st["tasks"]["design"]["status"], st["tasks"]["design"]["commit"]),
                         ("accepted", tip))

    def test_index_sync_is_part_of_the_commit(self):
        """rec: index sync is part of the commit (REC-10)"""
        _base, cand, paths = self.candidate()
        parent = self.g.head()
        op = self.commit_intent(cand, paths)
        with self.assertRaises(Crash):
            self.g.commit_candidate(cand, paths, "Design the thing", self.run_.state["run_id"],
                                    "design", op, parent, crash=crash_at("commit:after-update-ref"))
        self.assertFalse(self.g.is_clean())                      # the stale index shows phantom changes
        record.reconcile(self.reload(), self.g)
        self.assertTrue(self.g.is_clean())
        self.assertEqual(self.reload().state["tasks"]["design"]["status"], "accepted")

    def test_unexpected_branch_tip(self):
        """rec: unexpected branch tip (REC-03)"""
        _base, cand, paths = self.candidate()
        self.commit_intent(cand, paths)
        git(self.root, "commit", "-q", "--allow-empty", "-m", "someone else")
        with self.assertRaises(record.ReconcileError) as ctx:
            record.reconcile(self.reload(), self.g)
        self.assertIn("Someone changed the branch", str(ctx.exception))
        self.assertEqual(len(self.reload().state["intents"]), 1)   # nothing was settled by guessing


class EffectRecovery(RunCase):
    def test_restores_are_re_run(self):
        """rec: restores are re-run (REC-09)"""
        base, cand, paths = self.candidate("src/deep/new.py", "x = 1\n")
        self.write("docs/other.md", "also new\n")
        cand = self.g.snapshot(self.run_.index_file)
        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        self.g.pin(self.run_.name, "design/base", base)
        self.run_.begin("restore", target=base, paths=paths, expected=base)
        with self.assertRaises(Crash):
            self.g.restore(base, paths, expected_tree=base, index_file=self.run_.index_file,
                           crash=crash_at("restore:after-removals"))
        record.reconcile(self.reload(), self.g)
        self.assertEqual(self.g.snapshot(self.run_.index_file), base)
        self.assertFalse(os.path.exists(os.path.join(self.root, "src")))
        self.assertEqual(self.reload().state["intents"], [])

    def test_idempotent_effects(self):
        """rec: idempotent effects (REC-12)"""
        base, cand, _paths = self.candidate()
        _n, adir = self.run_.new_attempt("design")
        with open(os.path.join(adir, "result.json"), "w") as fh:
            fh.write("{}")
        rel = os.path.relpath(adir, self.run_.path)
        self.run_.begin("pin", name="design/candidate-1", object=cand)
        self.run_.begin("close", dir=rel)
        self.run_.begin("patch", base=base, candidate=cand, path="tasks/010-design/failed.patch")
        self.g.pin(self.run_.name, "design/candidate-1", cand)   # the pin happened; the rest did not
        done = record.reconcile(self.reload(), self.g)
        self.assertEqual(len(done), 3)
        self.assertEqual(list(self.g.pins(self.run_.name).values()), [cand])
        run = self.reload()
        self.assertEqual(run.integrity_check(), [])
        self.assertIn("tasks/010-design/attempt-1/result.json", run._manifest()["files"])
        with open(os.path.join(run.task_dir("design"), "failed.patch"), "rb") as fh:
            self.assertEqual(fh.read(), self.g.full_patch(base, cand))
        self.assertEqual(record.reconcile(self.reload(), self.g), [])    # and once more: nothing to do

    def test_external_changes_while_paused(self):
        """run: external changes while paused (RUN-12, record level)"""
        tree = self.g.snapshot(self.run_.index_file)
        self.run_.state["expect"] = {"tip": self.g.head(), "tree": tree}
        self.run_.save()
        self.assertEqual(record.reconcile(self.reload(), self.g), [])
        self.write("docs/d.md", "edited while the run waited\n")
        with self.assertRaises(record.ReconcileError) as ctx:
            record.reconcile(self.reload(), self.g)
        self.assertIn("docs/d.md", str(ctx.exception))


class AgentRecovery(RunCase):
    def spawn(self, code):
        child = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
        self.addCleanup(lambda: (child.poll() is None and child.kill(), child.wait()))
        time.sleep(0.2)
        return child

    def agent_intent(self, child):
        _n, adir = self.run_.new_attempt("design")
        _i, inv = self.run_.new_invocation(adir)
        op = self.run_.begin("agent", task="design",
                             invocation_dir=os.path.relpath(inv, self.run_.path))
        self.run_.amend(op, process=record.process_identity(child.pid))
        self.run_.state["tasks"]["design"]["session_id"] = "sess-1"
        self.run_.save()
        return inv

    def test_no_concurrent_authors(self):
        """rec: no concurrent authors (REC-04)"""
        # The child ignores SIGINT and has a child of its own in the same group.
        child = self.spawn("import signal, subprocess, sys, time\n"
                           "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
                           "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                           "time.sleep(60)\n")
        inv = self.agent_intent(child)
        with self.assertRaises(record.OrphanAlive):
            record.reconcile(self.reload(), self.g)
        self.assertIsNone(child.poll())                          # refused, and left alone
        self.assertEqual(len(self.reload().state["intents"]), 1)

        record.reconcile(self.reload(), self.g, stop_orphans=True, grace_s=0.5)
        child.wait(timeout=5)
        with self.assertRaises(ProcessLookupError):
            os.killpg(child.pid, 0)                              # descendants are gone too
        self.assertEqual(record.read_json(os.path.join(inv, "outcome.json"))["status"], "interrupted")

    def test_unknown_completion_is_not_success(self):
        """rec: unknown completion is not success (REC-05)"""
        child = self.spawn("import time; time.sleep(60)")
        inv = self.agent_intent(child)
        child.send_signal(signal.SIGKILL)
        child.wait()
        run = self.reload()
        record.reconcile(run, self.g)
        self.assertEqual(record.read_json(os.path.join(inv, "outcome.json"))["status"], "interrupted")
        st = self.reload().state
        self.assertIsNone(st["tasks"]["design"]["session_id"])
        self.assertEqual(st["intents"], [])
        n, retry_dir = run.new_invocation(os.path.dirname(inv))
        self.assertEqual(n, 2)
        self.assertNotEqual(retry_dir, inv)
        self.assertTrue(os.path.exists(os.path.join(inv, "outcome.json")))


class DecisionPublication(RunCase):
    def set_aside_path(self):
        return os.path.join(self.run_.task_dir("design"), "set-aside.json")

    def set_aside_record(self, attempt):
        return {"task": "design", "attempt": attempt, "status": "blocked",
                "reason": f"reason of attempt {attempt}", "at": "2026-09-20T11:02:14Z",
                "paths": ["docs/d.md"]}

    def test_a_published_decision_is_protected_and_leaves_no_intent(self):
        path = self.set_aside_path()
        self.run_.publish_decision(path, self.set_aside_record(1))
        run = self.reload()
        self.assertEqual(record.read_json(path), self.set_aside_record(1))
        self.assertEqual(run.state["intents"], [])
        self.assertIn("tasks/010-design/set-aside.json", run._manifest()["files"])
        self.assertEqual(run.integrity_check(), [])
        with open(os.path.join(run.path, "events.jsonl"), encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
        self.assertEqual([e["event"] for e in events[-2:]], ["intent", "outcome"])
        self.assertEqual(events[-1]["kind"], "decision")

    def test_a_replaced_decision_file_is_repaired(self):
        """rec: a replaced decision file is repaired (REC-16)"""
        path = self.set_aside_path()
        self.run_.publish_decision(path, self.set_aside_record(1))
        with self.assertRaises(Crash):
            self.run_.publish_decision(path, self.set_aside_record(2),
                                       crash=crash_at("decision:file-written"))
        run = self.reload()
        self.assertEqual(record.read_json(path), self.set_aside_record(2))    # new bytes ...
        self.assertEqual(run.integrity_check(),
                         ["tasks/010-design/set-aside.json was changed"])     # ... under the old hash
        self.assertEqual([it["kind"] for it in run.state["intents"]], ["decision"])

        done = record.reconcile(run, self.g)
        self.assertEqual(len(done), 1)
        run = self.reload()
        self.assertEqual(run.state["intents"], [])
        self.assertEqual(run.integrity_check(), [])
        self.assertEqual(record.read_json(path), self.set_aside_record(2))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), record.dump_json(self.set_aside_record(2)))
        self.assertEqual(record.reconcile(self.reload(), self.g), [])         # and once more

    def test_a_first_decision_file_lost_before_its_manifest_entry_is_repaired(self):
        path = self.set_aside_path()
        with self.assertRaises(Crash):
            self.run_.publish_decision(path, self.set_aside_record(1),
                                       crash=crash_at("decision:file-written"))
        record.reconcile(self.reload(), self.g)
        run = self.reload()
        self.assertEqual(run.integrity_check(), [])
        self.assertIn("tasks/010-design/set-aside.json", run._manifest()["files"])
        self.assertEqual(record.read_json(path), self.set_aside_record(1))

    def test_an_intent_without_its_file_is_rebuilt_from_the_payload(self):
        """The crash came after the intent was durable and before any write: the file is missing,
        or still holds the previous record. Only the intent's payload can repair it."""
        path = self.set_aside_path()
        rel = "tasks/010-design/set-aside.json"
        self.run_.begin("decision", path=rel, payload=self.set_aside_record(1))
        self.assertFalse(os.path.exists(path))
        record.reconcile(self.reload(), self.g)
        run = self.reload()
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), record.dump_json(self.set_aside_record(1)))
        self.assertEqual(run._manifest()["files"][rel], record.sha256_file(path))
        self.assertEqual(run.integrity_check(), [])
        self.assertEqual(run.state["intents"], [])

        self.run_ = run
        run.begin("decision", path=rel, payload=self.set_aside_record(2))
        self.assertEqual(record.read_json(path), self.set_aside_record(1))    # the old record
        record.reconcile(self.reload(), self.g)
        run = self.reload()
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), record.dump_json(self.set_aside_record(2)))
        self.assertEqual(run._manifest()["files"][rel], record.sha256_file(path))
        self.assertEqual(run.integrity_check(), [])
        self.assertEqual(run.state["intents"], [])


if __name__ == "__main__":
    unittest.main()
