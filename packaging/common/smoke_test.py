"""Check a packaged Scriptorum before it is wrapped into an installer (F10).

Three checks, each with its result on one line:
  1. contents   the parts F10 lists are inside: the interface, the bundled
                modules and fonts, the dictionaries, the example adventure,
                the licence texts, Qt WebEngine and its resources
  2. typst      the packaged app's own build helper (F7.1) builds a one-line
                page to PDF, so Python and Typst work inside the package
  3. start      the packaged app starts without a screen, installs its bundled
                modules into a scratch folder and keeps running for 25 seconds
                with no Python error

Only the standard library is used. Run by build.py; can also be run by hand:
  python smoke_test.py <folder made by PyInstaller> <the program inside it>
"""

from __future__ import annotations

import os
import pickle
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

START_SECONDS = 25


def _find(root: Path, pattern: str) -> list:
    return [p for p in root.rglob(pattern)]


def check_contents(root: Path) -> list:
    """Return a list of what is missing (empty when all is there)."""
    missing = []
    package = next((p for p in _find(root, "scriptorum") if p.is_dir() and (p / "bundled").is_dir()), None)
    if package is None:
        return ["the scriptorum package with its bundled/ folder"]
    wanted = {
        "interface (ui/index.html)": package / "ui" / "index.html",
        "interface script (ui/dist/app.js)": package / "ui" / "dist" / "app.js",
        "core element kit (bundled/scriptorum.core/module.json)": package / "bundled" / "scriptorum.core" / "module.json",
        "English interface (bundled/scriptorum.en)": package / "bundled" / "scriptorum.en",
        "Vaesen game system (bundled/scriptorum.free-league-vaesen)": package / "bundled" / "scriptorum.free-league-vaesen",
        "Vaesen theme (bundled/scriptorum.vaesen)": package / "bundled" / "scriptorum.vaesen",
        "spelling dictionaries (dictionaries/)": package / "dictionaries",
        "licence texts (licences/)": package / "licences",
        "example adventure (examples/)": package / "examples",
    }
    for label, path in wanted.items():
        if not path.exists() or (path.is_dir() and not any(path.iterdir())):
            missing.append(label)
    fonts = [p for p in (package / "bundled").rglob("*") if p.suffix.lower() in (".ttf", ".otf")]
    if not fonts:
        missing.append("bundled fonts (.ttf or .otf in bundled/)")
    if not _find(root, "COPYING"):
        missing.append("COPYING (the GPL text)")
    if not _find(root, "QtWebEngineProcess*"):
        missing.append("Qt WebEngine's helper program (QtWebEngineProcess)")
    if not _find(root, "qtwebengine_resources.pak"):
        missing.append("Qt WebEngine resources (qtwebengine_resources.pak)")
    if not _find(root, "icudtl.dat"):
        missing.append("Qt WebEngine's ICU data (icudtl.dat)")
    if not _find(root, "*typst*"):
        missing.append("the Typst engine")
    return missing


def _send(stream, obj) -> None:
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">Q", len(data)) + data)
    stream.flush()


def _receive(stream):
    head = stream.read(8)
    if len(head) < 8:
        raise EOFError("the helper closed its output")
    size = struct.unpack(">Q", head)[0]
    return pickle.loads(stream.read(size))


def check_typst(program: Path) -> str:
    """Empty string on success, else the reason."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "no-packages").mkdir()
        (tmp / "main.typ").write_text("Smoke test: Scriptorum å ä ö\n", "utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen([str(program), "--scriptorum-build-helper"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        try:
            spec = {"input": str(tmp / "main.typ"), "root": str(tmp), "font_paths": [],
                    "no_packages": str(tmp / "no-packages")}
            _send(process.stdin, {"op": "compile-once", "spec": spec, "kwargs": {}, "cwd": str(tmp)})
            reply = _receive(process.stdout)
        except Exception as exc:  # noqa: BLE001
            process.kill()
            err = process.stderr.read().decode("utf-8", "replace")[-2000:]
            return f"the build helper did not answer ({exc}). {err}".strip()
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
        process.wait(timeout=30)
        if "error" in reply:
            return f"Typst reported: {reply['error'].get('message')}"
        data = reply.get("value")
        if not isinstance(data, (bytes, bytearray)) or not bytes(data).startswith(b"%PDF"):
            return "the build helper did not return a PDF"
    return ""


def check_start(program: Path) -> tuple:
    """(result, detail): result is 'pass', 'fail' or 'skip'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = dict(os.environ)
        env.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SCRIPTORUM_HOME": str(tmp / "home"),
            "SCRIPTORUM_DOCUMENTS": str(tmp / "documents"),
            "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu",
            "QTWEBENGINE_DISABLE_SANDBOX": "1",
        })
        log = tmp / "stderr.txt"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        with open(log, "wb") as err:
            process = subprocess.Popen([str(program)], env=env, stdout=subprocess.DEVNULL, stderr=err,
                                       stdin=subprocess.DEVNULL, creationflags=flags)
            end = time.monotonic() + START_SECONDS
            while time.monotonic() < end and process.poll() is None:
                time.sleep(0.5)
            alive = process.poll() is None
            if alive:
                process.kill()
                process.wait(timeout=15)
        text = log.read_text("utf-8", "replace")
        modules = tmp / "home" / "modules"
        installed = modules.is_dir() and any(modules.iterdir())
        if "platform plugin" in text and "offscreen" in text:
            return "skip", "this Qt has no screenless mode here; start the package by hand instead"
        if "Traceback" in text:
            tail = text[text.index("Traceback"):][:3000]
            return "fail", f"Python error at start:\n{tail}"
        if not alive:
            return "fail", f"the app ended by itself after start (exit code {process.returncode}).\n{text[-3000:]}"
        if not installed:
            return "fail", "the app kept running but did not install its bundled modules (no modules folder)"
        return "pass", ""


def main(argv: list) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    root, program = Path(argv[1]), Path(argv[2])
    failed = False

    missing = check_contents(root)
    if missing:
        failed = True
        print("[smoke] contents: FAIL, missing: " + "; ".join(missing))
    else:
        print("[smoke] contents: pass")

    reason = check_typst(program)
    if reason:
        failed = True
        print(f"[smoke] typst: FAIL, {reason}")
    else:
        print("[smoke] typst: pass (the build helper made a PDF)")

    if os.environ.get("SCRIPTORUM_SKIP_START_CHECK"):
        print("[smoke] start: skipped (SCRIPTORUM_SKIP_START_CHECK is set)")
    else:
        result, detail = check_start(program)
        if result == "fail":
            failed = True
        print(f"[smoke] start: {result.upper() if result == 'fail' else result}" + (f", {detail}" if detail else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
