"""UI smoke tests for the M2-0.2.2 fixes: menus after use (T-UI-01), hiding
the live preview (T-UI-14), folding acts and scenes (T-UI-15), the countdown
step's text width (T-UI-16) and the hover strip of the block controls
(T-SRC-14)."""

from __future__ import annotations

import json
import os

import pytest

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
    from tests.conftest import pack_sample

    folder = tmp_path_factory.mktemp("ui-fixes")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    path = pack_sample("m2-full", folder)
    assert json.loads(window.bridge.openPath(str(path)))["ok"]
    driver.run("window.__scriptorum.refresh()")
    driver.wait_until(lambda: driver.state()["pages"] > 0, 20)
    yield driver
    window.close()


def _click(ui, selector: str) -> None:
    """A real press and click, as a mouse gives them."""
    ui.js(
        f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
        " el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));"
        " el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));"
        " el.click(); return true; })()"
    )


def _popup_open(ui) -> bool:
    return ui.js("!document.getElementById('menu-popup').classList.contains('hidden')") is True


def test_T_UI_01_menus_keep_working_after_use(ui):
    """T-UI-01: every menu opens, also after an item of another menu was used."""
    for round_ in range(2):
        for index in range(9):
            _click(ui, f"#menubar .menu-btn:nth-child({index + 1})")
            assert _popup_open(ui), (round_, index)
            assert ui.js("document.querySelectorAll('#menu-popup .menu-item').length") > 0
        # Use an item (View → Visual mode), then the menus must still open.
        _click(ui, "#menubar .menu-btn:nth-child(3)")
        ui.js("[...document.querySelectorAll('#menu-popup .menu-item')][0].click()")
        assert not _popup_open(ui)
    # Clicking the same menu again closes it; a press outside closes it too.
    _click(ui, "#menubar .menu-btn:nth-child(1)")
    _click(ui, "#menubar .menu-btn:nth-child(1)")
    assert not _popup_open(ui)
    _click(ui, "#menubar .menu-btn:nth-child(1)")
    _click(ui, "#editor-pane")
    assert not _popup_open(ui)


def test_T_UI_14_hide_the_live_preview(ui):
    """T-UI-14: the live preview can be hidden and shown again; the editor takes the width."""
    width = ui.js("document.getElementById('editor-pane').getBoundingClientRect().width")
    _click(ui, "#tb-preview")
    assert ui.js("document.getElementById('preview-pane').offsetParent === null") is True
    assert ui.js("document.getElementById('tb-preview').getAttribute('aria-pressed')") == "false"
    wider = ui.js("document.getElementById('editor-pane').getBoundingClientRect().width")
    assert wider > width * 1.5
    _click(ui, "#menubar .menu-btn:nth-child(3)")
    assert "Show live preview" in ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].map(b => b.textContent)")
    ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].find(b => b.textContent === 'Show live preview').click()")
    assert ui.js("document.getElementById('preview-pane').offsetParent !== null") is True


def test_T_UI_15_fold_acts_and_scenes(ui):
    """T-UI-15: an act or a scene folds away in the editor and the outline; the text does not change."""
    before = ui.state()["text"]
    visible = "[...document.querySelectorAll('#visual > .blk-list > .blk')].filter(b => b.offsetParent !== null).length"
    shown = ui.js(visible)
    _click(ui, "#outline li .fold")  # the first act
    assert ui.js(visible) == 1  # only the act heading is left
    assert ui.js("[...document.querySelectorAll('#outline li')].filter(l => l.querySelector('.scene') && l.offsetParent !== null).length") == 0
    _click(ui, "#outline li .fold")
    assert ui.js(visible) == shown
    # Fold one scene in the editor: its fields and content hide, its title stays.
    _click(ui, "#visual > .blk-list > .blk[data-collapse-key='s:1'] > .fold")
    scene = "#visual > .blk-list > .blk[data-collapse-key='s:1']"
    assert ui.js(f"document.querySelector({json.dumps(scene + ' .el-children')}).offsetParent === null") is True
    assert ui.js(f"document.querySelector({json.dumps(scene + ' .field-title input')}).offsetParent !== null") is True
    _click(ui, scene + " > .fold")
    ui.run("window.__scriptorum.flush()")
    assert ui.state()["text"] == before


def test_T_UI_16_countdown_step_text_has_room(ui):
    """T-UI-16: a countdown step's text box gets the width of the row, even with a narrow editor."""
    ui.window.resize(1000, 800)
    ui.wait(300)
    body = ui.js("document.querySelector('.el-countdown-step .el-body').getBoundingClientRect().width")
    row = ui.js("document.querySelector('.el-countdown-step').getBoundingClientRect().width")
    assert body > row * 0.6
    ui.window.resize(1440, 900)


def test_T_SRC_14_controls_stay_while_the_mouse_moves_to_them(ui):
    """T-SRC-14: the block's hover area reaches its controls, so they do not vanish on the way."""
    reach = ui.js(
        "(() => { const b = document.querySelector('#visual .blk-paragraph');"
        " const before = getComputedStyle(b, '::before');"
        " const c = b.querySelector(':scope > .blk-controls');"
        " return [parseFloat(before.left), parseFloat(before.width), parseFloat(getComputedStyle(c).left)]; })()"
    )
    strip_left, strip_width, controls_left = reach
    assert strip_left <= controls_left and strip_left + strip_width >= 0
