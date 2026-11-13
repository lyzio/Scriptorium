"""Milestone 6 part C2: the editor. Test Plan T-SRC-17 (sub-headings in the
text), T-BUILD-30 (printing them), T-UI-36 (moving, raising and lowering
them), T-UI-37 (the grip strip and Scriptorum's own dragging), T-UI-38
(moving blocks into and out of containers) and T-UI-39 (Information moved
into and out of person cards keeps who knows it)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from scriptorum import paths
from scriptorum.core import source
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library
from scriptorum.core.recent import RecentFiles
from scriptorum.core.session import Session
from tests.conftest import SAMPLES, pack_sample, sample_text
from tests.drag_js import HELPERS as DRAG_HELPERS
from tests.test_m5c import _structure

BUNDLED = paths.BUNDLED_MODULES_DIR
VAESEN = ("scriptorum.free-league-vaesen", "1.0.0", "scriptorum.vaesen", "1.0.0")
PLAIN = ("scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
THEMES = ("scriptorum.vaesen", "scriptorum.plain", "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu")

SUBS = """#scene(title: "The mill")[
Intro to the mill.

=== Upstairs

Upstairs text.

==== The loft

Loft text.

===== A beam

Beam text.

=== Downstairs

Downstairs text.
]

#scene(title: "The chapel")[
Chapel text.

=== The crypt

