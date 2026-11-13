"""App settings (design document F18, built in M4) and app palettes (F16).

One settings page for the app itself, never for a single adventure. The
values are kept in the app's own folder (app-settings.json) and every change
takes effect at once, without a restart.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from scriptorum.core.modules import Library, Module, parse_version
from scriptorum.core.palettes import TOKENS, css_variables, low_contrast

DEFAULT_PALETTE = "scriptorum.claret-and-ink"

DEFAULTS = {
    "palette": DEFAULT_PALETTE,       # F16: the palette module's id
    "palette_version": None,          # None: the newest installed version
    "mode": "system",                 # F16: light, dark or system (follow the computer)
    "ui_size": 13,                    # F18: interface text size (px)
    "editor_size": 16,                # F18: editor text size (px)
    "spell_language": "sv",           # F18: default spell-check language (F4.8)
    "start_mode": "visual",           # F18: the editor mode the app starts in
    "snapshot_minutes": 15,           # F2.6, F18: how often a snapshot is taken
    "snapshot_keep": 20,              # F18: how many snapshots are kept
    "language": "scriptorum.en",      # F15, F18: the interface language module
    "full_screen": False,             # F9 (M6): opens in full screen if left that way
    "update_weekly": False,           # F21 (M6 part C): Check once a week, off by default
    "update_asked": False,            # F21: the question at first start is asked once
    "update_last_check": 0,           # F21: when the weekly check last ran (seconds)
    "update_address": "",             # F22 (M6 part C5): empty means the built-in address
}

CHOICES = {
    "mode": ("light", "dark", "system"),
    "start_mode": ("visual", "hybrid", "source"),
    "spell_language": ("sv", "en", "en-gb"),
    "full_screen": (True, False),
    "update_weekly": (True, False),
    "update_asked": (True, False),
}
RANGES = {"ui_size": (11, 18), "editor_size": (12, 24), "snapshot_minutes": (1, 120), "snapshot_keep": (1, 200),
          "update_last_check": (0, 2 ** 40)}


class AppSettings:
    def __init__(self, file: Path):
        self.file = Path(file)
        self.values: Dict[str, object] = dict(DEFAULTS)
        if self.file.is_file():
            try:
                stored = json.loads(self.file.read_text("utf-8"))
                for key, value in stored.items():
                    if key in DEFAULTS:
                        self.values[key] = value
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                pass  # an unreadable file falls back to the defaults

    def get(self, key: str):
        return self.values.get(key, DEFAULTS.get(key))

    def update(self, changes: dict) -> dict:
        """Store the changed values; unknown keys and values out of range are
        ignored. Written crash-safely, like an adventure (F1.1)."""
        for key, value in (changes or {}).items():
            if key not in DEFAULTS:
                continue
            if key in CHOICES and value not in CHOICES[key]:
                continue
            if key == "update_address":
                # F22: only an https address (or empty, for the built-in one).
                from scriptorum.core.updates import address_ok
                if not isinstance(value, str) or (value.strip() and not address_ok(value)):
                    continue
                value = value.strip()
            if key in RANGES:
                try:
                    lo, hi = RANGES[key]
                    value = max(lo, min(hi, int(value)))
                except (TypeError, ValueError):
                    continue
            self.values[key] = value
        self.save()
        return dict(self.values)

    def save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".app-settings.", dir=self.file.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(self.values, handle, indent=2)
        os.replace(tmp, self.file)


# --- palettes (F16) ------------------------------------------------------------------

def palettes(library: Library) -> List[Module]:
    """Installed palettes, newest version of each, Claret & Ink first."""
    newest: Dict[str, Module] = {}
    for module in library.of_kind("palette"):
        current = newest.get(module.id)
        if current is None or parse_version(module.version) > parse_version(current.version):
            newest[module.id] = module
    return sorted(newest.values(), key=lambda m: (m.id != DEFAULT_PALETTE, m.name.lower()))


def chosen_palette(library: Library, settings: AppSettings) -> Optional[Module]:
    """The palette in use: the one chosen, or Claret & Ink when it is gone."""
    wanted, version = settings.get("palette"), settings.get("palette_version")
    if version:
        module = library.get(wanted, version)
        if module is not None:
            return module
    for module in palettes(library):
        if module.id == wanted:
            return module
    return library.newest(DEFAULT_PALETTE)


def palette_info(module: Module, skip_css: bool = False) -> dict:
    data = module.palette()
    light, dark = data.get("light") or {}, data.get("dark") or {}
    # A palette may define only one mode: the other is taken from it (F16).
    light, dark = light or dark, dark or light
    return {
        "id": module.id, "version": module.version, "name": module.name,
        "light": light, "dark": dark,
        "lightVars": css_variables(light), "darkVars": css_variables(dark),
        "css": "" if skip_css else module.stylesheet(),
        "lowContrast": {"light": low_contrast(light), "dark": low_contrast(dark)},
    }


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "palette"


def save_palette(library: Library, name: str, light: dict, dark: dict, author: str = "") -> Module:
    """New palette from this one (F16): the colours chosen with the pickers
    are saved as a palette module in the library, which can be shared and
    installed like any other (F14). Saving again under the same name makes a
    new version, so nothing that used the older one changes."""
    name = (name or "").strip() or "My palette"
    module_id = f"my.{_slug(name)}"
    version = "1.0.0"
    existing = [m for m in library.of_kind("palette") if m.id == module_id]
    if existing:
        newest = max(existing, key=lambda m: parse_version(m.version))
        major, minor, patch = parse_version(newest.version)
        version = f"{major}.{minor + 1}.0"
    clean = lambda colours: {k: str(v).upper() for k, v in (colours or {}).items() if k in TOKENS and re.match(r"^#[0-9A-Fa-f]{6}$", str(v))}
    folder = Path(tempfile.mkdtemp(prefix=".palette-", dir=library.root))
    try:
        (folder / "module.json").write_text(json.dumps({
            "id": module_id, "kind": "palette", "name": name, "version": version, "format": 1, "app": "1.0.0",
            "licence": "GPL-3.0-or-later", "authors": [author or "Scriptorum user"],
            "description": "A palette made with the colour pickers in Scriptorum (F16).", "requires": [],
        }, indent=2), "utf-8")
        (folder / "palette.json").write_text(json.dumps({"light": clean(light), "dark": clean(dark)}, indent=2), "utf-8")
        return library.install_folder(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
