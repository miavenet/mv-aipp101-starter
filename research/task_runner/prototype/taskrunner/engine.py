"""The runner. Each task goes implement -> gate -> review -> (human) -> commit.

What is fixed: the order of tasks, the path through the phases, what counts as passing (exit codes
and a structured review verdict), and the state on disk. What is not fixed is the agent's work, so
that is bounded by attempts, time and money. State is saved after every phase; to resume, run again.
"""

import hashlib
import json
import os
import re
import subprocess
import time

from . import agents as agents_mod
from .gitops import Git, protected_hits

DONE, MORE, ERROR, HUMAN = 0, 1, 2, 255

IMPLEMENT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["outcome", "notes"],
    "properties": {"outcome": {"type": "string", "enum": ["done", "blocked"]},
                   "notes": {"type": "string"}}}
REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["approved", "reasons"],
    "properties": {"approved": {"type": "boolean"},
                   "reasons": {"type": "array", "items": {"type": "string"}}}}
TAIL = 4000


def _volatile(text):
    """Strip timings so the same failure hashes the same twice."""
    return re.sub(r"\d+(\.\d+)?\s*(ms|s|sec|seconds)\b", "<t>", text)


class Runner:
    def __init__(self, plan, make_agent=agents_mod.make, log=lambda m: print(m, flush=True)):
        self.plan, self.make_agent, self.log = plan, make_agent, log
        self.dir = os.path.join(plan.root, ".runner", plan.name)
        self.state_path = os.path.join(self.dir, "state.json")
        self.git = Git(plan.root)
        os.makedirs(self.dir, exist_ok=True)
        ignore = os.path.join(plan.root, ".runner", ".gitignore")
        if not os.path.exists(ignore):
            with open(ignore, "w") as f:
                f.write("*\n")
        self.state = self._load()

    # ---- state -------------------------------------------------------------------------------
    def _load(self):
        try:
            with open(self.state_path) as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {"tasks": {}, "cost_usd": 0.0, "started": False}
        for t in self.plan.tasks:
            state["tasks"].setdefault(t.id, {"status": "pending", "phase": "implement", "attempt": 0,
                                             "cost_usd": 0.0, "tokens": {"in": 0, "out": 0}, "seconds": 0.0})
        return state

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.state_path)

    def event(self, task_id, what, **more):
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task_id, "event": what, **more}
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, "events.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
        detail = " ".join(f"{k}={v}" for k, v in more.items() if k != "detail")
        self.log(f"[{rec['ts'][11:]}] {task_id}: {what} {detail}".rstrip())

    # ---- scheduling --------------------------------------------------------------------------
    def current(self):
        """The first task in plan order that is not done. None when everything is done."""
        for t in self.plan.tasks:
            if self.state["tasks"][t.id]["status"] != "done":
                return t
        return None

    def run(self):
        while True:
            code = self.next()
            if code != MORE:
                return code

    def next(self):
        """Advance one phase of one task. Returns DONE, MORE, ERROR or HUMAN."""
        task = self.current()
        if task is None:
            return DONE
        st = self.state["tasks"][task.id]
        if st["status"] in ("failed", "blocked"):
            self.log(f"{task.id} is {st['status']}: {st.get('reason', '')}\n"
                     f"Fix the cause, then: runner retry {task.id}")
            return HUMAN if st["status"] == "blocked" else ERROR
        if st["status"] == "awaiting_human":
            self.log(f"{task.id} passed its gate and review and waits for a person. "
                     f"Inspect the work tree, then: runner approve {task.id}")
            return HUMAN
        if not self.state["started"]:
            problem = self._start_run()
            if problem:
                self.log(problem)
                return ERROR
        if st["status"] == "pending":
            st.update(status="running", phase="implement")
            if self.git.ok:
                st["base"] = self.git.snapshot()
            self.event(task.id, "start", title=task.title)
        code = getattr(self, "_" + st["phase"])(task, st)
        self.save()
        return code

    def _start_run(self):
        if self.git.ok:
            if self.git.dirty() and not self.plan.defaults["allow_dirty"]:
                return ("The work tree has uncommitted changes, so a task's changes could not be told apart "
                        "from yours. Commit or stash them, or set allow_dirty = true under [defaults].")
            if self.plan.defaults["branch"]:
                self.git.switch(self.plan.defaults["branch"])
        else:
            self.log("warning: not a git repository. Commits, protected files and review diffs are off.")
        self.state["started"] = True
        self.save()
        return None

    def _fail(self, task, st, reason, status="failed"):
        st.update(status=status, reason=reason)
        self.event(task.id, status, reason=reason)
        return HUMAN if status == "blocked" else ERROR

    # ---- phases ------------------------------------------------------------------------------
    def _call(self, task, st, agent_name, role, prompt, **kw):
        if self.state["cost_usd"] >= self.plan.defaults["run_budget_usd"]:
            return None, f"run budget of ${self.plan.defaults['run_budget_usd']} is spent"
        try:
            agent = self.make_agent(agent_name, self.plan.agents)
        except ValueError as e:
            return None, str(e)
        log_dir = os.path.join(self.dir, task.id, f"attempt-{st['attempt']}", role)
        r = agent.run(prompt, cwd=self.plan.root, log_dir=log_dir, timeout_s=task.timeout_min * 60,
                      budget_usd=task.budget_usd, **kw)
        st["cost_usd"] = round(st["cost_usd"] + (r.cost_usd or 0), 4)
        self.state["cost_usd"] = round(self.state["cost_usd"] + (r.cost_usd or 0), 4)
        st["seconds"] = round(st["seconds"] + r.seconds, 1)
        for k in ("in", "out"):
            st["tokens"][k] += r.tokens.get(k, 0)
        self.event(task.id, role, agent=agent_name, ok=r.ok, seconds=r.seconds,
                   cost=r.cost_usd if r.cost_usd is not None else "n/a")
        return r, ""

    def _implement(self, task, st):
        if st["attempt"] >= task.max_attempts:
            return self._fail(task, st, f"no passing result in {task.max_attempts} attempts. "
                                        f"Last problem: {st.get('feedback', '')[-600:]}")
        st["attempt"] += 1
        resumed = bool(st.get("session_id"))
        r, problem = self._call(task, st, task.agent, "implement", self._implement_prompt(task, st, resumed),
                                schema=IMPLEMENT_SCHEMA, session_id=st.get("session_id"), model=task.model)
        if r is None:
            st["attempt"] -= 1
            return self._fail(task, st, problem)
        if not r.ok:
            # A broken or timed-out session is not continued: the next attempt starts clean.
            st["session_id"] = None
            st["feedback"] = f"The previous agent run ended with an error: {r.error}"
            return MORE
        st["session_id"] = r.session_id
        if (r.structured or {}).get("outcome") == "blocked":
            return self._fail(task, st, "agent reports it is blocked: " + str(r.structured.get("notes", "")), "blocked")
        st["notes"] = str((r.structured or {}).get("notes", ""))[:2000]
        if self.git.ok and task.protected:
            hits = protected_hits(self.git.changed(st["base"], self.git.snapshot()), task.protected)
            if hits:
                self.git.restore(st["base"], hits)
                st["feedback"] = ("You changed protected files, and the runner has put them back: "
                                  + ", ".join(hits) + ". Solve the task without touching them.")
                self.event(task.id, "protected-files-restored", files=",".join(hits))
                return MORE
        st["phase"] = "gate"
        return MORE

    def _gate(self, task, st):
        log_path = os.path.join(self.dir, task.id, f"attempt-{st['attempt']}", "gate.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        failed = ""
        with open(log_path, "w") as log:
            for cmd in task.gate:
                try:
                    p = subprocess.run(cmd, shell=True, cwd=self.plan.root, capture_output=True, text=True,
                                       timeout=task.gate_timeout_min * 60)
                    code, out = p.returncode, p.stdout + p.stderr
                except subprocess.TimeoutExpired as e:
                    code, out = 124, f"{e.stdout or ''}\n[gate command timed out after {task.gate_timeout_min} min]"
                log.write(f"$ {cmd}\n{out}\n[exit {code}]\n\n")
                if code != 0:
                    failed = f"$ {cmd}\n[exit {code}]\n{out[-TAIL:]}"
                    break
        self.event(task.id, "gate", passed=not failed, attempt=st["attempt"])
        if not failed:
            st["last_gate_hash"] = None
            st["phase"] = "review" if task.review else ("human" if task.human_review else "commit")
            return MORE
        digest = hashlib.sha256(_volatile(failed).encode()).hexdigest()
        if digest == st.get("last_gate_hash"):
            return self._fail(task, st, "no progress: the gate failed twice running with the same output. "
                                        f"See {os.path.relpath(log_path, self.plan.root)}")
        st.update(last_gate_hash=digest, phase="implement",
                  feedback="The acceptance check failed. Output:\n" + failed)
        return MORE

    def _review(self, task, st):
        before = self.git.snapshot() if self.git.ok else None
        r, problem = self._call(task, st, task.reviewer or task.agent, "review", self._review_prompt(task, st, before),
                                schema=REVIEW_SCHEMA, model=task.review_model, read_only=True)
        if r is None:
            return self._fail(task, st, problem)
        if self.git.ok and self.git.snapshot() != before:
            return self._fail(task, st, "the reviewer changed the work tree, so its verdict and the gate result no "
                                        "longer describe the same code. Inspect the tree before retrying")
        verdict = r.structured if r.ok else None
        if not isinstance(verdict, dict) or not isinstance(verdict.get("approved"), bool):
            st["review_errors"] = st.get("review_errors", 0) + 1
            if st["review_errors"] >= 2:
                return self._fail(task, st, f"the reviewer gave no usable verdict twice. Last error: {r.error}")
            return MORE                               # try the review once more; nothing counts as approval
        self.event(task.id, "verdict", approved=verdict["approved"])
        if verdict["approved"]:
            st["phase"] = "human" if task.human_review else "commit"
            return MORE
        reasons = "\n".join(f"- {x}" for x in verdict.get("reasons") or ["(no reasons given)"])
        st.update(phase="implement", feedback="The checks passed, but an independent reviewer rejected the change:\n"
                                              + reasons)
        return MORE

    def _human(self, task, st):
        st["status"] = "awaiting_human"
        self.event(task.id, "awaiting-human")
        self.log(f"Inspect the work tree, then: runner approve {task.id}")
        return HUMAN

    def _commit(self, task, st):
        sha = ""
        if self.git.ok and task.commit:
            paths = self.git.changed(st["base"], self.git.snapshot())
            if paths:
                msg = f"{task.title}\n\nTask {task.id} of plan {self.plan.name}, by {task.agent}, attempt {st['attempt']}."
                if task.commit_trailer:
                    msg += "\n\n" + task.commit_trailer
                sha = self.git.commit(paths, msg)
        st.update(status="done", phase="done", commit=sha)
        self.event(task.id, "done", commit=sha or "none", attempts=st["attempt"], cost=st["cost_usd"])
        return MORE

    # ---- prompts -----------------------------------------------------------------------------
    def _implement_prompt(self, task, st, resumed):
        feedback = st.get("feedback", "")
        if resumed and feedback:                      # same session: it already has the task, send only what is new
            return (f"{feedback}\n\nFix this and finish the task. The same rules apply. "
                    f"This is attempt {st['attempt']} of {task.max_attempts}.")
        gates = "\n".join(f"    {c}" for c in task.gate)
        rules = ["Work only inside this repository. Do not commit, push or switch branches: the runner commits.",
                 "The task is accepted only if the acceptance commands exit 0 and an independent reviewer approves "
                 "the diff. Your own report does not count.",
                 "Never make a check pass by weakening, deleting or skipping a test, or by special-casing its "
                 "inputs. If the task cannot be done properly, answer with outcome \"blocked\" and say why."]
        if task.protected:
            rules.append("Do not change these files. The runner reverts any change to them: " + ", ".join(task.protected))
        text = (f"You are carrying out one task from a task list, unattended. Nobody can answer questions.\n\n"
                f"# Task {task.id}: {task.title}\n\n{task.prompt}\n\n# Acceptance commands\n\n{gates}\n\n# Rules\n\n"
                + "\n".join(f"- {r}" for r in rules))
        if feedback:
            text += f"\n\n# What went wrong last time (attempt {st['attempt'] - 1})\n\n{feedback}"
        return text

    def _review_prompt(self, task, st, now):
        diff = self.git.diff(st["base"], now) if self.git.ok else "(no git repository: read the files directly)"
        return (f"Review a change made by another agent for the task below. Do not modify any file.\n\n"
                f"# Task {task.id}: {task.title}\n\n{task.prompt}\n\n"
                f"# Context\n\nThe acceptance commands already pass:\n" + "\n".join(f"    {c}" for c in task.gate) +
                f"\n\n# What to check\n\n- The change does what the task asks, fully, and nothing unrelated.\n"
                f"- Tests were not weakened, deleted or skipped, and no input is special-cased to satisfy a test.\n"
                f"- No obvious defect a careful engineer would stop.\n\n"
                f"Approve only if all three hold. Give concrete reasons when you reject.\n\n# Diff\n\n{diff}")
