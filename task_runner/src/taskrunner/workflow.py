"""Load a workflow, its types and personas; apply precedence; expand panels; validate.

This module is pure apart from reading files and asking git three questions about the root:
is it a repository, which files are tracked, and which declared paths are ignored.
It never checks agent capabilities: `validate` must work with no agent installed (B5).
"""

import heapq
import math
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field

from . import patterns

BUILTIN_LIBRARY = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "library"))

KINDS = ("produce", "review", "check", "human")
CAPABILITIES = ("answer", "read", "execute", "write", "resume", "boundary")
BUILTIN_AGENTS = ("claude", "codex")
BUILTIN_PROTECTED = ["**/.gitignore", "**/.gitattributes", "**/.gitmodules"]

ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.-]*)\}")

PLACEHOLDERS = {
    "task.id", "task.title", "task.prompt", "inputs", "outputs", "gates", "rules", "persona",
    "target", "diff", "findings", "attempt", "max_attempts", "result_schema",
}
REVIEW_ONLY_PLACEHOLDERS = {"persona", "target", "diff"}

BUILTIN_DEFAULTS = {
    "agent": "claude",
    "model": "",
    "max_attempts": 3,
    "timeout_min": 30,
    "gate_timeout_min": 20,
    "budget_usd": 5.0,
    "run_budget_usd": 50.0,
    "run_budget_tokens": 0,
    "max_parallel": 4,
    "recheck_passed": "diff",
    "branch": "run",
    "commit_trailer": "",
    "protected": [],
    "diff_cap_bytes": 200000,
    "inputs_cap_bytes": 40000,
    "findings_cap_bytes": 60000,
}

STR, BOOL, INT, NUM, STRLIST, TABLE, ANY = "string", "boolean", "integer", "number", \
    "list of strings", "table", "any"

DEFAULTS_KEYS = {
    "agent": STR, "model": STR, "max_attempts": INT, "timeout_min": NUM, "gate_timeout_min": NUM,
    "budget_usd": NUM, "run_budget_usd": NUM, "run_budget_tokens": INT, "max_parallel": INT,
    "recheck_passed": STR,
    "branch": STR, "commit_trailer": STR, "protected": STRLIST, "diff_cap_bytes": INT,
    "inputs_cap_bytes": INT, "findings_cap_bytes": INT, "complexity": STR,
}
TOP_KEYS = {"name": STR, "root": STR, "library": STRLIST, "defaults": TABLE, "agents": TABLE,
            "task": ANY, "model_policy": TABLE}
AGENT_KEYS = {
    "kind": STR, "model": STR, "sandbox": STR, "review_mode": STR, "permission_mode": STR,
    "ignore_user_config": BOOL, "extra_args": STRLIST, "argv": STRLIST, "read_only_args": STRLIST,
}
TYPE_KEYS = {
    "name": STR, "kind": STR, "description": STR, "requires": STRLIST, "complexity": STR, "review_type": STR,
    "needs_run_dir": BOOL, "agent": STR, "model": STR, "gate": ANY, "protected": STRLIST,
    "prompt": STR, "params": TABLE, "max_attempts": INT, "timeout_min": NUM, "budget_usd": NUM,
}
PARAM_KEYS = {"default": ANY, "required": BOOL}
PERSONA_KEYS = {
    "name": STR, "code": STR, "title": STR, "agent": STR, "model": STR, "advisory": BOOL,
    "focus": STRLIST, "blocking": STRLIST, "out_of_scope": STRLIST,
}

COMMON_TASK_KEYS = {"id": STR, "type": STR, "title": STR, "needs": STRLIST, "params": TABLE}
AGENT_TASK_KEYS = {"agent": STR, "model": STR, "timeout_min": NUM, "budget_usd": NUM,
                   "prompt": STR, "prompt_file": STR, "recheck_passed": STR, "fallback_agents": STRLIST, "complexity": STR}
TASK_KEYS = {
    "produce": {**COMMON_TASK_KEYS, **AGENT_TASK_KEYS, "max_attempts": INT, "outputs": ANY,
                "writes": STRLIST, "removes": STRLIST, "gate": ANY, "reviewers": ANY,
                "protected": STRLIST},
    "review": {**COMMON_TASK_KEYS, **AGENT_TASK_KEYS, "reviews": STR, "perspective": STR,
               "advisory": BOOL, "protected": STRLIST},
    "check": {**COMMON_TASK_KEYS, "verifies": STR, "run": STRLIST, "read_only": BOOL,
              "restores": BOOL, "protected": STRLIST},
    "human": {**COMMON_TASK_KEYS, "verifies": STR},
}
ALL_TASK_KEYS = set().union(*TASK_KEYS.values())
PANEL_ENTRY_KEYS = {
    "perspective": STR, "advisory": BOOL, "agent": STR, "model": STR, "type": STR, "prompt": STR,
    "prompt_file": STR, "recheck_passed": STR, "timeout_min": NUM, "budget_usd": NUM, "fallback_agents": STRLIST, "complexity": STR,
    "params": TABLE,
}
GATE_KEYS = {"run": STR, "new": BOOL, "fail_pattern": STR}
OUTPUT_KEYS = {"path": STR, "may_be_empty": BOOL}

BYPASS_SANDBOXES = {"danger-full-access"}
BYPASS_PERMISSION_MODES = {"bypassPermissions"}
BYPASS_ARGS = {"--dangerously-skip-permissions", "--dangerously-bypass-approvals-and-sandbox",
               "--yolo"}


class WorkflowError(Exception):
    """Raised by `load_or_raise` when a workflow has errors."""

    def __init__(self, errors, warnings=()):
        super().__init__("\n".join(errors))
        self.errors = list(errors)
        self.warnings = list(warnings)


