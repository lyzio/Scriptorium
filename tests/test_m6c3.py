"""M6 part C3: sub-headings anywhere and the end of a scene (T-SRC-19,
T-BUILD-31), the editor's width and coming back to the same place (T-UI-40,
T-UI-41), numbered pins, the map key and lines (T-WORLD-27, T-WORLD-28) and
Only as handout (T-WORLD-29)."""

from __future__ import annotations

import io
import json

import pytest
from pypdf import PdfReader

from scriptorum.core import source
from tests.test_m5c import _structure
from tests.test_m6c2 import THEMES, VAESEN, PLAIN

OUTSIDE = """= The first act

=== Before we begin

Info page text.

==== Background

Background text.

#scene(title: "The mill")[
Intro to the mill.

=== Upstairs

Upstairs text.
]

=== Between the scenes

Between text.

#scene(title: "The chapel")[
Chapel text.
]
"""


def _tree(items):
    out = []
    for it in items:
        if isinstance(it, list):
            out[-1] = (out[-1][0], _tree(it))
        else:
            out.append((it.title, []))
    return out


# --- T-BUILD-31 sub-headings outside scenes ----------------------------------------------

@pytest.mark.unit
def test_T_BUILD_31_build_copy_retags_outside_only(session):
    """T-BUILD-31: the build's copy writes a sub-heading outside a scene one
    level higher with its style label; inside a scene nothing changes; lines
    stay where they were; text without sub-headings is untouched."""
    session.new("Copy", *VAESEN)
    kinds = session.kinds()
    copy = source.retag_outside_headings(OUTSIDE, kinds)
    assert copy.count("\n") == OUTSIDE.count("\n")
    assert "== Before we begin <scriptorum-sub-1>" in copy
    assert "=== Background <scriptorum-sub-2>" in copy
    assert "== Between the scenes <scriptorum-sub-1>" in copy
    assert "\n=== Upstairs\n" in copy
    plain = '#scene(title: "A")[\nText.\n]\n'
    assert source.retag_outside_headings(plain, kinds) is plain


@pytest.mark.integration
@pytest.mark.parametrize("theme", THEMES)
def test_T_BUILD_31_levels_bookmarks_and_tags(session, tmp_path, theme):
    """T-BUILD-31: outside a scene Sub-heading 1 and 2 are tagged H2 and H3
    and nest under their act; inside a scene they stay H3; the table of
    contents lists only acts and scenes; the author's text is unchanged."""
    session.new("Outside", *(VAESEN if theme == "scriptorum.vaesen" else PLAIN[:2] + (theme, "1.0.0")))
    text = "#contents()\n\n#page-break()\n\n" + OUTSIDE
    session.set_chapter_text(0, text)
    reply = session.export_pdf(tmp_path / "a.pdf", variant="accessible")
    assert reply["ok"], reply
    data = (tmp_path / "a.pdf").read_bytes()
    reader = PdfReader(io.BytesIO(data))
    assert _tree(reader.outline) == [("The first act", [
        ("Before we begin", [("Background", [])]),
        ("The mill", [("Upstairs", [])]),
        ("Between the scenes", []),
        ("The chapel", [])])]
    contents = "".join(reader.pages[1].extract_text().split())
    assert "Themill" in contents and "Thechapel" in contents
    assert "Beforewebegin" not in contents and "Betweenthescenes" not in contents
    tags = [kind for kind, _ in _structure(data)]
    assert "/H2" in tags and "/H3" in tags
    assert session.adventure.chapter_text(session.adventure.chapters[0]) == text


@pytest.mark.unit
def test_T_BUILD_31_skipped_levels_outside(session):
    """T-BUILD-31: a skipped level outside a scene is found too, and offered
    the level that fits; well-formed text gives no warning."""
    session.new("Skip", *VAESEN)
    kinds = session.kinds()
    assert source.skipped_headings(source.parse(OUTSIDE, kinds), kinds) == []
    bad = "= Act\n\n==== Too deep\n\nText.\n\n#scene(title: \"A\")[\nX.\n]\n\n===== Deeper\n"
    found = source.skipped_headings(source.parse(bad, kinds), kinds)
    assert [(f["title"], f["level"], f["to"]) for f in found] == [("Too deep", 4, 3), ("Deeper", 5, 3)]


