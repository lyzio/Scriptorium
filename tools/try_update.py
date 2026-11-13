"""Try installing an update by hand, without the project's key and without a
web server (F22, M6-0.6.7). For the project manager's hand checks; it is not
part of the app.

    python tools/try_update.py prepare            a working test update 9.9.9
    python tools/try_update.py prepare --broken   a 9.9.9 that fails to start
    python tools/try_update.py start              start Scriptorum as installed there
    python tools/try_update.py clean              remove everything it made

prepare copies this folder's app into a scratch folder as "the installed
app" (this version), with a throwaway key built in instead of the project's.
It then makes an update pack of the same app as version 9.9.9, signs it with
the throwaway key, and installs it into a scratch Scriptorum folder, just as
Download and install does after the download. Nothing in this repository,
and nothing in your own Scriptorum folder, is changed.

start runs that installed app with that Scriptorum folder, so its start-up
step finds 9.9.9: Help ▸ About shows the version that runs, and the Help
menu offers Go back to version … while 9.9.9 runs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scriptorum import __version__  # noqa: E402
from scriptorum.core import packs, signing  # noqa: E402

PLACE = Path(tempfile.gettempdir()) / "scriptorium-try-update"
TEST_VERSION = "9.9.9"
BROKEN_MAIN = '''def main(argv=None):
    raise RuntimeError("This test version of Scriptorum is broken on purpose (tools/try_update.py --broken).")
'''


def _package_files() -> list:
    try:
        names = subprocess.run(["git", "ls-files", "-z", "scriptorum"], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout.split("\0")
        names = [n for n in names if n]
    except (OSError, subprocess.CalledProcessError):
        names = [p.relative_to(ROOT).as_posix() for p in (ROOT / "scriptorum").rglob("*") if p.is_file()]
    return sorted(n for n in names if "__pycache__" not in n and not n.endswith(".pyc") and (ROOT / n).is_file())


def prepare(broken: bool) -> None:
    clean(quiet=True)
    app = PLACE / "installed-app"
    home = PLACE / "scriptorum-folder"
    files = _package_files()
    for name in files:
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    private, public = signing.new_key_pair()
    (app / "scriptorum" / "core" / "update_key.py").write_text(
        f'"""A throwaway key made by tools/try_update.py, never the project\'s."""\n\nPUBLIC_KEY = "{public}"\n', "utf-8")
    contents = {name: (ROOT / name).read_bytes() for name in files}
    init = "scriptorum/__init__.py"
    contents[init] = contents[init].replace(f'__version__ = "{__version__}"'.encode(), f'__version__ = "{TEST_VERSION}"'.encode())
    if broken:
        contents["scriptorum/app/main.py"] = BROKEN_MAIN.encode()
    listing = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    manifest = json.dumps({"format": packs.PACK_FORMAT, "version": TEST_VERSION, "runtime": packs.runtime(),
                           "files": listing}, indent=1, sort_keys=True).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(packs.MANIFEST, manifest)
        zf.writestr(packs.SIGNATURE, signing.sign(manifest, private))
        for name, data in sorted(contents.items()):
            zf.writestr(name, data)
    pack = PLACE / f"scriptorum-{TEST_VERSION}-update.zip"
    pack.write_bytes(buffer.getvalue())
    packs.Versions(home).install(pack, key=public)
    print(f"Prepared in {PLACE}:")
    print(f"  the installed app is version {__version__}, with a throwaway key;")
    print(f"  version {TEST_VERSION}{' (broken on purpose)' if broken else ''} is installed in its Scriptorum folder.")
    print("Next: python tools/try_update.py start")


def start() -> int:
    app = PLACE / "installed-app"
    if not (app / "scriptorum").is_dir():
        print("Nothing prepared yet. Run: python tools/try_update.py prepare", file=sys.stderr)
        return 1
    env = dict(os.environ, SCRIPTORUM_HOME=str(PLACE / "scriptorum-folder"))
    for name in ("SCRIPTORUM_NO_UPDATES", "SCRIPTORUM_VERSION_DIR", "SCRIPTORUM_BUILTIN_VERSION"):
        env.pop(name, None)
    return subprocess.run([sys.executable, "-m", "scriptorum", *sys.argv[2:]], cwd=app, env=env).returncode


def clean(quiet: bool = False) -> None:
    shutil.rmtree(PLACE, ignore_errors=True)
    if not quiet:
        print(f"Removed {PLACE}.")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python tools/try_update.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["prepare", "start", "clean"])
    parser.add_argument("--broken", action="store_true", help="prepare a 9.9.9 that fails to start")
    args, _ = parser.parse_known_args()
    if args.action == "prepare":
        prepare(args.broken)
        return 0
    if args.action == "start":
        return start()
    clean()
    return 0


if __name__ == "__main__":
    sys.exit(main())
