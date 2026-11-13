"""Make a Scriptorum release: the update pack, its signature and the signed
update file (design document F22 and D12, built in M6-0.6.7).

Once, on the project manager's own computer, make the signing key:

    python tools/release.py keygen

The private key is written outside the repository (by default to
~/.scriptorum-release/update-signing-key.pem; keep it safe and never share
it), and the matching public key into scriptorum/core/update_key.py, which
is committed so every copy of the app can check the signatures.

Then a release is one command, run on the tagged commit of main (D12):

    python tools/release.py 0.6.8 --note "What is new, in one or two lines."

It writes into dist-release/:

    scriptorum-0.6.8-update.zip   the update pack (the scriptorum package,
                                  pack.json with every file's checksum, and
                                  pack.sig, the signature of pack.json)
    scriptorum-update.json        the signed update file (F21, F22)

and, with --publish, attaches both to the GitHub release v0.6.8 of
lyzio/Scriptorum with the gh command (otherwise it prints that command).
On GitHub (decided 13 November 2026) the same script runs in the release job
(.github/workflows/release.yml) when an accepted build's tag v<version> is
pushed: the key then comes only from the repository secret UPDATE (handed to
the script as SCRIPTORUM_SIGNING_KEY), never from a file, and the note from the
tag's message (--note-from-tag). A release is never marked pre-release, since
GitHub's "latest" address, which the app's update address uses, skips
pre-releases (F21).

--moved-to https://… writes into the update file that the update address has
moved. --allow-untagged makes a test release from any commit; such a release
is never published. Nothing here is part of the app; it never runs there.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scriptorum.core import packs, signing, updates  # noqa: E402

# The repository is named in one place only, the app's update address (F21).
REPOSITORY = updates.UPDATE_URL.split("/releases/")[0]
REPOSITORY_SLUG = "/".join(REPOSITORY.rstrip("/").split("/")[-2:])
DEFAULT_KEY = Path.home() / ".scriptorum-release" / "update-signing-key.pem"
KEY_FILE = ROOT / "scriptorum" / "core" / "update_key.py"
SIGNING_ENV = "SCRIPTORUM_SIGNING_KEY"   # the environment variable the release job fills from the secret
SIGNING_SETTING = "UPDATE"                # the repository secret on GitHub that holds the key
ZIP_DATE = (1980, 1, 1, 0, 0, 0)   # the same pack bytes on every computer


class Refused(Exception):
    """A release that may not be made, with the reason in plain words."""


def _inside_repository(path: Path) -> bool:
    path = path.expanduser().resolve()
    return path == ROOT or ROOT in path.parents


def _key_path(given) -> Path:
    if given:
        return Path(given).expanduser()
    env = os.environ.get("SCRIPTORUM_RELEASE_KEY")
    return Path(env).expanduser() if env else DEFAULT_KEY


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def app_version() -> str:
    text = (ROOT / "scriptorum" / "__init__.py").read_text("utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise Refused("scriptorum/__init__.py gives no version.")
    return match.group(1)


def keygen(key_path: Path, force: bool = False) -> str:
    """Make the project's key pair: the private key outside the repository,
    the public key into the app."""
    if _inside_repository(key_path):
        raise Refused(f"The private key may not be kept inside the repository: {key_path}")
    if key_path.exists() and not force:
        raise Refused(f"A key already exists at {key_path}. Every installed copy of Scriptorum trusts "
                      "that key, so it is not replaced (use --force only if you really mean to).")
    pem, public = signing.new_key_pair()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
    write_public_key(public)
    return public


def write_public_key(public: str) -> None:
    text = KEY_FILE.read_text("utf-8")
    text = re.sub(r'PUBLIC_KEY = "[^"]*"', f'PUBLIC_KEY = "{public}"', text)
    KEY_FILE.write_text(text, "utf-8")


def _load_key(key_path: Path) -> bytes:
    """The private key: from the secret SCRIPTORUM_SIGNING_KEY when it is set
    (the release job on GitHub), otherwise from the key file outside the
    repository. The key is only ever held in memory here."""
    secret = os.environ.get(SIGNING_ENV, "").strip()
    if secret:
        pem = (secret + "\n").encode("ascii", errors="replace")
        where = f"the GitHub secret {SIGNING_SETTING}"
    else:
        if _inside_repository(key_path):
            raise Refused(f"The private key may not be kept inside the repository: {key_path}")
        try:
            pem = key_path.read_bytes()
        except OSError as exc:
            raise Refused(f"No signing key: neither the GitHub secret {SIGNING_SETTING} (as {SIGNING_ENV}) nor a key file at {key_path}. "
                          "Make it once with: python tools/release.py keygen") from exc
        where = str(key_path)
    try:
        public = signing.public_of(pem)
    except (ValueError, TypeError) as exc:
        raise Refused(f"{where} is not a signing key.") from exc
    if public != signing.public_key():
        raise Refused("The signing key does not match the public key built into the app "
                      "(scriptorum/core/update_key.py), so no copy of Scriptorum would accept this release.")
    return pem


def check_commit(version: str) -> None:
    """D12: releases are made only from tagged commits on main."""
    if _git("status", "--porcelain", "--untracked-files=no").strip():
        raise Refused("The working tree has changed files. A release is made only from a clean, tagged commit of main.")
    tags = _git("tag", "--points-at", "HEAD").split()
    if f"v{version}" not in tags:
        raise Refused(f"This commit is not tagged v{version}. A release is made only from the tagged commit of main.")
    for main in ("main", "origin/main"):
        try:
            subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", main], cwd=ROOT, check=True,
                           capture_output=True)
            return
        except subprocess.CalledProcessError:
            continue
    raise Refused("This commit is not on main. A release is made only from the tagged commit of main.")


def tag_note(version: str) -> str:
    """The note of a release made on GitHub: the message of the annotated tag
    v<version>, or "Scriptorum <version>" for a tag without a message."""
    try:
        kind = _git("for-each-ref", f"refs/tags/v{version}", "--format=%(objecttype)").strip()
        message = _git("for-each-ref", f"refs/tags/v{version}", "--format=%(contents)") if kind == "tag" else ""
    except subprocess.CalledProcessError:
        message = ""
    message = message.split("-----BEGIN PGP SIGNATURE-----")[0].strip()
    return message or f"Scriptorum {version}"


def changelog_section(version: str, changelog: Path = ROOT / "CHANGELOG.md") -> str:
    """The section of CHANGELOG.md for this version (its heading and text up to
    the next version), which becomes the release's description; empty if the
    changelog has none."""
    try:
        text = changelog.read_text("utf-8")
    except OSError:
        return ""
    lines, keep = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if keep:
                break
            keep = line[3:].split()[0] == version if line[3:].split() else False
        if keep:
            lines.append(line)
    return "\n".join(lines[1:]).strip()


def publish_commands(version: str, files: list, note: str, exists: bool, notes_file=None) -> list:
    """The gh commands that publish the files: a new GitHub release on main,
    described by the version's section of CHANGELOG.md (or the note), or the
    files added to the release of that tag when it already exists. Never a
    pre-release: GitHub's "latest" address skips those (F21)."""
    if exists:
        return [["gh", "release", "upload", f"v{version}", *map(str, files), "--clobber", "--repo", REPOSITORY_SLUG]]
    notes = ["--notes-file", str(notes_file)] if notes_file else ["--notes", note]
    return [["gh", "release", "create", f"v{version}", *map(str, files), "--repo", REPOSITORY_SLUG,
             "--verify-tag", "--title", f"Scriptorum {version}", *notes]]