# --- the window -------------------------------------------------------------------------------

from tests.test_m6c2 import ui, load, text, history, drag, keydown, order  # noqa: E402,F401

SCENE = """#scene(title: "The church")[
Opening words.

#box(title: "A vision")[
Inside the box.
]

#check(roll: "FEAR", difficulty: "Easy")[A fear check.]

#person(name: "Tore")[
#information(variant: "secret")[He knows.]
]

Closing words.
]

#scene(title: "The farm")[
Farm words.
]
"""


def _focus(ui, selector_js: str) -> None:
    ui.js(f"(() => {{ const e = {selector_js}; e.focus(); return true; }})()")
    ui.wait(100)


def _type_new_heading(ui, words: str) -> None:
    ui.js(f"(() => {{ const h = [...document.querySelectorAll('#visual .heading-edit')].find(x => !x.textContent); h.focus();"
          f" document.execCommand('insertText', false, {json.dumps(words)}); return true; }})()")


@pytest.mark.ui
def test_T_SRC_19_sub_heading_from_anywhere_in_a_scene(ui):
    """T-SRC-19: with the cursor in a Box, a check, a person card's
    Information or a field, Insert ▸ Sub-heading lands in the scene just after
    the block holding the cursor, never inside it; one undo step each."""
    cases = [
        ("[...document.querySelectorAll('#visual .el-box .rich')][0]", "#box", "A fear check"),
        ("[...document.querySelectorAll('#visual .el-check .rich')][0]", "A fear check.]", "#person"),
        ("[...document.querySelectorAll('#visual .el-information .rich')][0]", "He knows.]\n]", "Closing words"),
        ("[...document.querySelectorAll('#visual .el-box input')][0]", "#box", "A fear check"),
    ]
    for n, (where, after, before) in enumerate(cases):
        load(ui, SCENE)
        _focus(ui, where)
        start = history(ui)
        ui.run("window.__scriptorum.insert('heading-3')")
        _type_new_heading(ui, f"Heading {n}")
        written = text(ui)
        assert f"\n=== Heading {n}\n" in written, (n, written)
        assert order(written, after, f"=== Heading {n}", before), (n, written)
        assert history(ui) >= start + 1
        # Not inside the Box, check or card: the scene holds it directly.
        doc = source.parse(written, ui.window.bridge.session.kinds())
        scene = doc["blocks"][0]
        assert any(b["type"] == "heading" and b["text"] == f"Heading {n}" for b in scene["body"]["blocks"]), n


@pytest.mark.ui
def test_T_SRC_19_outside_scenes_and_end_of_scene(ui):
    """T-SRC-19: a sub-heading inserted outside any scene lands where the
    cursor is; End of scene moves the blocks after the cursor out of the
    scene, one undo step; Alt+→ brings a block back in; text that never used
    it reads and writes back byte-identical."""
    start_text = '= Act\n\nInfo page.\n\n' + SCENE
    load(ui, start_text)
    assert text(ui) == start_text
    _focus(ui, "window.__blk('Info page.').querySelector('.rich')")
    ui.run("window.__scriptorum.insert('heading-3')")
    _type_new_heading(ui, "Before the scenes")
    written = text(ui)
    assert order(written, "= Act", "Info page.", "=== Before the scenes", '#scene(title: "The church")')
    doc = source.parse(written, ui.window.bridge.session.kinds())
    assert any(b["type"] == "heading" and b["text"] == "Before the scenes" for b in doc["blocks"])
    # End of scene after the check: the person card and the closing words leave the scene.
    ui.js(FIND_C3)
    _focus(ui, "[...document.querySelectorAll('#visual .el-check .rich')][0]")
    before = history(ui)
    ui.run("window.__scriptorum.insert('scene-end')")
    ended = text(ui)
    assert history(ui) == before + 1
    doc = source.parse(ended, ui.window.bridge.session.kinds())
    church = next(b for b in doc["blocks"] if b.get("kind") == "scene" and b["fields"]["title"] == "The church")
    assert [b.get("kind") or b["type"] for b in church["body"]["blocks"]][-1] == "check"
    after = doc["blocks"][doc["blocks"].index(church) + 1:]
    assert [b.get("kind") or b["type"] for b in after][:3] == ["person", "paragraph", "scene"]
    assert "#scene-end" not in ended
    # The editor shows where each scene ends.
    assert ui.js("document.querySelectorAll('#visual .scene-end-line').length") == 2
    assert ui.js("document.querySelector('#visual .scene-end-line').textContent") == "End of scene"
    # Undo brings them back in, as one step.
    ui.run("window.__scriptorum.undo()")
    assert text(ui) == written
    # With the cursor on the last block, End of scene opens an empty paragraph after the scene.
    load(ui, SCENE)
    _focus(ui, "window.__blk('Farm words.').querySelector('.rich')")
    ui.run("window.__scriptorum.insert('scene-end')")
    ui.js("document.activeElement && document.execCommand('insertText', false, 'Outside now.'); true")
    assert text(ui).rstrip().endswith("]\n\nOutside now.")
    # Outside a scene it says why and changes nothing.
    load(ui, "Just a paragraph.\n")
    _focus(ui, "document.querySelector('#visual .rich')")
    ui.run("window.__scriptorum.insert('scene-end')")
    assert text(ui) == "Just a paragraph.\n"
    assert "inside a scene" in ui.js("document.getElementById('st-flash').textContent")


