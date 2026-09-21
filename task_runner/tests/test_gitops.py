"""Git primitives: snapshots, pins, restore by type and mode, the commit recipe, reverts.

Scenarios GIT-01 to GIT-16, and the primitive-level halves of FAIL-02, FAIL-07 and REC-11.
Where a scenario's full form needs the engine, the docstring says which part is tested here.
"""

import os
import re
import stat
import subprocess
import tempfile
import unittest

from helpers import RepoCase, git

from taskrunner import gitops


def gitout(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


class GitCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.g = gitops.Git(self.root)
        self._idx = tempfile.TemporaryDirectory()
        self.addCleanup(self._idx.cleanup)
        self.index = os.path.join(self._idx.name, "git-index")

    def snap(self):
        return self.g.snapshot(self.index)

    def path(self, rel):
        return os.path.join(self.root, rel)


class Snapshots(GitCase):
    def test_snapshot_has_no_side_effects(self):
        """git: snapshot has no side effects (GIT-01)"""
        self.write("new.txt", "untracked\n")
        self.write("README.md", "edited\n")
        before_status = gitout(self.root, "status", "--porcelain")
        before_index = gitout(self.root, "ls-files", "--stage")
        tree = self.snap()
        self.assertRegex(tree, r"^[0-9a-f]{40}$")
        self.assertEqual(gitout(self.root, "status", "--porcelain"), before_status)
        self.assertEqual(gitout(self.root, "ls-files", "--stage"), before_index)
        with open(self.path("README.md")) as fh:
            self.assertEqual(fh.read(), "edited\n")

    def test_snapshot_of_a_clean_tree_is_heads_tree(self):
        self.assertEqual(self.snap(), self.g.tree_of("HEAD"))

    def test_untracked_files_are_seen(self):
        """git: untracked files are seen (GIT-03). Primitive level: the new file is in the diff
        between snapshots and in the commit made from the candidate."""
        base = self.snap()
        self.write("src/new.py", "print(1)\n")
        cand = self.snap()
        self.assertEqual(self.g.changed_paths(base, cand), [("A", "src/new.py", "000000", "100644")])
        self.assertIn("src/new.py", self.g.review_diff(base, cand))
        commit = self.g.commit_candidate(cand, ["src/new.py"], "t", "run", "task", "op-1",
                                         self.g.head())
        self.assertEqual(self.g.commit_files(commit), ["src/new.py"])

    def test_ignored_files_are_outside_the_snapshot(self):
        self.write(".gitignore", "build/\n")
        self.commit()
        base = self.snap()
        self.write("build/out.o", "x")
        self.assertEqual(self.snap(), base)
        self.assertEqual(list(self.g.check_ignored(["build/out.o", "README.md"])), ["build/out.o"])
        self.assertIn(".gitignore:1: build/", self.g.check_ignored(["build/out.o"])["build/out.o"])

    def test_the_reused_index_is_faithful(self):
        """git: the reused index is faithful (GIT-15)"""
        self.write("a.txt", "a\n")
        first = self.snap()
        second = self.snap()
        fresh = self.g.snapshot(os.path.join(self._idx.name, "another-index"))
        self.assertEqual({first, second, fresh}, {first})
        self.write("a.txt", "b\n")                      # and it still notices a change
        self.assertNotEqual(self.snap(), first)

    def test_snapshots_are_pinned(self):
        """git: snapshots are pinned (GIT-07)"""
        self.write("only-here.txt", "kept alive by a ref\n")
        tree = self.snap()
        ref = self.g.pin("20260919T000000Z-1a2b3c4d", "implement/candidate-1", tree)
        os.unlink(self.path("only-here.txt"))
        os.unlink(self.index)                           # nothing else refers to the tree
        git(self.root, "gc", "--prune=now", "-q")
        self.assertEqual(gitout(self.root, "cat-file", "-t", tree), "tree")
        self.assertEqual(self.g.pins("20260919T000000Z-1a2b3c4d"), {ref: tree})
        self.assertEqual(self.g.pin("20260919T000000Z-1a2b3c4d", "implement/candidate-1", tree), ref)

    def test_odd_names_survive(self):
        base = self.snap()
        odd = "dir with space/new\nline.txt"
        self.write(odd, "x\n")
        cand = self.snap()
        self.assertEqual([p for _s, p, _o, _n in self.g.changed_paths(base, cand)], [odd])


class Restore(GitCase):
    def test_restore_by_type_and_mode(self):
        """fail: restore by type and mode (FAIL-02, primitive level: the restore itself; the
        set-aside around it is the engine's)."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        victim = os.path.join(outside.name, "victim.txt")
        with open(victim, "w") as fh:
            fh.write("outside\n")
        odd = "odd dir/sp ace\nnewline.txt"
        self.write("run.sh", "#!/bin/sh\necho base\n")
        os.chmod(self.path("run.sh"), 0o755)
        os.symlink("README.md", self.path("link"))
        self.write("sub/deep/b.txt", "b\n")
        self.write("becomes-dir.txt", "file\n")
        self.write(odd, "odd\n")
        with open(self.path("blob.bin"), "wb") as fh:
            fh.write(bytes(range(256)) * 4)
        self.commit()
        base = self.snap()

        # the attempt
        self.write("run.sh", "#!/bin/sh\necho changed\n")
        os.chmod(self.path("run.sh"), 0o644)
        os.unlink(self.path("link"))
        os.symlink(victim, self.path("link"))
        os.rename(self.path("sub"), self.path("sub-moved"))
        os.symlink(outside.name, self.path("sub"))       # sub/ is now a link to outside
        os.makedirs(os.path.join(outside.name, "deep"))
        with open(os.path.join(outside.name, "deep", "b.txt"), "w") as fh:
            fh.write("outside b\n")
        os.unlink(self.path("becomes-dir.txt"))
        self.write("becomes-dir.txt/inner/c.txt", "c\n")
        self.write(odd, "changed\n")
        with open(self.path("blob.bin"), "wb") as fh:
            fh.write(b"\0\1\2")
        self.write("brand/new/file.txt", "new\n")
        cand = self.snap()

        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        self.g.restore(base, paths, expected_tree=base, index_file=self.index)

        self.assertEqual(self.snap(), base)
        self.assertTrue(os.stat(self.path("run.sh")).st_mode & stat.S_IXUSR)
        self.assertTrue(os.path.islink(self.path("link")))
        self.assertEqual(os.readlink(self.path("link")), "README.md")
        with open(victim) as fh:
            self.assertEqual(fh.read(), "outside\n")            # never written through
        self.assertFalse(os.path.islink(self.path("sub")))
        with open(os.path.join(outside.name, "deep", "b.txt")) as fh:
            self.assertEqual(fh.read(), "outside b\n")          # nothing outside changed
        self.assertTrue(os.path.isfile(self.path("becomes-dir.txt")))
        with open(self.path("blob.bin"), "rb") as fh:
            self.assertEqual(fh.read(), bytes(range(256)) * 4)
        self.assertFalse(os.path.exists(self.path("brand")))
        self.assertFalse(os.path.exists(self.path("sub-moved")))

    def test_links_are_never_followed(self):
        """git: links are never followed (GIT-08)"""
        self.write("target.txt", "target\n")
        os.symlink("target.txt", self.path("link"))
        self.commit()
        base = self.snap()
        os.unlink(self.path("link"))
        self.write("link", "now a regular file\n")
        self.g.restore(base, ["link"], expected_tree=base, index_file=self.index)
        self.assertTrue(os.path.islink(self.path("link")))
        with open(self.path("target.txt")) as fh:
            self.assertEqual(fh.read(), "target\n")

        # and the other way round: a file the attempt replaced with a link
        self.write("plain.txt", "plain\n")
        self.commit()
        base = self.snap()
        os.unlink(self.path("plain.txt"))
        os.symlink("target.txt", self.path("plain.txt"))
        self.g.restore(base, ["plain.txt"], expected_tree=base, index_file=self.index)
        self.assertFalse(os.path.islink(self.path("plain.txt")))
        with open(self.path("target.txt")) as fh:
            self.assertEqual(fh.read(), "target\n")

    def test_modes_are_restored(self):
        """git: modes are restored (GIT-09)"""
        self.write("tool.sh", "#!/bin/sh\n")
        os.chmod(self.path("tool.sh"), 0o755)
        self.commit()
        base = self.snap()
        os.chmod(self.path("tool.sh"), 0o644)
        cand = self.snap()
        self.assertEqual(self.g.changed_paths(base, cand), [("M", "tool.sh", "100755", "100644")])
        self.g.restore(base, ["tool.sh"], expected_tree=base, index_file=self.index)
        self.assertTrue(os.stat(self.path("tool.sh")).st_mode & stat.S_IXUSR)

    def test_parents_are_checked(self):
        """git: parents are checked (GIT-10)"""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        self.write("sub/deep/b.txt", "inside\n")
        self.commit()
        base = self.snap()
        os.rename(self.path("sub"), self.path("gone"))
        os.symlink(outside.name, self.path("sub"))
        self.g.restore(base, ["sub/deep/b.txt", "gone/deep/b.txt"])
        self.assertFalse(os.path.islink(self.path("sub")))
        with open(self.path("sub/deep/b.txt")) as fh:
            self.assertEqual(fh.read(), "inside\n")
        self.assertEqual(os.listdir(outside.name), [])
        self.assertEqual(self.snap(), base)

    def test_paths_outside_the_repository_are_refused(self):
        base = self.snap()
        for bad in ("../x", "/etc/passwd", ".git/config", "a/../../x"):
            with self.assertRaises(gitops.RestoreError):
                self.g.restore(base, [bad])

    def test_emptied_directories_are_removed(self):
        """git: emptied directories are removed (GIT-16)"""
        self.write("keep/kept.txt", "k\n")
        self.commit()
        base = self.snap()
        self.write("a/b/c/new.txt", "n\n")
        self.write("keep/extra/new.txt", "n\n")
        cand = self.snap()
        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        self.g.restore(base, paths, expected_tree=base, index_file=self.index)
        self.assertFalse(os.path.exists(self.path("a")))
        self.assertFalse(os.path.exists(self.path("keep/extra")))
        self.assertTrue(os.path.exists(self.path("keep/kept.txt")))

    def test_a_restore_that_does_not_reach_the_target_is_an_environment_failure(self):
        base = self.snap()
        self.write("stray.txt", "not in the path list\n")
        with self.assertRaises(gitops.RestoreError) as ctx:
            self.g.restore(base, [], expected_tree=base, index_file=self.index)
        self.assertEqual(ctx.exception.paths, ["stray.txt"])
        self.assertTrue(os.path.exists(self.path("stray.txt")))     # the tree is left alone

    def test_unsupported_entries_are_removed_early(self):
        """git: unsupported entries are removed early (GIT-11, primitive level: finding and
        removing them; failing the attempt is the engine's)."""
        base = self.snap()
        os.makedirs(self.path("vendor/nested"))
        git(self.path("vendor/nested"), "init", "-q")               # no commit: `git add` would fail
        os.makedirs(self.path("other"))
        git(self.path("other"), "init", "-q")
        git(self.path("other"), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "--allow-empty", "-m", "x")
        self.assertEqual(self.g.embedded_repositories(), ["other", "vendor/nested"])
        for rel in self.g.embedded_repositories():
            self.g.remove_embedded(rel)
        self.assertFalse(os.path.exists(self.path("vendor")))
        self.assertEqual(self.snap(), base)

    def test_an_ignored_embedded_repository_is_left_alone(self):
        """git: a fetched dependency in an ignored build directory is not an unsupported entry"""
        with open(self.path(".gitignore"), "w") as fh:
            fh.write(".build/\n")
        base = self.snap()
        os.makedirs(self.path(".build/debug/_deps/dep-src"))
        git(self.path(".build/debug/_deps/dep-src"), "init", "-q")
        os.makedirs(self.path("src/nested"))
        git(self.path("src/nested"), "init", "-q")
        self.assertEqual(self.g.embedded_repositories(), ["src/nested"])
        self.g.remove_embedded("src/nested")
        self.assertEqual(self.snap(), base)                          # the ignored one changes nothing
        self.assertTrue(os.path.isdir(self.path(".build/debug/_deps/dep-src/.git")))

    def test_gitlinks_in_a_tree_are_reported(self):
        os.makedirs(self.path("nested"))
        git(self.path("nested"), "init", "-q")
        git(self.path("nested"), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
            "--allow-empty", "-m", "x")
        tree = self.snap()
        self.assertEqual(self.g.gitlinks(tree), ["nested"])
        with self.assertRaises(gitops.RestoreError):                # never restored *to*
            self.g.restore(tree, ["nested"])


class RecoveryArtifacts(GitCase):
    def test_recovery_artifacts_are_complete(self):
        """fail: recovery artifacts are complete and pinned (FAIL-07, primitive level)"""
        self.write("src/a.py", "a = 1\n")
        self.commit()
        base = self.snap()
        self.write("src/a.py", "a = 2\n" + "# filler\n" * 5000)
        with open(self.path("img.bin"), "wb") as fh:
            fh.write(os.urandom(4096))
        cand = self.snap()
        patch = self.g.full_patch(base, cand)
        capped = gitops.cap_diff(self.g.review_diff(base, cand), 2000, "tasks/x/attempt-1/full.diff")
        self.assertLess(len(capped), len(patch))
        self.assertIn("diff truncated", capped)
        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        self.g.restore(base, paths, expected_tree=base, index_file=self.index)
        subprocess.run(["git", "apply", "--binary", "-"], cwd=self.root, input=patch, check=True)
        self.assertEqual(self.snap(), cand)

    def test_cap_diff_cuts_at_a_file_boundary(self):
        base = self.snap()
        self.write("a.txt", "a\n" * 50)
        self.write("b.txt", "b\n" * 50)
        self.write("c.txt", "c\n" * 50)
        text = self.g.review_diff(base, self.snap())
        self.assertEqual(gitops.cap_diff(text, 10 ** 6), text)
        one = len(text.split("diff --git ")[1]) + len("diff --git ")
        capped = gitops.cap_diff(text, one + 10, "full.diff")
        self.assertIn("+++ b/a.txt", capped)
        self.assertNotIn("+++ b/b.txt", capped)
        self.assertIn("[diff truncated: 1 of 3 files shown. Omitted: b.txt, c.txt. "
                      "The full diff is in full.diff.]", capped)
        self.assertEqual(capped, gitops.cap_diff(text, one + 10, "full.diff"))


class Branches(GitCase):
    def test_the_run_branch_is_checked_out(self):
        """git: the run branch is checked out (GIT-14, primitive level; run.json is in test_cli)"""
        before = self.snap()
        original = self.g.create_and_checkout_run_branch("run/demo-1a2b3c4d")
        self.assertEqual(original, "main")
        self.assertEqual(self.g.current_branch(), "run/demo-1a2b3c4d")
        self.assertEqual(self.snap(), before)
        self.assertTrue(self.g.is_clean())

    def test_detached_head_is_detected(self):
        git(self.root, "checkout", "-q", "--detach")
        self.assertIsNone(self.g.current_branch())

    def test_no_dirty_starts(self):
        """run: no dirty starts (RUN-02, primitive level: staged and unstaged changes are seen)"""
        self.assertTrue(self.g.is_clean())
        self.write("README.md", "staged\n")
        git(self.root, "add", "README.md")
        self.assertFalse(self.g.is_clean())
        self.write("README.md", "staged, then edited again\n")
        self.assertEqual(len(self.g.dirty_paths()), 1)
        self.commit()
        self.write("untracked.txt", "x\n")
        self.assertFalse(self.g.is_clean())


class Commits(GitCase):
    def accept(self, op="op-0001", **kw):
        base = self.snap()
        self.write("src/a.txt", "candidate\n")
        cand = self.snap()
        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        return cand, self.g.commit_candidate(cand, paths, "Implement the book", "RUN-UUID",
                                             "implement", op, self.g.head(), **kw)

    def test_one_commit_per_accepted_producer(self):
        """git: one commit per accepted producer (GIT-02, primitive level: whatever the attempts
        did, acceptance is one commit of the candidate, holding only the task's files)."""
        self.g.create_and_checkout_run_branch("run/demo-1")
        before = int(gitout(self.root, "rev-list", "--count", "HEAD"))
        cand, commit = self.accept()
        self.assertEqual(int(gitout(self.root, "rev-list", "--count", "HEAD")), before + 1)
        self.assertEqual(self.g.tree_of(commit), cand)
        self.assertEqual(self.g.commit_files(commit), ["src/a.txt"])
        self.assertEqual(gitout(self.root, "rev-parse", "main"), gitout(self.root, "rev-parse", "HEAD~1"))

    def test_commits_carry_the_operation_id(self):
        """git: commits carry the operation id (GIT-12)"""
        _cand, commit = self.accept(op="op-0042", extra_trailer="Reviewed-by: nobody")
        body = gitout(self.root, "log", "-1", "--format=%B", commit)
        self.assertIn("Run: RUN-UUID", body)
        self.assertIn("Task: implement", body)
        self.assertIn("Operation: op-0042", body)
        self.assertIn("Reviewed-by: nobody", body)
        self.assertTrue(self.g.find_operation(commit, "op-0042"))
        self.assertFalse(self.g.find_operation(commit, "op-0041"))
        self.assertEqual(gitout(self.root, "log", "-1", "--format=%s", commit), "Implement the book")

    def test_the_index_follows_the_commit(self):
        """git: the index follows the commit (GIT-13)"""
        _cand, commit = self.accept()
        self.assertEqual(gitout(self.root, "status", "--porcelain"), "")
        git(self.root, "revert", "--no-edit", commit)
        self.assertFalse(os.path.exists(self.path("src/a.txt")))

    def test_without_the_index_sync_a_revert_fails(self):
        """The reason for the last step of the recipe, kept as a test of the claim."""
        def stop(point):
            if point == "commit:after-update-ref":
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.accept(crash=stop)
        self.assertNotEqual(gitout(self.root, "status", "--porcelain"), "")
        self.g.sync_index()
        self.assertEqual(gitout(self.root, "status", "--porcelain"), "")

    def test_current_branch_option(self):
        """git: current branch option (GIT-05, primitive level: with no run branch the commit lands
        on the checked-out branch; refusing a detached HEAD is in test_cli)."""
        _cand, commit = self.accept()
        self.assertEqual(gitout(self.root, "rev-parse", "main"), commit)

    def test_a_tree_that_is_not_the_candidate_is_refused(self):
        base = self.snap()
        self.write("src/a.txt", "task\n")
        self.write("NOTES.md", "outside the task\n")
        cand = self.snap()
        tip = self.g.head()
        with self.assertRaises(gitops.CommitRefused) as ctx:
            self.g.commit_candidate(cand, ["src/a.txt"], "s", "r", "t", "op", tip)
        self.assertIn("NOTES.md", str(ctx.exception))
        self.assertEqual(self.g.head(), tip)
        self.assertNotEqual(base, cand)

    def test_a_moved_tip_is_refused(self):
        base = self.snap()
        self.write("a.txt", "x\n")
        cand = self.snap()
        with self.assertRaises(gitops.CommitRefused):
            self.g.commit_candidate(cand, ["a.txt"], "s", "r", "t", "op", "0" * 40)
        self.assertNotEqual(base, cand)

    def test_a_deletion_is_committed(self):
        self.write("old.txt", "old\n")
        self.commit()
        base = self.snap()
        os.unlink(self.path("old.txt"))
        cand = self.snap()
        paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
        commit = self.g.commit_candidate(cand, paths, "s", "r", "t", "op", self.g.head())
        self.assertEqual(self.g.tree_of(commit), cand)
        self.assertEqual(gitout(self.root, "status", "--porcelain"), "")


class TreeWith(GitCase):
    def test_paths_are_taken_from_the_source_and_the_rest_from_the_base(self):
        """git: `tree_with` takes each path from the source tree, an absent one is removed, and
        everything else stays as the base has it (the piece shared by the commit recipe and the
        recovery of set-aside work)."""
        self.write("old.txt", "old\n")
        self.write("keep.txt", "keep\n")
        self.commit()
        base = self.g.tree_of("HEAD")
        self.write("src/a.txt", "candidate\n")
        self.write("src/new.txt", "new\n")
        self.write("keep.txt", "changed elsewhere\n")
        os.unlink(self.path("old.txt"))
        os.chmod(self.path("src/new.txt"), 0o755)
        source = self.snap()
        tree = self.g.tree_with(base, source, ["src/a.txt", "src/new.txt", "old.txt"])
        entries = self.g.ls_tree(tree)
        self.assertEqual(sorted(set(entries) - set(self.g.ls_tree(base))), ["src/a.txt", "src/new.txt"])
        self.assertNotIn("old.txt", entries)
        self.assertEqual(entries["keep.txt"], self.g.ls_tree(base)["keep.txt"])
        self.assertEqual(entries["src/a.txt"], self.g.ls_tree(source)["src/a.txt"])
        self.assertEqual(entries["src/new.txt"], self.g.ls_tree(source)["src/new.txt"])
        self.assertEqual(entries["src/new.txt"][0], "100755")

    def test_no_paths_is_the_base_and_the_repository_is_untouched(self):
        self.write("a.txt", "one\n")
        self.commit()
        base = self.g.tree_of("HEAD")
        self.write("a.txt", "two\n")
        source = self.snap()
        before = (gitout(self.root, "status", "--porcelain"), gitout(self.root, "ls-files", "-s"))
        self.assertEqual(self.g.tree_with(base, source, []), base)
        self.assertEqual(self.g.tree_with(base, source, ["a.txt"]), source)
        self.assertEqual((gitout(self.root, "status", "--porcelain"),
                          gitout(self.root, "ls-files", "-s")), before)
        with open(self.path("a.txt")) as fh:
            self.assertEqual(fh.read(), "two\n")


class Reverts(GitCase):
    def three_commits(self):
        commits = []
        for n, name in enumerate(("a", "b", "c"), 1):
            base = self.snap()
            self.write(f"{name}.txt", f"{name}\n")
            cand = self.snap()
            paths = [p for _s, p, _o, _n in self.g.changed_paths(base, cand)]
            commits.append(self.g.commit_candidate(cand, paths, f"task {name}", "RUN", name,
                                                   f"op-{n}", self.g.head()))
        return commits

    def test_reverts_add_commits_and_remove_files(self):
        start = self.g.tree_of("HEAD")
        commits = self.three_commits()
        since = self.g.head()
        made = self.g.revert_commits(list(reversed(commits)), "op-9", "RUN", since)
        self.assertEqual(len(made), 3)
        self.assertEqual(self.g.tree_of("HEAD"), start)
        self.assertEqual(int(gitout(self.root, "rev-list", "--count", f"{since}..HEAD")), 3)
        self.assertTrue(self.g.is_clean())
        self.assertEqual(self.g.trailers(made[0])["Reverts"], commits[2])

    def test_reopen_is_resumable(self):
        """rec: reopen is resumable (REC-11, primitive level: killed during the second of three
        reverts; the half-done one is aborted, the first is recognised by its operation id)."""
        start = self.g.tree_of("HEAD")
        commits = list(reversed(self.three_commits()))
        since = self.g.head()

        def stop(point):
            if point == "revert:2:staged":
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.g.revert_commits(commits, "op-9", "RUN", since, crash=stop)
        self.assertTrue(self.g.revert_in_progress())
        first = self.g.head()

        made = self.g.revert_commits(commits, "op-9", "RUN", since)
        self.assertEqual(made[0], first)                       # not reverted a second time
        self.assertEqual(int(gitout(self.root, "rev-list", "--count", f"{since}..HEAD")), 3)
        self.assertEqual(self.g.tree_of("HEAD"), start)
        self.assertTrue(self.g.is_clean())

    def test_a_conflicting_revert_stops_and_changes_nothing(self):
        self.write("f.txt", "one\n")
        self.commit()
        first = self.g.head()
        self.write("f.txt", "two\n")
        self.commit()
        self.write("f.txt", "three\n")
        self.commit()
        tip = self.g.head()
        second = gitout(self.root, "rev-parse", "HEAD~1")
        with self.assertRaises(gitops.RevertConflict) as ctx:
            self.g.revert_commits([second], "op-9", "RUN", tip)
        self.assertEqual(ctx.exception.commit, second)
        self.assertEqual(self.g.head(), tip)
        self.assertTrue(self.g.is_clean())
        self.assertNotEqual(first, tip)


class NothingDestructive(GitCase):
    FORBIDDEN = ("reset", "clean", "stash", "push", "merge", "rebase", "fetch", "pull", "gc")

    def test_no_destructive_or_remote_operations(self):
        """git: no destructive or remote operations (GIT-04, primitive level: every git command the
        module runs during a full exercise is recorded, and the source is searched as well)."""
        gitops.TRACE = []
        self.addCleanup(setattr, gitops, "TRACE", None)
        self.g.create_and_checkout_run_branch("run/x")
        base = self.snap()
        self.write("a.txt", "a\n")
        cand = self.snap()
        self.g.pin("r", "cand", cand)
        self.g.full_patch(base, cand)
        commit = self.g.commit_candidate(cand, ["a.txt"], "s", "r", "t", "op-1", self.g.head())
        self.write("junk.txt", "j\n")
        self.g.restore(cand, ["junk.txt"], expected_tree=cand, index_file=self.index)
        self.g.revert_commits([commit], "op-2", "r", commit)
        self.g.unpin_run("r")
        used = {argv[0] for argv in gitops.TRACE}
        self.assertTrue(used)
        self.assertEqual(used & set(self.FORBIDDEN), set())

        with open(gitops.__file__, encoding="utf-8") as fh:
            source = fh.read()
        for word in self.FORBIDDEN:
            self.assertIsNone(re.search(rf"[\"']{word}[\"']", source), word)
        self.assertNotIn("--hard", source)


if __name__ == "__main__":
    unittest.main()
