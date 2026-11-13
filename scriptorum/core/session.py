"""One open adventure and everything the interface needs from the core.

The window talks to this class through the bridge (scriptorum.app.bridge);
the tests talk to it directly. It owns no interface text of its own: every
message is looked up in the interface-language module (F15).

Milestone 3 adds world-building (F3, F5, F6): the codex, maps, the
relationship chart, handouts and the player PDF, through scriptorum.core.world.

Milestone 2 adds work protection (F2): recovery copies at each pause in
typing, snapshots, read-only opening when the adventure is open elsewhere,
protected mode for missing modules, and unpacked folders. It also adds the
adventure settings page (F7.3, F7.9), find and replace (F4.7), images
(F4.6), fonts (F11) and element positions for editing on the page (F12).
"""

from __future__ import annotations

import copy
import io
import itertools
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from scriptorum import __version__, paths
from scriptorum.core import fonts, scav, source, world as world_mod
from scriptorum.core.appsettings import AppSettings
from scriptorum.core.build import (
    MIN_COLUMN_MM,
    classical_margins,
    clean_margins,
    column_width,
    ORIENTATIONS,
    PAGE_SETTINGS,
    PAPERS,
    TITLE_FIELDS,
    Builder,
    BuildResult,
    Problem,
    effective_page,
)
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library, ModuleError, parse_version, theme_offered_for
from scriptorum.core.protect import LockRegistry, RecoveryStore, SnapshotClock, SnapshotStore, path_key
from scriptorum.core.recent import RecentFiles
from scriptorum.core.scav import Adventure, ModuleRef, ScavError
from scriptorum.core.world import World, WorldError

_session_ids = itertools.count(1)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}


