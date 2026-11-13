"""Test Plan group BUILD — preview and export (3.3, F7)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from pypdf import PdfReader

from tests.conftest import ROOT

pytestmark = pytest.mark.integration

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


def _pdf_pages(data: bytes) -> list:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(data)).pages]


def test_T_BUILD_01_sample_to_pdf(session, sample, tmp_path):
    """T-BUILD-01: the sample adventure exports to a PDF with the expected pages."""
    session.open(sample("m1-basic"))
    reply = session.export_pdf(tmp_path / "out.pdf")
    assert reply["ok"], reply
    pages = _pdf_pages((tmp_path / "out.pdf").read_bytes())
    # The title page (F7.9, from M2), then the act heading with scene 1 on the
    # next page (F7.4, from M2); scene 2 switches the new page off.
    assert len(pages) == 2
    # M4: the title page and act headings print in the theme's display face,
    # without forced capitals (F8), so the text is compared in capitals.
    assert pages[0].upper() == "SKUGGAN ÖVER ÖDMÅRDEN"
    assert "ACT ONE: THE SILENT MILL" in pages[1].upper()
    assert "THE MILL" in pages[1].upper() and "THE CHURCH" in pages[1].upper()


def test_T_BUILD_02_identical_builds(session, sample):
    """T-BUILD-02: building the same adventure twice gives identical PDFs."""
    session.open(sample("m1-basic"))
    first = session.build("pdf")
    second = session.build("pdf")
    assert first.ok and second.ok
    assert first.output[0] == second.output[0]
    # Also identical from a fresh build folder (a new session).
    from scriptorum.core.session import Session

    other = Session(session.library, session.strings, session.recent, session.work_dir.parent / "other-build")
    other.open(session.adventure.path)
    assert other.build("pdf").output[0] == first.output[0]


def test_T_BUILD_04_error_on_authors_line(session):
    """T-BUILD-04: a Typst error is reported on the author's own line."""
    session.new("Errors", *GS, *TH)
    text = "= Errors\n\nFirst paragraph.\n\nSecond paragraph.\n\n#let broken = \n"
    session.set_chapter_text(0, text)
    result = session.build("png")
    assert not result.ok
    error = result.errors[0]
    assert error.chapter == "text/chapter-01.typ"
    assert error.line == 7
    assert session.localize(error).startswith("Line 7:")


def test_T_BUILD_07_build_never_changes_authors_files(session, sample):
    """T-BUILD-07: checksums of the adventure are unchanged after builds."""
    path = sample("m1-basic")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    session.open(path)
    in_memory = dict(session.adventure.files)
    session.build("png")
    session.build("pdf")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert session.adventure.files == in_memory


@pytest.mark.parametrize("escape", [
    '#read("/../../../../etc/hostname")',
    '#read("../../../../../../etc/hostname")',
    '#image("/../outside.png")',
])
def test_T_BUILD_08_typst_reads_only_the_build_folder(session, escape):
    """T-BUILD-08: a chapter cannot read files outside the build folder."""
    session.new("Escape", *GS, *TH)
    session.set_chapter_text(0, f"= Escape\n\n{escape}\n")
    result = session.build("pdf")
    assert not result.ok


def test_T_BUILD_08_no_internet_packages(session):
    """T-BUILD-08 (and D9): Typst packages from the internet are refused before compiling."""
    session.new("Packages", *GS, *TH)
    session.set_chapter_text(0, '= Packages\n\n#import "@preview/cetz:0.3.0"\n')
    result = session.build("pdf")
    assert not result.ok
    assert result.errors[0].key == "error.build.packagesNotAllowed"
    assert result.errors[0].line == 3


def _page_count(session, text: str) -> int:
    session.set_chapter_text(0, text)
    result = session.build("pdf")
    assert result.ok, [session.localize(e) for e in result.errors]
    return len(_pdf_pages(result.output[0]))


def test_T_BUILD_09_scenes_start_new_pages(session):
    """T-BUILD-09: every scene starts a new page unless switched off."""
    session.new("Pages", *GS, *TH)
    three = "= Pages\n\n#scene(title: \"One\")[\nText.\n]\n\n#scene(title: \"Two\")[\nText.\n]\n\n#scene(title: \"Three\")[\nText.\n]\n"
    assert _page_count(session, three) == 4  # title page + three scenes
    off = three.replace('#scene(title: "Two")', '#scene(title: "Two", new-page: false)')
    assert _page_count(session, off) == 3


# --- Milestone 2 -------------------------------------------------------------------

def _flat(data: bytes) -> list:
    """Page texts without spaces (labels are letter-spaced)."""
    return ["".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(data)).pages]


