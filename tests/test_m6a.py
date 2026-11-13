"""Milestone 6 part A: the module manager (F14) and the installation checks
(9.7). Test Plan T-MOD-08, T-MOD-15 to 19, T-MOD-21 to 24 and T-UI-31."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from scriptorum import paths
from scriptorum.core import modmanager
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library, ModuleError, pack_scmod
from scriptorum.core.recent import RecentFiles
from scriptorum.core.session import Session
from tests.test_fonts import make_font

BUNDLED = paths.BUNDLED_MODULES_DIR
ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "tools" / "guides"


# --- helpers -----------------------------------------------------------------------------
@pytest.fixture
def lib(tmp_path):
    """A library of its own, so modules installed here never reach other tests."""
    library = Library(tmp_path / "library")
    library.install_bundled(BUNDLED)
    return library


@pytest.fixture
def tab(lib, tmp_path):
    return Session(lib, Strings.from_library(lib), RecentFiles(tmp_path / "recent.json"), tmp_path / "build",
                   home=tmp_path / "home")


def theme_folder(tmp_path, module_id="test.ink", version="1.0.0", name="Ink", base="scriptorum.plain") -> Path:
    """A general theme made from a copy of a bundled one, under a new ID."""
    target = tmp_path / "src" / f"{module_id}-{version}"
    shutil.copytree(BUNDLED / base, target)
    manifest = json.loads((target / "module.json").read_text("utf-8"))
    manifest.update({"id": module_id, "version": version, "name": name, "standard": False,
                     "description": f"Test theme {name} {version}."})
    manifest.pop("standard")
    (target / "module.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return target


def scmod(folder: Path, tmp_path: Path) -> Path:
    """Zip a module folder as a .scmod, without the packer's own checks, so
    a broken module can be offered to the installer."""
    target = tmp_path / f"{folder.name}.scmod"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(folder).as_posix())
    return target


def make_zip(path: Path, entries) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            if isinstance(name, zipfile.ZipInfo):
                zf.writestr(name, data)
            else:
                zf.writestr(name, data)
    return path


def adventure_with(tab, tmp_path, theme_id, theme_version, text=None, name="adv") -> Path:
    tab.new("Lantern Night", "scriptorum.plain-system", "1.0.0", theme_id, theme_version)
    if text is not None:
        tab.set_chapter_text(0, text)
    return tab.save(tmp_path / f"{name}.scav")


def files_of(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


# --- T-MOD-15 package imports ---------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.parametrize("line", ['#import "@preview/cetz:0.2.2": canvas', '#import "@local/house:1.0.0": *',
                                  '#include "@acme/parts:0.1.0"'])
def test_T_MOD_15_package_import_refused_on_install(lib, tmp_path, line):
    """T-MOD-15: a module whose Typst file imports a package by name is
    refused at installation, with the file and line named (9.7, D9)."""
    folder = theme_folder(tmp_path)
    template = folder / "templates" / "box.typ"
    template.write_text("// a theme\n\n" + line + "\n" + template.read_text("utf-8"), "utf-8")
    with pytest.raises(ModuleError) as info:
        modmanager.install(lib, scmod(folder, tmp_path))
    assert info.value.key == "error.module.packageImport"
    assert info.value.details["file"] == "templates/box.typ" and info.value.details["line"] == 3
    assert lib.get("test.ink", "1.0.0", include_disabled=True) is None
    tab_text = Strings.from_library(lib).t(info.value.key, **info.value.details)
    assert "templates/box.typ, line 3" in tab_text and "never downloads" in tab_text


@pytest.mark.integration
def test_T_MOD_15_package_import_refused_before_build(lib, tab, tmp_path):
    """T-MOD-15: a module copied into the library by hand is caught before
    compiling, with the same file and line, and nothing is built."""
    folder = theme_folder(tmp_path)
    shutil.copytree(folder, lib.root / "test.ink" / "1.0.0")
    adventure_with(tab, tmp_path, "test.ink", "1.0.0")
    assert tab.build("pdf").ok
    template = lib.root / "test.ink" / "1.0.0" / "templates" / "scene.typ"
    template.write_text('#import "@preview/tablex:0.0.8": *\n' + template.read_text("utf-8"), "utf-8")
    tab.builder = None
    tab._start_builder()
    result = tab.build("pdf")
    assert not result.ok and result.errors[0].key == "error.build.modulePackage"
    assert result.errors[0].details["file"] == "templates/scene.typ" and result.errors[0].details["line"] == 1
    assert "@preview/tablex:0.0.8" in tab.localize(result.errors[0])
    # Bundled modules import nothing by name.
    from scriptorum.core.modules import package_import
    assert all(package_import(m.path) is None for m in lib.installed() if m.id != "test.ink")


# --- T-MOD-16 install with every check -------------------------------------------------------
@pytest.mark.integration
def test_T_MOD_16_install_valid_module(lib, tmp_path):
    """T-MOD-16: a valid .scmod installs, is listed, and is offered."""
    result = modmanager.install(lib, scmod(theme_folder(tmp_path), tmp_path))
    assert result["status"] == "installed" and result["module"].key == "test.ink@1.0.0"
    rows = {r["id"]: r for r in modmanager.module_list(lib, [])}
    assert rows["test.ink"]["canRemove"] and rows["test.ink"]["canSave"] and not rows["test.ink"]["bundled"]
    tab = Session(lib, Strings.from_library(lib), RecentFiles(tmp_path / "r.json"), tmp_path / "b", home=tmp_path / "h")
    offered = {g["id"]: {t["id"] for t in g["themes"]} for g in tab.game_systems()}
    assert "test.ink" in offered["scriptorum.plain-system"] and "test.ink" in offered["scriptorum.free-league-vaesen"]


def _broken(kind, tmp_path):
    folder = theme_folder(tmp_path)
    manifest = json.loads((folder / "module.json").read_text("utf-8"))
    if kind == "manifest":
        manifest.pop("licence")
        (folder / "module.json").write_text(json.dumps(manifest), "utf-8")
    elif kind == "filetype":
        (folder / "templates" / "helper.py").write_text("print('x')\n", "utf-8")
    elif kind == "font":
        for font in (folder / "fonts").rglob("*.ttf"):
            font.unlink()
        (folder / "fonts" / "Shop.ttf").write_bytes(make_font({1: "Shop Sans", 13: "All rights reserved."}))
    elif kind == "requirement":
        manifest["requires"] = [{"id": "test.absent-kit", "version": "1.x"}]
        (folder / "module.json").write_text(json.dumps(manifest), "utf-8")
    elif kind == "wrongversion":
        manifest["requires"] = [{"id": "scriptorum.core", "version": "2.x"}]
        (folder / "module.json").write_text(json.dumps(manifest), "utf-8")
    elif kind == "compile":
        (folder / "templates" / "scene.typ").write_text("#let render(..args) = {\n  this is ( not typst\n}\n", "utf-8")
    elif kind == "renderer":
        (folder / "templates" / "_generic.typ").unlink()
        (folder / "templates" / "box.typ").unlink()
    return folder


@pytest.mark.integration
@pytest.mark.parametrize("kind,key", [
    ("manifest", "error.module.missingField"),
    ("filetype", "error.module.forbiddenFile"),
    ("font", "error.module.fontRefused"),
    ("requirement", "error.module.requirementMissing"),
    ("wrongversion", "error.module.requirementMissing"),
    ("compile", "error.module.compile"),
    ("renderer", "error.module.noRenderer"),
])
def test_T_MOD_16_each_check_refuses(lib, tmp_path, kind, key):
    """T-MOD-16: each failing check refuses the module with its reason in
    plain words, and nothing is left in the library (9.7)."""
    before = sorted(p.relative_to(lib.root).as_posix() for p in lib.root.rglob("*"))
    with pytest.raises(ModuleError) as info:
        modmanager.install(lib, scmod(_broken(kind, tmp_path), tmp_path))
    assert info.value.key == key
    text = Strings.from_library(lib).t(info.value.key, **info.value.details)
    assert "{" not in text and len(text) > 20
    after = sorted(p.relative_to(lib.root).as_posix() for p in lib.root.rglob("*"))
    assert after == before


# --- T-MOD-17 disable, enable, remove ---------------------------------------------------------
@pytest.mark.integration
def test_T_MOD_17_disable_enable_remove(lib, tab, tmp_path):
    """T-MOD-17: a disabled module is not offered and comes back when
    enabled; removing warns with the adventures that use it; after removal
    such an adventure opens in protected mode."""
    modmanager.install(lib, scmod(theme_folder(tmp_path), tmp_path))
    path = adventure_with(tab, tmp_path, "test.ink", "1.0.0")
    tab.close()

    modmanager.set_disabled(lib, "test.ink", "1.0.0", True)
    offered = {t["id"] for g in tab.game_systems() for t in g["themes"]}
    assert "test.ink" not in offered
    assert lib.get("test.ink", "1.0.0") is None and lib.get("test.ink", "1.0.0", include_disabled=True)
    tab.open(path)
    assert tab.read_only == "protected"
    assert tab.missing_details()[0]["reason"] == "disabled"
    banner = tab.t("banner.protected", modules=tab.missing_text())
    assert "You need these modules to edit or export this adventure" in banner
    assert "Ink (test.ink 1.0.0), disabled" in banner

    modmanager.set_disabled(lib, "test.ink", "1.0.0", False)
    assert tab.refresh_modules() is True and tab.read_only is None and not tab.missing
    assert tab.build("svg").ok
    tab.close()

    row = next(r for r in modmanager.module_list(lib, tab.recent._read()) if r["id"] == "test.ink")
    assert row["usedBy"] == [{"title": "Lantern Night", "path": str(path.resolve())}]
    modmanager.remove(lib, "test.ink", "1.0.0")
    assert not (lib.root / "test.ink").exists()
    tab.open(path)
    assert tab.read_only == "protected"
    assert tab.missing_details() == [{"id": "test.ink", "version": "1.0.0", "reason": "missing"}]
    assert "test.ink 1.0.0" in tab.missing_text()


# --- T-MOD-18 switching version with a preview -------------------------------------------------
@pytest.mark.integration
def test_T_MOD_18_switch_version_with_preview(lib, tab, tmp_path):
    """T-MOD-18: two versions listed; the adventure keeps its version until
    switched; the preview uses the trial version; Cancel changes nothing;
    Apply changes only the module lines, and every other file is unchanged."""
    modmanager.install(lib, scmod(theme_folder(tmp_path, version="1.0.0"), tmp_path))
    newer = theme_folder(tmp_path, version="1.1.0")
    page = json.loads((newer / "page.json").read_text("utf-8"))
    page["columns"] = 1 if page.get("columns", 1) != 1 else 2
    (newer / "page.json").write_text(json.dumps(page), "utf-8")
    modmanager.install(lib, scmod(newer, tmp_path))
    path = adventure_with(tab, tmp_path, "test.ink", "1.0.0", "#scene(title: \"Harbour\")[\nThe fog lifts.\n]\n")
    before = files_of(path)
    versions = tab.settings_info()["versions"]["theme"]
    assert versions == {"id": "test.ink", "current": "1.0.0", "installed": ["1.1.0", "1.0.0"]}

    info = tab.preview_version("theme", "1.1.0")
    assert info["versionPreview"]["version"] == "1.1.0" and info["versionPreview"]["major"] is False
    assert tab.adventure.theme.version == "1.0.0" and not tab.dirty
    assert tab.build("svg").ok
    stamp = tab.work_dir / "m" / "test.ink" / ".scriptorum-version"
    assert stamp.read_text() == "1.1.0"
    tab.cancel_version_preview()
    assert tab.build("svg").ok and stamp.read_text() == "1.0.0"
    assert not tab.dirty

    tab.preview_version("theme", "1.1.0")
    # An export never uses the trial version.
    assert tab.export_pdf(tmp_path / "trial.pdf")["ok"]
    assert stamp.read_text() == "1.0.0"
    tab.apply_version_preview()
    assert tab.adventure.theme.version == "1.1.0" and tab.dirty and tab.version_preview is None
    tab.save()
    after = files_of(path)
    assert set(after) == set(before)
    changed = {n for n in after if after[n] != before[n]}
    assert changed == {"manifest.json"}
    old, new = json.loads(before["manifest.json"]), json.loads(after["manifest.json"])
    assert new["theme"] == {"id": "test.ink", "version": "1.1.0"}
    assert [m for m in new["modules"] if m["id"] == "test.ink"] == [{"id": "test.ink", "version": "1.1.0"}]
    for key in old:
        if key not in ("theme", "modules", "modified", "app_version", "app"):
            assert old[key] == new[key], key


# --- T-MOD-19 which adventures use a module ------------------------------------------------------
@pytest.mark.integration
def test_T_MOD_19_used_by_recent_adventures(lib, tab, tmp_path):
    """T-MOD-19: each content module shows the adventures on the Recent files
    list that use it; app modules show none."""
    a = adventure_with(tab, tmp_path, "scriptorum.plain", "1.0.0", name="one")
    tab.new("Second", "scriptorum.free-league-vaesen", "1.0.0", "scriptorum.vaesen", "1.0.0")
    b = tab.save(tmp_path / "two.scav")
    rows = {(r["id"], r["version"]): r for r in modmanager.module_list(lib, tab.recent._read(), tab.app_settings)}
    assert [u["path"] for u in rows[("scriptorum.plain", "1.0.0")]["usedBy"]] == [str(a.resolve())]
    assert [u["title"] for u in rows[("scriptorum.vaesen", "1.0.0")]["usedBy"]] == ["Second"]
    assert {u["title"] for u in rows[("scriptorum.core", "1.0.0")]["usedBy"]} == {"Lantern Night", "Second"}
    assert rows[("scriptorum.claret-and-ink", "1.0.0")]["usedBy"] == []
    b.unlink()  # a file that is gone drops off quietly
    rows = {(r["id"], r["version"]): r for r in modmanager.module_list(lib, tab.recent._read(), tab.app_settings)}
    assert rows[("scriptorum.vaesen", "1.0.0")]["usedBy"] == []


# --- T-MOD-21 safe unpacking ------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.parametrize("entry", ["../escape.json", "templates/../../escape.json", "/tmp/escape.json", "link"])
def test_T_MOD_21_unsafe_entries_refused(lib, tmp_path, entry):
    """T-MOD-21: an entry that climbs out of the folder, an absolute path or a
    link refuses the module, the entry named; nothing is written outside."""
    folder = theme_folder(tmp_path)
    good = scmod(folder, tmp_path)
    bad = tmp_path / "bad.scmod"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as out:
        for item in src.infolist():
            out.writestr(item, src.read(item))
        if entry == "link":
            info = zipfile.ZipInfo("templates/link.typ")
            info.external_attr = (0o120777 << 16)
            out.writestr(info, "/etc/passwd")
        else:
            out.writestr(entry, "{}")
    with pytest.raises(ModuleError) as info:
        modmanager.install(lib, bad)
    assert info.value.key == "error.module.unsafeEntry"
    assert info.value.details["entry"] == ("templates/link.typ" if entry == "link" else entry)
    assert not (lib.root.parent / "escape.json").exists() and not (lib.root / "escape.json").exists()
    assert not Path("/tmp/escape.json").exists()
    assert not [p for p in lib.root.iterdir() if p.name.startswith(".scmod-")]


@pytest.mark.unit
def test_T_MOD_21_resolved_paths_not_text(tmp_path):
    """T-MOD-21: a sibling folder whose name starts with the same text is
    still outside (the old check compared text)."""
    from scriptorum.core.modules import unpack_scmod

    target = tmp_path / "unpack"
    target.mkdir()
    bad = make_zip(tmp_path / "sib.scmod", [("module.json", "{}"), ("../unpack-evil/x.json", "{}")])
    with pytest.raises(ModuleError):
        unpack_scmod(bad, target)
    assert not (tmp_path / "unpack-evil").exists()


# --- T-MOD-22 an adventure without its modules, and Save as .scmod file ---------------------------
@pytest.mark.integration
def test_T_MOD_22_share_adventure_and_scmod(lib, tab, tmp_path):
    """T-MOD-22: the adventure is shared as its .scav file and the module as a
    .scmod saved from the module manager. Opened elsewhere without it, the
    adventure lists the missing module; once installed, it leaves protected
    mode at once and exports byte-identically."""
    modmanager.install(lib, scmod(theme_folder(tmp_path), tmp_path))
    path = adventure_with(tab, tmp_path, "test.ink", "1.0.0", "#scene(title: \"Harbour\")[\nThe fog lifts. Åsa och Örjan.\n]\n")
    assert "modules/" not in " ".join(files_of(path))  # nothing is packed
    original = tmp_path / "original.pdf"
    assert tab.export_pdf(original)["ok"]
    sent = modmanager.save_as_scmod(lib, "test.ink", "1.0.0", tmp_path / "send" / "test.ink")
    assert sent.name == "test.ink.scmod" and "module.json" in zipfile.ZipFile(sent).namelist()
    with pytest.raises(ModuleError) as info:
        modmanager.save_as_scmod(lib, "scriptorum.plain", "1.0.0", tmp_path / "plain.scmod")
    assert info.value.key == "error.module.bundled"

    other_root = tmp_path / "other"
    other = Library(other_root / "library")
    other.install_bundled(BUNDLED)
    there = Session(other, Strings.from_library(other), RecentFiles(other_root / "recent.json"), other_root / "build",
                    home=other_root / "home")
    there.open(path)
    assert there.read_only == "protected"
    banner = there.t("banner.protected", modules=there.missing_text())
    assert "You need these modules to edit or export this adventure: test.ink 1.0.0" in banner
    assert not there.export_pdf(tmp_path / "blocked.pdf")["ok"]
    assert modmanager.install(other, sent)["status"] == "installed"
    assert there.refresh_modules() and there.read_only is None
    copy = tmp_path / "copy.pdf"
    assert there.export_pdf(copy)["ok"]
    assert copy.read_bytes() == original.read_bytes()


# --- T-MOD-23 what may be disabled or removed; one version, one content ----------------------------
@pytest.mark.integration
def test_T_MOD_23_bundled_and_fallback_rules(lib, tab, tmp_path):
    """T-MOD-23: bundled modules can be disabled but not removed; the core
    element kit, the English interface and Claret & Ink neither; a palette or
    interface language in use cannot be disabled."""
    rows = {r["id"]: r for r in modmanager.module_list(lib, [], tab.app_settings)}
    for always in ("scriptorum.core", "scriptorum.en", "scriptorum.claret-and-ink"):
        assert not rows[always]["canDisable"] and not rows[always]["canRemove"]
        assert rows[always]["disableReason"] == "alwaysOn"
        with pytest.raises(ModuleError) as info:
            modmanager.set_disabled(lib, always, "1.0.0", True, tab.app_settings)
        assert info.value.key == "error.module.alwaysOn"
    assert rows["scriptorum.vaesen"]["bundled"] and rows["scriptorum.vaesen"]["canDisable"]
    assert not rows["scriptorum.vaesen"]["canRemove"] and rows["scriptorum.vaesen"]["removeReason"] == "bundled"
    with pytest.raises(ModuleError) as info:
        modmanager.remove(lib, "scriptorum.vaesen", "1.0.0")
    assert info.value.key == "error.module.bundled"
    modmanager.set_disabled(lib, "scriptorum.vaesen", "1.0.0", True)
    lib.install_bundled(BUNDLED)  # the next start does not enable it again
    assert lib.is_disabled("scriptorum.vaesen", "1.0.0")
    modmanager.set_disabled(lib, "scriptorum.vaesen", "1.0.0", False)

    # A palette of your own in use cannot be disabled until another is chosen.
    from scriptorum.core.appsettings import save_palette
    mine = save_palette(lib, "Moss", {}, {})
    tab.app_settings.update({"palette": mine.id, "palette_version": mine.version})
    with pytest.raises(ModuleError) as info:
        modmanager.set_disabled(lib, mine.id, mine.version, True, tab.app_settings)
    assert info.value.key == "error.module.inUse"
    tab.app_settings.update({"palette": "scriptorum.claret-and-ink", "palette_version": None})
    modmanager.set_disabled(lib, mine.id, mine.version, True, tab.app_settings)


@pytest.mark.integration
def test_T_MOD_23_same_version_rule(lib, tmp_path):
    """T-MOD-23: the same file again says it is already installed; the same
    ID and version with other content is refused."""
    folder = theme_folder(tmp_path)
    assert modmanager.install(lib, scmod(folder, tmp_path))["status"] == "installed"
    assert modmanager.install(lib, scmod(folder, tmp_path))["status"] == "already"
    (folder / "labels" / "en.json").write_text(json.dumps({"print.page": "Sida"}), "utf-8")
    with pytest.raises(ModuleError) as info:
        modmanager.install(lib, pack_scmod(folder, tmp_path / "changed.scmod"))
    assert info.value.key == "error.module.sameVersion"
    assert lib.get("test.ink", "1.0.0").labels().get("print.page") != "Sida"


# --- T-MOD-24 another main version --------------------------------------------------------------
@pytest.mark.integration
def test_T_MOD_24_major_version_switch(lib, tab, tmp_path):
    """T-MOD-24: a switch to another MAJOR version is marked so the window
    warns first; an element the new version lacks is drawn in the generic
    frame with a warning, and nothing is converted."""
    modmanager.install(lib, scmod(theme_folder(tmp_path, version="1.0.0"), tmp_path))
    two = theme_folder(tmp_path, version="2.0.0")
    (two / "templates" / "box.typ").unlink()
    modmanager.install(lib, scmod(two, tmp_path))
    text = '#scene(title: "Harbour")[\n#box(title: "Tide")[High water at dawn.]\n]\n'
    adventure_with(tab, tmp_path, "test.ink", "1.0.0", text)
    info = tab.preview_version("theme", "2.0.0")
    assert info["versionPreview"]["major"] is True
    result = tab.build("svg")
    assert result.ok
    assert any(w.key == "warning.build.genericFrame" and w.details["element"] == "box" for w in result.warnings)
    tab.apply_version_preview()
    assert tab.chapter(0)["text"] == text


# --- T-UI-31 the guides install through the module manager ------------------------------------------
@pytest.mark.integration
def test_T_UI_31_guides_install_through_the_module_manager(lib, tmp_path):
    """T-UI-31: both guides' Testing and Packing sections install through
    File ▸ Settings… ▸ Modules, with no copying by hand and no restart; the
    game-system guide's example installs that way with every check."""
    from tests.test_m5e import _harbour_tales

    for name in ("how-to-write-a-theme.md", "how-to-write-a-game-system.md"):
        guide = (GUIDES / name).read_text("utf-8")
        testing = guide[guide.index("## Testing"):]
        assert "File ▸ Settings… ▸ Modules ▸ Install module…" in testing
        assert "Save as .scmod file…" in testing
        assert "restart" not in testing.replace("no need to restart", "")
        assert "Put your theme's folder in the module library" not in guide
        assert "Put the folder in the module library" not in guide
        assert "When the module manager is in your version" not in guide
    folder = _harbour_tales(tmp_path)
    result = modmanager.install(lib, pack_scmod(folder, tmp_path / "yourname.harbour-tales-1.0.0.scmod"))
    assert result["status"] == "installed"


