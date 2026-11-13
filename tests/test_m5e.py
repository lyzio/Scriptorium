"""Test Plan tests for Milestone 5 part E: the author guides (F19).
T-UI-23 and T-MOD-14.

The guides are written in tools/guides/*.md (kept in the project as
documents too) and turned into interface text of scriptorum.en by
tools/make_guides.py. T-MOD-14 builds the guides' own examples, so a reader
who follows a guide gets a module that installs and prints.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tests.test_ui_smoke import Driver

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "tools" / "guides"
STRINGS = ROOT / "scriptorum" / "bundled" / "scriptorum.en" / "strings"
BUNDLED = ROOT / "scriptorum" / "bundled"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

# What F19 says each guide covers: (topic, words a section heading or text must hold).
THEME_TOPICS = [
    ("what a theme is and may change", "What a theme is and what it may change"),
    ("general or single game system", "A general theme or one for a single game system"),
    ("the folder and its manifest", "The manifest"),
    ("one template per element kind, with what each receives", "The templates"),
    ("page setup and settings.json", "Page setup and settings.json"),
    ("fonts and their licence files", "Fonts"),
    ("ornaments as SVG", "Ornaments as SVG"),
    ("paper styles and the print-friendly rules", "Handout papers"),
    ("labels", "Labels"),
    ("licence and the unofficial notice", "Licence and attribution"),
    ("testing against the sample adventures", "Testing your theme"),
    ("packing as .scmod", "Packing it as a .scmod file to share"),
    ("worked examples", "Worked examples: Legends and Lattes and Call of Cthulhu"),
]
SYSTEM_TOPICS = [
    ("what a game system is", "What a game system is"),
    ("its manifest", "The manifest"),
    ("turning on elements (elements.json)", "Turning on elements"),
    ("its own codex types", "Codex types of its own"),
    ("dice and check notation", "Dice and checks"),
    ("the creature stat block", "The creature stat block"),
    ("its own elements", "Elements of its own"),
    ("labels and language modules", "Labels and language modules"),
    ("licence", "Licence"),
    ("testing", "Testing"),
    ("packing", "Packing it as a .scmod file to share"),
    ("worked example", "Worked example: the Vaesen game system"),
]


def _strings(area):
    return json.loads((STRINGS / f"{area}.json").read_text("utf-8"))


def _blocks(markdown, tag):
    """Code blocks of a guide whose first line starts with ``` + tag."""
    found = []
    for match in re.finditer(r"^```([^\n]*)\n(.*?)^```", markdown, re.M | re.S):
        info = match.group(1).strip()
        if info.startswith(tag):
            found.append((info[len(tag):].strip(), match.group(2)))
    return found


# --- T-UI-23 the guides' text ----------------------------------------------------------------

def test_T_UI_23_guides_are_interface_text():
    """T-UI-23: the guides' text lives in the interface-language module, one
    strings/<area>.json each, made from the guides kept in the project, and
    they cover every topic F19 lists."""
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_guides.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for area, title, topics in (("guide-theme", "How to write a theme", THEME_TOPICS),
                                ("guide-game-system", "How to write a game system", SYSTEM_TOPICS)):
        texts = _strings(area)
        assert texts["title"] == title
        headings = [v for k, v in texts.items() if k.endswith(".title") and k != "title"]
        for topic, heading in topics:
            assert heading in headings, (area, topic)
        assert all(texts[k].strip() for k in texts), area
        # Every value is plain text: no HTML for the viewer to trust.
        assert not any(re.search(r"<(script|a|img|iframe)\b", v, re.I) for v in texts.values())
        # No address on the internet to follow (D9).
        assert not any(re.search(r"https?://", v) for v in texts.values())
    menu = _strings("menu")
    assert menu["guideTheme"] == "How to write a theme" and menu["guideGameSystem"] == "How to write a game system"
    theme = (GUIDES / "how-to-write-a-theme.md").read_text("utf-8")
    # The theme guide names the two heading labels the templates must keep (F17).
    assert "<scriptorum-title-heading>" in theme and "<scriptorum-scene-heading>" in theme
    flat = " ".join(theme.split())
    assert "not affiliated with or endorsed by the owners" in flat and "opacity` of at most 0.2" in flat


def test_T_UI_23_guide_templates_match_the_code():
    """T-UI-23: every element template the theme guide lists exists in the
    bundled themes, and every bundled template is listed."""
    theme = (GUIDES / "how-to-write-a-theme.md").read_text("utf-8")
    listed = set(re.findall(r"`([a-z-]+)\.typ`", theme)) - {"_page", "_generic", "_style", "rumour"}
    present = {p.stem for p in (BUNDLED / "scriptorum.plain" / "templates").glob("*.typ")} - {"_page", "_generic", "_style"}
    assert listed == present, (listed ^ present)


# --- T-MOD-14 the guides' examples work --------------------------------------------------

