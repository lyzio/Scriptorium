"""Help ▸ About Scriptorum (design document F9; built in M6 part B).

The About window has three tabs. This module gathers what the second and third
show: every part Scriptorum is built on, with its version, what it does and its
licence (from the licence register, design document section 7), and the full
text of each licence used. Everything is read from files that ship with the
app, so the window works offline (D9). Fonts and the Typst packages copied
into themes are read from the installed modules, so a theme installed later
shows its fonts too.
"""

from __future__ import annotations

import platform
import re
from importlib import metadata
from pathlib import Path
from typing import Dict, List, Optional

from scriptorum import __version__, paths

LICENCES_DIR = paths.PACKAGE_DIR / "licences"
TEXTS = LICENCES_DIR / "texts"
PARTS = LICENCES_DIR / "parts"

# The Licences tab, in this order. Ids are SPDX identifiers; the names are
# the licences' own names, which stay in English (F9).
LICENCES = [
    ("GPL-3.0", "GNU General Public License, version 3"),
    ("LGPL-3.0", "GNU Lesser General Public License, version 3"),
    ("Apache-2.0", "Apache License 2.0"),
    ("MPL-2.0", "Mozilla Public License 2.0"),
    ("MIT", "MIT License"),
    ("MIT-0", "MIT No Attribution"),
    ("BSD-3-Clause", "BSD 3-Clause License"),
    ("OFL-1.1", "SIL Open Font License 1.1"),
    ("Python", "Python Software Foundation License"),
]

# Shown in the About tab with the full licence (F9, decided 12 November 2026).
IDEA_BY = "lyzio"
IDEA_SITE = "https://lyzio.net"


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return ""


def _qt_versions() -> Dict[str, str]:
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        versions = {"pyside": PySide6.__version__, "qt": qVersion()}
    except Exception:  # noqa: BLE001 - the core also runs without Qt (tests, the helper)
        versions = {"pyside": _version("PySide6"), "qt": ""}
    try:
        from PySide6.QtWebEngineCore import qWebEngineChromiumVersion
        versions["chromium"] = qWebEngineChromiumVersion()
    except Exception:  # noqa: BLE001
        versions["chromium"] = ""
    return versions


def _package_versions() -> Dict[str, str]:
    """The pinned versions of the bundled interface parts (ui-src/package.json)."""
    return {"cytoscape": "3.34.0", "phosphor": "2.1.1"}


def programs() -> List[dict]:
    """The programs and libraries (licence register, section 7)."""
    qt = _qt_versions()
    pv = _package_versions()
    return [
        {"id": "python", "name": "Python", "version": platform.python_version(), "what": "python",
         "licence": "Python", "file": "parts/python.txt"},
        {"id": "qt", "name": "Qt and PySide6", "version": " / ".join(v for v in (qt["qt"], qt["pyside"]) if v),
         "what": "qt", "licence": "LGPL-3.0", "file": "parts/qt.txt"},
        {"id": "chromium", "name": "Qt WebEngine (Chromium)", "version": qt["chromium"], "what": "chromium",
         "licence": "LGPL-3.0, BSD-3-Clause", "file": "parts/chromium.txt", "note": "chromium"},
        {"id": "typst", "name": "Typst", "version": _version("typst"), "what": "typst",
         "licence": "Apache-2.0", "file": "parts/typst.txt"},
        {"id": "spylls", "name": "spylls", "version": _version("spylls"), "what": "spylls",
         "licence": "MPL-2.0", "file": "parts/spylls.txt"},
        # F22 (M6-0.6.7): checks the project's signature on update files and packs.
        {"id": "cryptography", "name": "cryptography", "version": _version("cryptography"), "what": "cryptography",
         "licence": "Apache-2.0, BSD-3-Clause", "file": "parts/cryptography.txt"},
        {"id": "cytoscape", "name": "Cytoscape.js", "version": pv["cytoscape"], "what": "cytoscape",
         "licence": "MIT", "file": "parts/cytoscape.txt"},
        {"id": "phosphor", "name": "Phosphor Icons (Light)", "version": pv["phosphor"], "what": "phosphor",
         "licence": "MIT", "file": "parts/phosphor.txt"},
    ]


def _licence_of(text: str) -> str:
    head = text[:4000].upper()
    if "OPEN FONT LICENSE" in head:
        return "OFL-1.1"
    if "APACHE LICENSE" in head:
        return "Apache-2.0"
    if "LESSER GENERAL PUBLIC" in head:
        return "LGPL-3.0"
    if "GENERAL PUBLIC LICENSE" in head:
        return "GPL-3.0"
    if "MIT NO ATTRIBUTION" in head:
        return "MIT-0"
    if "MOZILLA PUBLIC LICENSE" in head:
        return "MPL-2.0"
    if "PERMISSION IS HEREBY GRANTED" in head:
        return "MIT"
    return ""