# --- T-MOD-08 the module manager in the window ----------------------------------------------------------
@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6a")
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
    driver.library = library
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def _answer(ui, button="ask-yes"):
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True, 10)
    text = ui.js("document.getElementById('ask-text').textContent")
    ui.js(f"document.getElementById('{button}').click(); true")
    return text


def _row(ui, key):
    return ui.js(f"(() => {{ const r = document.querySelector('.module-table tr[data-module=\"{key}\"]');"
                 " return r ? {disabled: r.classList.contains('is-disabled'), text: r.textContent,"
                 " buttons: [...r.querySelectorAll('button')].map(b => [b.dataset.action, b.disabled])} : null; })()")


@pytest.mark.ui
def test_T_MOD_08_module_manager_in_the_window(ui, tmp_path):
    """T-MOD-08 (with T-MOD-16, 17 and 22 in the window): Settings ▸ Modules
    installs a .scmod, refuses a broken one with its reason, disables and
    enables with a warning, saves it as a file, and removes it."""
    ui.run("window.__scriptorum.openSettingsWindow('modules')")
    assert ui.js("document.getElementById('module-install').textContent") == "Install module…"
    assert _row(ui, "scriptorum.core@1.0.0")["buttons"] == [["disable", True], ["remove", True], ["save", True]]
    vaesen = _row(ui, "scriptorum.vaesen@1.0.0")
    assert ["disable", False] in vaesen["buttons"] and ["remove", True] in vaesen["buttons"]
    assert "comes with Scriptorum" in vaesen["text"]

    broken = scmod(_broken("filetype", tmp_path), tmp_path)
    ui.run(f"window.__scriptorum.shell.installModule({json.dumps(str(broken))})", 120)
    status = ui.js("document.getElementById('module-status').textContent")
    assert "helper.py" in status and ui.js("document.getElementById('module-status').classList.contains('warn')")
    assert _row(ui, "test.ink@1.0.0") is None

    good = scmod(theme_folder(tmp_path / "g"), tmp_path)
    ui.run(f"window.__scriptorum.shell.installModule({json.dumps(str(good))})", 120)
    assert ui.js("document.getElementById('module-status').textContent") == "Ink 1.0.0 is installed."
    assert _row(ui, "test.ink@1.0.0")["buttons"] == [["disable", False], ["remove", False], ["save", False]]

    ui.js("document.querySelector('tr[data-module=\"test.ink@1.0.0\"] button[data-action=disable]').click(); true")
    text = _answer(ui)
    assert "Disable Ink 1.0.0?" in text and "No adventure on your Recent files list uses it" in text
    ui.wait_until(lambda: (_row(ui, "test.ink@1.0.0") or {}).get("disabled") is True, 10)
    assert ui.library.is_disabled("test.ink", "1.0.0")
    ui.js("document.querySelector('tr[data-module=\"test.ink@1.0.0\"] button[data-action=enable]').click(); true")
    ui.wait_until(lambda: (_row(ui, "test.ink@1.0.0") or {}).get("disabled") is False, 10)

    target = ui.folder / "sent" / "ink.scmod"
    target.parent.mkdir()
    ui.run(f"window.__scriptorum.shell.saveModule('test.ink@1.0.0', {json.dumps(str(target))})")
    assert target.is_file() and ui.js("document.getElementById('module-status').textContent").startswith("Saved as ")

    ui.js("document.querySelector('tr[data-module=\"test.ink@1.0.0\"] button[data-action=remove]').click(); true")
    assert "Remove Ink 1.0.0 from this computer?" in _answer(ui)
    ui.wait_until(lambda: _row(ui, "test.ink@1.0.0") is None, 10)
    ui.run("window.__scriptorum.closeSettings()")


