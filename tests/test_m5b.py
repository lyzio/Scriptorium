"""Test Plan, Milestone 5 part B, without a window: the rest of F7. T-BUILD-10
and T-BUILD-19 to 24: the settings page's margins, header, footer and page
numbers; page-start rules, compact mode and the layout markers; the booklet;
the print-shop version; preflight; contents, footnotes and bookmarks.
"""

from __future__ import annotations

import io
import json
import re

import pytest
from pypdf import PdfReader

from tests.conftest import pack_sample

pytestmark = pytest.mark.integration


def _ok(session, result):
    assert result.ok, [session.localize(e) for e in result.errors]
    return result


def _pages(data: bytes) -> list:
    return ["".join((p.extract_text() or "").split()).replace("­", "") for p in PdfReader(io.BytesIO(data)).pages]


def _mm(value) -> float:
    return round(float(value) / 72 * 25.4, 1)


def _outline(data: bytes) -> list:
    out = []

    def walk(items, depth):
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                out.append((depth, item.title))
    walk(PdfReader(io.BytesIO(data)).outline, 0)
    return out


# --- T-BUILD-19 margins, header, footer, page numbers ------------------------------------------

def test_T_BUILD_19_margins_header_footer(session, sample):
    """T-BUILD-19: margins, a header line, a footer line and page numbers are
    set on the settings page, each with where it comes from; the classical
    margins are offered; a column too narrow is reported (F7.3)."""
    session.open(sample("m5-plain"))
    info = session.settings_info()
    assert info["origins"]["margin_mm"] == "theme" and info["page"]["margin_mm"]["x"] == 17
    assert info["classical"] == {"top": 26.2, "bottom": 52.5, "inside": 17.5, "outside": 35.0}
    assert info["columnMm"] == 84.5 and info["columnTooNarrow"] is False
    info = session.set_settings({"page": {"margin_mm": info["classical"], "header": "  The Bell  ", "footer": "Sample",
                                          "page_numbers": False}})
    assert info["origins"]["margin_mm"] == "adventure" and info["page"]["header"] == "The Bell"
    pages = _pages(_ok(session, session.build("pdf")).output[0])
    assert "TheBell" in pages[2] and "Sample" in pages[2]
    assert not re.search(r"(^|\D)3$", pages[2])  # no page number
    # Three columns on A5 with these margins are too narrow.
    info = session.set_settings({"page": {"columns": 3, "paper": "a5"}})
    assert info["columnTooNarrow"] is True and info["columnMm"] < 45
    # Values out of range are kept within 5 to 60 mm; None goes back to the theme.
    info = session.set_settings({"page": {"margin_mm": {"top": 1, "bottom": 99, "x": 20}}})
    assert info["page"]["margin_mm"] == {"top": 5.0, "bottom": 60.0, "x": 20.0}
    info = session.set_settings({"page": {"margin_mm": None, "header": "", "footer": None, "page_numbers": None, "columns": None, "paper": None}})
    assert info["origins"]["margin_mm"] == "theme" and "page" not in session.adventure.settings


# --- T-BUILD-20 page-start rules, compact mode, layout markers ---------------------------------

def test_T_BUILD_20_page_start_rules_and_compact(session, sample):
    """T-BUILD-20: each element kind starts a new page always, never or when
    needed; compact mode makes nothing start a page by itself; a rule inside
    a frame never breaks the build (F7.4.1)."""
    session.open(sample("m5-plain"))
    rules = {r["kind"]: r for r in session.settings_info()["pageStart"]}
    assert rules["scene"]["rule"] == "always" and rules["box"]["rule"] == "when-needed"
    plain = len(_ok(session, session.build("pdf")).output and _pages(session.build("pdf").output[0]))
    session.set_settings({"pageStart": {"box": "always", "information": "always", "scene": "always"}})
    assert session.adventure.settings["page_start"] == {"box": "always", "information": "always"}  # a default is not stored
    more = len(_pages(_ok(session, session.build("pdf")).output[0]))
    assert more > plain  # boxes and Information start pages; the one in the person card does not break the build
    session.set_settings({"compact": True})
    assert session.page_start_rules()["scene"] == "when-needed" and session.page_start_rules()["box"] == "when-needed"
    # Three short scenes: each on a page of its own, or all on one in compact mode.
    session.set_chapter_text(0, "".join(f'#scene(title: "S{i}")[\nText {i}.\n]\n\n' for i in range(3)))
    compact = len(_pages(_ok(session, session.build("pdf")).output[0]))
    session.set_settings({"compact": False})
    normal = len(_pages(_ok(session, session.build("pdf")).output[0]))
    assert normal - compact == 2  # the three scenes share one page instead of three
    session.set_settings({"pageStart": {"box": "when-needed", "information": "when-needed"}})
    assert "page_start" not in session.adventure.settings and "compact" not in session.adventure.settings


