"""Where Scriptorum keeps its own data on each platform.

Everything lives in one per-user folder. The SCRIPTORUM_HOME environment
variable overrides it, which the tests use to stay isolated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BUNDLED_MODULES_DIR = PACKAGE_DIR / "bundled"
UI_DIR = PACKAGE_DIR / "ui"


def app_home() -> Path:
    """The per-user data folder (module library, recent files, logs)."""
    override = os.environ.get("SCRIPTORUM_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Scriptorum"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Scriptorum"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "scriptorum"
    base.mkdir(parents=True, exist_ok=True)
    return base


def module_library_dir() -> Path:
    path = app_home() / "modules"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_home() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_root() -> Path:
    """Scratch space for builds. Never inside the author's adventure."""
    path = app_home() / "builds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def examples_dir() -> Path:
    """F20: the example adventures bundled with the app (unpacked folders)."""
    return Path(__file__).resolve().parent / "examples"


def documents_dir() -> Path:
    """The user's documents folder, where a copy of the example adventure is
    made (F20). SCRIPTORUM_DOCUMENTS overrides it (used by the tests)."""
    override = os.environ.get("SCRIPTORUM_DOCUMENTS")
    if override:
        path = Path(override)
    else:
        path = Path.home() / "Documents"
        if not path.is_dir():
            path = Path.home()
    path.mkdir(parents=True, exist_ok=True)
    return path
