"""Print-safe quality checks and the print export variants (design document
F7.5 and F7.6, built in M5).

Preflight looks at the finished PDF and the build folder:

- every font is embedded (an error: export stops);
- every font used can print å, ä and ö (a warning naming the font);
- every image in the text has at least 300 dpi at its printed size (a
  warning naming the image and its line; map images are checked in the
  session, F5.6).

Broken codex references, empty required fields, paper styles and long
handouts are found by the build itself (F7.5.3, F7.5.6, F7.5.7).

The variants:

- the booklet: two pages per sheet on the next paper size up, side by side in
  reading order or in fold order; a second Typst pass places the pages of the
  finished PDF onto the larger sheets as vectors, so it has no links or
  bookmarks (F7.6.4);
- the print-shop version: the page grows by the bleed and a slug for crop
  marks, and the file is PDF/A-2b (F7.6.5). It is laid out in the first pass,
  since Typst cannot place PDF pages in a PDF/A file.
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scriptorum.core.build import PAPER_MM, SHEET_UP, Problem, column_width, paper_size
from scriptorum.core.fonts import read_names

SWEDISH = "åäöÅÄÖ"
MIN_DPI = 300
BLEED_MM = 3.0      # F7.6.5: the usual bleed a print shop asks for
SLUG_MM = 7.0       # room outside the bleed for the crop marks
BOOKLET_ORDERS = ("side-by-side", "fold")


# --- fonts ----------------------------------------------------------------------------------

def font_chars(data: bytes) -> set:
    """The characters a TrueType or OpenType font maps (cmap formats 4 and 12)."""
    chars: set = set()
    try:
        count = struct.unpack(">H", data[4:6])[0]
        tables = {data[12 + 16 * i:16 + 16 * i]: struct.unpack(">II", data[20 + 16 * i:28 + 16 * i]) for i in range(count)}
        base = tables[b"cmap"][0]
        for i in range(struct.unpack(">H", data[base + 2:base + 4])[0]):
            offset = base + struct.unpack(">I", data[base + 8 + 8 * i:base + 12 + 8 * i])[0]
            fmt = struct.unpack(">H", data[offset:offset + 2])[0]
            if fmt == 4:
                segs = struct.unpack(">H", data[offset + 6:offset + 8])[0] // 2
                ends = struct.unpack(f">{segs}H", data[offset + 14:offset + 14 + 2 * segs])
                starts = struct.unpack(f">{segs}H", data[offset + 16 + 2 * segs:offset + 16 + 4 * segs])
                for s, e in zip(starts, ends):
                    if e != 0xFFFF:
                        chars.update(range(s, e + 1))
            elif fmt == 12:
                groups = struct.unpack(">I", data[offset + 12:offset + 16])[0]
                for g in range(groups):
                    s, e, _ = struct.unpack(">III", data[offset + 16 + 12 * g:offset + 28 + 12 * g])
                    chars.update(range(s, e + 1))
    except (KeyError, struct.error, IndexError):
        return set()
    return chars


def _pdf_fonts(pdf: bytes) -> Dict[str, bool]:
    """Every font in the PDF by its PostScript name, and whether it is embedded."""
    from pypdf import PdfReader

    found: Dict[str, bool] = {}
    reader = PdfReader(io.BytesIO(pdf))
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        fonts = resources.get("/Font") or {}
        for ref in fonts.values():
            font = ref.get_object()
            name = str(font.get("/BaseFont", "")).lstrip("/")
            name = name.split("+", 1)[-1]
            descriptor = font.get("/FontDescriptor")
            if descriptor is None and "/DescendantFonts" in font:
                descriptor = font["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            descriptor = descriptor.get_object() if descriptor is not None else {}
            embedded = str(font.get("/Subtype")) == "/Type3" or any(k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3"))
            found[name] = found.get(name, True) and embedded
    return found


def check_pdf_fonts(pdf: bytes, build_dir: Path) -> List[Problem]:
    """F7.5.1: all fonts embedded; each font used has å, ä and ö."""
    problems: List[Problem] = []
    used = _pdf_fonts(pdf)
    for name, embedded in sorted(used.items()):
        if not embedded:
            problems.append(Problem("error.preflight.fontNotEmbedded", {"font": name}))
    files = [f for pattern in ("m/*/fonts/*", "assets/fonts/*") for f in Path(build_dir).glob(pattern)
             if f.suffix.lower() in (".ttf", ".otf")]
    for file in sorted(files):
        data = file.read_bytes()
        names = read_names(data)
        postscript = names.get(6, "")
        if postscript not in used:
            continue
        chars = font_chars(data)
        if chars and not all(ord(c) in chars for c in SWEDISH):
            problems.append(Problem("warning.preflight.noSwedish", {"font": names.get(4, postscript)}))
    return problems


# --- images -----------------------------------------------------------------------------------

def image_width_px(data: bytes) -> Optional[int]:
    """The pixel width of a PNG or JPEG file."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">I", data[16:20])[0]
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return struct.unpack(">H", data[i + 7:i + 9])[0]
            i += 2 + length
    return None


IMAGE_CALL = re.compile(r'#image\("(/assets/images/[^"\\]+)"(, alt: "(?:[^"\\]|\\.)+")?\)')


def check_images(adventure, page: dict) -> List[Problem]:
    """F7.5.2: an image below 300 dpi at its printed size gives a warning
    naming the image and its line. An image in the text prints at the width
    of its column (F4.6)."""
    problems: List[Problem] = []
    column_in = column_width(page) / 25.4
    if column_in <= 0:
        return problems
    for chapter in adventure.chapters:
        text = adventure.chapter_text(chapter)
        for match in IMAGE_CALL.finditer(text):
            data = adventure.files.get(match.group(1).lstrip("/"))
            width = image_width_px(data) if data else None
            if width is None:
                continue
            dpi = int(width / column_in)
            if dpi < MIN_DPI:
                line = text.count("\n", 0, match.start()) + 1
                problems.append(Problem("warning.preflight.lowResolution",
                                        {"image": Path(match.group(1)).name, "dpi": dpi}, chapter, line))
    return problems


