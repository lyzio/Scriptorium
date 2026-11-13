"""Test Plan UI smoke tests for Milestone 2: the real window, headless.

The tests run in file order and share one window, like one person working
through the Milestone 2 functions: the settings page, the insert menu,
editing on the page, Hybrid mode, tables, images, find and replace, spell
check, tabs, pasting, Convert to, moving blocks and the outline.
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from tests.drag_js import HELPERS as DRAG_HELPERS

from tests.test_ui_smoke import Driver

pytestmark = pytest.mark.ui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


@pytest.fixture(scope="module")
def ui(library, tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session
    from tests.conftest import pack_sample

    folder = tmp_path_factory.mktemp("ui-m2")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    path = pack_sample("m2-full", folder)
    assert json.loads(window.bridge.openPath(str(path)))["ok"]
    driver.run("window.__scriptorum.refresh()")
    driver.wait_until(lambda: driver.state()["pages"] > 0 and driver.state()["elements"], 20)
    yield driver
    window.close()


def text(ui) -> str:
    ui.run("window.__scriptorum.flush()")
    return ui.state()["text"]


def keydown(ui, selector, key: str, **mods) -> None:
    """A key press on an element, or on whatever has the focus."""
    options = json.dumps({"key": key, "bubbles": True, "cancelable": True, **mods})
    target = f"document.querySelector({json.dumps(selector)})" if selector else "document.activeElement"
    ui.js(f"(() => {{ const el = {target}; el.focus && el.focus();"
          f" el.dispatchEvent(new KeyboardEvent('keydown', {options})); return true; }})()")


def menu_items(ui) -> list:
    return ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].map(b => b.textContent)")


# --- settings page (F7.3, F7.9) --------------------------------------------------------

def test_T_UI_09_page_setup_on_the_settings_page(ui):
    """T-UI-09: page size, orientation and columns are set on the adventure
    settings page and shown in the preview; they are not in the toolbar."""
    assert ui.js("document.getElementById('tb-page')") is None
    assert "Page" not in ui.js("[...document.querySelectorAll('#toolbar .chip-label')].map(c => c.textContent)")
    ui.run("window.__scriptorum.openSettings()")
    assert ui.js("!document.getElementById('settings').classList.contains('hidden')") is True
    assert ui.js("document.getElementById('set-columns').value") == "2"
    before = ui.builds()
    ui.js("const s = document.getElementById('set-columns'); s.value = '1'; s.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.settings.get("page", {}).get("columns") == 1)
    ui.wait_until(lambda: ui.builds() > before, 10)
    assert ui.window.bridge.session.page_settings()["values"]["columns"] == 1
    page_json = json.loads((ui.window.bridge.session.work_dir / "page.json").read_text())
    assert page_json["columns"] == 1


def test_T_UI_11_settings_show_where_values_come_from(ui):
    """T-UI-11: each value shows where it comes from; changing a value
    changes the preview."""
    origin = lambda key: ui.js(f"document.getElementById('origin-{key}').textContent")  # noqa: E731
    assert origin("columns") == "Set for this adventure"
    assert origin("paper") == "From the theme Vaesen"
    assert origin("orientation") == "App default"
    assert ui.js("document.getElementById('reset-paper').classList.contains('hidden')") is True
    before = ui.builds()
    ui.js("const s = document.getElementById('set-paper'); s.value = 'a5'; s.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: origin("paper") == "Set for this adventure")
    ui.wait_until(lambda: ui.builds() > before, 10)
    # Corrected in M6 part B: wait until the new page picture has loaded.
    ui.wait_until(lambda: (ui.js("document.querySelector('#pages img')?.naturalWidth") or 0) > 0, 10)
    width = ui.js("document.querySelector('#pages img').naturalWidth")
    assert 540 < width < 580  # A5 is 148 mm wide: 559 px at 96 dpi
    ui.js("document.getElementById('reset-paper').click(); document.getElementById('reset-columns').click(); true")
    ui.wait_until(lambda: origin("paper") == "From the theme Vaesen" and origin("columns") == "From the theme Vaesen")
    # The title page fields are stored in the adventure settings.
    ui.js("const i = document.getElementById('set-author'); i.value = 'Åsa Berg'; i.dispatchEvent(new Event('input')); true")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.settings["title_page"].get("author") == "Åsa Berg")
    ui.run("window.__scriptorum.closeSettings()")
    assert ui.js("document.getElementById('settings').classList.contains('hidden')") is True


# --- insert menu and shortcuts (F4.4) -------------------------------------------------

def test_T_UI_13_insert_menu_and_shortcuts(ui):
    """T-UI-13: every element the game system turns on is in the Insert menu
    with its shortcut; Ctrl+D asks whether to insert dice or a check."""
    # M4 (F9): the toolbar's Insert button became the insert groups; the
    # Insert menu keeps the full list.
    ui.js("[...document.querySelectorAll('#menubar .menu-btn')].find(b => b.textContent === 'Insert').click(); true")
    items = menu_items(ui)
    for name in ("Paragraph", "Act heading", "Scene", "Read-aloud", "Information", "Person", "Creature",
                 "Countdown", "Dice", "Check", "Handout", "Table", "Image…", "Page break", "Column break"):
        assert any(i.startswith(name) for i in items), name
    assert not any(i.startswith("Countdown step") for i in items)  # only inside a countdown
    assert "SceneCtrl+Shift+S" in items and "DiceCtrl+D" in items
    ui.js("document.body.click(); true")
    # Ctrl+D inside a sentence: choose dice, and an inline die goes in at the caret.
    ui.js("""(() => { const p = document.querySelectorAll('.blk-paragraph .para')[0]; p.focus();
        const r = document.createRange(); r.selectNodeContents(p); r.collapse(false);
        getSelection().removeAllRanges(); getSelection().addRange(r); return true; })()""")
    keydown(ui, None, "d", ctrlKey=True)
    assert menu_items(ui) == ["Dice", "Check"]
    ui.js("[...document.querySelectorAll('#menu-popup .menu-item')][0].click(); true")
    assert 'Åsa, Märta and Örjan wait on the jetty.#dice(dice: "D6")' in text(ui) or \
        'wait on the jetty. #dice(dice: "D6")' in text(ui)


# --- editing on the page (F12 stage 1) --------------------------------------------------

def test_T_UI_10_click_element_on_page(ui):
    """T-UI-10: clicking an element on a preview page opens a popover with its
    fields; the change applies and the page updates."""
    ui.wait_until(lambda: any(e["kind"] == "person" for e in ui.state()["elements"]), 15)
    person = next(e for e in ui.state()["elements"] if e["kind"] == "person")
    opened = ui.js(f"window.__scriptorum.openPopoverAt({person['page'] - 1}, {person['x'] + 5}, {person['y'] + 6}, 595, 700, 200)"
                   f".then(r => window.__opened = r); true")
    assert opened
    ui.wait_until(lambda: ui.js("window.__opened") is True)
    assert ui.js("document.querySelector('#popover-body .el-person .field-name input').value") == "Lovisa Berg"
    before = ui.builds()
    ui.type_input("#popover-body .el-person .field-name input", "Lovisa Berg-Holm")
    ui.run("window.__scriptorum.closePopover()")
    assert ui.js("document.getElementById('popover').classList.contains('hidden')") is True
    assert '#person(name: "Lovisa Berg-Holm"' in ui.state()["text"]
    ui.wait_until(lambda: ui.builds() > before, 10)
    assert ui.js("document.querySelector('.el-person .field-name input').value") == "Lovisa Berg-Holm"


# --- Hybrid mode (F4.1) ------------------------------------------------------------------

def test_T_SRC_10_hybrid_mode(ui):
    """T-SRC-10: Hybrid mode shows the source of the element under the
    cursor, matching Source mode; an edit there applies."""
    ui.run("window.__scriptorum.setMode('hybrid')")
    ui.js("document.querySelector('.el-check .el-body').focus(); true")
    expected = '#check(roll: "Vigilance", difficulty: "hard")[The characters hear oars that are not their own.]'
    ui.wait_until(lambda: ui.js("document.getElementById('hybrid-source').value") == expected)
    assert expected in ui.state()["text"]
    ui.js("const a = document.getElementById('hybrid-source'); a.focus(); a.value = a.value.replace('hard', 'easy'); true")
    ui.js("document.querySelector('.el-scene .field-title input').focus(); true")  # leaving the box applies it
    ui.wait_until(lambda: 'difficulty: "easy"' in (ui.state()["text"] or ""))
    assert ui.js("document.querySelector('.el-check .field-difficulty input').value") == "easy"
    ui.run("window.__scriptorum.setMode('visual')")


# --- tables, images, find and replace, spell check (F4.5–F4.8) ------------------------------

def test_T_SRC_11_tables(ui):
    """T-SRC-11 (F4.5): Tab moves between cells and adds a row at the end;
    tab-separated text from a spreadsheet fills the cells."""
    ui.js("document.querySelectorAll('.el-scene .field-title input')[1].focus(); true")
    ui.run("window.__scriptorum.insert('table')")
    last_table = "[...document.querySelectorAll('.tbl')].pop()"
    ui.js(f"(() => {{ const c = {last_table}.querySelector('[data-r=\"0\"][data-c=\"0\"]'); c.focus(); c.textContent = 'Hour';"
          " c.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
    keydown(ui, None, "Tab")
    assert ui.js("document.activeElement.dataset.c") == "1"
    ui.js("document.execCommand('insertText', false, 'Event'); true")
    ui.js(f"{last_table}.querySelector('[data-r=\"1\"][data-c=\"1\"]').focus(); true")
    keydown(ui, None, "Tab")  # Tab in the last cell adds a row
    ui.wait_until(lambda: ui.js(f"{last_table}.querySelectorAll('tr').length") == 3)
    ui.js(f"""(() => {{ const c = {last_table}.querySelector('[data-r="1"][data-c="0"]'); c.focus();
        const dt = new DataTransfer(); dt.setData('text/plain', '22:00\\tThe singing starts\\n02:00\\tA crash from the crypt\\n');
        c.dispatchEvent(new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}})); return true; }})()""")
    source = text(ui)
    assert "table.header([Hour], [Event])," in source
    assert "[22:00], [The singing starts]," in source and "[02:00], [A crash from the crypt]," in source


def test_T_SRC_11_images(ui):
    """T-SRC-11 (F4.6): an image dragged into the editor is copied into the
    adventure's assets/images/."""
    data = base64.b64encode((ui.window.bridge.session.adventure.files["assets/images/bell.png"])).decode()
    ui.run(f"window.__scriptorum.dropImage('Lantern map.png', {json.dumps(data)})")
    assert '#image("/assets/images/Lantern-map.png")' in text(ui)
    assert "assets/images/Lantern-map.png" in ui.window.bridge.session.adventure.files
    ui.wait_until(lambda: ui.js("[...document.querySelectorAll('.img-preview')].every(i => i.complete && i.naturalWidth > 0)") is True)


