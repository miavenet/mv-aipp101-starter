#!/usr/bin/env python3
"""Task runner: carry a task list to completion with a headless coding agent.

  runner.py validate PLAN        check the plan and print the execution order
  runner.py run PLAN             run until done, or until a person is needed
  runner.py next PLAN            advance one phase of one task
  runner.py status PLAN          show where every task stands
  runner.py approve PLAN TASK    release a task that waits for a person
  runner.py retry PLAN TASK      give a failed or blocked task a fresh set of attempts

Exit codes: 0 all done, 1 more work (next only), 2 error or failed task, 255 a person is needed.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taskrunner import tasks                                    # noqa: E402
from taskrunner.engine import DONE, ERROR, HUMAN, Runner         # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["validate", "run", "next", "status", "approve", "retry"])
    ap.add_argument("plan")
    ap.add_argument("task", nargs="?")
    args = ap.parse_args(argv)
    try:
        plan = tasks.load(args.plan)
    except tasks.PlanError as e:
        print(f"Plan is not valid:\n{e}", file=sys.stderr)
        return ERROR

    if args.command == "validate":
        print(f"Plan '{plan.name}': {len(plan.tasks)} tasks, root {plan.root}")
        for i, t in enumerate(plan.tasks, 1):
            reviewer = (t.reviewer or t.agent) if t.review else "none"
            print(f"{i:3}. {t.id:<24} agent={t.agent} reviewer={reviewer} gates={len(t.gate)}"
                  + (f" needs={','.join(t.needs)}" if t.needs else "") + (" human" if t.human_review else ""))
        return DONE

    runner = Runner(plan)
    if args.command == "status":
        for t in plan.tasks:
            st = runner.state["tasks"][t.id]
            line = f"{t.id:<24} {st['status']:<15} attempt {st['attempt']}/{t.max_attempts}  ${st['cost_usd']:.2f}"
            print(line + (f"  {st['commit']}" if st.get("commit") else "")
                  + (f"  {st['reason'][:100]}" if st["status"] in ("failed", "blocked") else ""))
        print(f"total ${runner.state['cost_usd']:.2f} of ${plan.defaults['run_budget_usd']:.2f}")
        return DONE
    if args.command in ("approve", "retry"):
        try:
            st = runner.state["tasks"][plan.task(args.task or "").id]
        except tasks.PlanError as e:
            print(e, file=sys.stderr)
            return ERROR
        if args.command == "approve":
            if st["status"] != "awaiting_human":
                print(f"{args.task} is not waiting for approval (it is {st['status']})", file=sys.stderr)
                return ERROR
            st.update(status="running", phase="commit")
        else:
            if st["status"] not in ("failed", "blocked"):
                print(f"{args.task} is {st['status']}, so there is nothing to retry", file=sys.stderr)
                return ERROR
            st.update(status="running", phase="implement", attempt=0, session_id=None, last_gate_hash=None,
                      review_errors=0, reason="")
        runner.save()
        print(f"{args.task}: {args.command} recorded. Continue with: runner.py run {args.plan}")
        return DONE
    code = runner.run() if args.command == "run" else runner.next()
    if code == DONE:
        print(f"All {len(plan.tasks)} tasks done. Total ${runner.state['cost_usd']:.2f}.")
    return code


if __name__ == "__main__":
    sys.exit(main())
