"""M6 part C5, build M6-0.6.7: installing updates (F22) and the fixes for
issues #8 and #9.

T-REL-04  signed update files and packs; damaged or unsafe ones refused
T-REL-05  Download and install from Help ▸ Check for updates…
T-REL-06  the start-up step, going back by itself and by hand, two versions kept
T-REL-07  the release script and the signing key
T-REL-08  the release job on GitHub, with the key as the secret UPDATE
T-UI-44   the manual update address
T-UI-45   the update address can move
T-UI-46   paragraphs fill the editor's width (issue #8)
T-UI-47   a short block's ↑ ↓ + × menu stays usable (issue #9)
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scriptorum import __version__
from scriptorum.core import packs, signing, update_key, updates
from scriptorum.core.packs import PackError, Versions
from tests.update_keys import OTHER_PRIVATE, OTHER_PUBLIC, PRIVATE, PUBLIC, signed

ROOT = Path(__file__).resolve().parents[1]

RUN_MAIN = '''import os
def main(argv):
    import scriptorum
    print("RAN " + scriptorum.__version__ + " " + os.path.dirname(os.path.abspath(scriptorum.__file__)))
    return 0
'''
FAIL_MAIN = '''def main(argv):
    raise RuntimeError("this version is broken")
'''
CRASH_MAIN = '''import os
def main(argv):
    os._exit(3)
'''


def pack_bytes(version, main=RUN_MAIN, runtime=None, private=PRIVATE, extra=None, tamper=None,
               unlisted=None, raw=None, link=None) -> bytes:
    """A small update pack for the tests: a scriptorum package whose app.main
    reports which version ran."""
    files = {
        "scriptorum/__init__.py": f'__version__ = "{version}"\n'.encode(),
        "scriptorum/app/__init__.py": b"",
        "scriptorum/app/main.py": main.encode(),
        "scriptorum/bundled/LICENSE": b"GPL",
    }
    files.update(extra or {})
    listing = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = json.dumps({"format": 1, "version": version, "runtime": runtime or packs.runtime(),
                           "files": listing}).encode()
    signature = signing.sign(manifest, private).encode()
    if tamper:
        files[tamper] = files[tamper] + b"# changed after signing\n"
    if unlisted:
        files[unlisted] = b"not in the list"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("pack.json", manifest)
        zf.writestr("pack.sig", signature)
        for name, data in files.items():
            zf.writestr(name, data)
        for name in raw or []:
            zf.writestr(name, b"x")
        if link:
            info = zipfile.ZipInfo(link)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return buffer.getvalue()


def write(tmp_path, name, data) -> Path:
    file = tmp_path / name
    file.write_bytes(data)
    return file


def update_info(version, pack=None, url="https://example.org/scriptorum-update.zip", runtime=None, **more):
    info = {"version": version, "note": "Better exports.",
            "download": {"linux": "https://example.org/dl", "macos": "https://example.org/dl", "windows": "https://example.org/dl"},
            "runtime": runtime or packs.runtime()}
    if pack is not None:
        info["pack"] = {"url": url, "sha256": hashlib.sha256(pack).hexdigest(), "size": len(pack),
                        "signature": signing.sign(pack, PRIVATE)}
    info.update(more)
    return info


def snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


# --- T-REL-04 signatures -------------------------------------------------------------------

@pytest.mark.unit
def test_T_REL_04_update_file_signature():
    """T-REL-04: only an update file signed with the project's key is used;
    an unsigned one, one signed with another key, one changed after signing,
    a cut-short one and one read by a copy without a key are refused."""
    info = update_info("9.0.0")
    assert updates.read_file(signed(info), "0.6.7")["state"] == "newer"
    unsigned = json.dumps(info).encode()
    assert updates.read_file(unsigned, "0.6.7") == {"state": "unsigned"}
    assert updates.read_file(signed(info, OTHER_PRIVATE), "0.6.7") == {"state": "unsigned"}
    changed = json.loads(signed(info))
    changed["update"]["note"] = "Something else."
    assert updates.read_file(json.dumps(changed).encode(), "0.6.7") == {"state": "unsigned"}
    assert updates.read_file(signed(info)[:-20], "0.6.7") == {"state": "invalid"}
    assert updates.read_file(signed(info), "0.6.7", key="") == {"state": "no-key"}
    saved = update_key.PUBLIC_KEY
    try:
        update_key.PUBLIC_KEY = ""
        assert updates.read_file(signed(info), "0.6.7") == {"state": "no-key"}
    finally:
        update_key.PUBLIC_KEY = saved
    assert signing.key_set(PUBLIC) and not signing.key_set("") and not signing.key_set("not a key")


@pytest.mark.unit
def test_T_REL_04_packs_checked(tmp_path):
    """T-REL-04: a correct pack unpacks; every damaged or unsafe one is
    refused with its reason, and nothing in the author's folder changes."""
    home = tmp_path / "home"
    versions = Versions(home)
    good = write(tmp_path, "good.zip", pack_bytes("0.6.8"))
    assert versions.install(good, have=None)["version"] == "0.6.8"
    before = snapshot(home)
    cases = {
        "signature": pack_bytes("0.6.9", private=OTHER_PRIVATE),
        "damaged": pack_bytes("0.6.9", tamper="scriptorum/app/main.py"),
        "unlisted": pack_bytes("0.6.9", unlisted="scriptorum/extra.py"),
        "unsafe": pack_bytes("0.6.9", raw=["../escape.py"]),
        "filetype": pack_bytes("0.6.9", raw=["scriptorum/tool.exe"]),
        "runtime": pack_bytes("0.6.9", runtime={"python": "2.7", "pyside6": "1.0.0"}),
    }
    for reason, data in cases.items():
        with pytest.raises(PackError) as caught:
            versions.install(write(tmp_path, f"{reason}.zip", data))
        assert caught.value.reason == reason, (reason, caught.value)
        assert snapshot(home) == before, reason
    for name, data in (("absolute", pack_bytes("0.6.9", raw=["/tmp/escape.py"])),
                       ("link", pack_bytes("0.6.9", link="scriptorum/link.py"))):
        with pytest.raises(PackError) as caught:
            versions.install(write(tmp_path, f"{name}.zip", data))
        assert caught.value.reason == "unsafe", name
        assert snapshot(home) == before, name
    with pytest.raises(PackError) as caught:
        versions.install(write(tmp_path, "short.zip", pack_bytes("0.6.9")[:400]))
    assert caught.value.reason == "damaged"
    assert snapshot(home) == before
    assert not (tmp_path / "escape.py").exists() and not Path("/tmp/escape.py").exists()