def _split_name(stem: str) -> str:
    """"LibreBaskerville" → "Libre Baskerville", "TT2020" stays."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)


def fonts(library) -> List[dict]:
    """Every font family in the installed modules, with its licence file:
    one row per licence file in a module's fonts/ folder (F11 keeps one
    beside each font)."""
    rows, seen = [], set()
    for module in sorted(library.installed(), key=lambda m: (m.name.lower(), m.version)):
        folder = module.path / "fonts"
        if not folder.is_dir():
            continue
        for licence in sorted(folder.glob("*.txt")):
            stem = re.sub(r"[-_](OFL|LICEN[CS]E|COPYING)$", "", licence.stem, flags=re.I)
            name = _split_name(stem)
            key = (name, module.id)
            if key in seen:
                continue
            seen.add(key)
            text = licence.read_text("utf-8", errors="replace")
            rows.append({"id": f"font:{module.id}:{licence.name}", "name": name, "version": "", "what": "font",
                         "module": module.name, "licence": _licence_of(text) or "OFL-1.1",
                         "path": str(licence)})
    return rows


def typst_packages(library) -> List[dict]:
    """The Typst packages copied into themes (D15), once per name and version,
    with the themes that carry them."""
    found: Dict[str, dict] = {}
    for module in sorted(library.installed(), key=lambda m: m.name.lower()):
        vendor = module.path / "vendor"
        if not vendor.is_dir():
            continue
        for package in sorted(p for p in vendor.iterdir() if p.is_dir()):
            licence = next((f for f in sorted(package.iterdir()) if f.name.upper().startswith(("LICENSE", "LICENCE"))), None)
            name, _, version = package.name.rpartition("-")
            row = found.setdefault(package.name, {
                "id": f"package:{package.name}", "name": {"cetz": "CeTZ"}.get(name, name), "version": version,
                "what": f"package.{name}" if name in ("fletcher", "cetz", "oxifmt") else "package",
                "licence": _licence_of(licence.read_text("utf-8", errors="replace")) if licence else "",
                "path": str(licence) if licence else "", "modules": []})
            row["modules"].append(module.name)
    return list(found.values())


def dictionaries() -> List[dict]:
    """The spelling dictionaries (F4.8)."""
    rows = []
    for code, name, version in (("sv", "Swedish", "dictionary-sv 4.0.0"),
                                ("en", "English (United States)", "dictionary-en 4.0.0"),
                                ("en-gb", "English (United Kingdom)", "dictionary-en-gb 3.0.0")):
        folder = paths.PACKAGE_DIR / "dictionaries" / code
        licence = next(iter(sorted(folder.glob("*.txt"))), None) if folder.is_dir() else None
        rows.append({"id": f"dictionary:{code}", "name": name, "version": version, "what": f"dictionary.{code}",
                     "licence": "LGPL-3.0" if code == "sv" else "MIT, BSD-3-Clause",
                     "path": str(licence) if licence else ""})
    return rows


def info(library) -> dict:
    """Everything the About window shows."""
    return {
        "version": __version__,
        "ideaBy": IDEA_BY,
        "ideaSite": IDEA_SITE,
        "programs": programs(),
        "packages": typst_packages(library),
        "fonts": fonts(library),
        "dictionaries": dictionaries(),
        "licences": [{"id": i, "name": n} for i, n in LICENCES],
    }


def text(ref: str, library=None) -> Optional[str]:
    """The full text behind one row or one licence. Only files that ship with
    the app or sit in an installed module are read."""
    if ref.startswith("licence:"):
        ident = ref.split(":", 1)[1]
        if ident not in {i for i, _ in LICENCES}:
            return None
        return (TEXTS / f"{ident}.txt").read_text("utf-8", errors="replace")
    if ref.startswith("part:"):
        name = ref.split(":", 1)[1]
        file = (LICENCES_DIR / name).resolve()
        if LICENCES_DIR.resolve() not in file.parents or not file.is_file():
            return None
        return file.read_text("utf-8", errors="replace")
    if ref.startswith("file:"):
        file = Path(ref.split(":", 1)[1]).resolve()
        allowed = [paths.PACKAGE_DIR.resolve()]
        if library is not None:
            allowed.append(Path(library.root).resolve())
        if not file.is_file() or not any(root in file.parents for root in allowed):
            return None
        return file.read_text("utf-8", errors="replace")
    return None
