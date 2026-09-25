"""The run directory: create it, keep its state durably, record intents and outcomes, reconcile
after a crash, and regenerate the files that are written for readers (04, 05 Crash recovery).

`state.json` is the only thing read back. STATUS.md and index.json are derived: deleting them
loses nothing. Write-once is enforced by hashes (`integrity.json`), never by file modes.
"""

import datetime
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import threading
import uuid

from . import __version__, gitops

RUNS_DIR = ".runs"
HEARTBEAT_S = 30                                   # how often a working runner refreshes STATUS.md
RUNS_DIR_ENV = "TASK_RUNNER_RUNS_DIR"         # set by `runner --runs-dir DIR`, or exported by the owner
LOCK_FILE = "lock"
STATE_VERSION = 1
FINISHED_STATUSES = ("done",)
TASK_TERMINAL = ("accepted", "objected", "blocked", "failed", "skipped")
# Decision-bearing files of a finished directory (04, rule 4). state.json and findings.json are
# covered from the moment they exist.
DECISION_FILES = ("result.json", "verdict.json", "verification.json", "outputs.json",
                  "decision.json")


class RecordError(Exception):
    pass


class LockHeld(RecordError):
    def __init__(self, holder, path):
        self.holder, self.path = holder, path
        who = (f"run {holder.get('run_id')} (pid {(holder.get('process') or {}).get('pid')})"
               if holder else "an unreadable lock")
        super().__init__(f"another runner holds this repository: {who}. Lock file: {path}")


class ReconcileError(RecordError):
    """The repository or the record is not what the state expects. Stop; never guess."""


class OrphanAlive(ReconcileError):
    def __init__(self, identity, task):
        self.identity, self.task = identity, task
        super().__init__(f"the child process of task '{task}' from the previous runner is still running "
                         f"(pid {identity.get('pid')}). Refusing to start a second one beside it; "
                         "`resume --stop-orphans` stops it first")


def _no_crash(point):
    return None


# -- durable files ------------------------------------------------------------------------------

def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_durable(path, data, crash=_no_crash):
    """Temporary file, flush, sync, rename, sync the directory. A crash leaves the old file intact;
    a leftover temporary file is ignored and overwritten next time."""
    path = os.fspath(path)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    crash("state:before-rename")
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path))


def dump_json(obj):
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


# -- process identity (B6) ----------------------------------------------------------------------

def boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _proc_stat(pid):
    """(state, start ticks) from /proc/<pid>/stat. The command name may hold spaces and
    parentheses, so the fields are read after the last ')'. Field 3 is the state, 22 the start."""
    with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
        rest = fh.read().rpartition(")")[2].split()
    return rest[0], int(rest[19])


def process_identity(pid):
    """What identifies a process beyond its pid, which is reused: start ticks and the boot id on
    Linux; elsewhere the weaker `ps` start time. None if there is no such live process."""
    if os.path.isdir("/proc/self"):
        try:
            state, ticks = _proc_stat(pid)
        except (OSError, ValueError, IndexError):
            return None
        if state in ("Z", "X"):
            return None
        ident = {"pid": pid, "start_ticks": ticks, "boot_id": boot_id()}
    else:
        res = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True)
        if res.returncode != 0 or not res.stdout.strip():
            return None
        ident = {"pid": pid, "lstart": res.stdout.strip()}
    try:
        ident["pgid"] = os.getpgid(pid)
    except OSError:
        return None
    return ident


def is_alive(identity):
    """Is the very process that `identity` describes still running? A reused pid is not."""
    if not identity or "pid" not in identity:
        return False
    now = process_identity(identity["pid"])
    if now is None:
        return False
    keys = ("start_ticks", "boot_id") if "start_ticks" in identity else ("lstart",)
    return all(now.get(k) == identity.get(k) for k in keys)


def stop_process_group(identity, grace_s=5.0):
    """SIGINT, then SIGTERM, then SIGKILL to the whole group, waiting `grace_s` after each."""
    pgid = identity.get("pgid") or identity["pid"]
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if not is_alive(identity):
            return True
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + grace_s
        while time.monotonic() < deadline:
            if not is_alive(identity):
                return True
            time.sleep(0.05)
    return not is_alive(identity)


# -- the repository lock ------------------------------------------------------------------------

class Lock:
    """One run at a time per repository. Created exclusively; holds the run id and the identity of
    the process that took it. A lock whose process is gone is stale and is replaced."""

    def __init__(self, runs_dir):
        self.path = os.path.join(runs_dir, LOCK_FILE)
        self.held = False

    def holder(self):
        try:
            return read_json(self.path)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {}

    def acquire(self, run_id):
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                holder = self.holder()
                if holder is None:
                    continue
                # An unreadable lock is treated as held: another runner may be writing it now.
                if holder == {} or is_alive(holder.get("process")):
                    raise LockHeld(holder, self.path)
                os.unlink(self.path)                    # stale: its process is gone
                continue
            with os.fdopen(fd, "wb") as fh:
                fh.write(dump_json({"run_id": run_id, "process": process_identity(os.getpid())}))
                fh.flush()
                os.fsync(fh.fileno())
            self.held = True
            return self
        raise LockHeld(self.holder() or {}, self.path)

    def release(self):
        if self.held:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            self.held = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


# -- .runs/ -------------------------------------------------------------------------------------