@pytest.mark.unit
def test_T_REL_04_download_checked(tmp_path):
    """T-REL-04: the downloaded pack must match the signed update file's size,
    checksum and signature; a download that fails changes nothing."""
    versions = Versions(tmp_path / "home")
    data = pack_bytes("0.6.8")
    pack = update_info("0.6.8", data)["pack"]
    with pytest.raises(updates.InstallError) as caught:
        updates.install(pack, versions, lambda url: data + b"x")
    assert caught.value.reason == "damaged"
    wrong = dict(pack, signature=signing.sign(data, OTHER_PRIVATE))
    with pytest.raises(updates.InstallError) as caught:
        updates.install(wrong, versions, lambda url: data)
    assert caught.value.reason == "signature"

    def down(url):
        raise OSError("no route")
    with pytest.raises(updates.InstallError) as caught:
        updates.install(pack, versions, down)
    assert caught.value.reason == "unreachable"
    with pytest.raises(updates.InstallError) as caught:
        updates.install(pack, versions, lambda url: data, expected="0.6.9")
    assert caught.value.reason == "version"
    assert versions.kept() == [] and versions.state()["current"] is None
    assert updates.install(pack, versions, lambda url: data) == "0.6.8"
    assert versions.kept() == ["0.6.8"]


# --- T-REL-06 the start-up step ------------------------------------------------------------------

def boot(tmp_path, home, key=PUBLIC, builtin=None) -> str:
    """Run the start-up step in its own process, as the installed app does,
    with the installed app's own version standing in for the real window."""
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from scriptorum.core import update_key\n"
        f"update_key.PUBLIC_KEY = {key!r}\n"
        "from scriptorum import boot\n"
        "boot._builtin_main = lambda argv: (print('RAN builtin ' + boot.builtin_version()), 0)[1]\n"
        "from pathlib import Path\n"
        f"sys.exit(boot.run([], home=Path({str(home)!r})))\n"
    )
    env = dict(os.environ, SCRIPTORUM_HOME=str(home))
    env.pop("SCRIPTORUM_NO_UPDATES", None)
    env.pop("SCRIPTORUM_VERSION_DIR", None)
    env.pop("SCRIPTORUM_BUILTIN_VERSION", None)
    if builtin:
        env["SCRIPTORUM_BUILTIN_VERSION"] = builtin
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True,
                            text=True, timeout=120)
    return (result.stdout + result.stderr).strip()


def ran(output: str) -> str:
    lines = [line for line in output.splitlines() if line.startswith("RAN ")]
    return lines[-1].split()[1] if lines else output


def install(tmp_path, versions, version, main=RUN_MAIN, running=None, **opts):
    return versions.install(write(tmp_path, f"p-{version}.zip", pack_bytes(version, main, **opts)), running=running)


@pytest.mark.integration
def test_T_REL_06_runs_a_newer_verified_version(tmp_path):
    """T-REL-06: a newer verified version in the author's folder runs, from
    that folder; damaged, missing, made for another Python or Qt, or not
    newer than the installed app: the installed app runs its own version."""
    home = tmp_path / "home"
    versions = Versions(home)
    assert ran(boot(tmp_path, home)) == "builtin"           # nothing kept
    install(tmp_path, versions, "9.0.8")
    out = boot(tmp_path, home)
    assert ran(out) == "9.0.8" and str(versions.folder("9.0.8")) in out
    assert versions.state()["trying"] is None                 # it started
    # Damaged: one file changed after it was installed.
    main = versions.folder("9.0.8") / "scriptorum" / "app" / "main.py"
    main.write_text(main.read_text() + "\n# changed\n")
    assert ran(boot(tmp_path, home)) == "builtin"
    # Missing.
    shutil.rmtree(versions.folder("9.0.8"))
    assert ran(boot(tmp_path, home)) == "builtin"
    # Made for another Python and Qt: unpacked by hand, never chosen.
    packs.unpack(write(tmp_path, "other.zip", pack_bytes("9.0.9", runtime={"python": "2.7", "pyside6": "1.0.0"})),
                 versions.folder("9.0.9"))
    state = versions.state()
    state.update({"current": "9.0.9", "failed": []})
    versions.save(state)
    assert ran(boot(tmp_path, home)) == "builtin"
    # Not newer than the installed app.
    install(tmp_path, versions, "0.0.1")
    assert ran(boot(tmp_path, home)) == "builtin"
    # Signed with another key than the one built into the installed app.
    install(tmp_path, versions, "9.1.0")
    assert ran(boot(tmp_path, home, key=OTHER_PUBLIC)) == "builtin"
    assert ran(boot(tmp_path, home)) == "9.1.0"