Crypt text.
]
"""


def _walk(blocks):
    for block in blocks:
        yield block
        if isinstance(block.get("body"), dict):
            yield from _walk(block["body"]["blocks"])


# --- T-SRC-17 sub-headings in the text ---------------------------------------------------

@pytest.mark.unit
def test_T_SRC_17_parse_and_write_back(session):
    """T-SRC-17: Sub-heading 1, 2 and 3 are ===, ==== and ===== inside a
    scene; they parse as headings of levels 3, 4 and 5 and write back
    byte-identical; the outline lists them under their scene with their path."""
    session.new("Subs", *VAESEN)
    kinds = session.kinds()
    doc = source.parse(SUBS, kinds)
    assert source.serialize(doc, kinds) == SUBS
    heads = [(b["level"], b["text"]) for b in _walk(doc["blocks"]) if b["type"] == "heading"]
    assert heads == [(3, "Upstairs"), (4, "The loft"), (5, "A beam"), (3, "Downstairs"), (3, "The crypt")]
    # Written afresh (as the editor sends them), they are the same text.
    for b in _walk(doc["blocks"]):
        b.pop("raw", None)
    assert source.serialize(doc, kinds) == SUBS
    outline = source.outline(doc)
    assert [(o["kind"], o.get("level"), o["title"], o["path"]) for o in outline] == [
        ("scene", None, "The mill", [0]), ("heading", 3, "Upstairs", [0, 1]), ("heading", 4, "The loft", [0, 3]),
        ("heading", 5, "A beam", [0, 5]), ("heading", 3, "Downstairs", [0, 7]),
        ("scene", None, "The chapel", [1]), ("heading", 3, "The crypt", [1, 1])]
    assert source.skipped_headings(doc, kinds) == []


@pytest.mark.unit
def test_T_SRC_17_skipped_levels_found(session):
    """T-SRC-17, T-UI-36: a sub-heading that skips a level, such as ====
    directly under a scene, is found (its text is never changed)."""
    session.new("Skips", *VAESEN)
    text = '#scene(title: "S")[\n==== Too deep\n\nText.\n\n=== Fine\n\n===== Skips again\n]\n'
    doc = source.parse(text, session.kinds())
    assert [(s["title"], s["level"], s["to"]) for s in source.skipped_headings(doc, session.kinds())] == [
        ("Too deep", 4, 3), ("Skips again", 5, 4)]
    assert source.serialize(doc, session.kinds()) == text


# --- T-BUILD-30 printing sub-headings -----------------------------------------------------

def _filler(n):
    return "\n\n".join(f"Paragraph {i} of running text that fills a line or two so the column moves on." for i in range(n))


@pytest.mark.integration
@pytest.mark.parametrize("theme", THEMES)
def test_T_BUILD_30_levels_bookmarks_and_tags(session, tmp_path, theme):
    """T-BUILD-30: in every theme the three levels print in smaller heading
    styles; the bookmarks nest acts, scenes and sub-headings; the table of
    contents lists only acts and scenes; the accessible PDF tags the
    sub-headings as levels 3, 4 and 5 with no level skipped."""
    session.new("Levels", *(VAESEN if theme == "scriptorum.vaesen" else PLAIN[:2] + (theme, "1.0.0")))
    text = "#contents()\n\n#page-break()\n\n= The first act\n\n" + SUBS
    session.set_chapter_text(0, text)
    reply = session.export_pdf(tmp_path / "a.pdf", variant="accessible")
    assert reply["ok"], reply
    data = (tmp_path / "a.pdf").read_bytes()
    reader = PdfReader(io.BytesIO(data))

    def tree(items):
        out = []
        for it in items:
            if isinstance(it, list):
                out[-1] = (out[-1][0], tree(it))
            else:
                out.append((it.title, []))
        return out
    assert tree(reader.outline) == [("The first act", [
        ("The mill", [("Upstairs", [("The loft", [("A beam", [])])]), ("Downstairs", [])]),
        ("The chapel", [("The crypt", [])])])]
    contents = "".join(reader.pages[1].extract_text().split())
    assert "Themill" in contents and "Thechapel" in contents
    assert "Upstairs" not in contents and "Thecrypt" not in contents
    tags = [kind for kind, _ in _structure(data)]
    for level in ("/H3", "/H4", "/H5"):
        assert level in tags, (theme, level)
    # Smaller than a scene title, in the theme's own look.
    style = (BUNDLED / theme / "templates" / "_style.typ").read_text("utf-8")
    sizes = [float(m) for m in re.findall(r"size: ([0-9.]+)pt", style.split("#let sub-heading-style")[1].split("#let sub-heading-space")[0])]
    scene = float(re.search(r"scene: ([0-9.]+)pt", style).group(1))
    assert len(sizes) == 3 and all(s < scene for s in sizes) and sizes == sorted(sizes, reverse=True)


def _lines(page):
    """(text, x, y) of each run of text on a PDF page."""
    found = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            # Typst places text through the transformation matrix: combine both.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            found.append((text.strip(), x, y))
    page.extract_text(visitor_text=visit)
    return found


@pytest.mark.integration
def test_T_BUILD_30_never_alone_at_the_foot(session):
    """T-BUILD-30: a sub-heading never starts a page by itself and is never
    left alone at the foot of a page or column: with the filler growing line
    by line, whenever a sub-heading prints, text of its own section follows
    it in the same column."""
    session.new("Foot", *VAESEN)
    width = None
    for n in range(14, 34):
        session.set_chapter_text(0, f'#scene(title: "Long")[\n{_filler(n)}\n\n=== Watch me\n\nMy own text follows here.\n]\n')
        result = session.build("pdf")
        assert result.ok
        reader = PdfReader(io.BytesIO(result.output[0]))
        width = float(reader.pages[0].mediabox.width)
        for page in reader.pages:
            runs = _lines(page)
            for text, x, y in runs:
                if text.startswith("Watch me"):
                    column = x < width / 2
                    below = [t for t, x2, y2 in runs if (x2 < width / 2) == column and y2 < y - 1]
                    assert below, (n, "heading alone at the foot")
                    assert any("My own text" in t for t, x2, y2 in runs if (x2 < width / 2) == column), n


@pytest.mark.integration
def test_T_BUILD_30_example_accessible_pdf(tmp_path, monkeypatch, library):
    """T-BUILD-30, F20: the bundled example adventure's headings no longer
    skip a level, so its accessible PDF passes; the test sample keeps its
    older text, which warns and stops the accessible PDF."""
    text = (paths.examples_dir() / "jatten-finns-skuld" / "text" / "chapter-01.typ").read_text("utf-8")
    old = sample_text("example-jattens-skuld")
    assert text.count("\n==== ") == old.count("\n==== ") - 5 and text.count("\n=== ") == old.count("\n=== ") + 5
    assert text.replace("\n=== ", "\n==== ") != text
    session = Session(library, Strings.from_library(library), RecentFiles(tmp_path / "recent.json"), tmp_path / "build")
    monkeypatch.setattr(paths, "documents_dir", lambda: tmp_path / "docs", raising=False)
    folder = tmp_path / "example"
    import shutil
    shutil.copytree(paths.examples_dir() / "jatten-finns-skuld", folder)
    target = tmp_path / "example.scav"
    with zipfile.ZipFile(target, "w") as zf:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(folder).as_posix())
    session.open(target)
    build = session.build("pdf")
    assert not [w for w in build.warnings if w.key == "warning.heading.skipsLevel"]
    reply = session.export_pdf(tmp_path / "example.pdf", variant="accessible")
    assert reply["ok"], reply
    session.open(pack_sample("example-jattens-skuld", tmp_path))
    texts = [session.localize(w) for w in session.build("pdf").warnings if w.key == "warning.heading.skipsLevel"]
    assert texts == [
        "Line 196: The heading “Vad Gerda vet” skips a level: it is a Sub-heading 2 with no Sub-heading 1 above it in its scene. Raise it to Sub-heading 1.",
        "Line 237: The heading “Möjliga vägar ut” skips a level: it is a Sub-heading 2 with no Sub-heading 1 above it in its scene. Raise it to Sub-heading 1."]
    assert not session.export_pdf(tmp_path / "old.pdf", variant="accessible")["ok"]


# --- the window -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6c2")
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


FIND = r"""
window.__blk = (text) => [...document.querySelectorAll('#visual section.blk')].find(s => {
  const own = s.querySelector(':scope > .heading-edit, :scope > .rich, :scope > .el > .el-body');
  return own && own.textContent.trim() === text; });
