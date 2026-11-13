"""Test Plan, Milestone 4 (Vaesen look): elements, themes, fonts, handouts,
palettes and the example adventure, without a window.

T-SRC-16, T-BUILD-16 to 18, T-WORLD-24 and 25, T-LOOK-01 to 06, 08 to 10,
T-UI-20 and T-UI-22, and the core part of T-UI-21.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile

import pytest
from pypdf import PdfReader

from tests.conftest import ROOT, SAMPLES, pack_sample

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")
THEMES = ("scriptorum.vaesen", "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu")
BUNDLED = ROOT / "scriptorum" / "bundled"


def _pages(data: bytes) -> list:
    """Page texts without spaces or soft hyphens, in capitals (labels are
    letter-spaced and set in capitals by the themes)."""
    return ["".join((p.extract_text() or "").split()).replace("­", "").upper() for p in PdfReader(io.BytesIO(data)).pages]


def _fonts(data: bytes) -> set:
    reader = PdfReader(io.BytesIO(data))
    names = set()
    for page in reader.pages:
        res = page.get("/Resources", {}).get("/Font", {})
        for key in res:
            names.add(str(res[key].get_object()["/BaseFont"]))
    return names


def _svg(session) -> str:
    result = session.build("svg")
    assert result.ok, [session.localize(e) for e in result.errors]
    return "".join(p.decode() if isinstance(p, bytes) else p for p in result.output).lower()


def _ok(session, result):
    assert result.ok, [session.localize(e) for e in result.errors]
    return result


def _roundtrip(session, text: str) -> bool:
    from scriptorum.core import source
    doc = source.parse(text, session.kinds())
    return source.serialize(doc, session.kinds()) == text


# --- T-SRC-16 scene Type --------------------------------------------------------------------

def test_T_SRC_16_scene_type(session):
    """T-SRC-16: a scene with a Type parses and writes back byte-identical,
    and prints small beside the scene number: "SCENE 2 · CLIMAX" (11.1)."""
    session.new("Typer", *GS, *TH)
    text = ('#scene(title: "First")[\nText.\n]\n\n#scene(title: "Second", type: "Climax")[\nMore text.\n]\n')
    assert _roundtrip(session, text)
    session.set_chapter_text(0, text)
    doc = session.chapter(0)["doc"]
    assert doc["blocks"][1]["fields"]["type"] == "Climax"
    pages = _pages(_ok(session, session.build("pdf")).output[0])
    assert "SCENE2·CLIMAX" in "".join(pages)
    assert "SCENE1·" not in "".join(pages)  # a scene without a Type prints as before


# --- T-BUILD-16 act headings in a row, T-BUILD-17 no title line --------------------------

def test_T_BUILD_16_act_headings_in_a_row(session):
    """T-BUILD-16: two act headings in a row and a scene share one page; with a
    page break before the second heading it starts a new page (F7.4)."""
    session.new("Akter", *GS, *TH)
    session.set_chapter_text(0, '= Act one\n\n= Act two\n\n#scene(title: "First")[\nText.\n]\n')
    pages = _pages(_ok(session, session.build("pdf")).output[0])
    assert len(pages) == 2  # title page + one page with both headings and the scene
    assert "ACTONE" in pages[1] and "ACTTWO" in pages[1] and "FIRST" in pages[1]
    session.set_chapter_text(0, '= Act one\n\n#page-break()\n\n= Act two\n\n#scene(title: "First")[\nText.\n]\n')
    pages = _pages(_ok(session, session.build("pdf")).output[0])
    assert len(pages) == 3
    assert "ACTONE" in pages[1] and "ACTTWO" not in pages[1]
    assert "ACTTWO" in pages[2] and "FIRST" in pages[2]


def test_T_BUILD_17_new_adventure_has_no_title_line(session, tmp_path):
    """T-BUILD-17: a new adventure's text starts with its first scene; the
    title prints only on the title page (F7.9)."""
    session.new("Skuggan i dimman", *GS, *TH)
    text = session.adventure.chapter_text(session.adventure.chapters[0])
    assert text.startswith("#scene(")
    reply = session.export_pdf(tmp_path / "new.pdf")
    assert reply["ok"], reply
    pages = _pages((tmp_path / "new.pdf").read_bytes())
    assert "SKUGGANIDIMMAN" in pages[0]
    assert all("SKUGGANIDIMMAN" not in p for p in pages[1:])


# --- T-BUILD-18 the example adventure in all three themes -----------------------------------

@pytest.mark.parametrize("theme", THEMES)
def test_T_BUILD_18_example_adventure(session, sample, theme):
    """T-BUILD-18: Jätten Finns skuld builds in every theme, and every part
    prints, with å, ä and ö, and the printed words in English (F20)."""
    session.open(sample("example-jattens-skuld"))
    session.set_theme(theme)
    result = _ok(session, session.build("pdf"))
    # M6 part C (F4): the sample keeps its older text, whose sub-headings
    # directly under a scene skip a level; that is the only warning (test
    # plan change log, 13 Nov 2026). The bundled example has them raised.
    assert [w.key for w in result.warnings] == ["warning.heading.skipsLevel"] * 2
    flat = "".join(_pages(result.output[0]))
    for printed in ("JÄTTENFINNSSKULD", "EXEMPELÄVENTYR", "OKÄND",                      # title page
                    "JOHANNASTRANDH", "PERMÅNSSON", "EDVARDMALMROS", "GUSTAFLINDELL", "BENGTLÖÖF",
                    "JÄTTENFINN", "GERDAUNDERBACKEN", "MIGHT6",                           # people and creatures
                    "SPECIALREGEL:ATTROPAENJÄTTESNAMN",                                    # Box
                    "HANSKALLHAFVASOLOCHMÅNE",                                             # the epigraph Quote
                    "VARJEBESÖKTARUNGEFÄRENTIMME",                                         # pacing note
                    "COUNTDOWN", "KL.22", "SCENE1·ENCOUNTER", "SCENE2·CLIMAX",
                    "READALOUD", "SECRET", "HANDOUT#1", "HANDOUT#2", "TIDHÄNDELSE"):
        assert printed in flat, (theme, printed)
    player = _ok(session, session.build("pdf", player=True))
    text = "".join(_pages(player.output[0]))
    assert "ÄRADEHERRAR" in text and "JÄTTENBYGDEKYRKIAN" in text
    fonts = _fonts(player.output[0])
    assert any("HomemadeApple" in f for f in fonts)  # Johanna's letter: Everyday hand
    assert any("PinyonScript" in f for f in fonts)   # Wolf's chronicle: Copperplate


def _raised(text: str) -> str:
    """F20 (M6 part C): the bundled example is the sample with its five
    sub-headings directly under a scene raised from ==== to ===, so its
    accessible PDF passes; the sample itself is never changed."""
    for title in ("Vad Gerda vet", "Vaggvisan", "Lösningar i scenen", "Möjliga vägar ut", "Kyrkan rämnar"):
        text = text.replace(f"\n==== {title}\n", f"\n=== {title}\n")
    return text


def test_T_BUILD_18_example_round_trips(session, sample):
    """F20: the converted example is in Scriptorum's own format: it reads and
    writes back byte-identical, with only lists kept as locked blocks."""
    from scriptorum.core import source
    session.open(sample("example-jattens-skuld"))
    text = session.adventure.chapter_text("text/chapter-01.typ")
    doc = source.parse(text, session.kinds())
    assert source.serialize(doc, session.kinds()) == text
    locked = [b for b in source._walk(doc["blocks"]) if b["type"] == "locked"]
    assert all(b["raw"].startswith("- ") for b in locked)
    assert (ROOT / "scriptorum" / "examples" / "jatten-finns-skuld" / "text" / "chapter-01.typ").read_text("utf-8") == _raised(text)


# --- T-WORLD-24 long handouts, T-WORLD-25 tilt and Parchment ------------------------------------

LINE = "Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen om natten."


def _letter(paragraphs: int) -> str:
    return "\n\n".join([LINE] * paragraphs)


def _handout_adventure(session, paragraphs, easy=True, extra=""):
    session.new("Brev", *GS, *TH)
    text = (f'#scene(title: "Brevet")[\n#handout(title: "Ett långt brev", handwriting: "Homemade Apple", id: "h-long")[\n'
            f"{_letter(paragraphs)}\n]\n{extra}]\n")
    session.set_chapter_text(0, text)
    if easy:
        session.set_settings({"switches": {"easyRead": True}})


def test_T_WORLD_24_long_handouts(session):
    """T-WORLD-24: a handout slightly over one sheet is set smaller and stays
    on one sheet; a longer one continues on further sheets with captions
    "1 of 2", "./." at the foot of every sheet but the last, the easy-read
    copy split on its own, one number in both PDFs; more than 4 sheets warns."""
    # Find the size of one sheet: the most paragraphs that fit at full size.
    fits = 1
    while True:
        _handout_adventure(session, fits + 1, easy=False)
        if session.handout_sheets().get(1, 1) > 1:
            break
        fits += 1
    # Somewhat longer: two sheets at the normal size.
    _handout_adventure(session, int(fits * 1.5) + 2)
    assert session.handout_sheets() == {1: 2}
    player = _ok(session, session.build("pdf", player=True))
    pages = _pages(player.output[0])
    sheets = [p for p in pages if "HANDOUT1·ETTLÅNGTBREV" in p]
    easy = [p for p in pages if "HANDOUT1·EASY-READ" in p]
    assert len(sheets) == 2 and "1OF2" in sheets[0] and "2OF2" in sheets[1]
    assert "./." in sheets[0] and "./." not in sheets[1]
    assert easy and all("OF" in p for p in easy)  # the easy-read copy has its own count
    # The last sheet holds at least 5 % of the lines and never fewer than 3.
    assert sheets[1].count("JAGSKRIFVER") >= 1
    # No text outside any sheet: every page of the player PDF is a sheet.
    assert all("HANDOUT1" in p for p in pages)
    # More than 4 sheets: a warning, and export still works.
    _handout_adventure(session, fits * 5, easy=False)
    # The adventure PDF keeps one plain handout that continues onto the next page.
    book = _pages(_ok(session, session.build("pdf")).output[0])
    assert sum("HANDOUT#1" in p for p in book) == 1
    assert sum("JAGSKRIFVER" in p for p in book) >= 2
    result = _ok(session, session.build("pdf", player=True))
    warning = [w for w in result.warnings if w.key == "warning.handout.long"]
    assert warning and warning[0].details["sheets"] > 4
    assert "unusually long" in session.localize(warning[0])


def test_T_WORLD_24_slightly_long_stays_on_one_sheet(session):
    """T-WORLD-24: text that only just overflows is set smaller (at most
    15 %) and stays on one sheet."""
    fits = 1
    while True:
        _handout_adventure(session, fits + 1, easy=False)
        if session.handout_sheets().get(1, 1) > 1:
            break
        fits += 1
    # At fits + 1 paragraphs the handout needed a second sheet even at 85 %;
    # one line less than that is placed on one sheet, set smaller.
    _handout_adventure(session, fits, easy=False)
    assert session.handout_sheets() == {1: 1}
    session.set_chapter_text(0, session.adventure.chapter_text(session.adventure.chapters[0]).replace(
        "]\n]\n", " Ett par ord till för att fylla ut raden ännu mer.\n]\n]\n"))
    assert session.handout_sheets() == {1: 1}


def test_T_WORLD_25_tilt_and_parchment(session, sample):
    """T-WORLD-25: tilted handouts on Parchment (−1°) and letter paper (+5°);
    the easy-read copy keeps the tilt; Parchment is never filled (F6.5)."""
    session.open(sample("m4-look"))
    result = _ok(session, session.build("svg", player=True))
    svg = [p.decode() if isinstance(p, bytes) else p for p in result.output]
    rotated = [i for i, p in enumerate(svg) if re.search(r"matrix\((0\.99|0\.996)", p)]
    # Each tilted handout and its easy-read copy is turned.
    assert len(rotated) >= 4, rotated
    paper = json.loads((BUNDLED / "scriptorum.vaesen" / "handouts.json").read_text("utf-8"))
    parchment = next(p for p in paper["papers"] if p["id"] == "parchment")
    assert parchment["edge"] == "soft" and parchment["corner"] == "round" and parchment["marks"]["hatch"][0] > 0
    assert "fill" not in parchment and parchment["marks"]["opacity"] <= 0.2
    assert not [w for w in result.warnings if w.key.startswith("warning.paper")]
    text = session.adventure.chapter_text("text/chapter-01.typ")
    assert 'paper: "parchment", tilt: -1' in text and "tilt: 5" in text and _roundtrip(session, text)


def test_T_WORLD_25_tilt_out_of_range(session):
    """F6.5: a tilt outside −5° to +5° is reported on the author's line."""
    session.new("Lutning", *GS, *TH)
    session.set_chapter_text(0, '#scene(title: "S")[\n#handout(title: "Lapp", tilt: 9)[Text.]\n]\n')
    result = session.build("pdf")
    assert not result.ok and result.errors[0].key == "error.build.outOfRange" and result.errors[0].line == 2