@pytest.mark.integration
def test_T_REL_06_goes_back_when_a_version_fails(tmp_path):
    """T-REL-06: a version that fails with an error goes back to the previous
    one at once; one that never reports that it started goes back at the
    next start; either way Scriptorum says so, and the failed version is not
    run again."""
    home = tmp_path / "home"
    versions = Versions(home)
    install(tmp_path, versions, "9.0.8")
    assert ran(boot(tmp_path, home)) == "9.0.8"
    install(tmp_path, versions, "9.0.9", FAIL_MAIN, running="9.0.8")
    out = boot(tmp_path, home)
    assert ran(out) == "9.0.8", out
    assert versions.take_notice() == {"kind": "failed", "version": "9.0.9", "back_to": "9.0.8"}
    assert ran(boot(tmp_path, home)) == "9.0.8"                 # never run again
    assert list((home / "logs").glob("update-start-*.log"))      # details stay on this computer
    # A crash before the window opened: back at the next start.
    install(tmp_path, versions, "9.1.0", CRASH_MAIN, running="9.0.8")
    out = boot(tmp_path, home)
    assert "RAN" not in out and versions.state()["trying"] == "9.1.0"
    assert ran(boot(tmp_path, home)) == "9.0.8"
    assert versions.take_notice() == {"kind": "failed", "version": "9.1.0", "back_to": "9.0.8"}
    # With no previous version kept, the installed app's own version runs.
    versions2 = Versions(tmp_path / "home2")
    install(tmp_path, versions2, "9.0.9", FAIL_MAIN)
    assert ran(boot(tmp_path, tmp_path / "home2")) == "builtin"
    assert versions2.take_notice() == {"kind": "failed", "version": "9.0.9", "back_to": __version__}


@pytest.mark.integration
def test_T_REL_06_go_back_by_hand_and_two_kept(tmp_path):
    """T-REL-06: Help ▸ Go back to version X makes the next start run X; only
    the newest and the previous version are kept; adventures, modules,
    palettes and settings are never touched."""
    home = tmp_path / "home"
    (home / "modules" / "someone.theme" / "1.0.0").mkdir(parents=True)
    (home / "modules" / "someone.theme" / "1.0.0" / "module.json").write_text('{"id": "someone.theme"}')
    (home / "app-settings.json").write_text('{"palette": "scriptorum.claret-and-ink"}')
    (home / "recent.json").write_text('["/home/gm/adventure.scav"]')
    keep = {k: v for k, v in snapshot(home).items()}
    versions = Versions(home)
    install(tmp_path, versions, "9.0.8")
    install(tmp_path, versions, "9.0.9", running="9.0.8")
    assert versions.kept() == ["9.0.8", "9.0.9"]
    assert ran(boot(tmp_path, home)) == "9.0.9"
    install(tmp_path, versions, "9.1.0", running="9.0.9")
    assert versions.kept() == ["9.0.9", "9.1.0"]                 # 0.6.8 removed
    assert ran(boot(tmp_path, home)) == "9.1.0"
    # Going back from 0.7.0 runs 0.6.9 next time; 0.7.0 is removed then.
    assert versions.back_target("9.1.0", __version__) == "9.0.9"
    assert versions.go_back("9.1.0", __version__) == "9.0.9"
    assert ran(boot(tmp_path, home)) == "9.0.9"
    assert versions.kept() == ["9.0.9"]
    assert versions.take_notice() == {"kind": "back", "version": "9.1.0", "back_to": "9.0.9"}
    # From the only kept version, going back runs the installed app's own.
    assert versions.back_target("9.0.9", __version__) == __version__
    assert versions.go_back("9.0.9", __version__) == __version__
    assert ran(boot(tmp_path, home)) == "builtin"
    # Nothing to go back to while the installed app's own version runs.
    assert versions.back_target(__version__, __version__) is None
    after = snapshot(home)
    for name, data in keep.items():
        assert after[name] == data, name


# --- T-REL-07 the release script -----------------------------------------------------------------

def _repo_copy(tmp_path: Path, version: str) -> Path:
    """A copy of this repository as its own git repository, with the version
    to release, so the release script can be run on it as written."""
    repo = tmp_path / "repo"
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for name in filter(None, names.split("\0")):
        source = ROOT / name
        if not source.is_file():
            continue
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for name in ("scriptorum/core/signing.py", "scriptorum/core/packs.py", "scriptorum/core/update_key.py",
                 "scriptorum/boot.py", "tools/release.py", ".github/workflows/release.yml"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, repo / name)
    init = repo / "scriptorum" / "__init__.py"
    init.write_text(init.read_text("utf-8").replace(f'__version__ = "{__version__}"', f'__version__ = "{version}"'), "utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.org")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "copy"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
    return repo


def _release(repo: Path, *args: str, extra_env=None, drop=()):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.org")
    env.pop("SCRIPTORUM_SIGNING_KEY", None)
    env.update(extra_env or {})
    for name in drop:
        env.pop(name, None)
    return subprocess.run([sys.executable, "tools/release.py", *args], cwd=repo, env=env, capture_output=True,
                          text=True, timeout=300)


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.org")
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)