window.__el = (cls, n) => [...document.querySelectorAll('#visual .el-' + cls)][n || 0].closest('section.blk');
window.__over = (sec, where, dx) => { sec.scrollIntoView({block: 'center'}); const r = sec.getBoundingClientRect();
  return [r.left + (dx === undefined ? 90 : dx), where === 'top' ? r.top + 3 : r.bottom - 3]; };
true
"""


def load(ui, text, *system, title="C2"):
    reply = json.loads(ui.window.bridge.newAdventure(json.dumps({
        "title": title, "gameSystem": {"id": (system or VAESEN)[0], "version": "1.0.0"},
        "theme": {"id": (system or VAESEN)[2], "version": "1.0.0"}})))
    assert reply["ok"]
    ui.js("window.__dragUp && window.__dragUp(-1, -1); true")  # no drag left over from a test before
    ui.window.bridge.session.set_chapter_text(0, text)
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js(DRAG_HELPERS)
    ui.js(FIND)


def text(ui) -> str:
    ui.run("window.__scriptorum.flush()")
    return ui.state()["text"]


def history(ui) -> int:
    return ui.state()["historyPos"]


def drag(ui, grip_js: str, point_js: str, **opts) -> None:
    """Press on a grip, move to a point and let go (opts: release, steps)."""
    ui.js(f"(() => {{ const g = {grip_js}; const p = {point_js}; window.__drag(g, p[0], p[1], {json.dumps(opts)}); return true; }})()")
    ui.wait(150)


def order(source_text: str, *parts: str) -> bool:
    places = [source_text.index(p) for p in parts]
    return places == sorted(places)


def keydown(ui, selector_js: str, key: str, **mods) -> None:
    options = json.dumps({"key": key, "bubbles": True, "cancelable": True, **mods})
    ui.js(f"(() => {{ const el = {selector_js}; el.focus(); el.dispatchEvent(new KeyboardEvent('keydown', {options})); return true; }})()")
    ui.wait(150)


def context_items(ui, sec_js: str) -> list:
    ui.js(f"""(() => {{ const s = {sec_js}; s.scrollIntoView({{block: 'center'}}); const r = s.getBoundingClientRect();
        s.querySelector('.heading-edit, .rich').dispatchEvent(new MouseEvent('contextmenu', {{bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 8}})); return true; }})()""")
    return ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].map(b => b.textContent)")


def has(items: list, label: str) -> bool:
    """A menu item by its label (its text also holds the shortcut)."""
    return any(i == label or i.startswith(label) and i[len(label):] in ("Tab", "Shift+Tab") for i in items)


def pick(ui, label: str) -> None:
    ui.js(f"[...document.querySelectorAll('#menu-popup .menu-item')].find(b => b.textContent.startsWith({json.dumps(label)})).click(); true")
    ui.wait(200)


# --- T-SRC-17 in the window ---------------------------------------------------------------

@pytest.mark.ui
def test_T_SRC_17_sub_headings_in_visual_and_source(ui):
    """T-SRC-17: Sub-heading 1, 2 and 3 typed in Visual mode are written as
    ===, ==== and =====; Source mode shows the same; a paragraph converts to
    each level and back, each conversion one undo step."""
    load(ui, '#scene(title: "Writing")[\nA paragraph to convert.\n]\n')
    ui.js("document.querySelector('#visual .el-scene .rich').focus(); true")
    for kind in ("heading-3", "heading-4", "heading-5"):
        ui.run(f"window.__scriptorum.insert('{kind}')")
        ui.js(f"(() => {{ const h = [...document.querySelectorAll('#visual .heading-edit')].find(x => !x.textContent); h.focus();"
              f" document.execCommand('insertText', false, 'Level {kind[-1]}'); return true; }})()")
    written = text(ui)
    assert "=== Level 3\n" in written and "==== Level 4\n" in written and "===== Level 5\n" in written
    assert order(written, "A paragraph", "=== Level 3", "==== Level 4", "===== Level 5")
    ui.run("window.__scriptorum.setMode('source')")
    assert ui.js("document.querySelector('.source-area').value") == written
    # Convert a paragraph to each level and back, one undo step each (a
    # paragraph under a Sub-heading 3, so every level is allowed there).
    load(ui, '#scene(title: "Writing")[\n=== One\n\n==== Two\n\n===== Three\n\nA paragraph to convert.\n]\n')
    for kind, mark in (("heading-3", "=== "), ("heading-4", "==== "), ("heading-5", "===== "), ("paragraph", "")):
        before = history(ui)
        ui.run(f"window.__scriptorum.convert([0, 3], '{kind}')")
        now = text(ui)
        assert f"\n{mark}A paragraph to convert.\n" in now, kind
        assert history(ui) == before + 1
    # Converted to Sub-heading 3 right under the scene, a paragraph rises to 1 (no skipped level).
    load(ui, '#scene(title: "Writing")[\nFirst words.\n]\n')
    ui.run("window.__scriptorum.convert([0, 0], 'heading-5')")
    assert "[\n=== First words.\n" in text(ui)
    # The paragraph style list offers the three levels inside a scene.
    ui.js("document.querySelector('#visual .el-scene .rich').focus(); true")
    ui.wait(100)
    options = ui.js("[...document.querySelectorAll('#tb-style option')].map(o => o.textContent)")
    assert options == ["Paragraph", "Sub-heading 1", "Sub-heading 2", "Sub-heading 3"]
    items = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.insert" for i in m["items"]]
    assert {"Sub-heading 1", "Sub-heading 2", "Sub-heading 3"} <= set(items)


# --- T-UI-36 moving, raising and lowering sub-headings ----------------------------------------

@pytest.mark.ui
def test_T_UI_36_move_with_keys_and_buttons(ui):
    """T-UI-36: Alt+↓ / Alt+↑ and the arrows move a sub-heading with
    everything under it past the sub-heading of the same level, in one undo
    step."""
    load(ui, SUBS)
    start = history(ui)
    keydown(ui, "window.__blk('Upstairs').querySelector('.heading-edit')", "ArrowDown", altKey=True)
    moved = text(ui)
    assert order(moved, "Intro", "=== Downstairs", "Downstairs text.", "=== Upstairs", "Upstairs text.", "==== The loft",
                 "Loft text.", "===== A beam", "Beam text.", '"The chapel"')
    assert history(ui) == start + 1
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == SUBS
    ui.js(FIND)
    # The ↑ button on Downstairs does the same.
    ui.js("window.__blk('Downstairs').querySelector(':scope > .blk-controls .icon-btn').click(); true")
    ui.wait(150)
    assert order(text(ui), "=== Downstairs", "Downstairs text.", "=== Upstairs", "==== The loft", "===== A beam")
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == SUBS
    # At the top of its scene Alt+↑ steps out of the scene, just before it:
    # since M6 part C3 a sub-heading may stand outside any scene (F4).
    ui.js(FIND)
    keydown(ui, "window.__blk('The crypt').querySelector('.heading-edit')", "ArrowUp", altKey=True)
    assert order(text(ui), '"The chapel"', "=== The crypt", "Chapel text.")
    keydown(ui, "window.__blk('The crypt').querySelector('.heading-edit')", "ArrowUp", altKey=True)
    assert order(text(ui), "=== The crypt", '#scene(title: "The chapel")')


@pytest.mark.ui
def test_T_UI_36_drag_with_the_grip(ui):
    """T-UI-36: dragged by its grip, a sub-heading moves with its section,
    within its scene and into another, in one undo step; one dropped where
    it would skip a level rises by itself, and directly under a scene it is
    a Sub-heading 1."""
    load(ui, SUBS)
    start = history(ui)
    drag(ui, "window.__strip(window.__blk('Upstairs'))", "window.__over(window.__blk('Crypt text.'), 'bottom')")
    moved = text(ui)
    assert order(moved, '"The mill"', "Intro", "=== Downstairs", '"The chapel"', "=== The crypt", "Crypt text.",
                 "=== Upstairs", "Upstairs text.", "==== The loft", "Loft text.", "===== A beam")
    assert history(ui) == start + 1
    ui.run("window.__scriptorum.undo()")
    ui.js(FIND)
    # The loft (Sub-heading 2) dropped directly under the chapel scene, above any sub-heading: it rises
    # to Sub-heading 1, and its A beam with it.
    drag(ui, "window.__strip(window.__blk('The loft'))", "window.__over(window.__blk('Chapel text.'), 'top')")
    moved = text(ui)
    assert order(moved, '"The chapel"', "=== The loft", "Loft text.", "==== A beam", "Beam text.", "Chapel text.", "=== The crypt")
    assert "==== The loft" not in moved


@pytest.mark.ui
def test_T_UI_36_raise_lower_and_tab(ui):
    """T-UI-36: Raise and Lower in the right-click menu and Shift+Tab / Tab
    change one level at a time, with the sub-headings under it; Lower is
    not offered where it would skip a level."""
    load(ui, SUBS)
    items = context_items(ui, "window.__blk('Upstairs')")
    assert not has(items, "Raise") and not has(items, "Lower")  # Sub-heading 1, first in its scene
    ui.js("document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true")
    items = context_items(ui, "window.__blk('The loft')")
    assert has(items, "Raise") and not has(items, "Lower")
    ui.js("document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true")
    assert has(context_items(ui, "window.__blk('Downstairs')"), "Lower")  # under A beam: Lower would not skip
    ui.js("document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true")
    context_items(ui, "window.__blk('The loft')")
    pick(ui, "Raise")
    raised = text(ui)
    assert "=== The loft" in raised and "==== A beam" in raised
    ui.js(FIND)
    keydown(ui, "window.__blk('The loft').querySelector('.heading-edit')", "Tab")
    assert text(ui) == SUBS
    ui.js(FIND)
    before = history(ui)
    keydown(ui, "window.__blk('The loft').querySelector('.heading-edit')", "Tab", shiftKey=True)
    assert "=== The loft" in text(ui) and history(ui) == before + 1
    ui.run("window.__scriptorum.undo()")
    ui.js(FIND)
    # Tab where it would skip a level does nothing and says why.
    keydown(ui, "window.__blk('Upstairs').querySelector('.heading-edit')", "Tab")
    assert text(ui) == SUBS
    assert "skip a level" in ui.js("document.getElementById('st-flash').textContent")


@pytest.mark.ui
def test_T_UI_36_outline(ui):
    """T-UI-36: the outline shows sub-headings indented under their scene;
    dragging one there moves its section, and the drop line shows the level
    it will get; folding hides only the screen."""
    load(ui, SUBS)
    items = ui.js("[...document.querySelectorAll('#outline li[data-item] .outline-item')].map(b => [b.className, b.textContent, b.getBoundingClientRect().left + parseFloat(getComputedStyle(b).paddingLeft)])")
    labels = [(c.split()[1:], t) for c, t, _ in items]
    assert [t for _, t in labels] == ["1The mill", "Upstairs", "The loft", "A beam", "Downstairs", "2The chapel", "The crypt"]
    indent = {t: x for _, t, x in items}
    assert indent["1The mill"] < indent["Upstairs"] < indent["The loft"] < indent["A beam"]
    assert indent["Upstairs"] == indent["Downstairs"] == indent["The crypt"]
    # The drop line shows the level A beam (Sub-heading 3) will get: under
    # Downstairs a Sub-heading 2, just under the scene a Sub-heading 1.
    li = "[...document.querySelectorAll('#outline li[data-item]')]"
    ui.js(f"(() => {{ const lis = {li}; const to = lis[5].getBoundingClientRect();"
          f" window.__drag(lis[3], to.left + 60, to.top + 3, {{release: false}}); return true; }})()")
    deep = ui.js("[document.querySelector('.drop-line').getBoundingClientRect().left, document.querySelector('#outline').getBoundingClientRect().left]")
    ui.js(f"(() => {{ const to = {li}[1].getBoundingClientRect(); window.__dragMove(to.left + 60, to.top + 3); return true; }})()")
    shallow = ui.js("[document.querySelector('.drop-line').getBoundingClientRect().left, document.querySelector('#outline').getBoundingClientRect().left]")
    assert deep[0] - shallow[0] == 14 and shallow[0] - shallow[1] == 28 + 14
    ui.js(f"(() => {{ const to = {li}[1].getBoundingClientRect(); window.__dragUp(to.left + 60, to.top + 3); return true; }})()")
    ui.wait(150)
    moved = text(ui)
    assert order(moved, '"The mill"', "Intro", "=== A beam", "Beam text.", "=== Upstairs", "Upstairs text.", "==== The loft", "=== Downstairs")
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == SUBS
    # Into the other scene: Upstairs (with its section) dragged below The crypt in the outline.
    ui.js(f"(() => {{ const lis = {li}; const to = lis[6].getBoundingClientRect(); window.__drag(lis[1], to.left + 60, to.bottom - 2); return true; }})()")
    ui.wait(150)
    assert order(text(ui), '"The chapel"', "=== The crypt", "=== Upstairs", "==== The loft", "===== A beam")
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == SUBS
    # Folding Upstairs hides its section in the editor and in the outline; the text is unchanged.
    ui.run("window.__scriptorum.toggleCollapse('u:1')")
    ui.js(FIND)
    assert ui.js("window.__blk('Upstairs text.').classList.contains('collapse-hidden')") is True
    assert ui.js("window.__blk('The loft').classList.contains('collapse-hidden')") is True
    assert ui.js("window.__blk('Downstairs').classList.contains('collapse-hidden')") is False
    hidden = ui.js(f"{li}.filter(l => l.classList.contains('collapse-hidden')).map(l => l.querySelector('.outline-item').textContent)")
    assert hidden == ["The loft", "A beam"]
    assert text(ui) == SUBS
    ui.run("window.__scriptorum.toggleCollapse('u:1')")


@pytest.mark.ui
def test_T_UI_36_older_adventure_offers_raise(ui):
    """T-UI-36: an older adventure with ==== directly under a scene opens
    unchanged; the warnings panel names it and offers to raise it."""
    path = pack_sample("example-jattens-skuld", ui.folder)
    json.loads(ui.window.bridge.openPath(str(path)))
    ui.run("window.__scriptorum.refresh()")
    original = sample_text("example-jattens-skuld")
    assert text(ui) == original
    ui.wait_until(lambda: any("skips a level" in w["text"] for w in ui.state()["warnings"]), 40)
    ui.run("window.__scriptorum.openWarnings()")
    buttons = ui.js("[...document.querySelectorAll('#warnings-list .warning-fix')].map(b => b.textContent)")
    assert buttons == ["Raise to Sub-heading 1", "Raise to Sub-heading 1"]
    before = history(ui)
    ui.js("document.querySelector('#warnings-list .warning-fix').click(); true")
    ui.wait(400)
    now = text(ui)
    assert "\n=== Vad Gerda vet\n" in now and now.replace("\n=== Vad Gerda vet\n", "\n==== Vad Gerda vet\n") == original
    assert history(ui) == before + 1


# --- T-UI-37 the grip strip and Scriptorum's own dragging --------------------------------------

@pytest.mark.ui
def test_T_UI_37_grip_strip_and_own_dragging(ui):
    """T-UI-37: on the example adventure, the grip is a strip down the
    block's left side touching it, with a hand pointer; a drag shows a faint
    copy and a drop line; where it may not go there is no line, the pointer
    says not allowed and letting go moves nothing; the editor scrolls near
    its edge; Esc and letting go outside cancel; a move is one undo step; no
    system drag-and-drop is used and the window keeps responding."""
    path = pack_sample("example-jattens-skuld", ui.folder)
    json.loads(ui.window.bridge.openPath(str(path)))
    ui.run("window.__scriptorum.refresh()")
    ui.js(DRAG_HELPERS)
    ui.js(FIND)
    original = text(ui)
    assert ui.js("document.querySelectorAll('[draggable=true]').length") == 0
    geometry = ui.js("""(() => { const s = document.querySelector('#visual .blk-paragraph'); s.scrollIntoView({block: 'center'});
        s.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        const g = s.querySelector(':scope > .grip-strip'); g.style.display = 'flex';
        const a = g.getBoundingClientRect(), b = s.getBoundingClientRect();
        const r = [a.width, a.right, b.left, a.height, b.height, getComputedStyle(g).cursor, g.textContent];
        g.style.display = ''; return r; })()""")
    width, right, left, height, block_height, cursor, glyph = geometry
    assert 18 <= width <= 24 and abs(right - left) <= 2 and abs(height - block_height) <= 1
    assert cursor == "grab" and glyph == "::"
    # Mid-drag: a faint copy follows the pointer and a line shows where it lands.
    para = "[...document.querySelectorAll('#visual .blk-paragraph')]"
    drag(ui, f"window.__strip({para}[0])", f"window.__over({para}[3], 'bottom')", release=False)
    state = ui.js("""(() => { const g = document.querySelector('.drag-ghost'); const l = document.querySelector('.drop-line');
        return [!!g, g && parseFloat(getComputedStyle(g).opacity), l && !l.classList.contains('hidden'), document.body.className]; })()""")
    assert state[0] and state[1] < 1 and state[2] and "dragging-block" in state[3]
    # Esc cancels with nothing moved.
    ui.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true})); true")
    assert ui.js("!document.querySelector('.drag-ghost') && !document.body.classList.contains('dragging-block')") is True
    ui.js("window.__dragUp(0, 0); true")
    assert text(ui) == original
    # A paragraph over a person card's list: not allowed, no line, the reason in the status bar.
    drag(ui, f"window.__strip({para}[0])",
         "(() => { const a = document.querySelector('#visual .el-card .el-children .add-row'); a.scrollIntoView({block: 'center'}); const r = a.getBoundingClientRect(); return [r.left + 90, r.top + r.height / 2]; })()",
         release=False)
    state = ui.js("[document.body.classList.contains('drag-not-allowed'), document.querySelector('.drop-line').classList.contains('hidden'), document.getElementById('st-flash').textContent]")
    assert state == [True, True, "A person card holds only Information."]
    ui.js("(() => { const a = document.querySelector('#visual .el-card .el-children .add-row').getBoundingClientRect(); window.__dragUp(a.left + 90, a.top + a.height / 2); return true; })()")
    assert text(ui) == original
    # Near the bottom edge the editor scrolls by itself.
    pane = "document.querySelector('.editor-pane')"
    ui.js(f"{pane}.scrollTop = 0; true")
    top = ui.js(f"{pane}.scrollTop")
    drag(ui, f"window.__strip({para}[0])", f"(() => {{ const r = {pane}.getBoundingClientRect(); return [r.left + 200, r.bottom - 10]; }})()", release=False)
    ui.wait(600)
    assert ui.js(f"{pane}.scrollTop") > top + 50
    # Letting go outside the editor (over the preview) cancels.
    ui.js("(() => { const r = document.getElementById('preview-pane').getBoundingClientRect(); window.__dragMove(r.left + 50, r.top + 200); window.__dragUp(r.left + 50, r.top + 200); return true; })()")
    ui.wait(150)
    assert text(ui) == original
    # A real move is one undo step, and the window keeps responding.
    before = history(ui)
    drag(ui, f"window.__strip({para}[0])", f"window.__over({para}[2], 'bottom')")
    assert text(ui) != original and history(ui) == before + 1
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == original
    assert ui.js("1 + 1") == 2


# --- T-UI-38 into and out of containers --------------------------------------------------------

BOXES = """#scene(title: "Containers")[
#box(title: "Rules")[
Box text.
]

