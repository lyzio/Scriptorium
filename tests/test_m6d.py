"""M6 part D on GitHub, build M6-0.6.8: the installers job and the packaging
kit in packaging/ (decided 13 November 2026).

T-REL-09  the installers job; the kit takes its pins from the app; cryptography
          goes into the frozen app
T-REL-10  (manual) the first installers from GitHub on real computers
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "packaging"
WORKFLOW = ROOT / ".github" / "workflows" / "installers.yml"


def kit_module():
    spec = importlib.util.spec_from_file_location("scriptorum_packaging_kit", KIT / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_pins() -> dict:
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.M | re.S).group(1)
    return dict(re.findall(r'"([A-Za-z0-9_.\-]+)==([^"]+)"', block))


@pytest.mark.integration
def test_T_REL_09_installers_workflow():
    """T-REL-09: built for a tag and from Run workflow, on Ubuntu 22.04, both
    Macs and Windows, with Python 3.13; --release only for a tag; results kept
    as downloads; attached only for a tag (or when asked), once the release
    exists; never a pre-release; write access only where it attaches."""
    text = WORKFLOW.read_text("utf-8")
    assert 'tags: ["v*"]' in text and "workflow_dispatch:" in text
    for machine in ("ubuntu-22.04", "macos-15 }", "macos-15-intel", "windows-2022"):
        assert machine in text, machine
    assert 'python-version: "3.13"' in text
    assert "python kit/packaging/build.py app --out out $flags" in text
    assert 'FOR_RELEASE: ${{ github.event_name == \'push\' }}' in text and 'flags="--release"' in text
    assert "actions/upload-artifact@v4" in text and "if-no-files-found: error" in text
    assert "if: github.event_name == 'push' || inputs.attach" in text
    assert 'gh release view "$TAG"' in text and "gh release upload" in text and "--clobber" in text
    assert "prerelease" not in text and "release create" not in text   # the release job makes it (F22)
    top, jobs = text.split("\njobs:", 1)
    assert "contents: read" in top and text.count("contents: write") == 1
    assert jobs.index("contents: write") > jobs.index("attach:")
    assert "persist-credentials: false" in text and "secrets." not in text
    # The Linux libraries are the kit's own list.
    kit = kit_module()
    for package in {deb for deb, _ in kit.LINUX_LIBRARIES.values()}:
        assert package in text, package


@pytest.mark.unit
def test_T_REL_09_kit_takes_the_pins_from_the_app(tmp_path):
    """T-REL-09: the kit reads every pinned version from the app's own
    pyproject.toml and names none of its own; a build that does not pin a
    needed library is refused; cryptography is needed from 0.6.7."""
    kit = kit_module()
    config = json.loads((KIT / "kit.json").read_text("utf-8"))
    assert "pins" not in config and config["kit_version"] == "1.0.2"
    assert kit.read_pins(ROOT) == app_pins()
    assert {"PySide6", "typst", "spylls", "cryptography"} <= set(app_pins())
    for text in (KIT / "build.py").read_text("utf-8"), (KIT / "common" / "scriptorum.spec").read_text("utf-8"):
        for version in app_pins().values():
            assert f'"{version}"' not in text, version      # no copy of a pin in the kit
    # A build without cryptography pinned, from a version that signs updates: refused.
    src = tmp_path / "app"
    (src / "scriptorum" / "core").mkdir(parents=True)
    (src / "scriptorum" / "core" / "signing.py").write_text("")
    (src / "pyproject.toml").write_text('dependencies = [\n    "PySide6==6.8.3",\n    "typst==0.15.0",\n'
                                        '    "spylls==0.1.7",\n]\n')
    with pytest.raises(SystemExit):
        kit.read_pins(src)
    (src / "scriptorum" / "core" / "signing.py").unlink()     # an older version (before 0.6.7)
    assert kit.read_pins(src) == {"PySide6": "6.8.3", "typst": "0.15.0", "spylls": "0.1.7"}
    # The real build folder passes the kit's check, with the app's own pins.
    kit.PINS.clear()
    assert kit.check_source(ROOT, release=True) == __import__("scriptorum").__version__
    assert kit.PINS == app_pins()


@pytest.mark.unit
def test_T_REL_09_release_check_reads_the_address(tmp_path):
    """T-REL-09: --release refuses only an app whose UPDATE_URL is still the
    placeholder; from 0.6.7 the file names the placeholder as a constant too."""
    kit = kit_module()
    assert not kit.update_address_is_placeholder((ROOT / "scriptorum" / "core" / "updates.py").read_text("utf-8"))
    assert kit.update_address_is_placeholder('PLACEHOLDER = "Paste update url here"\nUPDATE_URL = PLACEHOLDER\n')
    assert kit.update_address_is_placeholder('UPDATE_URL = "Paste update url here"\n')


@pytest.mark.unit
def test_T_REL_09_frozen_app_carries_cryptography():
    """T-REL-09: the PyInstaller recipe carries cryptography's code and its
    package metadata, and spylls's, which the start-up step reads (F22)."""
    spec = (KIT / "common" / "scriptorum.spec").read_text("utf-8")
    metadata = re.search(r'for dist in \(([^)]*)\):\n\s+try:\n\s+datas \+= copy_metadata\(dist\)', spec)
    assert metadata and {"spylls", "cryptography"} <= set(re.findall(r'"([^"]+)"', metadata.group(1)))
    assert 'collect_submodules("cryptography.hazmat.primitives")' in spec
    # The frozen app starts through the start-up step (F22), as python -m scriptorum does.
    assert 'SRC / "scriptorum" / "__main__.py"' in spec
    assert "from scriptorum.boot import run" in (ROOT / "scriptorum" / "__main__.py").read_text("utf-8")


