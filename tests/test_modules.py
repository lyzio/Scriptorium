"""Test Plan group MOD — modules (section 9)."""

from __future__ import annotations

import json
import shutil

import pytest

from scriptorum import paths
from scriptorum.core.build import self_test
from scriptorum.core.modules import (
    ID_RE,
    Library,
    ModuleError,
    pack_scmod,
    validate_folder,
    version_matches,
)
from scriptorum.core.scav import ModuleRef, new_adventure

BUNDLED = paths.BUNDLED_MODULES_DIR


def _copy(name: str, tmp_path, new_id: str = None, version: str = None):
    target = tmp_path / (new_id or name)
    shutil.copytree(BUNDLED / name, target)
    manifest = json.loads((target / "module.json").read_text())
    if new_id:
        manifest["id"] = new_id
    if version:
        manifest["version"] = version
    (target / "module.json").write_text(json.dumps(manifest))
    return target


@pytest.mark.unit
def test_T_MOD_01_bundled_manifests_valid(library):
    """T-MOD-01: every bundled module is valid and its ID has an author prefix (D13)."""
    folders = [p for p in BUNDLED.iterdir() if (p / "module.json").is_file()]
    # M4: the two general themes and the Claret & Ink palette (F8, F16).
    # M5: the Plain game system and the Plain theme (F8, decided 11 Nov 2026).
    assert {p.name for p in folders} == {
        "scriptorum.core", "scriptorum.free-league-vaesen", "scriptorum.vaesen", "scriptorum.en",
        "scriptorum.legends-and-lattes", "scriptorum.call-of-cthulhu", "scriptorum.claret-and-ink",
        "scriptorum.plain-system", "scriptorum.plain",
    }
    for folder in folders:
        manifest = validate_folder(folder)
        assert ID_RE.match(manifest["id"])
        assert manifest["id"] == folder.name
    installed = {m.key for m in library.installed()}
    assert {"scriptorum.core@1.0.0", "scriptorum.free-league-vaesen@1.0.0", "scriptorum.vaesen@1.0.0", "scriptorum.en@1.0.0"} <= installed


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["evil.py", "script.js", "notes.md", "run.sh"])
def test_T_MOD_02_forbidden_file_type(tmp_path, bad):
    """T-MOD-02: a module with a forbidden file type is refused, file named."""
    folder = _copy("scriptorum.vaesen", tmp_path, new_id="test.vaesen")
    (folder / "templates" / bad).write_text("print('hi')")
    with pytest.raises(ModuleError) as info:
        validate_folder(folder)
    assert info.value.key == "error.module.forbiddenFile"
    assert bad in info.value.details["file"]


@pytest.mark.unit
def test_T_MOD_03_missing_requirement(tmp_path, library):
    """T-MOD-03: a missing or wrong-version requirement refuses installation."""
    empty = Library(tmp_path / "empty-library")
    theme = _copy("scriptorum.vaesen", tmp_path, new_id="test.lonely")
    with pytest.raises(ModuleError) as info:
        empty.install_folder(theme)
    assert info.value.key == "error.module.requirementMissing"
    assert info.value.details["requires"] == "scriptorum.free-league-vaesen"

    manifest = json.loads((theme / "module.json").read_text())
    manifest["requires"] = [{"id": "scriptorum.free-league-vaesen", "version": "2.x"}]
    (theme / "module.json").write_text(json.dumps(manifest))
    with pytest.raises(ModuleError):
        library.install_folder(theme)
    assert version_matches("1.4.2", "1.x") and not version_matches("1.4.2", "2.x")
    assert version_matches("1.4.2", "1.4.x") and version_matches("1.4.2", "1.4.2")