@pytest.mark.integration
def test_T_REL_07_release_script(tmp_path):
    """T-REL-07: the key is made once, outside the repository; one command on
    the tagged commit of main makes the pack and the signed update file;
    wrong cases are refused and write nothing; the app installs the result
    and runs it at the next start."""
    version = "9.9.1"
    repo = _repo_copy(tmp_path, version)
    key = tmp_path / "keys" / "signing.pem"
    # The private key may not live inside the repository.
    inside = _release(repo, "keygen", "--key", str(repo / "signing.pem"))
    assert inside.returncode == 1 and "inside the repository" in inside.stderr
    made = _release(repo, "keygen", "--key", str(key))
    assert made.returncode == 0, made.stderr
    assert key.is_file() and stat.S_IMODE(key.stat().st_mode) == 0o600
    public = signing.public_of(key.read_bytes())
    assert f'PUBLIC_KEY = "{public}"' in (repo / "scriptorum" / "core" / "update_key.py").read_text()
    again = _release(repo, "keygen", "--key", str(key))
    assert again.returncode == 1 and "already exists" in again.stderr
    _git(repo, "commit", "-q", "-am", "the project's public key")
    out = repo / "dist-release"
    # Not tagged yet.
    refused = _release(repo, version, "--note", "Better exports.", "--key", str(key))
    assert refused.returncode == 1 and f"not tagged v{version}" in refused.stderr
    _git(repo, "tag", f"v{version}")
    # Changed files.
    readme = repo / "README.md"
    readme.write_text(readme.read_text() + "\nchanged\n")
    refused = _release(repo, version, "--note", "Better exports.", "--key", str(key))
    assert refused.returncode == 1 and "changed files" in refused.stderr
    _git(repo, "checkout", "README.md")
    # A version that is not the app's.
    refused = _release(repo, "9.9.2", "--note", "x", "--key", str(key))
    assert refused.returncode == 1 and "not 9.9.2" in refused.stderr
    # The key inside the repository.
    shutil.copy2(key, repo / "copied.pem")
    refused = _release(repo, version, "--note", "x", "--key", str(repo / "copied.pem"))
    assert refused.returncode == 1 and "inside the repository" in refused.stderr
    (repo / "copied.pem").unlink()
    assert not out.exists()
    # The real one.
    done = _release(repo, version, "--note", "Better exports.", "--key", str(key))
    assert done.returncode == 0, done.stderr
    assert "gh release create v9.9.1" in done.stdout
    pack = out / f"scriptorum-{version}-update.zip"
    update_file = out / "scriptorum-update.json"
    assert pack.is_file() and update_file.is_file()
    with zipfile.ZipFile(pack) as zf:
        names = zf.namelist()
    assert names[:2] == ["pack.json", "pack.sig"]
    assert "scriptorum/app/main.py" in names and not any("__pycache__" in n for n in names)
    assert not any(n.startswith(("tests/", "ui-src/", "tools/")) for n in names)
    # The app checks the file with the project's key and installs the pack.
    result = updates.read_file(update_file.read_bytes(), __version__, "linux", key=public, have=packs.PINNED)
    assert result["state"] == "newer" and result["version"] == version
    assert result["pack"]["url"] == f"https://github.com/lyzio/Scriptorum/releases/download/v{version}/scriptorum-{version}-update.zip"
    assert result["download"] == f"https://github.com/lyzio/Scriptorum/releases/tag/v{version}"
    home = tmp_path / "home"
    versions = Versions(home)
    assert updates.install(result["pack"], versions, lambda url: pack.read_bytes(), key=public,
                           have=packs.runtime() if packs.runtime() == packs.PINNED else None,
                           expected=version) == version
    # Two runs make the same pack, byte for byte.
    second = _release(repo, version, "--note", "Better exports.", "--key", str(key), "--out", str(tmp_path / "again"))
    assert second.returncode == 0
    assert (tmp_path / "again" / pack.name).read_bytes() == pack.read_bytes()
    # The next start runs it, from the author's folder.
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from scriptorum.core import update_key\n"
        f"update_key.PUBLIC_KEY = {public!r}\n"
        "from scriptorum import boot\n"
        "real = boot._main_of\n"
        "def fake(folder, argv):\n"
        "    real(folder, argv)\n"
        "    import scriptorum\n"
        "    return lambda a: (print('RAN', scriptorum.__version__, scriptorum.__file__), 0)[1]\n"
        "boot._main_of = fake\n"
        "boot._builtin_main = lambda argv: (print('RAN builtin'), 0)[1]\n"
        "from pathlib import Path\n"
        f"sys.exit(boot.run([], home=Path({str(home)!r})))\n"
    )
    env = dict(os.environ, SCRIPTORUM_HOME=str(home))
    env.pop("SCRIPTORUM_NO_UPDATES", None)
    started = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert f"RAN {version} {versions.folder(version)}" in started.stdout, started.stdout + started.stderr
    # A test release is never published.
    refused = _release(repo, version, "--note", "x", "--key", str(key), "--allow-untagged", "--publish")
    assert refused.returncode == 1 and "never published" in refused.stderr


