"""Test Plan group SRC — source format and editor (D11, F4)."""

from __future__ import annotations

import io
import json

import pytest

from scriptorum.core import source
from tests.conftest import sample_text

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")


@pytest.fixture
def kinds(session):
    session.new("Kinds", *GS, *TH)
    return session.kinds()


def _walk(blocks):
    for block in blocks:
        yield block
        if isinstance(block.get("body"), dict):
            yield from _walk(block["body"]["blocks"])


@pytest.mark.unit
@pytest.mark.parametrize("name", ["m1-basic", "m1-locked"])
def test_T_SRC_01_round_trip(kinds, name):
    """T-SRC-01: parse each sample chapter and write it back unchanged."""
    text = sample_text(name)
    assert source.serialize(source.parse(text, kinds), kinds) == text


@pytest.mark.unit
def test_T_SRC_02_elements(kinds):
    """T-SRC-02: each M1 element has the right kind, fields, variant and body."""
    doc = source.parse(sample_text("m1-basic"), kinds)
    elements = [b for b in _walk(doc["blocks"]) if b["type"] == "element"]
    by_kind = {}
    for block in elements:
        by_kind.setdefault(block["kind"], []).append(block)
    scene = by_kind["scene"][0]
    assert scene["fields"] == {"title": "The mill", "location": "Ödmården, the old mill", "present": "Miller Elsa"}
    assert by_kind["scene"][1]["new_page"] is False
    assert "The wheel has stopped" in by_kind["read-aloud"][0]["body"]
    assert [b["variant"] for b in by_kind["information"]] == ["secret", "secret", "public", "hint"]
    person = by_kind["person"][0]
    assert person["fields"]["name"] == "Miller Elsa"
    assert person["fields"]["mood"] == "Frightened, keeps the door barred"
    assert person["fields"]["description"].startswith("Widowed this summer")
    assert [b["kind"] for b in person["body"]["blocks"]] == ["information", "information"]


@pytest.mark.unit
def test_T_SRC_03_unknown_code_is_locked(kinds):
    """T-SRC-03: unknown Typst is a locked block, written back unchanged."""
    text = sample_text("m1-locked")
    doc = source.parse(text, kinds)
    locked = [b for b in _walk(doc["blocks"]) if b["type"] == "locked"]
    raws = [b["raw"] for b in locked]
    assert any(r.startswith("#let flourish") for r in raws)
    assert any(r.startswith("// A comment") for r in raws)
    assert any(r.startswith("#table(") for r in raws)
    assert any(r.startswith("- A list item") for r in raws)
    assert any("#emph[inline code]" in r for r in raws)
    # Editing a neighbouring block never changes a locked block.
    doc["blocks"][1]["text"] = "An edited paragraph."
    source.mark_changed(doc["blocks"][1])
    out = source.serialize(doc, kinds)
    for raw in raws:
        assert raw in out


@pytest.mark.unit
@pytest.mark.parametrize("plain", [
    "Price: 5 $ or 10 % off, mail@example.com",
    "Use *stars* and _underscores_ and #hashes",
    "Brackets [like this] and <label> and `code`",
    "- not a list",
    "= not a heading",
    "1. not a numbered list",
    "a // not a comment, a/b and C:\\path",
    "Swedish: Åsa, Märta, Örjan ~ tilde",
])
def test_T_SRC_04_escaping(plain):
    """T-SRC-04: typed text is escaped so Typst prints exactly what was typed."""
    import typst
    from pypdf import PdfReader

    markup = source.escape_inline(plain)
    assert source.inline_ok(markup)
    assert source.inline_to_plain(markup) == " ".join(plain.split())
    # The printed text equals the typed text.
    pdf = typst.compile(("#set page(width: 40cm)\n" + markup).encode(), format="pdf", ignore_system_fonts=True)
    printed = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert " ".join(printed.split()) == " ".join(plain.split())


@pytest.mark.unit
def test_T_SRC_05_bold_and_italic(kinds):
    """T-SRC-05: bold and italic are written as Typst markup and read back."""
    import typst

    markup = "Plain, *bold* and _italic_ and *_both_*."
    assert source.inline_ok(markup)
    strong = json.loads(typst.query(markup.encode(), "strong"))
    emph = json.loads(typst.query(markup.encode(), "emph"))
    assert len(strong) == 2 and len(emph) == 2
    block = source.parse(markup + "\n", kinds)["blocks"][0]
    assert (block["type"], block["text"]) == ("paragraph", markup)


