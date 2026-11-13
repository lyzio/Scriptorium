"""The build helper (design document F7.1; built in M6 part B).

Every Typst compile and query runs in one separate helper process instead of
inside the app. The helper starts with the app and is reused for every build,
so Typst keeps its warm caches and the preview stays as fast as before. A build
that runs longer than the time limit (60 seconds, fixed) is stopped by ending
the helper; a crash inside Typst ends only the helper. Either way the editor
and the unsaved text are untouched, and the next build starts a new helper.

The app and the helper talk over the helper's standard input and output, one
pickled request and one pickled reply at a time. Both ends are Scriptorum's
own code; nothing else ever writes to these pipes.
"""

from __future__ import annotations

import atexit
import os
import pickle
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# F7.1 (decided 12 November 2026): the time limit of one build, in seconds.
# Fixed, not a setting. Tests lower it so they need not wait a minute.
TIME_LIMIT = 60.0

_ROOT = Path(__file__).resolve().parents[2]  # the folder that holds scriptorum/


class HelperTypstError(RuntimeError):
    """A Typst error raised in the helper, carried back with the same parts
    the error mapping reads (3.4): message, diagnostic and trace."""

    def __init__(self, message: str, diagnostic: str = "", trace=None, hints=None):
        super().__init__(message)
        self.message = message
        self.diagnostic = diagnostic
        self.trace = list(trace or [])
        self.hints = list(hints or [])


class BuildStopped(Exception):
    """The helper did not answer: ``reason`` is "time" (the time limit was
    reached and the helper was stopped) or "crash" (the helper ended)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- the app's side ----------------------------------------------------------------------
def _send(stream, obj) -> None:
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">Q", len(data)))
    stream.write(data)
    stream.flush()


def _receive(stream):
    head = stream.read(8)
    if len(head) < 8:
        raise EOFError
    size = struct.unpack(">Q", head)[0]
    data = stream.read(size)
    if len(data) < size:
        raise EOFError
    return pickle.loads(data)


class Helper:
    """One helper process, shared by every tab. Requests are served one at a
    time; the time limit counts from the moment a request is sent, never
    while it waits for another tab's build."""

    def __init__(self):
        self._lock = threading.Lock()
        self.process: Optional[subprocess.Popen] = None
        self.starts = 0  # how many helpers were started (tests read it)

    # -- the process ---------------------------------------------------------------------
    def _command(self) -> list:
        if getattr(sys, "frozen", False):  # an installed app (F10): the app runs its own helper
            return [sys.executable, "--scriptorum-build-helper"]
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "from scriptorum.core.helper import serve; serve()")
        return [sys.executable, "-c", code, str(_ROOT)]

    def _ensure(self) -> subprocess.Popen:
        if self.process is None or self.process.poll() is not None:
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(
                self._command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            self.starts += 1
        return self.process

    def start(self) -> None:
        """Start the helper ahead of the first build and warm Typst up, so
        the first preview is quick too (in the background)."""
        def warm():
            try:
                self.call({"op": "warm"})
            except Exception:  # noqa: BLE001 - the first build simply starts it again
                pass
        threading.Thread(target=warm, daemon=True).start()

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def pid(self) -> Optional[int]:
        return self.process.pid if self.process is not None and self.process.poll() is None else None

    # -- one request -----------------------------------------------------------------------
    def call(self, request: dict, limit: Optional[float] = None):
        """Send one request and wait for its reply. Raises BuildStopped when
        the time limit is reached or the helper ends, and HelperTypstError
        for an ordinary Typst error."""
        with self._lock:
            process = self._ensure()
            box: dict = {}
            request = {**request, "cwd": os.getcwd()}

            def talk():
                try:
                    _send(process.stdin, request)
                    box["reply"] = _receive(process.stdout)
                except (EOFError, OSError, pickle.UnpicklingError, BrokenPipeError) as exc:
                    box["broken"] = exc

            worker = threading.Thread(target=talk, daemon=True)
            worker.start()
            worker.join(TIME_LIMIT if limit is None else limit)
            if worker.is_alive():
                # F7.1: stopped after the time limit; the next build starts a new helper.
                self.stop()
                worker.join(5)
                raise BuildStopped("time")
            if "broken" in box:
                self.stop()
                raise BuildStopped("crash")
        reply = box["reply"]
        if "error" in reply:
            raise HelperTypstError(**reply["error"])
        return reply.get("value")


_helper: Optional[Helper] = None
_helper_lock = threading.Lock()


def helper() -> Helper:
    """The app's one helper."""
    global _helper
    with _helper_lock:
        if _helper is None:
            _helper = Helper()
            atexit.register(_helper.stop)
        return _helper


# --- the helper's side ------------------------------------------------------------------
_compilers: dict = {}


def _compiler(typst, spec: dict):
    """A compiler for one build folder, kept between builds (its caches are
    what makes a rebuild fast). A new font set makes a new compiler."""
    key = (spec["input"], spec["root"], tuple(spec.get("font_paths", ())), spec.get("fonts_key"))
    compiler = _compilers.get(key)
    if compiler is None:
        while len(_compilers) >= 8:  # never more than eight build folders at once
            _compilers.pop(next(iter(_compilers)))
        compiler = typst.Compiler(
            input=spec["input"], root=spec["root"], font_paths=list(spec.get("font_paths", ())),
            ignore_system_fonts=True, package_path=spec["no_packages"], package_cache_path=spec["no_packages"],
        )
        _compilers[key] = compiler
    return compiler


def _fresh(typst, spec: dict):
    return typst.Compiler(
        input=spec["input"], root=spec["root"], font_paths=list(spec.get("font_paths", ())),
        ignore_system_fonts=True, package_path=spec["no_packages"], package_cache_path=spec["no_packages"],
    )


def _handle(typst, request: dict):
    op = request["op"]
    if op == "warm":
        return None
    if op == "compile":
        compiler = _compiler(typst, request["spec"])
        data, warnings = compiler.compile_with_warnings(**request["kwargs"])
        return {"data": data, "warnings": [str(getattr(w, "message", w)) for w in warnings]}
    if op == "query":
        # A query on the build compiler would leave it reading stale files
        # (typst 0.15.0), so each query gets a fresh compiler; Typst's own
        # cache keeps that cheap.
        return _fresh(typst, request["spec"]).query(request["selector"], **request.get("kwargs", {}))
    if op == "compile-once":
        return _fresh(typst, request["spec"]).compile(**request["kwargs"])
    raise ValueError(op)


def serve() -> None:
    """The helper's loop: read a request, answer it, until the app goes away."""
    import typst

    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    # Nothing but replies may reach the pipe: anything printed goes to stderr.
    sys.stdout = sys.stderr
    while True:
        try:
            request = _receive(stdin)
        except EOFError:
            return
        if request.get("cwd"):
            try:
                os.chdir(request["cwd"])  # Typst shows paths relative to it (3.4)
            except OSError:
                pass
        try:
            reply = {"value": _handle(typst, request)}
        except typst.TypstError as exc:
            reply = {"error": {
                "message": str(getattr(exc, "message", "") or exc),
                "diagnostic": str(getattr(exc, "diagnostic", "") or ""),
                "trace": [str(t) for t in (getattr(exc, "trace", None) or [])],
                "hints": [str(h) for h in (getattr(exc, "hints", None) or [])],
            }}
        except Exception as exc:  # noqa: BLE001 - reported as a Typst error, never silent
            reply = {"error": {"message": f"{type(exc).__name__}: {exc}"}}
        try:
            _send(stdout, reply)
        except (BrokenPipeError, OSError):
            return


def wait_for(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()