@pytest.mark.integration
def test_T_REL_08_release_job_on_github(tmp_path):
    """T-REL-08: the workflow runs only for a tag v<version>, in the protected
    environment "release", on a standard runner with the pinned Python and
    library, and may only write releases; the script signs with the key from
    the secret alone and never writes it; a missing or wrong secret is
    refused; the note is the tag's message; never a pre-release."""
    import importlib.util
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    assert 'tags: ["v*"]' in workflow and "branches" not in workflow.split("jobs:")[0]
    assert "environment: release" in workflow and "runs-on: ubuntu-24.04" in workflow
    assert workflow.count("permissions:") == 1 and "contents: write" in workflow
    assert "SCRIPTORUM_SIGNING_KEY: ${{ secrets.UPDATE }}" in workflow and "secrets." not in workflow.replace("secrets.UPDATE", "")
    assert 'python-version: "3.13"' in workflow and "--note-from-tag --publish" in workflow
    pinned = [line.strip().strip('",') for line in (ROOT / "pyproject.toml").read_text().splitlines() if "cryptography==" in line]
    assert pinned and f'"{pinned[0]}"' in workflow
    assert "prerelease" not in workflow
    spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    new = tool.publish_commands("9.9.1", ["a.zip", "u.json"], "Note.", exists=False)
    again = tool.publish_commands("9.9.1", ["a.zip", "u.json"], "Note.", exists=True)
    assert new[0][:4] == ["gh", "release", "create", "v9.9.1"] and "--verify-tag" in new[0]
    assert again[0][:3] == ["gh", "release", "upload"] and "--clobber" in again[0]
    assert not any("prerelease" in part for command in new + again for part in command)
    assert tool.REPOSITORY_SLUG == "lyzio/Scriptorum" and tool.GITHUB_SECRET == "UPDATE"

    version = "9.9.1"
    repo = _repo_copy(tmp_path, version)
    home = tmp_path / "ci-home"           # the runner's home: no key file there
    home.mkdir()
    key = tmp_path / "keys" / "signing.pem"
    assert _release(repo, "keygen", "--key", str(key)).returncode == 0
    _git(repo, "commit", "-q", "-am", "the project's public key")
    _git(repo, "tag", "-a", f"v{version}", "-m", "Better maps.\n\nAnd quicker exports.")
    secret = {"SCRIPTORUM_SIGNING_KEY": key.read_text(), "HOME": str(home)}
    done = _release(repo, version, "--note-from-tag", extra_env=secret)
    assert done.returncode == 0, done.stderr
    update_file = json.loads((repo / "dist-release" / "scriptorum-update.json").read_text())
    assert update_file["update"]["note"] == "Better maps.\n\nAnd quicker exports."
    public = signing.public_of(key.read_bytes())
    assert updates.read_file(json.dumps(update_file).encode(), "0.6.7", key=public, have=packs.PINNED)["state"] == "newer"
    # The key was never written anywhere but where keygen put it.
    body = key.read_bytes().splitlines()[1]          # the key itself, not its PEM header
    leaked = [p for folder in (repo, home) for p in folder.rglob("*")
              if p.is_file() and ".git" not in p.parts and body in p.read_bytes()]
    assert leaked == []
    shutil.rmtree(repo / "dist-release")
    # A missing secret, with no key file either: refused, nothing written.
    missing = _release(repo, version, "--note-from-tag", extra_env={"HOME": str(home)})
    assert missing.returncode == 1 and "No signing key" in missing.stderr
    # Another key in the secret: refused.
    wrong = _release(repo, version, "--note-from-tag",
                     extra_env={"SCRIPTORUM_SIGNING_KEY": OTHER_PRIVATE.decode(), "HOME": str(home)})
    assert wrong.returncode == 1 and "does not match" in wrong.stderr
    assert not (repo / "dist-release").exists()
    # A tag without a message gives "Scriptorum <version>".
    _git(repo, "tag", "-d", f"v{version}")
    _git(repo, "tag", f"v{version}")
    plain = _release(repo, version, "--note-from-tag", extra_env=secret)
    assert plain.returncode == 0, plain.stderr
    note = json.loads((repo / "dist-release" / "scriptorum-update.json").read_text())["update"]["note"]
    assert note == f"Scriptorum {version}"


# --- the window: T-REL-05, T-UI-44, T-UI-45, T-UI-46, T-UI-47 -------------------------------------

from tests.test_m6c2 import load, text, ui  # noqa: E402,F401


def _check(ui, url, file_bytes):
    bridge = ui.window.bridge
    bridge.update_url = url
    bridge.update_opener = lambda u: file_bytes
    done = ui.js("Number(document.body.dataset.updateDone || 0)")
    ui.run("window.__scriptorum.updates.check()")
    ui.wait_until(lambda: ui.js("Number(document.body.dataset.updateDone || 0)") == done + 1, 15)
    ui.wait(100)
    return {
        "text": ui.js("document.getElementById('update-text').textContent"),
        "install": not ui.js("document.getElementById('update-install').classList.contains('hidden')"),
        "open": not ui.js("document.getElementById('update-open').classList.contains('hidden')"),
        "address": ui.js("document.getElementById('update-address').textContent"),
    }


def _close_dialogs(ui):
    ui.js("for (const d of document.querySelectorAll('dialog[open]')) d.close(); true")
    if not ui.js("document.getElementById('settings').classList.contains('hidden')"):
        ui.js("document.getElementById('settings-close').click(); true")
        ui.wait(200)


