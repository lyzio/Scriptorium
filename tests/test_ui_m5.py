"""Test Plan UI smoke tests for Milestone 5 part A: the start-up window
(F9), the preview zoom (F7.2) and the palette editor's Save next to Done
(F16). T-UI-26, T-UI-27 and T-UI-28.

The tests run in file order and share one window.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.conftest import pack_sample
from tests.test_ui_smoke import Driver

pytestmark = pytest.mark.ui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")


@pytest.fixture(scope="module")
def ui(library, tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session
    from scriptorum.core.startup import CheckResult

    folder = tmp_path_factory.mktemp("ui-m5")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    missing = [CheckResult("dictionaries", False, "startup.reason.noSpylls")]
    window = MainWindow(session, headless_test=True, startup_results=missing)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


# --- T-UI-26 the start-up window ------------------------------------------------------------

def _startup_window(monkeypatch=None):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.startup_window import StartupWindow
    from scriptorum.core.startup import Startup, bundled_strings

    QApplication.instance() or QApplication([])
    startup = Startup()
    window = StartupWindow(startup, bundled_strings(), "0.5.1")
    answers = []
    window.done.connect(answers.append)
    return startup, window, answers


def test_T_UI_26_startup_window_closes_by_itself(library):
    """T-UI-26: with every check passing, the window ticks each line and
    closes by itself, asking for the main window to open."""
    from scriptorum.app.startup_window import TICK

    startup, window, answers = _startup_window()
    window.show()
    window.run_now()
    assert answers == [True]
    assert window.bar.value() == 5
    assert all(mark.text() == TICK for mark in window.marks.values())
    assert window.lines["typst"].text() == "Typst can build a page"


def test_T_UI_26_startup_window_continue_anyway(library, tmp_path, monkeypatch):
    """T-UI-26 (accepted when): with a dictionary missing, the start-up window
    marks that line and stays open; Copy details copies the results; Continue
    anyway opens the app."""
    from PySide6.QtGui import QGuiApplication

    from scriptorum.app.startup_window import CROSS

    monkeypatch.setenv("SCRIPTORUM_DICTIONARIES", str(tmp_path / "none"))
    startup, window, answers = _startup_window()
    window.show()
    window.run_now()
    assert answers == []  # it stays open
    assert window.marks["dictionaries"].text() == CROSS
    assert window.lines["dictionaries"].text() == "Spelling dictionaries loaded: no dictionary was found"
    assert window.continue_button.isVisible() and window.continue_button.isEnabled()
    window.copy_button.click()
    assert "[FAILED]  Spelling dictionaries loaded" in QGuiApplication.clipboard().text()
    window.continue_button.click()
    assert answers == [True]


def test_T_UI_26_quiet_bar_names_what_is_missing(ui):
    """T-UI-26: after Continue anyway a quiet bar in the main window names
    what is missing."""
    ui.wait_until(lambda: ui.js("!document.getElementById('startup-bar').classList.contains('hidden')") is True)
    text = ui.js("document.getElementById('startup-bar-text').textContent")
    assert text == "Scriptorum started without a part: Spelling dictionaries loaded: the spylls library is not installed"


def test_T_UI_26_check_installation(ui):
    """T-UI-26: Help ▸ Check installation shows the same list on demand,
    with no network request, and can run the theme self-test."""
    labels = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.help" for i in m["items"]]
    assert "Check installation…" in labels
    ui.run("window.__scriptorum.openCheckDialog()", 30)
    lines = ui.js("[...document.querySelectorAll('#check-list li')].map(l => l.className + ':' + l.textContent)")
    assert len(lines) == 5 and all(l.startswith("passed:") for l in lines), lines
    assert ui.js("document.getElementById('check-summary').textContent") == "Every check passed."
    # Every part is back, so the quiet bar goes.
    assert ui.js("document.getElementById('startup-bar').classList.contains('hidden')") is True
    ui.js("document.getElementById('check-selftest').click(); true")
    ui.wait_until(lambda: ui.js("Number(document.body.dataset.selfTestDone || 0)") >= 1, 120)
    assert ui.js("document.getElementById('check-summary').textContent") == "Theme self-test: every theme builds the test adventure."
    assert ui.js("document.querySelectorAll('#check-themes li.passed').length") == 7
    assert ui.window.interceptor.blocked == []
    ui.js("document.getElementById('check-close').click(); true")


# --- T-UI-27 zoom in the live preview -------------------------------------------------------

def _open(ui, name):
    path = pack_sample(name, ui.folder)
    reply = json.loads(ui.window.bridge.openPath(str(path)))
    assert reply.get("ok", True), reply
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.state()["pages"] > 0, 30)
    ui.wait_until(lambda: ui.js("window.__scriptorum.zoom.get().percent") is not None, 15)
    return path


def _page_width(ui) -> float:
    return ui.js("document.querySelector('#pages img.page').getBoundingClientRect().width")


def test_T_UI_27_zoom_bar(ui):
    """T-UI-27: the zoom bar has − and +, the size, Fit width and Whole page;
    the pages are SVG, so they stay sharp; − and + step the size."""
    _open(ui, "m5-plain")
    texts = ui.js("[...document.querySelectorAll('#zoom-bar button')].map(b => b.textContent.trim() || b.title)")
    # M5 part B adds Two pages and Own window (F7.2).
    assert texts == ["Zoom out", "Zoom in", "Fit width", "Whole page", "Two pages", "Own window"]
    assert ui.js("document.querySelector('#pages img.page').src").endswith(".svg")
    assert ui.js("window.__scriptorum.zoom.get().zoom") == "fit-width"
    pane = ui.js("document.getElementById('preview-pane').clientWidth")
    assert abs(_page_width(ui) - (pane - 36)) < 2
    ui.js("window.__scriptorum.zoom.set(100); true")
    assert ui.js("document.getElementById('zoom-value').textContent") == "100 %"
    assert abs(_page_width(ui) - ui.js("document.querySelector('#pages img.page').naturalWidth")) < 2
    ui.js("document.getElementById('zoom-in').click(); true")
    assert ui.js("document.getElementById('zoom-value').textContent") == "110 %"
    ui.js("document.getElementById('zoom-out').click(); document.getElementById('zoom-out').click(); true")
    assert ui.js("document.getElementById('zoom-value').textContent") == "90 %"
    ui.js("window.__scriptorum.zoom.set(10); true")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 50
    assert ui.js("document.getElementById('zoom-out').disabled") is True
    ui.js("window.__scriptorum.zoom.set(900); true")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 400
    ui.js("document.getElementById('zoom-whole-page').click(); true")
    height = ui.js("document.querySelector('#pages img.page').getBoundingClientRect().height")
    assert height <= ui.js("document.getElementById('preview-pane').clientHeight")
    assert ui.js("document.getElementById('zoom-whole-page').getAttribute('aria-pressed')") == "true"


def test_T_UI_27_keys_and_wheel(ui):
    """T-UI-27: Ctrl + plus, Ctrl + minus and Ctrl + 0 work while the preview
    has focus; Ctrl and the scroll wheel zoom around the pointer."""
    ui.js("window.__scriptorum.zoom.set(100); document.getElementById('preview-pane').focus(); true")
    key = "document.getElementById('preview-pane').dispatchEvent(new KeyboardEvent('keydown', {key: '%s', ctrlKey: true, bubbles: true})); true"
    ui.js(key % "+")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 110
    ui.js(key % "-")
    ui.js(key % "-")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 90
    ui.js(key % "0")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 100
    # The point under the pointer stays where it is.
    before = ui.js("""(() => { const r = document.querySelector('#pages img.page').getBoundingClientRect();
        const x = r.left + r.width * 0.25, y = r.top + 200;
        window.__pt = {x, y, fx: (x - r.left) / r.width};
        document.getElementById('preview-pane').dispatchEvent(new WheelEvent('wheel', {deltaY: -100, ctrlKey: true, clientX: x, clientY: y, bubbles: true, cancelable: true}));
        return window.__pt; })()""")
    assert ui.js("window.__scriptorum.zoom.get().percent") == 110
    after = ui.js("(() => { const r = document.querySelector('#pages img.page').getBoundingClientRect(); return (window.__pt.x - r.left) / r.width; })()")
    assert abs(after - before["fx"]) < 0.02


def test_T_UI_27_zoom_holds_and_is_remembered(ui):
    """T-UI-27: the zoom holds while the author types and the preview
    refreshes, and the adventure opens at the same size next time; the
    .scav file is unchanged by it."""
    path = ui.folder / "zoomed.scav"
    reply = json.loads(ui.window.bridge.saveTo(str(path)))
    assert reply["ok"], reply
    before = path.read_bytes()
    ui.js("window.__scriptorum.zoom.set(150); true")
    builds = ui.builds()
    ui.type_input(".el-scene .field-title input", "Fog over the old quay")
    ui.run("window.__scriptorum.flush()")
    ui.wait_until(lambda: ui.builds() > builds, 30)
    assert ui.js("window.__scriptorum.zoom.get().percent") == 150
    # The refreshed page picture loads a moment after the build (0.5.4).
    ui.wait_until(lambda: ui.js("document.querySelector('#pages img.page')?.naturalWidth || 0") > 0, 15)
    assert abs(_page_width(ui) - 1.5 * ui.js("document.querySelector('#pages img.page').naturalWidth")) < 2
    # The zoom is written a moment after it changes.
    def stored():
        file = ui.window.bridge.view_state.file
        return file.is_file() and 150 in json.loads(file.read_text("utf-8"))["zoom"].values()
    ui.wait_until(stored, 15)
    assert path.read_bytes() == before  # never in the .scav file
    # Another adventure keeps its own zoom; opening this one again brings 150 % back.
    _open(ui, "m1-basic")
    assert ui.js("window.__scriptorum.zoom.get().zoom") == "fit-width"
    json.loads(ui.window.bridge.openPath(str(path)))
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.js("window.__scriptorum.zoom.get().zoom") == 150, 15)


# --- T-UI-28 the palette editor's Save next to Done -----------------------------------------

def _visible(ui, element_id: str) -> bool:
    return ui.js(f"""(() => {{ const e = document.getElementById('{element_id}'); const r = e.getBoundingClientRect();
        return !e.classList.contains('hidden') && r.width > 0 && r.bottom <= window.innerHeight && r.top >= 0; }})()""")


def test_T_UI_28_save_next_to_done(ui):
    """T-UI-28: while a new palette is edited its Save and Cancel sit at the
    foot of the Settings window, next to Done, in view however long the list
    of colours is; they are hidden otherwise."""
    ui.run("window.__scriptorum.openSettingsWindow('colours')")
    assert ui.js("document.getElementById('palette-save').classList.contains('hidden')") is True
    ui.js("document.getElementById('app-newPalette').click(); true")
    ui.wait_until(lambda: ui.js("!!document.getElementById('palette-editor')") is True)
    foot = ui.js("[...document.querySelectorAll('.settings-foot button:not(.hidden)')].map(b => b.id)")
    assert foot == ["palette-cancel", "palette-save", "settings-close"]
    for element in ("palette-save", "palette-cancel", "settings-close"):
        assert _visible(ui, element), element
    # Scrolled to the top of the long list, the buttons are still in view.
    ui.js("document.querySelector('.settings-pages').scrollTop = 0; true")
    assert _visible(ui, "palette-save")
    assert ui.js("document.querySelectorAll('#palette-editor button').length") == 0
    ui.js("document.getElementById('palette-cancel').click(); true")
    assert ui.js("document.getElementById('palette-save').classList.contains('hidden')") is True
    ui.run("window.__scriptorum.closeSettings()")


def test_T_UI_28_close_asks_to_save(ui):
    """T-UI-28: closing Settings with unsaved colours asks whether to save
    them: Keep editing leaves the window open, Save saves and closes."""
    ui.run("window.__scriptorum.openSettingsWindow('colours')")
    ui.js("document.getElementById('app-newPalette').click(); true")
    ui.wait_until(lambda: ui.js("!!document.getElementById('palette-editor')") is True)
    ui.type_input("#palette-name", "Skymning")
    ui.js("""(() => { const i = document.querySelector('#palette-editor input[data-token=window][data-mode=light]');
        i.value = '#e8dcc8'; i.dispatchEvent(new Event('input')); })()""")
    ui.js("document.getElementById('settings-close').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True)
    assert ui.js("document.getElementById('ask-text').textContent") == "The new palette has colours that are not saved. Save them?"
    assert [ui.js(f"document.getElementById('ask-{b}').textContent") for b in ("yes", "no", "cancel")] == ["Save palette", "Don't save", "Keep editing"]
    ui.js("document.getElementById('ask-cancel').click(); true")
    ui.wait(200)
    assert ui.js("!document.getElementById('settings').classList.contains('hidden')") is True
    ui.js("document.getElementById('settings-close').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True)
    ui.js("document.getElementById('ask-yes').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('settings').classList.contains('hidden')") is True, 10)
    assert ui.window.bridge.session.app_settings.get("palette") == "my.skymning"
    assert ui.window.bridge.session.library.newest("my.skymning").palette()["light"]["window"] == "#E8DCC8"
    json.loads(ui.window.bridge.resetPalette())


def test_T_UI_28_failed_save_shows_reason(ui, monkeypatch):
    """T-UI-28: a save that fails shows its reason at the foot of the window,
    and the colours stay to be saved again."""
    from scriptorum.core import appsettings

    def full_disk(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(appsettings, "save_palette", full_disk)
    ui.run("window.__scriptorum.openSettingsWindow('colours')")
    ui.js("document.getElementById('app-newPalette').click(); true")
    ui.wait_until(lambda: ui.js("!!document.getElementById('palette-editor')") is True)
    ui.js("document.getElementById('palette-save').click(); true")
    ui.wait_until(lambda: (ui.js("document.getElementById('settings-foot-note').textContent") or "").startswith("The palette was not saved:"), 10)
    assert "No space left on device" in ui.js("document.getElementById('settings-foot-note').textContent")
    assert ui.js("!!document.getElementById('palette-editor')") is True
    assert ui.js("document.getElementById('settings-foot-note').classList.contains('quiet')") is False
    ui.js("document.getElementById('palette-cancel').click(); true")
    ui.run("window.__scriptorum.closeSettings()")
    assert ui.js("document.getElementById('settings').classList.contains('hidden')") is True


# --- M5 part B in the window: T-UI-29 and T-BUILD-19, 20, 23 (window parts) -------------------

def test_T_BUILD_19_settings_page_print_values(ui):
    """T-BUILD-19 (window part): margins, Classical proportions, header,
    footer, page numbers, page starts and the printing values are on the
    settings page and change the preview at once."""
    _open(ui, "m5-print")
    ui.run("window.__scriptorum.openSettingsWindow('adventure')")
    margins = [ui.js(f"document.getElementById('set-margin-{k}').value") for k in ("top", "bottom", "inside", "outside")]
    assert margins == ["18", "22", "16", "20"]
    assert ui.js("document.getElementById('origin-margin_mm').textContent") == "Set for this adventure"
    assert ui.js("document.getElementById('set-pageHeader').value") == "The Lighthouse Keeper's Log"
    rows = ui.js("[...document.querySelectorAll('#set-pageStart span')].map(s => s.textContent)")
    assert "Scene" in rows and "Box" in rows
    assert ui.js("document.querySelector('#set-pageStart select[data-kind=box]').value") == "always"
    assert ui.js("document.getElementById('set-bookletOrder').value") == "fold"
    assert ui.js("document.getElementById('set-bleed').value") == "3"
    builds = ui.builds()
    ui.js("document.getElementById('set-classical').click(); true")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.settings["page"]["margin_mm"]["outside"] == 35.0, 10)
    ui.wait_until(lambda: ui.builds() > builds, 30)
    ui.js("(() => { const c = document.getElementById('set-compact'); c.checked = true; c.dispatchEvent(new Event('change')); })()")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.settings.get("compact") is True, 10)
    assert ui.js("document.querySelector('#set-pageStart select').disabled") is True
    ui.run("window.__scriptorum.closeSettings()")


def test_T_UI_29_show_breaks_and_warnings_panel(ui):
    """T-UI-29: View ▸ Show breaks marks breaks in the preview; the status bar
    counts the warnings and opens the warnings panel; an export adds its
    preflight warnings there."""
    view = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.view" for i in m["items"]]
    assert "Show breaks" in view and "Two-page spread" in view and "Preview in its own window" in view
    assert ui.window.bridge.show_breaks is False
    json.loads(ui.window.bridge.setShowBreaks(True))
    assert ui.window.bridge.show_breaks is True
    json.loads(ui.window.bridge.setShowBreaks(False))
    reply = json.loads(ui.window.bridge.exportVariantTo(str(ui.folder / "print.pdf"), "print-shop"))
    assert reply["ok"] and reply["variant"] == "print-shop"
    ui.js(f"window.__scriptorum.afterExport({json.dumps(reply)}); true")
    ui.wait_until(lambda: ui.js("!document.getElementById('warnings-panel').classList.contains('hidden')") is True)
    items = ui.js("[...document.querySelectorAll('#warnings-list li')].map(l => l.textContent)")
    assert any("sketch-small.png prints at only" in i for i in items)
    assert "warning" in ui.js("document.getElementById('st-problems').textContent")
    ui.js("document.getElementById('warnings-close').click(); true")
    ui.js("document.getElementById('st-problems').click(); true")
    assert ui.js("!document.getElementById('warnings-panel').classList.contains('hidden')") is True
    ui.js("document.getElementById('warnings-close').click(); true")
    export = [m for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.file"][0]
    children = [i for i in export["items"] if i["label"] == "Export"][0]["children"]
    # M5 part C adds the accessible PDF (F17.5).
    assert children[2:4] == ["Booklet PDF (two pages per sheet)…", "Print-shop PDF (bleed, crop marks, PDF/A)…"]


def test_T_UI_29_two_page_spread(ui):
    """T-UI-29: the two-page spread shows page 1 alone on the right, then two
    pages side by side; Fit width fits both."""
    ui.js("document.getElementById('zoom-spread').click(); true")
    assert ui.js("window.__scriptorum.zoom.get().spread") is True
    pos = ui.js("[...document.querySelectorAll('#pages img.page')].slice(0, 3).map(i => { const r = i.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top)]; })")
    assert pos[1][1] == pos[2][1] and pos[1][0] < pos[2][0]   # pages 2 and 3 side by side
    assert pos[0][0] == pos[2][0]                             # page 1 on the right
    ui.js("document.getElementById('zoom-fit-width').click(); true")
    width = ui.js("document.getElementById('pages').getBoundingClientRect().width")
    assert width <= ui.js("document.getElementById('preview-pane').clientWidth")
    ui.js("document.getElementById('zoom-spread').click(); true")
    assert ui.js("window.__scriptorum.zoom.get().spread") is False


def test_T_UI_29_preview_window(ui):
    """T-UI-29: the preview opens in a window of its own with the same zoom
    bar; it follows the next build; nothing reaches the network."""
    from tests.test_ui_smoke import Driver

    json.loads(ui.window.bridge.openPreviewWindow())
    preview = ui.window.preview_window
    assert preview is not None and preview.isVisible()

    class Second(Driver):
        def js(self, code):
            original = self.window.page
            return super().js(code)

    second = Second(ui.app, preview)
    second.wait_until(lambda: second.js("!!(window.__preview && window.__preview.ready)") is True, 30)
    second.wait_until(lambda: second.js("document.querySelectorAll('#pages img.page').length") > 0, 30)
    buttons = second.js("[...document.querySelectorAll('#zoom-bar button')].map(b => b.id)")
    assert buttons == ["zoom-out", "zoom-in", "zoom-fit-width", "zoom-whole-page", "zoom-spread"]
    assert "Preview" in preview.view.title()
    count = second.js("Number(document.body.dataset.buildCount || 0)")
    ui.type_input(".el-scene .field-title input", "Arrival at the old lighthouse")
    ui.run("window.__scriptorum.flush()")
    second.wait_until(lambda: second.js("Number(document.body.dataset.buildCount || 0)") > count, 30)
    assert ui.window.interceptor.blocked == []
    json.loads(ui.window.bridge.openPreviewWindow())  # a second call shows the same window
    assert ui.window.preview_window is preview
    preview.close()


# --- M5 part C in the window: T-BUILD-25 to 27 (window parts) -----------------------------------

def test_T_BUILD_25_27_accessible_in_the_window(ui):
    """T-BUILD-25 to 27 (window parts): the document language on the settings
    page; a description field under each image, written into the text; the
    map editor's description; File ▸ Export ▸ Accessible PDF (PDF/UA)."""
    _open(ui, "m5-access")
    ui.run("window.__scriptorum.openSettingsWindow('adventure')")
    assert ui.js("document.getElementById('set-language').value") == "sv"
    assert ui.js("[...document.getElementById('set-language').options].map(o => o.textContent)")[:2] == ["English", "Swedish"]
    ui.run("window.__scriptorum.closeSettings()")
    values = ui.js("[...document.querySelectorAll('.img-description input')].map(i => i.value)")
    assert len(values) == 2 and values[0].startswith("En skiss av fyren")
    ui.js("""(() => { const i = document.querySelectorAll('.img-description input')[1]; i.focus();
        i.value = 'Loggboken på bordet.'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""")
    ui.run("window.__scriptorum.flush()")
    ui.wait_until(lambda: 'alt: "Loggboken på bordet."' in (ui.state()["text"] or ""), 10)
    export = [m for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.file"][0]
    children = [i for i in export["items"] if i["label"] == "Export"][0]["children"]
    assert children[-1] == "Accessible PDF (PDF/UA)…"
    reply = json.loads(ui.window.bridge.exportVariantTo(str(ui.folder / "ua.pdf"), "accessible"))
    assert reply["ok"] and reply["variant"] == "accessible", reply
    assert b"<pdfuaid:part>1</pdfuaid:part>" in (ui.folder / "ua.pdf").read_bytes()
    # The map editor has the description.
    ui.run("window.__scriptorum.world.openMap('m-skarvik')", 15)
    ui.wait_until(lambda: ui.js("!!document.querySelector('.map-description')") is True, 10)
    assert ui.js("document.querySelector('.map-description').value").startswith("Karta över Skärvik")