def _harbour_tales(folder: Path) -> Path:
    guide = (GUIDES / "how-to-write-a-game-system.md").read_text("utf-8")
    target = folder / "yourname.harbour-tales"
    for name, content in _blocks(guide, "file:"):
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(content, "utf-8")
    (target / "LICENSE.txt").write_text("Harbour Tales, CC-BY-4.0.\n", "utf-8")
    return target


def _theme_from_plain(folder: Path, name: str, manifest: dict, files) -> Path:
    target = folder / name
    shutil.copytree(BUNDLED / "scriptorum.plain", target)
    (target / "module.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    for file, content in files:
        (target / file).write_text(content, "utf-8")
    return target


def test_T_MOD_14_game_system_guide_example(library, session, tmp_path):
    """T-MOD-14: the game-system guide's example (Harbour Tales with its own
    Rumour element) installs, is offered with every general theme, prints in
    a theme that has a template for the Rumour and in the generic frame with
    a warning in one that has not, and reports a wrong value on its line."""
    from scriptorum.core.modules import pack_scmod

    guide = (GUIDES / "how-to-write-a-game-system.md").read_text("utf-8")
    folder = _harbour_tales(tmp_path)
    assert {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} >= {
        "module.json", "elements.json", "notation.json", "stat-blocks/creature.json", "codex-types/ship.json",
        "elements/rumour.json", "typst/elements.typ", "labels/en.json"}
    gs = library.install_folder(folder)
    (template,) = _blocks(guide, "theme:")
    ink = _theme_from_plain(tmp_path, "harbour-theme", {
        "id": "yourname.harbour-theme", "kind": "theme", "name": "Harbour theme", "version": "1.0.0", "format": 1,
        "app": "1.0.0", "licence": "GPL-3.0-or-later", "authors": ["Test"], "description": "A theme for Harbour Tales.",
        "requires": [{"id": gs.id, "version": "1.x"}]}, [template])
    th = library.install_folder(ink)
    try:
        offered = {g["id"]: {t["id"] for t in g["themes"]} for g in session.game_systems()}
        assert {"scriptorum.plain", "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu", th.id} <= offered[gs.id]
        assert th.id not in offered["scriptorum.free-league-vaesen"]
        kinds = session_kinds = None
        session.new("Hamnen", gs.id, gs.version, th.id, th.version)
        session_kinds = session.kinds()
        assert "rumour" in session_kinds and "map" not in session_kinds
        assert [f["name"] for f in session_kinds["rumour"]["fields"]] == ["heard-from", "truth"]
        ((_, adventure),) = _blocks(guide, "adventure")
        session.set_chapter_text(0, adventure)
        result = session.build("pdf")
        assert result.ok, [session.localize(p) for p in result.errors]
        assert not any(p.key == "warning.build.genericFrame" for p in result.warnings)
        from pypdf import PdfReader
        import io
        text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(result.output[0])).pages)
        flat = re.sub(r"\s", "", text).upper()
        assert "RUMOUR" in flat and "OLDMAJA" in flat and "BRAWN" in flat and "3D10" in flat
        # A general theme draws the Rumour in its plain frame and says so.
        session.set_theme("scriptorum.plain")
        result = session.build("pdf")
        assert result.ok and any(p.key == "warning.build.genericFrame" and p.details["element"] == "rumour" for p in result.warnings)
        # A wrong value is reported on the author's line, in plain words.
        session.set_chapter_text(0, 'Text.\n\n#rumour(truth: "maybe")[X]\n')
        result = session.build("pdf")
        assert not result.ok and result.errors[0].key == "error.build.outOfRange" and result.errors[0].line == 3
        assert session.localize(result.errors[0]) == "Line 3: Rumour: “Is it true?” is outside the allowed range."
        # Packed as the guide says, it is a .scmod with module.json at the top.
        scmod = pack_scmod(folder, tmp_path / "yourname.harbour-tales-1.0.0.scmod")
        assert "module.json" in zipfile.ZipFile(scmod).namelist()
    finally:
        shutil.rmtree(library.root / th.id, ignore_errors=True)
        shutil.rmtree(library.root / gs.id, ignore_errors=True)


