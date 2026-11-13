"""Shared test setup (Test Plan sections 2 and 5).

Each test run gets its own Scriptorum home folder, so tests never touch a
real module library or recent-files list.
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "samples"
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def update_test_key():
    """F22 (M6-0.6.7): the app trusts the tests' own key while they run, never
    the project's; tests of a copy without a key set it back to empty."""
    from scriptorum.core import update_key
    from tests.update_keys import PUBLIC

    saved = update_key.PUBLIC_KEY
    update_key.PUBLIC_KEY = PUBLIC
    os.environ["SCRIPTORUM_NO_UPDATES"] = "1"   # no test starts a kept version by accident
    yield PUBLIC
    update_key.PUBLIC_KEY = saved


@pytest.fixture(scope="session")
def home(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("scriptorum-home")
    os.environ["SCRIPTORUM_HOME"] = str(path)
    return path


@pytest.fixture(scope="session")
def library(home):
    from scriptorum import paths
    from scriptorum.core.modules import Library

    lib = Library(paths.module_library_dir())
    lib.install_bundled(paths.BUNDLED_MODULES_DIR)
    return lib


@pytest.fixture
def session(library, tmp_path):
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    return Session(library, Strings.from_library(library), RecentFiles(tmp_path / "recent.json"), tmp_path / "build")


def pack_sample(name: str, target_dir: Path) -> Path:
    """Zip a sample folder (tests/samples/<name>/) into a .scav file."""
    folder = SAMPLES / name
    target = target_dir / f"{name}.scav"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(folder).as_posix())
    return target


@pytest.fixture
def sample(tmp_path):
    return lambda name: pack_sample(name, tmp_path)


def sample_text(name: str) -> str:
    return (SAMPLES / name / "text" / "chapter-01.typ").read_text("utf-8")
