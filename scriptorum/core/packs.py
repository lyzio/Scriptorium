"""Update packs and the versions kept in the author's own Scriptorum folder
(design document F22, decided 13 November 2026, built in M6 part C5).

An update pack is a zip file that holds Scriptorum's own code, the interface
and the bundled modules (the ``scriptorum`` package), never Python, Qt or
Typst. Beside the package it holds two files::

    pack.json   {"format": 1, "version": "0.6.8",
                 "runtime": {"python": "3.13", "pyside6": "6.8.3", ...},
                 "files": {"scriptorum/__init__.py": "<sha256>", ...}}
    pack.sig    the project's Ed25519 signature of pack.json (base64)

A verified pack is unpacked into ``<app home>/app-versions/<version>/``,
beside the module library; the installed app itself is never changed. At
every start the installed app looks there for a newer verified version made
for its own Python, Qt and Typst and runs it (``scriptorum.boot``). The
newest and the previous version are kept, so Scriptorum can go back by
itself when a version fails to start, or by hand (Help ▸ Go back to version).

This module uses only the standard library and the signature check, so the
start-up step can use it before anything else is loaded. Nothing here makes
a network request (D9).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from scriptorum.core import signing

PACK_FORMAT = 1
MANIFEST = "pack.json"
SIGNATURE = "pack.sig"
STATE = "state.json"
VERSIONS_DIR = "app-versions"
PACKAGE = "scriptorum"
MAX_PACK_BYTES = 300 * 1024 * 1024   # far above a real pack (about 25 MB)

# What a pack may hold (as for a .scmod, 9.7, plus the app's own code and
# interface). Anything else refuses the whole pack.
ALLOWED_SUFFIXES = {
    ".py", ".json", ".typ", ".svg", ".png", ".jpg", ".jpeg", ".ttf", ".otf", ".woff2",
    ".txt", ".md", ".dic", ".aff", ".js", ".html", ".css",
}
LICENCE_NAMES = re.compile(r"^(licen[cs]e|copying|ofl|notice)([-_.].*)?$", re.IGNORECASE)

# The libraries a pack is made for. A pack runs only where every one of them
# is the exact version it names (F22.2: Python, Qt and Typst; the signature
# and spelling libraries ship inside the installers too).
RUNTIME_KEYS = ("python", "pyside6", "typst", "cryptography", "spylls")
# The pinned versions (D4, TechStack) a release is made for. The release
# script writes them into every pack and update file.
PINNED = {"python": "3.13", "pyside6": "6.8.3", "typst": "0.15.0", "cryptography": "48.0.1", "spylls": "0.1.7"}


class PackError(Exception):
    """A pack or an unpacked version that may not be used. ``reason`` is one
    of: signature, damaged, unsafe, filetype, unlisted, version, runtime."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# --- the runtime ---------------------------------------------------------------------

def runtime() -> Dict[str, str]:
    """The versions of Python and the pinned libraries this app runs on."""
    found = {"python": f"{sys.version_info[0]}.{sys.version_info[1]}"}
    for key, module, attribute in (("pyside6", "PySide6", "__version__"), ("typst", "typst", "__version__"),
                                   ("cryptography", "cryptography", "__version__")):
        try:
            found[key] = str(getattr(__import__(module), attribute))
        except Exception:  # noqa: BLE001 - a missing library simply does not match
            found[key] = ""
    try:
        from importlib import metadata
        found["spylls"] = metadata.version("spylls")
    except Exception:  # noqa: BLE001
        found["spylls"] = ""
    return found


def runtime_matches(wanted, have: Optional[Dict[str, str]] = None) -> bool:
    if not isinstance(wanted, dict) or not wanted:
        return False
    have = runtime() if have is None else have
    for key, value in wanted.items():
        if not isinstance(value, str) or have.get(key, "") != value:
            return False
    return "python" in wanted


def parse_version(text: str) -> tuple:
    parts = str(text).strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(text)
    return tuple(int(p) for p in parts)


def newer(a: str, b: str) -> bool:
    try:
        return parse_version(a) > parse_version(b)
    except ValueError:
        return False


# --- one unpacked version ---------------------------------------------------------------

