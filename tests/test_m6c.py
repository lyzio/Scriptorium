"""Milestone 6 part C1: printing and the Help menu. Test Plan T-SRC-18
(elements written with their brackets), T-LOOK-12 (spacing in every theme),
T-WORLD-26 (person portraits) and T-UI-32 (the update check)."""

from __future__ import annotations

import io
import json
import re
import struct
import time
import zipfile
import zlib
from pathlib import Path

import pytest
from pypdf import PdfReader

from scriptorum import __version__, paths
from scriptorum.core import source, updates
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library
from scriptorum.core.recent import RecentFiles
from scriptorum.core.scav import ScavError
from scriptorum.core.session import Session
from tests.test_m5c import _structure

BUNDLED = paths.BUNDLED_MODULES_DIR
VAESEN = ("scriptorum.free-league-vaesen", "1.0.0", "scriptorum.vaesen", "1.0.0")
PLAIN = ("scriptorum.plain-system", "1.0.0", "scriptorum.plain", "1.0.0")
THEMES = ("scriptorum.vaesen", "scriptorum.plain", "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu")


def png(width: int, height: int) -> bytes:
    """A small PNG picture with a pattern, made without any image library."""
    rows = b"".join(b"\x00" + b"".join(bytes([(x * 7) % 256, (y * 5) % 256, 140]) for x in range(width))
                    for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _texts(pdf: bytes) -> list:
    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]


def _flat(text: str) -> str:
    return "".join(text.split())


def _ok(session, result):
    assert result.ok, [session.localize(e) for e in result.errors]
    return result


# --- T-SRC-18 elements written with their brackets ---------------------------------------------

BARE = """#scene(title: "Before and after")[
Text before the column break.

#column-break

Text in the second column.

#page-break

Text on the next page.
]
"""


@pytest.mark.integration
def test_T_SRC_18_no_body_no_fields_written_with_brackets(session):
    """T-SRC-18: every element with no body and no fields filled in is written
    with (), as the editor sends it (no stored head): the breaks, the table of
    contents, the relationship chart, and a mention and see-page with no
    target yet. Elements with fields or a body are written as before."""
    session.new("Brackets", *VAESEN)
    kinds = session.kinds()
    for kind in ("column-break", "page-break", "contents", "relationship-chart", "mention", "see"):
        block = {"type": "element", "kind": kind, "fields": {}, "variant": None, "new_page": None, "body": None}
        assert source.block_text(block, kinds) == f"#{kind}()", kind
    # Unchanged for elements that have fields or a body.
    scene = {"type": "element", "kind": "scene", "fields": {"title": "S"}, "body": {"blocks": []}}
    assert source.block_text(scene, kinds).startswith('#scene(title: "S")[')
    read = {"type": "element", "kind": "read-aloud", "fields": {}, "body": ""}
    assert source.block_text(read, kinds) == "#read-aloud[]"
    # Every always-on layout marker with no body and no fields gets them.
    for kind, d in kinds.items():
        if d.get("body", "none") == "none" and not any(f.get("required") for f in d.get("fields", [])):
            block = {"type": "element", "kind": kind, "fields": {}, "body": None}
            assert source.block_text(block, kinds).endswith("()"), kind