# --- T-LOOK ---------------------------------------------------------------------------------

def test_T_LOOK_01_vaesen_fonts(session, sample):
    """T-LOOK-01: the Vaesen faces print, each a bundled static weight with
    its licence file that passes the font guard and has å, ä and ö."""
    from scriptorum.core import fonts
    from tests.test_world import _cmap
    session.open(sample("m4-look"))
    result = _ok(session, session.build("pdf"))
    used = _fonts(result.output[0])
    for face in ("Berolina", "PlayfairDisplay", "LibreBaskerville", "CormorantGaramond-Medium", "CormorantGaramond", "Acme"):
        assert any(face in f for f in used), (face, used)
    for module in ("scriptorum.vaesen", "scriptorum.core", "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu"):
        folder = BUNDLED / module / "fonts"
        licences = [f.name for f in folder.iterdir() if f.suffix == ".txt"]
        for font in [f for f in folder.iterdir() if f.suffix in (".ttf", ".otf")]:
            data = font.read_bytes()
            assert fonts.check_font(data).ok, font.name
            assert all(ord(c) in _cmap(data) for c in "åäöÅÄÖ"), font.name
            family = re.split(r"[-_]", font.stem)[0].replace("9pt", "")
            assert any(l.lower().startswith(family.lower()[:6]) for l in licences), (font.name, licences)
            assert "[" not in font.name  # never a variable font (F8)


