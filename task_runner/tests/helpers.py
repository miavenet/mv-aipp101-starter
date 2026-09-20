"""Shared test helpers: a scratch git repository holding a workflow file."""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from taskrunner import workflow  # noqa: E402

RUNNER = os.path.normpath(os.path.join(HERE, "..", "runner"))


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class RepoCase(unittest.TestCase):
    """Each test gets an empty committed git repository in `self.root`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "config", "user.name", "Test")
        self.write("README.md", "scratch\n")
        self.commit()

    def write(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
        return full

    def commit(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c", "--allow-empty")

    def load(self, text, rel="workflow.toml"):
        return workflow.load(self.write(rel, text))

    def assertError(self, wf, *fragments):
        for e in wf.errors:
            if all(f in e for f in fragments):
                return e
        self.fail(f"no error containing {fragments!r} in:\n  " + "\n  ".join(wf.errors or ["(none)"]))

    def assertWarning(self, wf, *fragments):
        for w in wf.warnings:
            if all(f in w for f in fragments):
                return w
        self.fail(f"no warning containing {fragments!r} in:\n  " + "\n  ".join(wf.warnings or ["(none)"]))

    def assertLoads(self, wf):
        self.assertEqual(wf.errors, [])


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, RUNNER, *args], cwd=cwd, capture_output=True, text=True)
