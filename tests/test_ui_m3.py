"""Test Plan UI smoke tests for Milestone 3: the real window, headless.

The tests run in file order and share one window, like one person working
through the Milestone 3 functions with the sample m3-world: the Codex,
Handouts and "In this scene" panels, an entry and where it is used, the map
editor, the relationship chart, Handouts only, undo of a codex change, and
an M2 adventure whose text is turned into codex links.
"""

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

    folder = tmp_path_factory.mktemp("ui-m3")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    path = pack_sample("m3-world", folder)
    assert json.loads(window.bridge.openPath(str(path)))["ok"]
    driver.run("window.__scriptorum.refresh()")
    driver.wait_until(lambda: driver.state()["pages"] > 0 and driver.state()["elements"], 30)
    yield driver
    window.close()


def session(ui):
    return ui.window.bridge.session


def texts(ui, selector: str) -> list:
    return ui.js(f"[...document.querySelectorAll({json.dumps(selector)})].map(e => e.textContent.trim())")


def test_T_WORLD_18_sidebars(ui):
    """T-WORLD-18: the Codex and Handouts tabs and the "In this scene" panel
    (F9.3); Handouts only shows exactly what the players receive (F6.4)."""
    ui.run("window.__scriptorum.showNavTab('codex')")
    groups = texts(ui, "#codex-panel .codex-group-title")
    assert groups == ["Clue (1)", "Person (2)", "Place (2)", "Creature (1)", "Maps (1)"]
    assert "Lovisa Berg" in texts(ui, "#codex-panel .codex-item")
    ui.type_input("#codex-panel .codex-search", "chap")
    assert texts(ui, "#codex-panel .codex-item") == ["The chapel"]
    ui.type_input("#codex-panel .codex-search", "")
    ui.run("window.__scriptorum.showNavTab('handouts')")
    assert texts(ui, "#handouts-panel .handout-item") == ["#1Skärvik and the bayMap", "#2Lovisa's warning", "#3The sexton's note"]
    # "In this scene": put the cursor in the first scene.
    ui.js("document.querySelectorAll('#visual .rich')[3].focus()")
    ui.wait_until(lambda: texts(ui, "#scene-panel-list .codex-item") != [], 5)
    assert ui.js("document.getElementById('scene-panel-scene').textContent") == "The harbour"
    assert texts(ui, "#scene-panel-list .codex-item") == [
        "PlaceSkärvik harbour", "PersonLovisa Berg", "PersonNils Ek", "ClueThe bell of the Hoppet"]
    # Handouts only.
    builds = ui.builds()
    ui.run("window.__scriptorum.setHandoutsOnly(true)")
    ui.wait_until(lambda: ui.builds() > builds and ui.state()["pages"] == 5, 20)
    assert ui.window.bridge.player_preview is True
    assert ui.js("document.getElementById('tb-handouts').getAttribute('aria-pressed')") == "true"
    builds = ui.builds()
    ui.run("window.__scriptorum.setHandoutsOnly(false)")
    ui.wait_until(lambda: ui.builds() > builds and ui.state()["elements"], 20)
    assert ui.state()["pages"] == 5 and ui.window.bridge.player_preview is False


def test_T_WORLD_08_entry_view(ui):
    """T-WORLD-08: an entry shows where it is used: scenes, printed pages and
    backlinks (F3.6)."""
    ui.run("window.__scriptorum.world.openEntry('c-nils-ek')")
    body = ui.js("document.getElementById('worldview-body').textContent")
    assert "In the scenes: The harbour, The chapel" in body
    assert "Printed on pages: 2, 3" in body
    assert "Linked from: Lovisa Berg" in body
    assert ui.js("document.getElementById('worldview-title').textContent") == "Nils Ek"
    assert ui.js("getComputedStyle(document.getElementById('visual')).display") == "none"


def test_T_WORLD_20_undo_codex_change(ui):
    """T-WORLD-20: a change to an entry is one undo step from Edit → Undo."""
    ui.type_input("#worldview-body .field-mood .field-input", "Brave")
    ui.wait_until(lambda: session(ui).world.entry("c-nils-ek")["fields"]["mood"] == "Brave", 5)
    ui.wait_until(lambda: ui.js("window.__scriptorum.worldMarks()") >= 1, 5)
    ui.run("window.__scriptorum.undo()")
    assert session(ui).world.entry("c-nils-ek")["fields"]["mood"] == "Frightened"
    ui.wait_until(lambda: ui.js("document.querySelector('#worldview-body .field-mood .field-input').value") == "Frightened", 5)


def _click_map(ui, x: float, y: float):
    ui.js(f"""(() => {{ const svg = document.querySelector('.map-overlay'); const r = svg.getBoundingClientRect();
      svg.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, clientX: r.left + r.width * {x}, clientY: r.top + r.height * {y}}}));
      svg.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true}})); return true; }})()""")