def test_T_LOOK_02_secret_box_fill(session, sample):
    """T-LOOK-02: the secret box has a red scroll and a pale grey fill by
    default, pale beige when set; both light enough for black and white."""
    from scriptorum.core.palettes import luminance
    session.new("Hemlis", *GS, *TH)
    session.set_chapter_text(0, '#scene(title: "S")[\n#information(variant: "secret")[Något.]\n]\n')
    assert session.settings_info()["secretFill"] == "grey"
    svg = _svg(session)
    assert "#eceae6" in svg and "#f3ecdf" not in svg
    assert "data:image/svg+xml" in svg  # the scroll ornament is drawn on the box
    session.set_settings({"secretFill": "beige"})
    assert session.adventure.settings["secret_fill"] == "beige"
    svg = _svg(session)
    assert "#f3ecdf" in svg and "#eceae6" not in svg
    assert luminance("#ECEAE6") > 0.75 and luminance("#F3ECDF") > 0.75
    session.set_settings({"secretFill": "grey"})
    assert "secret_fill" not in session.adventure.settings  # the default is not stored
    scroll = (BUNDLED / "scriptorum.vaesen" / "ornaments" / "scroll.svg").read_text()
    assert set(re.findall(r"#[0-9A-Fa-f]{6}", scroll)) == {"#7B1F2A"}


