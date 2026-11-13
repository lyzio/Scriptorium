"""Test Plan UI smoke tests for Milestone 4: the toolbar's insert groups, the
six menus and the Light / Dark switch, the Settings window, palettes and
dark mode, and the example adventure (F9, F16, F18, F20).

The tests run in file order and share one window.
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

    folder = tmp_path_factory.mktemp("ui-m4")
    os.environ["SCRIPTORUM_DOCUMENTS"] = str(folder / "documents")
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


def texts(ui, selector: str) -> list:
    return ui.js(f"[...document.querySelectorAll({json.dumps(selector)})].map(e => e.textContent.trim())")


def css_var(ui, name: str) -> str:
    return ui.js(f"getComputedStyle(document.documentElement).getPropertyValue('{name}').trim()")


def test_T_UI_19_settings_window_without_adventure(ui):
    """T-UI-19: File ▸ Settings… (Ctrl+,) opens one window with Application,
    Colours, Modules and Adventure; Adventure is greyed out with no adventure."""
    ui.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: ',', ctrlKey: true, bubbles: true})); true")
    ui.wait_until(lambda: ui.js("!document.getElementById('settings').classList.contains('hidden')") is True)
    assert texts(ui, ".settings-nav button > span") == ["Application", "Colours", "Modules", "Adventure"]
    assert ui.js("document.getElementById('sn-adventure').disabled") is True
    assert ui.js("document.getElementById('sn-adventure-name').textContent") == "No adventure open"
    assert ui.js("window.__scriptorum.settingsSection()") == "application"
    # Modules: until M6 a list of the installed modules.
    ui.run("window.__scriptorum.showSection('modules')")
    # Corrected for M6: the name cell also holds tags, the ID and the description.
    names = ui.js("[...document.querySelectorAll('.module-table .module-name')].map(e => e.firstChild.textContent)")
    assert {"Vaesen", "Legends and Lattes", "Call of Cthulhu", "Claret & Ink", "Core elements"} <= set(names)
    ui.run("window.__scriptorum.closeSettings()")


def test_T_UI_20_light_and_dark(ui):
    """T-UI-20 / T-UI-07: Light, Dark and Follow the computer switch the
    window at once; the page preview stays white."""
    ui.run("window.__scriptorum.shell.setApp({mode: 'light'})")
    assert ui.js("document.documentElement.dataset.mode") == "light"
    assert css_var(ui, "--bg").upper() == "#DED5C7"
    # The switch at the right end of the menu bar.
    ui.js("document.querySelector('#mode-switch button[data-mode=dark]').click(); true")
    ui.wait_until(lambda: ui.js("document.documentElement.dataset.mode") == "dark")
    assert css_var(ui, "--bg").upper() == "#1B2F33" and css_var(ui, "--accent-ink").upper() == "#CC9A8E"
    assert ui.window.bridge.session.app_settings.get("mode") == "dark"
    # Follow the computer: the computer's light/dark setting decides.
    ui.run("window.__scriptorum.shell.setApp({mode: 'system'})")
    ui.window.bridge.set_system_dark(True)
    ui.wait_until(lambda: ui.js("document.documentElement.dataset.mode") == "dark")
    ui.window.bridge.set_system_dark(False)
    ui.wait_until(lambda: ui.js("document.documentElement.dataset.mode") == "light")
    assert ui.js("getComputedStyle(document.querySelector('.page') || document.body).backgroundColor") is not None


def test_T_UI_24_open_example(ui):
    """T-UI-24: the welcome screen opens the example adventure as a copy in
    the user's documents; the bundled original never changes."""
    from scriptorum import paths
    from scriptorum.core.modules import folder_digest
    original = paths.examples_dir() / "jatten-finns-skuld"
    before = folder_digest(original)
    assert ui.js("document.getElementById('w-example').textContent") == "Open the example adventure"
    ui.js("document.getElementById('w-example').click(); true")
    ui.wait_until(lambda: (ui.state()["info"] or {}).get("title") == "Jätten Finns skuld", 30)
    copy = ui.folder / "documents" / "Jätten Finns skuld.scav"
    assert copy.is_file() and ui.state()["info"]["path"] == str(copy)
    ui.wait_until(lambda: ui.state()["pages"] > 0, 30)
    ui.type_input(".el-scene .field-title input", "Under Helgonabacken i natt")
    ui.run("window.__scriptorum.flush()")
    assert json.loads(ui.window.bridge.save())["ok"]
    assert folder_digest(original) == before
    # Help ▸ Open the example adventure makes another copy.
    help_items = [i["label"] for i in ui.js("window.__scriptorum.menuModel()")[5]["items"]]
    assert "Open the example adventure" in help_items