@pytest.mark.ui
def test_T_REL_05_download_and_install(ui, tmp_path):
    """T-REL-05: Download and install appears beside the download page and
    nothing is downloaded until it is clicked; the pack is checked and
    unpacked into the author's folder; the open adventure and its unsaved
    text are untouched; a version that needs a newer Python, Qt or Typst
    offers only the download page."""
    bridge = ui.window.bridge
    bridge.versions = Versions(tmp_path / "home")
    load(ui, '#scene(title: "Harbour")[\nThe boats.\n]\n')
    bridge.session.set_chapter_text(0, '#scene(title: "Harbour")[\nThe boats, unsaved.\n]\n')
    ui.run("window.__scriptorum.refresh()")
    before = text(ui)
    assert bridge.session.dirty
    data = pack_bytes("9.0.1")
    url = "https://example.org/scriptorum-update.json"
    pack_url = "https://example.org/scriptorum-9.0.1-update.zip"
    downloads = []
    bridge.update_downloader = lambda u: downloads.append(u) or data
    bridge.update_requests.clear()
    blocked = len(ui.window.interceptor.blocked)
    r = _check(ui, url, signed(update_info("9.0.1", data, pack_url)))
    assert r["text"] == f"Scriptorum 9.0.1 is available. You have {__version__}."
    assert r["install"] and r["open"]
    assert downloads == [] and bridge.versions.kept() == []
    assert ui.js("document.getElementById('update-install').textContent") == "Download and install"
    done = ui.js("Number(document.body.dataset.installDone || 0)")
    ui.js("document.getElementById('update-install').click(); true")
    ui.wait_until(lambda: ui.js("Number(document.body.dataset.installDone || 0)") == done + 1, 30)
    assert ui.js("document.getElementById('update-install-text').textContent") == \
        "Ready. The update is installed the next time Scriptorum starts."
    assert downloads == [pack_url] and bridge.update_requests == [url, pack_url]
    assert bridge.versions.kept() == ["9.0.1"] and bridge.versions.state()["current"] == "9.0.1"
    assert text(ui) == before and bridge.session.dirty
    assert len(ui.window.interceptor.blocked) == blocked
    # The installed app's own files are not changed.
    assert (ROOT / "scriptorum" / "__init__.py").read_text().count(f'"{__version__}"') == 1
    # A damaged download is refused and changes nothing.
    r = _check(ui, url, signed(update_info("9.0.2", data, pack_url)))
    bridge.update_downloader = lambda u: data[:-10]
    done = ui.js("Number(document.body.dataset.installDone || 0)")
    ui.js("document.getElementById('update-install').click(); true")
    ui.wait_until(lambda: ui.js("Number(document.body.dataset.installDone || 0)") == done + 1, 30)
    assert ui.js("document.getElementById('update-install-text').textContent").startswith("The update was refused")
    assert bridge.versions.kept() == ["9.0.1"]
    # A version that needs a newer Python, Qt or Typst: only the download page.
    other = dict(packs.runtime(), pyside6="6.9.0")
    r = _check(ui, url, signed(update_info("9.1.0", data, pack_url, runtime=other)))
    assert "This version needs a new installer" in r["text"]
    assert not r["install"] and r["open"]
    _close_dialogs(ui)


@pytest.mark.ui
def test_T_REL_06_go_back_and_notice_in_the_window(ui, tmp_path, monkeypatch):
    """T-REL-06 in the window: Help ▸ Go back to version X is offered only
    while a version from the author's folder runs; the notice of a version
    that did not start is shown once."""
    bridge = ui.window.bridge
    bridge.versions = Versions(tmp_path / "home")
    help_items = lambda: [i["label"] for m in ui.js("window.__scriptorum.menuModel()")  # noqa: E731
                          if m["key"] == "menu.help" for i in m["items"]]
    ui.run("window.__scriptorum.updates.loadVersionInfo()")
    assert not any(label.startswith("Go back to version") for label in help_items())
    state = bridge.versions.state()
    state["notice"] = {"kind": "failed", "version": "9.0.2", "back_to": "9.0.1"}
    bridge.versions.save(state)
    bridge.start_notice = bridge.versions.take_notice()
    monkeypatch.setenv("SCRIPTORUM_BUILTIN_VERSION", "0.6.0")   # as if 0.6.0 were the installed app
    ui.run("window.__scriptorum.updates.loadVersionInfo()")
    assert ui.js("document.getElementById('message-dialog').open") is True
    assert ui.js("document.getElementById('message-text').textContent") == \
        "Scriptorum 9.0.2 did not start, so Scriptorum went back to version 9.0.1."
    _close_dialogs(ui)
    assert "Go back to version 0.6.0" in help_items()
    ui.js("window.__scriptorum.updates.goBack(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True, 5)
    assert "Go back to Scriptorum 0.6.0" in ui.js("document.getElementById('ask-text').textContent")
    ui.js("document.getElementById('ask-yes').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('message-dialog').open") is True, 5)
    assert ui.js("document.getElementById('message-text').textContent") == \
        "Scriptorum 0.6.0 runs the next time Scriptorum starts."
    assert bridge.versions.state()["notice"]["kind"] == "back"
    _close_dialogs(ui)
    monkeypatch.delenv("SCRIPTORUM_BUILTIN_VERSION")
    ui.run("window.__scriptorum.updates.loadVersionInfo()")
    _close_dialogs(ui)