def test_T_WORLD_21_map_editor(ui):
    """T-WORLD-21: place a pin; draw an area, which stops at 15 corners and
    closes on its first corner; a layer's Show in handout setting is saved
    (F5.1, F5.2, F5.8)."""
    ui.run("window.__scriptorum.world.openMap('m-skarvik')")
    items = lambda: [len(layer["items"]) for layer in session(ui).world.maps()["m-skarvik"]["layers"]]
    assert items() == [3, 2]
    ui.run("window.__scriptorum.world.setTool('pin')")
    _click_map(ui, 0.4, 0.4)
    ui.wait_until(lambda: items() == [4, 2], 5)
    ui.run("window.__scriptorum.world.setTool('area')")
    for i in range(16):
        _click_map(ui, 0.1 + i * 0.02, 0.2 + (i % 2) * 0.1)
    assert len(ui.js("window.__scriptorum.world.mapState().drawing")) == 15
    assert "at most 15 corners" in ui.js("document.querySelector('.map-hint').textContent")
    _click_map(ui, 0.1, 0.2)  # the first corner closes the area
    ui.wait_until(lambda: items() == [5, 2], 5)
    area = session(ui).world.maps()["m-skarvik"]["layers"][0]["items"][-1]
    assert area["type"] == "area" and len(area["points"]) == 15
    ui.js("document.querySelectorAll('.map-layer-row input[type=checkbox]')[1].click()")
    ui.wait_until(lambda: session(ui).world.maps()["m-skarvik"]["layers"][1]["show_in_handout"] is True, 5)
    # Browse: a click on a pin opens its codex entry (F5.3).
    ui.run("window.__scriptorum.world.setTool('browse')")
    ui.js("document.querySelector('.map-overlay .item-pin').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}))")
    ui.wait_until(lambda: (ui.js("window.__scriptorum.world.viewOpen()") or {}).get("kind") == "entry", 5)


def test_T_WORLD_10_chart_in_the_window(ui):
    """T-WORLD-10 (window): dragging an entry in the chart saves its place."""
    ui.run("window.__scriptorum.world.openChart()")
    ui.wait_until(lambda: len(ui.js("window.__scriptorum.world.chartPositions()")) == 4, 10)
    assert ui.js("window.__scriptorum.world.moveChartNode('c-the-chapel', 400, 240)")
    ui.wait_until(lambda: next(n for n in session(ui).chart()["nodes"] if n["id"] == "c-the-chapel")["x"] == 0.5, 5)
    ui.run("window.__scriptorum.world.closeView()")


def test_T_WORLD_09_entries_from_text(ui):
    """T-WORLD-09: a loose person card becomes a codex entry and a card; a
    codex entry from selected text replaces it with a mention (F3.7)."""
    from tests.conftest import pack_sample

    path = pack_sample("m2-full", ui.folder)
    assert json.loads(ui.window.bridge.openPath(str(path)))["ok"]
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.state()["text"] and "Lovisa" in ui.state()["text"], 20)
    # The M2 adventure offers its text-to-codex links in a banner (F3.12).
    assert ui.js("!document.getElementById('upgrade-banner').classList.contains('hidden')")
    ui.run("window.__scriptorum.personToEntry([2, 3])")
    ui.run("window.__scriptorum.flush()")
    text = ui.state()["text"]
    assert '#card(entry: "c-lovisa-berg")[' in text and "#person(" not in text
    assert session(ui).world.entry("c-lovisa-berg")["fields"]["mood"] == "Tired and stubborn"
    # Select "Åsa" in the first paragraph and make it an entry.
    ui.js("""(() => { const box = [...document.querySelectorAll('#visual .rich')].find(b => b.textContent.includes('Åsa')); box.focus();
      const node = [...box.childNodes].find(n => n.nodeType === 3 && n.textContent.includes('Åsa'));
      const start = node.textContent.indexOf('Åsa'); const r = document.createRange();
      r.setStart(node, start); r.setEnd(node, start + 3); getSelection().removeAllRanges(); getSelection().addRange(r);
      box.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 300, clientY: 220})); return true; })()""")
    labels = ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].map(b => b.textContent)")
    assert "Make a codex entry of the selected text" in labels
    ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].find(b => b.textContent.startsWith('Make a codex entry')).click()")
    ui.wait_until(lambda: ui.js("document.getElementById('prompt-dialog').open"), 5)
    assert ui.js("document.getElementById('prompt-input').value") == "Åsa"
    ui.js("document.getElementById('prompt-choice').value = 'person'; document.getElementById('prompt-ok').click()")
    ui.wait_until(lambda: "c-asa" in session(ui).world.entries(), 5)
    ui.wait_until(lambda: '#mention(entry: "c-asa")' in (ui.js("window.__scriptorum.flush().then(() => 0)") or 0, ui.state()["text"])[1], 10)
    assert 'Sunday. #mention(entry: "c-asa"), Märta' in ui.state()["text"]


def test_T_WORLD_13_upgrade_in_the_window(ui):
    """T-WORLD-13 (window): the upgrade dialog lists the text and links it."""
    ui.run("window.__scriptorum.offerUpgrade(true)")
    assert ui.js("document.getElementById('upgrade-dialog').open")
    rows = texts(ui, "#upgrade-list tr .upgrade-value")
    assert rows[0] == "Skärvik harbour, early morning" and "Nils Ek" in rows
    ui.js("document.getElementById('upgrade-apply').click()")
    ui.wait_until(lambda: "place:" in (ui.state()["text"] or ""), 10)
    text = ui.state()["text"]
    assert "location:" not in text and 'writer: "c-nils-ek"' in text
