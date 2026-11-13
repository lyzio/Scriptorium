"""Test Plan, Milestone 5 part A, without a window: the Plain game system and
Plain theme (F8), the start-up checks (F9) and the remembered preview zoom
(F7.2). T-MOD-13, T-LOOK-11, T-UI-26 (core part) and T-UI-27 (core part).
"""

from __future__ import annotations

import io
import json
import os
import re

import pytest
from pypdf import PdfReader

from tests.conftest import ROOT, sample_text

BUNDLED = ROOT / "scriptorum" / "bundled"
PLAIN_GS = ("scriptorum.plain-system", "1.0.0")
PLAIN_TH = ("scriptorum.plain", "1.0.0")


def _text(data: bytes) -> str:
    return "".join("".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(data)).pages).replace("­", "")


def _ok(session, result):
    assert result.ok, [session.localize(e) for e in result.errors]
    return result


# --- T-MOD-13 the Plain game system --------------------------------------------------------

@pytest.mark.unit
def test_T_MOD_13_plain_is_offered_first(session):
    """T-MOD-13: the New adventure dialog offers the Plain game system and the
    Plain theme first, so they are preselected; Vaesen and its theme can still
    be picked; Plain is a general theme offered for every game system."""
    systems = session.game_systems()
    assert systems[0]["id"] == "scriptorum.plain-system" and systems[0]["standard"] is True
    assert systems[0]["themes"][0]["id"] == "scriptorum.plain"
    vaesen = next(g for g in systems if g["id"] == "scriptorum.free-league-vaesen")
    assert vaesen["themes"][0]["id"] == "scriptorum.vaesen"
    assert "scriptorum.plain" in {t["id"] for t in vaesen["themes"]}
    assert "scriptorum.vaesen" not in {t["id"] for t in systems[0]["themes"]}


@pytest.mark.unit
def test_T_MOD_13_plain_turns_on_every_core_element(library):
    """T-MOD-13: the Plain game system turns on every element of the core
    element kit and adds none of its own; its codex types are the core ones."""
    plain = library.get(*PLAIN_GS)
    core = library.newest("scriptorum.core")
    layout = {k for k, d in core.element_kinds().items() if d.get("category") == "layout" or d.get("always_on")}
    assert set(plain.turned_on()) == set(core.element_kinds()) - layout
    assert not (plain.path / "elements").exists()
    assert plain.codex_types() == {}
    assert plain.manifest["requires"] == [{"id": "scriptorum.core", "version": "1.x"}]


@pytest.mark.integration
def test_T_MOD_13_plain_dice_and_free_stats(session):
    """T-MOD-13: dice use plain notation (d6, 2d10+1, d100); a creature has no
    fixed attributes but free name-and-value lines; a check is free text with
    an optional difficulty."""
    session.new("Plain dice", *PLAIN_GS, *PLAIN_TH)
    text = (
        '#scene(title: "Test")[\n'
        'Roll #dice(dice: "d6"), then #dice(dice: "2d10+1") and #dice(dice: "d100").\n\n'
        '#creature(name: "Grey wolf", stat-lines: "Strength 3\\nSpeed 5")\n\n'
        '#check(roll: "Climbing")[Up the wall.]\n'
        ']\n'
    )
    session.set_chapter_text(0, text)
    printed = _text(_ok(session, session.build("pdf")).output[0])
    for words in ("d6", "2d10+1", "d100", "Strength", "Speed", "Climbing"):
        assert words.upper() in printed.upper(), words
    kinds = session.kinds()
    names = [f["name"] for f in kinds["creature"]["fields"]]
    assert "stat-lines" in names and "might" not in names
    # Vaesen keeps its own dice: 2d10+1 is not Vaesen notation.
    session.new("Vaesen dice", "scriptorum.free-league-vaesen", "1.0.0", "scriptorum.vaesen", "1.0.0")
    session.set_chapter_text(0, '#scene(title: "Test")[\n#dice(dice: "2d10+1")\n]\n')
    assert not session.build("pdf").ok


# --- T-LOOK-11 the Plain theme -------------------------------------------------------------

