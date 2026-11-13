"""Module library and loader (design document section 9, F14).

A module is a folder (or a .scmod zip of that folder) with a ``module.json``
manifest. Installed modules live in the library, one folder per module and
version: ``<library>/<id>/<version>/``. Several versions can sit side by side;
an adventure always uses the exact version it pins.

Modules contain only data and Typst (3.1). Installation refuses any other
file type (9.1, 9.7).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, List, Optional

from scriptorum import __version__

MODULE_FORMAT = 1

KINDS = {
    "game-system",
    "element-kit",
    "theme",
    "adventure-language",
    "interface-language",
    "palette",
}
CONTENT_KINDS = {"game-system", "element-kit", "theme", "adventure-language"}

REQUIRED_FIELDS = [
    "id", "kind", "name", "version", "format", "app",
    "licence", "authors", "description", "requires",
]

# 9.2: an author prefix and a name joined by a dot, lower case, digits, hyphens.
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
RANGE_RE = re.compile(r"^(\d+)(?:\.(\d+|x))?(?:\.(\d+|x))?$")

# 9.1: JSON, Typst, SVG, PNG, OTF, TTF, WOFF2 and plain-text licence files.
ALLOWED_SUFFIXES = {".json", ".typ", ".svg", ".png", ".otf", ".ttf", ".woff2", ".txt"}
LICENCE_NAMES = re.compile(r"^(licen[cs]e|copying|ofl)([-_.].*)?$", re.IGNORECASE)

RESERVED_PREFIX = "scriptorum."

# F14 (decided 12 Nov 2026): the app falls back on these three, so they can be
# neither disabled nor removed.
ALWAYS_ON = ("scriptorum.core", "scriptorum.en", "scriptorum.claret-and-ink")
DISABLED_FILE = "disabled.json"
# 9.7 (decided 12 Nov 2026): a package imported by name, "@preview/..." or any
# other "@namespace/...", would make Typst try to download it (D9).
PACKAGE_IMPORT_LINE = re.compile(r'(?:import|include)\s*\(?\s*"(@[A-Za-z0-9_-]+/[^"]*)"')


class ModuleError(Exception):
    """A module was refused. ``key`` is an interface-string key (F15)."""

    def __init__(self, key: str, **details):
        super().__init__(f"{key} {details}")
        self.key = key
        self.details = details


def parse_version(text: str) -> tuple:
    m = VERSION_RE.match(text or "")
    if not m:
        raise ValueError(text)
    return tuple(int(p) for p in m.groups())


def version_matches(version: str, wanted: str) -> bool:
    """Version ranges in ``requires``: ``1.x``, ``1.2.x`` or an exact ``1.2.3``."""
    v = parse_version(version)
    m = RANGE_RE.match(wanted.strip())
    if not m:
        return False
    parts = [p for p in m.groups()]
    for i, part in enumerate(parts):
        if part is None or part == "x":
            return True
        if int(part) != v[i]:
            return False
    return True


@dataclass
class Module:
    id: str
    version: str
    kind: str
    name: str
    manifest: dict
    path: Path

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    # --- content helpers ---------------------------------------------------
    def labels(self, locale: str = "en") -> Dict[str, str]:
        file = self.path / "labels" / f"{locale}.json"
        if file.is_file():
            return json.loads(file.read_text("utf-8"))
        return {}

    def element_kinds(self) -> Dict[str, dict]:
        """9.4: one ``elements/<id>.json`` per element kind, in file order."""
        folder = self.path / "elements"
        kinds: Dict[str, dict] = {}
        if folder.is_dir():
            order = self.manifest.get("element_order")
            files = sorted(folder.glob("*.json"))
            if order:
                files.sort(key=lambda f: order.index(f.stem) if f.stem in order else len(order))
            for file in files:
                definition = json.loads(file.read_text("utf-8"))
                kinds[definition["id"]] = definition
        return kinds

    def turned_on(self) -> Optional[List[str]]:
        """Game systems (9.3, approved 5 Nov 2026): ``elements.json`` lists the
        element kinds of the core element kit the game system turns on."""
        file = self.path / "elements.json"
        if not file.is_file():
            return None
        data = json.loads(file.read_text("utf-8"))
        return list(data.get("on", []))

    def stat_blocks(self) -> Dict[str, dict]:
        """Game systems: ``stat-blocks/<element-id>.json`` describe the stats a
        stat block shows and the sections it uses (11.5)."""
        folder = self.path / "stat-blocks"
        blocks: Dict[str, dict] = {}
        if folder.is_dir():
            for file in sorted(folder.glob("*.json")):
                blocks[file.stem] = json.loads(file.read_text("utf-8"))
        return blocks

    def codex_types(self) -> Dict[str, dict]:
        """9.5: one ``codex-types/<id>.json`` per codex type. The core element
        kit holds the built-in types every game uses (Person, Place, Clue,
        decided 6 Nov 2026); a game system adds its own (Vaesen: Creature)."""
        folder = self.path / "codex-types"
        types: Dict[str, dict] = {}
        if folder.is_dir():
            for file in sorted(folder.glob("*.json")):
                definition = json.loads(file.read_text("utf-8"))
                types[definition["id"]] = {**definition, "module": self.id}
        return types

    def notation(self) -> dict:
        """Game systems: dice and check notation (9.3, 11.7)."""
        file = self.path / "notation.json"
        return json.loads(file.read_text("utf-8")) if file.is_file() else {}

    def handouts(self) -> dict:
        """Themes: paper styles and handwriting fonts for handouts (F6.5, 11.9)."""
        file = self.path / "handouts.json"
        return json.loads(file.read_text("utf-8")) if file.is_file() else {}

    def handwriting(self) -> List[dict]:
        """F6.7, F8 (M4): the handwriting hands an element kit bundles."""
        file = self.path / "handwriting.json"
        return json.loads(file.read_text("utf-8")).get("hands", []) if file.is_file() else []

    def palette(self) -> dict:
        """F16: a palette module's colours for light and dark mode."""
        file = self.path / "palette.json"
        return json.loads(file.read_text("utf-8")) if file.is_file() else {}

    def stylesheet(self) -> str:
        """F16: a palette module's own window stylesheet, if it has one."""
        file = self.path / "palette.css"
        return file.read_text("utf-8") if file.is_file() else ""

    def has_template(self, element_id: str) -> bool:
        return (self.path / "templates" / f"{element_id}.typ").is_file()

    def page_setup(self) -> dict:
        file = self.path / "page.json"
        return json.loads(file.read_text("utf-8")) if file.is_file() else {}

    def strings(self) -> Dict[str, str]:
        """Interface-language modules: every ``strings/<area>.json`` merged."""
        merged: Dict[str, str] = {}
        folder = self.path / "strings"
        for file in sorted(folder.glob("*.json")):
            area = file.stem
            for key, value in json.loads(file.read_text("utf-8")).items():
                merged[f"{area}.{key}"] = value
        return merged