@pytest.mark.integration
def test_T_SRC_18_older_text_without_brackets_still_prints(session, tmp_path):
    """T-SRC-18: an older adventure with #column-break and #page-break written
    without brackets opens, builds with the breaks working and nothing like
    "(..) => .." printed, and saving without edits leaves its text unchanged.
    Once the block is edited it is written with ()."""
    session.new("Older text", *VAESEN)
    session.set_chapter_text(0, BARE)
    path = tmp_path / "older.scav"
    session.save(path)
    session.open(path)
    chapter = session.adventure.chapters[0]
    assert session.adventure.chapter_text(chapter) == BARE
    result = _ok(session, session.build("pdf"))
    pages = _texts(result.output[0])
    whole = "".join(pages)
    assert "=>" not in whole and "(..)" not in whole
    # The page break worked: the last text is on a page after the first two.
    first = next(i for i, p in enumerate(pages) if "Text before the column break" in p)
    last = next(i for i, p in enumerate(pages) if "Text on the next page" in p)
    assert last == first + 1
    # The column break worked: the second column's text is to the right.
    svg = _ok(session, session.build("svg")).output[first].decode("utf-8")
    assert "column break" not in svg
    # The build never changed the author's text, and saving without edits keeps it.
    assert session.adventure.chapter_text(chapter) == BARE
    session.save(tmp_path / "again.scav")
    with zipfile.ZipFile(tmp_path / "again.scav") as zf:
        assert zf.read(chapter).decode("utf-8") == BARE
    # The build's own copy has the brackets, on the same lines.
    copy = (session.builder.work_dir / chapter).read_text("utf-8")
    assert copy.split("\n")[1:] == BARE.replace("#column-break\n", "#column-break()\n").replace("#page-break\n", "#page-break()\n").split("\n")
    # Edited (its stored head dropped), the block is written with ().
    doc = source.parse(BARE, session.kinds())
    inner = doc["blocks"][0]["body"]["blocks"]
    breaks = [b for b in inner if b["type"] == "element"]
    assert [b["head_raw"] for b in breaks] == ["#column-break", "#page-break"]
    for b in breaks:
        source.mark_changed(b)
        b.pop("head_raw")
    doc["blocks"][0].pop("raw", None)
    written = source.serialize(doc, session.kinds())
    assert "#column-break()\n" in written and "#page-break()\n" in written


@pytest.mark.integration
def test_T_SRC_18_samples_unchanged(session, sample):
    """T-SRC-18: the samples, which already write (), round-trip byte-identical,
    and the build's copy of them is unchanged."""
    for name in ("m5-print", "m5-plain", "m3-world"):
        session.open(sample(name))
        chapter = session.adventure.chapters[0]
        text = session.adventure.chapter_text(chapter)
        assert source.complete_bare_calls(text, session.kinds()) == text
        assert source.serialize(source.parse(text, session.kinds()), session.kinds()) == text


# --- T-LOOK-12 spacing in every theme ----------------------------------------------------------

@pytest.mark.unit
def test_T_LOOK_12_spacing_set_once_in_style():
    """T-LOOK-12: every bundled theme sets its spacing in _style.typ (line
    spacing about 0.8 em, paragraph spacing about 1.2 em, and the small,
    medium and large steps), running text uses it and stays justified, and
    text inside frames is left-aligned with the same line spacing."""
    for theme in THEMES:
        folder = BUNDLED / theme / "templates"
        style = (folder / "_style.typ").read_text("utf-8")
        m = re.search(r"#let spacing = \(([^)]*)\)", style)
        assert m, theme
        values = dict(part.strip().split(": ") for part in m.group(1).replace("\n", " ").split(","))
        assert values["small"] == "3pt" and values["medium"] == "6pt" and values["large"] == "10pt", theme
        assert values["leading"] == "0.8em" and values["paragraph"] == "1.2em", theme
        assert "set par(justify: false, leading: spacing.leading" in style, theme
        page = (folder / "_page.typ").read_text("utf-8")
        assert "set par(justify: true, leading: spacing.leading, spacing: spacing.paragraph)" in page, theme
        # No template sets a tighter line spacing of its own any more, and
        # every card and box template takes its gaps from the scale.
        for name in ("person", "codex-card", "creature", "check", "countdown", "information"):
            body = (folder / f"{name}.typ").read_text("utf-8")
            assert "spacing" in body and "leading: 0.5em" not in body, (theme, name)
        # The framed text helpers are left-aligned in every theme.
        for helper in re.findall(r"#let framed-text\(body\) = ([^\n]*)", style):
            assert helper.startswith("frame-par("), (theme, helper)