@pytest.mark.unit
def test_T_REL_09_kit_leaves_its_own_work_out(tmp_path, monkeypatch):
    """T-REL-09: built from the repository folder, the kit's own work/ and
    dist/ never go into the copied source."""
    kit = kit_module()
    src = tmp_path / "repo"
    (src / "packaging" / "work" / "venv").mkdir(parents=True)
    (src / "packaging" / "dist").mkdir()
    (src / "packaging" / "build.py").write_text("")
    (src / "scriptorum").mkdir()
    (src / "scriptorum" / "__init__.py").write_text('__version__ = "0.6.8"\n')
    (src / "packaging" / "work" / "venv" / "big.bin").write_text("x")
    monkeypatch.setattr(kit, "KIT", src / "packaging")
    kit.clean_copy(src, tmp_path / "copy")
    copied = {p.relative_to(tmp_path / "copy").as_posix() for p in (tmp_path / "copy").rglob("*")}
    assert "packaging/build.py" in copied and "scriptorum/__init__.py" in copied
    assert not any(name.startswith(("packaging/work", "packaging/dist")) for name in copied)


@pytest.mark.unit
def test_T_REL_11_code_scanning_findings_stay_fixed():
    """T-REL-11: the three regular expressions CodeQL found in Cytoscape.js's
    stylesheet parser (js/redos) are not in the bundled interface; the build
    replaces them and would stop if Cytoscape changed them."""
    bundle = (ROOT / "scriptorum" / "ui" / "dist" / "app.js").read_text("utf-8")
    for unsafe in ("(\\s|.)", "(?:.|\\s)", "(.|\\s)", "(?:\\s|.)"):
        assert unsafe not in bundle, unsafe
    assert "remaining.replace(/[/][*][\\s\\S]+?[*][/]/g" in bundle
    build = (ROOT / "ui-src" / "build.mjs").read_text("utf-8")
    assert "throw new Error(`Cytoscape no longer contains" in build
    assert json.loads((ROOT / "ui-src" / "package.json").read_text("utf-8"))["scripts"]["build"] == "node build.mjs"
    # The release script names the secret's setting without the word that makes
    # code scanning take it for a secret (alert 1, a false alarm, renamed).
    release = (ROOT / "tools" / "release.py").read_text("utf-8")
    assert "GITHUB_SECRET" not in release and "KEY_SECRET" not in release


@pytest.mark.unit
def test_T_REL_11_release_description_from_the_changelog():
    """T-REL-11: a release is described by its version's section of
    CHANGELOG.md; the README holds no version history."""
    spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    version = __import__("scriptorum").__version__
    section = tool.changelog_section(version)
    assert section and "Windows installer has not been tested yet" in section
    assert not section.startswith("## ") and "\n## " not in section
    assert tool.changelog_section("9.9.9") == ""
    command = tool.publish_commands(version, ["a.zip"], "Note.", exists=False, notes_file=Path("notes.md"))[0]
    assert command[-2:] == ["--notes-file", "notes.md"]
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "## What " not in readme and "CHANGELOG.md" in readme and "Not yet tested" in readme