#table(
  columns: 2,
  table.header([Roll], [Result]),
  [1], [Nothing],
)

- First item
- Second item

#person(name: "Agda")[
]

#box(title: "Empty")[
]

#read-aloud[Fog over the water.]
]
"""

TABLE = """#table(
  columns: 2,
  table.header([Roll], [Result]),
  [1], [Nothing],
)"""


@pytest.mark.ui
def test_T_UI_38_drag_into_and_out_of_containers(ui):
    """T-UI-38: a table dragged into a Box over its contents lands inside;
    over the Box's own frame it lands just after it; an empty Box shows Drop
    here; each move is one undo step and the block's text is untouched."""
    load(ui, BOXES)
    rules = "window.__el('box', 0)"
    table = "window.__el('tbl-edit') || document.querySelector('#visual .tbl-edit').closest('section.blk')"
    table = "document.querySelector('#visual .tbl-edit').closest('section.blk')"
    before = history(ui)
    drag(ui, f"window.__strip({table})", "window.__over(window.__blk('Box text.'), 'bottom')")
    inside = text(ui)
    assert order(inside, '#box(title: "Rules")[', "Box text.", "#table(", "]\n\n- First") and TABLE in inside
    assert history(ui) == before + 1
    # Out again: over the Box's own frame at its left edge, below the middle: just after the Box.
    drag(ui, f"window.__strip({table})", f"(() => {{ const b = {rules}; b.scrollIntoView({{block: 'center'}}); const r = b.getBoundingClientRect(); return [r.left + 3, r.bottom - 4]; }})()")
    assert text(ui) == BOXES
    # An empty Box shows Drop here while a block is dragged, and takes the block.
    ui.js("window.__el('box', 1).scrollIntoView({block: 'center'}); true")
    drag(ui, f"window.__strip({table})", "[0, 0]", release=False)
    shown = ui.js("(() => { const h = window.__el('box', 1).querySelector('.drop-here'); return getComputedStyle(h).display !== 'none' && h.textContent; })()")
    assert shown == "Drop here"
    ui.js("(() => { const r = window.__el('box', 1).querySelector('.drop-here').getBoundingClientRect(); window.__dragMove(r.left + 90, r.top + r.height / 2); window.__dragUp(r.left + 90, r.top + r.height / 2); return true; })()")
    ui.wait(150)
    assert order(text(ui), '#box(title: "Empty")[', "#table(", "#read-aloud") and TABLE in text(ui)
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == BOXES
    # A person card can go into a Box; a Box into a person card cannot.
    drag(ui, "window.__strip(window.__el('person'))", "window.__over(window.__blk('Box text.'), 'bottom')")
    assert order(text(ui), '#box(title: "Rules")[', "Box text.", '#person(name: "Agda")', "#table(")
    ui.run("window.__scriptorum.undo()")
    drag(ui, f"window.__strip({rules})",
         "(() => { const a = window.__el('person').querySelector('.el-children .add-row'); a.scrollIntoView({block: 'center'}); const r = a.getBoundingClientRect(); return [r.left + 90, r.top + r.height / 2]; })()")
    assert text(ui) == BOXES
    assert ui.js("document.getElementById('st-flash').textContent") == "A person card holds only Information."


