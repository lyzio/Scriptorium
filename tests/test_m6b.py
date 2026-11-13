"""Milestone 6 part B: safer builds and the window's new parts. Test Plan
T-BUILD-28, T-BUILD-29, T-MOD-25, T-UI-30, T-UI-33, T-UI-34 and T-UI-35."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

import pytest

from scriptorum import paths
from scriptorum.core import helper as helper_module
from scriptorum.core import modmanager
from scriptorum.core.helper import helper
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library, ModuleError
from scriptorum.core.recent import RecentFiles
from scriptorum.core.session import Session

BUNDLED = paths.BUNDLED_MODULES_DIR
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 4.0  # seconds: the real limit is 60 (F7.1); the tests need not wait a minute
# Nested small loops: busy for minutes without using memory (one loop over a
# huge range would build the whole list first and run out of memory instead).
SPIN = "#let _spin = { let n = 0; for i in range(100000) { for j in range(100000) { n += 1 } }; n }\n#let _ = _spin\n"


@pytest.fixture
def short_limit(monkeypatch):
    monkeypatch.setattr(helper_module, "TIME_LIMIT", LIMIT)
    yield LIMIT


def theme(tmp_path, module_id="test.ink", spin=False, version="1.0.0") -> Path:
    target = tmp_path / "src" / f"{module_id}-{version}"
    shutil.copytree(BUNDLED / "scriptorum.plain", target)
    manifest = json.loads((target / "module.json").read_text("utf-8"))
    manifest.update({"id": module_id, "version": version, "name": "Ink"})
    manifest.pop("standard", None)
    (target / "module.json").write_text(json.dumps(manifest), "utf-8")
    if spin:  # a theme that never finishes building (F7.1)
        scene = target / "templates" / "scene.typ"
        scene.write_text(scene.read_text("utf-8") + "\n" + SPIN, "utf-8")
    return target


def scmod(folder: Path, tmp_path: Path) -> Path:
    target = tmp_path / f"{folder.name}.scmod"
    with zipfile.ZipFile(target, "w") as zf:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(folder).as_posix())
    return target


@pytest.fixture
def lib(tmp_path):
    library = Library(tmp_path / "library")
    library.install_bundled(BUNDLED)
    return library


@pytest.fixture
def tab(lib, tmp_path):
    return Session(lib, Strings.from_library(lib), RecentFiles(tmp_path / "recent.json"), tmp_path / "build",
                   home=tmp_path / "home")


TEXT = '#scene(title: "The harbour")[\nThe fog lifts.\n]\n'


# --- T-BUILD-28 the time limit --------------------------------------------------------------
@pytest.mark.integration
def test_T_BUILD_28_build_stopped_after_time_limit(lib, tab, tmp_path, short_limit):
    """T-BUILD-28: a build that never finishes is stopped after the time
    limit and says so; the session stays usable during the wait; the next
    build after the fault is removed works; normal builds are as fast as before."""
    shutil.copytree(theme(tmp_path, spin=True), lib.root / "test.ink" / "1.0.0")
    tab.new("Fog", "scriptorum.plain-system", "1.0.0", "test.ink", "1.0.0")
    tab.set_chapter_text(0, TEXT)
    box, answered = {}, []

    def build():
        box["result"] = tab.build("svg")

    started = time.monotonic()
    worker = threading.Thread(target=build)
    worker.start()
    # The editor stays usable: the session answers while the build runs.
    while worker.is_alive() and time.monotonic() - started < LIMIT - 1:
        answered.append(tab.info()["title"])
        tab.set_chapter_text(0, TEXT)
        time.sleep(0.2)
    worker.join(LIMIT + 20)
    took = time.monotonic() - started
    result = box["result"]
    assert not result.ok and result.errors[0].key == "error.build.timeLimit"
    assert LIMIT - 0.5 < took < LIMIT + 10
    assert answered and set(answered) == {"Fog"}
    text = tab.localize(result.errors[0])
    assert text == f"The last build was stopped after {int(LIMIT)} seconds, probably because of a theme or module."
    # The fault removed: the next build works.
    tab.set_theme("scriptorum.plain")
    assert tab.build("svg").ok
    # Normal builds are as fast as before: a rebuild of a short adventure.
    times = []
    for _ in range(3):
        t = time.monotonic()
        assert tab.build("svg").ok
        times.append(time.monotonic() - t)
    assert min(times) < 0.5


# --- T-BUILD-29 the helper is reused, survives a crash, stops an export cleanly ------------------
@pytest.mark.integration
def test_T_BUILD_29_helper_reused(tab):
    """T-BUILD-29: the helper is reused between builds."""
    tab.new("Fog", "scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
    assert tab.build("svg").ok
    pid, starts = helper().pid(), helper().starts
    for _ in range(3):
        assert tab.build("svg").ok
    assert helper().pid() == pid and helper().starts == starts


@pytest.mark.integration
def test_T_BUILD_29_crash_inside_the_helper(lib, tab, tmp_path, short_limit):
    """T-BUILD-29: a crash inside the helper leaves the text untouched, says
    the build stopped unexpectedly, and the next build starts a new helper."""
    shutil.copytree(theme(tmp_path, spin=True), lib.root / "test.ink" / "1.0.0")
    tab.new("Fog", "scriptorum.plain-system", "1.0.0", "test.ink", "1.0.0")
    tab.set_chapter_text(0, TEXT)
    box = {}
    worker = threading.Thread(target=lambda: box.setdefault("result", tab.build("svg")))
    worker.start()
    assert helper_module.wait_for(lambda: helper().pid() is not None, 10)
    time.sleep(0.5)
    helper().process.kill()  # Typst "crashes" in the middle of the build
    worker.join(20)
    result = box["result"]
    assert not result.ok and result.errors[0].key == "error.build.crashed"
    assert tab.localize(result.errors[0]).startswith("The last build stopped unexpectedly.")
    assert tab.chapter(0)["text"] == TEXT and tab.dirty
    starts = helper().starts
    tab.set_theme("scriptorum.plain")
    assert tab.build("svg").ok and helper().starts == starts + 1


@pytest.mark.integration
def test_T_BUILD_29_stopped_export_writes_no_file(lib, tab, tmp_path, short_limit):
    """T-BUILD-29: an export stopped by the time limit says so and writes no
    file; an existing file of the same name stays as it was."""
    shutil.copytree(theme(tmp_path, spin=True), lib.root / "test.ink" / "1.0.0")
    tab.new("Fog", "scriptorum.plain-system", "1.0.0", "test.ink", "1.0.0")
    tab.set_chapter_text(0, TEXT)
    new = tmp_path / "out" / "new.pdf"
    old = tmp_path / "out" / "old.pdf"
    old.parent.mkdir()
    old.write_bytes(b"%PDF-1.7 the earlier export")
    reply = tab.export_pdf(new)
    assert not reply["ok"] and "stopped after" in reply["errors"][0]["text"]
    assert not new.exists()
    reply = tab.export_pdf(old)
    assert not reply["ok"] and old.read_bytes() == b"%PDF-1.7 the earlier export"
    assert not [p for p in old.parent.iterdir() if p.name.endswith(".tmp")]


# --- T-MOD-25 a module whose build never finishes ------------------------------------------------
@pytest.mark.integration
def test_T_MOD_25_install_refused_within_time_limit(lib, tmp_path, short_limit):
    """T-MOD-25: installing a module whose build never finishes is refused
    within the time limit, and nothing is left in the library."""
    before = sorted(p.relative_to(lib.root).as_posix() for p in lib.root.rglob("*"))
    started = time.monotonic()
    with pytest.raises(ModuleError) as info:
        modmanager.install(lib, scmod(theme(tmp_path, spin=True), tmp_path))
    assert time.monotonic() - started < LIMIT * 3 + 10
    assert info.value.key == "error.module.timeLimit"
    text = Strings.from_library(lib).t(info.value.key, **info.value.details)
    assert text == f"Ink did not finish building within {int(LIMIT)} seconds, so it was not installed."
    assert sorted(p.relative_to(lib.root).as_posix() for p in lib.root.rglob("*")) == before


@pytest.mark.integration
def test_T_MOD_25_self_test_finishes(lib, tab, tmp_path, short_limit):
    """T-MOD-25: Help ▸ Check installation's theme self-test finishes and
    names a theme copied into the library by hand whose build never finishes."""
    from scriptorum.core.startup import theme_self_test

    shutil.copytree(theme(tmp_path, spin=True), lib.root / "test.ink" / "1.0.0")
    started = time.monotonic()
    lines = theme_self_test(tab)
    assert time.monotonic() - started < LIMIT * 6 + 30
    failed = [line for line in lines if line.get("problems")]
    assert failed and {line["theme"] for line in failed} == {"Ink"}
    assert any("stopped after" in p for line in failed for p in line["problems"])


# --- T-UI-33 no milestone names in the interface ------------------------------------------------------
@pytest.mark.unit
def test_T_UI_33_no_milestone_names_in_interface_text(library):
    """T-UI-33: no interface text names a milestone, and the removed texts
    are gone (F15)."""
    table = Strings.from_library(library).table
    pattern = re.compile(r"\bM[1-9]\b|later milestone|arrives? in", re.I)
    offenders = {k: v for k, v in table.items() if not k.startswith("guide") and pattern.search(v)}
    assert offenders == {}
    for gone in ("app.later", "settings.laterNote", "sidebar.laterTab", "menu.saveForSharing"):
        assert gone not in table
    assert table["menu.insertNeedsAdventure"] == "Open or create an adventure first"
    assert table["menu.insertReadOnly"] == "This adventure is read-only"
    html = (paths.UI_DIR / "index.html").read_text("utf-8")
    assert "settings.laterNote" not in html


# --- the window ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6b")
    library = Library(folder / "library")
    library.install_bundled(BUNDLED)
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build",
                      home=folder / "home")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def _menu(ui, key):
    return [i for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == key for i in m["items"]]


@pytest.mark.ui
def test_T_UI_33_insert_menu_says_why(ui):
    """T-UI-33: the Insert menu with no adventure open says why it is empty."""
    labels = [i["label"] for i in _menu(ui, "menu.insert")]
    assert labels == ["Open or create an adventure first"]
    assert all("sharing" not in i["label"] for i in _menu(ui, "menu.file"))


@pytest.mark.ui
def test_T_UI_34_about_window(ui):
    """T-UI-34: the About window, its three tabs, every part's licence text,
    every licence, the idea credit, and no network request."""
    blocked = len(ui.window.interceptor.blocked)
    ui.run("window.__scriptorum.about.openAbout()")
    assert ui.js("document.getElementById('about-dialog').open") is True
    text = ui.js("document.getElementById('about-page-about').textContent")
    assert "Idea by lyzio · lyzio.net" in text and "Free software under the GNU GPL, version 3 or later." in text
    assert "Created by" not in text and "written by" not in text.lower()
    assert ui.js("document.getElementById('about-version').textContent").startswith("Version 0.")
    info = ui.js("window.__scriptorum.about.info()")
    names = {r["name"]: r for r in info["programs"]}
    assert set(names) == {"Python", "Qt and PySide6", "Qt WebEngine (Chromium)", "Typst", "spylls",
                          "Cytoscape.js", "Phosphor Icons (Light)"}
    assert names["Typst"]["version"] == "0.15.0" and names["Typst"]["licence"] == "Apache-2.0"
    assert names["spylls"]["licence"] == "MPL-2.0"  # its own licence file (the register said MIT)
    assert names["Qt and PySide6"]["version"].startswith("6.8")
    assert {(p["name"], p["version"]) for p in info["packages"]} == {("fletcher", "0.5.8"), ("CeTZ", "0.3.4"), ("oxifmt", "0.2.1")}
    fonts = {f["name"] for f in info["fonts"]}
    assert {"Libre Baskerville", "Playfair Display", "Berolina", "EB Garamond", "Special Elite", "Homemade Apple"} <= fonts
    assert len(info["dictionaries"]) == 3
    # Every row opens its full text.
    rows = ui.js("[...document.querySelectorAll('#about-hood tr.about-row')].map(r => r.dataset.part)")
    assert len(rows) == len(info["programs"]) + len(info["packages"]) + len(info["fonts"]) + len(info["dictionaries"])
    for index, part in enumerate(rows):
        ui.run(f"document.querySelectorAll('#about-hood tr.about-row')[{index}].click()")
        ui.wait_until(lambda: not ui.js("document.getElementById('about-text-box').classList.contains('hidden')"), 5)
        body = ui.js("document.getElementById('about-text').textContent")
        assert len(body) > 400 and "could not be found" not in body, part
        ui.js("document.getElementById('about-text-back').click(); true")
    chromium = rows.index("chromium")
    ui.run(f"document.querySelectorAll('#about-hood tr.about-row')[{chromium}].click()")
    assert "too long to show line by line" in ui.js("document.getElementById('about-text').textContent")
    # Every licence's full text.
    ids = ui.js("[...document.querySelectorAll('#about-licences button')].map(b => b.dataset.licence)")
    assert ids == ["GPL-3.0", "LGPL-3.0", "Apache-2.0", "MPL-2.0", "MIT", "MIT-0", "BSD-3-Clause", "OFL-1.1", "Python"]
    for ident in ids:
        ui.run(f"document.querySelector('#about-licences button[data-licence=\"{ident}\"]').click()")
        assert len(ui.js("document.getElementById('about-text').textContent")) > 800
    # lyzio.net opens in the computer's browser, not in Scriptorum.
    ui.js("window.__scriptorum.about.showTab('about'); document.getElementById('about-site').click(); true")
    ui.wait_until(lambda: getattr(ui.window.bridge, "opened_sites", []) == ["https://lyzio.net"], 5)
    assert len(ui.window.interceptor.blocked) == blocked
    ui.js("document.getElementById('about-close').click(); true")
    assert ui.js("document.getElementById('about-dialog').open") is False


@pytest.mark.ui
def test_T_UI_35_full_screen(ui):
    """T-UI-35: the toolbar button, the View menu and the shortcut enter and
    leave full screen; Esc leaves it; the choice is remembered."""
    settings = ui.window.session.app_settings
    ui.window.bridge._tab_for_new_document().new("Fog", "scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
    ui.window.bridge._changed()
    ui.run("window.__scriptorum.refresh()")
    assert ui.js("!!document.querySelector('#tb-fullscreen svg')")
    view = lambda: [i["label"] for i in _menu(ui, "menu.view")]  # noqa: E731
    assert "Enter full screen" in view()
    ui.js("document.getElementById('tb-fullscreen').click(); true")
    ui.wait_until(lambda: ui.window.isFullScreen(), 10)
    ui.wait_until(lambda: ui.js("window.__scriptorum.fullScreen()") is True, 5)
    assert settings.get("full_screen") is True
    assert "Exit full screen" in view()
    assert ui.js("document.getElementById('tb-fullscreen').getAttribute('aria-pressed')") == "true"
    # Menu bar, toolbar and status bar stay.
    assert ui.js("['menubar', 'toolbar', 'statusbar'].every(id => !document.getElementById(id).classList.contains('hidden'))")
    ui.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true")
    ui.wait_until(lambda: not ui.window.isFullScreen(), 10)
    assert settings.get("full_screen") is False
    ui.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'F11', bubbles: true})); true")
    ui.wait_until(lambda: ui.window.isFullScreen(), 10)
    ui.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'F11', bubbles: true})); true")
    ui.wait_until(lambda: not ui.window.isFullScreen(), 10)
    # The window manager (or the Mac's green button) changes it too, and the page follows.
    ui.window.showFullScreen()
    ui.wait_until(lambda: ui.js("window.__scriptorum.fullScreen()") is True, 10)
    assert settings.get("full_screen") is True
    ui.window.showNormal()
    ui.wait_until(lambda: ui.js("window.__scriptorum.fullScreen()") is False, 10)
    assert settings.get("full_screen") is False


# --- T-UI-30 the pages' script policy ----------------------------------------------------------------------
@pytest.mark.ui
def test_T_UI_30_page_script_policy(library, tmp_path):
    """T-UI-30: both pages carry the policy; the app works as before; an
    inline script and eval are refused. This window loads the real page
    (test_eval=False), as the app does."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow

    for name in ("index.html", "preview.html"):
        html = (paths.UI_DIR / name).read_text("utf-8")
        policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
        assert "script-src 'self' qrc:;" in policy and "unsafe-inline" not in policy.split("style-src")[0]
        assert "unsafe-eval" not in policy and "default-src 'none'" in policy
        assert not re.search(r"<script(?![^>]*\bsrc=)", html)  # no inline script anywhere

    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(tmp_path / "recent.json"), tmp_path / "build",
                      home=tmp_path / "home")
    window = MainWindow(session, headless_test=True, test_eval=False)
    window.show()

    def js(code):  # no eval here: the code itself is the expression
        box = {}
        loop = QEventLoop()
        window.page.runJavaScript(code, 0, lambda r: (box.setdefault("r", r), loop.quit()))
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        return box.get("r")

    try:
        end = time.monotonic() + 60
        while not window.bridge.ui_ready and time.monotonic() < end:
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        assert window.bridge.ui_ready  # the app works under its policy
        assert js("typeof window.__scriptorum") == "object"
        assert js("document.querySelectorAll('#menubar .menu-btn').length") == 6
        # An inline script, as an escaping mistake would insert one, is refused.
        js("(() => { const s = document.createElement('script'); s.textContent = 'window.__ran = 1'; "
           "document.body.append(s); const d = document.createElement('div'); "
           "d.innerHTML = '<img src=x onerror=\"window.__ran2 = 1\">'; document.body.append(d); return 1; })()")
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        assert js("typeof window.__ran") == "undefined" and js("typeof window.__ran2") == "undefined"
        assert js("(() => { try { eval('1 + 1'); return 'ran'; } catch (e) { return 'refused'; } })()") == "refused"
        assert window.interceptor.blocked == []
    finally:
        window.close()