# --- the print-shop version -------------------------------------------------------------------

def print_shop_page(page: dict, bleed_mm: float = BLEED_MM) -> str:
    """F7.6.5: Typst lines that grow every page by the bleed and the slug and
    draw crop marks at the trim corners. The text keeps its place on the trim."""
    w, h = paper_size(page.get("paper", "a4"), page.get("orientation", "portrait"))
    o = bleed_mm + SLUG_MM
    m = page.get("margin_mm", {})
    if "inside" in m:
        margin = f"(top: {m['top'] + o}mm, bottom: {m['bottom'] + o}mm, inside: {m['inside'] + o}mm, outside: {m['outside'] + o}mm)"
    else:
        margin = f"(top: {m.get('top', 20) + o}mm, bottom: {m.get('bottom', 20) + o}mm, x: {m.get('x', 20) + o}mm)"
    mark = SLUG_MM - 1.0
    gap = bleed_mm
    W, H = w + 2 * o, h + 2 * o
    lines = []
    for x, y, dx, dy in ((o, o, -1, -1), (W - o, o, 1, -1), (o, H - o, -1, 1), (W - o, H - o, 1, 1)):
        # A horizontal and a vertical mark at each corner, outside the bleed.
        hx0 = x + dx * (gap + 1.0)
        lines.append(f"place(top + left, line(start: ({hx0}mm, {y}mm), end: ({hx0 + dx * mark}mm, {y}mm), stroke: 0.25pt + black))")
        vy0 = y + dy * (gap + 1.0)
        lines.append(f"place(top + left, line(start: ({x}mm, {vy0}mm), end: ({x}mm, {vy0 + dy * mark}mm), stroke: 0.25pt + black))")
    marks = "pdf.artifact({ " + "; ".join(lines) + " })"
    return f"#set page(width: {W}mm, height: {H}mm, flipped: false, margin: {margin}, foreground: {marks})"


# --- the booklet --------------------------------------------------------------------------------

def booklet_sheet(paper: str, wanted: Optional[str] = None) -> str:
    """F7.6.4: the next paper size up, unless another was chosen."""
    if wanted in PAPER_MM and wanted != paper:
        return wanted
    return SHEET_UP.get(paper, "a3")


def booklet_order(pages: int, order: str) -> List[Tuple[Optional[int], Optional[int]]]:
    """The two pages on each side of each sheet, numbered from 1; None is a
    blank page. Side by side keeps reading order; fold order makes the sheets
    fold into a booklet, with blank pages added up to a multiple of four."""
    if order == "fold":
        n = pages + (-pages % 4)
        sides = []
        for i in range(n // 4):
            sides.append((n - 2 * i, 2 * i + 1))          # front: last and first
            sides.append((2 * i + 2, n - 2 * i - 1))      # back: second and second-to-last
        return [tuple(p if p <= pages else None for p in side) for side in sides]
    n = pages + (pages % 2)
    return [(i + 1, i + 2 if i + 2 <= pages else None) for i in range(0, n, 2)]


def booklet_source(pages: int, page: dict, sheet: str, order: str) -> str:
    """The Typst text of the second pass: two pages of src.pdf on each sheet."""
    pw, ph = paper_size(page.get("paper", "a4"), page.get("orientation", "portrait"))
    sw, sh = PAPER_MM.get(sheet, PAPER_MM["a3"])
    across = pw <= ph  # portrait pages side by side; landscape pages one above the other
    if across:
        sw, sh = max(sw, sh), min(sw, sh)
        cell = f"columns: (1fr, 1fr), rows: (100%,)"
    else:
        sw, sh = min(sw, sh), max(sw, sh)
        cell = f"columns: (100%,), rows: (1fr, 1fr)"
    out = [
        "// F7.6.4 booklet: written by Scriptorum for every export. Never edit by hand.",
        f"#set page(width: {sw}mm, height: {sh}mm, margin: 0pt)",
    ]
    sides = booklet_order(pages, order)
    for index, (a, b) in enumerate(sides):
        def one(p):
            if p is None:
                return "[]"
            return f'align(center + horizon, image("src.pdf", page: {p}, width: {pw}mm))'
        out.append(f"#grid({cell}, {one(a)}, {one(b)})")
        if index < len(sides) - 1:
            out.append("#pagebreak()")
    return "\n".join(out) + "\n"


def compose_booklet(pdf: bytes, page: dict, work_dir: Path, sheet: str, order: str) -> bytes:
    """Run the second Typst pass in a folder of its own."""
    from pypdf import PdfReader

    from scriptorum.core.helper import helper

    folder = Path(work_dir) / "booklet"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "src.pdf").write_bytes(pdf)
    pages = len(PdfReader(io.BytesIO(pdf)).pages)
    (folder / "booklet.typ").write_text(booklet_source(pages, page, sheet, order), "utf-8")
    empty = folder / ".no-packages"
    empty.mkdir(exist_ok=True)
    # F7.1 (M6): the second pass runs in the build helper too, within the time limit.
    spec = {"input": str(folder / "booklet.typ"), "root": str(folder), "font_paths": [], "no_packages": str(empty)}
    return helper().call({"op": "compile-once", "spec": spec, "kwargs": {"format": "pdf", "timestamp": 0}})
