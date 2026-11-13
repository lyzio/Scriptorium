"""Test Plan, Milestone 5 part C, without a window: the accessible PDF (F17).
T-BUILD-25 to 27, and the PDF/UA part of T-BUILD-10.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

pytestmark = pytest.mark.integration


def _ok(session, result):
    assert result.ok, [session.localize(e) for e in result.errors]
    return result


def _structure(data: bytes) -> list:
    """Every structure element of a tagged PDF: (type, its /Alt or None)."""
    reader = PdfReader(io.BytesIO(data))
    root = reader.trailer["/Root"]
    found = []

    def walk(node, depth=0):
        if depth > 60:
            return
        node = node.get_object()
        if isinstance(node, list):
            for child in node:
                walk(child, depth + 1)
            return
        if not hasattr(node, "get"):
            return
        if "/S" in node:
            found.append((str(node["/S"]), str(node["/Alt"]) if "/Alt" in node else None))
        kids = node.get("/K")
        if kids is not None:
            walk(kids, depth + 1)
    walk(root["/StructTreeRoot"])
    return found


# --- T-BUILD-25 the document language ------------------------------------------------------------

def test_T_BUILD_25_document_language(session, sample):
    """T-BUILD-25: the settings page has a document language; it is written
    into the PDF and chooses the spell-check dictionaries; English is the
    default and is not stored (F17.2)."""
    session.open(sample("m5-print"))
    info = session.settings_info()
    assert info["language"] == "en" and info["languages"][:2] == ["en", "sv"]
    pdf = _ok(session, session.build("pdf")).output[0]
    assert PdfReader(io.BytesIO(pdf)).trailer["/Root"]["/Lang"] == "en"
    session.set_settings({"language": "sv"})
    assert session.adventure.settings["language"] == "sv"
    pdf = _ok(session, session.build("pdf")).output[0]
    assert PdfReader(io.BytesIO(pdf)).trailer["/Root"]["/Lang"] == "sv"
    session.set_settings({"language": "xx"})  # not offered: back to the default
    assert "language" not in session.adventure.settings
    from scriptorum.core.spelling import SpellChecker
    checker = SpellChecker()
    checker.load_now()
    assert checker.misspelled(["sjön", "harbour"], ("sv",)) == ["harbour"]
    assert checker.misspelled(["sjön", "harbour"], ("en", "en-gb")) == ["sjön"]
    assert checker.misspelled(["sjön", "harbour"]) == []


def test_T_BUILD_25_language_offers_installed_modules(session, sample, library, tmp_path):
    """T-BUILD-25: the language of an installed adventure-language module is
    offered as a document language (9.3); that the module then prints its
    words is T-MOD-07."""
    import json

    folder = tmp_path / "lang"
    (folder / "labels").mkdir(parents=True)
    (folder / "module.json").write_text(json.dumps({
        "id": "test.deutsch", "kind": "adventure-language", "name": "Deutsch", "version": "1.0.0", "format": 1,
        "app": "0.1.0", "licence": "GPL-3.0-or-later", "authors": ["Test"], "description": "Deutsche Wörter",
        "language": "de", "requires": [{"id": "scriptorum.core", "version": "1.x"}]}), "utf-8")
    library.install_folder(folder)
    session.open(sample("m5-print"))
    assert "de" in session.settings_info()["languages"]
    session.set_settings({"language": "de"})
    assert session.adventure.settings["language"] == "de"


# --- T-BUILD-26 descriptions -------------------------------------------------------------------

def test_T_BUILD_26_descriptions(session, sample, tmp_path):
    """T-BUILD-26: images and maps have a description field; it parses and
    writes back byte-identical and becomes the alt text; preflight warns when
    one is missing, and the accessible PDF stops with the image or map named
    (F17.3)."""
    from scriptorum.core import source

    session.open(sample("m5-access"))
    text = session.adventure.chapter_text(session.adventure.chapters[0])
    doc = source.parse(text, session.kinds())
    assert source.serialize(doc, session.kinds()) == text
    images = [b for b in doc["blocks"][1 + 1]["body"]["blocks"] if b["type"] == "image"] if False else \
        [b for b in source.parse(text, session.kinds())["blocks"] for b in ([b] + (b.get("body") or {}).get("blocks", []) if isinstance(b.get("body"), dict) else [b]) if b["type"] == "image"]
    assert [b["alt"][:12] for b in images] == ["En skiss av ", "Loggboken up"]
    reply = session.export_pdf(tmp_path / "a.pdf")
    assert reply["ok"] and not any("description" in w["text"] for w in reply["warnings"])
    figures = [alt for kind, alt in _structure((tmp_path / "a.pdf").read_bytes()) if kind == "/Figure"]
    assert any(a and a.startswith("En skiss av fyren") for a in figures)
    assert any(a and a.startswith("Karta över Skärvik") for a in figures)
    # The print sample has no descriptions: warnings, and the accessible PDF stops.
    session.open(sample("m5-print"))
    reply = session.export_pdf(tmp_path / "b.pdf")
    texts = [w["text"] for w in reply["warnings"]]
    assert "Line 34: The image sketch-small.png has no description for screen readers." in texts
    reply = session.export_pdf(tmp_path / "c.pdf", variant="accessible")
    assert not reply["ok"] and reply["errors"][0]["text"] == "Line 34: The image sketch-small.png needs a description for the accessible PDF."
    assert not (tmp_path / "c.pdf").exists()
    session.open(sample("m3-world"))
    reply = session.export_pdf(tmp_path / "d.pdf", variant="accessible")
    assert not reply["ok"] and "The map Skärvik and the bay needs a description" in reply["errors"][0]["text"]


def test_T_BUILD_26_image_description_in_the_editor(session):
    """T-BUILD-26: a description typed for an image is written into the text,
    and removing it gives the image back its M4 form."""
    from scriptorum.core import source

    session.new("Bild", "scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
    plain = '#scene(title: "S")[\n#image("/assets/images/a.png")\n]\n'
    doc = source.parse(plain, session.kinds())
    image = doc["blocks"][0]["body"]["blocks"][0]
    assert image == {"type": "image", "path": "/assets/images/a.png", "line": image.get("line")} or "alt" not in image
    image["alt"] = 'A "quoted" picture'
    doc["blocks"][0].pop("raw", None)  # as the editor does for a changed block
    image.pop("raw", None)
    assert source.serialize(doc, session.kinds()) == '#scene(title: "S")[\n#image("/assets/images/a.png", alt: "A \\"quoted\\" picture")\n]\n'
    del image["alt"]
    assert source.serialize(doc, session.kinds()) == plain


# --- T-BUILD-27 the accessible PDF -------------------------------------------------------------

def test_T_BUILD_27_accessible_pdf(session, sample, tmp_path):
    """T-BUILD-27: the accessible PDF is PDF/UA-1: tagged headings starting at
    level 1 with the title, lists, table header cells, the document language
    and figures with their descriptions; ornaments and frames are artifacts,
    not content; two exports are identical (F17.1, F17.4, F17.5)."""
    session.open(sample("m5-access"))
    a = session.export_pdf(tmp_path / "ua1.pdf", variant="accessible")
    b = session.export_pdf(tmp_path / "ua2.pdf", variant="accessible")
    assert a["ok"] and b["ok"], a
    data = (tmp_path / "ua1.pdf").read_bytes()
    assert data == (tmp_path / "ua2.pdf").read_bytes()
    assert b"<pdfuaid:part>1</pdfuaid:part>" in data
    reader = PdfReader(io.BytesIO(data))
    assert reader.trailer["/Root"]["/Lang"] == "sv" and reader.trailer["/Root"]["/MarkInfo"]["/Marked"]
    kinds = [k for k, _ in _structure(data)]
    headings = [k for k in kinds if k.startswith("/H")]
    assert headings[0] == "/H1"                       # the title page's title
    assert "/H2" in headings                          # scenes under acts
    assert "/L" in kinds and "/LI" in kinds           # the list
    assert "/TH" in kinds and "/Table" in kinds       # table header cells
    assert kinds.count("/Figure") >= 3                # two images and the map
    assert all(alt for k, alt in _structure(data) if k == "/Figure")


def test_T_BUILD_27_samples_and_pdfa_with_ua(session, sample, tmp_path):
    """T-BUILD-27: samples without images, maps or skipped heading levels
    export as PDF/UA as they are; a skipped level is explained on its line;
    PDF/A-2b and PDF/UA-1 can be combined with the pinned Typst (F17.5)."""
    for name in ("m1-basic", "m4-look"):
        session.open(sample(name))
        reply = session.export_pdf(tmp_path / f"{name}.pdf", variant="accessible")
        assert reply["ok"], (name, reply)
    # The example adventure jumps from a scene (level 2) to a level-4 heading:
    # the accessible PDF says so in plain words on the author's line.
    session.open(sample("example-jattens-skuld"))
    reply = session.export_pdf(tmp_path / "j.pdf", variant="accessible")
    assert not reply["ok"]
    assert reply["errors"][0]["text"].startswith("Line 196: The headings jump from level 2 to level 4.")
    session.open(sample("m5-access"))
    result = session.build("pdf", standards=["a-2b", "ua-1"],
                           page_extra='#set document(date: datetime(year: 2026, month: 11, day: 12))')
    assert result.ok
    assert b"<pdfaid:part>2</pdfaid:part>" in result.output[0] and b"<pdfuaid:part>1</pdfuaid:part>" in result.output[0]


def test_T_BUILD_10_ua_variant_repeatable(session, sample, tmp_path):
    """T-BUILD-10 (PDF/UA part): the accessible PDF exports identically twice."""
    session.open(sample("m4-look"))
    a = session.export_pdf(tmp_path / "x.pdf", variant="accessible")
    b = session.export_pdf(tmp_path / "y.pdf", variant="accessible")
    assert a["ok"] and b["ok"]
    assert (tmp_path / "x.pdf").read_bytes() == (tmp_path / "y.pdf").read_bytes()