def test_T_UI_17_toolbar(ui):
    """T-UI-17: the mode switch, the paragraph style, the insert groups,
    Table and Image, Preview and Handouts only; each group lists only the
    elements the game system turns on, and an empty group is hidden."""
    assert texts(ui, "#tb-groups .tb-group span:not(.icon-svg)") == ["Structure", "Boxes", "People", "Rules", "Handouts"]
    assert texts(ui, "#tb-groups .tb-plain span:not(.icon-svg)") == ["Table", "Image"]
    assert ui.js("document.querySelectorAll('#tb-groups svg').length") >= 7  # Phosphor Light icons
    for gone in ("tb-export", "tb-system", "tb-theme", "tb-insert"):
        assert ui.js(f"document.getElementById('{gone}')") is None
    assert ui.js("document.getElementById('tb-style').tagName") == "SELECT"
    labels = lambda group: [i["label"] for i in ui.js(f"window.__scriptorum.groupItems('{group}')")]
    # M6 part C (F4): the three sub-heading levels follow the scene (test plan change log, 13 Nov 2026).
    assert labels("structure") == ["Act heading", "Scene", "Sub-heading 1", "Sub-heading 2", "Sub-heading 3", "End of scene", "Page break", "Column break"]
    assert labels("boxes") == ["Read-aloud", "Secret", "Public information", "Hint", "Box", "Quote"]
    assert labels("people") == ["Person", "Creature", "Codex card", "Mention", "See page", "New codex entry…"]
    assert labels("rules") == ["Check", "Dice", "Countdown", "Pacing note"]
    assert labels("handouts") == ["Handout", "Map", "Relationship chart", "New map…"]
    # Inserting from a group: Public information goes in as a public box.
    ui.js("document.querySelector('.el-scene .field-title input').focus()")
    ui.js("document.getElementById('tb-group-boxes').click(); true")
    ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].find(b => b.textContent === 'Public information').click(); true")
    ui.run("window.__scriptorum.flush()")
    assert '#information(variant: "public")' in ui.state()["text"]
    ui.run("window.__scriptorum.undo()")
    # A game system with fewer elements: groups list only those; empty ones hide.
    current = ui.window.bridge.session.editor_info()["elements"]
    few = [d for d in current if d["id"] in ("scene", "read-aloud")]
    ui.js(f"window.__scriptorum.setDefs({json.dumps(few)}); true")
    assert texts(ui, "#tb-groups .tb-group span:not(.icon-svg)") == ["Structure", "Boxes"]
    assert [i["label"] for i in ui.js("window.__scriptorum.groupItems('boxes')")] == ["Read-aloud"]
    ui.js(f"window.__scriptorum.setDefs({json.dumps(current)}); true")
    # Handouts only is shown only while the preview is shown.
    ui.run("window.__scriptorum.setPreview(false)")
    assert ui.js("document.getElementById('tb-handouts').classList.contains('hidden')") is True
    ui.run("window.__scriptorum.setPreview(true)")
    assert ui.js("document.getElementById('tb-handouts').classList.contains('hidden')") is False


def test_T_UI_18_menu_bar(ui):
    """T-UI-18: six menus and the Light / Dark switch; File ▸ Export holds the
    adventure and handouts PDFs; the former Adventure, Export and Modules
    items are reachable; File ▸ New adventure has no submenu."""
    menus = ui.js("window.__scriptorum.menuModel()")
    assert [m["key"] for m in menus] == ["menu.file", "menu.edit", "menu.view", "menu.insert", "menu.format", "menu.help"]
    assert ui.js("document.querySelectorAll('#mode-switch button').length") == 2
    file_items = {i["label"]: i for i in menus[0]["items"]}
    assert file_items["New adventure…"]["children"] == []
    # M5 (F9, F7.6): the booklet and print-shop PDFs follow the first two.
    assert file_items["Export"]["children"][:2] == ["Export adventure PDF…", "Export handouts PDF…"]
    # Corrected in M6 part B: Save for sharing was dropped (F14, 12 Nov 2026).
    assert "Settings…" in file_items and "Revert to previous version…" in file_items
    assert "Save for sharing…" not in file_items
    edit = [i["label"] for i in menus[1]["items"]]
    view = [i["label"] for i in menus[2]["items"]]
    assert "Link text to the codex…" in edit
    assert "Relationship chart" in view and "Show breaks" in view
    all_labels = [i["label"] for m in menus for i in m["items"]]
    assert "Add font…" not in all_labels and "New codex entry…" not in all_labels and "New map…" not in all_labels