def test_T_SRC_11_find_and_replace(ui):
    """T-SRC-11 (F4.7): find and replace across the whole adventure."""
    ui.run("window.__scriptorum.openFind()")
    ui.js("document.getElementById('find-query').value = 'harbour'; true")
    ui.run("window.__scriptorum.runFind()")
    assert ui.js("document.getElementById('find-count').textContent") == "1 of 7"
    ui.js("document.getElementById('find-replace').value = 'haven'; true")
    history = ui.state()["historyLength"]
    ui.run("window.__scriptorum.replaceAll()")
    assert ui.js("document.getElementById('find-count').textContent") == "7 replaced"
    source = ui.state()["text"]
    # Only the link names still say "harbour".
    assert source.lower().count("harbour") == source.count("s-harbour") == 2 and "Skärvik haven, early morning" in source
    # Link names are not text, so the countdown still finds its scene.
    assert '#scene(title: "The haven"' in source and 'id: "s-harbour"' in source and 'go-to: "s-harbour"' in source
    assert ui.state()["historyLength"] == history + 1  # one undo step
    ui.run("window.__scriptorum.undo()")
    assert "Skärvik harbour, early morning" in ui.state()["text"]
    ui.js("document.getElementById('find-close').click(); true")


def test_T_SRC_11_spell_check(ui):
    """T-SRC-11 (F4.8): Swedish and English words are checked; misspelt words
    are marked and suggestions offered."""
    ui.wait_until(lambda: ui.window.bridge.spelling.ready, 60)
    wrong = json.loads(ui.window.bridge.spell(json.dumps(["Spökhuset", "står", "tomt", "iinte", "The", "ghosst", "harbour", "colour", "color"])))
    assert wrong == {"ready": True, "wrong": ["ghosst", "iinte"]}
    ui.js("""(() => { const p = document.querySelectorAll('.blk-paragraph .para')[0]; p.focus();
        document.execCommand('insertText', false, ' Spökhuset står iinte tomt, the ghosst waits.'); return true; })()""")
    ui.wait_until(lambda: int(ui.js("document.body.dataset.misspelt || 0")) >= 2, 15)
    suggestions = []
    ui.window.bridge.suggestions.connect(lambda reply: suggestions.append(json.loads(reply)))
    ui.window.bridge.suggest("ghosst")
    ui.wait_until(lambda: suggestions, 30)
    assert "ghost" in suggestions[0]["suggestions"]
    ui.run("window.__scriptorum.undo()")


