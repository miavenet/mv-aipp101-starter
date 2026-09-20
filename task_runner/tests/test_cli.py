"""The command line: validate and graph (WF-13), start, status, runs and prune (RUN-01, RUN-02,
RUN-17, GIT-05, GIT-14), and the stubs of later stages."""

import json
import os
import re
import shutil
import subprocess
import unittest

from helpers import RepoCase, git, run_cli

WORKFLOW = """
name = "demo"
[[task]]
id = "design"
type = "design"
outputs = ["docs/d.md"]
reviewers = ["principal-engineer", { perspective = "devops", advisory = true }]
[[task]]
id = "implement"
type = "implement"
needs = ["design"]
outputs = ["src/**"]
gate = ["true"]
[[task]]
id = "lint"
type = "check"
verifies = "implement"
read_only = true
run = ["true"]
[[task]]
id = "signoff"
type = "human"
needs = ["implement"]
"""


class Cli(RepoCase):
    def test_validate_prints_the_expanded_dag(self):
        path = self.write("wf.toml", WORKFLOW)
        res = run_cli("validate", path)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = [l for l in res.stdout.splitlines() if re.match(r"\s+\d+  ", l)]
        ids = [l.split()[1] for l in lines]
        self.assertEqual(ids, ["design", "design.review.principal-engineer", "design.review.devops",
                               "implement", "lint", "signoff"])
        self.assertIn("reviews design (advisory)", res.stdout)
        self.assertIn("verifies implement; read-only", res.stdout)
        self.assertIn("needs design", res.stdout)
        self.assertIn("claims on frozen outputs: none", res.stdout)

    def test_validate_reports_every_error_and_exits_2(self):
        path = self.write("wf.toml", WORKFLOW.replace('gate = ["true"]', 'gaet = ["true"]')
                          .replace('needs = ["implement"]', 'needs = ["nobody"]'))
        res = run_cli("validate", path)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown key 'gaet'", res.stderr)
        self.assertIn("unknown task 'nobody'", res.stderr)
        self.assertIn("2 errors", res.stderr)
        self.assertEqual(res.stdout, "")

    def test_validate_shows_claims(self):
        path = self.write("wf.toml", WORKFLOW + '[[task]]\nid = "extend"\ntype = "implement"\n'
                          'needs = ["implement"]\noutputs = ["src/extra.cpp"]\ngate = ["true"]\n')
        res = run_cli("validate", path)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("warning: 'extend' will modify outputs of accepted task 'implement'", res.stderr)
        self.assertIn("extend will modify", res.stdout)

    def test_dot_export(self):
        """wf: dot export (WF-13)"""
        path = self.write("wf.toml", WORKFLOW)
        res = run_cli("graph", path)
        self.assertEqual(res.returncode, 0, res.stderr)
        dot = res.stdout
        self.assertTrue(dot.startswith('digraph "demo" {'))
        self.assertEqual(dot.rstrip()[-1], "}")
        self.assertEqual(dot.count("{"), dot.count("}"))
        nodes = re.findall(r'^  "([^"]+)" \[label=', dot, re.M)
        self.assertEqual(sorted(nodes), sorted(["design", "design.review.principal-engineer",
                                                "design.review.devops", "implement", "lint", "signoff"]))
        edges = set(re.findall(r'^  "([^"]+)" -> "([^"]+)" \[label="(\w+)"', dot, re.M))
        self.assertEqual(edges, {
            ("design", "implement", "needs"), ("implement", "signoff", "needs"),
            ("design", "design.review.principal-engineer", "reviews"),
            ("design", "design.review.devops", "reviews"), ("implement", "lint", "verifies")})
        self.assertIn("style=dashed", dot)
        self.assertIn("style=dotted", dot)

    def test_graph_to_a_file(self):
        path = self.write("wf.toml", WORKFLOW)
        out = os.path.join(self.root, "g.dot")
        res = run_cli("graph", path, "-o", out)
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        with open(out) as fh:
            self.assertIn("digraph", fh.read())

    def test_later_commands_say_so(self):
        for cmd, stage in (("replan", 6),):
            res = run_cli(cmd, "whatever")
            self.assertEqual(res.returncode, 2)
            self.assertIn(f"not implemented yet (stage {stage})", res.stderr)

    def test_no_command(self):
        self.assertEqual(run_cli().returncode, 2)

    def test_the_shipped_example_validates(self):
        example = os.path.join(os.path.dirname(__file__), "..", "examples", "book-module.toml")
        res = run_cli("validate", example)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("13 tasks", res.stdout)