@pytest.mark.ui
def test_T_UI_44_update_address(ui):
    """T-UI-44: an https address entered in Settings is used and named in the
    Check for updates window; anything else is refused with a plain message;
    Use built-in address brings the built-in address back; with the
    placeholder built in, the entered address works on its own."""
    bridge = ui.window.bridge
    settings = bridge.session.app_settings
    settings.update({"update_address": ""})
    assert updates.UPDATE_URL == "https://github.com/lyzio/Scriptorum/releases/latest/download/scriptorium-update.json"
    ui.run("window.__scriptorum.openSettingsWindow('application')")
    assert ui.js("document.getElementById('app-updateAddress').value") == ""
    for bad in ("http://example.org/u.json", "not an address", "ftp://example.org/u.json"):
        ui.js(f"(() => {{ const i = document.getElementById('app-updateAddress'); i.value = {json.dumps(bad)};"
              " i.dispatchEvent(new Event('change')); return true; })()")
        ui.wait_until(lambda: not ui.js("document.getElementById('app-updateAddressError').classList.contains('hidden')"), 5)
        assert ui.js("document.getElementById('app-updateAddressError').textContent").startswith("Only a secure https address")
        assert settings.get("update_address") == ""
    entered = "https://mirror.example.org/scriptorium-update.json"
    ui.js(f"(() => {{ const i = document.getElementById('app-updateAddress'); i.value = {json.dumps(entered)};"
          " i.dispatchEvent(new Event('change')); return true; })()")
    ui.wait_until(lambda: settings.get("update_address") == entered, 5)
    assert ui.js("document.getElementById('app-updateAddressError').classList.contains('hidden')") is True
    ui.js("document.getElementById('settings-close').click(); true")
    bridge.update_requests.clear()
    asked = []
    r = _check(ui, updates.PLACEHOLDER, signed(update_info(__version__)))
    # The placeholder is built in, yet the entered address works on its own.
    assert bridge.update_requests == [entered]
    assert r["text"].startswith("Scriptorum is up to date")
    assert r["address"] == f"Address used: {entered} (entered in Settings)"
    _close_dialogs(ui)
    ui.run("window.__scriptorum.openSettingsWindow('application')")
    ui.js("document.getElementById('app-updateAddressReset').click(); true")
    ui.wait_until(lambda: settings.get("update_address") == "", 5)
    assert ui.js("document.getElementById('app-updateAddress').value") == ""
    ui.js("document.getElementById('settings-close').click(); true")
    ui.wait(200)
    bridge.update_requests.clear()
    r = _check(ui, updates.UPDATE_URL, signed(update_info(__version__)))
    assert bridge.update_requests == [updates.UPDATE_URL]
    assert r["address"] == f"Address used: {updates.UPDATE_URL} (built in)"
    # A file from any address must still carry the project's signature.
    r = _check(ui, updates.UPDATE_URL, signed(update_info("9.0.0"), OTHER_PRIVATE))
    assert r["text"].startswith("The update file is not signed with the project's key") and not r["install"]
    _close_dialogs(ui)
    del asked


@pytest.mark.ui
def test_T_UI_45_address_moved(ui):
    """T-UI-45: a signed update file that says the address has moved offers
    the new address; No changes nothing, Yes stores it and the next check
    asks only there; an unsigned or wrongly signed file is ignored."""
    bridge = ui.window.bridge
    settings = bridge.session.app_settings
    settings.update({"update_address": ""})
    url = updates.UPDATE_URL
    moved = "https://updates.example.org/scriptorium-update.json"

    def check_and_answer(file_bytes, answer):
        done = ui.js("Number(document.body.dataset.movedDone || 0)")
        _check(ui, url, file_bytes)
        ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open") is True, 5)
        assert ui.js("document.getElementById('ask-text').textContent") == \
            f"The update address has moved to {moved}. Use the new address?"
        ui.js(f"document.getElementById('{answer}').click(); true")
        ui.wait_until(lambda: ui.js("Number(document.body.dataset.movedDone || 0)") == done + 1, 5)

    check_and_answer(signed(update_info(__version__, moved_to=moved)), "ask-cancel")
    assert settings.get("update_address") == ""
    check_and_answer(signed(update_info(__version__, moved_to=moved)), "ask-yes")
    assert settings.get("update_address") == moved
    bridge.update_requests.clear()
    _check(ui, url, signed(update_info(__version__)))
    assert bridge.update_requests == [moved]
    settings.update({"update_address": ""})
    # Unsigned, and signed with another key: ignored, no move offered.
    for file_bytes in (json.dumps({"update": update_info("9.0.0", moved_to=moved)}).encode(),
                       signed(update_info("9.0.0", moved_to=moved), OTHER_PRIVATE)):
        done = ui.js("Number(document.body.dataset.movedDone || 0)")
        r = _check(ui, url, file_bytes)
        ui.wait(300)
        assert r["text"].startswith("The update file is not signed with the project's key"), r
        assert ui.js("document.getElementById('ask-dialog').open") is False
        assert ui.js("Number(document.body.dataset.movedDone || 0)") == done
        assert settings.get("update_address") == "" and not r["install"]
    _close_dialogs(ui)


LONG = "A long paragraph that runs on and on. " * 40

WIDTH_TEXT = f"""= The act

{LONG}

#scene(title: "The church")[
{LONG}

=== {"A heading that runs on and on " * 8}

#box(title: "A vision")[
Inside the box.
]
]
"""


def _width(ui, js):
    return ui.js(f"({js}).getBoundingClientRect().width")


