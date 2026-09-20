"""Commands, exit codes, printing. Exit 0: fine. 2: something is wrong. 255: a person is needed."""

import argparse
import math
import os
import sys
import signal
from types import SimpleNamespace
import uuid

from . import __version__, engine, gitops, record, workflow, qualification, preflight, agents, replan

EXIT_OK, EXIT_FAILED, EXIT_HUMAN = 0, 2, 255



def main(argv=None):
    previous = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        return _main(argv)
    except KeyboardInterrupt:
        return fail("interrupted; child processes stopped. Continue with runner resume")
    except (record.RecordError, gitops.GitError, gitops.RevertConflict, agents.InvocationError) as exc:
        return fail(str(exc))
    finally:
        signal.signal(signal.SIGTERM, previous)


def _main(argv=None):
    parser = argparse.ArgumentParser(prog="runner", description="Run a workflow of tasks to "
                                     "completion with headless coding agents.")
    parser.add_argument("--version", action="version", version=f"runner {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("validate", help="check everything; print the expanded DAG in execution "
                       "order")
    p.add_argument("workflow")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("graph", help="write the DAG as Graphviz DOT")
    p.add_argument("workflow")
    p.add_argument("-o", "--output", metavar="FILE")
    p.set_defaults(func=cmd_graph)

    p = sub.add_parser("doctor", help="qualify the workflow's agent profiles in scratch repositories")
    p.add_argument("workflow")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("check-gates", help="test every gate/check on disposable copies of the untouched tree")
    p.add_argument("workflow")
    p.set_defaults(func=cmd_check_gates)

    p = sub.add_parser("start", help="create a run and execute it")
    p.add_argument("workflow")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("status", help="print STATUS.md; --rebuild regenerates all derived files")
    p.add_argument("run", nargs="?", default="latest", help="a directory name, a UUID prefix, "
                   "or 'latest'")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("-C", dest="where", default=".", metavar="DIR", help="a directory inside the "
                   "repository (default: the current one)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("runs", help="list runs with status, cost and date")
    p.add_argument("workflow", help="a workflow file, or the name of a workflow")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("prune", help="delete the pinned refs of finished or deleted runs")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("resume", help="reconcile, then continue a run (default: the latest "
                       "unfinished one)")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--stop-orphans", action="store_true", help="stop an agent that a dead runner "
                   "left running, instead of refusing to continue beside it")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.add_argument("--add-budget", type=float, default=0, metavar="USD")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("resolve", help="settle an escalated review finding")
    p.add_argument("run")
    p.add_argument("finding")
    p.add_argument("--as", dest="decision", required=True, choices=("resolved", "advisory", "upheld"))
    p.add_argument("-m", dest="note", default="")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.set_defaults(func=cmd_resolve)

    for name, text in (("approve", "a person approves a human task"),
                       ("reject", "a person rejects; the note becomes feedback")):
        p = sub.add_parser(name, help=text)
        p.add_argument("run")
        p.add_argument("task")
        p.add_argument("-m", dest="note", default="", metavar="NOTE", required=(name == "reject"))
        p.add_argument("-C", dest="where", default=".", metavar="DIR")
        p.set_defaults(func=cmd_decide, decision=name)

    p = sub.add_parser("retry", help="fresh attempts for a failed or blocked task")
    p.add_argument("run")
    p.add_argument("task")
    p.add_argument("--apply-patch", action="store_true", help="put the set-aside work back first, "
                   "if its base is still the accepted tree")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("replan", help="install an edited workflow; reopen accepted work with revert commits")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--reopen", action="append", default=[], metavar="TASK")
    p.add_argument("--workflow", metavar="FILE", help="revised workflow (default: the original source)")
    p.add_argument("-C", dest="where", default=".", metavar="DIR")
    p.set_defaults(func=cmd_replan)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return EXIT_FAILED
    return args.func(args)