@dataclass
class Workflow:
    name: str = ""
    workflow_file: str = ""
    root: str = ""
    git_toplevel: str = ""
    library_dirs: list = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    model_policy: dict = field(default_factory=dict)
    agents: dict = field(default_factory=dict)
    types: dict = field(default_factory=dict)
    personas: dict = field(default_factory=dict)
    tasks: list = field(default_factory=list)      # expanded, in execution order
    claims: list = field(default_factory=list)     # frozen outputs a later task will modify
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def task(self, task_id):
        for t in self.tasks:
            if t["id"] == task_id:
                return t
        raise KeyError(task_id)

    def expanded(self):
        """Everything after types, personas, panels and defaults are applied, as plain data."""
        return {
            "name": self.name,
            "paths": {"workflow_file": self.workflow_file, "root": self.root,
                      "git_toplevel": self.git_toplevel, "library": list(self.library_dirs)},
            "defaults": dict(self.defaults),
            "agents": {k: dict(v) for k, v in self.agents.items()},
            "tasks": [dict(t) for t in self.tasks],
            "claims": [dict(c) for c in self.claims],
        }


def load_or_raise(path):
    wf = load(path)
    if wf.errors:
        raise WorkflowError(wf.errors, wf.warnings)
    return wf


def load(path):
    """Load and validate. Never raises for a bad workflow: every problem is in `.errors`."""
    return _Loader(path).load()


# --------------------------------------------------------------------------------------------


def _type_ok(value, kind):
    if kind == ANY:
        return True
    if kind == STR:
        return isinstance(value, str)
    if kind == BOOL:
        return isinstance(value, bool)
    if kind == INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == NUM:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == STRLIST:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == TABLE:
        return isinstance(value, dict)
    return False