@pytest.mark.integration
def test_T_LOOK_11_plain_sample_uses_every_core_element(session, sample):
    """T-LOOK-11: sample m5-plain uses every core element in the Plain game
    system and Plain theme and builds without errors or warnings; its text
    writes back byte-identical; the player PDF has its handouts."""
    from scriptorum.core import source

    session.open(sample("m5-plain"))
    text = sample_text("m5-plain")
    for kind, definition in session.kinds().items():
        # The always-on markers of M5 part B have their own sample, m5-print.
        if kind == "countdown-step" or definition.get("always_on"):
            continue
        assert re.search(rf"#{kind}[(\[]", text), kind
    doc = source.parse(text, session.kinds())
    assert source.serialize(doc, session.kinds()) == text
    result = _ok(session, session.build("pdf"))
    assert [session.localize(w) for w in result.warnings] == []
    printed = _text(result.output[0]).upper()
    for words in ("THEBELLATSKÄRVIK", "FOGOVERTHEQUAY", "THEDROWNEDBELL", "STRENGTH", "Å", "Ä", "Ö"):
        assert words in printed, words
    player = _ok(session, session.build("pdf", player=True))
    assert "LOVISA'SLETTER" in _text(player.output[0]).upper().replace("’", "'")


@pytest.mark.integration
def test_T_LOOK_11_plain_prints_in_black_and_white(session, sample):
    """T-LOOK-11: the Plain theme prints black text on white with one grey:
    every colour it draws is a grey; Libre Baskerville and Playfair Display
    print; the theme has no ornaments, only the bundled fonts."""
    session.open(sample("m5-plain"))
    svg = "".join(p.decode() if isinstance(p, bytes) else p for p in _ok(session, session.build("svg")).output).lower()
    colours = set(re.findall(r"#[0-9a-f]{6}\b", svg))
    not_grey = {c for c in colours if not (c[1:3] == c[3:5] == c[5:7])}
    # The map's base image and the handwriting hands are the author's, not the theme's.
    assert not_grey == set(), sorted(not_grey)
    pdf = _ok(session, session.build("pdf")).output[0]
    fonts = set()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for ref in page.get("/Resources", {}).get("/Font", {}).values():
            fonts.add(str(ref.get_object()["/BaseFont"]))
    assert any("LibreBaskerville" in f for f in fonts) and any("PlayfairDisplay" in f for f in fonts)
    theme = BUNDLED / "scriptorum.plain"
    assert not (theme / "ornaments").exists()
    families = {re.split(r"[-_]", f.stem)[0] for f in (theme / "fonts").iterdir() if f.suffix == ".ttf"}
    assert families == {"LibreBaskerville", "PlayfairDisplay"}
    for paper in json.loads((theme / "handouts.json").read_text("utf-8"))["papers"]:
        for key in ("outline", "inner", "ink"):
            c = paper[key].lower()
            assert c[1:3] == c[3:5] == c[5:7], (paper["id"], key, c)


@pytest.mark.integration
def test_T_LOOK_11_new_plain_adventure_builds(session):
    """T-LOOK-11: a new adventure in Plain builds at once, and the two builds
    are identical (F7.8)."""
    session.new("Ny äventyr", *PLAIN_GS, *PLAIN_TH)
    first = _ok(session, session.build("pdf")).output[0]
    second = _ok(session, session.build("pdf")).output[0]
    assert first == second


# --- T-UI-26 the start-up checks (core part) -----------------------------------------------

@pytest.mark.unit
def test_T_UI_26_every_check_passes(home):
    """T-UI-26: with everything installed every check passes, in the order
    the window shows them, and the session and dictionaries are ready."""
    from scriptorum.core.startup import CHECKS, Startup

    startup = Startup()
    results = startup.run()
    assert [r.id for r in results] == list(CHECKS)
    assert all(r.ok for r in results), [(r.id, r.reason, r.details) for r in results if not r.ok]
    assert startup.ok and startup.can_continue
    assert startup.session is not None and startup.spelling.ready
    assert startup.spelling.correct("hello") and startup.spelling.correct("hej")


@pytest.mark.unit
def test_T_UI_26_missing_dictionary(home, tmp_path, monkeypatch):
    """T-UI-26: with a dictionary missing, that line is marked with the reason
    in plain words, and Continue anyway is possible; spell check then says it
    is unavailable instead of waiting."""
    from scriptorum.core.startup import Startup, bundled_strings, line_text, report_text
    from scriptorum.core.spelling import SpellChecker

    monkeypatch.setenv("SCRIPTORUM_DICTIONARIES", str(tmp_path / "none"))
    startup = Startup()
    startup.run()
    failed = startup.failed()
    assert [r.id for r in failed] == ["dictionaries"]
    assert startup.can_continue
    strings = bundled_strings()
    assert line_text(strings, failed[0]) == "Spelling dictionaries loaded: no dictionary was found"
    report = report_text(strings, startup.results, "0.5.1")
    assert "[FAILED]  Spelling dictionaries loaded" in report and report.count("[ok]") == 4
    checker = SpellChecker()
    checker.load_now()
    assert checker.unavailable == "dictionaries" and checker.ready
    assert checker.misspelled(["xyzzy"]) == []


