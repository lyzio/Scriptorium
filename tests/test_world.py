"""Test Plan group WORLD (and T-MOD-07): codex, maps and handouts, Milestone 3.

The sample m3-world uses every M3 function: codex entries of each built-in
type, mentions, cards and "see page" lines, Information known by two people,
a map with a GM-only layer that is also a handout, two handouts, the
relationship chart and the end-of-book material.
"""

from __future__ import annotations

import hashlib
import io
import re
import json
import struct
import zlib

import pytest
from pypdf import PdfReader

from tests.conftest import ROOT, sample_text

pytestmark = pytest.mark.integration

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


def _flat(data: bytes) -> list:
    """Page texts without spaces (labels are letter-spaced)."""
    return ["".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(data)).pages]


def _png(width: int, height: int) -> bytes:
    rows = b"".join(b"\x00" + bytes((230, 225, 210)) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _book(session):
    result = session.build("pdf")
    assert result.ok, [session.localize(e) for e in result.errors]
    return result, _flat(result.output[0])


def _players(session):
    result = session.build("pdf", player=True)
    assert result.ok, [session.localize(e) for e in result.errors]
    return result, _flat(result.output[0])


# --- codex (F3) -----------------------------------------------------------------------

def test_T_WORLD_01_rename_changes_every_printed_name(session, sample):
    """T-WORLD-01: renaming an entry changes every printed name; the adventure
    text does not change."""
    session.open(sample("m3-world"))
    before = session.adventure.chapter_text("text/chapter-01.typ")
    _, pages = _book(session)
    assert "Skärvikharbour" in "".join(pages)
    session.update_entry("c-skarvik-harbour", {"fields": {"name": "Skärvik old harbour"}})
    _, pages = _book(session)
    flat = "".join(pages)
    assert "Skärvikharbour" not in flat
    # mention, scene location, map pin, the index and Lovisa's links all follow
    assert flat.count("Skärvikoldharbour") >= 4
    assert session.adventure.chapter_text("text/chapter-01.typ") == before


def test_T_WORLD_02_delete_referenced_entry_refused(session, sample):
    """T-WORLD-02: deleting a referenced entry is refused, and the places are listed."""
    from scriptorum.core.world import WorldError

    session.open(sample("m3-world"))
    with pytest.raises(WorldError) as refused:
        session.delete_entry("c-nils-ek")
    places = refused.value.details["places"]
    assert {p["where"] for p in places} == {"text", "entry"}
    assert any(p.get("scene") == "The chapel" for p in places)
    assert any(p.get("title") == "Lovisa Berg" for p in places)
    assert "c-nils-ek" in session.world.entries()
    # An entry nobody uses can be deleted.
    new = session.create_entry("clue", "A loose thread")
    session.delete_entry(new["id"])
    assert new["id"] not in session.world.entries()


def test_T_WORLD_03_information_known_by_two_people(session, sample):
    """T-WORLD-03: Information linked to two people shows on both cards: in
    full where it is written, as a pointer with its page elsewhere."""
    session.open(sample("m3-world"))
    _, pages = _book(session)
    flat = "".join(pages)
    secret = "Thelightunderthewateristhelanternofthe"
    # As a pointer with its page on both people's cards ...
    pointer = secret + "Hoppet.→p.2"
    assert flat.count(pointer) == 2
    # ... and in full once, where it is written in the running text.
    assert flat.count(secret + "Hoppet.") - flat.count(pointer) == 1
    # Information written inside Lovisa's card prints in full there only.
    assert flat.count("Noboathasgoneoutsince") == 1


def test_T_WORLD_06_codex_types_folders_and_tags(session, sample):
    """T-WORLD-06: the built-in codex types; an author-defined type with every
    field kind; entries in folders with tags (F3.1–F3.3)."""
    session.open(sample("m3-world"))
    types = session.world.types()
    assert {"person", "place", "clue", "creature"} <= set(types)
    assert [f["name"] for f in types["place"]["fields"]] == ["name", "description"]
    assert [f["name"] for f in types["clue"]["fields"]] == ["name", "description"]
    assert "item" not in types and "faction" not in types  # L10, L11
    # Creature takes its fields from the game system's stat block (11.5).
    assert {"might", "fear", "banishment"} <= {f["name"] for f in types["creature"]["fields"]}
    own = session.save_codex_type({"name": "Ship", "fields": [
        {"label": "Name", "kind": "text"}, {"label": "Story", "kind": "rich"}, {"label": "Crew", "kind": "number"},
        {"label": "Picture", "kind": "image"}, {"label": "Captain", "kind": "link"},
        {"label": "Rig", "kind": "choice", "options": ["Brig", "Schooner"]}]})
    assert [f["kind"] for f in own["fields"]] == ["text", "rich", "number", "image", "link", "choice"]
    assert "codex/types/t-ship.json" in session.adventure.files
    ship = session.create_entry("t-ship", "The Hoppet", {"crew": "12", "captain": ["c-nils-ek"], "rig": "Brig"}, "Ships")
    assert ship["fields"] == {"name": "The Hoppet", "crew": 12, "captain": ["c-nils-ek"], "rig": "Brig"}
    session.update_entry(ship["id"], {"tags": ["wreck", " sea "]})
    entry = session.world.entry(ship["id"])
    assert (entry["folder"], entry["tags"]) == ("Ships", ["sea", "wreck"])
    # A card of the new type prints every filled-in field.
    session.set_chapter_text(0, session.adventure.chapter_text("text/chapter-01.typ")
                             + f'\n#card(entry: "{ship["id"]}")[\n]\n')
    _, pages = _book(session)
    assert "THEHOPPET" in "".join(pages) and "Crew:12" in "".join(pages)


def test_T_WORLD_07_mention_card_and_see_page(session, sample):
    """T-WORLD-07: a mention prints the name; a card the full entry; a "see
    page" line points to where the entry is described (F3.4)."""
    session.open(sample("m3-world"))
    _, pages = _book(session)
    flat = "".join(pages)
    assert "ThebellringsoverSkärvikharboureverynight." in flat
    assert "LOVISABERG" in flat and "Mood:Tiredandstubborn" in flat
    assert "ThebelloftheHoppet→p.3" in flat
    assert "MIGHT4" in flat  # the creature card prints its stat block


def test_T_WORLD_08_where_used(session, sample):
    """T-WORLD-08: backlinks, scenes and printed pages of an entry, and the
    "In this scene" panel (F3.6)."""
    session.open(sample("m3-world"))
    _book(session)
    info = session.entry_info("c-nils-ek")
    assert [b["id"] for b in info["backlinks"]] == ["c-lovisa-berg"]
    assert info["scenes"] == ["The harbour", "The chapel"]
    assert info["pages"] == [2, 3]
    panel = session.scene_entries(0, 6)  # inside "The harbour"
    assert panel["scene"] == "The harbour"
    assert [e["id"] for e in panel["entries"]] == [
        "c-skarvik-harbour", "c-lovisa-berg", "c-nils-ek", "c-the-hoppet-bell"]


def test_T_WORLD_10_relationship_chart(session, sample):
    """T-WORLD-10: the chart holds linked entries at their saved positions;
    a moved entry is saved; two builds give identical pages (F3.9, F7.8)."""
    session.open(sample("m3-world"))
    chart = session.chart()
    ids = {n["id"] for n in chart["nodes"]}
    assert ids == {"c-lovisa-berg", "c-nils-ek", "c-skarvik-harbour", "c-the-chapel"}
    assert {"from": "c-lovisa-berg", "to": "c-nils-ek"} in chart["edges"]
    session.set_chart_positions({"c-the-chapel": [0.9, 0.1]})
    node = next(n for n in session.chart()["nodes"] if n["id"] == "c-the-chapel")
    assert (node["x"], node["y"]) == (0.9, 0.1)
    first, _ = _book(session)
    second, _ = _book(session)
    assert hashlib.sha256(first.output[0]).digest() == hashlib.sha256(second.output[0]).digest()
    assert "RELATIONSHIPS" in "".join(_flat(first.output[0]))


def test_T_WORLD_11_end_of_book_switches(session, sample):
    """T-WORLD-11: the clue overview and the index are off by default; each
    prints at the end of the adventure PDF when switched on (F3.10)."""
    session.open(sample("m3-world"))
    _, pages = _book(session)
    assert pages[-2].upper().startswith("CLUEOVERVIEW") and pages[-1].upper().startswith("INDEXOFPEOPLEANDPLACES")
    assert "Appearsin:Scene1,Theharbour;Scene2,Thechapel" in pages[-2]
    assert "LovisaBerg" in pages[-1] and "Thechapel" in pages[-1]
    session.set_settings({"switches": {"clueOverview": False, "index": False}})
    _, off = _book(session)
    assert len(off) == len(pages) - 2 and "CLUEOVERVIEW" not in "".join(off).upper()
    session.new("Fresh", *GS, *TH)
    assert session.settings_info()["switches"] == {"clueOverview": False, "index": False, "easyRead": False}


def test_T_WORLD_12_handwriting_of_a_person(session, sample):
    """T-WORLD-12: a letter written by a person uses that person's
    handwriting font (F3.11, F6.7)."""
    session.open(sample("m3-world"))
    session.update_entry("c-nils-ek", {"fields": {"handwriting": "Quill Hand"}})
    result, _ = _players(session)
    # The font is not installed here, so Typst says it could not find it:
    # proof that the handout asked for that person's handwriting.
    assert any("quill hand" in (w.message or "").lower() for w in result.warnings)
    gm = session.build("pdf")
    assert not any("quill hand" in (w.message or "").lower() for w in gm.warnings)


def test_T_WORLD_13_upgrade_m2_text_fields(session, sample):
    """T-WORLD-13: text in M2 fields becomes codex links after the author
    confirms; declined values stay text; one undo step (F3.12)."""
    session.open(sample("m2-full"))
    assert session.offers_upgrade()
    found = session.upgrade_candidates()
    values = [(c["element"], c["field"], c["value"]) for c in found]
    assert values == [
        ("scene", "location", "Skärvik harbour, early morning"),
        ("scene", "present", "Harbour master Lovisa Berg"),
        ("person", "linked-to", "The harbour"),
        ("person", "linked-to", "the Hoppet"),
        ("scene", "location", "The fishermen's chapel on the hill"),
        ("scene", "present", "Sexton Nils Ek"),
        ("handout", "written-by", "Nils Ek"),
    ]
    before = session.adventure.chapter_text("text/chapter-01.typ")
    choices = [{"key": c["key"], "accept": c["value"] != "the Hoppet", "type": "place" if c["field"] == "linked-to" else c["type"]}
               for c in found]
    result = session.apply_upgrade(choices)
    assert result == {"linked": 6, "created": 6}
    text = session.adventure.chapter_text("text/chapter-01.typ")
    assert 'place: "c-skarvik-harbour-early-morning"' in text
    assert 'people: ("c-harbour-master-lovisa-berg",)' in text
    assert 'links: ("c-the-harbour",), linked-to: "the Hoppet"' in text  # the declined value stays text
    assert 'writer: "c-nils-ek"' in text and "written-by" not in text
    _, pages = _book(session)
    assert "LOCATION:SKÄRVIKHARBOUR,EARLYMORNING" in "".join(pages).upper()
    assert session.world_undo()
    assert session.adventure.chapter_text("text/chapter-01.typ") == before
    assert session.world.entries() == {}


# --- maps (F5) ---------------------------------------------------------------------------

def test_T_WORLD_04_map_handout_version(session, sample):
    """T-WORLD-04: the handout copy of a map prints only the layers set to
    "Show in handout"; the adventure PDF prints every layer, notes included (F5.9)."""
    session.open(sample("m3-world"))
    _, book = _book(session)
    _, players = _players(session)
    gm_map = next(p for p in book if "SKÄRVIKANDTHEBAY" in p)
    player_map = next(p for p in players if "Skärvikandthebay" in p)  # caption under the map since 0.3.2
    for text in ("Thebay", "Skärvikharbour", "Thechapel"):
        assert text in gm_map and text in player_map
    for secret in ("WreckoftheHoppet", "Thebellringsfromhere"):
        assert secret in gm_map and secret not in player_map


def test_T_WORLD_14_map_images_areas_and_pins(session, sample):
    """T-WORLD-14: a map takes a JPEG or PNG only; an area has 3 to 15
    corners; a pin links to an entry; a small image gets the 300 dpi warning
    (F5.1, F5.3, F5.6–F5.8)."""
    from scriptorum.core.world import WorldError

    session.open(sample("m3-world"))
    with pytest.raises(WorldError) as refused:
        session.create_map("Sketch", "sketch.gif", b"GIF89a....")
    assert refused.value.key == "error.map.notJpegPng"
    jpeg = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffc0001108012c01f403012200021101031101ffd9")
    m = session.create_map("Bay", "bay.jpg", jpeg)
    assert (m["width"], m["height"], m["image"]) == (500, 300, "maps/m-bay/base.jpg")
    small = session.create_map("Chapel yard", "yard.png", _png(400, 300))
    corners = lambda n: [[0.1 + i / 40, 0.1 + (i % 2) / 5] for i in range(n)]
    for n, ok in ((2, False), (3, True), (15, True), (16, False)):
        layers = [{"name": "A", "show_in_handout": True, "items": [{"type": "area", "points": corners(n)}]}]
        if ok:
            assert len(session.update_map({"id": small["id"], "layers": layers})["layers"][0]["items"][0]["points"]) == n
        else:
            with pytest.raises(WorldError):
                session.update_map({"id": small["id"], "layers": layers})
    session.update_map({"id": small["id"], "layers": [{"name": "A", "items": [
        {"type": "pin", "x": 0.5, "y": 0.5, "entry": "c-the-chapel"}]}]})
    assert {"where": "map", "map": small["id"], "title": "Chapel yard"} in session.world.usages("c-the-chapel")
    session.set_chapter_text(0, session.adventure.chapter_text("text/chapter-01.typ") + f'\n#map(map: "{small["id"]}")\n')
    result, _ = _book(session)
    low = [w for w in result.warnings if w.key == "warning.map.lowResolution"]
    assert [w.details["map"] for w in low] == ["Chapel yard"]
    assert not any(w.details["map"] == "Skärvik and the bay" for w in low)


# --- handouts (F6) -----------------------------------------------------------------------

def test_T_WORLD_05_player_pdf(session, sample):
    """T-WORLD-05: the player PDF holds only handouts, one per page, numbered
    in adventure order, each followed by its easy-read copy (with easy-read
    copies switched on, F6.6)."""
    session.open(sample("m3-world"))
    assert session.settings_info()["switches"]["easyRead"]
    _, pages = _players(session)
    assert len(pages) == 5
    # The caption sits under each sheet (look revised 6 November 2026).
    assert "HANDOUT1·Skärvikandthebay" in pages[0]
    assert pages[1].startswith("Keeptheboatsinport") and pages[1].endswith("HANDOUT2·Lovisa'swarning")
    assert pages[2].startswith("Keeptheboatsinport") and pages[2].endswith("HANDOUT2·EASY-READ·Lovisa'swarning")
    assert pages[3].startswith("Cometothechapel") and pages[3].endswith("HANDOUT3·Thesexton'snote")
    assert pages[4].endswith("HANDOUT3·EASY-READ·Thesexton'snote")
    flat = "".join(pages)
    for gm_only in ("LOVISABERG", "Thelightunderthewater", "SCENE", "CLUEOVERVIEW", "MIGHT"):
        assert gm_only not in flat


def test_T_WORLD_16_handout_numbers_match(session, sample):
    """T-WORLD-16: each handout's number in the adventure PDF is its number in the
    player PDF (F6.2, F6.3)."""
    session.open(sample("m3-world"))
    _, book = _book(session)
    flat = "".join(book)
    assert flat.index("HANDOUT#1·SKÄRVIKANDTHEBAY") < flat.index("HANDOUT#2Lovisa'swarning") < flat.index("HANDOUT#3Thesexton'snote")
    assert [h["number"] for h in session.codex()["handouts"]] == [1, 2, 3]
    assert [h["title"] for h in session.codex()["handouts"]] == ["Skärvik and the bay", "Lovisa's warning", "The sexton's note"]


def test_T_WORLD_17_handout_look(session, sample):
    """T-WORLD-17: the handout sheet looks the same on every build; New look
    changes only its look; a theme paper style that colours the sheet or
    prints dark stains gives a preflight warning (F6.5, F7.5)."""
    session.open(sample("m3-world"))
    first, _ = _players(session)
    again, _ = _players(session)
    assert first.output[0] == again.output[0]
    text = session.adventure.chapter_text("text/chapter-01.typ")
    session.set_chapter_text(0, text.replace('id: "h-note")', 'id: "h-note", look: 1)'))
    other, pages = _players(session)
    assert other.output[0] != first.output[0]
    assert "Cometothechapelbeforethebellringsagain." in "".join(pages)
    assert not [w for w in first.warnings if w.key.startswith("warning.paper.")]
    # A theme paper style that breaks the rules (the bundled one does not).
    theme = session._theme()
    handouts = theme.path / "handouts.json"
    original = handouts.read_text("utf-8")
    try:
        data = json.loads(original)
        data["papers"].append({"id": "parchment", "sheet": "#F2E3C6"})
        data["papers"].append({"id": "coffee", "stains": {"count": [1, 2], "opacity": 0.4}})
        handouts.write_text(json.dumps(data), "utf-8")
        warned, _ = _players(session)
        keys = sorted((w.key, w.details["paper"]) for w in warned.warnings if w.key.startswith("warning.paper."))
        assert keys == [("warning.paper.coloured", "parchment"), ("warning.paper.tooDark", "coffee")]
    finally:
        handouts.write_text(original, "utf-8")


def test_T_WORLD_19_easy_read_off_by_default(session, sample):
    """T-WORLD-19: easy-read copies are off by default and follow each
    handout when switched on (F6.6)."""
    session.open(sample("m3-world"))
    session.set_settings({"switches": {"easyRead": False}})
    _, pages = _players(session)
    assert len(pages) == 3 and "EASY-READ" not in "".join(pages)
    assert [p[p.rindex("HANDOUT"):][:8] for p in pages] == ["HANDOUT1", "HANDOUT2", "HANDOUT3"]
    session.new("Fresh", *GS, *TH)
    session.set_chapter_text(0, "= A\n\n#scene(title: \"S\")[\n#handout(title: \"Note\")[Hello.]\n]\n")
    _, pages = _players(session)
    assert len(pages) == 1 and "Hello." in pages[0]


def test_T_WORLD_20_world_changes_undo(session, sample):
    """T-WORLD-20: a codex or map change is one undo step."""
    session.open(sample("m3-world"))
    session.update_entry("c-nils-ek", {"fields": {"mood": "Calm"}})
    session.update_map({"id": "m-skarvik", "title": "The bay"})
    assert session.world_undo()
    assert session.world.maps()["m-skarvik"]["title"] == "Skärvik and the bay"
    assert session.world.entry("c-nils-ek")["fields"]["mood"] == "Calm"
    assert session.world_undo()
    assert session.world.entry("c-nils-ek")["fields"]["mood"] == "Frightened"


def test_m3_sample_round_trip(session, sample, tmp_path):
    """T-FILE-07 for the M3 sample: open and save without edits leaves every
    text file byte-identical, the codex and maps included."""
    import zipfile

    path = sample("m3-world")
    session.open(path)
    session.save(tmp_path / "again.scav")
    with zipfile.ZipFile(path) as a, zipfile.ZipFile(tmp_path / "again.scav") as b:
        for name in a.namelist():
            if name != "manifest.json":
                assert a.read(name) == b.read(name), name


def test_m3_elements_in_sample(session, sample):
    """T-BUILD-13 for M3: m2-full and m3-world together use every element
    the Vaesen game system turns on."""
    used = set()
    for name in ("m2-full", "m3-world"):
        session.open(sample(name))
        text = sample_text(name)
        used |= {k for k in session.kinds() if f"#{k}(" in text or f"#{k}[" in text}
    # From M4 Vaesen also turns on Box, Quote and Pacing note, which sample
    # m4-look uses (test plan change log, 11 Nov 2026).
    m4_elements = {"box", "quote", "pacing"}
    assert used == set(json.loads((ROOT / "scriptorum/bundled/scriptorum.free-league-vaesen/elements.json").read_text())["on"]) - m4_elements


# --- modules (T-MOD-07) ---------------------------------------------------------------------

def test_T_MOD_07_adventure_language(library, session, tmp_path):
    """T-MOD-07: an adventure-language module replaces printed words; a
    missing word falls back to English with a warning (9.3, 9.6.6)."""
    folder = tmp_path / "sv"
    (folder / "labels").mkdir(parents=True)
    (folder / "module.json").write_text(json.dumps({
        "id": "test.svenska", "kind": "adventure-language", "name": "Svenska", "version": "1.0.0", "format": 1,
        "app": "0.1.0", "licence": "GPL-3.0-or-later", "authors": ["Test"], "description": "Swedish printed words",
        "language": "sv", "requires": [{"id": "scriptorum.core", "version": "1.x"}],
    }), "utf-8")
    (folder / "labels" / "scriptorum.core.json").write_text(json.dumps({
        "print.scene": "Scen", "print.read-aloud": "Läs högt", "print.location": "Plats"}), "utf-8")
    module = library.install_folder(folder)
    session.new("Klockan", *GS, *TH)
    session.adventure.manifest["modules"].append({"id": module.id, "version": module.version})
    session.set_chapter_text(0, "= Akt ett\n\n#scene(title: \"Hamnen\", location: \"Kajen\")[\n#read-aloud[Dimma.]\n]\n")
    _, english = _book(session)
    assert "SCENE1" in english[1] and "READALOUD" in english[1]
    session.adventure.settings["language"] = "sv"
    result, swedish = _book(session)
    assert "SCEN1" in swedish[1] and "LÄSHÖGT" in swedish[1] and "PLATS:KAJEN" in swedish[1].upper()
    missing = [w for w in result.warnings if w.key == "warning.build.missingTranslation"]
    assert missing and missing[0].details["language"] == "Svenska"
    assert "print in English" in session.localize(missing[0])


def test_T_WORLD_15_map_in_the_gm_book(session, sample):
    """T-WORLD-15: a map placed in the text prints in the adventure PDF with every
    layer, its notes and areas included, and pins named after their codex
    entries (F5.4, F5.9)."""
    session.open(sample("m3-world"))
    _, book = _book(session)
    page = next(p for p in book if "SKÄRVIKANDTHEBAY" in p)
    for text in ("Thebay", "WreckoftheHoppet", "Thebellringsfromhereatnight.", "Skärvikharbour", "Thechapel"):
        assert text in page


# --- handout sheet, look revised 6 November 2026 (F6.5, F6.6, D16) -----------------------

def _drawing(data: bytes, page: int) -> str:
    """The page's content stream as text, to look at what it draws."""
    reader = PdfReader(io.BytesIO(data))
    return reader.pages[page].get_contents().get_data().decode("latin-1")


def _colours(stream: str) -> set:
    """Fill (rg) and stroke (RG) colours set on the page."""
    import re
    found = set()
    for r, g, b, op in re.findall(r"([\d.]+) ([\d.]+) ([\d.]+) (rg|RG|scn|SCN)\b", stream):
        found.add(("RG" if op in ("RG", "SCN") else "rg", round(float(r), 2), round(float(g), 2), round(float(b), 2)))
    return found


def _rgb(hexcode):
    return tuple(round(int(hexcode[i:i + 2], 16) / 255, 2) for i in (1, 3, 5))


def test_T_WORLD_22_handout_sheet(session, sample):
    """T-WORLD-22: the handout is drawn as in the reference examples: a
    coloured torn outline with a thin inner line, a curled corner, dashed
    fold lines, spot marks and a caption under it; the paper itself is never
    filled with a colour; the easy-read copy keeps the sheet; the version in
    the adventure PDF stays plain (F6.5, F6.6)."""
    session.open(sample("m3-handouts"))
    result, pages = _players(session)
    assert len(pages) == 6
    assert pages[0].endswith("HANDOUT1·Toresbrevtillsällskapet")
    assert pages[1].endswith("HANDOUT1·EASY-READ·Toresbrevtillsällskapet")
    assert "Klockanringerigeninatt.Gåinteut." in pages[4]
    data = result.output[0]
    papers = {p["id"]: p for p in session._theme().handouts()["papers"]}
    for page, paper in ((0, "letter"), (1, "letter"), (2, "worn"), (4, "plain")):
        stream = _drawing(data, page)
        colours = _colours(stream)
        style = papers[paper]
        assert ("RG",) + _rgb(style["outline"]) in colours, (page, colours)
        assert ("RG",) + _rgb(style["inner"]) in colours, (page, colours)
        # Dashed fold lines on letter and worn paper, none on plain.
        dashed = re.search(r"\[3 3\] ?0 d", stream) is not None
        assert dashed == (paper != "plain"), (page, paper)
        # The paper is never filled with a colour: the only fills are white
        # (the curled corner), the ink, the caption's grey and the marks.
        fills = {c[1:] for c in colours if c[0] == "rg"}
        allowed = {(1.0, 1.0, 1.0), (0.0, 0.0, 0.0), _rgb(style["ink"]), _rgb("#1F1B18"), _rgb("#5E5650"),
                   _rgb(style.get("marks", {}).get("colour", "#C9AE84"))}
        assert fills <= allowed, (page, fills - allowed)
    # Spot rings on letter paper, none on plain.
    assert ("RG",) + _rgb(papers["letter"]["marks"]["colour"]) in _colours(_drawing(data, 0))
    # The adventure PDF keeps the plain version with its number.
    _, book = _book(session)
    flat = "".join(book)
    assert "HANDOUT#1Toresbrevtillsällskapet" in flat and "HANDOUT#3Enlappikyrkbänken" in flat


def _cmap(data: bytes) -> set:
    """Characters a TrueType font has (its format 4 cmap subtable)."""
    import struct
    tables = {data[12 + 16 * i:16 + 16 * i]: struct.unpack(">II", data[20 + 16 * i:28 + 16 * i])
              for i in range(struct.unpack(">H", data[4:6])[0])}
    base = tables[b"cmap"][0]
    chars = set()
    for i in range(struct.unpack(">H", data[base + 2:base + 4])[0]):
        offset = struct.unpack(">I", data[base + 8 + 8 * i:base + 12 + 8 * i])[0]
        sub = base + offset
        if struct.unpack(">H", data[sub:sub + 2])[0] != 4:
            continue
        segs = struct.unpack(">H", data[sub + 6:sub + 8])[0] // 2
        ends = struct.unpack(f">{segs}H", data[sub + 14:sub + 14 + 2 * segs])
        starts = struct.unpack(f">{segs}H", data[sub + 16 + 2 * segs:sub + 16 + 4 * segs])
        for a, b in zip(starts, ends):
            chars.update(range(a, b + 1))
    return chars


def test_T_WORLD_23_bundled_handwriting(session, sample):
    """T-WORLD-23: the theme brings two open-licence handwriting fonts, a
    plain hand and a formal script, both with å, ä and ö, and a letter in
    one of them prints in it; the easy-read copy does not (F6.6, F6.7, D16)."""
    from scriptorum.core import fonts
    session.open(sample("m3-handouts"))
    # From M4 the hands live in the core element kit, so every theme offers
    # them (F8, T-LOOK-06); the plain hand and the formal script come first.
    theme = next(m for m in session._kits() if m.id == "scriptorum.core")
    hands = theme.handwriting()
    assert [h["family"] for h in hands][:2] == ["Homemade Apple", "Pinyon Script"]
    for h in hands:
        data = (theme.path / h["file"]).read_bytes()
        assert fonts.check_font(data).ok, h
        assert all(ord(c) in _cmap(data) for c in "åäöÅÄÖ"), h
    options = [o["id"] for o in session.choice_options("handwriting")]
    assert {"Homemade Apple", "Pinyon Script"} <= set(options)
    result = session.build("pdf", player=True)
    assert result.ok and not [w for w in result.warnings if "font" in (w.message or "").lower()]
    reader = PdfReader(io.BytesIO(result.output[0]))

    def page_fonts(i):
        res = reader.pages[i]["/Resources"]["/Font"]
        return {str(res[k].get_object()["/BaseFont"]) for k in res}
    assert any("HomemadeApple" in f for f in page_fonts(0))   # Tore's letter
    assert any("PinyonScript" in f for f in page_fonts(2))    # Agnes's note
    assert not any("HomemadeApple" in f or "PinyonScript" in f for f in page_fonts(1))  # easy-read
    text = "".join(p.extract_text() or "" for p in reader.pages[:3])
    assert "Högtärade" in text and "käraste" in text  # å, ä, ö in both hands