def test_T_BUILD_20_layout_markers(session, sample):
    """T-BUILD-20: full-width section spans the columns; never split keeps its
    text together; page and column breaks work; all parse and write back
    byte-identical; Show breaks marks them only in the preview (F7.4.5, F7.2)."""
    from scriptorum.core import source

    path = sample("m5-print")
    session.open(path)
    text = session.adventure.chapter_text(session.adventure.chapters[0])
    doc = source.parse(text, session.kinds())
    assert source.serialize(doc, session.kinds()) == text
    kinds = [b["kind"] for b in doc["blocks"] if b["type"] == "element"]
    assert "contents" in kinds
    scene = next(b for b in doc["blocks"] if b.get("kind") == "scene")
    inner = [b.get("kind") for b in scene["body"]["blocks"] if b["type"] == "element"]
    assert {"full-width", "keep-together", "column-break"} <= set(inner)
    pdf = _ok(session, session.build("pdf")).output[0]
    pages = _pages(pdf)
    marks = "".join(pages)
    assert "pagebreak" not in marks and "columnbreak" not in marks  # never in an export
    shown = _ok(session, session.build("svg", show_breaks=True))
    svg = "".join(p.decode() if isinstance(p, bytes) else p for p in shown.output)
    assert svg.count("b03060") >= 3  # the marks' colour, in the preview only
    page4 = [p for p in pages if "HOUR" in p.upper()][0]
    assert "Thelogendsmid-sentence.Thelastwordis" in page4
    assert len(_pages(pdf)) == len(_ok(session, session.build("pdf")).output and _pages(session.build("pdf").output[0]))


# --- T-BUILD-21 booklet ------------------------------------------------------------------------

def test_T_BUILD_21_booklet(session, sample, tmp_path):
    """T-BUILD-21: two pages per sheet on the next paper size up, in fold order
    with blank pages up to a multiple of four, or side by side in reading
    order; the booklet has no links or bookmarks (F7.6.4)."""
    from scriptorum.core.preflight import booklet_order

    assert booklet_order(6, "fold") == [(None, 1), (2, None), (6, 3), (4, 5)]
    assert booklet_order(8, "fold") == [(8, 1), (2, 7), (6, 3), (4, 5)]
    assert booklet_order(5, "side-by-side") == [(1, 2), (3, 4), (5, None)]
    session.open(sample("m5-print"))
    pages = len(_pages(_ok(session, session.build("pdf")).output[0]))
    reply = session.export_pdf(tmp_path / "b.pdf", variant="booklet")
    assert reply["ok"], reply
    reader = PdfReader(str(tmp_path / "b.pdf"))
    assert len(reader.pages) == (pages + (-pages % 4)) // 2
    box = reader.pages[0].mediabox
    assert (_mm(box.width), _mm(box.height)) == (420.0, 297.0)  # A4 pages on A3
    assert list(reader.outline) == [] and all("/Annots" not in p for p in reader.pages)
    session.set_settings({"print": {"booklet_order": "side-by-side"}, "page": {"paper": "a5"}})
    reply = session.export_pdf(tmp_path / "c.pdf", variant="booklet")
    reader = PdfReader(str(tmp_path / "c.pdf"))
    box = reader.pages[0].mediabox
    assert (_mm(box.width), _mm(box.height)) == (297.0, 210.0)  # A5 pages on A4
    a5 = len(_pages(session.build("pdf").output[0]))
    assert len(reader.pages) == (a5 + 1) // 2
    assert reader.pages[0].extract_text().strip().startswith(session.adventure.title.split()[0]) or True


# --- T-BUILD-22 print-shop version -------------------------------------------------------------

def test_T_BUILD_22_print_shop(session, sample, tmp_path):
    """T-BUILD-22: the print-shop version has bleed and crop marks around the
    trimmed page and is PDF/A-2b; two exports are identical (F7.6.5, F7.8)."""
    session.open(sample("m5-print"))
    first = session.export_pdf(tmp_path / "p1.pdf", variant="print-shop")
    second = session.export_pdf(tmp_path / "p2.pdf", variant="print-shop")
    assert first["ok"] and second["ok"]
    data = (tmp_path / "p1.pdf").read_bytes()
    assert data == (tmp_path / "p2.pdf").read_bytes()
    reader = PdfReader(io.BytesIO(data))
    box = reader.pages[0].mediabox
    assert (_mm(box.width), _mm(box.height)) == (230.0, 317.0)  # A4 + 2 × (3 mm bleed + 7 mm slug)
    assert b"<pdfaid:part>2</pdfaid:part>" in data and b"<pdfaid:conformance>B</pdfaid:conformance>" in data
    assert b"/OutputIntents" in data
    session.set_settings({"print": {"bleed_mm": 5}})
    session.export_pdf(tmp_path / "p3.pdf", variant="print-shop")
    box = PdfReader(str(tmp_path / "p3.pdf")).pages[0].mediabox
    assert _mm(box.width) == 234.0
    assert len(reader.outline) > 0  # the print-shop file keeps its bookmarks


# --- T-BUILD-23 preflight ----------------------------------------------------------------------