@pytest.mark.unit
def test_T_MOD_04_versions_side_by_side(tmp_path, library, session):
    """T-MOD-04: two versions installed; an adventure uses the exact version it pins."""
    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    newer = _copy("scriptorum.vaesen", tmp_path, version="1.1.0")
    (newer / "page.json").write_text(json.dumps({**json.loads((newer / "page.json").read_text()), "columns": 1}))
    lib.install_folder(newer, allow_reserved=True)
    assert {m.version for m in lib.installed() if m.id == "scriptorum.vaesen"} == {"1.0.0", "1.1.0"}

    from scriptorum.core.build import Builder
    builder = Builder(lib, tmp_path / "build")
    kits = [ModuleRef("scriptorum.core", "1.0.0")]
    gs = ModuleRef("scriptorum.free-league-vaesen", "1.0.0")
    old = new_adventure("Old", gs, ModuleRef("scriptorum.vaesen", "1.0.0"), kits, "= Old\n")
    assert builder.content_modules(old)["scriptorum.vaesen"].version == "1.0.0"
    builder.prepare(old)
    assert json.loads((tmp_path / "build" / "m" / "scriptorum.vaesen" / "page.json").read_text())["columns"] == 2
    new = new_adventure("New", gs, ModuleRef("scriptorum.vaesen", "1.1.0"), kits, "= New\n")
    builder.prepare(new)
    assert json.loads((tmp_path / "build" / "m" / "scriptorum.vaesen" / "page.json").read_text())["columns"] == 1


@pytest.mark.integration
def test_T_MOD_05_generic_frame(tmp_path):
    """T-MOD-05: an element kind without a renderer is drawn in the generic frame, with a warning."""
    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    lite = _copy("scriptorum.vaesen", tmp_path, new_id="test.vaesen-lite")
    (lite / "templates" / "person.typ").unlink()
    lib.install_folder(lite)

    from scriptorum.core.build import Builder
    adventure = new_adventure(
        "Lite", ModuleRef("scriptorum.free-league-vaesen", "1.0.0"), ModuleRef("test.vaesen-lite", "1.0.0"),
        [ModuleRef("scriptorum.core", "1.0.0")],
        "#scene(title: \"S\")[\n#person(name: \"Elsa\", mood: \"Calm\")[\n]\n]\n",
    )
    result = Builder(lib, tmp_path / "build").build(adventure, "pdf")
    assert result.ok
    assert [w.details["element"] for w in result.warnings if w.key == "warning.build.genericFrame"] == ["person"]


@pytest.mark.integration
def test_T_MOD_06_modules_compile_against_test_adventure(library, tmp_path):
    """T-MOD-06: every installed theme with its game system compiles the test adventure."""
    assert self_test(library, tmp_path) == []


@pytest.mark.unit
def test_T_MOD_09_scmod_package_round_trip(tmp_path):
    """T-MOD-09: a module packed as .scmod installs like its folder; reserved prefix refused for others."""
    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    folder = _copy("scriptorum.vaesen", tmp_path, new_id="test.packed")
    package = pack_scmod(folder, tmp_path / "test.packed.scmod")
    module = lib.install_scmod(package)
    assert module.key == "test.packed@1.0.0"
    assert (module.path / "templates" / "scene.typ").is_file()

    reserved = _copy("scriptorum.vaesen", tmp_path, version="9.0.0")
    with pytest.raises(ModuleError) as info:
        lib.install_scmod(pack_scmod(reserved, tmp_path / "reserved.scmod"))
    assert info.value.key == "error.module.reservedPrefix"


# --- Milestone 2 -------------------------------------------------------------------

def _game_with(tmp_path, lib, new_id: str, turned_on=None, stat_block=None):
    """A copy of the Vaesen game system and theme with other choices."""
    game = _copy("scriptorum.free-league-vaesen", tmp_path, new_id=new_id)
    if turned_on is not None:
        (game / "elements.json").write_text(json.dumps({"on": turned_on}))
    if stat_block is not None:
        (game / "stat-blocks" / "creature.json").write_text(json.dumps(stat_block))
    lib.install_folder(game)
    theme = _copy("scriptorum.vaesen", tmp_path, new_id=new_id + "-theme")
    manifest = json.loads((theme / "module.json").read_text())
    manifest["requires"] = [{"id": new_id, "version": "1.x"}]
    (theme / "module.json").write_text(json.dumps(manifest))
    lib.install_folder(theme)
    return new_id, new_id + "-theme"


def _session_for(lib, tmp_path, game_id, theme_id):
    from scriptorum.core.i18n import Strings
    from scriptorum.core.recent import RecentFiles
    from scriptorum.core.session import Session

    s = Session(lib, Strings.from_library(lib), RecentFiles(tmp_path / "recent.json"), tmp_path / "build")
    s.new("Test", game_id, "1.0.0", theme_id, "1.0.0")
    return s


