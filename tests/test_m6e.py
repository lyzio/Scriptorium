"""M6 fix build 0.6.9 (decided 14 November 2026).

T-MOD-26    Change game system (F14)
T-BUILD-32  every empty required field is listed after one build (issue #12)
T-UI-48     Raise all in the warnings panel (issue #6)
T-WORLD-34  a clue's text typed into its Information item becomes the clue's
            description while it has none (issue #7)
T-REL-12    the macOS app signed from the inside out; installers attached when
            one platform fails (F10)
Issue #11 is a correction to T-WORLD-28's window test (tests/test_m6c3.py).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from scriptorum.core import source
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library, ModuleError
from scriptorum.core.recent import RecentFiles
from scriptorum.core.session import Session
from scriptorum.core.world import WorldError
from tests.conftest import pack_sample
from tests.test_m6c2 import BUNDLED, DRAG_HELPERS, FIND

ROOT = Path(__file__).resolve().parents[1]
VAESEN_GS = ("scriptorum.free-league-vaesen", "1.0.0")
PLAIN_GS = ("scriptorum.plain-system", "1.0.0")


def _open(session, tmp_path, name):
    session.open(pack_sample(name, tmp_path))
    return session


def _manifest(session) -> str:
    return json.dumps(session.adventure.manifest, sort_keys=True)


def _others(session) -> dict:
    """Every file of the adventure except its manifest."""
    return {k: v for k, v in session.adventure.files.items() if k != "manifest.json"}


# --- T-BUILD-32 every error at once (issue #12) ----------------------------------------------

@pytest.mark.integration
def test_T_BUILD_32_every_required_field_at_once(session, tmp_path):
    """T-BUILD-32: three empty required fields in three places are all
    reported after one build, each on its line; after one is filled in,
    the other two are still listed."""
    _open(session, tmp_path, "m2-full")
    text = session.adventure.chapter_text(session.adventure.chapters[0])
    text = (text.replace('title: "The harbour"', 'title: ""')
                .replace('name: "Lovisa Berg"', 'name: ""')
                .replace('title: "The sexton\'s note"', 'title: ""'))
    session.set_chapter_text(0, text)
    lines = {i + 1 for i, line in enumerate(text.split("\n"))
             if line.startswith(('#scene(title: ""', '#person(name: ""', '#handout(title: ""'))}
    result = session.build("pdf")
    assert not result.ok
    found = [(e.key, e.details["element"], e.details["field"], e.line) for e in result.errors]
    assert [f[:3] for f in found] == [("error.build.requiredField", "scene", "title"),
                                      ("error.build.requiredField", "person", "name"),
                                      ("error.build.requiredField", "handout", "title")]
    assert {f[3] for f in found} == lines
    # Each says what is missing, in words.
    assert all(session.problem_json(e)["text"] for e in result.errors)
    session.set_chapter_text(0, text.replace('#scene(title: ""', '#scene(title: "The harbour"', 1))
    again = session.build("pdf")
    assert [(e.details["element"]) for e in again.errors] == ["person", "handout"]


# --- T-MOD-26 Change game system ---------------------------------------------------------------

@pytest.mark.unit
def test_T_MOD_26_build_copy_fits_the_game_system(session, tmp_path):
    """T-MOD-26: the build's own copy leaves out a creature's fields the new
    stat block lacks and prints dice outside the notation as plain text,
    with the same number of lines; text that fits is unchanged."""
    _open(session, tmp_path, "m5-plain")
    plain = session.adventure.chapter_text(session.adventure.chapters[0])
    # Under Plain everything fits.
    copy, found = source.fit_to_game_system(plain, session.kinds(), {"dice": ["d6", "d20", "d10", "d100"], "modifiers": True})
    assert copy == plain and found == []
    session.preview_game_system(*VAESEN_GS)
    session.apply_version_preview()
    kinds = session.kinds()
    notation = session.library.get(*VAESEN_GS).notation()
    copy, found = source.fit_to_game_system(plain, kinds, notation)
    assert copy.count("\n") == plain.count("\n")
    assert "stat-lines" not in copy and "stat-lines" in plain
    assert [f["kind"] for f in found] == ["dice", "field", "dice", "dice"]
    assert [f.get("dice") for f in found if f["kind"] == "dice"] == ["d20", "2d10+1", "d100"]
    assert "#[d20]" in copy and '#dice(dice: "d20")' not in copy
    # A dice block keeps its rule and its own closing bracket.
    block = '#dice(dice: "d20")[Roll for the weather.]\n'
    assert source.fit_to_game_system(block, kinds, notation)[0] == "#block[d20 Roll for the weather.]\n"
    assert source.dice_fits("3D6", notation) and not source.dice_fits("2d6+1", notation)


@pytest.mark.integration
def test_T_MOD_26_change_game_system(session, tmp_path):
    """T-MOD-26: m5-plain from Plain to Vaesen. Before the preview a list
    names what does not fit; Cancel changes nothing; Apply changes only the
    manifest's game system, theme and module lines, in one undo step; the
    text, codex, maps and handouts are byte-identical; the kept stat lines
    and other dice get warnings on their lines and the adventure prints;
    changing back gives the same manifest and no warnings."""
    _open(session, tmp_path, "m5-plain")
    manifest, files = _manifest(session), _others(session)
    fit = session.game_system_fit(*VAESEN_GS)
    assert fit["themeOffered"] and fit["name"] == "Vaesen"
    keys = [p["key"] for p in fit["problems"]]
    assert keys.count("warning.fit.dice") == 3 and keys.count("warning.fit.fields") == 1
    assert all(p["line"] for p in fit["problems"])
    assert any("d20" in p["text"] and "Vaesen" in p["text"] for p in fit["problems"])
    # The preview, then Cancel.
    info = session.preview_game_system(*VAESEN_GS)
    assert info["versionPreview"]["which"] == "system" and info["versionPreview"]["name"] == "Vaesen"
    assert session.build("png").ok
    session.cancel_version_preview()
    assert _manifest(session) == manifest and _others(session) == files
    # Apply.
    session.preview_game_system(*VAESEN_GS)
    session.apply_version_preview()
    m = session.adventure.manifest
    assert (m["game_system"]["id"], m["theme"]["id"]) == (VAESEN_GS[0], "scriptorum.plain")
    assert [x["id"] for x in m["modules"]] == ["scriptorum.core", VAESEN_GS[0], "scriptorum.plain"]
    assert _others(session) == files
    result = session.build("pdf")
    assert result.ok
    warned = [(w.key, w.line) for w in result.warnings if w.key.startswith("warning.fit.")]
    assert len(warned) == 4 and all(line for _key, line in warned)
    reply = session.export_pdf(tmp_path / "vaesen.pdf")
    assert reply["ok"], reply
    # One undo step brings Plain back.
    assert session.world_undo()
    assert _manifest(session) == manifest
    # Changing back gives the same manifest, and nothing is left to warn about.
    session.preview_game_system(*VAESEN_GS)
    session.apply_version_preview()
    session.preview_game_system(*PLAIN_GS)
    session.apply_version_preview()
    assert _manifest(session) == manifest and _others(session) == files
    assert not [w for w in session.build("pdf").warnings if w.key.startswith("warning.fit.")]


@pytest.mark.integration
def test_T_MOD_26_theme_and_codex_types(session, tmp_path):
    """T-MOD-26: from Vaesen to Plain, the Vaesen theme is not offered, so a
    theme for Plain must be picked; a general theme stays. Codex entries of
    a type Plain lacks are kept and get a warning."""
    _open(session, tmp_path, "m4-look")
    files = _others(session)
    fit = session.game_system_fit(*PLAIN_GS)
    assert not fit["themeOffered"] and fit["themes"][0]["id"] == "scriptorum.plain"
    assert [p["key"] for p in fit["problems"]] == ["warning.fit.codexType"]
    assert "Creature" in fit["problems"][0]["text"]
    with pytest.raises(ModuleError) as refused:
        session.preview_game_system(*PLAIN_GS)
    assert refused.value.key == "error.gameSystem.pickTheme"
    session.preview_game_system(*PLAIN_GS, "scriptorum.plain")
    session.apply_version_preview()
    assert session.adventure.manifest["theme"]["id"] == "scriptorum.plain"
    assert "scriptorum.vaesen" not in [x["id"] for x in session.adventure.manifest["modules"]]
    assert _others(session) == files
    assert session.build("pdf").ok


@pytest.mark.integration
def test_T_MOD_26_read_only(session, tmp_path):
    """T-MOD-26: a read-only adventure says so."""
    _open(session, tmp_path, "m5-plain")
    session.read_only = "openElsewhere"
    with pytest.raises(WorldError) as refused:
        session.preview_game_system(*VAESEN_GS)
    assert refused.value.key == "error.scav.readOnly"
    assert session.t(refused.value.key).startswith("This adventure is read-only")


# --- the window ----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6e")
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


def _load(ui, text_):
    reply = json.loads(ui.window.bridge.newAdventure(json.dumps({
        "title": "Fix", "gameSystem": {"id": VAESEN_GS[0], "version": "1.0.0"},
        "theme": {"id": "scriptorum.vaesen", "version": "1.0.0"}})))
    assert reply["ok"]
    ui.window.bridge.session.set_chapter_text(0, text_)
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js(DRAG_HELPERS)
    ui.js(FIND)


def _text(ui) -> str:
    ui.run("window.__scriptorum.flush()")
    return ui.state()["text"]


SKIPPED = """#scene(title: "The mill")[
The wheel turns.