def report_problems(wf, out):
    for w in wf.warnings:
        print(f"warning: {w}", file=out)
    for e in wf.errors:
        print(f"error: {e}", file=out)
    if wf.errors:
        n = len(wf.errors)
        print(f"{wf.workflow_file}: {n} error{'s' if n != 1 else ''}", file=out)


def cmd_validate(args):
    wf = workflow.load(args.workflow)
    report_problems(wf, sys.stderr)
    if wf.errors:
        return EXIT_FAILED
    print(format_dag(wf))
    return EXIT_OK


def format_dag(wf):
    lines = [f"workflow {wf.name}: {len(wf.tasks)} tasks, in execution order",
             f"root {wf.root}", ""]
    width = max(len(t["id"]) for t in wf.tasks)
    for n, t in enumerate(wf.tasks, 1):
        kind_type = t["kind"] if t["type"] == t["kind"] else f"{t['kind']}/{t['type']}"
        parts = []
        if t["needs"]:
            parts.append("needs " + ", ".join(t["needs"]))
        if t.get("reviews"):
            parts.append("reviews " + t["reviews"] + (" (advisory)" if t.get("advisory") else ""))
        if t.get("verifies"):
            parts.append("verifies " + t["verifies"])
        if t["kind"] == "check":
            mode = "read-only" if t["read_only"] else "restores" if t["restores"] else "writer"
            parts.append(mode)
        if t["kind"] in ("produce", "review"):
            parts.append("agent " + t["agent"] + (f" ({t['model']})" if t["model"] else ""))
        lines.append(f"{n:>3}  {t['id']:<{width}}  {kind_type:<22} " + "; ".join(parts))
        if t["kind"] == "produce":
            lines.append(f"     {'':<{width}}  outputs: " + ", ".join(o["path"] for o in t["outputs"]))
            if t["writes"] != [o["path"] for o in t["outputs"]]:
                lines.append(f"     {'':<{width}}  writes:  " + ", ".join(t["writes"]))
            if t["removes"]:
                lines.append(f"     {'':<{width}}  removes: " + ", ".join(t["removes"]))
            for g in t["gates"]:
                lines.append(f"     {'':<{width}}  gate{' (new)' if g['new'] else ''}: {g['run']}")
    lines.append("")
    if wf.claims:
        lines.append("claims on frozen outputs:")
        for c in wf.claims:
            consumers = ", ".join(c["consumers"]) if c["consumers"] else "none"
            lines.append(f"  {c['task']} will modify {', '.join(c['paths'])} of {c['of']} "
                         f"(accepted consumers: {consumers})")
    else:
        lines.append("claims on frozen outputs: none")
    return "\n".join(lines)


def cmd_graph(args):
    wf = workflow.load(args.workflow)
    report_problems(wf, sys.stderr)
    if wf.errors:
        return EXIT_FAILED
    dot = format_dot(wf)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(dot)
    else:
        sys.stdout.write(dot)
    return EXIT_OK