# --- tabs (F2.2), pasting, Convert to, moving blocks, the outline -------------------------

def test_T_FILE_13_two_adventures_in_tabs(ui):
    """T-FILE-13: each tab keeps its own text, title and unsaved state."""
    first = ui.state()["info"]["id"]
    first_text = text(ui)
    reply = json.loads(ui.window.bridge.newAdventure(json.dumps({
        "title": "Convert test", "gameSystem": {"id": GS[0], "version": GS[1]}, "theme": {"id": TH[0], "version": TH[1]},
    })))
    assert reply["ok"]
    ui.run("window.__scriptorum.refresh()")
    tabs = ui.state()["tabs"]
    assert [t["title"] for t in tabs] == ["The Bell of Skärvik", "Convert test"] and tabs[1]["active"]
    assert ui.js("[...document.querySelectorAll('#tabbar .tab-label')].map(b => b.textContent)") == ["The Bell of Skärvik •", "Convert test •"]
    ui.type_input(".el-scene .field-title input", "Only in the second tab")
    second_text = text(ui)
    ui.run(f"window.__scriptorum.switchTab({json.dumps(first)})")
    assert ui.state()["text"] == first_text and ui.state()["info"]["title"] == "The Bell of Skärvik"
    assert ui.window.windowTitle() == "The Bell of Skärvik (unsaved) — Scriptorum"
    second = ui.state()["tabs"][1]["id"]
    ui.run(f"window.__scriptorum.switchTab({json.dumps(second)})")
    assert ui.state()["text"] == second_text and "Only in the second tab" in second_text


