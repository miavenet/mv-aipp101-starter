"""Run gate and check commands: a shell, its own process group, a time limit, the output streamed
to a log with a bounded tail kept for feedback. Returns facts: pass or fail and the output."""

import os

from . import proc

FEEDBACK_TAIL = 6000
# Agents authenticate through these; gates and checks must not inherit them (05, Profiles).
AUTH_PREFIXES = ("ANTHROPIC_", "OPENAI_", "CLAUDE_", "CODEX_", "AZURE_OPENAI_", "GEMINI_")
AUTH_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "AWS_BEARER_TOKEN_BEDROCK", "TASK_RUNNER_RUN_DIR")


def command_env(base, run_id="", task_id=""):
    env = {k: v for k, v in base.items()
           if not k.startswith(AUTH_PREFIXES) and k not in AUTH_NAMES}
    if run_id:
        env.update(TASK_RUNNER_RUN=run_id, TASK_RUNNER_TASK=task_id)
    return env


def run_commands(commands, *, cwd, log_path, timeout_s, env, on_start=None):
    """Run each command in turn and stop at the first that does not pass. Returns one dict per
    command that ran: command, result (pass | fail | timeout | error), exit, seconds, tail."""
    results = []
    for command in commands:
        with open(log_path, "ab") as fh:
            fh.write(proc.redact(f"$ {command}\n".encode("utf-8")))
        res = proc.run_process(["/bin/sh", "-c", command], cwd=cwd, env=env, stdout_path=log_path,
                               timeout_s=timeout_s, on_start=on_start)
        if res.status == "not-started":
            result, tail = "error", res.error
        else:
            tail = res.stdout_tail.decode("utf-8", errors="replace")[-FEEDBACK_TAIL:]
            if res.status == "timed-out":
                result = "timeout"
            elif res.returncode in (126, 127):
                result = "error"
            else:
                result = "pass" if res.returncode == 0 else "fail"
        with open(log_path, "ab") as fh:
            fh.write(f"[{result}, exit {res.returncode}, {res.seconds:.1f}s]\n".encode("utf-8"))
        results.append({"command": command, "result": result, "exit": res.returncode,
                        "seconds": round(res.seconds, 3), "tail": tail})
        if result != "pass":
            break
    return results


def passed(results, commands):
    return len(results) == len(commands) and all(r["result"] == "pass" for r in results)
