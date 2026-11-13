"""The .scav adventure file (design document section 4 and F1).

A .scav file is a zip archive with a fixed folder structure:

    manifest.json   format version, app version, title, game system, theme,
                    pinned content modules, chapter order, dates
    settings.json   adventure settings page values (F7.3)
    text/           one Typst file per chapter
    codex/ codex/types/ maps/ handouts/ assets/images/ assets/fonts/

Saving is crash-safe (F1.1): a complete new file is written next to the old
one and only then moved over it. Files from an older format are migrated in
memory (F1.2); files from a newer format are refused untouched (F1.3).

The same structure can be an ordinary unpacked folder (F2.4), for authors
who use Git. A folder is saved file by file, each one crash-safely, and only
files whose content changed are rewritten.

A file name inside an adventure can never reach outside it (F2.10).
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from scriptorum import __version__

FORMAT_VERSION = 1

FOLDERS = [
    "text/",
    "codex/",
    "codex/types/",
    "maps/",
    "handouts/",
    "assets/images/",
    "assets/fonts/",
]

# Migrations from an older format version to the next one, keyed by the
# version they start from. Each takes (manifest, files) and returns both.
# Format 1 is the first format, so none are registered yet.
MIGRATIONS: Dict[int, Callable[[dict, Dict[str, bytes]], tuple]] = {}


class ScavError(Exception):
    """A .scav file could not be read or written. The message key is an
    interface-string key (F15); ``details`` fills its placeholders."""

    def __init__(self, key: str, **details):
        super().__init__(key)
        self.key = key
        self.details = details


class NewerFormatError(ScavError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ModuleRef:
    id: str
    version: str

    def to_json(self) -> dict:
        return {"id": self.id, "version": self.version}


@dataclass
class Adventure:
    manifest: dict
    settings: dict = field(default_factory=dict)
    files: Dict[str, bytes] = field(default_factory=dict)
    path: Optional[Path] = None
    migrated_from: Optional[int] = None
    is_folder: bool = False

    # --- manifest helpers -------------------------------------------------
    @property
    def title(self) -> str:
        return self.manifest.get("title", "")

    @property
    def chapters(self) -> List[str]:
        return list(self.manifest.get("chapters", []))

    @property
    def game_system(self) -> ModuleRef:
        gs = self.manifest["game_system"]
        return ModuleRef(gs["id"], gs["version"])

    @property
    def theme(self) -> ModuleRef:
        th = self.manifest["theme"]
        return ModuleRef(th["id"], th["version"])

    @property
    def modules(self) -> List[ModuleRef]:
        return [ModuleRef(m["id"], m["version"]) for m in self.manifest.get("modules", [])]

    def chapter_text(self, chapter: str) -> str:
        return self.files[chapter].decode("utf-8")

    def set_chapter_text(self, chapter: str, text: str) -> None:
        if chapter not in self.manifest["chapters"]:
            raise KeyError(chapter)
        self.files[chapter] = text.encode("utf-8")

    def add_file(self, folder: str, name: str, data: bytes) -> str:
        """Copy a file into the adventure (F1.4, F4.6, F11.2). Returns the
        stored name; an existing file with other content gets a new name."""
        stem, dot, suffix = Path(name).name.partition(".")
        clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "file"
        candidate = f"{folder}{clean}{dot}{suffix.lower()}"
        number = 2
        while candidate in self.files and self.files[candidate] != data:
            candidate = f"{folder}{clean}-{number}{dot}{suffix.lower()}"
            number += 1
        self.files[candidate] = data
        return candidate

    def files_in(self, folder: str) -> List[str]:
        return sorted(n for n in self.files if n.startswith(folder) and not n.endswith("/"))


def safe_name(name: str) -> bool:
    """F2.10: a name inside an adventure stays inside it."""
    parts = name.replace("\\", "/").split("/")
    return bool(name) and not name.startswith("/") and ".." not in parts and ":" not in parts[0]


def new_adventure(
    title: str,
    game_system: ModuleRef,
    theme: ModuleRef,
    other_modules: List[ModuleRef],
    first_chapter_text: str,
) -> Adventure:
    """File → New (F2.1)."""
    modules = [*other_modules, game_system, theme]
    seen, pinned = set(), []
    for ref in modules:
        if ref.id not in seen:
            seen.add(ref.id)
            pinned.append(ref.to_json())
    now = _now()
    manifest = {
        "format": FORMAT_VERSION,
        "app": __version__,
        "title": title,
        "game_system": game_system.to_json(),
        "theme": theme.to_json(),
        "modules": pinned,
        "chapters": ["text/chapter-01.typ"],
        "created": now,
        "modified": now,
    }
    return Adventure(
        manifest=manifest,
        settings={},
        files={"text/chapter-01.typ": first_chapter_text.encode("utf-8")},
    )


def load(path: Path) -> Adventure:
    """Open a .scav file or an unpacked adventure folder (F1.2, F1.3, F2.4)."""
    path = Path(path)
    if path.is_dir():
        return _load_folder(path)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                raise ScavError("error.scav.notAdventure", path=str(path))
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            settings = {}
            if "settings.json" in names:
                settings = json.loads(zf.read("settings.json").decode("utf-8"))
            unsafe = [n for n in names if not safe_name(n)]
            if unsafe:
                raise ScavError("error.scav.unsafeName", path=str(path), name=unsafe[0])
            files = {
                n: zf.read(n)
                for n in names
                if not n.endswith("/") and n not in ("manifest.json", "settings.json")
            }
    except zipfile.BadZipFile as exc:
        raise ScavError("error.scav.notAdventure", path=str(path)) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ScavError("error.scav.damaged", path=str(path)) from exc
    return _finish_load(path, manifest, settings, files, is_folder=False)


def _load_folder(path: Path) -> Adventure:
    manifest_file = path / "manifest.json"
    if not manifest_file.is_file():
        raise ScavError("error.scav.notAdventure", path=str(path))
    try:
        manifest = json.loads(manifest_file.read_text("utf-8"))
        settings_file = path / "settings.json"
        settings = json.loads(settings_file.read_text("utf-8")) if settings_file.is_file() else {}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ScavError("error.scav.damaged", path=str(path)) from exc
    files: Dict[str, bytes] = {}
    for folder in FOLDERS:
        base = path / folder
        if not base.is_dir():
            continue
        for file in sorted(base.rglob("*")):
            if file.is_symlink():
                continue  # F2.10: never follow a link out of the adventure
            if file.is_file():
                files[file.relative_to(path).as_posix()] = file.read_bytes()
    return _finish_load(path, manifest, settings, files, is_folder=True)


def _finish_load(path: Path, manifest: dict, settings: dict, files: Dict[str, bytes], is_folder: bool) -> Adventure:
    version = manifest.get("format")
    if not isinstance(version, int):
        raise ScavError("error.scav.damaged", path=str(path))
    if version > FORMAT_VERSION:
        raise NewerFormatError(
            "error.scav.newerFormat", path=str(path), found=version, supported=FORMAT_VERSION
        )
    migrated_from = None
    while version < FORMAT_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ScavError("error.scav.cannotMigrate", path=str(path), found=version)
        migrated_from = migrated_from if migrated_from is not None else version
        manifest, files = step(manifest, files)
        version += 1
        manifest["format"] = version

    for chapter in manifest.get("chapters", []):
        if chapter not in files:
            raise ScavError("error.scav.missingChapter", path=str(path), chapter=chapter)

    return Adventure(
        manifest=manifest, settings=settings, files=files, path=path,
        migrated_from=migrated_from, is_folder=is_folder,
    )


def _zip_bytes(adventure: Adventure) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(adventure.manifest, ensure_ascii=False, indent=2) + "\n")
        zf.writestr("settings.json", json.dumps(adventure.settings, ensure_ascii=False, indent=2) + "\n")
        for folder in FOLDERS:
            zf.writestr(zipfile.ZipInfo(folder), b"")
        for name in sorted(adventure.files):
            zf.writestr(name, adventure.files[name])
    return buf.getvalue()


def _write_atomic(target: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def save_folder(adventure: Adventure, target: Path) -> Path:
    """F2.4: save as an unpacked folder. Each file is written crash-safely
    and only when its content changed, so Git sees only the changed lines."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    adventure.manifest["format"] = FORMAT_VERSION
    adventure.manifest["app"] = __version__
    adventure.manifest["modified"] = _now()
    wanted = {
        "manifest.json": (json.dumps(adventure.manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "settings.json": (json.dumps(adventure.settings, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        **{name: data for name, data in adventure.files.items() if safe_name(name)},
    }
    for folder in FOLDERS:
        (target / folder).mkdir(parents=True, exist_ok=True)
    for name, data in wanted.items():
        file = target / name
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.is_file() and file.read_bytes() == data:
            continue
        _write_atomic(file, data)
    # Files the adventure no longer has (only inside its own folders).
    for folder in FOLDERS:
        for file in sorted((target / folder).rglob("*")):
            if file.is_file() and not file.is_symlink() and file.relative_to(target).as_posix() not in wanted:
                file.unlink()
    adventure.path = target
    adventure.is_folder = True
    adventure.migrated_from = None
    return target


def save(adventure: Adventure, path: Optional[Path] = None, as_folder: Optional[bool] = None) -> Path:
    """Save crash-safely (F1.1): write a complete new file next to the old
    one, flush it to disk, then replace the old file in one step."""
    target = Path(path or adventure.path or "")
    if not str(target):
        raise ScavError("error.scav.noPath")
    if as_folder or (as_folder is None and (target.is_dir() or (adventure.is_folder and target == adventure.path))):
        return save_folder(adventure, target)
    target = target.with_suffix(".scav") if target.suffix.lower() != ".scav" else target
    target.parent.mkdir(parents=True, exist_ok=True)

    adventure.manifest["format"] = FORMAT_VERSION
    adventure.manifest["app"] = __version__
    adventure.manifest["modified"] = _now()
    data = _zip_bytes(adventure)

    fd, tmp_name = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    adventure.path = target
    adventure.is_folder = False
    adventure.migrated_from = None
    return target