README = """\
# .runs — the record of task runner runs

This directory is written by the task runner. It is the record of how work in this repository came
to be: every run, every task, every attempt, every prompt, every answer, every review finding. The
deliverables themselves are **not** here; they are in the repository, on the run's git branch.

By default this directory is `.runs/` at the top of the repository. `runner --runs-dir DIR ...`,
or the environment variable `TASK_RUNNER_RUNS_DIR`, puts it elsewhere; every later command on
these runs then needs the same setting.

Nothing in here is tracked by git (`.gitignore` holds `*`). Committing a run's record is the
owner's choice. A finished run can be deleted with `rm -rf`; `runner prune` then removes the git
refs it pinned under `refs/task-runner/`.

## How to read a run, cold

Open `<workflow>/<run>/STATUS.md`. It says, in words, what the run did, what it needs and what to
type next. Every directory also has an `index.json` that says what each file in it is. Start there
rather than guessing from file names.

    .runs/
      README.md                     this file
      lock                          present while a runner is working in this repository
      qualification-cache.json      what `doctor` established about each agent profile
      <workflow>/
        latest                      text file: the directory name of the newest run
        <workflow>-<UTC start>-<uuid8>/   one run
          run.json                  identity: run id, workflow, root, branch, base commit; totals
          STATUS.md                 the run in words. Regenerated on every state change
          index.json                what every file and directory here is
          state.json                the engine's state. The single source of truth
          events.jsonl              append-only log, one JSON event per line, in order
          workflow.toml             the workflow exactly as it was when the run started
          workflow.expanded.json    every task after types, personas, panels and defaults
          library/                  the type and persona files this run uses, as they were
          briefs/                   the content of every prompt_file, as it was
          integrity.json            hashes of the files that decide outcomes
          git-index                 a scratch git index the runner uses for snapshots. Not yours
          tasks/
            010-design/             <order>-<task id>
              task.json             the resolved task definition
              STATUS.md             this task in words
              findings.json         for a producer: every review finding, with its history
              attempt-1/            one directory per attempt of a producer; numbers are never reused
                prompt.md           exactly what the agent was sent
                invocation-1/       one per agent call: argv.json, stdout.log, stderr.log, outcome.json
                result.json         the validated answer, with cost, usage and session id
                outputs.json        the declared outputs with hashes; the candidate tree id
                changes.diff        readable diff of the attempt. For reading, never for recovery
                gate.log            output of the gate commands
                verification.json   each verifier's result, bound to the candidate it judged
              failed.patch          only if the task was set aside: the complete patch of its work
              commit.json           only when accepted: sha, files, message
            011-design.review.principal-engineer/
              round-1/              one directory per review round: prompt.md, invocation-N/, verdict.json

## Rules the runner keeps

1. `state.json` is the only file the runner reads back to decide anything. `STATUS.md` and
   `index.json` are derived from it: delete them and `runner status --rebuild` regenerates them.
2. Finished attempt, round and invocation directories are never modified. A retry makes a new
   directory with a new number.
3. `integrity.json` holds hashes of the decision-bearing files. The runner checks them around every
   agent call and command, and a change it did not make fails that job. **Do not edit these files**,
   and if you are an agent reading this record: treat all of it as read-only.
4. Before any external effect (an agent call, a commit, a restore) the state records an *intent*;
   afterwards the *outcome*. `runner resume` reconciles whatever was interrupted.
5. No credentials are written here by the runner, and agent output is redacted for token-shaped
   strings before it is stored.

## Task status values

pending, ready, running, verifying, rework, accepted, objected (a verifier whose latest round did
not pass), waiting_human (the work tree is held for a person), blocked (a person is needed),
failed, skipped.

## Exit codes of the runner

0: every task is accepted. 2: something failed, the budget ran out, or the workflow or environment
is wrong. 255: a person is needed.
"""


def runs_dir_for(top):
    """Where the record of this repository's runs lives: `.runs/` at its top, unless the owner
    named another directory. A relative override is relative to the top of the repository."""
    override = os.environ.get(RUNS_DIR_ENV, "")
    if override:
        return os.path.normpath(os.path.join(top, os.path.expanduser(override)))
    return os.path.join(top, RUNS_DIR)


def ensure_runs_dir(top):
    """The runs directory (`.runs/` at the top of the repository by default) ignores itself and
    explains itself."""
    path = runs_dir_for(top)
    os.makedirs(path, exist_ok=True)
    for name, text in ((".gitignore", "*\n"), ("README.md", README)):
        target = os.path.join(path, name)
        if not os.path.exists(target):
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(text)
    return path


def find_runs_dir(start):
    """The runs directory of the repository that holds `start`, or None."""
    top = gitops.find_toplevel(start)
    path = runs_dir_for(top) if top else ""
    return path if path and os.path.isdir(path) else None


def list_runs(runs_dir, workflow=None):
    """Every run directory, oldest first: a list of (workflow, name, path)."""
    found = []
    if not os.path.isdir(runs_dir):
        return found
    for wf in sorted(os.listdir(runs_dir)):
        wf_dir = os.path.join(runs_dir, wf)
        if not os.path.isdir(wf_dir) or (workflow and wf != workflow):
            continue
        for name in sorted(os.listdir(wf_dir)):
            path = os.path.join(wf_dir, name)
            if os.path.isfile(os.path.join(path, "run.json")):
                found.append((wf, name, path))
    return sorted(found, key=_run_order)


def _run_order(found):
    """Oldest first. The start time is in run.json; the directory name no longer begins with it."""
    wf, name, path = found
    try:
        started = read_json(os.path.join(path, "run.json")).get("started", "")
    except (OSError, ValueError):
        started = ""
    return (started, name, wf)


def resolve_run(runs_dir, ref="latest", unfinished_only=False):
    """RUN is a directory name, a UUID prefix, or `latest`."""
    runs = list_runs(runs_dir)
    if unfinished_only:
        runs = [r for r in runs if Run.load(r[2]).state["status"] not in FINISHED_STATUSES]
    if not runs:
        raise RecordError(f"no runs under {runs_dir}")
    if ref in (None, "", "latest"):
        return runs[-1][2]
    matches = [r for r in runs if r[1] == ref]
    if not matches:
        matches = [r for r in runs if read_json(os.path.join(r[2], "run.json"))["run_id"]
                   .startswith(ref.lower())]
    if not matches:
        raise RecordError(f"no run matches '{ref}'")
    if len(matches) > 1:
        raise RecordError(f"'{ref}' matches several runs: " + ", ".join(m[1] for m in matches))
    return matches[0][2]


# -- a run --------------------------------------------------------------------------------------

def _utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_stamp(now):
    return now.strftime("%Y%m%dT%H%M%SZ")