def gitout(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


class Runs(RepoCase):
    RUN_WORKFLOW = 'name = "demo"\n[[task]]\nid = "design"\ntype = "human"\n'
    def setUp(self):
        super().setUp()
        self.wf = self.write("wf.toml", self.RUN_WORKFLOW)
        self.commit()

    def start(self):
        res = run_cli("start", self.wf)
        self.assertEqual(res.returncode, 255, res.stderr)
        self.assertIn("needs_human", res.stderr)
        return re.search(r"^run (\S+)", res.stdout, re.M).group(1)

    def run_info(self, name):
        with open(os.path.join(self.root, ".runs", "demo", name, "run.json")) as fh:
            return json.load(fh)

    def run_dirs(self):
        base = os.path.join(self.root, ".runs", "demo")
        return sorted(n for n in os.listdir(base) if n != "latest")

    def test_start_always_creates(self):
        """run: start always creates (RUN-01)"""
        first = self.start()
        second = self.start()
        self.assertNotEqual(first, second)
        self.assertEqual(sorted([first, second]), self.run_dirs())
        with open(os.path.join(self.root, ".runs", "demo", "latest")) as fh:
            self.assertEqual(fh.read().strip(), second)
        ids = [self.run_info(d)["run_id"] for d in (first, second)]
        self.assertNotEqual(ids[0], ids[1])

    def test_the_run_branch_is_checked_out(self):
        """git: the run branch is checked out (GIT-14)"""
        before = gitout(self.root, "rev-parse", "HEAD^{tree}")
        name = self.start()
        info = self.run_info(name)
        self.assertEqual(info["branch"], f"run/demo-{info['run_id'][:8]}")
        self.assertEqual(info["original_branch"], "main")
        self.assertEqual(gitout(self.root, "symbolic-ref", "--short", "HEAD"), info["branch"])
        self.assertEqual(gitout(self.root, "rev-parse", "HEAD^{tree}"), before)
        self.assertEqual(gitout(self.root, "status", "--porcelain"), "")
        self.assertEqual(info["base_commit"], gitout(self.root, "rev-parse", "main"))

    def test_no_dirty_starts(self):
        """run: no dirty starts (RUN-02)"""
        self.write("src/a.py", "a = 1\n")
        self.commit()
        self.write("src/a.py", "a = 2\n")
        git(self.root, "add", "src/a.py")
        self.write("src/a.py", "a = 3\n")
        status = gitout(self.root, "status", "--porcelain")
        index = gitout(self.root, "ls-files", "--stage")
        res = run_cli("start", self.wf)
        self.assertEqual(res.returncode, 2)
        self.assertIn("not clean", res.stderr)
        self.assertIn("src/a.py", res.stderr)
        self.assertEqual(gitout(self.root, "status", "--porcelain"), status)
        self.assertEqual(gitout(self.root, "ls-files", "--stage"), index)
        with open(os.path.join(self.root, "src/a.py")) as fh:
            self.assertEqual(fh.read(), "a = 3\n")
        self.assertEqual(gitout(self.root, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertFalse(os.path.exists(os.path.join(self.root, ".runs")))
        self.assertNotIn("dirty", run_cli("start", "--help").stdout)      # no option to override

    def test_current_branch_option(self):
        """git: current branch option (GIT-05)"""
        self.wf = self.write("wf.toml", self.RUN_WORKFLOW.replace('name = "demo"',
                                                          'name = "demo"\n[defaults]\nbranch = "current"'))
        self.commit()
        name = self.start()
        info = self.run_info(name)
        self.assertEqual((info["branch"], info["original_branch"]), ("main", "main"))
        self.assertEqual(gitout(self.root, "branch", "--format=%(refname:short)"), "main")
        git(self.root, "checkout", "-q", "--detach")
        res = run_cli("start", self.wf)
        self.assertEqual(res.returncode, 2)
        self.assertIn("detached", res.stderr)

    def test_a_held_lock_refuses_a_second_runner(self):
        """run: lock (RUN-07, at the command line)"""
        from taskrunner import record
        runs = record.ensure_runs_dir(self.root)
        lock = record.Lock(runs).acquire("someone-else")
        try:
            res = run_cli("start", self.wf)
            self.assertEqual(res.returncode, 2)
            self.assertIn("another runner holds this repository", res.stderr)
            self.assertEqual(gitout(self.root, "symbolic-ref", "--short", "HEAD"), "main")
        finally:
            lock.release()

    def test_status_and_runs(self):
        name = self.start()
        res = run_cli("status", "-C", self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("| 010 | design | human | waiting_human |", res.stdout)
        info = self.run_info(name)
        for ref in (name, info["run_id"][:6], "latest"):
            self.assertEqual(run_cli("status", ref, "-C", self.root).stdout, res.stdout)
        self.assertEqual(run_cli("status", "nope", "-C", self.root).returncode, 2)

        status_md = os.path.join(self.root, ".runs", "demo", name, "STATUS.md")
        os.unlink(status_md)
        rebuilt = run_cli("status", name, "--rebuild", "-C", self.root)
        self.assertEqual(rebuilt.stdout, res.stdout)
        self.assertTrue(os.path.exists(status_md))

        listed = run_cli("runs", self.wf)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(name, listed.stdout)
        self.assertIn("needs_human", listed.stdout)
        self.assertIn(name, run_cli("runs", "demo", "-C", self.root).stdout)

    def test_prune(self):
        """run: prune (RUN-17)"""
        from taskrunner import gitops, record
        done, deleted, unfinished = self.start(), self.start(), self.start()
        g = gitops.Git(self.root)
        tree = g.tree_of("HEAD")
        for name in (done, deleted, unfinished):
            g.pin(name, "design/base", tree)
        run = record.Run.load(os.path.join(self.root, ".runs", "demo", done))
        run.state["status"] = "done"
        run.save()
        shutil.rmtree(os.path.join(self.root, ".runs", "demo", deleted))
        res = run_cli("prune", "-C", self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(g.pinned_runs(), [unfinished])
        self.assertIn(f"pruned  {done}", res.stdout)
        self.assertIn(f"pruned  {deleted}", res.stdout)
        self.assertIn(f"kept    {unfinished}", res.stdout)


if __name__ == "__main__":
    unittest.main()