def test_T_LOOK_03_curl_frame(session, sample):
    """T-LOOK-03: Hint, Public information, the check, the creature and the
    Box in the open curl frame; pen-nib bullets; bold at the start of a line
    is a label in capitals; tables in beige bands with brown rules."""
    session.open(sample("m4-look"))
    result = _ok(session, session.build("pdf"))
    flat = "".join(_pages(result.output[0]))
    raw = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(result.output[0])).pages)
    assert "HUVUDATTRIBUT:" in raw and "LYCKAT SLAG:" in raw  # labels in capitals
    assert "Misslyckat slag" in raw  # not bold, so not a label
    svg = _svg(session)
    assert svg.count("#f1eadc") >= 2  # table bands
    for name in ("curl.svg", "nib.svg"):
        assert (BUNDLED / "scriptorum.vaesen" / "ornaments" / name).is_file()
    style = (BUNDLED / "scriptorum.vaesen" / "templates" / "_style.typ").read_text()
    for template in ("information", "check", "creature", "box"):
        assert "curl-frame" in (BUNDLED / "scriptorum.vaesen" / "templates" / f"{template}.typ").read_text()
    assert 'ornament("nib.svg"' in style and "SPECIALREGEL:FIOLEN" in flat


def test_T_LOOK_04_box(session):
    """T-LOOK-04: the Box parses and writes back byte-identical, prints with
    and without a title, never splits, and has no "Handout also" (11.10)."""
    session.new("Ruta", *GS, *TH)
    text = ('#scene(title: "S")[\n#box(title: "Regel")[\nFörsta stycket.\n\nAndra stycket.\n]\n\n'
            '#box[\nUtan titel.\n]\n]\n')
    assert _roundtrip(session, text)
    session.set_chapter_text(0, text)
    flat = "".join(_pages(_ok(session, session.build("pdf")).output[0]))
    assert "REGEL" in flat and "FÖRSTASTYCKET" in flat and "UTANTITEL" in flat
    definition = session.kinds()["box"]
    assert definition["never_split"] and not definition["handout"]
    assert not any(f["name"] == "handout-also" for f in definition["fields"])