def test_T_UI_19_settings_window_with_adventure(ui):
    """T-UI-19: Adventure shows the current tab's adventure; every change
    applies at once (theme, secret box fill, text size)."""
    ui.run("window.__scriptorum.openSettingsWindow('adventure')")
    assert ui.js("document.getElementById('sn-adventure').disabled") is False
    assert ui.js("document.getElementById('sn-adventure-name').textContent") == "Jätten Finns skuld"
    themes = ui.js("[...document.querySelectorAll('#set-theme option')].map(o => o.textContent)")
    # M5: the Plain theme is the first of the general themes (F8).
    assert themes == ["Vaesen", "Plain (for every game system)", "Call of Cthulhu (for every game system)", "Legends and Lattes (for every game system)"]
    before = ui.builds()
    ui.js("const s = document.getElementById('set-theme'); s.value = 'scriptorum.call-of-cthulhu'; s.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.theme.id == "scriptorum.call-of-cthulhu", 10)
    ui.wait_until(lambda: ui.builds() > before, 20)  # re-rendered at once
    ui.js("const f = document.getElementById('set-secretFill'); f.value = 'beige'; f.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: ui.window.bridge.session.adventure.settings.get("secret_fill") == "beige", 10)
    ui.run("window.__scriptorum.showSection('colours')")
    ui.js("const i = document.getElementById('app-uiSize'); i.value = '15'; i.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: css_var(ui, "--ui-size") == "15px", 10)
    ui.run("window.__scriptorum.showSection('application')")
    ui.js("const i = document.getElementById('app-snapshotMinutes'); i.value = '10'; i.dispatchEvent(new Event('change')); true")
    ui.wait_until(lambda: ui.window.bridge.session.clock.interval == 600, 10)
    ui.run("window.__scriptorum.shell.setApp({ui_size: 13, snapshot_minutes: 15})")
    ui.run("window.__scriptorum.closeSettings()")


def test_T_UI_21_new_palette(ui):
    """T-UI-21: New palette from this one: change a colour, the window
    updates live; a text colour below 4.5 warns but is allowed; Save makes a
    palette module that is chosen, and still chosen after a restart."""
    from scriptorum.core import appsettings
    ui.run("window.__scriptorum.shell.setApp({mode: 'light'})")
    ui.run("window.__scriptorum.openSettingsWindow('colours')")
    ui.js("document.getElementById('app-newPalette').click(); true")
    ui.wait_until(lambda: ui.js("!!document.getElementById('palette-editor')") is True)
    assert ui.js("document.querySelectorAll('#palette-editor input[type=color]').length") == 2 * 25
    ui.js("""(() => { const i = document.querySelector('#palette-editor input[data-token=window][data-mode=light]');
        i.value = '#f0e6d2'; i.dispatchEvent(new Event('input')); })()""")
    ui.wait_until(lambda: css_var(ui, "--bg").lower() == "#f0e6d2")
    ui.js("""(() => { const i = document.querySelector('#palette-editor input[data-token=muted][data-mode=light]');
        i.value = '#b0b0b0'; i.dispatchEvent(new Event('input')); })()""")
    ui.wait_until(lambda: "contrast" in (ui.js("document.getElementById('palette-warning').textContent") or ""))
    ui.type_input("#palette-name", "Pergament")
    ui.js("document.getElementById('palette-save').click(); true")
    ui.wait_until(lambda: ui.window.bridge.session.app_settings.get("palette") == "my.pergament", 10)
    library = ui.window.bridge.session.library
    module = library.newest("my.pergament")
    assert module.kind == "palette" and module.palette()["light"]["window"] == "#F0E6D2"
    restarted = appsettings.AppSettings(ui.window.bridge.session.app_settings.file)
    assert appsettings.chosen_palette(library, restarted).id == "my.pergament"
    # Reset to Claret & Ink.
    ui.js("document.getElementById('app-resetPalette').click(); true")
    ui.wait_until(lambda: ui.window.bridge.session.app_settings.get("palette") == "scriptorum.claret-and-ink", 10)
    assert css_var(ui, "--bg").upper() == "#DED5C7"
    ui.run("window.__scriptorum.closeSettings()")


def test_T_UI_22_shift_skips_palette_stylesheet(ui):
    """T-UI-22 (window part): with Shift held at start the palette's own
    stylesheet is not used."""
    ui.window.bridge.skip_css = True
    info = json.loads(ui.window.bridge.appSettings())
    assert info["skipCss"] is True and info["palette"]["css"] == ""
    ui.window.bridge.skip_css = False


def test_T_LOOK_06_hands_in_the_editor(ui):
    """T-LOOK-06 (window part): the handwriting choice lists the six hands by
    their kind, with the font's name beside them."""
    options = ui.js("[...document.querySelector('.el-handout .field-choice').options].map(o => o.textContent)")
    assert options[1:7] == ["Everyday hand · Homemade Apple", "Copperplate · Pinyon Script", "Flowing hand · Dancing Script",
                            "Note hand · Caveat", "School hand · Cedarville Cursive", "Typewriter · TT2020 Style E"]


def test_T_WORLD_24_sheets_in_handouts_tab(ui):
    """F6.5: the Handouts tab shows the number of sheets beside a handout
    that needs more than one."""
    session = ui.window.bridge.session
    text = session.adventure.chapter_text("text/chapter-01.typ")
    long_letter = "\n\n".join(["Jag skrifver åter om jätten i kryptan och om sången på backen om natten."] * 60)
    session.set_chapter_text(0, text.replace("Ärade herrar,", "Ärade herrar,\n\n" + long_letter, 1))
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.showNavTab('handouts')")
    ui.wait_until(lambda: any("sheets" in t for t in texts(ui, "#handouts-panel .handout-sheets")), 30)
