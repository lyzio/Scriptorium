"""Crash logs (design document F2.11, D9).

An unexpected error is written to a log file in the app's own data folder.
Logs are never sent anywhere.
"""

from __future__ import annotations

import faulthandler
import platform
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from scriptorum import __version__, paths

LOGS_KEPT = 20
_fault_file = None


def write_crash_log(exc_type, exc, tb, folder: Optional[Path] = None) -> Path:
    folder = Path(folder or paths.logs_dir())
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = folder / f"crash-{stamp}-{int(time.time() * 1000) % 1000:03d}.log"
    lines = [
        f"Scriptorum {__version__} — {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Python {platform.python_version()} on {platform.platform()}",
        "",
        "".join(traceback.format_exception(exc_type, exc, tb)),
    ]
    target.write_text("\n".join(lines), "utf-8")
    logs = sorted(folder.glob("crash-*.log"))
    for old in logs[:-LOGS_KEPT]:
        old.unlink(missing_ok=True)
    return target


def install(folder: Optional[Path] = None) -> None:
    """Write a log for every unexpected error, and for hard crashes."""
    global _fault_file
    folder = Path(folder or paths.logs_dir())
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        try:
            write_crash_log(exc_type, exc, tb, folder)
        finally:
            previous(exc_type, exc, tb)

    def thread_hook(args):
        write_crash_log(args.exc_type, args.exc_value, args.exc_traceback, folder)

    sys.excepthook = hook
    threading.excepthook = thread_hook
    _fault_file = open(folder / "faults.log", "a", encoding="utf-8")
    faulthandler.enable(file=_fault_file)