WHAT = """#scene(title: "People")[
#person(name: "Tore Lund", mood: "Calm", description: [The ferryman.])[
]

#person(name: "Lovisa Strand", description: [The miller.])[
#information(variant: "public")[She runs the mill alone.]
]
]
"""


@pytest.mark.integration
@pytest.mark.parametrize("theme", THEMES)
def test_T_LOOK_12_what_they_know_only_with_something_under_it(session, theme):
    """T-LOOK-12: "What they know" prints only when something is under it."""
    session.new("Knowing", *(VAESEN if theme == "scriptorum.vaesen" else PLAIN[:2] + (theme, "1.0.0")))
    session.set_chapter_text(0, WHAT)
    pages = _texts(_ok(session, session.build("pdf")).output[0])
    flat = _flat("".join(pages)).upper()
    assert flat.count("WHATTHEYKNOW") == 1
    assert flat.index("TORELUND") < flat.index("LOVISASTRAND") < flat.index("WHATTHEYKNOW")


@pytest.mark.integration
@pytest.mark.parametrize("theme", THEMES)
def test_T_LOOK_12_samples_build_in_every_theme(session, sample, theme, record_property):
    """T-LOOK-12: m4-look, m5-plain and the example adventure build in every
    theme without errors; the page count is reported."""
    counts = {}
    for name in ("m4-look", "m5-plain", "example-jattens-skuld"):
        session.open(sample(name))
        if theme not in {t["id"] for t in session.themes_offered()}:
            continue  # the Vaesen theme is offered only for the Vaesen game system (F8)
        if session.adventure.theme.id != theme:
            session.set_theme(theme)
        result = _ok(session, session.build("pdf"))
        counts[name] = len(PdfReader(io.BytesIO(result.output[0])).pages)
    record_property("pages", json.dumps(counts))
    print(theme, counts)
    if theme == "scriptorum.vaesen":
        # The example adventure: 8 pages before (M6-0.6.2), 9 now; its people
        # page moved from page 3 to page 4 (F8, measured with the build).
        assert counts["example-jattens-skuld"] == 9


@pytest.mark.integration
def test_T_LOOK_12_card_gaps(session):
    """T-LOOK-12: on the person card the gaps after the name and Mood, before
    Linked to and What they know, and between known items are each a line's
    spacing plus a step of the scale; text in the card is left-aligned."""
    style = (BUNDLED / "scriptorum.vaesen" / "templates" / "_style.typ").read_text("utf-8")
    assert "#let gap(step) = spacing.leading + step" in style
    person = (BUNDLED / "scriptorum.vaesen" / "templates" / "person.typ").read_text("utf-8")
    assert person.count("gap(spacing.small)") >= 3 and "gap(5pt)" in person and "gap(spacing.medium)" in person
    assert "frame-par(" in person
    for name in ("creature", "codex-card"):
        assert "gap(" in (BUNDLED / "scriptorum.vaesen" / "templates" / f"{name}.typ").read_text("utf-8"), name


# --- T-WORLD-26 person portraits -------------------------------------------------------------

def _portrait_adventure(session, theme=VAESEN, small=False, describe=True):
    session.new("Portraits", *theme)
    face = session.add_portrait("face.png", png(120 if small else 900, 160 if small else 1200))
    lone = session.add_portrait("lone.png", png(1000, 750))
    fields = {"mood": "Wary", "description": "A miller's widow.", "portrait": face}
    if describe:
        fields["portrait-description"] = "A woman in a grey shawl"
    entry = session.create_entry("person", "Lovisa Strand", fields)
    session.create_entry("person", "Tore Lund", {"mood": "Calm"})
    tore = [e for e in session.world.entries().values() if e["title"] == "Tore Lund"][0]["id"]
    text = f"""#scene(title: "The mill")[
#card(entry: "{entry["id"]}")[
]

#person(name: "Agda", mood: "Sharp", description: [The innkeeper.], portrait: "{lone}", portrait-description: "An old woman with a pipe")[
]

#card(entry: "{tore}")[
]

#page-break()

#card(entry: "{entry["id"]}")[
]
]
"""
    session.set_chapter_text(0, text)
    return entry["id"], tore