@pytest.mark.ui
def test_T_UI_38_keys_at_container_edges(ui):
    """T-UI-38: Alt+→ moves a block into the container just above, at its
    end; Alt+← moves it out to just after its container; at the top or
    bottom of a container Alt+↑ / Alt+↓ and the ↑ ↓ buttons step out of it."""
    text_with_list_after_box = BOXES.replace(TABLE + "\n\n", "").replace("]\n\n- First item", "]\n\n- First item")
    load(ui, text_with_list_after_box)
    # A list is kept as a locked block in the editor; it moves like any block.
    listing = "[...document.querySelectorAll('#visual section.blk-locked')].find(s => s.textContent.includes('First item'))"
    original = text(ui)
    keydown(ui, f"{listing}.querySelector('.locked-code')", "ArrowRight", altKey=True)
    inside = text(ui)
    assert order(inside, '#box(title: "Rules")[', "Box text.", "- First item", "]\n\n#person")
    keydown(ui, f"{listing}.querySelector('.locked-code')", "ArrowLeft", altKey=True)
    assert text(ui) == original
    # At the top of the Box, Alt+↑ steps out to just before it.
    keydown(ui, "window.__blk('Box text.').querySelector('.rich')", "ArrowUp", altKey=True)
    assert order(text(ui), "Box text.", '#box(title: "Rules")[')
    ui.run("window.__scriptorum.undo()")
    ui.js(FIND)
    # At the bottom, the ↓ button steps out to just after it.
    ui.js("window.__blk('Box text.').querySelector(':scope > .blk-controls .icon-btn:nth-child(2)').click(); true")
    ui.wait(150)
    assert order(text(ui), '#box(title: "Rules")[\n]', "Box text.", "- First item")
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == original
    # Alt+→ with no container just above (the first block of the scene) says why.
    ui.js(FIND)
    keydown(ui, "window.__el('box', 0).querySelector('input')", "ArrowRight", altKey=True)
    assert text(ui) == original
    assert ui.js("document.getElementById('st-flash').textContent") == "There is no box, quote or other container just above to move it into."


