"""Test Plan UI smoke tests: the real window, started without a screen.

The tests run in file order and share one window, like one person working
through the Milestone 1 checklist.
"""

from __future__ import annotations

import json
import os
import time

import pytest

pytestmark = pytest.mark.ui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")


class Driver:
    def __init__(self, app, window):
        self.app = app
        self.window = window

    def wait(self, ms: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def js(self, code: str):
        from PySide6.QtCore import QEventLoop, QTimer

        # Values travel as JSON: Qt does not hand JavaScript arrays back to Python.
        wrapped = f"JSON.stringify(eval({json.dumps(code)}))"
        box = {}
        loop = QEventLoop()
        self.window.page.runJavaScript(wrapped, 0, lambda result: (box.setdefault("r", result), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        result = box.get("r")
        return json.loads(result) if isinstance(result, str) and result else None

    def run(self, expression: str, timeout: float = 15) -> None:
        """Run an async JavaScript expression and wait until it has finished."""
        self.js(f"window.__done = false; Promise.resolve({expression}).then(() => window.__done = true); null")
        self.wait_until(lambda: self.js("window.__done") is True, timeout)

    def wait_until(self, predicate, timeout: float = 15) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            self.wait(50)
        raise AssertionError("timed out waiting")

    def state(self) -> dict:
        return self.js("window.__scriptorum.state()")

    def builds(self) -> int:
        return int(self.js("Number(document.body.dataset.buildCount || 0)"))

    def type_input(self, selector: str, value: str) -> None:
        self.js(
            f"(() => {{ const el = document.querySelector({json.dumps(selector)}); el.focus();"
            f" el.value = {json.dumps(value)}; el.dispatchEvent(new Event('input', {{bubbles: true}})); }})()"
        )

    def type_rich(self, selector: str, html: str) -> None:
        self.js(
            f"(() => {{ const el = document.querySelector({json.dumps(selector)}); el.focus();"
            f" el.innerHTML = {json.dumps(html)}; el.dispatchEvent(new Event('input', {{bubbles: true}})); }})()"
        )


@pytest.fixture(scope="module")
def ui(library, tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    folder = tmp_path_factory.mktemp("ui")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def test_T_UI_01_window_starts(ui):
    """T-UI-01: the app starts and shows the main window."""
    menus = ui.js("[...document.querySelectorAll('#menubar .menu-btn')].map(b => b.textContent)")
    # M4 (F9, revised 6 Nov 2026): six menus; the former Adventure, Export and
    # Modules menus moved to File ▸ Export and File ▸ Settings… (T-UI-18).
    assert menus == ["File", "Edit", "View", "Insert", "Format", "Help"]
    assert ui.js("!document.getElementById('welcome').classList.contains('hidden')") is True
    assert ui.window.windowTitle() == "Scriptorum"


def test_T_UI_03_new_adventure_dialog(ui):
    """T-UI-03: the New adventure dialog lists game systems and their themes."""
    ui.js("window.__scriptorum.newDialog()")
    ui.wait_until(lambda: ui.js("document.getElementById('new-dialog').open") is True)
    systems = ui.js("[...document.querySelectorAll('#new-system option')].map(o => o.textContent)")
    themes = ui.js("[...document.querySelectorAll('#new-theme option')].map(o => o.textContent)")
    # M5 (F8, decided 11 Nov 2026): the Plain game system and Plain theme are
    # offered first and preselected (T-MOD-13).
    assert systems == ["Plain", "Vaesen"] and themes == ["Plain", "Call of Cthulhu", "Legends and Lattes"]
    assert ui.js("document.getElementById('new-system').selectedOptions[0].textContent") == "Plain"
    assert ui.js("document.getElementById('new-theme').selectedOptions[0].textContent") == "Plain"
    # The author can still pick any other game system: the tests that follow
    # are written for Vaesen.
    ui.js("(() => { const s = document.getElementById('new-system'); s.value = '1'; s.onchange(); })()")
    themes = ui.js("[...document.querySelectorAll('#new-theme option')].map(o => o.textContent)")
    # M4 (F8): the game system's own theme first, then the general themes.
    assert themes == ["Vaesen", "Plain", "Call of Cthulhu", "Legends and Lattes"]
    ui.js("document.getElementById('new-create').click()")  # no title yet
    assert ui.js("document.getElementById('new-error').textContent") == "Please give the adventure a title."
    ui.type_input("#new-title", "Skuggan över Ödmården")
    ui.js("document.getElementById('new-create').click()")
    ui.wait_until(lambda: ui.state()["info"].get("hasDocument") is True)
    for part in ("toolbar", "workspace", "statusbar"):
        assert ui.js(f"!document.getElementById('{part}').classList.contains('hidden')") is True
    assert ui.window.windowTitle() == "Skuggan över Ödmården (unsaved) — Scriptorum"
    ui.wait_until(lambda: ui.state()["pages"] > 0, 20)


def test_T_UI_05_outline(ui):
    """T-UI-05: the outline lists the scenes of the chapter."""
    outline = ui.js("[...document.querySelectorAll('#outline .outline-item')].map(b => b.textContent)")
    # M4 (F7.9): a new adventure's text starts with its first scene.
    assert outline == ["1First scene"]
    ui.type_input(".el-scene .field-title input", "The mill")
    ui.run("window.__scriptorum.flush()")
    outline = ui.js("[...document.querySelectorAll('#outline .outline-item')].map(b => b.textContent)")
    assert outline[0] == "1The mill"


def test_T_SRC_06_visual_and_source_agree(ui):
    """T-SRC-06: an edit in Visual mode shows in Source mode, and back."""
    ui.js("document.querySelector('.el-scene .field-title input').focus()")
    ui.run("window.__scriptorum.insert('read-aloud')")
    ui.type_rich(".el-read-aloud .el-body", "The wheel has <b>stopped</b>. Price: 5 $.")
    ui.run("window.__scriptorum.insert('information')")
    ui.type_rich(".el-information .el-body", "She saw a <i>light</i>.")
    ui.run("window.__scriptorum.flush()")
    text = ui.state()["text"]
    assert '#scene(title: "The mill")[' in text
    assert "#read-aloud[The wheel has *stopped*. Price: 5 \\$.]" in text
    assert '#information(variant: "secret")[She saw a _light_.]' in text

    ui.run("window.__scriptorum.setMode('source')")
    assert ui.js("document.querySelector('.source-area').value") == text
    # Add a paragraph just before the scene's closing bracket.
    assert text.endswith("\n]\n")
    new_text = text[: -len("]\n")] + "\nA paragraph typed in Source mode.\n]\n"
    ui.type_input(".source-area", new_text)
    ui.run("window.__scriptorum.flush()")
    ui.run("window.__scriptorum.setMode('visual')")
    paragraphs = ui.js("[...document.querySelectorAll('.blk-paragraph .para')].map(p => p.textContent)")
    assert "A paragraph typed in Source mode." in paragraphs


def test_T_SRC_07_undo_redo(ui):
    """T-SRC-07: undo and redo restore each step exactly."""
    state = ui.state()
    history_text = state["text"]
    ui.run("window.__scriptorum.undo()")
    undone = ui.state()["text"]
    assert "A paragraph typed in Source mode." not in undone
    assert undone != history_text
    ui.run("window.__scriptorum.redo()")
    assert ui.state()["text"] == history_text


def test_T_BUILD_06_preview_follows_typing(ui):
    """T-BUILD-06: the preview updates about 0.3 s after typing stops."""
    before = ui.builds()
    ui.type_input(".el-scene .field-location input", "Ödmården, the old mill")
    ui.run("window.__scriptorum.flush()")
    requested = ui.window.bridge.last_request_time
    ui.wait_until(lambda: ui.builds() > before, 10)
    delay = ui.window.bridge.last_build_start - requested
    assert 0.25 <= delay < 1.0, delay
    assert ui.state()["errors"] == []


def test_T_BUILD_05_last_good_pages_kept(ui):
    """T-BUILD-05: after an error the last good pages stay visible."""
    good = ui.js("[...document.querySelectorAll('#pages img')].map(i => i.src)")
    assert good
    before = ui.builds()
    ui.run("window.__scriptorum.setMode('source')")
    ui.type_input(".source-area", ui.state()["text"] + "\n#let broken = \n")
    ui.run("window.__scriptorum.flush()")
    ui.wait_until(lambda: ui.builds() > before, 10)
    state = ui.state()
    assert state["errors"] and state["errors"][0]["line"] == state["text"].count("\n")
    assert ui.js("[...document.querySelectorAll('#pages img')].map(i => i.src)") == good
    assert ui.js("document.querySelector('.gutter .gl.error').textContent.trim()") == str(state["errors"][0]["line"])
    assert "1 error" in ui.js("document.getElementById('st-problems').textContent")
    ui.run("window.__scriptorum.undo()")
    ui.wait_until(lambda: ui.state()["errors"] == [], 10)


def test_T_UI_04_status_bar_and_export(ui):
    """T-UI-04: the status bar shows line, page N of M, words, errors and last export."""
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js("document.querySelector('.el-read-aloud .el-body').focus()")
    reply = json.loads(ui.window.bridge.exportTo(str(ui.folder / "export.pdf")))
    assert reply["ok"] and (ui.folder / "export.pdf").stat().st_size > 1000
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.state()["pages"] > 0, 10)  # the refreshed preview arrives ~0.3 s later
    ui.js("document.querySelector('.el-read-aloud .el-body').focus()")
    status = ui.state()["status"]
    line, page, words, problems, export = status
    assert line.startswith("Line ")
    assert page.startswith("Page 1 of ")
    assert words.endswith(" words")
    assert problems == "No errors"
    assert export.startswith("Last export ") and export.endswith("export.pdf")


def test_T_FILE_01_save_and_reopen_through_window(ui):
    """T-FILE-01 through the window: save, reopen, same text."""
    text = ui.state()["text"]
    reply = json.loads(ui.window.bridge.saveTo(str(ui.folder / "skuggan.scav")))
    assert reply["ok"]
    assert ui.window.windowTitle() == "Skuggan över Ödmården — Scriptorum"
    reply = json.loads(ui.window.bridge.openPath(str(ui.folder / "skuggan.scav")))
    assert reply["ok"]
    ui.run("window.__scriptorum.refresh()")
    assert ui.state()["text"] == text


def test_T_UI_08_no_network_requests(ui):
    """T-UI-08 (automated part of T-REL-02): the interface made no network requests."""
    assert ui.window.interceptor.blocked == []
    # A deliberate attempt is stopped: by the WebEngine setting or the interceptor.
    ui.js("window.__fetch = 'pending'; fetch('https://example.com/').then(() => window.__fetch = 'reached', () => window.__fetch = 'blocked'); null")
    ui.wait_until(lambda: ui.js("window.__fetch") != "pending", 10)
    assert ui.js("window.__fetch") == "blocked"
    ui.js("const i = new Image(); i.onload = () => window.__img = 'reached'; i.onerror = () => window.__img = 'blocked'; i.src = 'https://example.com/x.png'; null")
    ui.wait_until(lambda: ui.js("window.__img") is not None, 10)
    assert ui.js("window.__img") == "blocked"
