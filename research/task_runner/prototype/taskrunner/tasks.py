"""Task list: load a TOML plan, apply defaults, validate, and give a fixed order."""

import os
import re
import tomllib
from dataclasses import dataclass, field

DEFAULTS = {
    "agent": "claude",          # who implements
    "reviewer": "",             # who reviews; empty means the same agent, always in a new session
    "review": True,
    "human_review": False,      # pause for a person after review, before the commit
    "max_attempts": 3,
    "timeout_min": 30,          # wall clock per agent call
    "gate_timeout_min": 20,     # wall clock per gate command
    "budget_usd": 5.0,          # per agent call, where the agent can enforce one
    "run_budget_usd": 50.0,     # whole run, checked before every agent call
    "commit": True,
    "branch": "",               # empty: commit on the current branch
    "protected": [],            # globs the implementing agent must not change
    "model": "",
    "review_model": "",
    "commit_trailer": "",       # appended to every commit message
    "allow_dirty": False,       # start even if the work tree has uncommitted changes
}
TASK_KEYS = {"id", "title", "prompt", "prompt_file", "needs", "gate"} | (set(DEFAULTS) - {"run_budget_usd", "branch", "allow_dirty"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PlanError(Exception):
    pass


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    gate: list
    needs: list
    opts: dict = field(default_factory=dict)

    def __getattr__(self, name):
        try:
            return self.__dict__["opts"][name]
        except KeyError:
            raise AttributeError(name)


@dataclass
class Plan:
    name: str
    root: str
    path: str
    defaults: dict
    agents: dict
    tasks: list             # in execution order

    def task(self, task_id):
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise PlanError(f"no task '{task_id}'")


def load(path):
    path = os.path.abspath(path)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise PlanError(f"{path}: {e}")
    base = os.path.dirname(path)
    errors = []

    defaults = dict(DEFAULTS)
    for k, v in doc.get("defaults", {}).items():
        if k not in DEFAULTS:
            errors.append(f"[defaults] unknown key '{k}'")
        elif type(v) is not type(DEFAULTS[k]) and not (isinstance(DEFAULTS[k], float) and isinstance(v, int)):
            errors.append(f"[defaults] '{k}' must be {type(DEFAULTS[k]).__name__}")
        else:
            defaults[k] = v

    root = os.path.abspath(os.path.join(base, doc.get("root", ".")))
    raw = doc.get("task", [])
    if not raw:
        errors.append("no [[task]] entries")
    tasks, seen = [], set()
    for i, t in enumerate(raw):
        tid = str(t.get("id", ""))
        where = f"task #{i + 1} ('{tid}')"
        if not ID_RE.match(tid):
            errors.append(f"{where}: id must match {ID_RE.pattern}")
        if tid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(tid)
        for k in t:
            if k not in TASK_KEYS:
                errors.append(f"{where}: unknown key '{k}'")
        prompt = t.get("prompt", "")
        if t.get("prompt_file"):
            try:
                with open(os.path.join(base, t["prompt_file"])) as f:
                    prompt = (prompt + "\n\n" + f.read()).strip()
            except OSError as e:
                errors.append(f"{where}: {e}")
        if not prompt.strip():
            errors.append(f"{where}: needs 'prompt' or 'prompt_file'")
        gate = t.get("gate", [])
        gate = [gate] if isinstance(gate, str) else list(gate)
        if not gate:
            errors.append(f"{where}: needs a 'gate' command. A task with no check cannot be verified")
        opts = {k: t.get(k, defaults[k]) for k in DEFAULTS}
        tasks.append(Task(tid, t.get("title", tid), prompt, gate, list(t.get("needs", [])), opts))

    ids = [t.id for t in tasks]
    for t in tasks:
        for n in t.needs:
            if n not in ids:
                errors.append(f"task '{t.id}': needs unknown task '{n}'")
    agents = doc.get("agents", {})
    known = set(agents) | {"claude", "codex"}
    for t in tasks:
        for role in ("agent", "reviewer"):
            if t.opts[role] and t.opts[role] not in known:
                errors.append(f"task '{t.id}': {role} '{t.opts[role]}' is not defined under [agents]")
    if errors:
        raise PlanError("\n".join(errors))
    return Plan(doc.get("name") or os.path.splitext(os.path.basename(path))[0], root, path,
                defaults, agents, _order(tasks))


def _order(tasks):
    """Dependencies first. Among ready tasks, the order in the file. Always the same result."""
    done, out, left = set(), [], list(tasks)
    while left:
        ready = [t for t in left if all(n in done for n in t.needs)]
        if not ready:
            raise PlanError("dependency cycle among: " + ", ".join(t.id for t in left))
        out.append(ready[0])
        done.add(ready[0].id)
        left.remove(ready[0])
    return out