==== The loft

Dust and old sacks.
]

#scene(title: "The cellar")[
==== Water on the floor

Cold.
]

#scene(title: "The yard")[
==== Mud

Deep mud.
]
"""


@pytest.mark.ui
def test_T_UI_48_raise_all(ui):
    """T-UI-48 (issue #6): with three headings that skip a level, the
    warnings panel offers Raise all; it raises all three in one undo step;
    with only one such heading there is no Raise all."""
    _load(ui, SKIPPED)
    ui.wait_until(lambda: sum("skips a level" in w["text"] for w in ui.state()["warnings"]) == 3, 40)
    ui.run("window.__scriptorum.openWarnings()")
    assert ui.js("document.querySelector('#warnings-list .raise-all-btn').textContent") == "Raise all 3 headings"
    assert ui.js("document.querySelectorAll('#warnings-list .warning-fix').length") == 3
    before = ui.state()["historyPos"]
    ui.js("document.querySelector('#warnings-list .raise-all-btn').click(); true")
    ui.wait_until(lambda: "====" not in _text(ui), 5)
    assert _text(ui) == SKIPPED.replace("====", "===")
    assert ui.state()["historyPos"] == before + 1
    ui.run("window.__scriptorum.undo()")
    assert _text(ui) == SKIPPED
    # One such heading: only its own Raise.
    _load(ui, SKIPPED.replace("==== Water", "=== Water").replace("==== Mud", "=== Mud"))
    ui.wait_until(lambda: sum("skips a level" in w["text"] for w in ui.state()["warnings"]) == 1, 40)
    ui.run("window.__scriptorum.openWarnings()")
    assert ui.js("document.querySelectorAll('#warnings-list .raise-all-btn').length") == 0
    assert ui.js("document.querySelectorAll('#warnings-list .warning-fix').length") == 1


@pytest.mark.ui
def test_T_WORLD_34_clue_text_from_its_item(ui):
    """T-WORLD-34 (issue #7): a new clue has no description; text typed into
    its Information item becomes the description when the author leaves the
    box, in one undo step; a second item of the same clue then shows it;
    a clue with a description is never overwritten."""
    (ui.folder / "clue").mkdir(exist_ok=True)
    assert json.loads(ui.window.bridge.openPath(str(pack_sample("m6-clues", ui.folder / "clue"))))["ok"]
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js(FIND)
    session = ui.window.bridge.session
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    ui.js("window.__scriptorum.insertFromCodex('clue'); true")
    ui.wait_until(lambda: ui.js("document.getElementById('pick-dialog').open"), 5)
    ui.js("document.getElementById('pick-new').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('prompt-dialog').open"), 5)
    ui.js("document.getElementById('prompt-input').value = 'The wet rope'; document.getElementById('prompt-ok').click(); true")
    ui.wait_until(lambda: 'clue: "c-the-wet-rope"' in _text(ui), 10)
    assert session.world.entry("c-the-wet-rope")["fields"].get("description", "") == ""
    # Type into the item, then leave it.
    body = "[...document.querySelectorAll('#visual .clue-empty')].map(n => n.closest('.el').querySelector('.el-body'))[0]"
    ui.js(f"(() => {{ const b = {body}; b.focus(); b.textContent = 'Frayed and still wet.'; "
          "b.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
    ui.js(f"(() => {{ const b = {body}; b.dispatchEvent(new FocusEvent('focusout', {{bubbles: true}})); return true; }})()")
    ui.wait_until(lambda: session.world.entry("c-the-wet-rope")["fields"].get("description") == "Frayed and still wet.", 10)
    # A second item of the same clue shows the clue's text.
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    ui.js("window.__scriptorum.insertFromCodex('clue'); true")
    ui.wait_until(lambda: ui.js("document.getElementById('pick-dialog').open"), 5)
    ui.js("[...document.querySelectorAll('#pick-list .pick-item')].find(b => b.textContent === 'The wet rope').click(); true")
    ui.wait_until(lambda: ui.js("[...document.querySelectorAll('#visual .clue-body')].filter(b => b.textContent === 'Frayed and still wet.').length") == 2, 10)
    ui.run("window.__scriptorum.undo()")    # the second item
    ui.run("window.__scriptorum.undo()")    # the description
    ui.wait_until(lambda: session.world.entry("c-the-wet-rope")["fields"].get("description", "") == "", 10)
    # The broken oar has a description: its item shows the clue's text, not a box to type in.
    assert session.world.entry("c-broken-oar")["fields"]["description"]
    assert ui.js("[...document.querySelectorAll('#visual .clue-body')].some(b => b.textContent.startsWith('An oar snapped'))")


# --- T-REL-12 signing from the inside out, and attaching when one platform fails ------------

def _kit():
    spec = importlib.util.spec_from_file_location("scriptorum_packaging_kit_e", ROOT / "packaging" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MACHO = bytes.fromhex("cffaedfe") + b"\0" * 28


@pytest.mark.unit
def test_T_REL_12_macos_signed_from_the_inside_out(tmp_path, monkeypatch):
    """T-REL-12: every library and helper program first, deepest first; then
    nested bundles, a framework by its real version folder; the app last;
    never --deep when signing; then the whole app is checked strictly."""
    kit = _kit()
    app = tmp_path / "Scriptorum.app"
    fw = app / "Contents" / "Frameworks" / "PySide6" / "Qt" / "lib" / "QtWebEngineCore.framework"
    helper = fw / "Versions" / "A" / "Helpers" / "QtWebEngineProcess.app"
    (helper / "Contents" / "MacOS").mkdir(parents=True)
    (helper / "Contents" / "MacOS" / "QtWebEngineProcess").write_bytes(MACHO)
    (fw / "Versions" / "A" / "QtWebEngineCore").write_bytes(MACHO)
    (fw / "Versions" / "Current").symlink_to("A")
    (fw / "QtWebEngineCore").symlink_to("Versions/Current/QtWebEngineCore")
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Scriptorum").write_bytes(MACHO)
    (app / "Contents" / "Frameworks" / "libpython3.13.dylib").write_bytes(MACHO)
    (app / "Contents" / "Resources").mkdir()
    (app / "Contents" / "Resources" / "scav.icns").write_bytes(b"icns")
    order = kit.macos_signing_order(app)
    names = [p.relative_to(tmp_path).as_posix() for p in order]
    assert names[-1] == "Scriptorum.app"
    assert names.index(next(n for n in names if n.endswith("MacOS/QtWebEngineProcess"))) < names.index(
        next(n for n in names if n.endswith("QtWebEngineProcess.app")))
    assert names.index(next(n for n in names if n.endswith("QtWebEngineProcess.app"))) < names.index(
        next(n for n in names if n.endswith("QtWebEngineCore.framework/Versions/A")))
    assert not any(n.endswith(".icns") or n.endswith("Versions/Current") for n in names)
    calls = []
    monkeypatch.setattr(kit, "run", lambda cmd, **kw: calls.append([str(c) for c in cmd]))
    kit.sign_macos_app(app)
    signing, check = calls[:-1], calls[-1]
    assert len(signing) == len(order) and all("--deep" not in c for c in signing)
    assert check[:4] == ["codesign", "--verify", "--deep", "--strict"]


@pytest.mark.integration
def test_T_REL_12_attached_when_one_platform_fails():
    """T-REL-12: the attach job runs unless the run was cancelled, so the
    installers that built are attached when another platform failed; with
    no installer at all it says so."""
    text = (ROOT / ".github" / "workflows" / "installers.yml").read_text("utf-8")
    attach = text.split("\n  attach:", 1)[1]
    assert "if: ${{ !cancelled() && (github.event_name == 'push' || inputs.attach) }}" in attach
    assert "needs: build" in attach and "fail-fast: false" in text
    assert "No platform built an installer" in attach