def test_T_LOOK_05_quote(session, sample):
    """T-LOOK-05: the Quote in its three looks: signature, description, a
    linked person's hand, tilt, the tint only on Scrap and switchable, never
    split, never a handout, byte-identical (11.11)."""
    session.open(sample("m4-look"))
    text = session.adventure.chapter_text("text/chapter-01.typ")
    assert _roundtrip(session, text)
    for look in ("framed", "scrap", "plain"):
        assert f'#quote(variant: "{look}"' in text
    result = _ok(session, session.build("pdf"))
    raw = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(result.output[0])).pages)
    assert "— Okänd" in raw and "— Agda Holm" in raw and "SJUNGEN VID KVARNÅN" in "".join(raw.split("\n")).upper().replace("  ", " ") or "SJUNGENVIDKVARNÅN" in "".join(_pages(result.output[0]))
    assert any("Caveat" in f for f in _fonts(result.output[0]))  # Agda's hand on her quote
    svg = _svg(session)
    assert svg.count("#f4ecd9") == 1  # the tint on the one tinted scrap only
    definition = session.kinds()["quote"]
    assert definition["never_split"] and not definition["handout"]
    assert {v["id"] for v in definition["variants"]} == {"framed", "scrap", "plain"}
    assert not [h for h in session.world.handouts() if "Näcken" in h["title"]]  # quotes are never handouts


def test_T_LOOK_06_handwriting_choice(session, sample, tmp_path):
    """T-LOOK-06: six hands from the core element kit, listed by the kind of
    hand with a description and the font's name; files store the font's
    name, so an M3 adventure opens and saves byte-identical."""
    session.open(sample("m3-handouts"))
    options = session.choice_options("handwriting")
    assert [o["label"] for o in options[:6]] == ["Everyday hand", "Copperplate", "Flowing hand", "Note hand", "School hand", "Typewriter"]
    assert [o["id"] for o in options[:6]] == ["Homemade Apple", "Pinyon Script", "Dancing Script", "Caveat", "Cedarville Cursive", "TT2020 Style E"]
    assert all(o["note"] and o["font"] == o["id"] for o in options[:6])
    core = next(m for m in session._kits() if m.id == "scriptorum.core")
    assert all((core.path / h["file"]).is_file() for h in core.handwriting())
    assert not (BUNDLED / "scriptorum.vaesen" / "fonts" / "HomemadeApple-Regular.ttf").exists()
    before = {n: d for n, d in session.adventure.files.items() if n.endswith((".typ", ".json")) and n != "manifest.json"}
    session.save(tmp_path / "saved.scav")
    with zipfile.ZipFile(tmp_path / "saved.scav") as zf:
        for name, data in before.items():
            assert zf.read(name) == data, name