def test_T_MOD_14_theme_guide_example(library, session, tmp_path):
    """T-MOD-14: the theme guide's example (a copy of Plain with its own
    manifest, colours and read-aloud template) installs as a general theme,
    is offered for every game system, and prints the example adventure with
    its own read-aloud look; packed, it installs from the .scmod file."""
    from scriptorum.core.modules import pack_scmod

    guide = (GUIDES / "how-to-write-a-theme.md").read_text("utf-8")
    files = _blocks(guide, "file:")
    manifest = json.loads(dict(files)["module.json"])
    folder = _theme_from_plain(tmp_path, manifest["id"], manifest, [f for f in files if f[0] != "module.json"])
    style = folder / "templates" / "_style.typ"
    # The colour change the guide shows, made the way it describes.
    colours = re.search(r"Change the ink.*?```\n(.*?)```", guide, re.S).group(1)
    text = style.read_text("utf-8")
    for line in colours.strip().splitlines():
        name = line.split("=")[0].strip()
        text, count = re.subn(rf"^{re.escape(name)} = .*$", line, text, count=1, flags=re.M)
        assert count == 1, name
    style.write_text(text, "utf-8")
    assert "standard" not in json.loads((folder / "module.json").read_text("utf-8"))
    scmod = pack_scmod(folder, tmp_path / "theme.scmod")
    theme = library.install_scmod(scmod)
    try:
        offered = {g["id"]: {t["id"] for t in g["themes"]} for g in session.game_systems()}
        assert all(theme.id in themes for themes in offered.values())
        session.new("Prov", "scriptorum.plain-system", "1.0.0", theme.id, theme.version)
        session.set_chapter_text(0, '#scene(title: "Kajen")[\n#read-aloud[Vinden river i tågvirket.]\n]\n')
        result = session.build("pdf")
        assert result.ok, [session.localize(p) for p in result.errors]
        assert not result.warnings
        source = (library.root / theme.id / theme.version / "templates" / "read-aloud.typ").read_text("utf-8")
        assert "stroke: (left: 1.5pt + accent)" in source
        # The example adventure prints in it too (T-BUILD-18's sample).
        from tests.conftest import pack_sample
        from pathlib import Path as _P
        path = pack_sample("example-jattens-skuld", tmp_path)
        session.open(_P(path))
        session.set_theme(theme.id)
        assert session.build("pdf").ok
    finally:
        shutil.rmtree(library.root / theme.id, ignore_errors=True)


# --- T-UI-23 Help ▸ How to write … -----------------------------------------------------------

@pytest.fixture(scope="module")
def ui(library, tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    folder = tmp_path_factory.mktemp("ui-m5e")
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def _choose(ui, label):
    """Open Help in the menu bar and click an item, as the author does."""
    ui.js("[...document.querySelectorAll('#menubar .menu-btn')].find(b => b.textContent === 'Help').click(); true")
    ui.js("[...document.querySelectorAll('#menu-popup .menu-item')]"
          f".find(b => b.firstChild.textContent === {json.dumps(label)}).click(); true")


@pytest.mark.ui
def test_T_UI_23_guides_open_in_the_app(ui):
    """T-UI-23: Help ▸ How to write a theme and Help ▸ How to write a game
    system open the guide inside the app, with no network request; its text
    comes from the interface-language module."""
    labels = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.help" for i in m["items"]]
    assert labels[-3:-1] == ["How to write a theme", "How to write a game system"], labels
    for label, area in (("How to write a theme", "guide-theme"), ("How to write a game system", "guide-game-system")):
        texts = _strings(area)
        before = ui.js("Number(document.body.dataset.guideShown || 0)")
        _choose(ui, label)
        ui.wait_until(lambda: ui.js("Number(document.body.dataset.guideShown || 0)") > before, 10)
        assert ui.js("document.getElementById('guide-dialog').open") is True
        assert ui.js("document.getElementById('guide-dialog').dataset.guide") == area
        assert ui.js("document.getElementById('guide-title').textContent") == texts["title"]
        sections = [v for k, v in texts.items() if re.fullmatch(r"s\d\d\.title", k)]
        assert ui.js("[...document.querySelectorAll('#guide-text h2')].map(h => h.textContent)") == sections
        assert ui.js("[...document.querySelectorAll('#guide-toc button')].map(b => b.textContent)") == sections
        # Code blocks keep their text exactly, and name their file.
        captions = ui.js("[...document.querySelectorAll('#guide-text figcaption')].map(c => c.textContent)")
        assert "module.json" in captions
        manifest = ui.js("[...document.querySelectorAll('#guide-text figure')].find(f => f.querySelector('figcaption')?.textContent === 'module.json').querySelector('pre').textContent")
        assert json.loads(manifest)["kind"] == ("theme" if area == "guide-theme" else "game-system")
        # Inline code and lists are drawn; nothing is inserted as HTML.
        assert ui.js("document.querySelectorAll('#guide-text code').length") > 10
        assert ui.js("document.querySelectorAll('#guide-text ul li').length") > 10
        assert ui.js("document.querySelectorAll('#guide-text a, #guide-text img, #guide-text script').length") == 0
        # The contents jump to a section.
        last = len(sections) - 1
        ui.js(f"document.querySelectorAll('#guide-toc button')[{last}].click(); true")
        ui.wait_until(lambda: ui.js("document.getElementById('guide-text').scrollTop") > 0, 5)
        ui.js("document.getElementById('guide-close').click(); true")
        assert ui.js("document.getElementById('guide-dialog').open") is False
    # The button at the foot opens the other guide.
    _choose(ui, "How to write a theme")
    assert ui.js("document.getElementById('guide-other').textContent") == "Open How to write a game system"
    ui.js("document.getElementById('guide-other').click(); true")
    assert ui.js("document.getElementById('guide-dialog').dataset.guide") == "guide-game-system"
    assert ui.js("document.getElementById('guide-text').scrollTop") == 0
    ui.js("document.getElementById('guide-close').click(); true")
    assert ui.window.interceptor.blocked == []