@pytest.mark.unit
def test_T_MOD_10_game_system_turns_elements_on(tmp_path):
    """T-MOD-10: only the elements the game system turns on are offered and
    recognised; the others stay locked blocks (9.3, amended 5 Nov 2026)."""
    from scriptorum.core import source

    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    game, theme = _game_with(tmp_path, lib, "test.mini", turned_on=["scene", "read-aloud"])
    s = _session_for(lib, tmp_path, game, theme)
    # M5: the layout markers, the table of contents and footnotes are always on (9.3, F7.4, F7.7).
    always = {"page-break", "column-break", "full-width", "keep-together", "contents", "footnote"}
    assert set(s.kinds()) == {"scene", "read-aloud"} | always
    assert {e["id"] for e in s.editor_info()["elements"]} == {"scene", "read-aloud"} | always
    text = '#scene(title: "S")[\n#read-aloud[Read.]\n\n#information[Not here.]\n]\n'
    doc = source.parse(text, s.kinds())
    inner = doc["blocks"][0]["body"]["blocks"]
    assert [b["type"] for b in inner] == ["element", "locked"]
    assert source.serialize(doc, s.kinds()) == text
    # Vaesen turns on every element of the core kit.
    vaesen = json.loads((BUNDLED / "scriptorum.free-league-vaesen" / "elements.json").read_text())["on"]
    kit = json.loads((BUNDLED / "scriptorum.core" / "module.json").read_text())["element_order"]
    assert set(vaesen) == set(kit) - {"page-break", "column-break"}


@pytest.mark.integration
def test_T_MOD_11_creature_stat_block(tmp_path):
    """T-MOD-11: the creature shows the game system's stats; a value outside
    the range is reported on the author's line (11.5)."""
    from pypdf import PdfReader
    import io

    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    block = {"element": "creature", "stats": [{"id": "brawn", "label": "stat.brawn", "min": 1, "max": 6}], "sections": ["skills"]}
    game, theme = _game_with(tmp_path, lib, "test.other", stat_block=block)
    s = _session_for(lib, tmp_path, game, theme)
    creature = next(e for e in s.editor_info()["elements"] if e["id"] == "creature")
    names = [f["name"] for f in creature["fields"]]
    assert "brawn" in names and "skills" in names
    assert "might" not in names and "banishment" not in names
    brawn = next(f for f in creature["fields"] if f["name"] == "brawn")
    assert (brawn["kind"], brawn["min"], brawn["max"], brawn["group"]) == ("number", 1, 6, "stats")

    s.set_chapter_text(0, '= Beasts\n\n#creature(name: "Troll", brawn: 7)\n')
    result = s.build("pdf")
    assert not result.ok
    error = result.errors[0]
    assert (error.key, error.details, error.line) == ("error.build.outOfRange", {"element": "creature", "field": "brawn"}, 3)
    s.set_chapter_text(0, '= Beasts\n\n#creature(name: "Troll", brawn: 5, skills: [Climb 3])\n')
    result = s.build("pdf")
    assert result.ok, [s.localize(e) for e in result.errors]
    flat = "".join("".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(result.output[0])).pages)
    assert "TROLL" in flat and "BRAWN5" in flat and "SKILLS" in flat and "Climb3" in flat
    assert "MIGHT" not in flat


@pytest.mark.unit
def test_T_MOD_12_changed_bundled_module_replaces_installed_copy(tmp_path):
    """T-MOD-12: a bundled module with the same version but changed files
    replaces the installed copy at start-up."""
    lib = Library(tmp_path / "lib")
    lib.install_bundled(BUNDLED)
    newer = tmp_path / "bundled"
    shutil.copytree(BUNDLED, newer)
    labels = newer / "scriptorum.vaesen" / "labels" / "en.json"
    data = json.loads(labels.read_text())
    data["print.page"] = "Sida"
    labels.write_text(json.dumps(data))
    lib.install_bundled(newer)
    assert lib.get("scriptorum.vaesen", "1.0.0").labels()["print.page"] == "Sida"
    # A third-party module keeps its installed copy (only bundled ones refresh).
    third = _copy("scriptorum.vaesen", tmp_path, new_id="test.keep")
    lib.install_folder(third)
    (third / "labels" / "en.json").write_text(json.dumps({"print.page": "Changed"}))
    # Corrected for M6 (F14, decided 12 Nov 2026): a changed third-party
    # module with the same version is refused, and the installed copy stays.
    with pytest.raises(ModuleError) as info:
        lib.install_folder(third)
    assert info.value.key == "error.module.sameVersion"
    assert lib.get("test.keep", "1.0.0").labels()["print.page"] == "Page"