def test_T_BUILD_11_title_page(session):
    """T-BUILD-11: page 1 is the title page; empty fields are not printed; the
    extra row sits at the bottom; chapter text starts on page 2."""
    session.new("Ljuset under isen", *GS, *TH)
    session.set_chapter_text(0, "= Act one\n\n#scene(title: \"The lake\")[\nChapter text.\n]\n")
    session.set_settings({"titlePage": {
        "header": "A Vaesen mystery", "subtitle": "A winter night", "author": "Åsa Berg",
        "description": "The ice groans under your feet.", "extra": "For three to five characters.",
    }})
    result = session.build("pdf")
    assert result.ok, [session.localize(e) for e in result.errors]
    reader = PdfReader(io.BytesIO(result.output[0]))
    first = "".join(reader.pages[0].extract_text().split())
    for text in ("A VAESEN MYSTERY", "LJUSET UNDER ISEN", "A winter night", "Åsa Berg",
                 "The ice groans under your feet.", "For three to five characters."):
        assert "".join(text.split()).upper() in first.upper(), text
    assert "Chapter text." not in first
    assert "Chapter text." in reader.pages[1].extract_text()
    # The extra row is the lowest text on the page.
    positions = {}
    reader.pages[0].extract_text(visitor_text=lambda t, cm, tm, fd, fs: positions.setdefault(t.strip(), tm[5]) if t.strip() else None)
    extra_y = positions["For three to five characters."]
    assert all(y >= extra_y for y in positions.values())

    session.set_settings({"titlePage": {k: "" for k in ("header", "subtitle", "author", "description", "extra")}})
    pages = _pdf_pages(session.build("pdf").output[0])
    assert pages[0].upper() == "LJUSET UNDER ISEN"


def test_T_BUILD_12_act_heading_shares_the_scene_page(session):
    """T-BUILD-12: an act heading prints at the top of its first scene's page;
    no page holds only the act heading."""
    session.new("Acts", *GS, *TH)
    text = (
        "= Act one\n\n#scene(title: \"First\")[\nText.\n]\n\n#scene(title: \"Second\")[\nText.\n]\n\n"
        "= Act two\n\nA short introduction to the act.\n\n#scene(title: \"Third\")[\nText.\n]\n"
    )
    session.set_chapter_text(0, text)
    result = session.build("pdf")
    assert result.ok
    pages = _pdf_pages(result.output[0])
    assert len(pages) == 4  # title page + three scenes
    pages = [p.upper() for p in pages]  # M4: headings without forced capitals
    assert "ACT ONE" in pages[1] and "FIRST" in pages[1]
    assert "SECOND" in pages[2] and "ACT TWO" not in pages[2]
    assert "ACT TWO" in pages[3] and "THIRD" in pages[3] and "A SHORT INTRODUCTION" in pages[3]


def test_T_BUILD_13_every_vaesen_element(session, sample):
    """T-BUILD-13 (M2 acceptance): a sample using every Vaesen element builds
    without errors, and every element prints."""
    session.open(sample("m2-full"))
    used = {b["kind"] for chapter in range(len(session.adventure.chapters))
            for b in _walk(session.chapter(chapter)["doc"]["blocks"]) if b["type"] == "element"}
    # The elements Vaesen turned on in M2. From M3 the codex and map elements
    # are on too; sample m3-world uses those (test plan change log, 6 Nov 2026).
    m2_elements = {"scene", "read-aloud", "information", "person", "creature",
                   "countdown", "countdown-step", "dice", "check", "handout"}
    assert used == m2_elements
    assert "#dice(" in session.adventure.chapter_text("text/chapter-01.typ")
    result = session.build("pdf")
    assert result.ok, [session.localize(e) for e in result.errors]
    assert result.warnings == []
    flat = "".join(_flat(result.output[0]))
    for printed in (
        "THEBELLOFSKÄRVIK", "ACTONE:THEBELLINTHEFOG", "SCENE1", "THEHARBOUR", "READALOUD", "SECRET",
        "LOVISABERG", "WHATTHEYKNOW", "CHECK", "VIGILANCE·HARD", "D6", "DayEvent", "Mondaylovisaclosestheharbour".lower(),
        "COUNTDOWN·THENIGHTOFTHEBELL", "Dusk:", "THEDROWNEDBELL-RINGER", "MIGHT4", "BODYCONTROL2", "FEAR2",
        "SKILLS", "MAGICPOWERS", "ATTACKS", "WEAKNESSES", "CONDITIONS", "BANISHMENT", "HANDOUT", "Thesexton'snote",
        "Writtenby:NilsEk",
    ):
        assert printed.lower() in flat.lower(), printed


def test_T_BUILD_14_countdown_goes_to_a_scene(session, sample):
    """T-BUILD-14: a countdown step that goes to a scene prints the scene's
    number, title and page."""
    session.open(sample("m2-full"))
    flat = "".join(_flat(session.build("pdf").output[0])).replace("\u00ad", "").replace("-", "")  # a word may hyphenate
    assert "Midnight:Thesextonrunsdowntotheharbour.→Scene1,Theharbour,p.2" in flat


def test_T_BUILD_15_empty_element_warning(session):
    """T-BUILD-15: an element box left empty gives a warning on its line."""
    session.new("Empty", *GS, *TH)
    session.set_chapter_text(0, "= Empty\n\n#scene(title: \"S\")[\nText.\n\n#information(variant: \"hint\")[]\n]\n")
    result = session.build("pdf")
    assert result.ok
    warning = next(w for w in result.warnings if w.key == "warning.build.emptyElement")
    assert (warning.details, warning.chapter, warning.line) == ({"element": "information"}, "text/chapter-01.typ", 6)
    assert session.localize(warning) == "Line 6: Information is empty, so it prints only its label."


def _walk(blocks):
    for block in blocks:
        yield block
        if isinstance(block.get("body"), dict):
            yield from _walk(block["body"]["blocks"])