class Session:
    def __init__(self, library: Library, strings: Strings, recent: RecentFiles, work_dir: Optional[Path] = None,
                 home: Optional[Path] = None, app_settings: Optional[AppSettings] = None):
        self.library = library
        self.strings = strings
        self.recent = recent
        self.id = uuid.uuid4().hex[:16]
        self.work_dir = Path(work_dir or paths.build_root() / f"session-{os.getpid()}-{next(_session_ids)}")
        self.adventure: Optional[Adventure] = None
        self.dirty = False
        self.builder: Optional[Builder] = None
        self.last_export: Optional[dict] = None
        home = Path(home or paths.app_home())
        self.recovery = RecoveryStore(home / "recovery")
        self.snapshots = SnapshotStore(home / "snapshots")
        self.locks = LockRegistry(home / "locks")
        self.clock = SnapshotClock(interval=15 * 60)
        self.read_only: Optional[str] = None  # why the adventure cannot be edited
        self.missing: List[dict] = []         # F2.9: modules that are not installed
        # F14 (M6): a module version being tried in the preview before it is applied.
        self.version_preview: Optional[dict] = None
        self.world_history: List[bytes] = []  # undo steps for codex and map changes
        self.last_refs: List[dict] = []       # F3.6: where entries printed, last build
        self.last_sheets: Dict[int, int] = {}  # F6.5: sheets per handout number, last build
        self.show_breaks = False  # F7.2 (M5): View ▸ Show breaks, in the preview only
        self.last_warnings: List[dict] = []  # F7.5 (M5): preflight warnings of the last export
        # F18: the app's own settings, shared by every tab.
        self.app_settings = app_settings or AppSettings(home / "app-settings.json")
        self.apply_app_settings()

    def apply_app_settings(self) -> None:
        """F18: snapshot interval and how many are kept take effect at once."""
        self.clock.interval = int(self.app_settings.get("snapshot_minutes")) * 60
        self.snapshots.kept = int(self.app_settings.get("snapshot_keep"))

    @classmethod
    def start(cls) -> "Session":
        """Open the module library and make sure the bundled modules are in it."""
        # F7.1 (M6): the build helper starts with the app and warms Typst up.
        from scriptorum.core.helper import helper
        helper().start()
        library = Library(paths.module_library_dir())
        library.install_bundled(paths.BUNDLED_MODULES_DIR)
        strings = Strings.from_library(library)
        recent = RecentFiles(paths.app_home() / "recent.json")
        return cls(library, strings, recent, app_settings=AppSettings(paths.app_home() / "app-settings.json"))

    def sibling(self, work_dir: Optional[Path] = None) -> "Session":
        """A new, empty session sharing this one's library (a new tab, F2.2)."""
        return Session(self.library, self.strings, self.recent, work_dir,
                       home=self.recovery.root.parent, app_settings=self.app_settings)

    # --- text ------------------------------------------------------------------
    def t(self, key: str, **details) -> str:
        return self.strings.t(key, **details)

    def localize(self, problem: Problem) -> str:
        details = dict(problem.details)
        labels = self.labels() if self.adventure else {}
        element = details.get("element")
        if element:
            details["element"] = labels.get(f"element.{element}", element)
            fld = details.get("field")
            if fld:
                field_label = labels.get(f"field.{element}.{fld}")
                if field_label is None:
                    field_label = next((labels.get(f["label"], f["name"]) for f in self.kinds().get(element, {}).get("fields", [])
                                        if f["name"] == fld and f.get("label")), fld) if self.builder else fld
                details["field"] = field_label
        if problem.message and "message" not in details:
            details["message"] = problem.message
        text = self.t(problem.key, **details)
        if problem.line:
            text = self.t("error.at", line=problem.line, message=text)
        return text

    def problem_json(self, problem: Problem) -> dict:
        data = problem.to_json()
        data["text"] = self.localize(problem)
        return data

    # --- library -----------------------------------------------------------------
    def game_systems(self) -> List[dict]:
        """For File → New: installed game systems and the themes for each."""
        from scriptorum.core.modules import theme_offered_for

        result = []
        themes = self.library.of_kind("theme")
        # F8 (decided 11 Nov 2026, M5): the standard choice, the Plain game
        # system and Plain theme, is offered first, so File → New preselects it.
        systems = sorted(self.library.of_kind("game-system"), key=lambda m: not m.manifest.get("standard"))
        for gs in systems:
            matching = []
            # F8: the game system's own themes first, then the general themes,
            # the standard one first among those.
            for th in sorted(themes, key=lambda t: (not any(r["id"] == gs.id for r in t.manifest["requires"]),
                                                    not t.manifest.get("standard"), t.name)):
                if theme_offered_for(self.library, th, gs):
                    matching.append({"id": th.id, "version": th.version, "name": th.name,
                                     "general": not any(r["id"] == gs.id for r in th.manifest["requires"]),
                                     "standard": bool(th.manifest.get("standard"))})
            result.append({"id": gs.id, "version": gs.version, "name": gs.name, "themes": matching,
                           "standard": bool(gs.manifest.get("standard"))})
        return result

    # --- files --------------------------------------------------------------------
    def _start_builder(self) -> None:
        self.builder = Builder(self.library, self.work_dir)

    def new(self, title: str, gs_id: str, gs_version: str, theme_id: str, theme_version: str) -> None:
        self.close()
        kits = [ModuleRef(m.id, m.version) for m in self._newest_kits()]
        starter = self.t("starter.sceneTitle")
        # F7.9 (decided 6 Nov 2026, built in M4): the text starts with its first
        # scene; the title page prints the title, so it is not a heading here.
        text = f"#scene(title: {source.quote_string(starter)})[\n]\n"
        self.adventure = scav.new_adventure(
            title, ModuleRef(gs_id, gs_version), ModuleRef(theme_id, theme_version), kits, text
        )
        self.dirty = True
        self.last_export = None
        self.read_only = None
        self.missing = []
        self.world_history = []
        self.clock = SnapshotClock(interval=int(self.app_settings.get("snapshot_minutes")) * 60)
        self._start_builder()
        self.write_recovery()

    def _newest_kits(self):
        newest = {}
        for module in self.library.of_kind("element-kit"):
            current = newest.get(module.id)
            if current is None or tuple(map(int, module.version.split("."))) > tuple(map(int, current.version.split("."))):
                newest[module.id] = module
        return list(newest.values())

    def open(self, path: Path) -> None:
        adventure = scav.load(Path(path))
        self.close()
        self.adventure = adventure
        self.dirty = adventure.migrated_from is not None
        self.last_export = None
        self.world_history = []
        self.clock = SnapshotClock(interval=int(self.app_settings.get("snapshot_minutes")) * 60)
        self._start_builder()
        self.missing = self.missing_modules()
        self.read_only = None
        if self.missing:
            # F2.9: protected mode. The content stays intact and export is blocked.
            self.read_only = "protected"
        elif not self.locks.acquire(adventure.path, self.id):
            # F2.3: already open in another window.
            self.read_only = "openElsewhere"
        self.recent.add(path)

    def save(self, path: Optional[Path] = None, as_folder: Optional[bool] = None) -> Path:
        if self.adventure is None:
            raise ScavError("error.scav.noPath")
        old_path = self.adventure.path
        target_path = Path(path) if path else old_path
        if self.read_only == "protected":
            raise ScavError("error.scav.protected")
        if self.read_only and (target_path is None or (old_path and Path(target_path).resolve() == Path(old_path).resolve())):
            raise ScavError("error.scav.readOnly")
        old_key = self.snapshot_key()
        target = scav.save(self.adventure, path, as_folder=as_folder)
        if old_path is None or Path(old_path).resolve() != Path(target).resolve():
            if old_path is not None and not self.read_only:
                self.locks.release(old_path, self.id)
            self.locks.acquire(target, self.id)
            self.read_only = None
            self.snapshots.move(old_key, self.snapshot_key())
        self.dirty = False
        self.clock.mark_changed()  # F2.6: newly saved changes still get a snapshot
        self.recovery.remove(self.id)
        self.recent.add(target)
        return target

    def close(self) -> None:
        """Forget the open adventure: release its lock and its recovery copy."""
        if self.adventure is not None and self.adventure.path is not None and self.read_only != "openElsewhere":
            self.locks.release(self.adventure.path, self.id)
        self.recovery.remove(self.id)
        self.adventure = None
        self.dirty = False
        self.read_only = None
        self.missing = []
        self.version_preview = None

    # --- work protection (F2.5–F2.8) ------------------------------------------------
    def write_recovery(self) -> None:
        """F2.5: a recovery copy in the app's data folder; the user's own
        file changes only when the user saves."""
        if self.adventure is None or self.read_only:
            return
        meta = {
            "title": self.adventure.title,
            "path": str(self.adventure.path) if self.adventure.path else None,
            "folder": self.adventure.is_folder,
        }
        self.recovery.write(self.id, scav._zip_bytes(self.adventure), meta)

    def snapshot_key(self) -> str:
        if self.adventure is not None and self.adventure.path is not None:
            return path_key(self.adventure.path)
        return f"unsaved-{self.id}"

    def maybe_snapshot(self, now: Optional[float] = None) -> Optional[str]:
        """F2.6: a snapshot every 15 minutes (F18: as set in the app settings)
        while there are unsaved or newly saved changes."""
        if self.adventure is None or self.read_only or not self.clock.due(now):
            return None
        snapshot = self.snapshots.take(self.snapshot_key(), scav._zip_bytes(self.adventure), self.adventure.title, now)
        self.clock.taken(now)
        return snapshot

    def snapshot_list(self) -> List[dict]:
        return self.snapshots.list(self.snapshot_key()) if self.adventure else []

    def revert(self, snapshot_id: str) -> None:
        """F2.7: restore a snapshot. The restored text is an ordinary edit:
        it can be undone and is saved only when the user saves."""
        data = self.snapshots.data(self.snapshot_key(), snapshot_id)
        restored = _adventure_from_bytes(data)
        self.adventure.manifest["chapters"] = restored.manifest.get("chapters", [])
        self.adventure.files = restored.files
        self.adventure.settings = restored.settings
        self.dirty = True
        self.clock.mark_changed()
        self.write_recovery()

    def restore_recovery(self, meta: dict) -> None:
        """F2.8: open a recovery copy left behind by a crash, as unsaved work
        on top of the original file."""
        data = self.recovery.data(meta["session"])
        adventure = _adventure_from_bytes(data)
        self.close()
        original = meta.get("path")
        adventure.path = Path(original) if original else None
        adventure.is_folder = bool(meta.get("folder"))
        self.adventure = adventure
        self.dirty = True
        self.clock = SnapshotClock(interval=int(self.app_settings.get("snapshot_minutes")) * 60)
        self._start_builder()
        self.missing = self.missing_modules()
        self.read_only = "protected" if self.missing else None
        if adventure.path is not None and not self.read_only and not self.locks.acquire(adventure.path, self.id):
            self.read_only = "openElsewhere"
        self.recovery.remove(meta["session"])
        self.write_recovery()

    # --- content --------------------------------------------------------------------
    def kinds(self) -> Dict[str, dict]:
        """The element kinds the game system turns on, from the modules that
        are installed (F2.9: in protected mode the others stay locked)."""
        modules = {}
        for ref in self.adventure.modules:
            module = self.library.get(ref.id, ref.version)
            if module is not None:
                modules[ref.id] = module
        return self.builder.element_kinds(self.adventure, modules)

    def labels(self) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        order = {"element-kit": 0, "game-system": 1, "theme": 2}
        modules = [self.library.get(r.id, r.version) for r in self.adventure.modules]
        for module in sorted((m for m in modules if m and m.kind in order), key=lambda m: order[m.kind]):
            merged.update(module.labels("en"))
        return merged

    # --- world-building (F3, F5, F6) -------------------------------------------------
    @property
    def world(self) -> World:
        types: Dict[str, dict] = {}
        for ref in self.adventure.modules:
            module = self.library.get(ref.id, ref.version)
            if module is not None and module.kind in ("element-kit", "game-system"):
                types.update(module.codex_types())
        return World(self.adventure, self.kinds(), types, {**self.labels(), **self._map_labels()})

    def _map_labels(self) -> Dict[str, str]:
        return {"map.layer.default": self.t("map.defaultLayer")}

    def _world_change(self) -> None:
        """Every codex, map or chart change is one undo step (F4.12)."""
        self.world_history.append(scav._zip_bytes(self.adventure))
        del self.world_history[:-30]

    def _world_changed(self) -> None:
        self.dirty = True
        self.clock.mark_changed()
        self.write_recovery()

    def world_undo(self) -> bool:
        if not self.world_history or self.read_only:
            return False
        restored = _adventure_from_bytes(self.world_history.pop())
        self.adventure.files = restored.files
        self.adventure.settings = restored.settings
        self.adventure.manifest["chapters"] = restored.manifest.get("chapters", [])
        self._world_changed()
        return True

    def _guard(self) -> None:
        if self.read_only:
            raise WorldError("error.scav.readOnly")

    def codex(self) -> dict:
        """The Codex sidebar (F3, F9.3): types, entries, maps, handouts."""
        w = self.world
        types = w.types()
        handwriting = self.choice_options("handwriting")
        sheets = self.handout_sheets()
        labels = self.labels()
        out_types = []
        for t in types.values():
            fields = []
            for f in t["fields"]:
                field = {**f, "label": labels.get(f.get("label", ""), f.get("label", f["name"]))}
                if f.get("options_from") == "handwriting":
                    field["options"] = handwriting
                elif f.get("kind") == "choice" and isinstance(f.get("options"), list) and f["options"] and isinstance(f["options"][0], str):
                    field["options"] = [{"id": o, "label": o} for o in f["options"]]
                fields.append(field)
            out_types.append({**t, "fields": fields})
        return {
            "types": out_types,
            "entries": [{**{k: e[k] for k in ("id", "type", "title", "folder", "tags")},
                         # F3 (M6 part C4): the editor shows a clue's text in its Information item.
                         **({"text": str(e["fields"].get("description", "") or "")} if e["type"] == "clue" else {})}
                        for e in w.entries().values()],
            "maps": [{"id": m["id"], "title": m.get("title", "")} for m in w.maps().values()],
            # F3 (M6 part C4): the elements an author's own type may be shown as.
            "cardKinds": [{"id": k, "name": labels.get(self.kinds()[k].get("name", ""), k)} for k in w.card_kinds()],
            "handouts": [{**{k: h[k] for k in ("number", "kind", "title", "chapter", "line")},
                          "sheets": sheets.get(h["number"], 1)} for h in w.handouts()],
        }

    def entry_info(self, entry_id: str) -> dict:
        """One entry with where it is used: backlinks, scenes and printed pages (F3.6)."""
        w = self.world
        entry = w.entry(entry_id)
        if entry is None:
            raise WorldError("error.codex.noEntry", entry=entry_id)
        pages = sorted({r["page"] for r in self.last_refs if r["id"] == entry_id})
        scenes = []
        for use in w.usages(entry_id):
            if use["where"] == "text" and use.get("scene") and use["scene"] not in scenes:
                scenes.append(use["scene"])
        return {**entry, "backlinks": w.backlinks(entry_id), "scenes": scenes, "pages": pages,
                "usages": w.usages(entry_id),
                # F3 (M6 part C4): a Clue entry shows who knows it.
                "knownBy": w.clue_knowers(entry_id) if entry["type"] == "clue" else []}

    def create_entry(self, type_id: str, title: str, fields: Optional[dict] = None, folder: str = "") -> dict:
        self._guard()
        self._world_change()
        try:
            entry = self.world.create_entry(type_id, title, fields, folder)
        except Exception:
            self.world_history.pop()
            raise
        self._world_changed()
        return entry

    def update_entry(self, entry_id: str, data: dict) -> dict:
        self._guard()
        self._world_change()
        try:
            entry = self.world.update_entry(entry_id, data)
        except Exception:
            self.world_history.pop()
            raise
        self._world_changed()
        return entry

    def delete_entry(self, entry_id: str) -> None:
        self._guard()
        self._world_change()
        try:
            self.world.delete_entry(entry_id)  # refused while in use (F3.8)
        except Exception:
            self.world_history.pop()
            raise
        self._world_changed()

    def convert_info(self, chapter: int, path: List[int]) -> dict:
        """F3 (M6 part C4): what Convert to codex entry offers for a block."""
        return self.world.convert_info(chapter, path)

    def convert_to_entry(self, chapter: int, path: List[int], type_id: str, link: Optional[str] = None) -> dict:
        """F3 (M6 part C4): the codex entry and the card in the text change
        together, as one undo step."""
        self._guard()
        self._world_change()
        try:
            result = self.world.convert_block(chapter, path, type_id, link)
        except Exception:
            self.world_history.pop()
            raise
        self._world_changed()
        return result

    def save_codex_type(self, data: dict) -> dict:
        self._guard()
        self._world_change()
        try:
            definition = self.world.save_type(data)
        except Exception:
            self.world_history.pop()
            raise
        self._world_changed()
        return definition

    def scene_entries(self, chapter: int, line: Optional[int]) -> dict:
        return self.world.scene_entries(chapter, line)

    def map_info(self, map_id: str) -> dict:
        m = self.world.maps().get(map_id)
        if m is None:
            raise WorldError("error.map.noMap", map=map_id)
        return m

    def create_map(self, title: str, name: str, data: bytes) -> dict:
        self._guard()
        self._world_change()
        try:
            m = self.world.create_map(title, name, data)
        except WorldError:
            self.world_history.pop()
            raise
        self._world_changed()
        return m

    def update_map(self, data: dict) -> dict:
        self._guard()
        self._world_change()
        try:
            m = self.world.update_map(data)
        except WorldError:
            self.world_history.pop()
            raise
        self._world_changed()
        return m

    def delete_map(self, map_id: str) -> None:
        self._guard()
        self._world_change()
        try:
            self.world.delete_map(map_id)
        except WorldError:
            self.world_history.pop()
            raise
        self._world_changed()

    def chart(self) -> dict:
        return self.world.chart()

    def set_chart_positions(self, positions: Dict[str, List[float]]) -> dict:
        self._guard()
        self._world_change()
        self.world.set_chart_positions(positions)
        self._world_changed()
        return self.world.chart()

    def upgrade_candidates(self) -> List[dict]:
        return self.world.upgrade_candidates() if not self.read_only else []

    def apply_upgrade(self, choices: List[dict]) -> dict:
        """F3.12: one step that can be undone."""
        self._guard()
        self._world_change()
        result = self.world.apply_upgrade(choices)
        self._world_changed()
        return result

    def offers_upgrade(self) -> bool:
        """F3.12: offered when an adventure saved before M3 is opened."""
        app = str(self.adventure.manifest.get("app", "0"))
        try:
            older = tuple(int(x) for x in app.split(".")[:2]) < (0, 3)
        except ValueError:
            older = False
        return older and bool(self.upgrade_candidates())

    def missing_modules(self) -> List[dict]:
        return [r.to_json() for r in self.adventure.modules if self.library.get(r.id, r.version) is None]

    def missing_details(self) -> List[dict]:
        """F2.9, F14 (decided 12 Nov 2026): every module the adventure pins
        that is not installed, or is installed but disabled, with its ID and
        exact version, and its name when the library knows it."""
        result = []
        for entry in self.missing:
            entry = dict(entry)
            switched_off = self.library.get(entry["id"], entry["version"], include_disabled=True)
            entry["reason"] = "disabled" if switched_off else "missing"
            known = switched_off or next((m for m in self.library.installed(True) if m.id == entry["id"]), None)
            if known is not None:
                entry["name"] = known.name
            result.append(entry)
        return result

    def missing_text(self) -> str:
        """The missing modules as one line: "Name (id 1.0.0)", "id 1.0.0"."""
        parts = []
        for m in self.missing_details():
            text = f"{m['name']} ({m['id']} {m['version']})" if m.get("name") else f"{m['id']} {m['version']}"
            if m.get("reason") == "disabled":
                text = self.t("banner.protected.disabled", module=text)
            parts.append(text)
        return ", ".join(parts)

    def refresh_modules(self) -> bool:
        """After the module manager installs, enables, disables or removes a
        module (F14): an open adventure whose modules are now all there leaves
        protected mode, and one that lost a module enters it. Returns whether
        anything changed."""
        if self.adventure is None:
            return False
        before = (self.read_only, json.dumps(self.missing_details(), sort_keys=True))
        self.missing = self.missing_modules()
        if self.missing:
            if self.read_only is None:
                if self.adventure.path is not None:
                    self.locks.release(self.adventure.path, self.id)
                self.read_only = "protected"
            self.version_preview = None
        elif self.read_only == "protected":
            self.read_only = None
            if self.adventure.path is not None and not self.locks.acquire(self.adventure.path, self.id):
                self.read_only = "openElsewhere"
        return before != (self.read_only, json.dumps(self.missing_details(), sort_keys=True))

    # --- module versions (F14.3; decided 12 Nov 2026, M6 part A) ------------------------
    def module_versions(self) -> dict:
        """For the adventure settings page: the installed versions of the
        adventure's game system and theme, newest first."""
        result = {}
        for which, ref in (("gameSystem", self.adventure.game_system), ("theme", self.adventure.theme)):
            versions = sorted((m.version for m in self.library.installed() if m.id == ref.id),
                              key=parse_version, reverse=True)
            if ref.version not in versions:
                versions.insert(0, ref.version)
            result[which] = {"id": ref.id, "current": ref.version, "installed": versions}
        return result

    def preview_version(self, which: str, version: str) -> dict:
        """Try another installed version of the game system or the theme in
        the preview. Nothing in the adventure changes until it is applied."""
        if self.read_only or which not in ("gameSystem", "theme"):
            return self.settings_info()
        ref = self.adventure.game_system if which == "gameSystem" else self.adventure.theme
        if version == ref.version:
            self.version_preview = None
            return self.settings_info()
        module = self.library.get(ref.id, version)
        if module is None:
            raise ModuleError("error.module.notInstalled", id=ref.id, version=version)
        game = module if which == "gameSystem" else self.library.get(self.adventure.game_system.id, self.adventure.game_system.version)
        theme = module if which == "theme" else self._theme()
        if game is None or theme is None or not theme_offered_for(self.library, theme, game):
            raise ModuleError("error.module.versionNotOffered", theme=theme.name if theme else self.adventure.theme.id,
                              game=game.name if game else self.adventure.game_system.id, version=version)
        self.version_preview = {
            "which": which, "id": ref.id, "version": version, "from": ref.version, "name": module.name,
            # 9.2: another MAJOR version may lack things the adventure uses.
            "major": parse_version(version)[0] != parse_version(ref.version)[0],
        }
        return self.settings_info()

    def cancel_version_preview(self) -> dict:
        self.version_preview = None
        return self.settings_info()

    def apply_version_preview(self) -> dict:
        """Apply the previewed version: only the module lines of the
        manifest change; the text, codex and maps are never touched."""
        pv = self.version_preview
        if pv is None or self.read_only:
            return self.settings_info()
        self._pin(self.adventure.manifest, pv)
        self.version_preview = None
        self.dirty = True
        self.clock.mark_changed()
        self.write_recovery()
        return self.settings_info()

    @staticmethod
    def _pin(manifest: dict, pv: dict) -> None:
        key = "game_system" if pv["which"] == "gameSystem" else "theme"
        manifest[key] = {"id": pv["id"], "version": pv["version"]}
        manifest["modules"] = [{"id": m["id"], "version": pv["version"]} if m["id"] == pv["id"] else m
                               for m in manifest.get("modules", [])]

    def _preview_adventure(self) -> Adventure:
        """A copy of the adventure with the previewed version pinned, for a
        preview build only. The adventure itself is left alone."""
        trial = copy.copy(self.adventure)
        trial.manifest = copy.deepcopy(self.adventure.manifest)
        self._pin(trial.manifest, self.version_preview)
        return trial

    def _kits(self):
        """The element kits this adventure pins (9.3)."""
        kits = []
        for ref in self.adventure.modules:
            module = self.library.get(ref.id, ref.version)
            if module is not None and module.kind == "element-kit":
                kits.append(module)
        return kits

    def _theme(self):
        return self.library.get(self.adventure.theme.id, self.adventure.theme.version)

    def choice_options(self, source_name: str) -> List[dict]:
        """Options for a choice field whose list comes from the modules or
        the adventure (11.9: paper styles and handwriting fonts)."""
        labels = self.labels()
        theme = self._theme()
        handouts = theme.handouts() if theme else {}
        if source_name == "papers":
            return [{"id": p["id"], "label": labels.get(p.get("label", ""), p["id"])} for p in handouts.get("papers", [])]
        if source_name == "handwriting":
            # F6.7, F8 (M4): the six hands of the core element kit, listed by
            # the kind of hand with a short description and the font's name;
            # then any hand a theme brings; then the adventure's own fonts,
            # listed by their font name. Files store the font's name.
            options = []
            for kit in self._kits():
                for hand in kit.handwriting():
                    options.append({"id": hand["family"], "label": labels.get(hand.get("label", ""), hand["family"]),
                                    "note": labels.get(hand.get("note", ""), ""), "font": hand["family"]})
            for f in handouts.get("handwriting", []):
                if all(o["id"] != f["family"] for o in options):
                    options.append({"id": f["family"], "label": f["family"], "font": f["family"]})
            for f in fonts.adventure_fonts(self.adventure):
                if f["ok"] and f["family"] and all(o["id"] != f["family"] for o in options):
                    options.append({"id": f["family"], "label": f["family"], "font": f["family"]})
            return options
        return []

    def editor_info(self) -> dict:
        """Element definitions and their labels, for the Visual editor (F4.3)."""
        labels = self.labels()
        elements = []
        for kind_id, d in self.kinds().items():
            fields = []
            for f in d.get("fields", []):
                field = {**f, "label": labels.get(f.get("label", ""), f["name"])}
                if f.get("kind") == "bool":
                    field["kind"] = "bool"
                if f.get("kind") == "choice" and f.get("options_from"):
                    field["options"] = self.choice_options(f["options_from"])
                fields.append(field)
            elements.append({
                "id": kind_id,
                "name": labels.get(d["name"], kind_id),
                "category": d.get("category", "block"),
                "body": d.get("body", "none"),
                "allow": d.get("allow"),
                "onlyInside": d.get("only_inside"),
                "fields": fields,
                "variants": [{"id": v["id"], "label": labels.get(v["label"], v["id"])} for v in d.get("variants") or []],
                "defaultVariant": d.get("default_variant"),
                "pageStart": d.get("page_start"),
                "pageStartSwitchable": bool(d.get("page_start_switchable")),
                "numbered": bool(d.get("numbered")),
                "outline": bool(d.get("outline")),
                "editor": d.get("editor", "frame"),
                "inlineForm": d.get("inline_form"),
                "bodyRequired": bool(d.get("body_required")),
                "enterAddsNext": bool(d.get("enter_adds_next")),
                "shortcut": d.get("shortcut"),
                "shortcutGroup": d.get("shortcut_group"),
                "module": d.get("module"),
                "newLook": bool(d.get("new_look")),
                "codexRef": d.get("codex_ref"),
            })
        return {"elements": elements}

    def info(self) -> dict:
        data = {"hasDocument": self.adventure is not None, "recent": self.recent.list(), "appVersion": __version__}
        if self.adventure is None:
            return data
        adv = self.adventure
        gs = self.library.get(adv.game_system.id, adv.game_system.version)
        th = self._theme()
        page = self.page_settings()["values"] if th else {}
        chapters = []
        for index, chapter in enumerate(adv.chapters):
            doc = self._parse(chapter)
            heading = next((b for b in doc["blocks"] if b["type"] == "heading"), None)
            chapters.append({
                "index": index,
                "path": chapter,
                "title": source.inline_to_plain(heading["text"]) if heading else chapter,
            })
        data.update({
            "id": self.id,
            "title": adv.title,
            "path": str(adv.path) if adv.path else None,
            "isFolder": adv.is_folder,
            "dirty": self.dirty,
            "readOnly": self.read_only,
            "gameSystem": {"id": adv.game_system.id, "version": adv.game_system.version, "name": gs.name if gs else adv.game_system.id},
            "theme": {"id": adv.theme.id, "version": adv.theme.version, "name": th.name if th else adv.theme.id},
            "page": {"paper": str(page.get("paper", "")).upper(), "columns": page.get("columns", 1)},
            "chapters": chapters,
            "missingModules": self.missing,
            "missingDetails": self.missing_details(),
            "missingText": self.missing_text(),
            "versionPreview": self.version_preview,
            "lastExport": self.last_export,
        })
        return data

    def _parse(self, chapter: str) -> dict:
        return source.parse(self.adventure.chapter_text(chapter), self.kinds())

    def chapter(self, index: int) -> dict:
        path = self.adventure.chapters[index]
        text = self.adventure.chapter_text(path)
        doc = source.parse(text, self.kinds())
        return {
            "index": index,
            "path": path,
            "text": text,
            "doc": doc,
            "outline": source.outline(doc),
            "words": source.word_count(doc),
        }

    def set_chapter_text(self, index: int, text: str) -> dict:
        path = self.adventure.chapters[index]
        if self.read_only:
            return self.chapter(index)
        if self.adventure.chapter_text(path) != text:
            self.adventure.set_chapter_text(path, text)
            self.dirty = True
            self.clock.mark_changed()
            self.write_recovery()  # F2.5: each edit arrives at a pause in typing
        return self.chapter(index)

    def set_chapter_doc(self, index: int, doc: dict) -> dict:
        text = source.serialize(doc, self.kinds())
        return self.set_chapter_text(index, text)

    # --- adventure settings page (F7.3, F7.9) ----------------------------------------
    def page_settings(self) -> dict:
        theme = self._theme()
        return effective_page(theme.page_setup() if theme else {}, self.adventure.settings)

    # --- page-start rules and compact mode (F7.4, M5) -------------------------------------
    PAGE_START_KINDS = ("scene", "read-aloud", "information", "person", "creature", "countdown", "check",
                        "handout", "box", "quote", "pacing", "card", "map", "relationship-chart", "contents")
    PAGE_START_RULES = ("always", "never", "when-needed")

    def page_start_rules(self) -> Dict[str, str]:
        """F7.4.1: each element kind starts a new page always, never or only
        when needed: the element's own default (9.4), changed on the settings
        page. Compact mode reduces page starts: nothing starts a page always."""
        kinds = self.kinds() if self.builder else {}
        stored = self.adventure.settings.get("page_start", {}) or {}
        rules = {}
        for kind in self.PAGE_START_KINDS:
            if kind not in kinds:
                continue
            rule = stored.get(kind) or kinds[kind].get("page_start", "when-needed")
            rules[kind] = rule if rule in self.PAGE_START_RULES else "when-needed"
        if self.adventure.settings.get("compact"):
            rules = {k: ("when-needed" if v == "always" else v) for k, v in rules.items()}
        return rules

    def settings_info(self) -> dict:
        """The settings page: each value and where it comes from (F7.3.2)."""
        page = self.page_settings()
        stored = self.adventure.settings.get("title_page", {}) or {}
        return {
            "titlePage": {"title": self.adventure.title, **{k: stored.get(k, "") for k in TITLE_FIELDS}},
            "page": {k: page["values"][k] for k in PAGE_SETTINGS},
            "origins": {k: page["origins"][k] for k in PAGE_SETTINGS},
            "options": {"paper": list(PAPERS), "orientation": list(ORIENTATIONS), "columns": [1, 2, 3]},
            # F7.3 (M5): classical margins for the chosen paper, and a warning
            # when the columns come out too narrow.
            "classical": classical_margins(page["values"]["paper"], page["values"].get("orientation", "portrait")),
            "columnMm": round(column_width(page["values"]), 1),
            "columnTooNarrow": column_width(page["values"]) < MIN_COLUMN_MM,
            # F7.4 (M5): page-start rules per element kind, and compact mode.
            "pageStart": [{"kind": k, "name": self.labels().get(f"element.{k}", k), "rule": rule,
                           "default": self.kinds()[k].get("page_start", "when-needed"),
                           "stored": k in (self.adventure.settings.get("page_start") or {})}
                          for k, rule in self._stored_rules().items()],
            "compact": bool(self.adventure.settings.get("compact")),
            # F17.2 (M5): the document language, for the PDF, spell check and
            # the adventure-language module that prints the words.
            "language": self.adventure.settings.get("language") or "en",
            "languages": self.document_languages(),
            # F7.6 (M5): the booklet's sheet and order, the print-shop bleed.
            "print": self.print_settings(),
            "sheetOptions": [k for k in ("a4", "a3", "us-tabloid") if k != page["values"]["paper"]],
            "theme": self._theme().name if self._theme() else "",
            # F8 (M4): the game system and the theme are chosen here only.
            "gameSystem": (self.library.get(self.adventure.game_system.id, self.adventure.game_system.version).name
                           if self.library.get(self.adventure.game_system.id, self.adventure.game_system.version) else self.adventure.game_system.id),
            "themeId": self.adventure.theme.id,
            "themes": [{"id": t["id"], "name": t["name"], "general": t.get("general", False)} for t in self.themes_offered()],
            # F14.3 (M6): the installed versions of both, and a version on trial.
            "versions": self.module_versions(),
            "versionPreview": self.version_preview,
            # F7.3 (M4): the fill of the secret box.
            "secretFill": "beige" if self.adventure.settings.get("secret_fill") == "beige" else "grey",
            # F7.3.3: switches for the end of the book and the player PDF.
            "switches": {
                "clueOverview": bool((self.adventure.settings.get("end_matter") or {}).get("clue_overview")),
                "index": bool((self.adventure.settings.get("end_matter") or {}).get("index")),
                "easyRead": bool(self.adventure.settings.get("easy_read")),
            },
        }

    def _stored_rules(self) -> Dict[str, str]:
        """The rules as set, before compact mode is applied."""
        compact = self.adventure.settings.pop("compact", None)
        try:
            return self.page_start_rules()
        finally:
            if compact is not None:
                self.adventure.settings["compact"] = compact

    def set_settings(self, data: dict) -> dict:
        """Store the settings page. A page value set to None goes back to the
        theme's value."""
        if self.read_only:
            return self.settings_info()
        settings = self.adventure.settings
        if "titlePage" in data:
            title_page = dict(settings.get("title_page", {}) or {})
            for key, value in data["titlePage"].items():
                if key == "title":
                    if value and value.strip():
                        self.adventure.manifest["title"] = value.strip()
                elif key in TITLE_FIELDS:
                    if value:
                        title_page[key] = value
                    else:
                        title_page.pop(key, None)
            if title_page:
                settings["title_page"] = title_page
            else:
                settings.pop("title_page", None)
        if "page" in data:
            page = dict(settings.get("page", {}) or {})
            for key, value in data["page"].items():
                if key not in PAGE_SETTINGS:
                    continue
                if value is None or value == "" and key not in ("header", "footer"):
                    page.pop(key, None)
                elif key in ("header", "footer"):
                    if str(value).strip():
                        page[key] = str(value).strip()[:120]
                    else:
                        page.pop(key, None)
                elif key == "page_numbers":
                    page[key] = bool(value)
                elif key == "margin_mm":
                    margins = clean_margins(value)
                    if margins:
                        page[key] = margins
                elif key == "columns":
                    page[key] = max(1, min(3, int(value)))
                elif key == "paper" and value in PAPERS or key == "orientation" and value in ORIENTATIONS:
                    page[key] = value
            if page:
                settings["page"] = page
            else:
                settings.pop("page", None)
        if "pageStart" in data:
            # F7.4.1: a rule equal to the element's own default is not stored.
            rules = dict(settings.get("page_start", {}) or {})
            kinds = self.kinds()
            for kind, rule in (data["pageStart"] or {}).items():
                if kind not in self.PAGE_START_KINDS or kind not in kinds:
                    continue
                if rule in self.PAGE_START_RULES and rule != kinds[kind].get("page_start", "when-needed"):
                    rules[kind] = rule
                else:
                    rules.pop(kind, None)
            if rules:
                settings["page_start"] = rules
            else:
                settings.pop("page_start", None)
        if "language" in data:
            # F17.2: English is the default and is not stored.
            if data["language"] and data["language"] != "en" and data["language"] in self.document_languages():
                settings["language"] = data["language"]
            else:
                settings.pop("language", None)
        if "print" in data:
            from scriptorum.core import preflight

            stored = dict(settings.get("print", {}) or {})
            for key, value in (data["print"] or {}).items():
                if key == "booklet_order" and value in preflight.BOOKLET_ORDERS:
                    stored[key] = value
                elif key == "booklet_sheet" and value in ("a4", "a3", "us-tabloid"):
                    stored[key] = value
                elif key == "bleed_mm":
                    try:
                        stored[key] = max(0.0, min(5.0, float(value)))
                    except (TypeError, ValueError):
                        pass
                elif value is None:
                    stored.pop(key, None)
            if stored:
                settings["print"] = stored
            else:
                settings.pop("print", None)
        if "compact" in data:
            if data["compact"]:
                settings["compact"] = True
            else:
                settings.pop("compact", None)
        if "secretFill" in data:
            # F7.3: pale grey is the default and is not stored.
            if data["secretFill"] == "beige":
                settings["secret_fill"] = "beige"
            else:
                settings.pop("secret_fill", None)
        if "theme" in data and data["theme"]:
            self.set_theme(data["theme"])
        if "switches" in data:
            end = dict(settings.get("end_matter", {}) or {})
            for key, name in (("clueOverview", "clue_overview"), ("index", "index")):
                if key in data["switches"]:
                    if data["switches"][key]:
                        end[name] = True
                    else:
                        end.pop(name, None)
            if end:
                settings["end_matter"] = end
            else:
                settings.pop("end_matter", None)
            if "easyRead" in data["switches"]:
                if data["switches"]["easyRead"]:
                    settings["easy_read"] = True
                else:
                    settings.pop("easy_read", None)
        self.dirty = True
        self.clock.mark_changed()
        self.write_recovery()
        return self.settings_info()

    # --- example adventure (F20, M4) --------------------------------------------------------
    EXAMPLE = "jatten-finns-skuld"

    def open_example(self) -> Path:
        """Open the example adventure Jätten Finns skuld. A copy is made in the
        user's documents, so the bundled original never changes."""
        import zipfile
        from scriptorum import paths

        folder = paths.examples_dir() / self.EXAMPLE
        title = json.loads((folder / "manifest.json").read_text("utf-8"))["title"]
        documents = paths.documents_dir()
        target = documents / f"{title}.scav"
        n = 2
        while target.exists():
            target = documents / f"{title} {n}.scav"
            n += 1
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(folder.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(folder).as_posix())
        self.open(target)
        return target

    # --- theme (F8 general themes, M4) -------------------------------------------------
    def themes_offered(self) -> List[dict]:
        """The themes offered for this adventure's game system (F8)."""
        gs_id = self.adventure.game_system.id
        for gs in self.game_systems():
            if gs["id"] == gs_id:
                return gs["themes"]
        return []

    def set_theme(self, theme_id: str, version: Optional[str] = None) -> dict:
        """Change the adventure's theme. The text, codex and maps are never
        touched; only the theme line of the manifest and its module list
        change, and the next build re-renders the adventure (F8)."""
        if self.read_only:
            return self.settings_info()
        self.version_preview = None
        offered = {t["id"]: t for t in self.themes_offered()}
        if theme_id not in offered:
            raise ValueError(theme_id)
        version = version or offered[theme_id]["version"]
        manifest = self.adventure.manifest
        old = manifest["theme"]["id"]
        if old == theme_id and manifest["theme"]["version"] == version:
            return self.settings_info()
        manifest["theme"] = {"id": theme_id, "version": version}
        modules = []
        for ref in manifest.get("modules", []):
            if ref["id"] == old:
                ref = {"id": theme_id, "version": version}
            if all(m["id"] != ref["id"] for m in modules):
                modules.append(ref)
        if all(m["id"] != theme_id for m in modules):
            modules.append({"id": theme_id, "version": version})
        manifest["modules"] = modules
        self.dirty = True
        self.clock.mark_changed()
        self.write_recovery()
        return self.settings_info()

    # --- find and replace (F4.7) -------------------------------------------------------
    def find(self, query: str, match_case: bool = False) -> List[dict]:
        """Every match in the whole adventure, with its chapter and line."""
        if not query:
            return []
        flags = 0 if match_case else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)
        hits = []
        for index, chapter in enumerate(self.adventure.chapters):
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds())
            for block, where, text in _text_slots(doc, self.kinds()):
                plain = source.inline_to_plain(text)
                for m in pattern.finditer(plain):
                    hits.append({
                        "chapter": index,
                        "line": block.get("line"),
                        "where": where,
                        "text": plain[max(0, m.start() - 30): m.end() + 30],
                    })
        return hits

    def replace_all(self, query: str, replacement: str, match_case: bool = False) -> int:
        """Replace every match in the text the author wrote (never inside
        markup or locked code). Returns how many were replaced."""
        if not query or self.read_only:
            return 0
        flags = 0 if match_case else re.IGNORECASE
        pattern = re.compile(re.escape(source.escape_inline(query)), flags)
        new = source.escape_inline(replacement)
        total = 0
        for index, chapter in enumerate(self.adventure.chapters):
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds())
            changed = 0
            for block, where, text in _text_slots(doc, self.kinds()):
                updated, count = pattern.subn(lambda m: new, text)
                if count:
                    _set_slot(block, where, updated)
                    source.mark_changed(block)
                    changed += count
            if changed:
                _forget_raw_of_parents(doc)
                self.set_chapter_doc(index, doc)
                total += changed
        return total

    # --- images and fonts (F4.6, F11) ------------------------------------------------
    def add_image(self, name: str, data: bytes) -> str:
        """F4.6: an image is copied into the adventure's assets/images/."""
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            raise ScavError("error.image.notImage", file=name)
        stored = self.adventure.add_file("assets/images/", name, data)
        self.dirty = True
        self.write_recovery()
        return "/" + stored

    def add_portrait(self, name: str, data: bytes) -> str:
        """11.4 (M6 part C): a person's portrait is a JPEG or PNG file, as
        for maps; any other file is refused with a plain explanation."""
        if world_mod.image_size(data) is None:
            raise ScavError("error.portrait.notJpegPng", file=name)
        return self.add_image(name, data)

    def add_font(self, path: Path) -> dict:
        """F11: add an open-licence font; refused fonts raise FontRefused."""
        result = fonts.add_font(self.adventure, Path(path))
        self.dirty = True
        self.write_recovery()
        return result

    def font_list(self) -> List[dict]:
        return fonts.adventure_fonts(self.adventure)

    # --- building ----------------------------------------------------------------------
    def build(self, fmt: str = "png", ppi: Optional[float] = None, player: bool = False, show_breaks: bool = False,
              page_extra: str = "", standards: Optional[List[str]] = None) -> BuildResult:
        """Build the adventure PDF, or the player PDF with only the handouts (F6.2,
        F6.4 "Handouts only")."""
        if self.missing:
            return BuildResult(False, errors=[Problem("error.build.missingModules", {"modules": self.missing_text()})])
        w = self.world
        data = w.build_data("player" if player else "gm", self.adventure.settings)
        # F7.4 (M5): page-start rules and compact mode; "Show breaks" only in
        # the preview, never in an exported PDF (F7.2).
        data["layout"] = {"page_start": self.page_start_rules(), "show_breaks": bool(show_breaks)}
        chunks = [h["source"] for h in w.handouts()] if player else None
        # F14 (M6): a version being previewed is used by the preview only,
        # never by an exported PDF.
        adventure = self._preview_adventure() if self.version_preview and fmt != "pdf" else self.adventure
        result = self.builder.build(adventure, fmt, ppi, world=data, player=chunks,
                                    language=self.adventure.settings.get("language"),
                                    page_extra=page_extra, standards=standards)
        if result.ok:
            if not player:
                result.warnings.extend(self.empty_elements())
                self.last_refs = self.builder.references()
            else:
                self.last_sheets = self.builder.sheets()
                result.warnings.extend(self.long_handouts(self.last_sheets))
            result.warnings.extend(self.world_warnings(w))
            result.warnings.extend(self.heading_warnings())
        return result

    @staticmethod
    def long_handouts(sheets: Dict[int, int]) -> List[Problem]:
        """F7.5.7: a handout on more than 4 sheets is unusually long for
        something handed to players. Export still works."""
        return [Problem("warning.handout.long", {"number": n, "sheets": k}) for n, k in sorted(sheets.items()) if k > 4]

    def handout_sheets(self) -> Dict[int, int]:
        """F6.5: the sheets each handout needs in the player PDF. Measured by
        a player build in a folder of its own, and kept until a handout, the
        theme or the settings change."""
        w = self.world
        handouts = w.handouts()
        if not handouts or self.missing:
            return {}
        key = json.dumps([[h["source"] for h in handouts], self.adventure.theme.to_json(), self.adventure.settings,
                          w.build_data("player", self.adventure.settings)], sort_keys=True, default=str)
        if getattr(self, "_sheets_key", None) != key:
            if getattr(self, "_sheet_builder", None) is None:
                self._sheet_builder = Builder(self.library, Path(str(self.work_dir) + "-sheets"))
            result = self._sheet_builder.build(self.adventure, "pdf", world=w.build_data("player", self.adventure.settings),
                                               player=[h["source"] for h in handouts],
                                               language=self.adventure.settings.get("language"))
            self.last_sheets = self._sheet_builder.sheets() if result.ok else {}
            self._sheets_key = key
        return self.last_sheets

    # The portrait's share of a person card's width, and the card's inset on
    # each side, as the bundled themes print it (11.4, _style.typ).
    PORTRAIT_SHARE = 0.33
    CARD_INSET_MM = 10 * 25.4 / 72

    def portraits(self, w: Optional[World] = None) -> List[dict]:
        """11.4 (M6 part C): every portrait the adventure PDF prints, with
        its description and the line of the card that prints it: a loose
        person card's own, or a codex Person's in every card of that person."""
        w = w or self.world
        entries = w.entries()
        found = []
        for chapter in self.adventure.chapters:
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds())
            for block in _walk(doc["blocks"]):
                if block.get("type") != "element":
                    continue
                fields = block.get("fields") or {}
                if block["kind"] == "person":
                    name, data = fields.get("name", ""), fields
                elif block["kind"] == "card":
                    e = entries.get(fields.get("entry"))
                    if not e or e.get("type") != "person":
                        continue
                    name, data = e.get("title", ""), e.get("fields") or {}
                else:
                    continue
                path = str(data.get("portrait") or "").strip()
                if path:
                    found.append({"person": name, "path": path, "description": str(data.get("portrait-description") or "").strip(),
                                  "chapter": chapter, "line": block.get("line")})
        return found

    def heading_warnings(self) -> List[Problem]:
        """F4 (M6 part C): a sub-heading that skips a level, such as ====
        directly under a scene in an older adventure. The adventure opens
        unchanged; the warnings panel names it and offers to raise it."""
        problems = []
        for chapter in self.adventure.chapters:
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds())
            for item in source.skipped_headings(doc, self.kinds()):
                problems.append(Problem("warning.heading.skipsLevel",
                                        {"title": item["title"], "level": item["level"], "to": item["to"],
                                         "from": item["level"] - 2, "sub": item["to"] - 2}, chapter, item["line"]))
        return problems

    def world_warnings(self, w: World) -> List[Problem]:
        """Broken codex references (F7.5.3), map images below 300 dpi (F5.6,
        F7.5.2) and paper styles that break the handout rules (F7.5.6)."""
        problems = []
        for b in w.broken_references():
            problems.append(Problem("warning.build.brokenReference", {"entry": b["entry"]},
                                    self.adventure.chapters[b["chapter"]] if isinstance(b["chapter"], int) else b["chapter"],
                                    b.get("line")))
        page = self.page_settings()["values"]
        column_mm = column_width(page)  # F7.3 (M5): x, or inside and outside margins
        maps = w.maps()
        for index, chapter in enumerate(self.adventure.chapters):
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds())
            for block in _walk(doc["blocks"]):
                if block["type"] == "element" and block["kind"] == "map":
                    m = maps.get((block.get("fields") or {}).get("map"))
                    if m and column_mm > 0:
                        dpi = int(m.get("width", 0) / (column_mm / 25.4))
                        if dpi < 300:
                            problems.append(Problem("warning.map.lowResolution", {"map": m.get("title", ""), "dpi": dpi},
                                                    chapter, block.get("line")))
        # 11.4 (M6 part C): a portrait below 300 dpi at its printed size,
        # about a third of the card's width, gets the usual warning.
        from scriptorum.core.preflight import MIN_DPI, image_width_px
        portrait_in = max(0.0, column_mm - 2 * self.CARD_INSET_MM) * self.PORTRAIT_SHARE / 25.4
        for item in self.portraits(w) if portrait_in > 0 else []:
            data = self.adventure.files.get(item["path"].lstrip("/"))
            width = image_width_px(data) if data else None
            if width is not None and int(width / portrait_in) < MIN_DPI:
                problems.append(Problem("warning.preflight.portraitLowResolution",
                                        {"person": item["person"], "dpi": int(width / portrait_in)}, item["chapter"], item["line"]))
        theme = self._theme()
        if theme is not None and w.handouts():
            for paper in theme.handouts().get("papers", []):
                sheet = str(paper.get("sheet", "white")).lower()
                stains = paper.get("stains", {}) or {}
                if sheet not in ("white", "#fff", "#ffffff", "none") or paper.get("fill"):
                    problems.append(Problem("warning.paper.coloured", {"paper": paper.get("id"), "theme": theme.name}))
                elif max(float(stains.get("opacity", 0) or 0),
                         float((paper.get("marks") or {}).get("opacity", 0) or 0)) > 0.2:
                    problems.append(Problem("warning.paper.tooDark", {"paper": paper.get("id"), "theme": theme.name}))
        return problems

    def empty_elements(self) -> List[Problem]:
        """An element box left empty prints only its label: warn about it on
        the author's line (T-USE finding, M1)."""
        kinds = self.kinds()
        problems = []
        for chapter in self.adventure.chapters:
            doc = source.parse(self.adventure.chapter_text(chapter), kinds)
            for block in _walk(doc["blocks"]):
                if block["type"] != "element":
                    continue
                definition = kinds.get(block["kind"], {})
                body = block.get("body")
                filled = (isinstance(body, str) and body.strip()) or (isinstance(body, dict) and body.get("blocks"))
                if block["kind"] == "information" and (block.get("fields") or {}).get("clue"):
                    continue  # F3 (M6 part C4): it prints the clue's description
                if definition.get("body_required") and not filled:
                    problems.append(Problem("warning.build.emptyElement", {"element": block["kind"]}, chapter, block.get("line")))
        return problems

    def element_map(self) -> List[dict]:
        """F12 stage 1: where each element of the last build sits on the
        pages, tied to its block (chapter and path of indexes). Empty when the
        build and the text cannot be matched one to one."""
        positions = self.builder.positions()
        kinds = self.kinds()
        inline = source.inline_kinds_of(kinds)
        expected = []
        for index, chapter in enumerate(self.adventure.chapters):
            doc = source.parse(self.adventure.chapter_text(chapter), kinds)
            expected.extend({"chapter": index, **e} for e in _element_order(doc["blocks"], [], kinds, inline))
        if [p["kind"] for p in positions] != [e["kind"] for e in expected]:
            return []
        return [{**e, **{k: p[k] for k in ("page", "x", "y")}} for e, p in zip(expected, positions)]

    def check_fonts(self) -> List[Problem]:
        """F11.4: fonts stored in the adventure are checked again at export."""
        return [Problem("error.font.refusedAtExport", {"file": Path(f["file"]).name})
                for f in self.font_list() if not f["ok"]]

    VARIANTS = ("full", "handouts", "booklet", "print-shop", "accessible")

    def document_languages(self) -> List[str]:
        """F17.2: English and Swedish, the spell-check languages (D10), and the
        language of every installed adventure-language module (9.3)."""
        codes = ["en", "sv"]
        for module in self.library.of_kind("adventure-language"):
            code = module.manifest.get("language")
            if code and code not in codes:
                codes.append(code)
        return codes

    @staticmethod
    def _plain_ua(problem: Problem) -> Problem:
        """F17.5: Typst's PDF/UA message about a skipped heading level, in
        plain words on the author's line."""
        m = re.search(r"skipped from heading level (\d+) to (\d+)", problem.message or "")
        if not m:
            return problem
        return Problem("error.preflight.headingSkip", {"from": m.group(1), "to": m.group(2), "next": int(m.group(1)) + 1},
                       problem.chapter, problem.line)

    def missing_descriptions(self, as_error: bool = False) -> List[Problem]:
        """F17.3: an image or map without a description gives a warning; for
        the accessible PDF it is an error, since PDF/UA needs one."""
        from scriptorum.core.preflight import IMAGE_CALL

        kind = "error" if as_error else "warning"
        problems = []
        maps = self.world.maps()
        for chapter in self.adventure.chapters:
            text = self.adventure.chapter_text(chapter)
            for match in IMAGE_CALL.finditer(text):
                if not match.group(2):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(Problem(f"{kind}.preflight.noImageDescription", {"image": Path(match.group(1)).name}, chapter, line))
            doc = source.parse(text, self.kinds())
            for block in _walk(doc["blocks"]):
                if block["type"] == "element" and block["kind"] == "map":
                    m = maps.get((block.get("fields") or {}).get("map"))
                    if m and not str(m.get("description") or "").strip():
                        problems.append(Problem(f"{kind}.preflight.noMapDescription", {"map": m.get("title", "")}, chapter, block.get("line")))
        # 11.4 (M6 part C): a portrait needs its description too.
        for item in self.portraits():
            if not item["description"]:
                problems.append(Problem(f"{kind}.preflight.noPortraitDescription", {"person": item["person"]}, item["chapter"], item["line"]))
        return problems

    def print_settings(self) -> dict:
        """F7.6 (M5): the booklet's sheet and page order, and the bleed of the
        print-shop version, from the adventure settings."""
        from scriptorum.core import preflight

        page = self.page_settings()["values"]
        stored = self.adventure.settings.get("print", {}) or {}
        order = stored.get("booklet_order") if stored.get("booklet_order") in preflight.BOOKLET_ORDERS else "fold"
        try:
            bleed = max(0.0, min(5.0, float(stored.get("bleed_mm", preflight.BLEED_MM))))
        except (TypeError, ValueError):
            bleed = preflight.BLEED_MM
        return {"sheet": preflight.booklet_sheet(page["paper"], stored.get("booklet_sheet")),
                "order": order, "bleed_mm": bleed}

    def export_pdf(self, target: Path, variant: str = "full") -> dict:
        """Export one variant (F7.6): the adventure PDF, the player PDF with
        only the handouts, the booklet (two pages per sheet) or the print-shop
        version (bleed, crop marks, PDF/A). Preflight runs first (F7.5):
        warnings are listed, errors stop the export. Written crash-safely like
        a save."""
        from scriptorum.core import preflight

        if self.missing:
            problem = Problem("error.export.protected", {"id": self.missing[0]["id"], "version": self.missing[0]["version"],
                                                         "modules": self.missing_text()})
            return {"ok": False, "errors": [self.problem_json(problem)]}
        if variant not in self.VARIANTS:
            variant = "full"
        font_problems = self.check_fonts()
        if font_problems:
            return {"ok": False, "errors": [self.problem_json(p) for p in font_problems]}
        page = self.page_settings()["values"]
        settings = self.print_settings()
        extra, standards = "", None
        if variant == "accessible":
            # F17.5 (M5): PDF/UA-1. Every image and map needs a description.
            missing = self.missing_descriptions(as_error=True)
            if missing:
                return {"ok": False, "errors": [self.problem_json(p) for p in missing]}
            standards = ["ua-1"]
        if variant == "print-shop":
            # PDF/A needs a date: the adventure's own last-saved day, so the
            # same file always exports the same PDF (F7.8).
            day = str(self.adventure.manifest.get("modified") or "2026-01-01")[:10]
            try:
                y, mo, d = (int(x) for x in day.split("-"))
            except ValueError:
                y, mo, d = 2026, 1, 1
            extra = (f"#set document(date: datetime(year: {y}, month: {mo}, day: {d}))\n"
                     + preflight.print_shop_page(page, settings["bleed_mm"]))
            standards = ["a-2b"]
        result = self.build("pdf", player=variant == "handouts", page_extra=extra, standards=standards)
        if not result.ok:
            return {"ok": False, "errors": [self.problem_json(self._plain_ua(p)) for p in result.errors]}
        data = result.output[0]
        checks = preflight.check_pdf_fonts(data, self.builder.work_dir)
        if variant != "handouts":
            checks += preflight.check_images(self.adventure, page)
            if variant != "accessible":
                checks += self.missing_descriptions()
        errors = [p for p in checks if p.key.startswith("error.")]
        if errors:
            return {"ok": False, "errors": [self.problem_json(p) for p in errors]}
        warnings = result.warnings + [p for p in checks if not p.key.startswith("error.")]
        if variant == "booklet":
            from scriptorum.core.build import stopped_problem
            from scriptorum.core.helper import BuildStopped
            try:
                data = preflight.compose_booklet(data, page, self.builder.work_dir, settings["sheet"], settings["order"])
            except BuildStopped as stopped:
                # F7.1 (M6): a stopped export says so and writes no file.
                return {"ok": False, "errors": [self.problem_json(stopped_problem(stopped))]}
        target = Path(target)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self.last_export = {"file": target.name, "path": str(target), "time": datetime.now().strftime("%H:%M")}
        self.last_warnings = [self.problem_json(p) for p in warnings]
        return {"ok": True, **self.last_export, "variant": variant, "warnings": self.last_warnings}


