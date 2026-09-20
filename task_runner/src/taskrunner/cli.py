"""Commands, exit codes, printing. Exit 0: fine. 2: something is wrong. 255: a person is needed."""

import argparse
import sys

from . import __version__, workflow

EXIT_OK, EXIT_FAILED, EXIT_HUMAN = 0, 2, 255

# Commands of 05 that later stages build: name -> (stage, help)
LATER = {
    "doctor": (4, "qualify each agent, model and profile per capability"),
    "check-gates": (4, "run every gate and check on the untouched tree"),
    "start": (2, "create a run and execute it"),
    "resume": (3, "reconcile, then continue a run"),
    "status": (2, "print STATUS.md; --rebuild regenerates all derived files"),
    "runs": (2, "list runs with status, cost and date"),
    "approve": (3, "a person approves a human task"),
    "reject": (3, "a person rejects; the note becomes feedback"),
    "retry": (3, "fresh attempts for a failed or blocked task"),
    "resolve": (5, "a person settles an escalated finding"),
    "replan": (6, "bring an edited workflow into the run, where safe"),
    "prune": (2, "delete the pinned refs of finished or deleted runs"),
}


def main(argv=None):
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

    for name, (stage, text) in LATER.items():
        p = sub.add_parser(name, help=f"{text} (stage {stage}, not implemented yet)")
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.set_defaults(func=cmd_later, stage=stage)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return EXIT_FAILED
    return args.func(args)


def cmd_later(args):
    print(f"runner {args.command}: not implemented yet (stage {args.stage})", file=sys.stderr)
    return EXIT_FAILED


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
