"""The command line: validate and graph (WF-13), and the stubs of later stages."""

import os
import re
import unittest

from helpers import RepoCase, run_cli

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
        for cmd, stage in (("start", 2), ("doctor", 4), ("resolve", 5), ("replan", 6), ("prune", 2)):
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


if __name__ == "__main__":
    unittest.main()