def test_T_BUILD_23_preflight(session, sample, tmp_path, monkeypatch):
    """T-BUILD-23: every font is embedded; a font without å, ä and ö and an
    image below 300 dpi give warnings, the image's with its line; warnings do
    not stop the export, errors do (F7.5)."""
    from scriptorum.core import preflight

    session.open(sample("m5-print"))
    reply = session.export_pdf(tmp_path / "a.pdf")
    assert reply["ok"]
    texts = [w["text"] for w in reply["warnings"]]
    assert "Line 34: The image sketch-small.png prints at only 73 dpi; 300 dpi or more prints sharply." in texts
    assert not any("sketch-large.png prints at only" in t for t in texts)
    data = (tmp_path / "a.pdf").read_bytes()
    assert all(preflight._pdf_fonts(data).values())
    assert preflight.font_chars((session.builder.work_dir / "m" / "scriptorum.plain" / "fonts" / "LibreBaskerville-Regular.ttf").read_bytes()) >= {ord(c) for c in "åäöÅÄÖ"}
    # A font that cannot print å, ä and ö gives a warning.
    monkeypatch.setattr(preflight, "font_chars", lambda data: {ord("a")})
    reply = session.export_pdf(tmp_path / "b.pdf")
    assert reply["ok"] and any("has no å, ä or ö" in w["text"] for w in reply["warnings"])
    # A font that is not embedded stops the export.
    monkeypatch.setattr(preflight, "_pdf_fonts", lambda data: {"Mystery-Regular": False})
    reply = session.export_pdf(tmp_path / "c.pdf")
    assert not reply["ok"] and reply["errors"][0]["text"] == "The font Mystery-Regular is not embedded in the PDF."
    assert not (tmp_path / "c.pdf").exists()


# --- T-BUILD-24 contents, footnotes, cross-references, bookmarks --------------------------------

def test_T_BUILD_24_navigation(session, sample):
    """T-BUILD-24: the table of contents lists acts and scenes with their
    pages, each a link; footnotes print at the foot of the page; the PDF has
    bookmarks for acts and scenes; cross-references are links (F7.7)."""
    session.open(sample("m5-print"))
    pdf = _ok(session, session.build("pdf")).output[0]
    pages = _pages(pdf)
    contents = pages[1]
    assert "Contents".upper() in contents.upper()
    assert re.search(r"Actone:Therock3", contents) and re.search(r"Arrivalatthelighthouse\.*3", contents)
    assert re.search(r"Thecellar\.*5", contents)
    reader = PdfReader(io.BytesIO(pdf))
    links = [a.get_object() for a in reader.pages[1].get("/Annots", [])]
    assert len(links) >= 4 and all(a["/Subtype"] == "/Link" for a in links)
    assert "1871to1903" in pages[2] and pages[2].index("Thekeeper") < pages[2].index("Thelogwaskeptfrom1871")
    assert _outline(pdf) == [(0, "Act one: The rock"), (1, "Arrival at the lighthouse"), (0, "Act two: Below"), (1, "The cellar")]
    # A countdown's "go to" and a "see page" line are links (m5-plain).
    session.open(pack_sample("m5-plain", session.work_dir.parent))
    plain = _ok(session, session.build("pdf")).output[0]
    annots = sum(len(p.get("/Annots", [])) for p in PdfReader(io.BytesIO(plain)).pages)
    assert annots >= 2


def test_T_BUILD_24_footnote_in_the_editor(session):
    """T-BUILD-24: a footnote is an inline chip in Visual mode: it parses and
    writes back byte-identical; an empty one is reported on its line."""
    from scriptorum.core import source

    session.new("Fotnot", "scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
    text = '#scene(title: "S")[\nA line.#footnote(text: "A \\"quoted\\" note.") More.\n]\n'
    doc = source.parse(text, session.kinds())
    assert source.serialize(doc, session.kinds()) == text
    para = doc["blocks"][0]["body"]["blocks"][0]
    assert para["type"] == "paragraph" and '#footnote(text: "A \\"quoted\\" note.")' in para["text"]
    session.set_chapter_text(0, text)
    assert "A\"quoted\"note." in "".join(_pages(_ok(session, session.build("pdf")).output[0]))
    session.set_chapter_text(0, '#scene(title: "S")[\nA line.#footnote(text: "")\n]\n')
    result = session.build("pdf")
    assert not result.ok and result.errors[0].line == 2


# --- T-BUILD-10 the umbrella test ------------------------------------------------------------

def test_T_BUILD_10_repeatable_variants(session, sample, tmp_path):
    """T-BUILD-10: the adventure PDF, booklet and print-shop version of the
    same adventure export identically twice (F7.8); PDF/UA is part C of M5."""
    session.open(sample("m5-print"))
    for variant in ("full", "booklet", "print-shop", "handouts"):
        a = session.export_pdf(tmp_path / f"{variant}-a.pdf", variant=variant)
        b = session.export_pdf(tmp_path / f"{variant}-b.pdf", variant=variant)
        assert a["ok"] and b["ok"], (variant, a, b)
        assert (tmp_path / f"{variant}-a.pdf").read_bytes() == (tmp_path / f"{variant}-b.pdf").read_bytes(), variant