PASTE = "Scene 1: The harbour\nFog lies thick over the water.\nThe bell belongs to the Hoppet.\n\nScene 2: The chapel\nThe sexton keeps the records."


def test_T_SRC_15_paste_several_lines(ui):
    """T-SRC-15: text of several lines pasted into a paragraph becomes one
    paragraph per line at once."""
    ui.run("window.__scriptorum.setMode('source')")
    ui.type_input(".source-area", "= Convert test\n\nFirst paragraph.\n")
    ui.run("window.__scriptorum.flush()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js(f"""(() => {{ const p = document.querySelector('.blk-paragraph .para'); p.focus(); p.textContent = '';
        p.dispatchEvent(new Event('input', {{bubbles: true}}));
        const dt = new DataTransfer(); dt.setData('text/plain', {json.dumps(PASTE)});
        p.dispatchEvent(new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}})); return true; }})()""")
    paragraphs = ui.js("[...document.querySelectorAll('.blk-paragraph .para')].map(p => p.textContent)")
    assert paragraphs == ["Scene 1: The harbour", "Fog lies thick over the water.", "The bell belongs to the Hoppet.",
                          "Scene 2: The chapel", "The sexton keeps the records."]
    assert text(ui).count("\n\n") >= 5


def test_T_SRC_13_convert_to(ui):
    """T-SRC-13: Convert to keeps the text; a scene takes in the blocks up to
    the next scene; each conversion is one undo step."""
    ui.run("window.__scriptorum.convert([1], 'scene')")
    source = text(ui)
    assert '#scene(title: "Scene 1: The harbour")[' in source
    assert source.index("Fog lies thick") > source.index("Scene 1: The harbour")
    # "Scene 2" is inside scene 1 now; converting it starts a new scene after it.
    ui.run("window.__scriptorum.convert([1, 2], 'scene')")
    source = text(ui)
    assert '#scene(title: "Scene 2: The chapel")[' in source
    outline = [o["title"] for o in ui.state()["outline"] if o["kind"] == "scene"]
    assert outline == ["Scene 1: The harbour", "Scene 2: The chapel"]
    ui.run("window.__scriptorum.convert([1, 0], 'read-aloud')")
    assert "#read-aloud[Fog lies thick over the water.]" in text(ui)
    history = ui.state()["historyPos"]
    ui.run("window.__scriptorum.convert([1, 1], 'information')")
    assert '#information(variant: "secret")[The bell belongs to the Hoppet.]' in text(ui)
    assert ui.state()["historyPos"] == history + 1
    ui.run("window.__scriptorum.undo()")
    assert "#information" not in ui.state()["text"] and "The bell belongs to the Hoppet." in ui.state()["text"]
    ui.run("window.__scriptorum.redo()")
    ui.run("window.__scriptorum.convert([1, 0], 'paragraph')")
    assert "#read-aloud" not in text(ui) and "Fog lies thick over the water." in ui.state()["text"]
    ui.run("window.__scriptorum.undo()")
    assert "#read-aloud[Fog lies thick over the water.]" in ui.state()["text"]
    # A heading from a paragraph, through the right-click menu.
    ui.js("""(() => { const s = [...document.querySelectorAll('.blk-paragraph')].pop();
        s.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 300, clientY: 300})); return true; })()""")
    items = ui.js("[...document.querySelectorAll('#menu-popup .menu-item, #menu-popup .menu-heading')].map(b => b.textContent)")
    assert "Convert to" in items and "Read-aloud" in items and "Insert after" in items
    ui.js("document.body.click(); true")


def test_T_SRC_14_moving_blocks(ui):
    """T-SRC-14: blocks move with ↑ ↓, Alt+↑/↓ and the grip (drag and drop);
    only to allowed places; each move is one undo step."""
    pos = lambda s: ui.state()["text"].index(s)  # noqa: E731
    assert pos("#read-aloud") < pos("#information")
    history = ui.state()["historyPos"]
    ui.run("window.__scriptorum.move([1, 0], 1)")
    text(ui)
    assert pos("#information") < pos("#read-aloud")
    assert ui.state()["historyPos"] == history + 1
    ui.run("window.__scriptorum.undo()")
    assert pos("#read-aloud") < pos("#information")
    # Alt+↓ from the keyboard.
    ui.js("document.querySelector('.el-read-aloud .el-body').focus(); true")
    keydown(ui, ".el-read-aloud .el-body", "ArrowDown", altKey=True)
    text(ui)
    assert pos("#information") < pos("#read-aloud")
    # Drag the read-aloud by its grip into scene 2, below "The sexton keeps the records."
    # M6 part C2: Scriptorum's own dragging with the pointer (F4.13), not the
    # system's drag-and-drop (test plan change log, 13 Nov 2026).
    ui.js(DRAG_HELPERS)
    drag = """(() => {
        const grip = window.__strip(document.querySelector('#visual .el-read-aloud'));
        const target = [...document.querySelectorAll('#visual .blk-paragraph')].find(s => s.textContent.includes('The sexton'));
        target.scrollIntoView({block: 'center'});
        const r = target.getBoundingClientRect();
        window.__drag(grip, r.left + 30, r.bottom - 3);
        return true; })()"""
    ui.js(drag)
    source = text(ui)
    assert source.index("The sexton keeps the records.") < source.index("#read-aloud") and source.index('"Scene 2') < source.index("#read-aloud")
    # A scene can never be dropped inside another scene (or itself).
    before = ui.state()["text"]
    ui.js("""(() => {
        const grip = window.__strip(document.querySelector('#visual .el-scene'));
        const target = document.querySelectorAll('#visual .el-scene')[1].querySelector('.blk');
        target.scrollIntoView({block: 'center'});
        const r = target.getBoundingClientRect();
        window.__drag(grip, r.left + 30, r.bottom - 3);
        return true; })()""")
    assert text(ui) == before


def test_T_UI_12_outline_acts_and_scenes(ui):
    """T-UI-12: the outline shows acts and scenes; dragging a scene moves it
    in the text, as one undo step."""
    items = ui.js("[...document.querySelectorAll('#outline .outline-item')].map(b => [b.className, b.textContent])")
    assert items == [["outline-item heading act", "Convert test"], ["outline-item scene", "1Scene 1: The harbour"],
                     ["outline-item scene", "2Scene 2: The chapel"]]
    history = ui.state()["historyPos"]
    ui.js(DRAG_HELPERS)
    ui.js("""(() => {
        const lis = [...document.querySelectorAll('#outline li.draggable')];
        const r = lis[1].getBoundingClientRect();
        window.__drag(lis[2], r.left + 40, r.top + 3);
        return true; })()""")
    source = text(ui)
    assert source.index("Scene 2: The chapel") < source.index("Scene 1: The harbour")
    assert [o["title"] for o in ui.state()["outline"] if o["kind"] == "scene"] == ["Scene 2: The chapel", "Scene 1: The harbour"]
    assert ui.state()["historyPos"] == history + 1
    ui.run("window.__scriptorum.undo()")
    assert [o["title"] for o in ui.state()["outline"] if o["kind"] == "scene"] == ["Scene 1: The harbour", "Scene 2: The chapel"]