def _images(svg: str) -> list:
    """(x, y, width, height) of every picture on an SVG page."""
    found = []
    for m in re.finditer(r"<image\b([^>]*)>", svg):
        attrs = dict(re.findall(r'([a-z:-]+)="([^"]*)"', m.group(1)))
        href = attrs.get("xlink:href", attrs.get("href", ""))
        # Only photographs: the themes' ornaments are SVG drawings.
        if "width" in attrs and "height" in attrs and href.startswith(("data:image/png", "data:image/jpeg", "data:image/jpg")):
            found.append((float(attrs["width"]), float(attrs["height"])))
    return found


@pytest.mark.integration
@pytest.mark.parametrize("theme", [VAESEN, PLAIN, PLAIN[:2] + ("scriptorum.legends-and-lattes", "1.0.0"),
                                   PLAIN[:2] + ("scriptorum.call-of-cthulhu", "1.0.0")])
def test_T_WORLD_26_portrait_prints_in_every_theme(session, theme):
    """T-WORLD-26: the portrait prints on every card of the person and on the
    loose card, uncropped (its shape kept) at about a third of the card's
    width, beside the name, mood and description; a card without one has none."""
    _portrait_adventure(session, theme)
    result = _ok(session, session.build("svg"))
    pages = [p.decode("utf-8") for p in result.output]
    first = [_images(p) for p in pages if "<image" in p]
    shapes = [round(h / w, 3) for page in first for (w, h) in page]
    # Lovisa twice (3:4) and Agda once (4:3): the shape of each picture kept.
    assert sorted(shapes) == sorted([round(1200 / 900, 3), round(1200 / 900, 3), round(750 / 1000, 3)])
    widths = {round(w, 1) for page in first for (w, h) in page}
    assert len(widths) == 1  # the same width on every card: a third of it
    page_width = float(re.search(r'<svg[^>]*width="([0-9.]+)', pages[0]).group(1))
    width = widths.pop()
    assert 0.08 * page_width < width < 0.2 * page_width  # a third of a column on a two-column page
    assert not result.errors


@pytest.mark.integration
def test_T_WORLD_26_layout_and_card_without_portrait(session):
    """T-WORLD-26: name, mood and description sit beside the portrait and
    the rest runs under it; a card without a portrait prints exactly as it
    does when no person has a portrait."""
    entry, tore = _portrait_adventure(session)
    pdf = _ok(session, session.build("pdf")).output[0]
    text = _flat(_texts(pdf)[1]).upper()
    assert text.index("LOVISASTRAND") < text.index("MOOD:WARY") < text.index("AMILLER")
    # A card with no portrait: the same drawing with or without portraits elsewhere.
    session.new("Alone", *VAESEN)
    session.create_entry("person", "Tore Lund", {"mood": "Calm"})
    tid = next(iter(session.world.entries()))
    session.set_chapter_text(0, f'#scene(title: "The mill")[\n#card(entry: "{tid}")[\n]\n]\n')
    alone = _ok(session, session.build("svg")).output[1]
    session.set_chapter_text(0, f'#scene(title: "The mill")[\n#card(entry: "{tid}")[\n]\n\n#page-break()\n\n#person(name: "Agda", portrait: "{session.add_portrait("a.png", png(300, 300))}", portrait-description: "Agda")[\n]\n]\n')
    beside = _ok(session, session.build("svg")).output[1]
    assert alone == beside