# --------------------------------------------------------------------------
# Helpers

def _adventure_from_bytes(data: bytes) -> Adventure:
    fd, tmp = tempfile.mkstemp(suffix=".scav")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        adventure = scav.load(Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)
    adventure.path = None
    return adventure


def _walk(blocks):
    for block in blocks:
        yield block
        body = block.get("body")
        if isinstance(body, dict):
            yield from _walk(body["blocks"])


def _text_slots(doc: dict, kinds: Dict[str, dict]):
    """Every piece of text the author reads: (block, where, markup). ``where``
    is 'text', 'body', ('field', name) or ('cell', row, column). Link names,
    choices, dice and images are not text and are never changed (F4.7)."""
    for block in _walk(doc.get("blocks", [])):
        btype = block["type"]
        if btype in ("heading", "paragraph"):
            yield block, "text", block.get("text", "")
        elif btype == "table":
            for c, cell in enumerate(block.get("header", [])):
                yield block, ("cell", -1, c), cell
            for r, row in enumerate(block.get("rows", [])):
                for c, cell in enumerate(row):
                    yield block, ("cell", r, c), cell
        elif btype == "element":
            locked = set(block.get("locked_fields", []))
            text_fields = {f["name"] for f in kinds.get(block["kind"], {}).get("fields", []) if f.get("kind") in ("text", "rich")}
            for name, value in (block.get("fields") or {}).items():
                if isinstance(value, str) and name not in locked and name in text_fields:
                    yield block, ("field", name), value
            if isinstance(block.get("body"), str):
                yield block, "body", block["body"]