@pytest.mark.parametrize("theme", THEMES)
def test_T_LOOK_08_three_themes(session, sample, tmp_path, theme):
    """T-LOOK-08: m4-look builds in each theme without errors or
    missing-renderer warnings; a letter keeps its hand; switching the theme
    leaves every text, codex and map file byte-identical."""
    path = sample("m4-look")
    session.open(path)
    with zipfile.ZipFile(path) as zf:
        original = {n: zf.read(n) for n in zf.namelist()}
    session.set_theme(theme)
    assert session.adventure.theme.id == theme
    result = _ok(session, session.build("pdf"))
    assert [session.localize(w) for w in result.warnings] == []
    player = _ok(session, session.build("pdf", player=True))
    assert any("Caveat" in f for f in _fonts(player.output[0]))  # Agda's letter keeps her hand
    session.save(tmp_path / "switched.scav")
    with zipfile.ZipFile(tmp_path / "switched.scav") as zf:
        for name, data in original.items():
            if name != "manifest.json":
                assert zf.read(name) == data, name
        manifest = json.loads(zf.read("manifest.json"))
    old = json.loads(original["manifest.json"])
    changed = {k for k in manifest if manifest[k] != old.get(k)}
    assert changed <= {"theme", "modules", "modified", "app"}
    assert manifest["theme"]["id"] == theme


def test_T_LOOK_09_general_themes(library, session, tmp_path):
    """T-LOOK-09: a theme that requires only scriptorum.core is offered for
    every game system, including a test one; the Vaesen theme only for
    Vaesen; each general theme says it is unofficial."""
    folder = tmp_path / "gs"
    folder.mkdir()
    (folder / "module.json").write_text(json.dumps({
        "id": "test.other-game", "kind": "game-system", "name": "Other game", "version": "1.0.0", "format": 1,
        "app": "0.1.0", "licence": "GPL-3.0-or-later", "authors": ["Test"], "description": "A test game system",
        "requires": [{"id": "scriptorum.core", "version": "1.x"}]}), "utf-8")
    (folder / "elements.json").write_text(json.dumps({"on": ["scene", "read-aloud", "box"]}), "utf-8")
    library.install_folder(folder)
    offered = {g["id"]: {t["id"] for t in g["themes"]} for g in session.game_systems()}
    # M5: the Plain theme is a general theme too (F8, decided 11 Nov 2026).
    assert offered["test.other-game"] == {"scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu", "scriptorum.plain"}
    assert offered["scriptorum.free-league-vaesen"] == set(THEMES) | {"scriptorum.plain"}
    for theme in ("scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu"):
        manifest = json.loads((BUNDLED / theme / "module.json").read_text("utf-8"))
        assert manifest["requires"] == [{"id": "scriptorum.core", "version": "1.x"}]
        assert "unofficial" in manifest["description"] and "not affiliated" in manifest["description"]
        licence = (BUNDLED / theme / "LICENSE.txt").read_text("utf-8")
        assert "unofficial" in licence and "not affiliated" in licence
    # A general theme builds an adventure of the test game system.
    session.new("Annat", "test.other-game", "1.0.0", "scriptorum.call-of-cthulhu", "1.0.0")
    session.set_chapter_text(0, '#scene(title: "S")[\n#box(title: "R")[Text.]\n]\n')
    assert session.build("pdf").ok
    shutil.rmtree(library.root / "test.other-game")