@pytest.mark.integration
def test_T_SRC_08_required_field_reported_on_line(session):
    """T-SRC-08: an empty required field is reported on the author's line."""
    session.new("Required", *GS, *TH)
    text = "= Required\n\nIntro.\n\n#scene(title: \"Ok\")[\n#person(mood: \"Calm\")[\n]\n]\n"
    session.set_chapter_text(0, text)
    result = session.build("pdf")
    assert not result.ok
    error = result.errors[0]
    assert error.key == "error.build.requiredField"
    assert error.details == {"element": "person", "field": "name"}
    assert error.chapter == "text/chapter-01.typ"
    assert error.line == 6
    assert session.localize(error) == "Line 6: Person: “Name” must be filled in."


@pytest.mark.integration
def test_T_SRC_09_information_inside_person(session):
    """T-SRC-09: an Information line inside a person card is shown under
    'What they know' on that card."""
    from pypdf import PdfReader

    session.new("Knows", *GS, *TH)
    text = (
        "#scene(title: \"Mill\")[\n"
        "#person(name: \"Miller Elsa\", mood: \"Afraid\")[\n"
        "#information(variant: \"secret\")[She saw a light under the water.]\n"
        "]\n]\n"
    )
    session.set_chapter_text(0, text)
    result = session.build("pdf")
    assert result.ok, [session.localize(e) for e in result.errors]
    pdf_text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(result.output[0])).pages)
    # Labels are letter-spaced, so compare without spaces.
    flat = "".join(pdf_text.split())
    assert "WHATTHEYKNOW" in flat
    assert flat.index("MILLERELSA") < flat.index("WHATTHEYKNOW") < flat.index("SECRET") < flat.index("Shesawalightunderthewater.")


@pytest.mark.unit
def test_T_SRC_12_m2_elements_tables_and_images(kinds):
    """T-SRC-12: every M2 element, a table and an image parse with the right
    fields, and unchanged text is written back byte-identical."""
    text = sample_text("m2-full")
    doc = source.parse(text, kinds)
    assert source.serialize(doc, kinds) == text
    blocks = list(_walk(doc["blocks"]))
    assert not [b for b in blocks if b["type"] == "locked"]
    by_kind = {}
    for block in blocks:
        by_kind.setdefault(block.get("kind") or block["type"], []).append(block)
    creature = by_kind["creature"][0]
    assert creature["fields"]["might"] == 4 and creature["fields"]["fear"] == 2
    assert creature["fields"]["type"] == "Vaesen"
    assert creature["fields"]["banishment"].startswith("Ring the chapel bell")
    steps = by_kind["countdown-step"]
    assert [s["fields"].get("when") for s in steps] == ["Dusk", "Midnight", None]
    assert steps[1]["fields"]["go-to"] == "s-harbour"
    assert by_kind["scene"][0]["fields"]["id"] == "s-harbour"
    dice = by_kind["dice"][0]
    assert dice["fields"] == {"dice": "D6"} and dice["body"].startswith("Roll each round")
    check = by_kind["check"][0]
    assert check["fields"] == {"roll": "Vigilance", "difficulty": "hard"}
    handout = by_kind["handout"][0]
    assert handout["fields"]["title"] == "The sexton's note" and handout["fields"]["written-by"] == "Nils Ek"
    # Inline dice stay inside their paragraph (11.7).
    inline = [b for b in by_kind["paragraph"] if "#dice(" in b["text"]]
    assert len(inline) == 1 and '#dice(dice: "D6", face: 6)' in inline[0]["text"]
    table = by_kind["table"][0]
    assert (table["columns"], table["header"], table["rows"][1]) == (2, ["Day", "Event"], ["Monday", "Lovisa closes the harbour"])
    assert by_kind["image"][0]["path"] == "/assets/images/bell.png"

    # Edited blocks are written in the canonical form and read back the same.
    table["rows"].append(["Tues\\*day", "*Fog*"])
    creature["fields"]["might"] = 5
    creature.pop("head_raw")  # as the editor does when a field changes
    for block in (table, creature, by_kind["scene"][1]):
        source.mark_changed(block)
    for scene in by_kind["scene"]:
        scene.pop("raw", None)  # an edited block changes the scene around it too
    again = source.parse(source.serialize(doc, kinds), kinds)
    again_blocks = list(_walk(again["blocks"]))
    assert next(b for b in again_blocks if b["type"] == "table")["rows"][-1] == ["Tues\\*day", "*Fog*"]
    assert next(b for b in again_blocks if b.get("kind") == "creature")["fields"]["might"] == 5
    # A countdown step outside a countdown is not recognised (11.6).
    loose = source.parse('#countdown-step[Alone.]\n', kinds)
    assert loose["blocks"][0]["type"] == "locked"
    # A table not in the canonical form stays locked (as in m1-locked).
    assert source.parse("#table(columns: 2, [A], [B])\n", kinds)["blocks"][0]["type"] == "locked"