def package_files() -> list:
    """Every file of the scriptorum package that git tracks, so nothing that
    happens to lie in the folder slips into a pack."""
    names = [n for n in _git("ls-files", "-z", "scriptorum").split("\0") if n]
    names = [n for n in names if "__pycache__" not in n and not n.endswith(".pyc")]
    for name in names:
        if not packs._allowed(name):
            raise Refused(f"{name} is a file type an update pack may not hold.")
    return sorted(names)


def make_pack(version: str, pem: bytes, files: list) -> bytes:
    listing = {}
    contents = {}
    for name in files:
        data = (ROOT / name).read_bytes()
        contents[name] = data
        listing[name] = hashlib.sha256(data).hexdigest()
    manifest = json.dumps({"format": packs.PACK_FORMAT, "version": version, "runtime": packs.PINNED,
                           "files": listing}, indent=1, sort_keys=True).encode("utf-8")
    signature = signing.sign(manifest, pem).encode("ascii")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in [(packs.MANIFEST, manifest), (packs.SIGNATURE, signature)] + sorted(contents.items()):
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return buffer.getvalue()


def make_update_file(version: str, note: str, pack: bytes, pack_name: str, pem: bytes,
                     base_url: str, moved_to=None) -> bytes:
    page = f"{REPOSITORY}/releases/tag/v{version}"
    info = {
        "version": version,
        "note": note.strip(),
        "download": {"linux": page, "macos": page, "windows": page},
        "runtime": packs.PINNED,
        "pack": {"url": f"{base_url.rstrip('/')}/{pack_name}", "sha256": hashlib.sha256(pack).hexdigest(),
                 "size": len(pack), "signature": signing.sign(pack, pem)},
    }
    if moved_to:
        if not updates.address_ok(moved_to):
            raise Refused("--moved-to must be an https address.")
        info["moved_to"] = moved_to
    wrapper = {"update": info, "signature": signing.sign(signing.canonical(info), pem)}
    return (json.dumps(wrapper, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def self_check(version: str, pack: bytes, update_file: bytes) -> None:
    """Check the result the way the app will, before anything is published."""
    result = updates.read_file(update_file, "0.0.0", "linux", have=packs.PINNED)
    if result.get("state") != updates.NEWER or result.get("version") != version or "pack" not in result:
        raise Refused(f"The update file did not pass the app's own check: {result.get('state')}")
    with tempfile.TemporaryDirectory() as temp:
        file = Path(temp) / "pack.zip"
        file.write_bytes(pack)
        manifest = packs.unpack(file, Path(temp) / "unpacked")
        if manifest["version"] != version:
            raise Refused("The pack holds another version.")


def release(version: str, note: str, key_path: Path, out: Path, allow_untagged: bool = False,
            moved_to=None, base_url=None) -> dict:
    if version != app_version():
        raise Refused(f"The app's version is {app_version()}, not {version} (scriptorum/__init__.py).")
    if not note.strip():
        raise Refused("Give a short note on what is new with --note.")
    pem = _load_key(key_path)
    if not allow_untagged:
        check_commit(version)
    files = package_files()
    pack = make_pack(version, pem, files)
    pack_name = f"scriptorum-{version}-update.zip"
    base_url = base_url or f"{REPOSITORY}/releases/download/v{version}"
    update_file = make_update_file(version, note, pack, pack_name, pem, base_url, moved_to)
    self_check(version, pack, update_file)
    out.mkdir(parents=True, exist_ok=True)
    (out / pack_name).write_bytes(pack)
    (out / "scriptorum-update.json").write_bytes(update_file)
    return {"pack": out / pack_name, "update": out / "scriptorum-update.json", "files": len(files)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/release.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="the version to release, or keygen to make the signing key once")
    parser.add_argument("--note", default="", help="what is new, in one or two lines")
    parser.add_argument("--note-from-tag", action="store_true", help="take the note from the tag's message (the release job)")
    parser.add_argument("--key", help=f"the private key (default {DEFAULT_KEY})")
    parser.add_argument("--out", default=str(ROOT / "dist-release"), help="where to write the files")
    parser.add_argument("--moved-to", help="tell every app that the update address has moved here (https)")
    parser.add_argument("--base-url", help="where the pack will be downloaded from (default: the GitHub release)")
    parser.add_argument("--publish", action="store_true", help="attach the files to the GitHub release with gh")
    parser.add_argument("--allow-untagged", action="store_true", help="a test release from any commit (never published)")
    parser.add_argument("--force", action="store_true", help="keygen: replace an existing key")
    args = parser.parse_args(argv)
    try:
        if args.version == "keygen":
            public = keygen(_key_path(args.key), args.force)
            print(f"The private key is in {_key_path(args.key)}. Keep it safe and never share it.")
            print(f"The public key {public} is written into scriptorum/core/update_key.py; commit that file.")
            print("Then give the key to the release job on GitHub, once:")
            print(f"gh secret set {SIGNING_SETTING} --repo {REPOSITORY_SLUG} < {_key_path(args.key)}")
            print("and keep one offline copy of the key file: GitHub never shows a secret again.")
            return 0
        if args.publish and args.allow_untagged:
            raise Refused("A test release made with --allow-untagged is never published.")
        note = tag_note(args.version) if args.note_from_tag else args.note
        made = release(args.version, note, _key_path(args.key), Path(args.out), args.allow_untagged,
                       args.moved_to, args.base_url)
    except Refused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    print(f"Made {made['pack'].name} ({made['files']} files) and {made['update'].name} in {made['pack'].parent}.")
    files = [made["pack"], made["update"]]
    description = changelog_section(args.version)
    notes_file = None
    if description:
        notes_file = made["pack"].parent / f"release-notes-{args.version}.md"
        notes_file.write_text(description + "\n", "utf-8")
    if args.publish:
        exists = subprocess.run(["gh", "release", "view", f"v{args.version}", "--repo", REPOSITORY_SLUG],
                                capture_output=True).returncode == 0
        for command in publish_commands(args.version, files, note, exists, notes_file):
            subprocess.run(command, check=True)
        print(f"Published on the GitHub release v{args.version}.")
    else:
        print("To publish it as the GitHub release, run:")
        for command in publish_commands(args.version, files, note, False, notes_file):
            print(" ".join(f'"{c}"' if " " in c else c for c in command))
    return 0


if __name__ == "__main__":
    sys.exit(main())