@pytest.mark.integration
def test_T_WORLD_26_preflight_and_accessible_pdf(session, tmp_path):
    """T-WORLD-26: a portrait without a description gives a warning with its
    line and stops the accessible PDF; one below 300 dpi gives a warning; the
    description is the picture's alt text; the handouts PDF has no portrait."""
    _portrait_adventure(session, small=True, describe=False)
    reply = session.export_pdf(tmp_path / "a.pdf")
    assert reply["ok"]
    texts = [w["text"] for w in reply["warnings"]]
    assert "Line 2: The portrait of Lovisa Strand has no description for screen readers." in texts
    assert any(t.startswith("Line 2: The portrait of Lovisa Strand prints at only") for t in texts)
    assert not any("Agda" in t for t in texts)  # described, and sharp enough
    reply = session.export_pdf(tmp_path / "b.pdf", variant="accessible")
    assert not reply["ok"] and reply["errors"][0]["text"] == "Line 2: The portrait of Lovisa Strand needs a description for the accessible PDF."
    assert not (tmp_path / "b.pdf").exists()
    # Described and sharp: the accessible PDF passes, with the description as alt text.
    _portrait_adventure(session)
    reply = session.export_pdf(tmp_path / "c.pdf", variant="accessible")
    assert reply["ok"], reply
    assert not any("portrait" in w["text"] for w in reply["warnings"])
    figures = [alt for kind, alt in _structure((tmp_path / "c.pdf").read_bytes()) if kind == "/Figure"]
    assert figures.count("A woman in a grey shawl") == 2 and "An old woman with a pipe" in figures
    # The handouts PDF holds no portrait (it holds only handouts).
    session.set_chapter_text(0, session.adventure.chapter_text(session.adventure.chapters[0]).replace(
        "#page-break()", '#handout(title: "A note")[Meet me at the mill.]'))
    reply = session.export_pdf(tmp_path / "d.pdf", variant="handouts")
    assert reply["ok"]
    assert b"/Subtype /Image" not in (tmp_path / "d.pdf").read_bytes()


@pytest.mark.unit
def test_T_WORLD_26_jpeg_and_png_only(session):
    """T-WORLD-26: a portrait is a JPEG or PNG file; others are refused."""
    session.new("Pictures", *VAESEN)
    assert session.add_portrait("face.png", png(10, 10)).endswith("face.png")
    jpeg = b"\xff\xd8\xff\xc0" + struct.pack(">HBHH", 17, 8, 40, 30) + b"\x03" + b"\x00" * 9 + b"\xff\xd9"
    assert session.add_portrait("face.jpg", jpeg).endswith("face.jpg")
    for name, data in (("face.gif", b"GIF89a" + b"\x00" * 20), ("face.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 "),
                       ("face.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")):
        with pytest.raises(ScavError) as err:
            session.add_portrait(name, data)
        assert err.value.key == "error.portrait.notJpegPng"
    assert session.t("error.portrait.notJpegPng", file="face.gif") == "“face.gif” cannot be a portrait: a portrait must be a JPEG or PNG file."
    # Both the person card and the codex Person have the Portrait and its description.
    for d in (session.kinds()["person"], session.world.types()["person"]):
        fields = {f["name"]: f for f in d["fields"]}
        assert fields["portrait"]["kind"] == "image" and fields["portrait"]["accept"] == "jpeg-png"
        assert fields["portrait-description"]["kind"] == "text"


@pytest.mark.unit
def test_T_WORLD_26_portrait_round_trips(session):
    """T-WORLD-26: a person card with a portrait parses and writes back
    byte-identical; a card without one is written exactly as before."""
    session.new("Round trip", *VAESEN)
    text = '#person(name: "Agda", portrait: "/assets/images/a.png", portrait-description: "An old woman")[\n]\n'
    doc = source.parse(text, session.kinds())
    assert doc["blocks"][0]["fields"]["portrait"] == "/assets/images/a.png"
    assert source.serialize(doc, session.kinds()) == text
    doc["blocks"][0].pop("head_raw")
    doc["blocks"][0].pop("raw", None)
    assert source.serialize(doc, session.kinds()) == text
    plain = '#person(name: "Tore", mood: "Calm")[\n]\n'
    doc = source.parse(plain, session.kinds())
    doc["blocks"][0].pop("head_raw")
    assert source.serialize(doc, session.kinds()) == plain