def validate_folder(src: Path) -> dict:
    """Checks 9.7.1 (manifest) and 9.7.2 (file types). Returns the manifest."""
    src = Path(src)
    manifest_file = src / "module.json"
    if not manifest_file.is_file():
        raise ModuleError("error.module.noManifest", path=str(src))
    try:
        manifest = json.loads(manifest_file.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ModuleError("error.module.badManifest", path=str(src)) from exc

    missing = [f for f in REQUIRED_FIELDS if f not in manifest]
    if missing:
        raise ModuleError("error.module.missingField", field=", ".join(missing))
    if not ID_RE.match(manifest["id"]):
        raise ModuleError("error.module.badId", id=manifest["id"])
    if manifest["kind"] not in KINDS:
        raise ModuleError("error.module.badKind", kind=manifest["kind"])
    try:
        parse_version(manifest["version"])
        parse_version(manifest["app"])
    except ValueError as exc:
        raise ModuleError("error.module.badVersion", version=str(exc)) from exc
    if manifest["format"] != MODULE_FORMAT:
        raise ModuleError("error.module.badFormat", format=manifest["format"])
    if parse_version(manifest["app"]) > parse_version(_app_version()):
        raise ModuleError("error.module.needsNewerApp", id=manifest["id"], app=manifest["app"])
    if not isinstance(manifest["requires"], list):
        raise ModuleError("error.module.missingField", field="requires")
    for req in manifest["requires"]:
        if not isinstance(req, dict) or "id" not in req or "version" not in req:
            raise ModuleError("error.module.badRequires", id=manifest["id"])
        if not RANGE_RE.match(str(req["version"])):
            raise ModuleError("error.module.badRequires", id=manifest["id"])

    for file in src.rglob("*"):
        if file.is_dir():
            continue
        if file.is_symlink():
            raise ModuleError("error.module.forbiddenFile", file=str(file.relative_to(src)))
        if file.suffix.lower() in ALLOWED_SUFFIXES:
            continue
        # F16: a palette may carry its own window stylesheet, palette.css. It
        # changes only the window, and nothing in it may reach the internet.
        if manifest["kind"] == "palette" and file.relative_to(src).as_posix() == "palette.css":
            from scriptorum.core.palettes import remote_address
            address = remote_address(file.read_text("utf-8", errors="replace"))
            if address:
                raise ModuleError("error.module.remoteStylesheet", address=address)
            continue
        if file.suffix == "" and LICENCE_NAMES.match(file.name):
            continue
        raise ModuleError("error.module.forbiddenFile", file=str(file.relative_to(src)))
    return manifest


_IMPORT_CACHE: Dict[str, tuple] = {}


def package_import(folder: Path) -> Optional[dict]:
    """9.7: the first place a module's Typst files import a package by name,
    as ``{"file", "line", "package"}``, or None. Builds call this every time,
    so the answer is kept until a Typst file of the module changes."""
    folder = Path(folder)
    files = sorted(folder.rglob("*.typ"))
    try:
        stamp = tuple((f.as_posix(), f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    except OSError:
        stamp = None
    cached = _IMPORT_CACHE.get(str(folder))
    if stamp is not None and cached is not None and cached[0] == stamp:
        return cached[1]
    found = _scan_imports(folder, files)
    if stamp is not None:
        _IMPORT_CACHE[str(folder)] = (stamp, found)
    return found


def _scan_imports(folder: Path, files) -> Optional[dict]:
    for file in files:
        if not file.is_file():
            continue
        try:
            text = file.read_text("utf-8", errors="replace")
        except OSError:
            continue
        if '"@' not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            match = PACKAGE_IMPORT_LINE.search(line)
            if match:
                return {"file": file.relative_to(folder).as_posix(), "line": number, "package": match.group(1)}
    return None


def check_package_imports(folder: Path) -> None:
    found = package_import(folder)
    if found:
        raise ModuleError("error.module.packageImport", **found)


def unpack_scmod(file: Path, target: Path) -> None:
    """9.1, 9.7 (decided 12 Nov 2026): unpack a ``.scmod`` file, every entry
    inside ``target``. An entry whose path would land outside it (``../`` or
    an absolute path), or a link, refuses the whole module and names the
    entry. The check compares resolved paths, not path text."""
    root = Path(target).resolve()
    with zipfile.ZipFile(file) as zf:
        infos = zf.infolist()
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name.replace("\\", "/")).parts
            is_link = stat.S_ISLNK(info.external_attr >> 16)
            absolute = name.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:", name))
            destination = (root / name).resolve()
            inside = destination == root or root in destination.parents
            if is_link or absolute or ".." in parts or not inside:
                raise ModuleError("error.module.unsafeEntry", entry=name)
        for info in infos:
            destination = (root / info.filename).resolve()
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, open(destination, "wb") as out:
                shutil.copyfileobj(source, out)


def _app_version() -> str:
    # Development versions below 1.0.0 load modules written for 1.0.0, since
    # version 1 is what they are built for.
    return "1.0.0" if parse_version(__version__) < (1, 0, 0) else __version__


class Library:
    """The module library (F14): installed once, shared by every adventure."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.last_install = "installed"  # or "already": the file was identical

    # --- what is installed ----------------------------------------------------
    def _disabled_keys(self) -> set:
        try:
            data = json.loads((self.root / DISABLED_FILE).read_text("utf-8"))
            return {k for k in data if isinstance(k, str)}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return set()

    def installed(self, include_disabled: bool = False) -> List[Module]:
        """The modules that can be used. A disabled module (F14) stays on the
        computer but is offered nowhere, so it is left out unless asked for."""
        modules = []
        disabled = None if include_disabled else self._disabled_keys()
        for manifest_file in sorted(self.root.glob("*/*/module.json")):
            if manifest_file.parent.parent.name.startswith("."):
                continue  # a staging folder of an installation in progress
            try:
                manifest = json.loads(manifest_file.read_text("utf-8"))
                module = Module(
                    id=manifest["id"],
                    version=manifest["version"],
                    kind=manifest["kind"],
                    name=manifest["name"],
                    manifest=manifest,
                    path=manifest_file.parent,
                )
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError, OSError):
                continue  # a broken folder copied in by hand is not a module
            if disabled and module.key in disabled:
                continue
            modules.append(module)
        return modules

    def get(self, module_id: str, version: str, include_disabled: bool = False) -> Optional[Module]:
        for module in self.installed(include_disabled):
            if module.id == module_id and module.version == version:
                return module
        return None

    def newest(self, module_id: str) -> Optional[Module]:
        candidates = [m for m in self.installed() if m.id == module_id]
        if not candidates:
            return None
        return max(candidates, key=lambda m: parse_version(m.version))

    def of_kind(self, kind: str) -> List[Module]:
        return [m for m in self.installed() if m.kind == kind]

    def requirement_met(self, req: dict, include_disabled: bool = False) -> bool:
        return any(
            m.id == req["id"] and version_matches(m.version, str(req["version"]))
            for m in self.installed(include_disabled)
        )

    # --- disable and remove (F14, decided 12 Nov 2026) --------------------------
    def is_disabled(self, module_id: str, version: str) -> bool:
        return f"{module_id}@{version}" in self._disabled_keys()

    def set_disabled(self, module_id: str, version: str, disabled: bool) -> None:
        """Disabling keeps the module on the computer but offers it nowhere."""
        if self.get(module_id, version, include_disabled=True) is None:
            raise ModuleError("error.module.notInstalled", id=module_id, version=version)
        if disabled and module_id in ALWAYS_ON:
            raise ModuleError("error.module.alwaysOn", id=module_id)
        keys = self._disabled_keys()
        key = f"{module_id}@{version}"
        if disabled:
            keys.add(key)
        else:
            keys.discard(key)
        self._write_disabled(keys)

    def _write_disabled(self, keys: set) -> None:
        store = self.root / DISABLED_FILE
        if keys:
            store.write_text(json.dumps(sorted(keys), indent=2), "utf-8")
        else:
            store.unlink(missing_ok=True)

    def required_by(self, module_id: str, version: str) -> List[Module]:
        """Installed modules that need this one and have no other installed
        version of it to fall back on."""
        others = [m for m in self.installed(True) if not (m.id == module_id and m.version == version)]
        result = []
        for module in others:
            for req in module.manifest.get("requires", []):
                if req["id"] != module_id or not version_matches(version, str(req["version"])):
                    continue
                if not any(o.id == module_id and version_matches(o.version, str(req["version"])) for o in others):
                    result.append(module)
        return result

    def discard(self, module: Module) -> None:
        """Take a module out of the library without asking: an installation
        whose checks failed leaves nothing behind (9.7)."""
        shutil.rmtree(module.path, ignore_errors=True)
        try:
            module.path.parent.rmdir()
        except OSError:
            pass

    def remove(self, module_id: str, version: str, bundled_dir: Optional[Path] = None) -> None:
        """Remove one version of a module from the library (F14). A module
        bundled with the app is never removed: the app would install it again
        at the next start."""
        module = self.get(module_id, version, include_disabled=True)
        if module is None:
            raise ModuleError("error.module.notInstalled", id=module_id, version=version)
        if module_id in ALWAYS_ON:
            raise ModuleError("error.module.alwaysOn", id=module_id)
        if is_bundled(module, bundled_dir):
            raise ModuleError("error.module.bundled", id=module_id, name=module.name)
        needing = self.required_by(module_id, version)
        if needing:
            raise ModuleError("error.module.requiredBy", name=module.name, by=", ".join(m.name for m in needing))
        shutil.rmtree(module.path)
        try:
            module.path.parent.rmdir()  # the last version: the module's folder goes too
        except OSError:
            pass
        keys = self._disabled_keys()
        if module.key in keys:
            keys.discard(module.key)
            self._write_disabled(keys)

    def install_folder(
        self,
        src: Path,
        checker: Optional[Callable[[Module], None]] = None,
        allow_reserved: bool = False,
        refresh: bool = False,
    ) -> Module:
        """Validate and copy a module folder into the library (9.7)."""
        manifest = validate_folder(src)
        if manifest["id"].startswith(RESERVED_PREFIX) and not allow_reserved:
            raise ModuleError("error.module.reservedPrefix", id=manifest["id"])
        # 9.7 (decided 12 Nov 2026): no package imported by name.
        check_package_imports(src)
        for req in manifest["requires"]:
            if not self.requirement_met(req, include_disabled=allow_reserved):
                raise ModuleError(
                    "error.module.requirementMissing",
                    id=manifest["id"], requires=req["id"], version=req["version"],
                )
        self.last_install = "installed"
        existing = self.get(manifest["id"], manifest["version"], include_disabled=True)
        if existing is not None:
            same = folder_digest(existing.path) == folder_digest(src)
            if same:
                # F14: an identical file says it is already installed.
                self.last_install = "already"
                return existing
            if not refresh:
                # F14 (decided 12 Nov 2026): adventures pin exact versions, so
                # one version number never stands for two different contents.
                raise ModuleError("error.module.sameVersion", id=manifest["id"],
                                  name=manifest["name"], version=manifest["version"])
            # A bundled module changed while keeping its version (development
            # builds before version 1): the app's copy replaces the old one.
            shutil.rmtree(existing.path)
        target = self.root / manifest["id"] / manifest["version"]
        staging = Path(tempfile.mkdtemp(prefix=".install-", dir=self.root))
        try:
            shutil.copytree(src, staging / "m")
            module = Module(
                id=manifest["id"], version=manifest["version"], kind=manifest["kind"],
                name=manifest["name"], manifest=manifest, path=staging / "m",
            )
            if checker is not None:
                checker(module)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging / "m"), str(target))
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self.get(manifest["id"], manifest["version"], include_disabled=True)

    def install_scmod(self, file: Path, checker=None) -> Module:
        """Install a ``.scmod`` package (9.1)."""
        tmp = Path(tempfile.mkdtemp(prefix=".scmod-", dir=self.root))
        try:
            unpack_scmod(file, tmp)
            return self.install_folder(tmp, checker=checker)
        except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as exc:
            raise ModuleError("error.module.notModule", path=str(file)) from exc
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def install_bundled(self, bundled_dir: Path, checker=None) -> List[Module]:
        """Install the modules that ship with the app, dependencies first."""
        pending = [p for p in sorted(Path(bundled_dir).iterdir()) if (p / "module.json").is_file()]
        installed: List[Module] = []
        for _ in range(len(pending) + 1):
            progress = False
            for folder in list(pending):
                manifest = json.loads((folder / "module.json").read_text("utf-8"))
                if all(self.requirement_met(r, include_disabled=True) for r in manifest.get("requires", [])):
                    installed.append(self.install_folder(folder, checker=checker, allow_reserved=True, refresh=True))
                    pending.remove(folder)
                    progress = True
            if not pending or not progress:
                break
        if pending:
            raise ModuleError("error.module.requirementMissing", id=pending[0].name, requires="?", version="?")
        return installed


def is_bundled(module: Module, bundled_dir: Optional[Path] = None) -> bool:
    """Whether this exact module and version comes with the app (F14)."""
    if bundled_dir is None:
        from scriptorum import paths
        bundled_dir = paths.BUNDLED_MODULES_DIR
    manifest_file = Path(bundled_dir) / module.id / "module.json"
    try:
        return json.loads(manifest_file.read_text("utf-8")).get("version") == module.version
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def folder_digest(folder: Path) -> str:
    """A checksum of every file in a module folder, ignoring build stamps."""
    digest = hashlib.sha256()
    for file in sorted(Path(folder).rglob("*")):
        if file.is_file() and not file.name.startswith("."):
            digest.update(file.relative_to(folder).as_posix().encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def pack_scmod(src: Path, out_file: Path) -> Path:
    """Pack a module folder into a ``.scmod`` file (9.1)."""
    validate_folder(src)
    out_file = Path(out_file)
    with zipfile.ZipFile(out_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(Path(src).rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(src).as_posix())
    return out_file


def iter_requirements(module: Module) -> Iterable[dict]:
    return module.manifest.get("requires", [])


def theme_offered_for(library: "Library", theme: Module, game_system: Module) -> bool:
    """F8 general themes (decided 6 Nov 2026, M4): a theme whose manifest
    requires only element kits, and no game system, is offered for every game
    system; a theme that requires a game system is offered only for that one."""
    requires = theme.manifest.get("requires", [])
    game_reqs = []
    for req in requires:
        kinds = {m.kind for m in library.installed() if m.id == req["id"]}
        if "game-system" in kinds or not kinds and req["id"] == game_system.id:
            game_reqs.append(req)
    if not game_reqs:
        return all(library.requirement_met(r) for r in requires)
    return any(r["id"] == game_system.id and version_matches(game_system.version, r["version"]) for r in game_reqs)