def task_dir_names(tasks):
    """<order>-<id>. Written tasks step by ten, leaving gaps for replanned tasks; the generated
    members of a panel follow their producer one by one (010-design, 011-design.review.…)."""
    names, n = {}, 0
    for t in tasks:
        n = n + 1 if t.get("generated") else (n // 10 + 1) * 10
        names[t["id"]] = f"{n:03d}-{t['id']}"
    return names


class Run:
    def __init__(self, path, state):
        self.path = path
        self.state = state
        self.crash = _no_crash
        self._status_lock = threading.Lock()         # regenerate() and the heartbeat both write STATUS.md

    # -- creation and loading ----------------------------------------------------------------

    @classmethod
    def create(cls, wf, git, branch, original_branch, now=None, run_id=None):
        """Make the run directory with a frozen copy of everything that defines the work."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        run_id = run_id or str(uuid.uuid4())
        runs = ensure_runs_dir(git.top)
        wf_dir = os.path.join(runs, wf.name)
        os.makedirs(wf_dir, exist_ok=True)
        name = f"{wf.name}-{_utc_stamp(now)}-{run_id[:8]}"
        path = os.path.join(wf_dir, name)
        os.mkdir(path)                                   # exclusive: never reuse a run directory

        with open(wf.workflow_file, "rb") as fh:
            frozen = fh.read()
        with open(os.path.join(path, "workflow.toml"), "wb") as fh:
            fh.write(frozen)
        with open(os.path.join(path, "workflow.expanded.json"), "wb") as fh:
            fh.write(dump_json(wf.expanded()))
        cls._freeze_library(wf, path)
        cls._freeze_briefs(wf, path)

        names = task_dir_names(wf.tasks)
        for t in wf.tasks:
            tdir = os.path.join(path, "tasks", names[t["id"]])
            os.makedirs(tdir)
            with open(os.path.join(tdir, "task.json"), "wb") as fh:
                fh.write(dump_json(t))

        run_json = {
            "run_id": run_id, "name": name, "workflow": wf.name,
            "workflow_sha256": hashlib.sha256(frozen).hexdigest(),
            "workflow_file": wf.workflow_file, "root": wf.root, "git_toplevel": git.top,
            "library": list(wf.library_dirs),
            "branch": branch, "original_branch": original_branch,
            "branch_mode": wf.defaults["branch"], "base_commit": git.head(),
            "started": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "runner_version": __version__,
            "agents": {},                                # versions are recorded by doctor (stage 4)
        }
        with open(os.path.join(path, "run.json"), "wb") as fh:
            fh.write(dump_json(run_json))

        state = {
            "version": STATE_VERSION, "run_id": run_id, "status": "running",
            "op_seq": 0, "intents": [], "active_producer": None, "expect": None,
            "spend": {"known_usd": 0.0, "reserved_usd": 0.0,
                      "unpriced": {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                                   "unknown_calls": 0}},
            "run_budget_usd": wf.defaults["run_budget_usd"],
            "run_budget_tokens": wf.defaults["run_budget_tokens"], "seconds": 0,
            "tasks": {t["id"]: {"status": "pending", "dir": names[t["id"]], "kind": t["kind"],
                                "type": t["type"], "attempts": 0, "cost_usd": 0.0,
                                "commit": None, "reason": ""} for t in wf.tasks},
            "order": [t["id"] for t in wf.tasks],
        }
        run = cls(path, state)
        write_durable(os.path.join(path, "integrity.json"), dump_json({"files": {}}))
        run.save()
        run.event("run-created", workflow=wf.name, branch=branch, base_commit=run_json["base_commit"])
        with open(os.path.join(wf_dir, "latest"), "w", encoding="utf-8") as fh:
            fh.write(name + "\n")
        run.regenerate()
        return run

    @staticmethod
    def _freeze_library(wf, path):
        used = {}
        for t in wf.tasks:
            tdef = wf.types.get(t["type"])
            if tdef and tdef.get("_where"):
                used[("types", t["type"])] = tdef["_where"]
            pdef = wf.personas.get(t.get("perspective") or "")
            if pdef and pdef.get("_where"):
                used[("personas", t["perspective"])] = pdef["_where"]
        for (sub, stem), source in sorted(used.items()):
            os.makedirs(os.path.join(path, "library", sub), exist_ok=True)
            shutil.copyfile(source, os.path.join(path, "library", sub, stem + ".toml"))

    @staticmethod
    def _freeze_briefs(wf, path):
        for t in wf.tasks:
            if t.get("prompt_file"):
                os.makedirs(os.path.join(path, "briefs"), exist_ok=True)
                shutil.copyfile(t["prompt_file"], os.path.join(path, "briefs", t["id"] + ".md"))

    @classmethod
    def load(cls, path):
        """Only `state.json` is read back. A leftover `state.json.tmp` is ignored."""
        return cls(path, read_json(os.path.join(path, "state.json")))

    @property
    def info(self):
        return read_json(os.path.join(self.path, "run.json"))

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def index_file(self):
        return os.path.join(self.path, "git-index")

    def task_dir(self, task_id):
        return os.path.join(self.path, "tasks", self.state["tasks"][task_id]["dir"])

    # -- state, events, intents --------------------------------------------------------------

    def save(self):
        write_durable(os.path.join(self.path, "state.json"), dump_json(self.state), self.crash)

    def event(self, event, **data):
        line = json.dumps({"at": datetime.datetime.now(datetime.timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "event": event, **data},
                          sort_keys=True, ensure_ascii=False)
        with open(os.path.join(self.path, "events.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def begin(self, kind, **expect):
        """Record the intent of an external effect, durably, before the effect. Returns its id."""
        self.state["op_seq"] += 1
        op_id = f"op-{self.state['op_seq']:04d}-{uuid.uuid4().hex[:8]}"
        self.state["intents"].append({"op": op_id, "kind": kind, "at": _utc_now_iso(), **expect})
        self.save()
        self.event("intent", op=op_id, kind=kind)
        return op_id

    def amend(self, op_id, **more):
        """Add what is only known once the effect has started, such as an agent's process."""
        self.intent(op_id).update(more)
        self.save()

    def intent(self, op_id):
        for it in self.state["intents"]:
            if it["op"] == op_id:
                return it
        raise KeyError(op_id)

    def finish(self, op_id, **outcome):
        """Record the outcome and clear the intent."""
        it = self.intent(op_id)
        self.state["intents"].remove(it)
        self.save()
        self.event("outcome", op=op_id, kind=it["kind"], **outcome)

    def set_status(self, task_id, status, reason=""):
        self.state["tasks"][task_id].update(status=status, reason=reason)

    def record_acceptance(self, task_id, commit, files, message):
        """A producer's work is committed: write commit.json, mark it accepted."""
        tdir = self.task_dir(task_id)
        self.write_decision(os.path.join(tdir, "commit.json"),
                            {"sha": commit, "files": files, "message": message})
        self.state["tasks"][task_id].update(status="accepted", commit=commit, reason="")
        self.state["last_tip"] = commit
        if self.state.get("active_producer") == task_id:
            self.state["active_producer"] = None

    # -- numbered directories (A2, A6) -------------------------------------------------------

    @staticmethod
    def _next_numbered(parent, prefix):
        """`<prefix>-N`, where N was never used under `parent`. Created exclusively, so nothing
        stale is ever found in it; a lost race simply takes the next number."""
        os.makedirs(parent, exist_ok=True)
        used = [int(n[len(prefix) + 1:]) for n in os.listdir(parent)
                if n.startswith(prefix + "-") and n[len(prefix) + 1:].isdigit()]
        n = max(used, default=0) + 1
        while True:
            path = os.path.join(parent, f"{prefix}-{n}")
            try:
                os.mkdir(path)
                return n, path
            except FileExistsError:
                n += 1

    def new_attempt(self, task_id):
        n, path = self._next_numbered(self.task_dir(task_id), "attempt")
        self.state["tasks"][task_id]["attempts"] += 1
        return n, path

    def new_round(self, task_id):
        return self._next_numbered(self.task_dir(task_id), "round")

    def new_invocation(self, parent):
        return self._next_numbered(parent, "invocation")

    # -- integrity (A9, B8) ------------------------------------------------------------------

    def _manifest_path(self):
        return os.path.join(self.path, "integrity.json")

    def _manifest(self):
        return read_json(self._manifest_path())

    def _rel(self, path):
        return os.path.relpath(path, self.path).replace(os.sep, "/")

    def protect(self, *paths):
        """Put decision-bearing files under the manifest, with their current hashes."""
        manifest = self._manifest()
        for p in paths:
            manifest["files"][self._rel(p)] = sha256_file(p)
        write_durable(self._manifest_path(), dump_json(manifest))

    def write_decision(self, path, obj):
        """Write a decision-bearing file durably and bring the manifest up to date."""
        write_durable(path, dump_json(obj))
        self.protect(path)

    def publish_decision(self, path, obj, crash=_no_crash):
        """write_decision under an intent: the complete payload is recorded first, so a crash between
        the file and its manifest entry is repaired by writing both again from the intent."""
        op = self.begin("decision", path=self._rel(path), payload=obj)
        write_durable(path, dump_json(obj))
        crash("decision:file-written")
        self.protect(path)
        self.finish(op, path=self._rel(path))

    def close_directory(self, directory):
        """A finished attempt, round or invocation directory: its decision files are now fixed.
        Hashing again gives the same result, so this is safe to repeat after a crash."""
        found = []
        for dirpath, _dirs, files in os.walk(directory):
            found += [os.path.join(dirpath, f) for f in files if f in DECISION_FILES]
        if found:
            self.protect(*sorted(found))
        return [self._rel(p) for p in sorted(found)]

    def integrity_begin(self):
        """Call before a job. Returns a guard for `integrity_end`."""
        problems = self.integrity_check()
        if problems:
            raise RecordError("the run record was changed: " + "; ".join(problems))
        return {"state.json": sha256_file(os.path.join(self.path, "state.json")),
                "integrity.json": sha256_file(self._manifest_path())}

    def integrity_end(self, guard):
        """Call after a job, before the runner writes anything. Lists what the job changed."""
        problems = self.integrity_check()
        for name, digest in guard.items():
            path = os.path.join(self.path, name)
            if not os.path.exists(path):
                problems.append(f"{name} was removed")
            elif sha256_file(path) != digest:
                problems.append(f"{name} was changed")
        return problems

    # -- pause requests -----------------------------------------------------------------------

    PAUSE_FILE = "pause.requested"

    def pause_path(self):
        return os.path.join(self.path, self.PAUSE_FILE)

    def request_pause(self, by="owner"):
        """`runner pause` leaves this file; the engine reads it before starting any call."""
        write_durable(self.pause_path(), dump_json({"requested_at": _utc_now_iso(), "by": by}))

    def pause_requested(self):
        return os.path.exists(self.pause_path())

    def clear_pause(self):
        try:
            os.remove(self.pause_path())
        except FileNotFoundError:
            pass

    def integrity_check(self):
        problems = []
        for rel, digest in sorted(self._manifest()["files"].items()):
            path = os.path.join(self.path, rel)
            if not os.path.exists(path):
                problems.append(f"{rel} was removed")
            elif sha256_file(path) != digest:
                problems.append(f"{rel} was changed")
        return problems

    # -- derived files (D14) -----------------------------------------------------------------

    def regenerate(self):
        """STATUS.md for the run and each task, then index.json in every directory. Pure functions
        of the state and of what is on disk, so rebuilding gives the same bytes. One line is
        observed from git instead: where a finished run's branch went. A merge happens outside
        the runner, so `runner status` regenerates a finished run to keep that line true."""
        info = self.info
        # run.json: the identity never changes; the totals are copied from the state.
        info.update(status=self.state["status"], spend=self.state["spend"],
                    seconds=self.state["seconds"], run_budget_usd=self.state["run_budget_usd"],
                    run_budget_tokens=self.state.get("run_budget_tokens", 0))
        self._write(os.path.join(self.path, "run.json"), dump_json(info).decode("utf-8"))
        with self._status_lock:
            self._write(os.path.join(self.path, "STATUS.md"),
                        render_run_status(info, self.state, branch_disposition(info, self.state),
                                          run_path=self.path, alive=self.runner_alive()))
        for task_id in self.state["order"]:
            tdir = self.task_dir(task_id)
            ledger = self.state["tasks"][task_id].get("ledger")
            if ledger is not None:
                self.write_decision(os.path.join(tdir, "findings.json"), ledger)
            self._write(os.path.join(tdir, "STATUS.md"),
                        render_task_status(task_id, self.state["tasks"][task_id], tdir, self.name))
        for dirpath, dirnames, _files in os.walk(self.path):
            dirnames.sort()
            self._write(os.path.join(dirpath, "index.json"),
                        dump_json(render_index(self.path, dirpath)).decode("utf-8"))

    def runner_alive(self):
        """Is a runner working on this run right now: the runs directory's lock names this run and
        the process it names is alive. Read by the status page, which otherwise cannot tell an
        operation in flight from one a dead runner left behind (both are open intents)."""
        holder = Lock(os.path.dirname(os.path.dirname(self.path))).holder() or {}
        return holder.get("run_id") == self.info.get("run_id") and is_alive(holder.get("process"))

    def refresh_status(self, now=None):
        """The heartbeat: rewrite the run's STATUS.md alone, with the age of what is in flight.
        Nothing changes in the state while one long agent call runs, so without this the file
        looks dead for half an hour. Observational: it never touches the state, and a failure to
        render (the engine may be changing the state under us) just skips the beat."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        try:
            text = render_run_status(self.info, self.state, None, now=now, run_path=self.path,
                                     alive=self.runner_alive())
        except Exception:                                   # noqa: BLE001 - never hurt the run
            return False
        target = os.path.join(self.path, "STATUS.md")
        with self._status_lock:
            tmp = target + ".beat"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, target)
        return True

    @staticmethod
    def _write(path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


# -- reconciliation (A2, B6) --------------------------------------------------------------------

def reconcile(run, git, stop_orphans=False, crash=_no_crash, grace_s=5.0):
    """Settle every intent that has no outcome, before anything else happens. Returns what was
    done, in words. Raises ReconcileError when the repository is not what the state expects."""
    done = []
    expect = run.state.get("expect")
    if expect:                                           # the run was paused holding the tree
        tip = git.head()
        if tip != expect["tip"]:
            raise ReconcileError(f"while the run was paused the branch tip changed: expected "
                                 f"{expect['tip']}, found {tip}")
        tree = git.snapshot(run.index_file)
        if tree != expect["tree"]:
            changed = [p for _s, p, _o, _n in git.changed_paths(expect["tree"], tree)]
            raise ReconcileError("while the run was paused the work tree changed: "
                                 + ", ".join(changed))
    for it in list(run.state["intents"]):
        handler = _RECONCILERS.get(it["kind"])
        if handler is None:
            raise ReconcileError(f"intent {it['op']} has unknown kind '{it['kind']}'")
        done.append(handler(run, git, it, stop_orphans=stop_orphans, crash=crash, grace_s=grace_s))
    if done:
        run.regenerate()
    return done


def _reconcile_commit(run, git, it, crash, **_):
    op, task = it["op"], it["task"]
    tip = git.head()
    if git.find_operation(tip, op):
        if git.tree_of(tip) != it["candidate"]:
            raise ReconcileError(f"commit {tip} carries operation {op} but its tree is not the "
                                 f"candidate {it['candidate']}")
        git.sync_index()                                 # the crash may have come before this step
        commit, what = tip, "the commit had been made; recorded the acceptance"
    elif tip == it["parent"]:
        tree = git.snapshot(run.index_file)
        if tree != it["candidate"]:
            raise ReconcileError(f"the work tree is {tree}, not the candidate {it['candidate']} "
                                 f"that was about to be committed for '{task}'")
        commit = git.commit_candidate(it["candidate"], it["paths"], it["subject"],
                                      run.state["run_id"], task, op, it["parent"],
                                      it.get("extra_trailer", ""), crash=crash)
        what = "the commit had not been made; committed the verified candidate"
    else:
        raise ReconcileError(f"task '{task}' was about to be committed on {it['parent']}, but the "
                             f"branch tip is {tip}, which does not carry operation {op}. Someone "
                             "changed the branch")
    message = git.commit_message(it["subject"], run.state["run_id"], task, op,
                                 it.get("extra_trailer", ""))
    run.record_acceptance(task, commit, git.commit_files(commit), message)
    run.finish(op, commit=commit)
    return f"{op} commit of '{task}': {what} ({commit[:7]})"


def _reconcile_restore(run, git, it, crash, **_):
    git.restore(it["target"], it["paths"], expected_tree=it.get("expected", it["target"]),
                index_file=run.index_file, crash=crash)
    run.finish(it["op"], restored=len(it["paths"]))
    return f"{it['op']} restore: run again from the pinned target and verified"


def _reconcile_recover(run, git, it, crash, **_):
    """Put the set-aside work back again from the pinned candidate and open the transaction from
    the intent, whatever the state already shows: only the intent says the recovery is done."""
    task, head = it["task"], git.head()
    if head != it["head"]:
        raise ReconcileError(f"the set-aside work of '{task}' was being put back on commit "
                             f"{it['head']}, but the branch tip is now {head}. Nothing was restored")
    if run.state.get("expect"):
        # A run stopped by a failed restore expected the tree it left behind. `reconcile` has
        # checked it; the replay below changes the tree, so a crash in it must not leave that
        # expectation to refuse the next `resume`. The intent's `head` still guards the branch.
        run.state["expect"] = None
        run.save()
    git.restore(it["target"], it["paths"], expected_tree=it["expected"],
                index_file=run.index_file, crash=crash)
    from . import engine
    engine.open_transaction(run, git, task, it["base"],
                            {"record": {"attempt": it["attempt"]}, "paths": it["paths"]}, it["op"])
    return (f"{it['op']} recovery of '{task}': the set-aside work of attempt {it['attempt']} is "
            "back, verified, and the transaction is open")


def _reconcile_decision(run, git, it, **_):
    run.write_decision(os.path.join(run.path, it["path"]), it["payload"])
    run.finish(it["op"], path=it["path"])
    return f"{it['op']} decision {it['path']}: written again from the intent"


def _reconcile_pin(run, git, it, **_):
    git.pin(run.name, it["name"], it["object"])
    run.finish(it["op"], ref=it["name"])
    return f"{it['op']} pin {it['name']}: repeated"


def _reconcile_patch(run, git, it, **_):
    write_durable(os.path.join(run.path, it["path"]), git.full_patch(it["base"], it["candidate"]))
    run.finish(it["op"], path=it["path"])
    return f"{it['op']} patch {it['path']}: regenerated from the pinned trees"


def _reconcile_close(run, git, it, **_):
    run.close_directory(os.path.join(run.path, it["dir"]))
    run.finish(it["op"], dir=it["dir"])
    return f"{it['op']} close {it['dir']}: hashed again"


def _reconcile_revert(run, git, it, crash, **_):
    made = git.revert_commits(it["commits"], it["op"], run.state["run_id"], it["since"], crash=crash)
    run.finish(it["op"], reverts=made)
    return f"{it['op']} reopen: {len(made)} revert commits are on the branch"


def _reconcile_agent(run, git, it, stop_orphans, grace_s, **_):
    identity, task = it.get("process"), it["task"]
    if is_alive(identity):
        if not stop_orphans:
            raise OrphanAlive(identity, task)
        if not stop_process_group(identity, grace_s):
            raise ReconcileError(f"could not stop the orphaned agent of '{task}' "
                                 f"(pid {identity['pid']})")
    inv = os.path.join(run.path, it["invocation_dir"])
    outcome = os.path.join(inv, "outcome.json")
    # Completion is unknown, so it is never success: the engine had not recorded an outcome.
    os.makedirs(inv, exist_ok=True)
    from . import budgets, agents
    # What the call used is read from the provider's own record when there is one (G4).
    since = agents._epoch(it.get("at"))
    usage = agents.partial_usage(it.get("agent_kind", ""), inv, since) if since is not None else {}
    result = agents.AgentResult(agents.INTERRUPTED, usage=usage,
                                usage_source="provider-record" if usage else "unknown")
    write_durable(outcome, dump_json({"status": "interrupted",
                                      "reason": "the runner stopped while this call was running",
                                      "usage": usage, "usage_source": result.usage_source}))
    budgets.settle(run.state, task, it.get("reservation", 0), result)
    run.state["tasks"][task]["session_id"] = None        # the session is abandoned
    run.finish(it["op"], status="interrupted", usage=usage)
    return (f"{it['op']} agent call of '{task}': marked interrupted; its session is abandoned"
            + (f"; it had used {usage['tokens_in']} tokens in, {usage['tokens_out']} out" if usage
               else "; its usage is unknown"))


def _reconcile_command(run, git, it, stop_orphans, grace_s, **_):
    identity, task = it.get("process"), it["task"]
    if is_alive(identity):
        if not stop_orphans:
            raise OrphanAlive(identity, task)
        if not stop_process_group(identity, grace_s):
            raise ReconcileError(f"could not stop the orphaned command of '{task}'")
    run.finish(it["op"], result="interrupted")
    return f"{it['op']} command of '{task}': marked interrupted; verification must run again"


def _reconcile_branch(run, git, it, **_):
    name = it["name"]
    if git.current_branch() != name:
        if git.branch_exists(name):
            raise ReconcileError(f"the run branch '{name}' exists but is not checked out")
        git.create_and_checkout_run_branch(name)
    run.finish(it["op"], branch=name)
    return f"{it['op']} run branch {name}: checked out"


def _reconcile_replan(run, git, it, crash, **_):
    from . import replan
    try:
        return replan.apply(run, git, it, crash)
    except replan.Refused as exc:
        raise ReconcileError(str(exc)) from exc


_RECONCILERS = {"replan": _reconcile_replan, "branch": _reconcile_branch,
                "commit": _reconcile_commit, "restore": _reconcile_restore, "pin": _reconcile_pin,
                "patch": _reconcile_patch, "close": _reconcile_close, "revert": _reconcile_revert,
                "agent": _reconcile_agent, "command": _reconcile_command,
                "decision": _reconcile_decision, "recover": _reconcile_recover}


# -- rendering ----------------------------------------------------------------------------------

RUN_HEADLINE = {"running": "in progress", "done": "done", "failed": "failed",
                "needs_human": "needs a person", "stopped": "stopped"}


def _money(x):
    return f"${x:.2f}"


def branch_disposition(info, state):
    """For a finished run on its own branch: is its last accepted commit in the branch it came
    from, and in that branch's upstream? None when there is nothing to say or git cannot tell.
    Observed, never decided: nothing in the engine reads it."""
    if state["status"] != "done" or info.get("branch_mode") == "current":
        return None
    commits = [state["tasks"][t].get("commit") for t in state["order"]]
    commits = [c for c in commits if c]
    target = info.get("original_branch")
    if not commits or not target:
        return None
    try:
        git = gitops.Git(info["git_toplevel"])
    except gitops.GitError:
        return None
    last = commits[-1]

    def contains(ref):
        if git.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).returncode:
            return None
        return git.run("merge-base", "--is-ancestor", last, ref, check=False).returncode == 0

    merged = contains("refs/heads/" + target)
    if merged is None:
        return None
    res = git.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", target + "@{upstream}",
                  check=False)
    upstream = res.stdout.decode("utf-8", "replace").strip() if res.returncode == 0 else ""
    return {"commit": last, "target": target, "merged": merged, "upstream": upstream or None,
            "pushed": contains("refs/remotes/" + upstream) if merged and upstream else None}


def _in_flight(state, now, run_path=None):
    """One line per agent call or command that has begun and not finished. With `run_path`, an
    agent call's line also says what the provider's own record shows it has used so far (G4):
    tokens, never dollars, and nothing when no record can be read."""
    lines = []
    for it in state["intents"]:
        if it.get("kind") not in ("agent", "command"):
            continue
        what = "agent call" if it["kind"] == "agent" else f"command `{it.get('command', '')}`"
        line = f"- **{it.get('task', '?')}**: {what}"
        if it.get("at"):
            line += f", started {it['at'][11:19]} UTC"
            if now is not None:
                began = datetime.datetime.strptime(it["at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
                secs = max(0, int((now - began).total_seconds()))
                line += f", running for {secs // 60} min {secs % 60:02d} s"
        if run_path and it["kind"] == "agent" and it.get("invocation_dir") and it.get("agent_kind"):
            from . import agents
            usage = agents.partial_usage(it["agent_kind"], os.path.join(run_path, it["invocation_dir"]),
                                         agents._epoch(it.get("at")))
            if usage:
                line += (f", {usage.get('tokens_in', 0)} tokens in and {usage.get('tokens_out', 0)} out "
                         "so far (the provider's record; unpriced)")
        if it.get("invocation_dir"):
            line += f". Log: `{it['invocation_dir']}/`"
        lines.append(line)
    return lines


def _set_aside_record(run_path, t):
    """The task's published `set-aside.json`, or None. `failed.patch` alone does not mean the
    work can be put back: an old run already replanned by an older runner may have `failed.patch`
    with no `set-aside.json` and nothing left to derive it from (C4's failure case), which
    `--apply-patch` cannot act on."""
    path = os.path.join(run_path, "tasks", t["dir"], "set-aside.json")
    return read_json(path) if os.path.exists(path) else None


def _has_set_aside(run_path, t):
    """Is there set-aside work of this task that can still be put back? A record whose `paths`
    is empty is itself "no set-aside work" (the attempt changed nothing; D9), so `--apply-patch`
    has nothing to apply."""
    rec = _set_aside_record(run_path, t)
    return bool(rec and rec["paths"])


PROTOCOL_BLOCK = "the reviewers could not answer in the required form"
MIXED_BLOCK = "one reviewer could not answer in the required form and another did not finish"
REVIEWER_CAUSE = {"protocol-error": "could not answer in the required form",
                  "timed-out": "ran past its time limit",
                  "agent-error": "ended with an error",
                  "interrupted": "was interrupted"}


def _block_kind(t):
    """How a producer's panel failed — "protocol", "mixed", or None. Read defensively: the field
    is absent in every state written before it existed, and it describes a `blocked` task only,
    so a retry or a replan that moves the task on cannot leave a stale label on the page."""
    return t.get("block_kind") if t["status"] == "blocked" else None


def _cause(r):
    """One broken reviewer's cause in its own words, never the panel's classification."""
    return REVIEWER_CAUSE.get(r["status"], r["status"])


def _reviewer_causes(t):
    """The list requirement 3 asks for, rendered whichever way the panel failed, so the accurate
    cause per reviewer is always on the page. The retry budget is named only where it means
    something: a timed-out call is finalised on its first try, without any retry."""
    lines = []
    for r in t.get("block_reviewers") or []:
        tries = r["tries"]
        spent = f" ({tries} tr{'y' if tries == 1 else 'ies'})" if r["status"] == "protocol-error" else ""
        lines.append(f"- {r['reviewer']}: {_cause(r)}{spent}.")
    return lines


def _panel_attention(task_id, t, kind):
    """The "Needs attention" line of a producer its panel could not judge. It says nobody judged
    the work, and sends the owner to the summaries rather than to a parser diagnostic."""
    where = f"tasks/{t['dir']}/STATUS.md"
    if kind == "protocol":
        n = len(t.get("rejected_reviews") or [])
        if n == 0:
            rejected = f"No answer could be read; see {where}."
        elif n == 1:
            rejected = f"1 review answer was rejected and it was not applied; it is summarised in {where}."
        else:
            rejected = (f"{n} review answers were rejected and none was applied; they are "
                        f"summarised in {where}.")
        return f"- **{task_id}** is blocked: {PROTOCOL_BLOCK}. {rejected}"
    per = "; ".join(f"{r['reviewer']}: {_cause(r)}" for r in t.get("block_reviewers") or [])
    return (f"- **{task_id}** is blocked: {MIXED_BLOCK}. Per reviewer: {per}. "
            f"The rejected answers are summarised in {where}.")


def render_run_status(info, state, disposition=None, now=None, run_path=None, alive=False):
    """`alive`: a runner holds this run's lock and is working. Its open operations are then the
    calls and commands in flight, listed under "In flight", not operations that were interrupted;
    that line is for a run no runner is working on, where an open intent is one left behind."""
    spend = state["spend"]
    unpriced = spend["unpriced"]
    lines = [f"# {info['workflow']} — run {info['run_id'][:8]} — "
             f"{RUN_HEADLINE.get(state['status'], state['status'])}", "",
             f"Started {info['started'].replace('T', ' ').replace('Z', ' UTC')}. "
             f"{state['seconds'] // 60} min of agent time. Branch {info['branch']}.",
             f"Spend: {_money(spend['known_usd'])} known of {_money(state['run_budget_usd'])}, "
             f"{_money(spend['reserved_usd'])} reserved"
             + (f", plus {unpriced['calls']} unpriced calls ({unpriced['tokens_in']} tokens in, "
                f"{unpriced['tokens_out']} out; {unpriced['unknown_calls']} with unknown usage"
                + (f"; cap {state['run_budget_tokens']} tokens" if state.get("run_budget_tokens") else "")
                + ")" if unpriced["calls"] or unpriced["unknown_calls"] else "") + ".", "",
             "| # | Task | Type | Status | Attempts | Cost | Commit |", "|---|---|---|---|---|---|---|"]
    attention = []
    for task_id in state["order"]:
        t = state["tasks"][task_id]
        status = t["status"] + (f" ({t['reason']})" if t["reason"] and t["status"] == "skipped" else "")
        kind = _block_kind(t)
        if kind:
            status = "blocked (protocol)" if kind == "protocol" else "blocked (protocol, in part)"
        if t.get("stale"):
            status += " (stale)"
            attention += [f"- **{task_id}** was accepted on an older version of {s['file']} "
                          f"({s['was'][:7]}, now {s['now'][:7]}), changed by '{s['by']}', and only "
                          "review or a person verified it. Its acceptance does not cover the new "
                          "content." for s in t["stale"]]
        lines.append(f"| {t['dir'].split('-', 1)[0]} | {task_id} | {t['type']} | {status} | "
                     f"{t['attempts'] or ''} | {_money(t['cost_usd']) if t['cost_usd'] else ''} | "
                     f"{(t['commit'] or '')[:7]} |")
        for finding in t.get("ledger", {}).get("findings", []):
            if finding["severity"] == "blocking" and finding["status"] in ("open", "disputed", "escalated"):
                attention.append(f"- **{finding['id']}** [{finding['status']}]: {finding['title']}")
        if t["status"] in ("waiting_human", "blocked", "failed"):
            attention.append(_panel_attention(task_id, t, kind) if kind else
                             f"- **{task_id}** is {t['status']}"
                             + (f": {t['reason']}" if t["reason"] else "")
                             + f". See tasks/{t['dir']}/STATUS.md.")
    selections = [(tid, state['tasks'][tid].get('provider_current')) for tid in state['order']]
    if any(selection for _, selection in selections):
        lines += ['', '## Providers']
        for tid, selection in selections:
            if selection:
                lines.append(f"- **{tid}**: {selection['profile']} / {selection['model'] or 'provider default'} "
                             f"({selection['complexity']}; {selection['reason']}).")
    flying = _in_flight(state, now, run_path) if state["status"] == "running" else []
    if flying:
        lines += ["", "## In flight"]
        if now is not None:
            lines.append(f"As of {now.strftime('%H:%M:%S')} UTC (refreshed about every "
                         f"{HEARTBEAT_S} s while the runner is alive; an old time here means no "
                         "runner is working on this run).")
        lines += flying
    if state.get("stop_reason"):
        attention.append(f"- The run stopped: {state['stop_reason']}")
    if state["intents"] and not (alive and state["status"] == "running"):
        attention.append(f"- {len(state['intents'])} operation(s) were interrupted; "
                         "`runner resume` reconciles them first.")
    if attention:
        lines += ["", "## Needs attention"] + attention
    lines += ["", "## Next"]
    if state["status"] == "done":
        d = disposition
        if d and d["merged"]:
            where = f"`{d['target']}`"
            if d["pushed"]:
                where += f" and in `{d['upstream']}` (as last fetched)"
            elif d["upstream"]:
                where += f"; `{d['upstream']}` does not have it yet: push `{d['target']}`"
            lines.append(f"    Merged: the last accepted commit {d['commit'][:7]} is in {where}.")
            lines.append(f"    Nothing is left to do. The branch {info['branch']} can be deleted; "
                         "`runner prune` removes this run's pinned refs.")
        elif d:
            lines.append(f"    Not merged: `{d['target']}` does not contain the last accepted "
                         f"commit {d['commit'][:7]}.")
            lines.append("    Inspect the branch; merging it is your call.")
        else:
            lines.append("    Inspect the branch; merging it is your call.")
    else:
        for task_id in state["order"]:
            t = state["tasks"][task_id]
            if t["kind"] == "human" and t["status"] == "waiting_human" and not t.get("decision"):
                lines += [f"    runner approve {info['name']} {task_id}",
                          f"    runner reject {info['name']} {task_id} -m \"why\""]
            elif t["status"] in ("failed", "blocked") or (
                    t["status"] == "pending" and t["kind"] == "produce" and _has_set_aside(run_path, t)):
                kind = _block_kind(t)
                if kind:
                    # Nobody judged this candidate, so continuing from the set-aside work is the
                    # right default rather than one of two options: no brackets. The flag is
                    # printed only when there is work to put back — an attempt that changed
                    # nothing leaves `paths: []`, and `retry --apply-patch` refuses such a task
                    # outright (D9), so an unconditional flag would name a command that fails.
                    recover = " --apply-patch" if run_path and _has_set_aside(run_path, t) else ""
                    lines += [f"    # {task_id}: " + (f"{PROTOCOL_BLOCK}." if kind == "protocol"
                              else "one reviewer could not answer in the required form; another "
                                   "did not finish."),
                              f"    # Read the rejected answers in tasks/{t['dir']}/STATUS.md first.",
                              f"    runner retry {info['name']} {task_id}{recover}"]
                else:
                    lines.append(f"    runner retry {info['name']} {task_id}"
                                 + (" [--apply-patch]" if t["kind"] == "produce" else ""))
        for t in state["tasks"].values():
            for finding in t.get("ledger", {}).get("findings", []):
                if finding["status"] == "escalated":
                    lines.append(f"    runner resolve {info['name']} {finding['id']} --as resolved|advisory|upheld")
        reason = str(state.get("stop_reason", ""))
        lines.append(f"    runner resume {info['name']}"
                     + ("" if state["status"] != "stopped" or reason.startswith("paused")
                        else " --add-tokens N" if reason.startswith("the token cap")
                        else " --add-budget USD"))
    return "\n".join(lines) + "\n"


def _rejected_answer_headline(entry):
    """What one rejected answer claimed, read from its summary alone and never judged here."""
    verdict, found, unreadable = entry["verdict"], entry["findings"], entry["unreadable_findings"]
    if verdict is None:
        return "no readable answer" if not found and not unreadable else "no readable verdict"
    if not found:
        return f"claimed verdict `{verdict}`, no findings"
    return f"claimed verdict `{verdict}`, {len(found)} finding" + ("s" if len(found) > 1 else "")


def _render_rejected_answer(entry):
    lines = [f"- **{entry['reviewer']}**, round {entry['round']}, try {entry['try']} — "
             f"{_rejected_answer_headline(entry)}:"]
    lines += [f"  - {f['severity']}: {f['title']}" for f in entry["findings"]]
    if entry["unreadable_findings"]:
        lines.append(f"  - {entry['unreadable_findings']} further entries could not be read")
    lines.append(f"  Rejected because: {entry['error']}")
    if entry.get("invocation"):
        lines.append(f"  Answer: `{entry['invocation']}/last-message.txt`")
    return lines


def _repaired_answers(ledger):
    """(reviewer, round, dropped entries) per repaired review answer, oldest first, derived from
    the `repair` history event `findings.apply_review` leaves on every finding a repaired answer
    raised, so this needs no new state.

    Answers are told apart by the `answer` discriminator that event carries: the findings of one
    answer share it, and no two answers do, so a repair keeps its own line for the life of the run
    whatever happens to its findings afterwards — a response, a resolution, or a retry, which
    supersedes them and clears the reviewers' rounds, so that the next repair is round 1 again. An
    event written before that field existed groups by its reviewer and round, as it did then."""
    answers = {}
    for f in (ledger or {}).get("findings", []):
        repair = next((h for h in f["history"] if h["event"] == "repair"), None)
        if repair is not None:
            answers.setdefault((f["reviewer"], repair["round"], repair.get("answer")),
                               repair["dropped"])
    return [(reviewer, round_no, dropped)
            for (reviewer, round_no, _answer), dropped in answers.items()]


def render_task_status(task_id, t, tdir, run_name):
    kind = _block_kind(t)
    headline = t["status"] if not kind else (
        f"blocked: {PROTOCOL_BLOCK}" if kind == "protocol" else
        "blocked: the panel did not finish (one reviewer could not answer in the required form)")
    lines = [f"# {task_id} — {headline}", "", f"Kind {t['kind']}, type {t['type']}."]
    if t["reason"]:
        lines.append(f"Reason: {t['reason']}")
    if t["commit"]:
        lines.append(f"Accepted as commit {t['commit']}. See commit.json.")
    if kind == "protocol":
        lines += ["", "This is a protocol failure of the panel, not a judgement of the work. No "
                  "finding from these rounds reached the ledger."]
    if kind:
        lines += ["", "Why each reviewer did not finish:"] + _reviewer_causes(t)
    entries = sorted(n for n in os.listdir(tdir)
                     if n.startswith(("attempt-", "round-")) and os.path.isdir(os.path.join(tdir, n)))
    entries.sort(key=lambda n: (n.split("-")[0], int(n.split("-")[1])))
    if entries:
        lines += ["", "## History"] + [f"- {n}/" for n in entries]
    if os.path.exists(os.path.join(tdir, "failed.patch")):
        lines += ["", "Its work was set aside in failed.patch; the candidate tree is pinned under "
                  "refs/task-runner/."]
        sa_path = os.path.join(tdir, "set-aside.json")
        if os.path.exists(sa_path):
            rec = read_json(sa_path)
            if rec["paths"]:                        # empty paths: nothing --apply-patch can put back
                lines.append(f"Set aside from attempt {rec['attempt']} ({rec['status']}: "
                             f"{rec['reason']}), {len(rec['paths'])} files.")
                lines.append(f"To put it back before the next attempt: runner retry {run_name} "
                             f"{task_id} --apply-patch")
    if t.get("recover"):
        lines += ["", f"Queued: the set-aside work of attempt {t['recover']['attempt']} will be "
                  "put back before the next attempt."]
    elif t.get("recovered"):
        r = t["recovered"]
        lines += ["", f"The set-aside work of attempt {r['attempt']} was put back before attempt "
                  f"{r['attempt'] + 1} ({r['files']} files)."]
    if t.get("rejected_reviews"):
        lines += ["", "## Rejected review answers", "",
                  "Not applied. Nothing below is in the ledger and none of it changed acceptance. "
                  "Read it before you retry: the concerns in it may be real.", ""]
        for entry in t["rejected_reviews"]:
            lines += _render_rejected_answer(entry)
    repaired = _repaired_answers(t.get("ledger"))
    if repaired:
        lines += ["", "## Repaired review answers", ""]
        for reviewer, round_no, dropped in repaired:
            what = ("1 meaningless `resolutions` entry was dropped" if len(dropped) == 1 else
                    f"{len(dropped)} meaningless `resolutions` entries were dropped")
            lines.append(f"- **{reviewer}**, round {round_no}: {what} and the answer was applied. "
                         "The entries named no finding in the ledger, and the round required none. "
                         "See findings.json.")
    return "\n".join(lines) + "\n"


FILE_NOTES = {
    "activity.json": "Hook telemetry routing, correlation IDs and configured source hashes",
    "hooks/": "Native headless-agent hook events; observational, not acceptance evidence",
    "hooks.jsonl": "Native hook events, correlated with run/task/invocation and session/tool IDs",
    "hooks.log": "Readable native hook events for tail -f",

    "run.json": "Identity of the run (id, workflow, root, branch, base commit) and its totals",
    "STATUS.md": "This directory in words. Regenerated from state.json",
    "index.json": "This file: what every entry in this directory is",
    "state.json": "The engine's state. The single source of truth",
    "state.json.tmp": "A leftover of an interrupted save. Ignored",
    "events.jsonl": "Append-only log, one JSON event per line",
    "workflow.toml": "Frozen copy of the workflow as started",
    "workflow.expanded.json": "Every task after types, personas, panels and defaults are applied",
    "integrity.json": "Hashes of the decision-bearing files, checked around every job",
    "git-index": "The run's scratch git index, used for work-tree snapshots",
    "qualification.json": "What doctor established for each agent profile, per capability",
    "library/": "Frozen copies of the type and persona files this run uses",
    "types/": "Frozen task type files",
    "personas/": "Frozen reviewer persona files",
    "briefs/": "Frozen content of every prompt_file, named by task id",
    "replans/": "One directory per replan: before, after, changes, reverts",
    "tasks/": "One directory per task: <order>-<task id>",
    "task.json": "The resolved task definition",
    "findings.json": "The findings ledger of this producer: all reviewers, all rounds",
    "failed.patch": "The complete, binary-capable patch of work that was set aside",
    "set-aside.json": "What was set aside: the attempt, why, the base and candidate trees, the paths",
    "commit.json": "The accepted commit: sha, files, message",
    "decision.json": "Who approved or rejected, when, and the comment",
    "prompt.md": "Exactly what the agent was sent",
    "feedback.md": "What sent the work back, and the findings that need a response",
    "result.json": "The agent's validated answer, with cost, usage, seconds and session id",
    "responses.json": "The author's answer to each finding",
    "inputs.json": "Hashes of the upstream outputs this attempt was given",
    "outputs.json": "Manifest of the declared outputs after this attempt, and the candidate tree id",
    "changes.diff": "Readable diff of this attempt, capped. For reading, never for recovery",
    "reverted.json": "Paths the runner put back: outside `writes`, protected or frozen",
    "gate.log": "Output of the gate commands",
    "verification.json": "Each gate, check and verdict with the candidate tree id it judged",
    "verdict.json": "The reviewer's validated answer, the candidate it judged, the diff base",
    "argv.json": "Exactly how the agent was invoked. Never holds credentials",
    "stdout.log": "The agent's standard output, streamed and redacted",
    "stderr.log": "The agent's standard error, streamed and redacted",
    "last-message.txt": "The agent's final message, written by this invocation",
    "schema.json": "The JSON schema the answer was asked to follow",
    "outcome.json": "How the call ended: ok, protocol-error, agent-error, timed-out, interrupted, environment, quota; usage_source: terminal, provider-record or unknown",
}


def _note(name, is_dir):
    key = name + "/" if is_dir else name
    if key in FILE_NOTES:
        return FILE_NOTES[key]
    if is_dir:
        stem, _, number = name.partition("-")
        if stem == "attempt" and number.isdigit():
            return f"Attempt {number} of this producer. Numbers are never reused"
        if stem == "round" and number.isdigit():
            return f"Review round {number} of this reviewer"
        if stem == "invocation" and number.isdigit():
            return f"Agent call {number}: raw invocation and output"
        if stem.isdigit():
            return f"Task '{number}'"
        return ""
    if name.endswith(".toml"):
        return "Frozen library file"
    if name.endswith(".md"):
        return "Frozen brief"
    return ""


def _about(run_path, directory):
    rel = os.path.relpath(directory, run_path).replace(os.sep, "/")
    if rel == ".":
        return "One run of a workflow. Start with STATUS.md"
    parts = rel.split("/")
    return _note(parts[-1], True) or f"Part of the run record: {rel}"


def render_index(run_path, directory):
    entries = {}
    names = set(os.listdir(directory)) | {"index.json"}
    for name in sorted(names):
        is_dir = os.path.isdir(os.path.join(directory, name))
        entries[name + ("/" if is_dir else "")] = _note(name, is_dir)
    rel = os.path.relpath(directory, run_path).replace(os.sep, "/")
    return {"path": "" if rel == "." else rel, "about": _about(run_path, directory),
            "files": entries}