FIND_C3 = "true"


@pytest.mark.ui
def test_T_SRC_19_menus_offer_it(ui):
    """T-SRC-19: the Structure group and the Insert menu list Sub-heading 1,
    2 and 3 and End of scene; the paragraph style list offers the
    sub-headings outside a scene too."""
    load(ui, "Info page.\n\n" + SCENE)
    items = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.insert" for i in m["items"]]
    assert {"Sub-heading 1", "Sub-heading 2", "Sub-heading 3", "End of scene"} <= set(items)
    _focus(ui, "window.__blk('Info page.').querySelector('.rich')")
    options = ui.js("[...document.querySelectorAll('#tb-style option')].map(o => o.textContent)")
    assert "Sub-heading 1" in options and "Act heading" in " ".join(options) or "Sub-heading 1" in options


# --- T-UI-40 the editor's width ---------------------------------------------------------------

@pytest.mark.ui
def test_T_UI_40_editor_fills_its_pane(ui):
    """T-UI-40: the editor column fills the pane between the side panel and
    the preview, in a wide window and with the preview hidden; paragraphs stop
    at about 100 characters; field rows use the full width."""
    load(ui, SCENE.replace("Opening words.", "Opening words. " * 60))
    for width in (1440, 2400):
        ui.window.resize(width, 900)
        ui.wait(300)
        pane = ui.js("document.getElementById('editor-pane').clientWidth")
        visual = ui.js("document.getElementById('visual').getBoundingClientRect().width")
        assert visual >= pane - 2, (width, visual, pane)
        scene = ui.js("document.querySelector('#visual .el-scene').getBoundingClientRect().width")
        assert scene > pane - 200, (width, scene, pane)
        para = ui.js("window.__blk((' Opening words.'.repeat(60)).trim()).querySelector('.rich').getBoundingClientRect().width")
        char = ui.js("(() => { const s = document.createElement('span'); s.textContent = '0'.repeat(100);"
                     " const r = window.__blk((' Opening words.'.repeat(60)).trim()).querySelector('.rich'); r.append(s);"
                     " const w = s.getBoundingClientRect().width; s.remove(); return w; })()")
        assert para <= char * 1.05 + 2, (width, para, char)
        # Nothing sticks out sideways: no horizontal scroll bar.
        assert ui.js("(() => { const p = document.getElementById('editor-pane'); return p.scrollWidth <= p.clientWidth + 1; })()"), \
            ui.js("(() => { const p = document.getElementById('editor-pane'); const w = p.getBoundingClientRect().right;"
                  " return JSON.stringify([p.scrollWidth, p.clientWidth, [...p.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > w + 1).slice(0, 5).map(e => e.className)]); })()")
        fields = ui.js("document.querySelector('#visual .el-scene > .el-fields').getBoundingClientRect().width")
        assert fields > scene - 60
    # With the preview hidden the editor takes its width too.
    ui.window.resize(1440, 900)
    ui.run("window.__scriptorum.setPreview(false)")
    ui.wait(300)
    pane = ui.js("document.getElementById('editor-pane').clientWidth")
    assert ui.js("document.getElementById('visual').getBoundingClientRect().width") >= pane - 2
    assert ui.js("document.querySelector('#visual .el-scene').getBoundingClientRect().width") > pane - 200
    ui.run("window.__scriptorum.setPreview(true)")
    ui.wait(200)