# --- T-UI-39 Information and person cards ---------------------------------------------------------

@pytest.mark.ui
def test_T_UI_39_information_keeps_who_knows_it(ui):
    """T-UI-39: an Information line dragged into a codex person's card leaves
    Known by (the card says it now); dragged out it is a box again and the
    person is back in Known by; moved from one person's card to another's,
    the knowledge moves; out of a loose card, the status bar says the person
    no longer knows it. Each move is one undo step."""
    load(ui, '#scene(title: "Knowing")[\nText.\n]\n')
    bridge = ui.window.bridge
    lovisa = json.loads(bridge.createEntry(json.dumps({"type": "person", "title": "Lovisa"})))["id"]
    tore = json.loads(bridge.createEntry(json.dumps({"type": "person", "title": "Tore"})))["id"]
    start = f"""#scene(title: "Knowing")[
#information(known-by: ("{lovisa}",), variant: "secret")[She saw the boat.]

#card(entry: "{lovisa}")[
]

#card(entry: "{tore}")[
]

#person(name: "Agda")[
#information(variant: "public")[Agda runs the mill.]
]

Closing text.
]
"""
    bridge.session.set_chapter_text(0, start)
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.reloadAfterWorld ? window.__scriptorum.reloadAfterWorld() : null")
    ui.js(DRAG_HELPERS)
    ui.js(FIND)
    assert text(ui) == start
    info = "window.__blk('She saw the boat.')"
    into = lambda n: f"(() => {{ const a = window.__el('card', {n}).querySelector('.el-children .add-row'); a.scrollIntoView({{block: 'center'}}); const r = a.getBoundingClientRect(); return [r.left + 90, r.top + 4]; }})()"  # noqa: E731
    before = history(ui)
    drag(ui, f"window.__strip({info})", into(0))
    now = text(ui)
    assert f'#card(entry: "{lovisa}")[\n#information(variant: "secret")[She saw the boat.]' in now
    assert lovisa not in now.split("#card")[0]
    assert history(ui) == before + 1
    # Dragged out: a free-standing box again, and Lovisa knows it.
    ui.js(FIND)
    drag(ui, f"window.__strip({info})", "window.__over(window.__blk('Closing text.'), 'bottom')")
    now = text(ui)
    assert f'#information(known-by: ("{lovisa}",), variant: "secret")[She saw the boat.]' in now
    assert order(now, "Closing text.", "She saw the boat.")
    ui.run("window.__scriptorum.undo()")
    ui.js(FIND)
    # From Lovisa's card to Tore's: the knowledge moves with it.
    drag(ui, f"window.__strip({info})", into(1))
    now = text(ui)
    assert f'#card(entry: "{tore}")[\n#information(variant: "secret")[She saw the boat.]' in now
    assert lovisa not in now.split(f'#card(entry: "{lovisa}")')[1].split("#card")[0] or "known-by" not in now
    assert "known-by" not in now
    # Out of a loose card: the status bar says Agda no longer knows it.
    ui.js(FIND)
    drag(ui, "window.__strip(window.__blk('Agda runs the mill.'))", "window.__over(window.__blk('Closing text.'), 'bottom')")
    now = text(ui)
    assert order(now, '#person(name: "Agda")[', "Closing text.", "Agda runs the mill.")
    assert ui.js("document.getElementById('st-flash').textContent") == "Agda no longer knows this. To keep it, add them under Known by."
    assert '#information(variant: "public")[Agda runs the mill.]' in now