# --- T-UI-32 the update check: the core ------------------------------------------------------

def _file(version, note="Fixes the booklet order.", pages=None):
    return json.dumps({"version": version, "note": note, "download": pages or {
        "linux": "https://example.org/dl/linux", "macos": "https://example.org/dl/mac", "windows": "https://example.org/dl/win"}}).encode()


@pytest.mark.unit
def test_T_UI_32_update_check_outcomes():
    """T-UI-32: the placeholder makes no request; a newer version gives its
    version, note and this computer's download page; the same version is up
    to date; an address that cannot be reached says so; only https is used."""
    asked = []

    def opener(data):
        def read(url):
            asked.append(url)
            if isinstance(data, Exception):
                raise data
            return data
        return read

    assert updates.UPDATE_URL == updates.PLACEHOLDER == "Paste update url here"
    assert updates.check("0.6.3", opener=opener(b"")) == {"state": "no-address"}
    assert asked == []
    url = "https://example.org/scriptorum/update.json"
    r = updates.check("0.6.3", url, opener(_file("1.0.0")), platform="linux")
    assert r == {"state": "newer", "version": "1.0.0", "note": "Fixes the booklet order.", "download": "https://example.org/dl/linux"}
    assert updates.check("0.6.3", url, opener(_file("1.0.0")), platform="darwin")["download"] == "https://example.org/dl/mac"
    assert updates.check("0.6.3", url, opener(_file("1.0.0")), platform="win32")["download"] == "https://example.org/dl/win"
    assert updates.check("0.6.3", url, opener(_file("0.6.3")))["state"] == "current"
    assert updates.check("0.6.3", url, opener(_file("0.6.2")))["state"] == "current"
    assert updates.check("0.6.3", url, opener(OSError("no route")))["state"] == "unreachable"
    assert updates.check("0.6.3", url, opener(b"<html>not found</html>"))["state"] == "invalid"
    # A download page that is not https is never opened.
    r = updates.check("0.6.3", url, opener(_file("1.0.0", pages={"linux": "http://example.org/dl"})), platform="linux")
    assert r["state"] == "newer" and r["download"] is None
    # Only https: a plain http address is never asked.
    before = len(asked)
    assert updates.check("0.6.3", "http://example.org/update.json", opener(_file("1.0.0")))["state"] == "not-https"
    assert len(asked) == before
    assert set(asked) == {url}


@pytest.mark.unit
def test_T_UI_32_weekly_setting(tmp_path):
    """T-UI-32: Check once a week is off by default; when on, it runs at most
    once a week; the first-start question is remembered."""
    from scriptorum.core.appsettings import AppSettings

    settings = AppSettings(tmp_path / "app-settings.json")
    assert settings.get("update_weekly") is False and settings.get("update_asked") is False
    assert not updates.weekly_due(settings)
    settings.update({"update_weekly": True, "update_asked": True})
    assert updates.weekly_due(settings, now=time.time())
    settings.update({"update_last_check": int(time.time())})
    assert not updates.weekly_due(settings, now=time.time() + 3600)
    assert updates.weekly_due(settings, now=time.time() + 8 * 24 * 3600)
    again = AppSettings(tmp_path / "app-settings.json")
    assert again.get("update_weekly") is True and again.get("update_asked") is True
    settings.update({"update_weekly": "yes"})  # not a choice: ignored
    assert settings.get("update_weekly") is True


