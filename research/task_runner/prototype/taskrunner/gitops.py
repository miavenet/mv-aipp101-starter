"""Git helpers. Work-tree snapshots use a scratch index, so the real index is never touched.

The run directory ignores itself (.runner/.gitignore holds "*"), so it never shows up here.
"""

import fnmatch
import os
import subprocess
import tempfile



class Git:
    def __init__(self, root):
        self.root = root
        self.ok = self._run("rev-parse", "--is-inside-work-tree")[0] == 0

    def _run(self, *args, env=None, stdin=None):
        p = subprocess.run(["git", "-c", f"safe.directory={self.root}", "-c", "core.quotepath=off", *args],
                           cwd=self.root, capture_output=True, text=True, input=stdin,
                           env={**os.environ, **(env or {})})
        return p.returncode, p.stdout, p.stderr

    def _check(self, *args, env=None):
        code, out, err = self._run(*args, env=env)
        if code:
            raise RuntimeError(f"git {' '.join(args[:2])}: {err.strip()}")
        return out

    def dirty(self):
        return bool(self._check("status", "--porcelain").strip())

    def snapshot(self):
        """Tree id of the whole work tree, untracked files included."""
        with tempfile.TemporaryDirectory() as d:
            env = {"GIT_INDEX_FILE": os.path.join(d, "index")}
            if self._run("rev-parse", "--verify", "-q", "HEAD")[0] == 0:
                self._check("read-tree", "HEAD", env=env)
            self._check("add", "-A", env=env)
            return self._check("write-tree", env=env).strip()

    def changed(self, base, now):
        out = self._check("diff", "--name-only", "-z", base, now)
        return [f for f in out.split("\0") if f]

    def diff(self, base, now, limit=60000):
        text = self._check("diff", base, now)
        return text if len(text) <= limit else text[:limit] + f"\n[diff cut at {limit} of {len(text)} characters]\n"

    def restore(self, base, paths):
        """Put paths back to their state in the base tree. Paths that did not exist there are removed."""
        for path in paths:
            if self._run("cat-file", "-e", f"{base}:{path}")[0] == 0:
                blob = subprocess.run(["git", "-c", f"safe.directory={self.root}", "cat-file", "blob", f"{base}:{path}"],
                                      cwd=self.root, capture_output=True).stdout
                os.makedirs(os.path.dirname(os.path.join(self.root, path)) or self.root, exist_ok=True)
                with open(os.path.join(self.root, path), "wb") as f:
                    f.write(blob)
            else:
                try:
                    os.remove(os.path.join(self.root, path))
                except OSError:
                    pass

    def switch(self, branch):
        if self._run("rev-parse", "--verify", "-q", f"refs/heads/{branch}")[0] == 0:
            self._check("switch", branch)
        else:
            self._check("switch", "-c", branch)

    def commit(self, paths, message):
        self._check("add", "-A", "--", *paths)
        self._check("commit", "-q", "-m", message, "--", *paths)
        return self._check("rev-parse", "--short", "HEAD").strip()


def protected_hits(paths, globs):
    return sorted(p for p in paths if any(fnmatch.fnmatch(p, g) for g in globs))