@pytest.mark.parametrize("theme", THEMES)
def test_T_LOOK_10_pacing_note(session, theme):
    """T-LOOK-10: the pacing note prints its text with the bold kept, an
    hourglass and a frame, in all three themes; never split, never a
    handout; byte-identical (11.12)."""
    session.new("Tempo", *GS, *TH)
    session.set_theme(theme)
    text = '#scene(title: "S")[\nFöre.\n\n#pacing[Låt dem leta i *tjugo minuter*.]\n\nEfter.\n]\n'
    assert _roundtrip(session, text)
    session.set_chapter_text(0, text)
    result = _ok(session, session.build("pdf"))
    assert "LÅTDEMLETAITJUGOMINUTER" in "".join(_pages(result.output[0]))
    assert any("Bold" in f for f in _fonts(result.output[0]))
    assert (BUNDLED / theme / "ornaments" / "hourglass.svg").is_file()
    definition = session.kinds()["pacing"]
    assert definition["never_split"] and not definition["handout"] and definition["toolbar_group"] == "rules"


# --- palettes (F16) ----------------------------------------------------------------------------

def test_T_UI_20_claret_and_ink_contrast(library):
    """T-UI-20: every text colour of Claret & Ink reads at a contrast of at
    least 4.5 on its background, in light and dark mode; the page preview
    stays white."""
    from scriptorum.core.palettes import TOKENS, low_contrast
    module = library.newest("scriptorum.claret-and-ink")
    palette = module.palette()
    assert set(palette["light"]) == set(TOKENS) == set(palette["dark"])
    assert low_contrast(palette["light"]) == [] and low_contrast(palette["dark"]) == []
    # The approved colours (12.5).
    assert (palette["light"]["window"], palette["light"]["editor"], palette["light"]["text"], palette["light"]["claret"]) == \
        ("#DED5C7", "#F3EEE6", "#1B2F33", "#69353F")
    assert (palette["dark"]["window"], palette["dark"]["sidebar"], palette["dark"]["editor"], palette["dark"]["claret-text"]) == \
        ("#1B2F33", "#14242A", "#243B40", "#CC9A8E")
    css = (ROOT / "scriptorum" / "ui" / "styles.css").read_text("utf-8")
    assert ".page { background: #fff; }" in css


def test_T_UI_22_palette_stylesheet(library, tmp_path):
    """T-UI-22: a palette whose palette.css loads a remote font is refused,
    with the address named; a local stylesheet is accepted; Shift skips it;
    Reset brings back Claret & Ink."""
    from scriptorum.core.appsettings import AppSettings, DEFAULT_PALETTE, chosen_palette, palette_info
    from scriptorum.core.modules import ModuleError

    def palette_folder(name, css):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "module.json").write_text(json.dumps({
            "id": f"test.{name}", "kind": "palette", "name": name, "version": "1.0.0", "format": 1, "app": "0.1.0",
            "licence": "GPL-3.0-or-later", "authors": ["Test"], "description": "A test palette", "requires": []}))
        (folder / "palette.json").write_text(json.dumps({"light": {"window": "#FFFFFF", "text": "#000000"}}))
        (folder / "palette.css").write_text(css)
        return folder

    remote = palette_folder("remote", "@font-face { font-family: X; src: url('https://fonts.example.com/x.woff2'); }")
    with pytest.raises(ModuleError) as refused:
        library.install_folder(remote)
    assert refused.value.key == "error.module.remoteStylesheet"
    assert refused.value.details["address"] == "https://fonts.example.com/x.woff2"
    for css in ("body { background: url(//cdn.example.com/p.png) }", "@import 'http://example.com/a.css';"):
        shutil.rmtree(remote)
        remote = palette_folder("remote", css)
        with pytest.raises(ModuleError):
            library.install_folder(remote)
    local = library.install_folder(palette_folder("local", ".menubar { border-radius: 0; }"))
    assert palette_info(local)["css"].startswith(".menubar")
    assert palette_info(local, skip_css=True)["css"] == ""
    settings = AppSettings(tmp_path / "app-settings.json")
    settings.update({"palette": local.id})
    assert chosen_palette(library, settings).id == local.id
    settings.update({"palette": DEFAULT_PALETTE, "palette_version": None})  # Reset to Claret & Ink
    assert chosen_palette(library, settings).id == DEFAULT_PALETTE
    shutil.rmtree(library.root / "test.local")


