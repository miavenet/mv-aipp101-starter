"""Run one child process the way the runner runs every child (05, Processes and logs): in its own
process group, with its output streamed to files as it arrives and only a bounded tail kept in
memory, under the runner's own clock, and with token-shaped strings redacted before anything is
stored. Used for agents and for gate and check commands alike. Reports facts; decides nothing.
"""

import os
import re
import selectors
import signal
import subprocess
import time

from . import record

TAIL_BYTES = 256 * 1024
LINE_LIMIT = 64 * 1024
GRACE_S = 5.0

# The one list of what counts as a secret in stored output (04, rule 5; RUN-10).
REDACTIONS = [
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"gh[ousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    re.compile(rb"(?i)(aws_secret_access_key\s*[=:]\s*)[A-Za-z0-9/+=]{40}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
]
REDACTED = b"[redacted]"


def redact(data):
    for pattern in REDACTIONS:
        data = pattern.sub(lambda m: (m.group(1) if m.groups() else b"") + REDACTED, data)
    return data


class _Sink:
    """Redacts whole lines, writes them to the log at once, keeps a bounded tail."""

    def __init__(self, path):
        self.fh = open(path, "ab")
        self.pending = b""
        self.tail = b""
        self.total = 0
        self.overlong = False

    def feed(self, chunk):
        # A token can cross any read boundary. Keep complete bounded lines, and suppress
        # an overlong line in full rather than leak a token split at the buffer limit.
        while chunk:
            newline = chunk.find(b"\n")
            end = newline + 1 if newline >= 0 else len(chunk)
            part, chunk = chunk[:end], chunk[end:]
            if not self.overlong:
                if len(self.pending) + len(part) > LINE_LIMIT:
                    self.pending = b""
                    self.overlong = True
                    self._emit(b"[overlong line omitted for safe redaction]\n")
                else:
                    self.pending += part
            if newline >= 0:
                if not self.overlong:
                    self._emit(self.pending)
                self.pending = b""
                self.overlong = False

    def _emit(self, data):
        data = redact(data)
        self.fh.write(data)
        self.fh.flush()
        self.total += len(data)
        self.tail = (self.tail + data)[-TAIL_BYTES:]

    def close(self):
        if self.pending:
            self._emit(self.pending)
            self.pending = b""
        self.fh.close()


class ProcResult:
    def __init__(self, status, returncode, stdout_tail, stderr_tail, seconds, identity, error=""):
        self.status = status                  # exited | timed-out | not-started
        self.returncode = returncode
        self.stdout_tail, self.stderr_tail = stdout_tail, stderr_tail
        self.seconds, self.identity, self.error = seconds, identity, error


def run_process(argv, *, cwd, env, stdin_data=b"", stdout_path, stderr_path=None,
                timeout_s=None, on_start=None, grace_s=GRACE_S):
    """Run `argv` to the end or to the deadline. `stderr_path=None` sends both streams to one log.
    `on_start(identity)` is called once the child exists, so the caller can record who it is."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE if stderr_path else subprocess.STDOUT,
                                start_new_session=True)
    except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
        return ProcResult("not-started", None, b"", b"", 0.0, None, str(exc))
    identity = record.process_identity(proc.pid) or {"pid": proc.pid, "pgid": proc.pid}
    try:
        if on_start:
            on_start(identity)
    except BaseException:
        stop_group(proc, identity, grace_s, polite=False)     # never leave a child nobody watches
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
        raise

    out, err = _Sink(stdout_path), (_Sink(stderr_path) if stderr_path else None)
    sel = selectors.DefaultSelector()
    os.set_blocking(proc.stdout.fileno(), False)
    sel.register(proc.stdout, selectors.EVENT_READ, out)
    if err:
        os.set_blocking(proc.stderr.fileno(), False)
        sel.register(proc.stderr, selectors.EVENT_READ, err)
    os.set_blocking(proc.stdin.fileno(), False)
    todo = memoryview(stdin_data)
    if len(todo):
        sel.register(proc.stdin, selectors.EVENT_WRITE, None)
    else:
        proc.stdin.close()

    deadline = started + timeout_s if timeout_s else None
    timed_out = False
    try:
        exited_at = None
        while any(k.data is not None for k in sel.get_map().values()):
            if proc.poll() is not None:
                # The child is gone; a straggler may still hold the pipe. Drain briefly, then stop.
                exited_at = exited_at or time.monotonic()
                if time.monotonic() - exited_at > 0.5:
                    break
            wait = 0.2
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    timed_out = True
                    break
                wait = min(wait, left)
            for key, _mask in sel.select(wait):
                if key.fileobj is proc.stdin:
                    try:
                        sent = os.write(proc.stdin.fileno(), todo[:65536])
                        todo = todo[sent:]
                    except (BrokenPipeError, BlockingIOError):
                        sent = 0
                        if proc.poll() is not None:
                            todo = todo[len(todo):]
                    if not len(todo):
                        sel.unregister(proc.stdin)
                        proc.stdin.close()
                    continue
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if chunk:
                    key.data.feed(chunk)
                else:
                    sel.unregister(key.fileobj)
        if not timed_out:
            left = None if deadline is None else max(0.0, deadline - time.monotonic())
            try:
                proc.wait(timeout=left)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        # Whatever happened, nothing of the group outlives the call.
        stop_group(proc, identity, grace_s, polite=timed_out)
        for key in list(sel.get_map().values()):
            if key.data is not None:
                try:
                    rest = os.read(key.fileobj.fileno(), 1 << 20)
                    if rest:
                        key.data.feed(rest)
                except (BlockingIOError, OSError):
                    pass
        sel.close()
        out.close()
        if err:
            err.close()
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass
    seconds = time.monotonic() - started
    return ProcResult("timed-out" if timed_out else "exited", proc.returncode, out.tail,
                      err.tail if err else b"", seconds, identity)


def stop_group(proc, identity, grace_s, polite=True):
    """SIGINT, SIGTERM, SIGKILL to the whole group. After a normal exit only stragglers remain, and
    they are killed without ceremony."""
    pgid = identity.get("pgid") or proc.pid
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL) if polite else (signal.SIGKILL,)
    for sig in signals:
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            break
        deadline = time.monotonic() + (grace_s if sig != signal.SIGKILL else 1.0)
        while time.monotonic() < deadline:
            if proc.poll() is not None and not _group_alive(pgid):
                break
            time.sleep(0.02)
        if proc.poll() is not None and not _group_alive(pgid):
            break
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