class _Loader:
    def __init__(self, path):
        self.wf = Workflow(workflow_file=os.path.abspath(path))
        self.base = os.path.dirname(self.wf.workflow_file)
        self.tracked = None

    def err(self, msg):
        if msg not in self.wf.errors:
            self.wf.errors.append(msg)

    def warn(self, msg):
        if msg not in self.wf.warnings:
            self.wf.warnings.append(msg)

    def check_keys(self, table, allowed, where):
        """Report unknown keys and wrong value types. Returns only the usable entries."""
        good = {}
        for key, value in table.items():
            if key not in allowed:
                self.err(f"{where}: unknown key '{key}'")
            elif not _type_ok(value, allowed[key]):
                self.err(f"{where}: '{key}' must be a {allowed[key]}")
            elif allowed[key] == NUM and (not math.isfinite(value) or value <= 0):
                self.err(f"{where}: '{key}' must be finite and greater than zero")
            else:
                good[key] = value
        return good

    # -- top level ---------------------------------------------------------------------------

    def load(self):
        wf = self.wf
        label = os.path.basename(wf.workflow_file)
        try:
            with open(wf.workflow_file, "rb") as fh:
                raw = tomllib.load(fh)
        except OSError as exc:
            self.err(f"{label}: cannot read: {exc.strerror or exc}")
            return wf
        except tomllib.TOMLDecodeError as exc:
            self.err(f"{label}: not valid TOML: {exc}")
            return wf

        top = self.check_keys(raw, TOP_KEYS, label)
        wf.name = top.get("name") or os.path.splitext(label)[0]
        if not ID_RE.match(wf.name):
            self.err(f"{label}: 'name' must match [A-Za-z0-9][A-Za-z0-9_-]*, got '{wf.name}'")
        wf.root = os.path.normpath(os.path.join(self.base, top.get("root", ".")))

        defaults = dict(BUILTIN_DEFAULTS)
        given = self.check_keys(top.get("defaults", {}), DEFAULTS_KEYS, f"{label} [defaults]")
        self.given_defaults = given
        defaults.update(given)
        if defaults["recheck_passed"] not in ("diff", "never"):
            self.err(f"{label} [defaults]: 'recheck_passed' must be \"diff\" or \"never\"")
        if defaults["branch"] not in ("run", "current"):
            self.err(f"{label} [defaults]: 'branch' must be \"run\" or \"current\"")
        for key in ("max_attempts", "max_parallel"):
            if defaults[key] < 1:
                self.err(f"{label} [defaults]: '{key}' must be at least 1")
        if defaults["run_budget_tokens"] < 0:
            self.err(f"{label} [defaults]: 'run_budget_tokens' must be 0 (no cap) or more")
        wf.defaults = defaults

        wf.model_policy = self.check_keys(top.get('model_policy', {}),
            {level: TABLE for level in ('mechanical', 'standard', 'high')}, f'{label} [model_policy]')
        for level, models in list(wf.model_policy.items()):
            wf.model_policy[level] = self.check_keys(models,
                {provider: STR for provider in ('claude', 'codex', 'command')}, f'model_policy.{level}')
            if any(not model.strip() for model in wf.model_policy[level].values()):
                self.err(f'model_policy.{level}: model names must not be empty')
        self.load_agents(top.get("agents", {}), label)
        self.check_root()
        self.load_library(top.get("library", []), label)

        raw_tasks = raw.get("task", [])
        if not isinstance(raw_tasks, list) or not all(isinstance(t, dict) for t in raw_tasks):
            self.err(f"{label}: tasks must be written as [[task]] tables")
            raw_tasks = []
        if not raw_tasks:
            self.err(f"{label}: the workflow has no tasks")

        tasks = self.resolve_tasks(raw_tasks)
        self.check_patterns(tasks, defaults["protected"], label)
        self.check_references(tasks)
        self.check_verifiers(tasks)
        self.check_paths(tasks)
        has_cycle = self.check_cycles(tasks)
        if not has_cycle:
            self.check_writers(tasks)
        self.protect_executed_files(tasks)
        self.check_ignored(tasks)
        used_agents = sorted({t["agent"] for t in tasks if t["kind"] in ("produce", "review")})
        for name in used_agents:
            profile = wf.agents.get(name, {})
            if profile.get("kind", name) in ("command", "codex"):
                cap = wf.defaults["run_budget_tokens"]
                self.warn(f"agent '{name}' reports no dollar cost: dollar limits do not bind on it; "
                          "time and attempts still apply, and usage is recorded as unpriced"
                          + (f"; run_budget_tokens stops the run once {cap} tokens were used"
                             if cap else "; set run_budget_tokens to cap its usage"))
        wf.tasks = self.order(tasks, has_cycle)
        for n, t in enumerate(wf.tasks):
            t["order"] = n
        return wf

    def load_agents(self, table, label):
        wf = self.wf
        for name in BUILTIN_AGENTS:
            wf.agents[name] = {"kind": name}
        for name, profile in table.items():
            where = f"{label} [agents.{name}]"
            if not isinstance(profile, dict):
                self.err(f"{where}: must be a table")
                continue
            good = self.check_keys(profile, AGENT_KEYS, where)
            kind = good.get("kind", name if name in BUILTIN_AGENTS else "command")
            if kind not in BUILTIN_AGENTS + ("command",):
                self.err(f"{where}: 'kind' must be \"claude\", \"codex\" or \"command\"")
            if kind == "command" and not good.get("argv"):
                self.err(f"{where}: a command agent needs 'argv'")
            mode = good.get("review_mode")
            if mode is not None and mode not in ("repository", "provided_context"):
                self.err(f"{where}: 'review_mode' must be \"repository\" or \"provided_context\"")
            good["kind"] = kind
            wf.agents[name] = good
            words = set(good.get("extra_args", [])) | set(good.get("argv", []))
            if (good.get("sandbox") in BYPASS_SANDBOXES
                    or good.get("permission_mode") in BYPASS_PERMISSION_MODES
                    or words & BYPASS_ARGS):
                self.warn(f"agent profile '{name}' is configured to bypass its sandbox or "
                          "permissions")

    # -- git ---------------------------------------------------------------------------------

    def git(self, *args, stdin=None):
        cmd = ["git"]
        if self.wf.git_toplevel:
            # The owner pointed the runner at this root, so trust exactly this repository.
            cmd += ["-c", f"safe.directory={self.wf.git_toplevel}"]
        cmd += ["-C", self.wf.root, *args]
        return subprocess.run(cmd, input=stdin, capture_output=True)

    def check_root(self):
        wf = self.wf
        if not os.path.isdir(wf.root):
            self.err(f"root '{wf.root}' is not a directory")
            return
        top = wf.root
        while not os.path.exists(os.path.join(top, ".git")):
            parent = os.path.dirname(top)
            if parent == top:
                top = ""
                break
            top = parent
        wf.git_toplevel = top
        ok = False
        if top:
            try:
                res = self.git("rev-parse", "--is-inside-work-tree")
                ok = res.returncode == 0 and res.stdout.strip() == b"true"
                detail = res.stderr.decode(errors="replace").strip()
            except OSError as exc:
                detail = f"cannot run git: {exc}"
        else:
            detail = ""
        if not ok:
            wf.git_toplevel = ""
            self.err(f"root '{wf.root}' is not a git repository: snapshots, restores and commits "
                     "all need git" + (f" ({detail})" if detail else ""))
            return
        if os.path.realpath(top) != os.path.realpath(wf.root):
            self.warn(f"root '{wf.root}' is a subdirectory of the git repository at '{top}'; "
                      "snapshots and the clean-tree rule cover the whole repository")
        res = self.git("ls-files", "-z")
        if res.returncode == 0:
            self.tracked = set(p for p in res.stdout.decode(errors="surrogateescape").split("\0")
                               if p)

    # -- library -----------------------------------------------------------------------------

    def load_library(self, extra, label):
        wf = self.wf
        dirs = []
        for d in extra:
            full = os.path.normpath(os.path.join(self.base, d))
            if not os.path.isdir(full):
                self.err(f"{label}: library directory '{d}' not found (looked for {full})")
            else:
                dirs.append(full)
        dirs.append(BUILTIN_LIBRARY)
        wf.library_dirs = dirs
        for d in dirs:                       # earlier directories win
            self.load_dir(d, "types", TYPE_KEYS, wf.types)
            self.load_dir(d, "personas", PERSONA_KEYS, wf.personas)
        for name in sorted(wf.types):
            self.check_type(wf.types[name])
        codes = {}
        for name in sorted(wf.personas):
            p = wf.personas[name]
            where = p["_where"]
            for key in ("code", "title"):
                if not p.get(key):
                    self.err(f"{where}: '{key}' is required")
            code = p.get("code")
            if code:
                if not re.match(r"[A-Z][A-Z0-9]*\Z", code):
                    self.err(f"{where}: 'code' must be capital letters and digits, got '{code}'")
                if code in codes:
                    self.err(f"personas '{codes[code]}' and '{name}' both use code '{code}'")
                else:
                    codes[code] = name

    def load_dir(self, libdir, sub, allowed, into):
        folder = os.path.join(libdir, sub)
        if not os.path.isdir(folder):
            return
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".toml"):
                continue
            stem = fname[:-5]
            if stem in into:
                continue                     # shadowed by an earlier library directory
            where = os.path.join(folder, fname)
            try:
                with open(where, "rb") as fh:
                    raw = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                self.err(f"{where}: cannot load: {exc}")
                continue
            good = self.check_keys(raw, allowed, where)
            if good.get("name", stem) != stem:
                self.err(f"{where}: 'name' is '{good['name']}' but the file is '{fname}'")
            good["name"] = stem
            good["_where"] = where
            into[stem] = good

    def check_type(self, t):
        where = t["_where"]
        kind = t.get("kind")
        if kind not in ("produce", "review"):
            self.err(f"{where}: 'kind' must be \"produce\" or \"review\"; check and human tasks "
                     "need no type file")
        for cap in t.get("requires", []):
            if cap not in CAPABILITIES:
                self.err(f"{where}: 'requires' names unknown capability '{cap}'")
        params = {}
        for pname, spec in t.get("params", {}).items():
            if not isinstance(spec, dict):
                self.err(f"{where}: [params.{pname}] must be a table")
                continue
            spec = self.check_keys(spec, PARAM_KEYS, f"{where} [params.{pname}]")
            if spec.get("required") and "default" in spec:
                self.err(f"{where} [params.{pname}]: a required parameter cannot have a default")
            if not spec.get("required") and "default" not in spec:
                self.err(f"{where} [params.{pname}]: needs 'default', or 'required = true'")
            params[pname] = spec
        t["params"] = params
        if not t.get("prompt", "").strip():
            self.err(f"{where}: 'prompt' template is required")
        for name in PLACEHOLDER_RE.findall(t.get("prompt", "")):
            if name.startswith("param."):
                if name[6:] not in params:
                    self.err(f"{where}: template uses undeclared parameter '{{{name}}}'")
            elif name not in PLACEHOLDERS:
                self.err(f"{where}: template uses unknown placeholder '{{{name}}}'")
            elif name in REVIEW_ONLY_PLACEHOLDERS and kind == "produce":
                self.err(f"{where}: placeholder '{{{name}}}' is for review types only")
        rt = t.get("review_type")
        if rt:
            if kind != "produce":
                self.err(f"{where}: 'review_type' belongs on a produce type")
            elif rt not in self.wf.types:
                self.err(f"{where}: review_type '{rt}' not found in library")
            elif self.wf.types[rt].get("kind") != "review":
                self.err(f"{where}: review_type '{rt}' is not a review type")
        t["gate"] = self.gates(t.get("gate", []), where)

    # -- tasks -------------------------------------------------------------------------------

    def gates(self, raw, where):
        out = []
        if not isinstance(raw, list):
            self.err(f"{where}: 'gate' must be a list")
            return out
        for entry in raw:
            if isinstance(entry, str):
                gate = {"run": entry, "new": False, "fail_pattern": ""}
            elif isinstance(entry, dict):
                good = self.check_keys(entry, GATE_KEYS, f"{where}: gate")
                if "run" not in good:
                    self.err(f"{where}: a gate table needs 'run'")
                    continue
                gate = {"run": good["run"], "new": good.get("new", False),
                        "fail_pattern": good.get("fail_pattern", "")}
                if gate["fail_pattern"]:
                    if not gate["new"]:
                        self.err(f"{where}: 'fail_pattern' only applies to a gate marked "
                                 "'new = true'")
                    try:
                        re.compile(gate["fail_pattern"])
                    except re.error as exc:
                        self.err(f"{where}: 'fail_pattern' is not a valid regular expression: "
                                 f"{exc}")
            else:
                self.err(f"{where}: a gate must be a string or a table")
                continue
            if not gate["run"].strip():
                self.err(f"{where}: a gate command is empty")
                continue
            out.append(gate)
        return out

    def kind_of(self, type_name):
        if type_name in ("check", "human"):
            return type_name, None
        t = self.wf.types.get(type_name)
        if t is None:
            return None, None
        return t.get("kind"), t

    def resolve_tasks(self, raw_tasks):
        tasks, seen = [], set()
        for n, raw in enumerate(raw_tasks, 1):
            tid = raw.get("id")
            where = f"task '{tid}'" if isinstance(tid, str) and tid else f"task #{n}"
            if not isinstance(tid, str) or not tid:
                self.err(f"{where}: 'id' is required")
                tid = None
            elif not ID_RE.match(tid):
                self.err(f"{where}: malformed id; ids match [A-Za-z0-9][A-Za-z0-9_-]* "
                         "(a dot is reserved for generated panel ids)")
            elif tid in seen:
                self.err(f"{where}: duplicate id")
                tid = None
            type_name = raw.get("type")
            if not isinstance(type_name, str) or not type_name:
                self.err(f"{where}: 'type' is required")
                for key in raw:
                    if key not in ALL_TASK_KEYS:
                        self.err(f"{where}: unknown key '{key}'")
                continue
            kind, tdef = self.kind_of(type_name)
            if kind not in KINDS:
                if tdef is None:
                    self.err(f"{where}: type '{type_name}' not found in library")
                for key in raw:
                    if key not in ALL_TASK_KEYS:
                        self.err(f"{where}: unknown key '{key}'")
                continue
            for key in list(raw):
                if key not in ALL_TASK_KEYS:
                    self.err(f"{where}: unknown key '{key}'")
                elif key not in TASK_KEYS[kind]:
                    self.err(f"{where}: key '{key}' does not apply to a {kind} task")
            good = self.check_keys({k: v for k, v in raw.items() if k in TASK_KEYS[kind]},
                                   TASK_KEYS[kind], where)
            if tid is None:
                continue
            seen.add(tid)
            task = self.build(tid, kind, type_name, tdef, good, where, persona_entry=None)
            tasks.append(task)
            if kind == "produce":
                tasks.extend(self.expand_panel(task, tdef, raw.get("reviewers"), where))
        return tasks

    def setting(self, key, task, persona, tdef):
        """task, then persona, then type, then workflow [defaults], then built-in. '' is unset."""
        for source in (task, persona or {}, tdef or {}, self.given_defaults):
            value = source.get(key)
            if value is not None and value != "":
                return value
        return BUILTIN_DEFAULTS.get(key)

    def build(self, tid, kind, type_name, tdef, good, where, persona_entry):
        wf = self.wf
        task = {
            "id": tid, "kind": kind, "type": type_name, "title": good.get("title") or tid,
            "generated": False, "needs": list(good.get("needs", [])),
            "reviews": None, "verifies": None,
        }
        if len(set(task["needs"])) != len(task["needs"]):
            self.err(f"{where}: 'needs' lists a task twice")
        if tid in task["needs"]:
            self.err(f"{where}: a task cannot need itself")

        persona = None
        if kind == "review":
            pname = good.get("perspective")
            if not pname:
                self.err(f"{where}: a review task needs 'perspective'")
            elif pname not in wf.personas:
                self.err(f"{where}: persona '{pname}' not found in library")
            else:
                persona = wf.personas[pname]
            task["perspective"] = pname
            task["persona_code"] = (persona or {}).get("code")
            task["reviews"] = good.get("reviews")
            if not task["reviews"]:
                self.err(f"{where}: a review task needs 'reviews'")
            advisory = good.get("advisory")
            if advisory is None:
                advisory = bool((persona or {}).get("advisory", False))
            task["advisory"] = advisory

        if kind in ("produce", "review"):
            if "prompt" in good and "prompt_file" in good:
                self.err(f"{where}: 'prompt' and 'prompt_file' are both set; give one")
            task["prompt"] = good.get("prompt", "")
            task["prompt_file"] = None
            if "prompt_file" in good:
                full = os.path.normpath(os.path.join(self.base, good["prompt_file"]))
                task["prompt_file"] = full
                if not os.path.isfile(full):
                    self.err(f"{where}: prompt_file '{good['prompt_file']}' not found "
                             f"(looked for {full})")
            agent = self.setting("agent", good, persona, tdef)
            if agent not in wf.agents:
                self.err(f"{where}: agent '{agent}' is not defined; built in are "
                         f"{', '.join(BUILTIN_AGENTS)}, others need an [agents.{agent}] table")
            task["agent"] = agent
            alternatives = good.get("fallback_agents", [])
            if alternatives:
                task["fallback_agents"] = alternatives
            if len(set([agent] + alternatives)) != len([agent] + alternatives):
                self.err(f"{where}: fallback_agents must be unique and exclude the primary agent")
            for alternative in alternatives:
                if alternative not in wf.agents:
                    self.err(f"{where}: fallback agent '{alternative}' is not defined")
            task["model"] = self.setting("model", good, persona, tdef) or ""
            complexity = self.setting('complexity', good, persona, tdef) or 'standard'
            if complexity not in ('mechanical', 'standard', 'high'):
                self.err(f"{where}: complexity must be mechanical, standard, or high")
            if wf.model_policy or self.setting('complexity', good, persona, tdef):
                task['complexity'] = complexity
            models = wf.model_policy.get(complexity, {})
            chosen = {}
            for name in [agent] + alternatives:
                profile = wf.agents.get(name, {})
                explicit_model = next((source['model'] for source in (good, persona or {}, tdef or {})
                                       if source.get('model')), '') if name == agent else ''
                model = (explicit_model or models.get(profile.get('kind'), '')
                         or (task['model'] if name == agent else '') or profile.get('model', ''))
                if models or alternatives:
                    chosen[name] = model
                if name != agent and profile.get('kind') != 'command' and not model:
                    self.err(f"{where}: fallback agent '{name}' needs a profile model or complexity model mapping")
                if name != agent:
                    primary = wf.agents.get(agent, {})
                    def bypass(p):
                        return (p.get('sandbox') in BYPASS_SANDBOXES
                                or p.get('permission_mode') in BYPASS_PERMISSION_MODES
                                or bool(set(p.get('extra_args', []) + p.get('argv', [])) & BYPASS_ARGS))
                    if bypass(profile) and not bypass(primary):
                        self.err(f"{where}: fallback '{name}' may not widen permission controls")
                    if profile.get('review_mode', 'repository') != primary.get('review_mode', 'repository'):
                        self.err(f"{where}: fallback '{name}' must preserve review_mode")
            if chosen:
                task['provider_models'] = chosen
            task["timeout_min"] = self.setting("timeout_min", good, None, tdef)
            task["budget_usd"] = self.setting("budget_usd", good, None, tdef)
            task["recheck_passed"] = self.setting("recheck_passed", good, None, None)
            if task["recheck_passed"] not in ("diff", "never"):
                self.err(f"{where}: 'recheck_passed' must be \"diff\" or \"never\"")
            task["requires"] = list((tdef or {}).get("requires", []))
            task["needs_run_dir"] = bool((tdef or {}).get("needs_run_dir", False))
            task["params"] = self.params(good.get("params", {}), tdef or {}, where)
        elif good.get("params"):
            self.err(f"{where}: a {kind} task has no type parameters")

        if kind == "produce":
            task["max_attempts"] = self.setting("max_attempts", good, None, tdef)
            if task["max_attempts"] < 1:
                self.err(f"{where}: 'max_attempts' must be at least 1")
            task["outputs"] = self.outputs(good.get("outputs"), where)
            paths = [o["path"] for o in task["outputs"]]
            task["writes"] = list(good["writes"]) if "writes" in good else list(paths)
            task["removes"] = list(good.get("removes", []))
            task["gates"] = (self.gates(good["gate"], where) if "gate" in good
                             else [dict(g) for g in (tdef or {}).get("gate", [])])
            task["gate_timeout_min"] = wf.defaults["gate_timeout_min"]
            task["review_type"] = (tdef or {}).get("review_type") or None
            task["reviewers"] = []
        if kind in ("check", "human"):
            task["verifies"] = good.get("verifies")
        if kind == "check":
            task["run"] = list(good.get("run", []))
            if not [c for c in task["run"] if c.strip()]:
                self.err(f"{where}: a check needs 'run'")
            task["read_only"] = good.get("read_only", False)
            task["restores"] = good.get("restores", False)
            if task["read_only"] and task["restores"]:
                self.err(f"{where}: 'read_only' and 'restores' cannot both be true")
            task["gate_timeout_min"] = wf.defaults["gate_timeout_min"]

        # `protected` is a union of every level and can never be narrowed (B9)
        protected = []
        for source in (BUILTIN_PROTECTED, wf.defaults["protected"],
                       (tdef or {}).get("protected", []), good.get("protected", [])):
            for p in source:
                if p not in protected:
                    protected.append(p)
        task["protected"] = protected
        task["_own_protected"] = list((tdef or {}).get("protected", [])) + \
            list(good.get("protected", []))
        return task

    def params(self, given, tdef, where):
        declared = tdef.get("params", {})
        out = {}
        for name in given:
            if name not in declared:
                self.err(f"{where}: type '{tdef.get('name')}' has no parameter '{name}'")
        for name, spec in declared.items():
            if name in given:
                out[name] = given[name]
            elif spec.get("required"):
                self.err(f"{where}: missing required parameter '{name}' of type "
                         f"'{tdef.get('name')}'")
            else:
                out[name] = spec.get("default")
        return out

    def outputs(self, raw, where):
        out = []
        if not isinstance(raw, list) or not raw:
            self.err(f"{where}: a produce task needs 'outputs'")
            return out
        for entry in raw:
            if isinstance(entry, str):
                out.append({"path": entry, "may_be_empty": False})
            elif isinstance(entry, dict):
                good = self.check_keys(entry, OUTPUT_KEYS, f"{where}: output")
                if "path" not in good:
                    self.err(f"{where}: an output table needs 'path'")
                    continue
                out.append({"path": good["path"], "may_be_empty": good.get("may_be_empty", False)})
            else:
                self.err(f"{where}: an output must be a string or a table")
        return out

    def expand_panel(self, producer, tdef, raw, where):
        members = []
        if raw is None:
            return members
        if not isinstance(raw, list):
            self.err(f"{where}: 'reviewers' must be a list")
            return members
        seen = set()
        for entry in raw:
            if isinstance(entry, str):
                entry = {"perspective": entry}
            elif not isinstance(entry, dict):
                self.err(f"{where}: a reviewer must be a persona name or a table")
                continue
            ewhere = f"{where}: reviewer '{entry.get('perspective', '?')}'"
            good = self.check_keys(entry, PANEL_ENTRY_KEYS, ewhere)
            pname = good.get("perspective")
            if not pname:
                self.err(f"{where}: a reviewer table needs 'perspective'")
                continue
            if pname in seen:
                self.err(f"{where}: perspective '{pname}' is listed twice in 'reviewers'")
                continue
            seen.add(pname)
            rtype = good.get("type") or (tdef or {}).get("review_type")
            if not rtype:
                self.err(f"{where}: 'reviewers' is set but type '{producer['type']}' names no "
                         f"'review_type', and reviewer '{pname}' gives no 'type'")
                continue
            kind, rdef = self.kind_of(rtype)
            if kind != "review":
                if rdef is None and rtype not in ("check", "human"):
                    self.err(f"{ewhere}: type '{rtype}' not found in library")
                else:
                    self.err(f"{ewhere}: type '{rtype}' is not a review type")
                continue
            if not re.match(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z", pname):
                self.err(f"{ewhere}: malformed persona name")
                continue
            rid = f"{producer['id']}.review.{pname}"
            fields = {k: v for k, v in good.items() if k != "type"}
            fields["reviews"] = producer["id"]
            if "recheck_passed" not in fields:
                fields["recheck_passed"] = producer["recheck_passed"]
            member = self.build(rid, "review", rtype, rdef, fields, f"task '{rid}'", None)
            member["generated"] = True
            member["title"] = f"{self.wf.personas.get(pname, {}).get('title', pname)} review of " \
                              f"{producer['id']}"
            members.append(member)
            producer["reviewers"].append(rid)
        return members

    # -- validation --------------------------------------------------------------------------

    def check_patterns(self, tasks, workflow_protected, label):
        for p in workflow_protected:
            for problem in patterns.validate_pattern(p):
                self.err(f"{label} [defaults]: protected pattern '{p}' {problem}")
        for name, t in sorted(self.wf.types.items()):
            for p in t.get("protected", []):
                for problem in patterns.validate_pattern(p):
                    self.err(f"{t['_where']}: protected pattern '{p}' {problem}")
        for t in tasks:
            sets = [("protected", t.pop("_own_protected", []))]
            if t["kind"] == "produce":
                sets += [("outputs", [o["path"] for o in t["outputs"]]),
                         ("writes", t["writes"]), ("removes", t["removes"])]
            bad = set()
            for key, plist in sets:
                for p in plist:
                    problems = patterns.validate_pattern(p)
                    for problem in problems:
                        self.err(f"task '{t['id']}': {key} pattern '{p}' {problem}")
                    if problems:
                        bad.add(p)
                    elif key != "protected" and set(p.split("/")) & {".git", ".runs"}:
                        self.err(f"task '{t['id']}': {key} path '{p}' is under .git or .runs, "
                                 "which no task may touch")
                        bad.add(p)
            t["_bad_patterns"] = bad

    def check_references(self, tasks):
        by_id = {t["id"]: t for t in tasks}
        for t in tasks:
            where = f"task '{t['id']}'"
            for n in t["needs"]:
                if n not in by_id:
                    self.err(f"{where}: 'needs' names unknown task '{n}'")
            for key in ("reviews", "verifies"):
                target = t.get(key)
                if not target:
                    continue
                if target not in by_id:
                    self.err(f"{where}: '{key}' names unknown task '{target}'")
                elif by_id[target]["kind"] != "produce":
                    self.err(f"{where}: '{key}' must name a produce task; '{target}' is a "
                             f"{by_id[target]['kind']} task")
                elif target == t["id"]:
                    self.err(f"{where}: '{key}' names itself")
        for producer in (t for t in tasks if t["kind"] == "produce"):
            seen = {}
            for r in tasks:
                if r["kind"] == "review" and r.get("reviews") == producer["id"] \
                        and r.get("perspective"):
                    if r["perspective"] in seen:
                        self.err(f"task '{producer['id']}': perspective '{r['perspective']}' "
                                 f"reviews it twice ('{seen[r['perspective']]}' and '{r['id']}')")
                    else:
                        seen[r["perspective"]] = r["id"]

    def check_verifiers(self, tasks):
        for p in (t for t in tasks if t["kind"] == "produce"):
            if p["gates"]:
                continue
            verifiers = [t for t in tasks
                         if t.get("reviews") == p["id"] or t.get("verifies") == p["id"]]
            if any(v["kind"] != "review" or not v.get("advisory") for v in verifiers):
                continue
            if verifiers:
                self.err(f"task '{p['id']}': its whole panel is advisory and it has no other "
                         "verifier; an advisory review cannot accept work")
            else:
                self.err(f"task '{p['id']}' has no gate, check, review or human verifier")

    def check_paths(self, tasks):
        for t in (t for t in tasks if t["kind"] == "produce"):
            bad = t["_bad_patterns"]
            writes = [w for w in t["writes"] if w not in bad]
            for o in t["outputs"]:
                path = o["path"]
                if path in bad:
                    continue
                if not patterns.covered_by(path, writes):
                    self.err(f"task '{t['id']}': output '{path}' is not covered by its 'writes'; "
                             "repeat the entry in 'writes'")
                for r in t["removes"]:
                    if r in bad:
                        continue
                    # a glob output beside a literal `removes` inside it is satisfiable
                    if r == path or (not patterns.has_wildcard(path) and patterns.matches(r, path)):
                        self.err(f"task '{t['id']}': '{path}' is in 'outputs' (must exist) and "
                                 f"matched by 'removes' entry '{r}' (must not exist)")
            for r in t["removes"]:
                if r not in bad and not patterns.covered_by(r, writes):
                    self.err(f"task '{t['id']}': removes path '{r}' is not covered by its "
                             "'writes'; a deletion is a change, and would be reverted")

    def check_cycles(self, tasks):
        """Needs cycles first; then cycles in the acceptance graph (A8). True if any."""
        by_id = {t["id"]: t for t in tasks}
        needs = {t["id"]: [n for n in t["needs"] if n in by_id and n != t["id"]] for t in tasks}
        cycle = _find_cycle(list(needs), lambda n: needs[n])
        if cycle:
            # printed in dependency direction: a needs b needs a
            self.err("dependency cycle: " + " -> ".join(cycle))
            return True
        graph = _milestone_graph(tasks)
        cycle = _find_cycle(list(graph), lambda n: graph[n])
        if not cycle:
            return False
        ids = []
        for node in cycle:
            if not ids or ids[-1] != node[0]:
                ids.append(node[0])
        if len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        producer = next((n[0] for n in cycle if n[1] == "accepted"), ids[0])
        k = ids.index(producer)
        ring = ids[k:] + ids[:k]
        ring.append(ring[0])
        reasons = []
        for t in tasks:
            target = t.get("reviews") or t.get("verifies")
            if target == producer and t["id"] in ring:
                verb = "reviews" if t.get("reviews") else "verifies"
                if producer in t["needs"]:
                    reasons.append(f"'{t['id']}' {verb} '{producer}' and also needs it")
                else:
                    reasons.append(f"'{t['id']}' {verb} '{producer}' but needs work downstream "
                                   "of it")
        self.err(f"acceptance cycle: {' -> '.join(ring)}: " + "; ".join(reasons)
                 + f": '{producer}' can never be accepted")
        return True

    def check_writers(self, tasks):
        by_id = {t["id"]: t for t in tasks}
        closure = {}

        def upstream(tid):
            if tid not in closure:
                closure[tid] = set()
                for n in by_id[tid]["needs"]:
                    if n in by_id:
                        closure[tid].add(n)
                        closure[tid] |= upstream(n)
            return closure[tid]

        producers = [t for t in tasks if t["kind"] == "produce"]
        for i, a in enumerate(producers):
            for b in producers[i + 1:]:
                if a["id"] in upstream(b["id"]):
                    first, later = a, b
                elif b["id"] in upstream(a["id"]):
                    first, later = b, a
                else:
                    first = later = None
                shared = self.overlaps(a["writes"], b["writes"], a, b)
                if not shared:
                    continue
                if first is None:
                    self.err(f"'{b['id']}' and '{a['id']}' both write {', '.join(shared)} and "
                             "neither depends on the other")
                    continue
                claimed = self.overlaps([o["path"] for o in first["outputs"]], later["writes"],
                                        first, later)
                if claimed:
                    consumers = [t["id"] for t in tasks
                                 if first["id"] in t["needs"] and t["id"] != later["id"]]
                    self.wf.claims.append({"task": later["id"], "of": first["id"],
                                           "paths": claimed, "consumers": consumers})
                    self.warn(f"'{later['id']}' will modify outputs of accepted task "
                              f"'{first['id']}': {', '.join(claimed)}. Accepted consumers of it: "
                              + (", ".join(consumers) if consumers else "none"))

    def overlaps(self, left, right, a, b):
        shared = []
        bad = a["_bad_patterns"] | b["_bad_patterns"]
        for x in left:
            for y in right:
                if x in bad or y in bad:
                    continue
                if patterns.may_overlap(x, y):
                    label = x if x == y else f"{x} / {y}"
                    if label not in shared:
                        shared.append(label)
        return shared

    def protect_executed_files(self, tasks):
        """Files a gate or check executes are protected by default (B9)."""
        if self.tracked is None:
            return
        by_id = {t["id"]: t for t in tasks}
        for t in tasks:
            if t["kind"] == "produce":
                commands, guarded = [g["run"] for g in t["gates"]], [t]
            elif t["kind"] == "check":
                commands = t["run"]
                guarded = [t] + ([by_id[t["verifies"]]] if t.get("verifies") in by_id else [])
            else:
                continue
            for cmd in commands:
                try:
                    words = shlex.split(cmd)
                except ValueError:
                    self.err(f"task '{t['id']}': command cannot be parsed: {cmd}")
                    continue
                for word in words:
                    path = os.path.normpath(word).replace(os.sep, "/")
                    if path not in self.tracked:
                        continue
                    for g in guarded:
                        if path in g.get("writes", []):
                            self.warn(f"task '{g['id']}' lists '{path}' in 'writes', and "
                                      f"'{t['id']}' executes it: the task may edit a file its own "
                                      "verifier executes")
                        elif path not in g["protected"]:
                            g["protected"].append(path)

    def check_ignored(self, tasks):
        if not self.wf.git_toplevel:
            for t in tasks:
                t.pop("_bad_patterns", None)
            return
        probes = {}
        for t in tasks:
            bad = t.pop("_bad_patterns", set())
            if t["kind"] != "produce":
                continue
            declared = [("output", o["path"]) for o in t["outputs"]] + \
                [("writes path", w) for w in t["writes"]] + [("removes path", r) for r in t["removes"]]
            for key, p in declared:
                if p in bad:
                    continue
                if patterns.has_wildcard(p):
                    prefix = "/".join(patterns.literal_prefix(p))
                    if not prefix:
                        continue
                    probe = prefix + "/__task_runner_probe__"
                else:
                    probe = p
                probes.setdefault(probe, []).append((t["id"], key, p))
        if not probes:
            return
        res = self.git("check-ignore", "-v", "-z", "--stdin",
                       stdin="\0".join(probes).encode() + b"\0")
        if res.returncode not in (0, 1):
            self.err("git check-ignore failed: " + res.stderr.decode(errors="replace").strip())
            return
        fields = res.stdout.decode(errors="replace").split("\0")
        reported = set()
        for i in range(0, len(fields) - 3, 4):
            source, line, rule, path = fields[i:i + 4]
            for tid, key, p in probes.get(path, []):
                if (tid, p) in reported:
                    continue
                reported.add((tid, p))
                self.err(f"'{tid}' {key} {p} is ignored by {source}:{line} '{rule}'; ignored "
                         "work is invisible to snapshots, reviewers and commits")

    # -- order -------------------------------------------------------------------------------

    def order(self, tasks, has_cycle):
        """Topological over the milestone graph; ties broken by position in the workflow."""
        if has_cycle:
            return tasks
        index = {t["id"]: n for n, t in enumerate(tasks)}
        graph = _milestone_graph(tasks)            # node -> nodes that must come after it
        waiting = {n: 0 for n in graph}
        for n, after in graph.items():
            for m in after:
                waiting[m] += 1
        rank = {"candidate": 0, "done": 0, "accepted": 1}
        heap = [(index[n[0]], rank[n[1]], n) for n, c in waiting.items() if c == 0]
        heapq.heapify(heap)
        out = []
        while heap:
            _, _, node = heapq.heappop(heap)
            if node[1] != "accepted":
                out.append(tasks[index[node[0]]])
            for m in graph[node]:
                waiting[m] -= 1
                if waiting[m] == 0:
                    heapq.heappush(heap, (index[m[0]], rank[m[1]], m))
        return out


def _milestone_graph(tasks):
    """The expanded acceptance graph (A8). Edges point from what comes first to what follows.

    A producer has a candidate and an accepted milestone. `needs` waits for accepted;
    `reviews` and `verifies` wait for the candidate; accepted waits for every verifier.
    """
    by_id = {t["id"]: t for t in tasks}

    def start(t):
        return (t["id"], "candidate" if t["kind"] == "produce" else "done")

    def end(t):
        return (t["id"], "accepted" if t["kind"] == "produce" else "done")

    graph = {}
    for t in tasks:
        graph.setdefault(start(t), [])
        if t["kind"] == "produce":
            graph.setdefault(end(t), [])
            graph[start(t)].append(end(t))
    for t in tasks:
        for n in t["needs"]:
            if n in by_id and n != t["id"]:
                graph[end(by_id[n])].append(start(t))
        target = t.get("reviews") or t.get("verifies")
        if target in by_id and by_id[target]["kind"] == "produce" and target != t["id"]:
            graph[start(by_id[target])].append(start(t))
            graph[end(t)].append(end(by_id[target]))
    return graph


def _find_cycle(nodes, successors):
    """Return one cycle as [a, b, ..., a], or None. Deterministic: follows the given order."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in nodes}
    for root in nodes:
        if colour[root] != WHITE:
            continue
        stack = [(root, iter(successors(root)))]
        path = [root]
        colour[root] = GREY
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = BLACK
                stack.pop()
                path.pop()
            elif colour[nxt] == GREY:
                return path[path.index(nxt):] + [nxt]
            elif colour[nxt] == WHITE:
                colour[nxt] = GREY
                path.append(nxt)
                stack.append((nxt, iter(successors(nxt))))
    return None