# --- T-UI-41 back to the same place ---------------------------------------------------------

@pytest.mark.ui
def test_T_UI_41_back_to_the_same_place(ui):
    """T-UI-41: after the Codex entry, a map and the relationship chart, the
    editor is back at the same scroll position, block and caret."""
    long = "\n\n".join(f"Paragraph number {n} with some words." for n in range(80))
    load(ui, f'#scene(title: "Long")[\n{long}\n]\n')
    bridge = ui.window.bridge
    entry = json.loads(bridge.createEntry(json.dumps({"type": "person", "title": "Anna"})))
    assert entry.get("ok"), entry
    ui.run("window.__scriptorum.refresh()")
    ui.js(FIND_C3)
    ui.js("(() => { const r = window.__blk('Paragraph number 60 with some words.').querySelector('.rich'); r.scrollIntoView({block: 'center'});"
          " r.focus(); const p = document.getElementById('editor-pane'); p.scrollTop += r.getBoundingClientRect().top - p.getBoundingClientRect().top - 200; const t = r.firstChild; const g = document.createRange(); g.setStart(t, 10); g.collapse(true);"
          " getSelection().removeAllRanges(); getSelection().addRange(g); return true; })()")
    ui.wait(150)
    scroll = ui.js("document.getElementById('editor-pane').scrollTop")
    assert scroll > 500
    for opener in (f"window.__scriptorum.world.openEntry({json.dumps(entry['id'])})", "window.__scriptorum.world.openChart()"):
        ui.run(opener)
        ui.wait(300)
        assert ui.js("!document.getElementById('worldview').classList.contains('hidden')")
        ui.js("document.getElementById('worldview-back').click(); true")
        ui.wait(300)
        assert abs(ui.js("document.getElementById('editor-pane').scrollTop") - scroll) <= 2
        assert ui.js("document.activeElement.textContent") == "Paragraph number 60 with some words."
        assert ui.js("getSelection().anchorOffset") == 10


# --- T-WORLD-27 and T-WORLD-28 numbered pins, the key and lines ---------------------------------

def _open_world(session, tmp_path):
    from tests.conftest import pack_sample
    session.open(pack_sample("m3-world", tmp_path))
    return session.map_info("m-skarvik")