@pytest.mark.ui
def test_T_BUILD_28_status_bar_says_so(ui, tmp_path, short_limit):
    """T-BUILD-28 in the window: the status bar says the build was stopped,
    the preview keeps its last good pages, and the next edit tries again."""
    library = ui.window.session.library
    shutil.copytree(theme(tmp_path, module_id="test.spin", spin=True), library.root / "test.spin" / "1.0.0")
    bridge = ui.window.bridge
    tab = bridge._tab_for_new_document()
    tab.new("Fog", "scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
    tab.set_chapter_text(0, TEXT)
    bridge._changed()
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.js("document.querySelectorAll('#pages img').length") > 0, 20)
    pages = ui.js("document.querySelectorAll('#pages img').length")
    manifest = tab.adventure.manifest  # switch to the looping theme
    manifest["theme"] = {"id": "test.spin", "version": "1.0.0"}
    manifest["modules"] = [m if m["id"] != "scriptorum.plain" else {"id": "test.spin", "version": "1.0.0"} for m in manifest["modules"]]
    before = ui.builds()
    bridge.requestBuild()
    ui.wait_until(lambda: "stopped after" in (ui.js("document.getElementById('st-problems').textContent") or ""), LIMIT + 20)
    assert ui.js("document.getElementById('st-problems').textContent").startswith(f"The last build was stopped after {int(LIMIT)} seconds")
    assert ui.js("document.querySelectorAll('#pages img').length") == pages  # the last good pages stay
    tab.set_theme("scriptorum.plain")
    bridge.requestBuild()
    ui.wait_until(lambda: ui.js("document.getElementById('st-problems').textContent") == "No errors", 20)
    assert ui.builds() > before