@pytest.mark.unit
def test_T_UI_26_missing_library(home, monkeypatch):
    """T-UI-26: with the spylls or typst library missing, the line names the
    library: "Spelling dictionaries: the spylls library is not installed"."""
    import builtins

    from scriptorum.core.startup import Startup, bundled_strings, line_text

    real = builtins.__import__

    def without(name, *args, **kwargs):
        if name.split(".")[0] in ("spylls", "typst"):
            raise ImportError(name)
        return real(name, *args, **kwargs)

    startup = Startup()
    monkeypatch.setattr(builtins, "__import__", without)
    dictionaries = startup.check_dictionaries()
    typst_line = startup.check_typst()
    monkeypatch.setattr(builtins, "__import__", real)
    strings = bundled_strings()
    assert line_text(strings, dictionaries) == "Spelling dictionaries loaded: the spylls library is not installed"
    assert line_text(strings, typst_line) == "Typst can build a page: the typst library is not installed"
    assert not dictionaries.fatal and not typst_line.fatal


@pytest.mark.unit
def test_T_UI_26_folder_not_writable(home, monkeypatch):
    """T-UI-26: a folder that cannot be written to is named; the app cannot
    start without it."""
    import tempfile

    from scriptorum.core.startup import Startup

    def refuse(*args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", refuse)
    result = Startup().check_folders()
    assert not result.ok and result.fatal and result.details["folder"]


@pytest.mark.unit
def test_T_UI_26_strings_exist():
    """T-UI-26: every line of the start-up window comes from the interface
    language module (F15)."""
    from scriptorum.core.startup import CHECKS, bundled_strings

    strings = bundled_strings()
    source = (ROOT / "scriptorum" / "core" / "startup.py").read_text("utf-8")
    for key in set(re.findall(r'"(startup\.reason\.[A-Za-z]+)"', source)):
        assert key in strings, key
    for check in CHECKS:
        assert f"startup.check.{check}" in strings


@pytest.mark.integration
def test_T_UI_26_theme_self_test(session):
    """T-UI-26: Help ▸ Check installation can run the slower theme self-test:
    every theme with every game system it is offered for."""
    from scriptorum.core.startup import theme_self_test

    lines = theme_self_test(session)
    pairs = {(l["theme"], l["gameSystem"]) for l in lines}
    assert ("Plain", "Plain") in pairs and ("Plain", "Vaesen") in pairs and ("Vaesen", "Vaesen") in pairs
    assert ("Vaesen", "Plain") not in pairs
    assert all(l["ok"] for l in lines), [l for l in lines if not l["ok"]]


# --- T-UI-27 zoom remembered per adventure (core part) -------------------------------------

@pytest.mark.unit
def test_T_UI_27_zoom_kept_outside_the_file(tmp_path):
    """T-UI-27: the zoom is remembered for each adventure in the app's own
    folder, never in the .scav file; values are kept between 50 % and 400 %."""
    from scriptorum.core.viewstate import ViewState, clean_zoom

    assert clean_zoom(20) == 50 and clean_zoom(1000) == 400 and clean_zoom("125") == 125
    assert clean_zoom("whole-page") == "whole-page" and clean_zoom("nonsense") == "fit-width"
    state = ViewState(tmp_path / "view-state.json")
    assert state.get_zoom("/a.scav") == "fit-width"
    state.set_zoom("/a.scav", 150)
    state.set_zoom("/b.scav", "whole-page")
    state.set_zoom("unsaved-1", 75)
    again = ViewState(tmp_path / "view-state.json")
    assert again.get_zoom("/a.scav") == 150 and again.get_zoom("/b.scav") == "whole-page"
    assert again.get_zoom("unsaved-1") == "fit-width"  # an unsaved adventure is not written down
    (tmp_path / "view-state.json").write_text("not json", "utf-8")
    assert ViewState(tmp_path / "view-state.json").get_zoom("/a.scav") == "fit-width"