def _q(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


SHAPES = {"produce": "box", "review": "ellipse", "check": "hexagon", "human": "octagon"}


def format_dot(wf):
    """One node per expanded task; an edge per `needs` (solid), `reviews` (dashed), `verifies` (dotted)."""
    lines = [f"digraph {_q(wf.name)} {{", "  rankdir=LR;", "  node [fontname=\"Helvetica\"];"]
    for t in wf.tasks:
        label = t["id"] + "\\n" + (t["type"] if t["type"] != t["kind"] else t["kind"])
        style = ', style="dashed"' if t.get("advisory") else ""
        lines.append(f"  {_q(t['id'])} [label=\"{label}\", shape={SHAPES[t['kind']]}{style}];")
    for t in wf.tasks:
        for n in t["needs"]:
            lines.append(f"  {_q(n)} -> {_q(t['id'])} [label=\"needs\"];")
        if t.get("reviews"):
            lines.append(f"  {_q(t['reviews'])} -> {_q(t['id'])} [label=\"reviews\", style=dashed];")
        if t.get("verifies"):
            lines.append(f"  {_q(t['verifies'])} -> {_q(t['id'])} [label=\"verifies\", style=dotted];")
    lines.append("}")
    return "\n".join(lines) + "\n"


# -- runs ---------------------------------------------------------------------------------------

def fail(message):
    print(f"runner: {message}", file=sys.stderr)
    return EXIT_FAILED


def check_capabilities(wf):
    wf.qualification_report = qualification.check_workflow(wf)
    return wf.qualification_report["problems"]


def cmd_doctor(args):
    wf = workflow.load(args.workflow)
    report_problems(wf, sys.stderr)
    if wf.errors:
        return EXIT_FAILED
    report = qualification.check_workflow(wf, force=args.force)
    for entry in report["profiles"].values():
        meta = entry["metadata"]
        mode = "read-only" if meta["read_only"] else "writer"
        print(f"{meta['profile']['kind']} {meta['model'] or '(default model)'} {mode}: "
              + (", ".join(entry["capabilities"]) or "no capabilities qualified")
              + (" (cached)" if entry["cached"] else ""))
        if entry["orphan_detection"].startswith("weaker"):
            print("warning: orphan detection is weaker on this host")
    print("qualification: " + os.path.join(record.runs_dir_for(gitops.Git(wf.root).top), "qualification.json"))
    for problem in report["problems"]:
        print(problem, file=sys.stderr)
    return EXIT_FAILED if report["problems"] else EXIT_OK


def cmd_check_gates(args):
    wf = workflow.load(args.workflow)
    report_problems(wf, sys.stderr)
    if wf.errors:
        return EXIT_FAILED
    report = preflight.check_gates(wf)
    for result in report["results"]:
        text = "fails as intended" if result["result"] == "fail" and result["fails_as_intended"] else result["result"]
        print(f"{result['id']}: {text}" +
              ("; changed paths: " + ", ".join(result["changed_paths"]) if result["changed_paths"] else ""))
    print("record: " + report["directory"])
    return EXIT_OK if report["ok"] else EXIT_FAILED


# Tests replace this to stop the runner at a named point, as a kill would.
CRASH = None


def execute(run, git):
    """Run the workflow as far as it goes. The engine works from the run's frozen copy."""
    run.crash = CRASH or run.crash
    code = engine.Engine(run, git, crash=CRASH).execute()
    status_md = os.path.join(run.path, "STATUS.md")
    print(f"run {run.name}: {run.state['status']}. See {status_md}", file=sys.stderr)
    return code


def cmd_start(args):
    wf = workflow.load(args.workflow)
    report_problems(wf, sys.stderr)
    if wf.errors:
        return EXIT_FAILED
    git = gitops.Git(wf.root)
    original = git.current_branch()
    current_mode = wf.defaults["branch"] == "current"
    if current_mode and original is None:
        return fail("HEAD is detached, and branch = \"current\" needs a branch to commit on. "
                    "Check out a branch first")
    dirty = git.dirty_paths()
    if dirty:
        shown = "".join(f"\n  {d}" for d in dirty[:20])
        return fail("the work tree is not clean, and a run starts only from a clean tree: a commit "
                    "limited to a task's paths would still take your uncommitted edits in those "
                    "files. Commit or remove these first; nothing was changed:" + shown)
    problems = check_capabilities(wf)
    if problems:
        return fail("\n".join(problems))

    runs_dir = record.ensure_runs_dir(git.top)
    lock = record.Lock(runs_dir)
    run_id = str(uuid.uuid4())
    try:
        lock.acquire(run_id)
    except record.LockHeld as exc:
        return fail(str(exc))
    with lock:
        branch = original if current_mode else f"run/{wf.name}-{run_id[:8]}"
        run = record.Run.create(wf, git, branch, original, run_id=run_id)
        qualification.attach_run(run, wf.qualification_report)
        if not current_mode:
            op = run.begin("branch", name=branch)
            git.create_and_checkout_run_branch(branch)
            run.finish(op, branch=branch)
        print(f"run {run.name}  ({run_id})")
        print(f"record  {run.path}")
        print(f"branch  {branch}" + ("" if current_mode else f"  (checked out; was {original})"))
        return execute(run, git)


def _runs_dir(where):
    path = record.find_runs_dir(os.path.abspath(where))
    if not path:
        raise record.RecordError(f"no .runs directory in the repository that holds '{where}'")
    return path


def cmd_status(args):
    try:
        run = record.Run.load(record.resolve_run(_runs_dir(args.where), args.run))
    except record.RecordError as exc:
        return fail(str(exc))
    if args.rebuild or not os.path.exists(os.path.join(run.path, "STATUS.md")):
        run.regenerate()
    with open(os.path.join(run.path, "STATUS.md"), encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return EXIT_OK


def cmd_runs(args):
    name = args.workflow
    if os.path.isfile(name):
        wf = workflow.load(name)
        name, where = wf.name, (wf.root if os.path.isdir(wf.root) else args.where)
    else:
        where = args.where
    try:
        runs = record.list_runs(_runs_dir(where), name)
    except record.RecordError as exc:
        return fail(str(exc))
    if not runs:
        return fail(f"no runs of workflow '{name}'")
    print(f"{'run':<28} {'status':<12} {'known spend':>11}  started")
    for _wf, run_name, path in runs:
        run = record.Run.load(path)
        print(f"{run_name:<28} {run.state['status']:<12} "
              f"{'$%.2f' % run.state['spend']['known_usd']:>11}  {run.info['started']}")
    return EXIT_OK


def cmd_prune(args):
    """Delete refs/task-runner/<run>/ of every run that is done or whose directory is gone. A run
    that is unfinished keeps its refs, and so does one whose set-aside work has lost its patch."""
    try:
        git = gitops.Git(os.path.abspath(args.where))
    except gitops.GitError as exc:
        return fail(str(exc))
    runs_dir = record.runs_dir_for(git.top)
    known = {name: path for _wf, name, path in record.list_runs(runs_dir)}
    for name in git.pinned_runs():
        if name not in known:
            reason = "its directory is gone"
        else:
            run = record.Run.load(known[name])
            if run.state["status"] not in record.FINISHED_STATUSES:
                print(f"kept    {name}: the run is {run.state['status']}")
                continue
            missing = [t for t, st in run.state["tasks"].items()
                       if st["status"] in ("failed", "blocked")
                       and not os.path.exists(os.path.join(run.task_dir(t), "failed.patch"))]
            if missing:
                print(f"kept    {name}: no failed.patch for {', '.join(missing)}")
                continue
            reason = "the run is done"
        refs = git.unpin_run(name)
        print(f"pruned  {name}: {len(refs)} ref(s), {reason}")
    return EXIT_OK


def _open_run(args, unfinished_only=False):
    """(run, git, lock) for a command that changes a run. The caller releases the lock."""
    runs_dir = _runs_dir(args.where)
    path = record.resolve_run(runs_dir, args.run, unfinished_only=unfinished_only
                              and args.run in (None, "", "latest"))
    run = record.Run.load(path)
    git = gitops.Git(run.info["git_toplevel"])
    lock = record.Lock(runs_dir).acquire(run.state["run_id"])
    return run, git, lock


def cmd_resume(args):
    if not math.isfinite(args.add_budget) or args.add_budget < 0:
        return fail("--add-budget must be a finite nonnegative amount")
    try:
        run, git, lock = _open_run(args, unfinished_only=True)
    except (record.RecordError, gitops.GitError) as exc:
        return fail(str(exc))
    with lock:
        if run.state["status"] == "done":
            print(f"run {run.name} is done; nothing to resume")
            return EXIT_OK
        branch = run.info["branch"]
        if git.current_branch() != branch and not any(i["kind"] == "branch"
                                                      for i in run.state["intents"]):
            return fail(f"reconciliation error: the run works on branch '{branch}', but "
                        f"'{git.current_branch()}' is checked out. Check out '{branch}' first")
        try:
            for line in record.reconcile(run, git, stop_orphans=args.stop_orphans,
                                         crash=CRASH or record._no_crash):
                print(f"reconciled: {line}")
        except record.ReconcileError as exc:
            return fail(f"reconciliation error: {exc}. Nothing was changed; put it back as it "
                        "was, then `runner resume`")
        except gitops.RestoreError as exc:
            return fail(f"environment failure: {exc}")
        if args.add_budget:
            if not math.isfinite(run.state["run_budget_usd"] + args.add_budget):
                return fail("the resulting run budget must be finite")
            run.state["run_budget_usd"] += args.add_budget
            run.save()
            run.event("budget-added", amount_usd=args.add_budget, budget_usd=run.state["run_budget_usd"])
        if any(st["kind"] in ("produce", "review") for st in run.state["tasks"].values()):
            frozen = record.read_json(os.path.join(run.path, "workflow.expanded.json"))
            wf = SimpleNamespace(root=frozen["paths"]["root"], tasks=frozen["tasks"], agents=frozen["agents"])
            report = qualification.check_workflow(wf, locked=True)
            if report["problems"]:
                return fail("\n".join(report["problems"]))
            qualification.attach_run(run, report)
            run.state.pop("needs_qualification", None)
            run.save()
        return execute(run, git)


def cmd_decide(args):
    try:
        run, git, lock = _open_run(args)
    except (record.RecordError, gitops.GitError) as exc:
        return fail(str(exc))
    with lock:
        try:
            engine.decide(run, engine.Engine(run, git), args.task, args.decision, args.note,
                          who=os.environ.get("USER", ""))
        except engine.Refused as exc:
            return fail(str(exc))
    done = "approved" if args.decision == "approve" else "rejected"
    print(f"{args.task}: {done}. Continue with: runner resume {run.name}")
    return EXIT_OK


def cmd_retry(args):
    try:
        run, git, lock = _open_run(args)
    except (record.RecordError, gitops.GitError) as exc:
        return fail(str(exc))
    with lock:
        try:
            engine.retry(run, engine.Engine(run, git), git, args.task, args.apply_patch)
        except engine.Refused as exc:
            return fail(str(exc))
    print(f"{args.task}: fresh attempts"
          + (", continuing from its set-aside work" if args.apply_patch else ", starting clean")
          + f". Continue with: runner resume {run.name}")
    return EXIT_OK


def cmd_resolve(args):
    try:
        run, git, lock = _open_run(args)
    except (record.RecordError, gitops.GitError) as exc:
        return fail(str(exc))
    with lock:
        try:
            engine.resolve(run, engine.Engine(run, git), args.finding, args.decision, args.note,
                           who=os.environ.get("USER", ""))
        except engine.Refused as exc:
            return fail(str(exc))
    print(f"{args.finding}: {args.decision}. Continue with: runner resume {run.name}")
    return EXIT_OK


def cmd_replan(args):
    try:
        run, git, lock = _open_run(args)
    except (record.RecordError, gitops.GitError) as exc:
        return fail(str(exc))
    with lock:
        source = args.workflow or run.state.get("workflow_file") or run.info["workflow_file"]
        try:
            directory, plan = replan.prepare(run, git, source, args.reopen)
            print("replan changes: " + (", ".join(plan["changes"]) or "none"))
            print("affected tasks: " + (", ".join(plan["affected"]) or "none"))
            print("revert commits: " + (", ".join(c[:7] for c in plan["commits"]) or "none"))
            print(replan.execute(run, git, directory, CRASH or record._no_crash))
        except (replan.Refused, gitops.GitError, gitops.RevertConflict) as exc:
            return fail(str(exc))
    print(f"Continue with: runner resume {run.name}")
    return EXIT_OK
