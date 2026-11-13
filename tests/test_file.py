"""Test Plan group FILE — the .scav file (F1, F2)."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile

import pytest

from scriptorum.core import scav
from scriptorum.core.recent import RecentFiles
from scriptorum.core.scav import ModuleRef, NewerFormatError

pytestmark = pytest.mark.unit

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_T_FILE_01_new_save_reopen(session, tmp_path):
    """T-FILE-01: title, game system, theme, module versions and text survive."""
    session.new("Skuggan över Ödmården", *GS, *TH)
    text = session.adventure.chapter_text("text/chapter-01.typ") + "\nÅsa och Örjan.\n"
    session.set_chapter_text(0, text)
    path = session.save(tmp_path / "skuggan.scav")
    reopened = scav.load(path)
    assert reopened.title == "Skuggan över Ödmården"
    assert reopened.game_system == ModuleRef(*GS)
    assert reopened.theme == ModuleRef(*TH)
    assert {m.id: m.version for m in reopened.modules} == {
        "scriptorum.core": "1.0.0", GS[0]: GS[1], TH[0]: TH[1],
    }
    assert reopened.chapter_text("text/chapter-01.typ") == text


def test_T_FILE_02_zip_layout(session, tmp_path):
    """T-FILE-02: a zip with manifest, settings and the section 4 folders."""
    session.new("Layout", *GS, *TH)
    path = session.save(tmp_path / "layout.scav")
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert {"manifest.json", "settings.json", "text/chapter-01.typ"} <= names
    for folder in scav.FOLDERS:
        assert folder in names
    for key in ("format", "app", "title", "game_system", "theme", "modules", "chapters", "created", "modified"):
        assert key in manifest


@pytest.mark.parametrize("failing", ["os.replace", "os.fsync"])
def test_T_FILE_03_crash_during_save_keeps_old_file(session, tmp_path, monkeypatch, failing):
    """T-FILE-03: a crash in the middle of saving leaves the old file intact."""
    session.new("Crash test", *GS, *TH)
    path = session.save(tmp_path / "crash.scav")
    before = _digest(path)

    session.set_chapter_text(0, "= Changed\n")

    def boom(*args, **kwargs):
        raise OSError("power cut")

    module, name = failing.split(".")
    monkeypatch.setattr(getattr(scav, module), name, boom)
    with pytest.raises(OSError):
        session.save(path)
    monkeypatch.undo()

    assert _digest(path) == before
    assert scav.load(path).title == "Crash test"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_T_FILE_04_newer_format_refused_untouched(tmp_path, sample):
    """T-FILE-04: a newer format gives a plain message and is not modified."""
    path = sample("m1-basic")
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["format"] = scav.FORMAT_VERSION + 1
    files["manifest.json"] = json.dumps(manifest).encode()
    newer = tmp_path / "newer.scav"
    with zipfile.ZipFile(newer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    before = _digest(newer)
    with pytest.raises(NewerFormatError) as info:
        scav.load(newer)
    assert info.value.key == "error.scav.newerFormat"
    assert _digest(newer) == before


def test_T_FILE_05_older_format_migrated(tmp_path, sample, monkeypatch):
    """T-FILE-05: an older format is migrated in memory and saved as current."""
    path = sample("m1-basic")
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["format"] = 0
    manifest["name"] = manifest.pop("title")  # pretend format 0 called it "name"
    files["manifest.json"] = json.dumps(manifest).encode()
    old = tmp_path / "old.scav"
    with zipfile.ZipFile(old, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)

    def zero_to_one(manifest, files):
        manifest["title"] = manifest.pop("name")
        return manifest, files

    monkeypatch.setitem(scav.MIGRATIONS, 0, zero_to_one)
    adventure = scav.load(old)
    assert adventure.migrated_from == 0
    assert adventure.title == "Skuggan över Ödmården"
    scav.save(adventure, old)
    with zipfile.ZipFile(old) as zf:
        assert json.loads(zf.read("manifest.json"))["format"] == scav.FORMAT_VERSION


def test_T_FILE_06_recent_files(tmp_path):
    """T-FILE-06: most recent first, no duplicates."""
    recent = RecentFiles(tmp_path / "recent.json")
    a, b = tmp_path / "a.scav", tmp_path / "b.scav"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    recent.add(a)
    recent.add(b)
    recent.add(a)
    assert recent.list() == [str(a.resolve()), str(b.resolve())]


def test_T_FILE_07_open_save_without_edits_keeps_text(session, sample, tmp_path):
    """T-FILE-07: opening and saving without edits leaves every text file identical."""
    for name in ("m1-basic", "m1-locked"):
        path = sample(name)
        with zipfile.ZipFile(path) as zf:
            before = {n: zf.read(n) for n in zf.namelist() if n.startswith("text/")}
        session.open(path)
        session.chapter(0)  # parse it, as the editor would
        out = session.save(tmp_path / f"{name}-resaved.scav")
        with zipfile.ZipFile(out) as zf:
            after = {n: zf.read(n) for n in zf.namelist() if n.startswith("text/") and not n.endswith("/")}
        assert after == before
