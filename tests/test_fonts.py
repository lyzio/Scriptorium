"""Test Plan group FONT — the font guard (F11)."""

from __future__ import annotations

import struct

import pytest

from scriptorum.core import fonts
from scriptorum.core.fonts import FontRefused

GS = ("scriptorum.free-league-vaesen", "1.0.0")
TH = ("scriptorum.vaesen", "1.0.0")

OFL = "This Font Software is licensed under the SIL Open Font License, Version 1.1."
OFL_URL = "https://openfontlicense.org"


def make_font(names: dict) -> bytes:
    """A minimal OpenType file holding only a ``name`` table, which is all
    the font guard reads (name IDs: 1 family, 13 licence, 14 licence URL)."""
    records, storage = [], b""
    for name_id, text in sorted(names.items()):
        data = text.encode("utf-16-be")
        records.append(struct.pack(">HHHHHH", 3, 1, 0x409, name_id, len(data), len(storage)))
        storage += data
    table = struct.pack(">HHH", 0, len(records), 6 + 12 * len(records)) + b"".join(records) + storage
    header = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 16, 0, 0)
    directory = b"name" + struct.pack(">III", 0, 12 + 16, len(table))
    return header + directory + table


@pytest.mark.unit
def test_T_FONT_01_open_licence_accepted(session, tmp_path):
    """T-FONT-01: an OFL or Apache font is copied with a licence file."""
    session.new("Fonts", *GS, *TH)
    folder = tmp_path / "fonts"
    folder.mkdir()
    ofl = folder / "Quill Hand.ttf"
    ofl.write_bytes(make_font({1: "Quill Hand", 13: OFL, 14: OFL_URL}))
    (folder / "OFL.txt").write_text("SIL OPEN FONT LICENSE Version 1.1 — full text")
    result = session.add_font(ofl)
    assert result == {"file": "assets/fonts/Quill-Hand.ttf", "family": "Quill Hand", "licence": "OFL-1.1"}
    assert session.adventure.files["assets/fonts/Quill-Hand.ttf"] == ofl.read_bytes()
    assert session.adventure.files["assets/fonts/Quill-Hand-LICENSE.txt"].startswith(b"SIL OPEN FONT LICENSE")

    apache = tmp_path / "Ink.otf"  # no licence file next to it: the embedded text is stored
    apache.write_bytes(make_font({1: "Ink", 13: "Licensed under the Apache License, Version 2.0", 14: "http://www.apache.org/licenses/LICENSE-2.0"}))
    assert session.add_font(apache)["licence"] == "Apache-2.0"
    assert b"Apache License" in session.adventure.files["assets/fonts/Ink-LICENSE.txt"]
    # The handout's handwriting choice now offers the added fonts (11.9).
    options = [o["id"] for o in session.choice_options("handwriting")]
    # The six hands of the core element kit come first (F8, M4), then the
    # added fonts, alphabetical.
    assert options == ["Homemade Apple", "Pinyon Script", "Dancing Script", "Caveat", "Cedarville Cursive",
                       "TT2020 Style E", "Ink", "Quill Hand"]
    assert session.dirty


@pytest.mark.unit
@pytest.mark.parametrize("names, reason", [
    ({1: "Shop Sans", 13: "Copyright Big Foundry. All rights reserved. Licensed for desktop use only."}, "error.font.notOpen"),
    ({1: "Mystery"}, "error.font.noLicence"),
])
def test_T_FONT_02_other_fonts_refused(session, tmp_path, names, reason):
    """T-FONT-02: a font without an open licence is refused with a plain
    explanation, and nothing is copied."""
    session.new("Refused", *GS, *TH)
    font = tmp_path / "Font.ttf"
    font.write_bytes(make_font(names))
    before = dict(session.adventure.files)
    with pytest.raises(FontRefused) as info:
        session.add_font(font)
    assert info.value.key == reason
    assert session.adventure.files == before
    text = session.t(info.value.key, **info.value.details)
    assert "Font.ttf" in text and "open licence" in text
    # Something that is not a font at all.
    other = tmp_path / "notes.txt"
    other.write_text("hello")
    with pytest.raises(FontRefused) as info:
        session.add_font(other)
    assert info.value.key == "error.font.notFont"


@pytest.mark.integration
def test_T_FONT_03_checked_again_at_export(session, tmp_path):
    """T-FONT-03: a stored font that does not pass the guard stops the export."""
    session.new("Export check", *GS, *TH)
    session.adventure.files["assets/fonts/Closed.ttf"] = make_font({1: "Closed", 13: "All rights reserved."})
    reply = session.export_pdf(tmp_path / "out.pdf")
    assert not reply["ok"]
    assert "Closed.ttf" in reply["errors"][0]["text"]
    assert not (tmp_path / "out.pdf").exists()
    del session.adventure.files["assets/fonts/Closed.ttf"]
    assert session.export_pdf(tmp_path / "out.pdf")["ok"]


@pytest.mark.unit
def test_font_name_table_reader():
    """The name-table reader understands the entries the guard uses."""
    names = fonts.read_names(make_font({1: "Åsa Script", 13: OFL}))
    assert names[1] == "Åsa Script" and names[13] == OFL
    assert fonts.check_font(b"not a font").reason == "error.font.notFont"