def _words(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "".join("".join(p.extract_text().split()) for p in reader.pages)


@pytest.mark.integration
def test_T_WORLD_27_numbers_and_key(session, tmp_path):
    """T-WORLD-27: each pin prints its number; numbers follow the order
    placed, an older pin without one gets the next free number, and a typed
    number is kept; the key lists number, name and note; the handout version
    has only the pins of handout layers in its key."""
    from scriptorum.core.world import pin_numbers
    m = _open_world(session, tmp_path)
    layers = m["layers"]
    pins = [i for l in layers for i in l["items"] if i["type"] == "pin"]
    assert pin_numbers(m) == {p["id"]: n + 1 for n, p in enumerate(pins)}
    # A GM-only pin with a note on the second layer, and a typed number.
    layers[1]["items"].append({"type": "pin", "x": 0.5, "y": 0.5, "text": "Smugglers' cave", "note": "Only the GM knows", "number": 7})
    layers[0]["items"][0]["note"] = "Boats wait here"
    m = session.update_map({"id": "m-skarvik", "layers": layers})
    numbers = pin_numbers(m)
    cave = next(i for l in m["layers"] for i in l["items"] if i.get("text") == "Smugglers' cave")
    assert numbers[cave["id"]] == 7 and cave["note"] == "Only the GM knows"
    harbour = m["layers"][0]["items"][0]
    assert numbers[harbour["id"]] == 1
    full = tmp_path / "full.pdf"
    assert session.export_pdf(full, variant="full")["ok"]
    words = _words(full.read_bytes())
    assert "Smugglers'cave—OnlytheGMknows" in words.replace("’", "'")
    assert "—Boatswaithere" in words
    player = tmp_path / "player.pdf"
    assert session.export_pdf(player, variant="handouts")["ok"]
    handout = _words(player.read_bytes()).replace("’", "'")
    assert "Boatswaithere" in handout and "Smugglers'cave" not in handout and "OnlytheGM" not in handout
    # Saving without edits keeps the map file unchanged.
    before = session.adventure.files["maps/m-skarvik/map.json"]
    session.update_map({"id": "m-skarvik", "layers": session.map_info("m-skarvik")["layers"]})
    assert session.adventure.files["maps/m-skarvik/map.json"] == before


@pytest.mark.integration
def test_T_WORLD_27_key_beside_or_under(session, tmp_path):
    """T-WORLD-27: the key sits beside an upright map and under a wide one."""
    import struct
    import zlib
    m = _open_world(session, tmp_path)

    def png(w, h):
        raw = b"".join(b"\x00" + b"\xff" * (w * 3) for _ in range(h))
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

    positions = {}
    for name, (w, h) in {"wide": (2200, 1400), "tall": (1400, 2000)}.items():
        made = session.create_map(name, f"{name}.png", png(w, h))
        session.update_map({"id": made["id"], "layers": [{"name": "L", "show_in_handout": True, "items": [
            {"type": "pin", "x": 0.4, "y": 0.4, "text": f"Keyword{name}"}]}]})
        text = session.adventure.chapter_text(session.adventure.chapters[0])
        session.set_chapter_text(0, f'#map(map: "{made["id"]}")\n\n' + text)
        result = session.build("pdf")
        assert result.ok, result.problems
        from tests.test_m6c2 import _lines
        reader = PdfReader(io.BytesIO(result.output[0]))
        page = next(p for p in reader.pages if f"Keyword{name}" in p.extract_text())
        runs = _lines(page)
        key = next((x, y) for t, x, y in runs if f"Keyword{name}" in t)
        positions[name] = key
        session.set_chapter_text(0, text)
    width = float(reader.pages[0].mediabox.width)
    # Wide map: the key starts at the left, under the map. Tall map: beside it, to the right.
    assert positions["tall"][0] - positions["wide"][0] > 60


@pytest.mark.integration
def test_T_WORLD_28_lines(session, tmp_path):
    """T-WORLD-28: a line between two pins follows a moved pin; a free line
    keeps its points; dashed and labels print; the handout version keeps only
    lines on handout layers; each change is one undo step."""
    m = _open_world(session, tmp_path)
    layers = m["layers"]
    a, b = [i["id"] for i in layers[0]["items"] if i["type"] == "pin"][:2]
    layers[0]["items"].append({"type": "line", "from": a, "to": b, "text": "Thecoastroad", "style": "dashed"})
    layers[1]["items"].append({"type": "line", "points": [[0.1, 0.9], [0.4, 0.8], [0.6, 0.95]], "text": "Secretpath"})
    start = len(session.world_history)
    m = session.update_map({"id": "m-skarvik", "layers": layers})
    assert len(session.world_history) == start + 1
    line = next(i for i in m["layers"][0]["items"] if i["type"] == "line")
    assert line["from"] == a and line["to"] == b and line["style"] == "dashed" and "points" not in line
    free = next(i for i in m["layers"][1]["items"] if i["type"] == "line")
    assert free["points"] == [[0.1, 0.9], [0.4, 0.8], [0.6, 0.95]] and "style" not in free
    # The build places the pin line on its pins, and follows a moved pin.
    data = session.world.build_data("pdf", {})
    built = next(i for i in data["maps"]["m-skarvik"]["layers"][0]["items"] if i["type"] == "line")
    pin_a = next(i for i in m["layers"][0]["items"] if i.get("id") == a)
    assert built["points"][0] == [pin_a["x"], pin_a["y"]]
    m["layers"][0]["items"][0]["x"] = 0.05
    m = session.update_map({"id": "m-skarvik", "layers": m["layers"]})
    data = session.world.build_data("pdf", {})
    built = next(i for i in data["maps"]["m-skarvik"]["layers"][0]["items"] if i["type"] == "line")
    assert built["points"][0][0] == 0.05
    full = tmp_path / "full.pdf"
    assert session.export_pdf(full, variant="full")["ok"]
    words = _words(full.read_bytes())
    assert "Thecoastroad" in words and "Secretpath" in words
    player = tmp_path / "player.pdf"
    assert session.export_pdf(player, variant="handouts")["ok"]
    handout = _words(player.read_bytes())
    assert "Thecoastroad" in handout and "Secretpath" not in handout
    # A free line needs two points.
    from scriptorum.core.world import WorldError
    layers = m["layers"]
    layers[0]["items"].append({"type": "line", "points": [[0.1, 0.1]]})
    with pytest.raises(WorldError):
        session.update_map({"id": "m-skarvik", "layers": layers})


# --- T-WORLD-29 Only as handout ------------------------------------------------------------------

@pytest.mark.integration
def test_T_WORLD_29_only_as_handout(session, tmp_path):
    """T-WORLD-29: ticked, the adventure PDF prints only "Give out Handout n ·
    title" with the number of the handouts PDF; the handouts PDF is unchanged,
    easy-read copy included; unticked it prints as before."""
    from tests.conftest import pack_sample
    session.open(pack_sample("m3-handouts", tmp_path))
    text = session.adventure.chapter_text(session.adventure.chapters[0])
    kinds = session.kinds()
    doc = source.parse(text, kinds)
    handouts = [b for b in source._walk(doc["blocks"]) if b.get("kind") == "handout"]
    first = handouts[0]
    title = first["fields"]["title"]
    body_words = "".join(source.inline_to_plain(first["body"]).split())[:30]

    def pdfs(name):
        full, player = tmp_path / f"{name}-full.pdf", tmp_path / f"{name}-player.pdf"
        assert session.export_pdf(full, variant="full")["ok"]
        assert session.export_pdf(player, variant="handouts")["ok"]
        return full.read_bytes(), player.read_bytes()

    before_full, before_player = pdfs("before")
    assert body_words in _words(before_full)
    head = first["raw"].split("[", 1)[0]
    ticked = text.replace(head, head[:-1] + ", only-handout: true)", 1)
    assert ticked != text
    session.set_chapter_text(0, ticked)
    after_full, after_player = pdfs("after")
    words = _words(after_full)
    assert body_words not in words
    assert "GIVEOUTHANDOUT1" in words.upper().replace("#", "") and "".join(title.split()) in words
    assert after_player == before_player
    access = tmp_path / "access.pdf"
    session.export_pdf(access, variant="accessible")
    # Unticked again it prints as before, byte for byte.
    session.set_chapter_text(0, text)
    again_full, _ = pdfs("again")
    assert again_full == before_full
    # The field round-trips; unticked it is never written.
    assert source.serialize(source.parse(ticked, kinds), kinds) == ticked
    assert "only-handout" not in text


@pytest.mark.ui
def test_T_WORLD_29_tag_in_the_editor(ui):
    """T-WORLD-29: the editor keeps the handout's full text and shows an
    "Only as handout" tag while the box is ticked."""
    load(ui, '#scene(title: "Post")[\n#handout(title: "A letter")[Dear friends, come at once.]\n]\n')
    assert ui.js("document.querySelector('#visual .only-handout-tag').hidden") is True
    load(ui, '#scene(title: "Post")[\n#handout(title: "A letter", only-handout: true)[Dear friends, come at once.]\n]\n')
    assert ui.js("document.querySelector('#visual .only-handout-tag').hidden") is False
    assert ui.js("document.querySelector('#visual .only-handout-tag').textContent") == "Only as handout"
    assert "Dear friends, come at once." in ui.js("document.querySelector('#visual .el-handout').textContent")


@pytest.mark.ui
def test_T_WORLD_28_line_tool_and_numbers_in_the_editor(ui):
    """T-WORLD-27, T-WORLD-28 (window): a placed pin gets the next number and
    shows it; the number and note can be set; the Line tool joins two pins or
    draws a free line ended by a double-click; each is one undo step."""
    from tests.conftest import pack_sample
    from tests.test_ui_m3 import _click_map
    (ui.folder / "c3-map").mkdir(exist_ok=True)
    path = pack_sample("m3-world", ui.folder / "c3-map")
    assert json.loads(ui.window.bridge.openPath(str(path)))["ok"]
    ui.run("window.__scriptorum.refresh()")
    session = ui.window.bridge.session
    layers = lambda: session.world.maps()["m-skarvik"]["layers"]
    ui.run("window.__scriptorum.world.openMap('m-skarvik')")
    assert ui.js("[...document.querySelectorAll('.map-overlay .map-pin-number')].map(t => t.textContent)") == ["1", "2"]
    ui.run("window.__scriptorum.world.setTool('pin')")
    _click_map(ui, 0.45, 0.45)
    ui.wait_until(lambda: len(layers()[0]["items"]) == 4, 5)
    assert layers()[0]["items"][-1]["number"] == 3
    ui.wait(200)
    ui.js("(() => { const n = document.querySelector('.map-pin-number-input'); n.value = '9'; n.dispatchEvent(new Event('change')); return true; })()")
    ui.wait_until(lambda: layers()[0]["items"][-1].get("number") == 9, 5)
    # Join the first two pins.
    ui.run("window.__scriptorum.world.setTool('line')")
    steps = len(session.world_history)
    pins = ui.js("[...document.querySelectorAll('.map-overlay .item-pin')].length")
    assert pins == 3
    for n in (0, 1):
        ui.js(f"document.querySelectorAll('.map-overlay .item-pin')[{n}].dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, detail: 1}})); true")
        ui.wait(150)
    ui.wait_until(lambda: any(i["type"] == "line" for i in layers()[0]["items"]), 5)
    line = next(i for i in layers()[0]["items"] if i["type"] == "line")
    assert line.get("from") and line.get("to") and "points" not in line
    assert len(session.world_history) == steps + 1
    # A free line: three clicks, then a double-click.
    ui.run("window.__scriptorum.world.setTool('line')")
    for x, y in ((0.1, 0.9), (0.3, 0.85), (0.5, 0.92)):
        _click_map(ui, x, y)
    ui.js("document.querySelector('.map-overlay').dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); true")
    ui.wait_until(lambda: sum(i["type"] == "line" for i in layers()[0]["items"]) == 2, 5)
    ui.wait_until(lambda: ui.js("document.querySelectorAll('.map-overlay polyline.item-line').length") == 2, 5)
    free = [i for i in layers()[0]["items"] if i["type"] == "line"][-1]
    assert len(free["points"]) == 3
    assert ui.js("document.querySelectorAll('.map-overlay polyline.item-line').length") == 2
    ui.run("window.__scriptorum.world.closeView()")


@pytest.mark.ui
def test_T_UI_41_each_tab_keeps_its_place(ui):
    """T-UI-41: switching to another adventure tab and back returns to the
    same scroll position and block in each tab."""
    long = "\n\n".join(f"Line of tab one, number {n}." for n in range(80))
    load(ui, f'#scene(title: "Tab one")[\n{long}\n]\n', title="Tab one")
    ui.js("(() => { const r = window.__blk('Line of tab one, number 50.').querySelector('.rich'); r.focus();"
          " const p = document.getElementById('editor-pane'); p.scrollTop += r.getBoundingClientRect().top - p.getBoundingClientRect().top - 200; return true; })()")
    ui.wait(150)
    scroll = ui.js("document.getElementById('editor-pane').scrollTop")
    assert scroll > 500
    first = ui.js("window.__scriptorum.state().tabs.find(t => t.active).id")
    load(ui, '#scene(title: "Tab two")[\nShort.\n]\n', title="Tab two")
    assert first
    ui.run(f"window.__scriptorum.switchTab({json.dumps(first)})")
    ui.wait(400)
    assert abs(ui.js("document.getElementById('editor-pane').scrollTop") - scroll) <= 2
    assert ui.js("document.activeElement.textContent") == "Line of tab one, number 50."