@pytest.mark.ui
def test_T_MOD_18_version_bar_in_the_window(ui, tmp_path):
    """T-MOD-18 and T-MOD-17 in the window: the version choice on the
    adventure settings page, the bar over the preview with Apply and Cancel,
    and protected mode entered and left as a module is disabled and enabled."""
    for version in ("1.0.0", "1.1.0"):
        modmanager.install(ui.library, scmod(theme_folder(tmp_path / version, version=version), tmp_path))
    bridge = ui.window.bridge
    bridge._tab_for_new_document().new("Lantern Night", "scriptorum.plain-system", "1.0.0", "test.ink", "1.0.0")
    bridge._changed()
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.openSettingsWindow('adventure')")
    options = ui.js("[...document.getElementById('set-themeVersion').options].map(o => o.value)")
    assert options == ["1.1.0", "1.0.0"] and ui.js("document.getElementById('set-themeVersion').value") == "1.0.0"
    ui.run("window.__scriptorum.pickVersion('theme', '1.1.0')")
    ui.wait_until(lambda: not ui.js("document.getElementById('version-bar').classList.contains('hidden')"), 10)
    assert ui.js("document.getElementById('version-bar-text').textContent").startswith("Previewing Ink 1.1.0.")
    assert bridge.session.adventure.theme.version == "1.0.0"
    ui.run("window.__scriptorum.endVersionPreview(false)")
    assert ui.js("document.getElementById('version-bar').classList.contains('hidden')") is True
    assert bridge.session.adventure.theme.version == "1.0.0"
    ui.run("window.__scriptorum.pickVersion('theme', '1.1.0')")
    ui.run("window.__scriptorum.endVersionPreview(true)")
    assert bridge.session.adventure.theme.version == "1.1.0"

    # Disabling the theme in use puts the open adventure in protected mode at once.
    ui.run("window.__scriptorum.openSettingsWindow('modules')")
    ui.js("document.querySelector('tr[data-module=\"test.ink@1.1.0\"] button[data-action=disable]').click(); true")
    _answer(ui)
    ui.wait_until(lambda: bridge.session.read_only == "protected", 10)
    ui.wait_until(lambda: "Ink (test.ink 1.1.0), disabled" in ui.js("document.getElementById('banner').textContent"), 10)
    ui.js("document.querySelector('tr[data-module=\"test.ink@1.1.0\"] button[data-action=enable]').click(); true")
    ui.wait_until(lambda: bridge.session.read_only is None, 10)
    ui.wait_until(lambda: ui.js("document.getElementById('banner').classList.contains('hidden')") is True, 10)
    ui.run("window.__scriptorum.closeSettings()")