def test_T_UI_21_saved_palette_survives_restart(library, tmp_path):
    """T-UI-21 (core part): a palette made with the colour pickers is saved
    as a palette module, chosen, and still chosen after a restart; a text
    colour below 4.5 is allowed but reported."""
    from scriptorum.core import appsettings
    from scriptorum.core.modules import validate_folder
    from scriptorum.core.palettes import low_contrast
    base = library.newest("scriptorum.claret-and-ink").palette()
    light = dict(base["light"], text="#9A9A9A")  # too pale: a quiet warning only
    module = appsettings.save_palette(library, "Min rödvin", light, base["dark"])
    assert module.id == "my.min-r-dvin" and module.kind == "palette"
    assert validate_folder(module.path)["kind"] == "palette"
    assert low_contrast(module.palette()["light"])
    settings = appsettings.AppSettings(tmp_path / "app-settings.json")
    settings.update({"palette": module.id, "palette_version": module.version})
    restarted = appsettings.AppSettings(tmp_path / "app-settings.json")
    assert appsettings.chosen_palette(library, restarted).id == module.id
    again = appsettings.save_palette(library, "Min rödvin", light, base["dark"])
    assert again.version == "1.1.0"  # saving again makes a new version
    shutil.rmtree(library.root / module.id)


def test_T_UI_25_app_settings(tmp_path):
    """T-UI-25 (F18): values are kept in the app's folder; values out of range or
    unknown are ignored; the snapshot interval takes effect at once."""
    from scriptorum.core.appsettings import AppSettings
    from scriptorum.core.protect import SnapshotClock
    settings = AppSettings(tmp_path / "a.json")
    settings.update({"snapshot_minutes": 5, "mode": "purple", "unknown": 1, "ui_size": 99})
    again = AppSettings(tmp_path / "a.json")
    assert again.get("snapshot_minutes") == 5 and again.get("mode") == "system" and again.get("ui_size") == 18
    clock = SnapshotClock(now=0, interval=5 * 60)
    clock.mark_changed()
    assert not clock.due(now=299) and clock.due(now=300)


def test_F20_open_example_makes_a_copy(session, tmp_path, monkeypatch):
    """T-UI-24 (core part): the example opens as a copy in the documents
    folder; editing and saving the copy leaves the bundled original alone."""
    from scriptorum.core.modules import folder_digest
    monkeypatch.setenv("SCRIPTORUM_DOCUMENTS", str(tmp_path / "docs"))
    original = ROOT / "scriptorum" / "examples" / "jatten-finns-skuld"
    before = folder_digest(original)
    first = session.open_example()
    assert first == tmp_path / "docs" / "Jätten Finns skuld.scav" and session.adventure.title == "Jätten Finns skuld"
    session.set_chapter_text(0, session.adventure.chapter_text("text/chapter-01.typ") + "\nEn ändring.\n")
    session.save()
    assert folder_digest(original) == before
    second = session.open_example()
    assert second.name == "Jätten Finns skuld 2.scav"
    assert _raised((SAMPLES / "example-jattens-skuld" / "text" / "chapter-01.typ").read_text("utf-8")) == \
        (original / "text" / "chapter-01.typ").read_text("utf-8")


def test_T_LOOK_09_themes_share_their_templates():
    """F8: the three bundled themes share their templates; only _style.typ
    (colours, fonts, frames) differs (tools/make_general_themes.py)."""
    base = BUNDLED / "scriptorum.vaesen" / "templates"
    for theme in THEMES[1:]:
        folder = BUNDLED / theme / "templates"
        assert sorted(p.name for p in folder.iterdir()) == sorted(p.name for p in base.iterdir())
        for template in base.iterdir():
            if template.name != "_style.typ":
                assert (folder / template.name).read_bytes() == template.read_bytes(), (theme, template.name)