@pytest.mark.unit
def test_T_UI_32_no_other_network_code():
    """T-UI-32, D9: the update check is the only code that opens a network
    connection; the web view, Typst builds, modules and palettes stay offline."""
    root = Path(__file__).resolve().parents[1] / "scriptorum"
    users = []
    for file in root.rglob("*.py"):
        text = file.read_text("utf-8")
        if re.search(r"\b(urllib\.request|urlopen|http\.client|socket\.create_connection|QNetworkAccessManager|requests\.)", text):
            users.append(file.relative_to(root).as_posix())
    assert users == ["core/updates.py"]


# --- T-UI-32 and T-SRC-18 in the window ------------------------------------------------------

@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6c")
    library = Library(folder / "library")
    library.install_bundled(BUNDLED)
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build",
                      home=folder / "home")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def _update(ui, url, opener):
    bridge = ui.window.bridge
    bridge.update_url = url
    bridge.update_opener = opener
    done = ui.js("Number(document.body.dataset.updateDone || 0)")
    ui.run("window.__scriptorum.updates.check()")
    ui.wait_until(lambda: ui.js("Number(document.body.dataset.updateDone || 0)") == done + 1, 15)
    return {
        "text": ui.js("document.getElementById('update-text').textContent"),
        "note": ui.js("document.getElementById('update-note-box').classList.contains('hidden') ? null : document.getElementById('update-note').textContent"),
        "button": not ui.js("document.getElementById('update-open').classList.contains('hidden')"),
        "open": ui.js("document.getElementById('update-dialog').open"),
    }


@pytest.mark.ui
def test_T_UI_32_update_check_in_the_window(ui):
    """T-UI-32: Help ▸ Check for updates… with the placeholder, a newer
    version, the same version and an address that cannot be reached."""
    items = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.help" for i in m["items"]]
    assert "Check for updates…" in items
    bridge = ui.window.bridge
    blocked = len(ui.window.interceptor.blocked)
    r = _update(ui, updates.PLACEHOLDER, None)
    assert r["text"] == "No update address is set yet, so Scriptorum cannot look for a newer version. Nothing was sent anywhere."
    assert bridge.update_requests == [] and not r["button"]
    url = "https://example.org/scriptorum/update.json"
    r = _update(ui, url, lambda u: _file("9.0.0", note="New exports.", pages={"linux": "https://example.org/dl", "macos": "https://example.org/dl", "windows": "https://example.org/dl"}))
    assert r["text"] == f"Scriptorum 9.0.0 is available. You have {__version__}." and r["note"] == "New exports." and r["button"]
    ui.js("document.getElementById('update-open').click(); true")
    ui.wait_until(lambda: bridge.opened_downloads == ["https://example.org/dl"], 5)
    r = _update(ui, url, lambda u: _file(__version__))
    assert r["text"] == f"Scriptorum is up to date. You have the newest version, {__version__}." and not r["button"] and r["note"] is None

    def down(u):
        raise OSError("unreachable")
    r = _update(ui, url, down)
    assert r["text"].startswith("The update address could not be reached.") and not r["button"]
    assert bridge.update_requests == [url, url, url]
    # The window's web view made no request of its own.
    assert len(ui.window.interceptor.blocked) == blocked
    ui.js("document.getElementById('update-close').click(); true")
    assert ui.js("document.getElementById('update-dialog').open") is False
    # The app still works after an unreachable address.
    assert ui.state()["ready"] is True