def _set_slot(block: dict, where, value: str) -> None:
    if where == "text":
        block["text"] = value
    elif where == "body":
        block["body"] = value
    elif where[0] == "field":
        block["fields"][where[1]] = value
        block.pop("head_raw", None)
    elif where[0] == "cell":
        if where[1] == -1:
            block["header"][where[2]] = value
        else:
            block["rows"][where[1]][where[2]] = value


def _forget_raw_of_parents(doc: dict) -> bool:
    """A changed block inside an element changes that element's text too."""
    changed = False
    for block in doc.get("blocks", []):
        body = block.get("body")
        if isinstance(body, dict) and _forget_raw_of_parents(body):
            block.pop("raw", None)
        if "raw" not in block and block["type"] != "locked":
            changed = True
    return changed


def _inline_calls(markup: str, inline) -> List[str]:
    return [m.group(0)[1:m.group(0).index("(")] for m in source.INLINE_CALL.finditer(markup or "")
            if m.group(0)[1:m.group(0).index("(")] in inline]


def _element_order(blocks, path, kinds, inline) -> List[dict]:
    """Elements in the order their marks appear in the build (F12)."""
    order = []
    for index, block in enumerate(blocks):
        here = path + [index]
        btype = block["type"]
        if btype in ("heading", "paragraph"):
            order += [{"kind": k, "path": here} for k in _inline_calls(block.get("text", ""), inline)]
        elif btype == "table":
            for row in [block.get("header", []), *block.get("rows", [])]:
                for cell in row:
                    order += [{"kind": k, "path": here} for k in _inline_calls(cell, inline)]
        elif btype == "element":
            definition = kinds.get(block["kind"], {})
            if definition.get("category") == "layout":
                continue
            order.append({"kind": block["kind"], "path": here})
            for field in definition.get("fields", []):
                value = (block.get("fields") or {}).get(field["name"])
                if field.get("kind") == "rich" and isinstance(value, str):
                    order += [{"kind": k, "path": here} for k in _inline_calls(value, inline)]
            body = block.get("body")
            if isinstance(body, str):
                order += [{"kind": k, "path": here} for k in _inline_calls(body, inline)]
            elif isinstance(body, dict):
                order += _element_order(body["blocks"], here, kinds, inline)
    return order