def _sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with open(file, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _allowed(relative: str) -> bool:
    name = PurePosixPath(relative).name
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix in ALLOWED_SUFFIXES:
        return True
    return suffix == "" and bool(LICENCE_NAMES.match(name))


def read_manifest(data: bytes, signature: str, key: Optional[str] = None) -> dict:
    """Check the signature of pack.json and return what it says."""
    try:
        signing.verify(data, signature.strip(), key)
    except signing.SignatureError as exc:
        raise PackError("signature", str(exc)) from exc
    try:
        manifest = json.loads(data.decode("utf-8"))
        version = str(manifest["version"])
        parse_version(version)
        files = manifest["files"]
        if manifest.get("format") != PACK_FORMAT or not isinstance(files, dict) or not files:
            raise ValueError("format")
        if not isinstance(manifest.get("runtime"), dict):
            raise ValueError("runtime")
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise PackError("damaged", "pack.json") from exc
    for relative, digest in files.items():
        path = PurePosixPath(relative)
        if (not isinstance(digest, str) or path.is_absolute() or ".." in path.parts
                or not path.parts or path.parts[0] != PACKAGE):
            raise PackError("unsafe", relative)
        if not _allowed(relative):
            raise PackError("filetype", relative)
    return manifest


def verify_folder(folder: Path, key: Optional[str] = None) -> dict:
    """Check an unpacked version: its signed file list, every file's
    checksum, and that it holds no file the list does not name. Python's own
    caches (__pycache__) are left out. Returns pack.json."""
    folder = Path(folder)
    try:
        data = (folder / MANIFEST).read_bytes()
        signature = (folder / SIGNATURE).read_text("ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise PackError("damaged", MANIFEST) from exc
    manifest = read_manifest(data, signature, key)
    listed = manifest["files"]
    seen = set()
    for current, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            file = Path(current) / name
            relative = file.relative_to(folder).as_posix()
            if relative in (MANIFEST, SIGNATURE):
                continue
            if file.is_symlink():
                raise PackError("unsafe", relative)
            if relative not in listed:
                raise PackError("unlisted", relative)
            if _sha256(file) != listed[relative]:
                raise PackError("damaged", relative)
            seen.add(relative)
        for name in dirs:
            if (Path(current) / name).is_symlink():
                raise PackError("unsafe", (Path(current) / name).relative_to(folder).as_posix())
    missing = set(listed) - seen
    if missing:
        raise PackError("damaged", sorted(missing)[0])
    return manifest


def unpack(pack: Path, target: Path, key: Optional[str] = None) -> dict:
    """Unpack a pack into ``target`` (which must not exist) with the same
    safe-unpacking checks as a .scmod (9.7): every entry stays inside the
    folder, no links, only allowed file types; then check it as a whole.
    On any problem nothing is left behind."""
    target = Path(target)
    root = target.resolve()
    try:
        with zipfile.ZipFile(pack) as zf:
            infos = zf.infolist()
            for info in infos:
                name = info.filename
                parts = PurePosixPath(name.replace("\\", "/")).parts
                is_link = stat.S_ISLNK(info.external_attr >> 16)
                absolute = name.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:", name))
                destination = (root / name).resolve()
                inside = destination == root or root in destination.parents
                if is_link or absolute or ".." in parts or not inside:
                    raise PackError("unsafe", name)
                if not info.is_dir() and name not in (MANIFEST, SIGNATURE) and not _allowed(name):
                    raise PackError("filetype", name)
            target.mkdir(parents=True)
            for info in infos:
                destination = (root / info.filename).resolve()
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, open(destination, "wb") as out:
                    shutil.copyfileobj(source, out)
        return verify_folder(target, key)
    except PackError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, ValueError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise PackError("damaged", str(exc)) from exc


# --- the versions kept in the author's folder ----------------------------------------------

class Versions:
    """``<app home>/app-versions``: the unpacked versions and ``state.json``::

        {"current": "0.6.8",      # the newest installed version, or null
         "previous": "0.6.7",     # the one before it, or null for the installed app
         "trying": null,          # set while a version starts, cleared once it has
         "failed": ["0.6.9"],     # versions that failed to start; never run again
         "notice": null}          # what to tell the author at the next start
    """

    def __init__(self, home: Path):
        self.root = Path(home) / VERSIONS_DIR

    # -- the state file ------------------------------------------------------------------
    def state(self) -> dict:
        state = {"current": None, "previous": None, "trying": None, "failed": [], "notice": None}
        try:
            stored = json.loads((self.root / STATE).read_text("utf-8"))
            if isinstance(stored, dict):
                for key in state:
                    if key in stored:
                        state[key] = stored[key]
        except (OSError, ValueError, UnicodeDecodeError):
            pass
        if not isinstance(state["failed"], list):
            state["failed"] = []
        return state

    def save(self, state: dict) -> None:
        """Written crash-safely: a new file next to the old one, then swapped."""
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / (STATE + ".new")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True), "utf-8")
        os.replace(temp, self.root / STATE)

    def folder(self, version: str) -> Path:
        return self.root / version

    def kept(self) -> List[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith("."))

    # -- installing ----------------------------------------------------------------------
    def install(self, pack: Path, key: Optional[str] = None, have: Optional[Dict[str, str]] = None,
                running: Optional[str] = None, expected: Optional[str] = None) -> dict:
        """Unpack a downloaded pack into a staging folder, check it, and make it
        the version that runs at the next start. The version running now
        (``running``, when it is a kept version) becomes the previous one; the
        installed app's own version is always there to go back to. Older
        versions are removed. Returns pack.json."""
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{os.getpid()}-{int(time.time() * 1000)}"
        manifest = unpack(pack, staging, key)
        version = manifest["version"]
        if expected is not None and version != expected:
            shutil.rmtree(staging, ignore_errors=True)
            raise PackError("version", version)
        if not runtime_matches(manifest["runtime"], have):
            shutil.rmtree(staging, ignore_errors=True)
            raise PackError("runtime", version)
        state = self.state()
        destination = self.folder(version)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
        if running and running != version and self.folder(running).is_dir():
            state["previous"] = running
        elif running != version:
            state["previous"] = None
        state["current"] = version
        state["failed"] = [v for v in state["failed"] if v != version]
        if state.get("trying") == version:
            state["trying"] = None
        self.save(state)
        self._tidy(state)
        return manifest

    def _tidy(self, state: dict) -> None:
        """Only the newest and the previous version are kept (F22.5)."""
        keep = {state.get("current"), state.get("previous")}
        for name in self.kept():
            if name not in keep:
                shutil.rmtree(self.folder(name), ignore_errors=True)
        for leftover in self.root.glob(".staging-*"):
            shutil.rmtree(leftover, ignore_errors=True)

    # -- choosing at start-up ------------------------------------------------------------------
    def usable(self, version: Optional[str], builtin: str, key: Optional[str] = None,
               have: Optional[Dict[str, str]] = None) -> bool:
        """A kept version runs only when it is newer than the installed app,
        verified, and made for this Python, Qt and Typst."""
        if not version or not newer(version, builtin):
            return False
        folder = self.folder(version)
        if not folder.is_dir():
            return False
        try:
            manifest = verify_folder(folder, key)
        except PackError:
            return False
        return manifest["version"] == version and runtime_matches(manifest["runtime"], have)

    def select(self, builtin: str, key: Optional[str] = None, have: Optional[Dict[str, str]] = None) -> Optional[str]:
        """F22.4, F22.5: the version to run now, or None for the installed
        app's own. A version that was started last time but never reported
        that it started is taken as failed: Scriptorum goes back to the
        previous one and leaves a notice for the author."""
        state = self.state()
        candidates = [v for v in (state.get("current"), state.get("previous")) if v]
        tried = state.get("trying")
        if tried and tried not in state["failed"]:
            state["failed"].append(tried)
            fallback = next((v for v in candidates if v != tried and v not in state["failed"]
                             and self.usable(v, builtin, key, have)), None)
            state["notice"] = {"kind": "failed", "version": tried, "back_to": fallback or builtin}
        state["trying"] = None
        chosen = None
        for version in candidates:
            if version in state["failed"]:
                continue
            if self.usable(version, builtin, key, have):
                chosen = version
                break
        state["trying"] = chosen
        self.save(state)
        self._tidy(state)
        return chosen

    def started(self, version: str) -> None:
        """The version opened its window: it is no longer on trial."""
        state = self.state()
        if state.get("trying") == version:
            state["trying"] = None
            self.save(state)

    def failed_now(self, version: str, builtin: str, key: Optional[str] = None,
                   have: Optional[Dict[str, str]] = None) -> Optional[str]:
        """A version raised an error while starting: mark it failed and return
        the version to run instead (None for the installed app's own)."""
        state = self.state()
        if version not in state["failed"]:
            state["failed"].append(version)
        state["trying"] = None
        fallback = next((v for v in (state.get("current"), state.get("previous"))
                         if v and v not in state["failed"] and self.usable(v, builtin, key, have)), None)
        state["notice"] = {"kind": "failed", "version": version, "back_to": fallback or builtin}
        state["trying"] = fallback
        self.save(state)
        return fallback

    def take_notice(self) -> Optional[dict]:
        state = self.state()
        notice = state.get("notice")
        if notice:
            state["notice"] = None
            self.save(state)
        return notice if isinstance(notice, dict) else None

    # -- going back by hand --------------------------------------------------------------------
    def back_target(self, running: str, builtin: str) -> Optional[str]:
        """Help ▸ Go back to version X: X is the previous kept version, or the
        installed app's own version. Nothing to go back to while the installed
        app's own version runs."""
        if running == builtin or not newer(running, builtin):
            return None
        state = self.state()
        previous = state.get("previous")
        if previous and previous != running and previous not in state["failed"] and self.folder(previous).is_dir():
            return previous
        return builtin

    def go_back(self, running: str, builtin: str) -> Optional[str]:
        """Make the next start run the previous version. The version left
        behind is removed, so only two are ever kept. Returns the version that
        will run, or None when there is nothing to go back to."""
        target = self.back_target(running, builtin)
        if target is None:
            return None
        state = self.state()
        state["current"] = target if target != builtin else None
        state["previous"] = None
        state["trying"] = None
        state["notice"] = {"kind": "back", "version": running, "back_to": target}
        self.save(state)
        # The folder left behind is removed at the next start, once it no
        # longer runs (F22.5: only two versions are kept).
        return target