@pytest.mark.ui
def test_T_UI_32_first_start_and_weekly(ui):
    """T-UI-32: at first start Scriptorum asks once, off by default (Esc or
    No keeps it off); with the weekly check off no request is ever made; the
    switch in Settings ▸ Application stores the choice."""
    bridge = ui.window.bridge
    settings = bridge.session.app_settings
    settings.update({"update_asked": False, "update_weekly": False, "update_last_check": 0})
    bridge.ask_updates_at_start = True
    bridge.update_url = "https://example.org/scriptorum/update.json"
    asked = []
    bridge.update_opener = lambda u: asked.append(u) or _file("0.6.3")
    ui.js("window.__scriptorum.updates.offer(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True, 5)
    assert "once a week" in ui.js("document.getElementById('ask-text').textContent")
    # The answer that has focus is "No, thanks": off by default.
    assert ui.js("document.activeElement.id") == "ask-cancel"
    assert ui.js("document.activeElement.textContent") == "No, thanks"
    ui.js("document.getElementById('ask-cancel').click(); true")
    ui.wait_until(lambda: settings.get("update_asked") is True, 5)
    ui.wait(300)
    assert settings.get("update_weekly") is False and asked == []
    # Asked once: not again.
    assert json.loads(bridge.updatePrompt())["ask"] is False
    assert json.loads(bridge.weeklyUpdateCheck())["started"] is False and asked == []
    # The switch in Settings ▸ Application.
    ui.run("window.__scriptorum.openSettingsWindow('application')")
    assert ui.js("document.getElementById('app-updateWeekly').checked") is False
    ui.js("document.getElementById('app-updateWeekly').click(); true")
    ui.wait_until(lambda: settings.get("update_weekly") is True, 5)
    # On, and a week since the last check: one quiet check at start.
    assert json.loads(bridge.weeklyUpdateCheck())["started"] is True
    ui.wait_until(lambda: asked == [bridge.update_url], 10)
    ui.wait_until(lambda: settings.get("update_last_check") > 0, 5)
    assert json.loads(bridge.weeklyUpdateCheck())["started"] is False  # not again within the week
    ui.js("document.getElementById('app-updateWeekly').click(); true")
    ui.wait_until(lambda: settings.get("update_weekly") is False, 5)
    ui.run("window.__scriptorum.closeSettings()")
    bridge.update_url = updates.PLACEHOLDER


@pytest.mark.ui
def test_T_SRC_18_breaks_inserted_in_the_editor(ui):
    """T-SRC-18: a column break, a page break, a table of contents and a
    relationship chart inserted in Visual mode, inside a scene and outside
    one, are written with their brackets and break in the preview."""
    reply = json.loads(ui.window.bridge.newAdventure(json.dumps({
        "title": "Breaks", "gameSystem": {"id": VAESEN[0], "version": VAESEN[1]}, "theme": {"id": VAESEN[2], "version": VAESEN[3]},
    })))
    assert reply["ok"]
    ui.run("window.__scriptorum.refresh()")
    ui.wait_until(lambda: ui.state()["pages"] > 0, 30)
    ui.js("document.querySelector('.el-scene .field-title input').focus()")
    for kind in ("column-break", "page-break", "contents", "relationship-chart"):
        ui.run(f"window.__scriptorum.insert('{kind}')")
    ui.run("window.__scriptorum.flush()")
    text = ui.state()["text"]
    for kind in ("column-break", "page-break", "contents", "relationship-chart"):
        assert f"#{kind}()" in text, (kind, text)
        assert not re.search(rf"#{kind}\s*\n", text), kind
    # Outside a scene: before the scene, at the top of the chapter.
    ui.run("window.__scriptorum.setMode('source')")
    source_text = ui.js("document.querySelector('.source-area').value")
    ui.type_input(".source-area", "#column-break()\n\n" + source_text)
    ui.run("window.__scriptorum.flush()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js("document.querySelector('.blk-element.el-column-break, .el-column-break')?.focus?.(); true")
    ui.run("window.__scriptorum.insert('page-break')")
    ui.run("window.__scriptorum.flush()")
    text = ui.state()["text"]
    assert text.count("#page-break()") == 2 and text.startswith("#column-break()")
    assert "#page-break\n" not in text and "#column-break\n" not in text
    # The preview builds without errors, and nothing like "(..) =>" is printed.
    ui.wait_until(lambda: not ui.state()["errors"], 30)
    pdf = ui.window.bridge.session.build("pdf")
    assert pdf.ok
    assert "=>" not in "".join(_texts(pdf.output[0]))
