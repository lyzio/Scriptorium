"""Work protection (design document F2).

* Recovery copies (F2.5, F2.8): at each pause in typing the open adventure is
  written to the app's data folder. The user's own file changes only when
  the user saves. After a crash the next start offers to restore it.
* Snapshots (F2.6, F2.7): every 15 minutes while there are unsaved or newly
  saved changes a snapshot is kept, and File → "Revert to previous version"
  restores one.
* Open-elsewhere locks (F2.3): an adventure that is already open in another
  window opens read-only there.

Everything lives in the app's own data folder, never next to the author's
file, and nothing is sent anywhere (D9).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

SNAPSHOT_INTERVAL = 15 * 60  # F2.6: seconds between snapshots
SNAPSHOTS_KEPT = 40          # per adventure; older ones are removed


def pid_alive(pid: int) -> bool:
    """True when a process with this ID is still running."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform.startswith("win"):
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def path_key(path: Path) -> str:
    return hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:20]


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------
# Recovery copies (F2.5, F2.8)

class RecoveryStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, session_id: str, data: bytes, meta: dict) -> None:
        _write_atomic(self.root / f"{session_id}.scav", data)
        info = {**meta, "pid": os.getpid(), "session": session_id, "time": time.time()}
        _write_atomic(self.root / f"{session_id}.json", json.dumps(info, ensure_ascii=False).encode("utf-8"))

    def remove(self, session_id: str) -> None:
        for suffix in (".scav", ".json"):
            (self.root / f"{session_id}{suffix}").unlink(missing_ok=True)

    def orphans(self) -> List[dict]:
        """Recovery copies left behind by a window that is no longer running."""
        found = []
        for meta_file in sorted(self.root.glob("*.json")):
            try:
                meta = json.loads(meta_file.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not (self.root / f"{meta_file.stem}.scav").is_file():
                continue
            if pid_alive(int(meta.get("pid", 0))):
                continue
            found.append(meta)
        return sorted(found, key=lambda m: m.get("time", 0), reverse=True)

    def data(self, session_id: str) -> bytes:
        return (self.root / f"{session_id}.scav").read_bytes()


# --------------------------------------------------------------------------
# Snapshots (F2.6, F2.7)

class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.kept = SNAPSHOTS_KEPT  # F18: how many snapshots are kept

    def folder(self, key: str) -> Path:
        return self.root / key

    def take(self, key: str, data: bytes, title: str, when: Optional[float] = None) -> str:
        when = time.time() if when is None else when
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when)) + f"-{int((when % 1) * 1000):03d}"
        folder = self.folder(key)
        _write_atomic(folder / f"{stamp}.scav", data)
        _write_atomic(folder / f"{stamp}.json", json.dumps({"title": title, "time": when}, ensure_ascii=False).encode("utf-8"))
        for old in self.list(key)[max(1, int(self.kept)):]:
            self.remove(key, old["id"])
        return stamp

    def list(self, key: str) -> List[dict]:
        folder = self.folder(key)
        items = []
        for meta_file in sorted(folder.glob("*.json"), reverse=True) if folder.is_dir() else []:
            try:
                meta = json.loads(meta_file.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append({"id": meta_file.stem, "title": meta.get("title", ""), "time": meta.get("time", 0)})
        return items

    def data(self, key: str, snapshot_id: str) -> bytes:
        return (self.folder(key) / f"{snapshot_id}.scav").read_bytes()

    def remove(self, key: str, snapshot_id: str) -> None:
        for suffix in (".scav", ".json"):
            (self.folder(key) / f"{snapshot_id}{suffix}").unlink(missing_ok=True)

    def move(self, old_key: str, new_key: str) -> None:
        """An unsaved adventure was saved: its snapshots follow it."""
        source = self.folder(old_key)
        if not source.is_dir() or old_key == new_key:
            return
        target = self.folder(new_key)
        target.mkdir(parents=True, exist_ok=True)
        for file in source.iterdir():
            os.replace(file, target / file.name)
        source.rmdir()


class SnapshotClock:
    """F2.6: decides when a snapshot is due. A snapshot is taken every 15
    minutes while there are unsaved or newly saved changes."""

    def __init__(self, now: Optional[float] = None, interval: Optional[float] = None):
        self.last = time.time() if now is None else now
        self.changed = False
        self.interval = SNAPSHOT_INTERVAL if interval is None else interval  # F18: seconds

    def mark_changed(self) -> None:
        self.changed = True

    def due(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return self.changed and now - self.last >= self.interval

    def taken(self, now: Optional[float] = None) -> None:
        self.last = time.time() if now is None else now
        self.changed = False


# --------------------------------------------------------------------------
# Open-elsewhere locks (F2.3)

class LockRegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, path: Path) -> Path:
        return self.root / f"{path_key(path)}.json"

    def holder(self, path: Path) -> Optional[dict]:
        file = self._file(path)
        try:
            data = json.loads(file.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not pid_alive(int(data.get("pid", 0))):
            return None  # a stale lock from a window that is gone
        return data

    def acquire(self, path: Path, owner: str) -> bool:
        """True when this window may edit the adventure; False when another
        window already has it open."""
        current = self.holder(path)
        if current is not None and current.get("owner") != owner:
            return False
        data = {"pid": os.getpid(), "owner": owner, "path": str(Path(path).resolve())}
        _write_atomic(self._file(path), json.dumps(data).encode("utf-8"))
        return True

    def release(self, path: Path, owner: str) -> None:
        current = self.holder(path)
        if current is not None and current.get("owner") == owner:
            self._file(path).unlink(missing_ok=True)