@pytest.mark.ui
def test_T_UI_46_paragraphs_fill_the_width(ui):
    """T-UI-46 (issue #8): paragraphs and headings fill the editor column like
    the frames, in a narrow and a wide window, in full screen and with the
    preview hidden; nothing stops at about 100 characters."""
    load(ui, WIDTH_TEXT)
    top = "[...document.querySelectorAll('#visual > .blk-paragraph, #visual .blk-paragraph')][0]"
    inner = "document.querySelector('#visual .el-scene .blk-paragraph')"

    def measure(label):
        ui.wait(300)
        para = _width(ui, f"{top}.querySelector('.rich')")
        block = _width(ui, top)
        scene = _width(ui, "document.querySelector('#visual .el-scene')")
        inner_para = _width(ui, f"{inner}.querySelector('.rich')")
        inner_block = _width(ui, inner)
        heading = _width(ui, "document.querySelector('#visual .el-scene .heading-edit')")
        hundred = ui.js("(() => { const s = document.createElement('span'); s.textContent = '0'.repeat(100);"
                        f" const r = {top}.querySelector('.rich'); r.append(s); const w = s.getBoundingClientRect().width;"
                        " s.remove(); return w; })()")
        assert abs(para - block) <= 2, (label, para, block)
        assert abs(para - scene) <= 2, (label, para, scene)
        assert abs(inner_para - inner_block) <= 2, (label, inner_para, inner_block)
        assert abs(heading - inner_block) <= 2, (label, heading, inner_block)
        return para, hundred

    ui.window.resize(1000, 800)
    measure("narrow")
    ui.window.resize(2400, 1000)
    para, hundred = measure("wide")
    assert para > hundred * 1.1, (para, hundred)
    ui.run("window.__scriptorum.setPreview(false)")
    para_hidden, _ = measure("preview hidden")
    assert para_hidden > para
    ui.run("window.__scriptorum.setPreview(true)")
    ui.window.resize(1440, 900)
    ui.window.set_full_screen(True)
    ui.wait(500)
    measure("full screen")
    ui.window.set_full_screen(False)
    ui.wait(300)
    ui.window.resize(1440, 900)


SHORT_TEXT = """First line.

Second line.

Third line.

#scene(title: "The farm")[
Inside one.

Inside two.
]
"""


def _mouse(ui, x, y):
    """Move the real mouse over the page (CSS pixels), so :hover works as for a person."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    target = ui.window.view.focusProxy() or ui.window.view
    QTest.mouseMove(target, QPoint(int(x), int(y)))
    ui.wait(80)


def _rect(ui, js):
    return ui.js(f"(() => {{ const r = ({js}).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }})()")


def _shown_menus(ui):
    return ui.js("[...document.querySelectorAll('#visual .blk')].filter(b => { const c = b.querySelector(':scope > .blk-controls');"
                 " return c && getComputedStyle(c).display !== 'none'; }).map(b => b.textContent.trim().slice(0, 24))")


@pytest.mark.ui
def test_T_UI_47_short_block_menu(ui):
    """T-UI-47 (issue #9): on a one-line block the ↑ ↓ + × buttons sit in a
    2 × 2 square beside it; while the pointer is on that menu no other
    block's menu shows, and each button acts on the hovered block."""
    _close_dialogs(ui)
    for where, first, second in (("top", "First line.", "Second line."), ("scene", "Inside one.", "Inside two.")):
        load(ui, SHORT_TEXT)
        block = f"window.__blk({json.dumps(first)})"
        ui.js(f"{block}.scrollIntoView({{block: 'center'}}); true")
        ui.wait(150)
        bx, by, bw, bh = _rect(ui, block)
        _mouse(ui, bx + 40, by + bh / 2)
        controls = f"{block}.querySelector(':scope > .blk-controls')"
        assert ui.js(f"getComputedStyle({controls}).display") == "grid"
        buttons = ui.js(f"[...{controls}.querySelectorAll('button')].map(b => {{ const r = b.getBoundingClientRect();"
                        " return [b.getAttribute('aria-label'), Math.round(r.left), Math.round(r.top), r.width, r.height]; })")
        assert [b[0] for b in buttons] == ["Move up", "Move down", "Insert after", "Delete"], buttons
        lefts = sorted({b[1] for b in buttons})
        tops = sorted({b[2] for b in buttons})
        assert len(lefts) == 2 and len(tops) == 2, buttons          # a 2 × 2 square
        square = tops[1] + buttons[0][4] - tops[0]
        assert square <= 52 and square > bh, (square, bh)            # it hangs below the one-line block
        # Move the pointer onto the menu and down over every button.
        for label, x, y, w, h in buttons:
            _mouse(ui, x + w / 2, y + h / 2)
            hit = ui.js(f"(() => {{ const e = document.elementFromPoint({x + w / 2}, {y + h / 2});"
                        f" return e && e.closest('.blk-controls') === {controls}; }})()")
            assert hit, (where, label)
            menus = _shown_menus(ui)
            assert len(menus) == 1 and first[:5] in menus[0], (where, label, menus)
        # ↓ on the lower row acts on the hovered block, never on the next one.
        down = [b for b in buttons if b[0] == "Move down"][0]
        _mouse(ui, down[1] + down[3] / 2, down[2] + down[4] / 2)
        ui.js(f"document.elementFromPoint({down[1] + down[3] / 2}, {down[2] + down[4] / 2}).click(); true")
        ui.wait(300)
        written = text(ui)
        assert written.index(second) < written.index(first), (where, written)
        # Moving away lets go of the menu.
        _mouse(ui, 5, 5)
        assert ui.js("document.body.classList.contains('blk-menu-held')") is False
