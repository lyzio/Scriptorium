"""The module manager (design document F14; built in M6 part A).

Settings ▸ Modules installs a module from a ``.scmod`` file with every check
of 9.7, disables and enables modules, removes them, saves an installed module
as a ``.scmod`` file to send to someone, and shows which adventures on the
Recent files list use each content module. It uses no internet access (D9).

Decided 12 November 2026:

- The adventures a module's warning names are those on the Recent files list
  (the last ten, F2.1). The app keeps no other record of adventures.
- Modules bundled with the app can be disabled but not removed; the core
  element kit, the English interface and the Claret & Ink palette can be
  neither. A palette or interface language in use cannot be disabled.
- No modules are ever packed into an adventure. A module that is not bundled
  is saved as its own ``.scmod`` file instead.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from scriptorum import paths
from scriptorum.core import fonts
from scriptorum.core.appsettings import AppSettings, chosen_palette
from scriptorum.core.modules import (
    ALWAYS_ON, CONTENT_KINDS, Library, Module, ModuleError, is_bundled, pack_scmod, theme_offered_for,
)

FONT_SUFFIXES = {".otf", ".ttf"}


# --- which adventures use a module (F14) ---------------------------------------------
def adventure_modules(path: Path) -> Optional[dict]:
    """The title of an adventure and the modules it pins, read from its
    manifest only (a ``.scav`` file or an unpacked folder). None when it
    cannot be read."""
    path = Path(path)
    try:
        if path.is_dir():
            manifest = json.loads((path / "manifest.json").read_text("utf-8"))
        else:
            with zipfile.ZipFile(path) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        pinned = {(m["id"], m["version"]) for m in manifest.get("modules", [])}
        for key in ("game_system", "theme"):
            if isinstance(manifest.get(key), dict):
                pinned.add((manifest[key]["id"], manifest[key]["version"]))
        return {"title": manifest.get("title") or path.stem, "path": str(path), "modules": pinned}
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile):
        return None


def recent_adventures(recent_paths: List[str]) -> List[dict]:
    """The adventures on the Recent files list that still exist."""
    result = []
    for entry in recent_paths:
        found = adventure_modules(Path(entry))
        if found is not None:
            result.append(found)
    return result


def used_by(module: Module, adventures: List[dict]) -> List[dict]:
    return [{"title": a["title"], "path": a["path"]} for a in adventures
            if (module.id, module.version) in a["modules"]]


# --- the list --------------------------------------------------------------------------
def in_use(module: Module, library: Library, settings: Optional[AppSettings]) -> bool:
    """Whether the app itself is using this palette or interface language."""
    if settings is None:
        return False
    if module.kind == "palette":
        chosen = chosen_palette(library, settings)
        return chosen is not None and chosen.id == module.id and chosen.version == module.version
    if module.kind == "interface-language":
        return settings.get("language") == module.id
    return False


def module_list(library: Library, recent_paths: List[str], settings: Optional[AppSettings] = None,
                bundled_dir: Optional[Path] = None) -> List[dict]:
    """Every installed module, disabled ones included, for Settings ▸ Modules."""
    adventures = recent_adventures(recent_paths)
    disabled = library._disabled_keys()
    rows = []
    for module in sorted(library.installed(True), key=lambda m: (m.kind, m.name.lower(), m.id, m.version)):
        bundled = is_bundled(module, bundled_dir)
        always = module.id in ALWAYS_ON
        using = in_use(module, library, settings)
        is_off = module.key in disabled
        rows.append({
            "id": module.id, "version": module.version, "name": module.name, "kind": module.kind,
            "description": module.manifest.get("description", ""),
            "authors": module.manifest.get("authors", []),
            "licence": module.manifest.get("licence", ""),
            "content": module.kind in CONTENT_KINDS,
            "bundled": bundled, "disabled": is_off, "inUse": using,
            # Why a button is greyed out: "alwaysOn", "inUse" or "bundled".
            "canDisable": not always and not (using and not is_off),
            "disableReason": "alwaysOn" if always else ("inUse" if using and not is_off else ""),
            "canRemove": not always and not bundled and not using,
            "removeReason": "alwaysOn" if always else ("bundled" if bundled else ("inUse" if using else "")),
            "canSave": not bundled,
            "usedBy": used_by(module, adventures) if module.kind in CONTENT_KINDS else [],
        })
    return rows


# --- the checks on installation (9.7) -----------------------------------------------------
def check_fonts(module: Module) -> None:
    """9.7.3: every font of the module passes the font guard (F11)."""
    for file in sorted(module.path.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in FONT_SUFFIXES:
            continue
        name = file.relative_to(module.path).as_posix()
        try:
            check = fonts.check_font(file.read_bytes())
        except Exception as exc:  # not a font at all
            raise ModuleError("error.module.fontUnreadable", file=name) from exc
        if not check.ok:
            raise ModuleError("error.module.fontRefused", file=name, family=check.family or name)


def check_json(module: Module) -> None:
    """Every JSON file of the module can be read."""
    for file in sorted(module.path.rglob("*.json")):
        try:
            json.loads(file.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModuleError("error.module.badJson", file=file.relative_to(module.path).as_posix()) from exc


def check_renderers(library: Library, module: Module) -> None:
    """9.7.7: a theme has a renderer, or relies on the generic frame, for
    every element kind of the game systems it supports."""
    from scriptorum.core.build import Builder
    from scriptorum.core.scav import ModuleRef, new_adventure

    if module.kind != "theme" or (module.path / "templates" / "_generic.typ").is_file():
        return
    kits = [ModuleRef(m.id, m.version) for m in library.of_kind("element-kit")]
    with tempfile.TemporaryDirectory(prefix="scriptorum-check-") as folder:
        for game in library.of_kind("game-system"):
            if not theme_offered_for(library, module, game):
                continue
            adventure = new_adventure("Test", ModuleRef(game.id, game.version), ModuleRef(module.id, module.version), kits, "")
            kinds = Builder(library, Path(folder) / game.id).element_kinds(adventure)
            for kind_id, definition in kinds.items():
                if definition.get("category") == "layout" or definition.get("always_on"):
                    continue
                if not module.has_template(kind_id):
                    raise ModuleError("error.module.noRenderer", theme=module.name, element=kind_id, game=game.name)


def compile_problems(library: Library, module: Module) -> List:
    """9.7.5: the module's Typst files compile against the built-in test
    adventure. A theme is built with every game system it is offered for, a
    game system with the themes offered for it, an element kit with the
    standard game system and theme."""
    from scriptorum.core.build import Builder, test_adventure_for
    from scriptorum.core.scav import ModuleRef, new_adventure

    if module.kind not in ("theme", "game-system", "element-kit"):
        return []
    kits: Dict[str, Module] = {}
    for kit in library.of_kind("element-kit"):
        if kit.id not in kits or kit.version > kits[kit.id].version:
            kits[kit.id] = kit
    if module.kind == "element-kit":
        kits[module.id] = module
    kit_refs = [ModuleRef(m.id, m.version) for m in kits.values()]
    pairs = []
    themes, games = library.of_kind("theme"), library.of_kind("game-system")
    if module.kind == "theme":
        pairs = [(g, module) for g in games if theme_offered_for(library, module, g)]
    elif module.kind == "game-system":
        offered = sorted((t for t in themes if theme_offered_for(library, t, module)),
                         key=lambda t: (not t.manifest.get("standard"), t.name))
        pairs = [(module, offered[0])] if offered else []
    else:
        standard_game = next((g for g in games if g.manifest.get("standard")), games[0] if games else None)
        standard_theme = next((t for t in themes if t.manifest.get("standard")), None)
        if standard_game and standard_theme:
            pairs = [(standard_game, standard_theme)]
    problems = []
    with tempfile.TemporaryDirectory(prefix="scriptorum-check-") as folder:
        for number, (game, theme) in enumerate(pairs):
            adventure = new_adventure("Test", ModuleRef(game.id, game.version), ModuleRef(theme.id, theme.version),
                                      kit_refs, "")
            builder = Builder(library, Path(folder) / f"b{number}")
            adventure.set_chapter_text(adventure.chapters[0], test_adventure_for(builder.element_kinds(adventure), game.notation()))
            result = builder.build(adventure, "pdf")
            problems.extend(result.errors)
            if problems:
                break
    return problems


def run_checks(library: Library, module: Module, localize=None) -> None:
    """The checks of 9.7 that need the module in the library: fonts, JSON,
    renderers and compiling. Raises ModuleError with the reason."""
    check_json(module)
    check_fonts(module)
    check_renderers(library, module)
    problems = compile_problems(library, module)
    if problems:
        problem = problems[0]
        if problem.key == "error.build.timeLimit":
            # 9.7, F7.1 (M6 part B): a module whose build never finishes is refused.
            raise ModuleError("error.module.timeLimit", name=module.name, seconds=problem.details.get("seconds", 60))
        message = localize(problem) if localize else (problem.message or problem.key)
        raise ModuleError("error.module.compile", name=module.name, message=message)


# --- install, disable, remove, save ---------------------------------------------------------
def install(library: Library, file: Path, localize=None) -> dict:
    """Install a module from a ``.scmod`` file (F14, 9.7). When any check
    fails the module is refused and nothing is left in the library."""
    module = library.install_scmod(Path(file))
    if library.last_install == "already":
        return {"status": "already", "module": module}
    try:
        run_checks(library, module, localize)
    except Exception:
        library.discard(module)
        raise
    return {"status": "installed", "module": module}


def set_disabled(library: Library, module_id: str, version: str, disabled: bool,
                 settings: Optional[AppSettings] = None) -> None:
    module = library.get(module_id, version, include_disabled=True)
    if module is None:
        raise ModuleError("error.module.notInstalled", id=module_id, version=version)
    if disabled and module_id in ALWAYS_ON:
        raise ModuleError("error.module.alwaysOn", id=module_id)
    if disabled and in_use(module, library, settings):
        raise ModuleError("error.module.inUse", name=module.name)
    library.set_disabled(module_id, version, disabled)


def remove(library: Library, module_id: str, version: str, settings: Optional[AppSettings] = None,
           bundled_dir: Optional[Path] = None) -> None:
    module = library.get(module_id, version, include_disabled=True)
    if module is None:
        raise ModuleError("error.module.notInstalled", id=module_id, version=version)
    if module_id in ALWAYS_ON:
        raise ModuleError("error.module.alwaysOn", id=module_id)
    if in_use(module, library, settings):
        raise ModuleError("error.module.inUse", name=module.name)
    library.remove(module_id, version, bundled_dir=bundled_dir)


def save_as_scmod(library: Library, module_id: str, version: str, target: Path,
                  bundled_dir: Optional[Path] = None) -> Path:
    """Save as .scmod file… (F14, decided 12 Nov 2026): write an installed
    module as one file to send along with an adventure. Bundled modules need
    no file, since every Scriptorum has them."""
    module = library.get(module_id, version, include_disabled=True)
    if module is None:
        raise ModuleError("error.module.notInstalled", id=module_id, version=version)
    if is_bundled(module, bundled_dir):
        raise ModuleError("error.module.bundled", id=module_id, name=module.name)
    target = Path(target)
    if target.suffix.lower() != ".scmod":
        target = target.with_name(target.name + ".scmod")
    target.parent.mkdir(parents=True, exist_ok=True)
    return pack_scmod(module.path, target)


def default_file_name(module: Module) -> str:
    return f"{module.id}-{module.version}.scmod"
