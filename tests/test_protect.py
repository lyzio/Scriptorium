"""Test Plan group FILE, Milestone 2 — work protection and file handling (F2)."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import zipfile
from pathlib import Path

import pytest

from scriptorum.core import crashlog, scav
from scriptorum.core.scav import ScavError
from tests.conftest import ROOT, SAMPLES

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


@pytest.mark.ui
def test_T_FILE_08_crash_loses_no_more_than_the_last_pause(tmp_path):
    """T-FILE-08: text typed before a pause survives a forced crash; the next
    start offers to restore it."""
    home = tmp_path / "home"
    script = tmp_path / "crash.py"
    script.write_text(textwrap.dedent(f"""
        import json, os, sys
        sys.path.insert(0, {str(ROOT)!r})
        os.environ["SCRIPTORUM_HOME"] = {str(home)!r}
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        from scriptorum.app.main import MainWindow
        from scriptorum.core.session import Session
        app = QApplication([])
        window = MainWindow(Session.start(), headless_test=True)
        window.show()
        def wait(ms):
            loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()
        def js(code):
            box = {{}}; loop = QEventLoop()
            window.page.runJavaScript(code, 0, lambda r: (box.setdefault("r", r), loop.quit()))
            QTimer.singleShot(5000, loop.quit); loop.exec(); return box.get("r")
        while not window.bridge.ui_ready: wait(50)
        window.bridge.newAdventure(json.dumps({{"title": "Crash", "gameSystem": {{"id": "{GS[0]}", "version": "{GS[1]}"}}, "theme": {{"id": "{TH[0]}", "version": "{TH[1]}"}}}}))
        js("window.__scriptorum.refresh()"); wait(1500)
        def type_title(text):
            js("const i = document.querySelector('.el-scene .field-title input'); i.focus(); i.value = " + json.dumps(text) + "; i.dispatchEvent(new Event('input', {{bubbles: true}})); true")
        type_title("Before the pause")
        wait(1200)  # a pause in typing: the edit reaches the core
        type_title("After the pause, never sent")
        wait(50)
        os._exit(1)  # a hard crash: no clean shutdown
    """))
    run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 1, run.stderr[-2000:]

    from scriptorum.core.i18n import Strings
    from scriptorum.core.modules import Library
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    library = Library(home / "modules")
    session = Session(library, Strings.from_library(library), RecentFiles(tmp_path / "recent.json"), tmp_path / "build", home=home)
    offered = session.recovery.orphans()
    assert [m["title"] for m in offered] == ["Crash"]
    session.restore_recovery(offered[0])
    text = session.adventure.chapter_text("text/chapter-01.typ")
    assert '#scene(title: "Before the pause")' in text
    assert session.dirty and session.adventure.path is None
    assert session.recovery.orphans() == []


@pytest.mark.unit
def test_T_FILE_09_snapshots_and_revert(session, tmp_path):
    """T-FILE-09: a snapshot every 15 minutes while there are changes; revert
    restores the chosen one."""
    session.new("Snapshots", *GS, *TH)
    path = session.save(tmp_path / "snap.scav")
    start = time.time()
    assert session.maybe_snapshot(start + 10) is None  # not yet 15 minutes
    first = session.adventure.chapter_text("text/chapter-01.typ")
    assert session.maybe_snapshot(start + 15 * 60 + 1) is not None  # newly saved changes
    session.set_chapter_text(0, first + "\nA second version.\n")
    assert session.maybe_snapshot(start + 20 * 60) is None  # 15 minutes since the last one
    assert session.maybe_snapshot(start + 31 * 60) is not None
    assert session.maybe_snapshot(start + 47 * 60) is None  # no changes since: none taken
    snapshots = session.snapshot_list()
    assert len(snapshots) == 2
    oldest = snapshots[-1]["id"]
    session.set_chapter_text(0, "= Something else\n")
    session.revert(oldest)
    assert session.adventure.chapter_text("text/chapter-01.typ") == first
    assert session.dirty
    assert scav.load(path).chapter_text("text/chapter-01.typ") == first  # the file is untouched


@pytest.mark.integration
def test_T_FILE_10_unpacked_folder(session, tmp_path):
    """T-FILE-10: an unpacked adventure folder is opened, edited and saved as
    a folder; only the changed lines change."""
    folder = tmp_path / "adventure"
    shutil.copytree(SAMPLES / "m1-basic", folder)
    session.open(folder)
    assert session.adventure.is_folder
    session.save()  # a folder Scriptorum has saved once, as an author's Git repository would hold
    time.sleep(1.1)  # so the "modified" time differs
    before = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    text = session.adventure.chapter_text("text/chapter-01.typ")
    session.set_chapter_text(0, text.replace("keeps the doors *barred* after dusk", "keeps the doors *locked* after dusk"))
    session.save()
    after = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed == {"text/chapter-01.typ", "manifest.json"}
    diff = [l for l in difflib.unified_diff(before["text/chapter-01.typ"].decode().splitlines(),
                                            after["text/chapter-01.typ"].decode().splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert len(diff) == 2 and "*locked*" in diff[1]
    manifest_diff = [l for l in difflib.unified_diff(before["manifest.json"].decode().splitlines(),
                                                     after["manifest.json"].decode().splitlines(), lineterm="", n=0)
                     if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert len(manifest_diff) == 2 and all('"modified"' in l for l in manifest_diff)
    assert (folder / "settings.json").read_bytes() == before["settings.json"]
    assert scav.load(folder).chapter_text("text/chapter-01.typ") == session.adventure.chapter_text("text/chapter-01.typ")


@pytest.mark.integration
def test_T_FILE_11_protected_mode(session, sample, tmp_path):
    """T-FILE-11: a missing module opens the adventure in protected mode:
    content intact, export blocked, the module named."""
    path = sample("m1-basic")
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["modules"].append({"id": "test.missing-kit", "version": "2.0.0"})
    files["manifest.json"] = json.dumps(manifest).encode()
    needy = tmp_path / "needy.scav"
    with zipfile.ZipFile(needy, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    session.open(needy)
    assert session.read_only == "protected"
    assert session.info()["missingModules"] == [{"id": "test.missing-kit", "version": "2.0.0"}]
    original = session.adventure.chapter_text("text/chapter-01.typ")
    session.set_chapter_text(0, "= Changed\n")
    assert session.adventure.chapter_text("text/chapter-01.typ") == original
    reply = session.export_pdf(tmp_path / "blocked.pdf")
    assert not reply["ok"] and "test.missing-kit" in reply["errors"][0]["text"]
    assert not (tmp_path / "blocked.pdf").exists()
    with pytest.raises(ScavError):
        session.save()
    assert session.chapter(0)["text"] == original


@pytest.mark.integration
def test_T_FILE_12_shared_adventure_cannot_reach_outside(session, tmp_path):
    """T-FILE-12: a shared adventure cannot read or write outside its folder."""
    # A file name in the zip that climbs out of the adventure.
    evil = tmp_path / "evil.scav"
    with zipfile.ZipFile(evil, "w") as zf:
        for file in sorted((SAMPLES / "m1-basic").rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(SAMPLES / "m1-basic").as_posix())
        zf.writestr("assets/../../escape.txt", b"x")
    with pytest.raises(ScavError) as info:
        scav.load(evil)
    assert info.value.key == "error.scav.unsafeName"
    # A link inside an unpacked folder is never followed.
    folder = tmp_path / "linked"
    shutil.copytree(SAMPLES / "m1-basic", folder)
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    (folder / "assets" / "images").mkdir(parents=True)
    os.symlink(secret, folder / "assets" / "images" / "link.png")
    adventure = scav.load(folder)
    assert "assets/images/link.png" not in adventure.files
    # A chapter cannot read a file outside the build folder.
    session.new("Escape", *GS, *TH)
    session.set_chapter_text(0, f'= Escape\n\n#read("/../../../../{secret}")\n')
    assert not session.build("pdf").ok


@pytest.mark.integration
def test_T_FILE_14_open_elsewhere_is_read_only(library, sample, tmp_path):
    """T-FILE-14: an adventure already open in another window opens read-only."""
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    def window(name):
        return Session(library, Strings.from_library(library), RecentFiles(tmp_path / "recent.json"), tmp_path / name)

    path = sample("m1-basic")
    first, second = window("one"), window("two")
    first.open(path)
    assert first.read_only is None
    second.open(path)
    assert second.read_only == "openElsewhere"
    text = second.adventure.chapter_text("text/chapter-01.typ")
    second.set_chapter_text(0, "= Not allowed\n")
    assert second.adventure.chapter_text("text/chapter-01.typ") == text
    with pytest.raises(ScavError):
        second.save()
    copy = second.save(tmp_path / "copy.scav")  # Save as still works
    assert copy.exists() and second.read_only is None
    first.close()
    third = window("three")
    third.open(path)
    assert third.read_only is None


@pytest.mark.unit
def test_T_FILE_15_crash_log(tmp_path):
    """T-FILE-15: an unexpected error writes a crash log locally."""
    previous = sys.excepthook
    try:
        crashlog.install(tmp_path)
        try:
            raise RuntimeError("Something unexpected")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous
    logs = list(tmp_path.glob("crash-*.log"))
    assert len(logs) == 1
    text = logs[0].read_text("utf-8")
    assert "RuntimeError: Something unexpected" in text and "Scriptorum" in text
