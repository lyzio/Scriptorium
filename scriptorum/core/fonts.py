"""Font guard (design document F11, D7).

Every font in an adventure may legally be shared. When a font is added, its
embedded licence information (the OpenType ``name`` table, entries 13 and 14)
is read. Fonts under an open licence, SIL OFL or Apache 2.0, are copied into
the adventure's ``assets/fonts/`` together with a licence file. Any other font
is refused with a plain explanation. The licence is checked again at export
(F11.4).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

FONT_SUFFIXES = {".ttf", ".otf"}

OPEN_LICENCES = {
    "OFL-1.1": re.compile(r"SIL\s+Open\s+Font\s+Licen[cs]e|scripts\.sil\.org/OFL|openfontlicense\.org|\bOFL\b", re.I),
    "Apache-2.0": re.compile(r"Apache\s+Licen[cs]e|apache\.org/licenses", re.I),
}

LICENCE_FILE = re.compile(r"^(ofl|licen[cs]e|copying)([-_. ].*)?(\.txt|\.md)?$", re.I)


@dataclass
class FontCheck:
    ok: bool
    licence: Optional[str]
    family: str
    reason: str = ""  # interface-string key when refused


class FontRefused(Exception):
    def __init__(self, key: str, **details):
        super().__init__(key)
        self.key = key
        self.details = details


def read_names(data: bytes) -> Dict[int, str]:
    """The English entries of a font's ``name`` table, by name ID."""
    if len(data) < 12:
        raise ValueError("not a font")
    tag = data[:4]
    offset = 0
    if tag == b"ttcf":  # a collection: read its first font
        offset = struct.unpack(">I", data[12:16])[0]
        tag = data[offset:offset + 4]
    if tag not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ValueError("not a font")
    num_tables = struct.unpack(">H", data[offset + 4:offset + 6])[0]
    name_offset = None
    for i in range(num_tables):
        rec = offset + 12 + 16 * i
        if data[rec:rec + 4] == b"name":
            name_offset = struct.unpack(">I", data[rec + 8:rec + 12])[0]
            break
    if name_offset is None:
        raise ValueError("no name table")
    _, count, string_offset = struct.unpack(">HHH", data[name_offset:name_offset + 6])
    storage = name_offset + string_offset
    names: Dict[int, tuple] = {}
    for i in range(count):
        rec = name_offset + 6 + 12 * i
        platform, encoding, language, name_id, length, str_offset = struct.unpack(">HHHHHH", data[rec:rec + 12])
        raw = data[storage + str_offset: storage + str_offset + length]
        if platform in (0, 3):
            text = raw.decode("utf-16-be", errors="replace")
            english = platform == 0 or language in (0x409, 0x809, 0)
        elif platform == 1:
            text = raw.decode("mac_roman", errors="replace")
            english = language == 0
        else:
            continue
        rank = 0 if english else 1
        if name_id not in names or rank < names[name_id][0]:
            names[name_id] = (rank, text)
    return {k: v[1] for k, v in names.items()}


def check_font(data: bytes) -> FontCheck:
    """F11.1–F11.3: read the embedded licence and decide."""
    try:
        names = read_names(data)
    except (ValueError, struct.error):
        return FontCheck(False, None, "", "error.font.notFont")
    family = names.get(16) or names.get(1) or ""
    text = " ".join(filter(None, [names.get(13), names.get(14)]))
    for licence, pattern in OPEN_LICENCES.items():
        if pattern.search(text):
            return FontCheck(True, licence, family)
    if not text.strip():
        return FontCheck(False, None, family, "error.font.noLicence")
    return FontCheck(False, None, family, "error.font.notOpen")


def licence_text(source: Path, data: bytes) -> bytes:
    """The licence file to store with the font: one found next to the font
    file, or else the licence text the font carries itself."""
    for candidate in sorted(Path(source).parent.iterdir()):
        if candidate.is_file() and LICENCE_FILE.match(candidate.name):
            return candidate.read_bytes()
    names = read_names(data)
    lines = [
        f"{names.get(1, '')} — licence information embedded in {Path(source).name}",
        "",
        names.get(0, ""),
        "",
        names.get(13, ""),
        names.get(14, ""),
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def add_font(adventure, source: Path) -> dict:
    """F11.2: copy an open-licence font and its licence file into the
    adventure. Refuses anything else with FontRefused."""
    source = Path(source)
    if source.suffix.lower() not in FONT_SUFFIXES:
        raise FontRefused("error.font.notFont", file=source.name)
    data = source.read_bytes()
    check = check_font(data)
    if not check.ok:
        raise FontRefused(check.reason, file=source.name)
    stored = adventure.add_file("assets/fonts/", source.name, data)
    stem = Path(stored).name.rsplit(".", 1)[0]
    adventure.files[f"assets/fonts/{stem}-LICENSE.txt"] = licence_text(source, data)
    return {"file": stored, "family": check.family, "licence": check.licence}


def adventure_fonts(adventure) -> list:
    """The fonts stored in an adventure, each with its check result."""
    result = []
    for name in adventure.files_in("assets/fonts/"):
        if Path(name).suffix.lower() not in FONT_SUFFIXES:
            continue
        check = check_font(adventure.files[name])
        result.append({"file": name, "family": check.family, "ok": check.ok, "licence": check.licence})
    return result
