#!/usr/bin/env python3
"""Build the Scriptorum installer for the computer this runs on (design document F10).

    python3.13 build.py <unpacked Scriptorum build folder>

Linux gives an AppImage, macOS a .dmg, Windows a setup program. All three come
from the same source and the same steps:

  1. check      the build folder is complete and its pinned versions match this kit
  2. copy       a clean copy of the build folder (caches and test output left out)
  3. tools      a private Python environment with the pinned packages and PyInstaller
  4. freeze     PyInstaller turns the app into a folder that needs nothing installed
  5. smoke      the frozen app is checked: contents, a Typst build, a start without a screen
  6. package    the folder is wrapped into the platform's installer
  7. finish     checksums, install notes and the source archive are written to dist/

Options:
  --check        only list what this computer still needs, build nothing
  --tests        also run the app's automated tests (python -m pytest) before freezing
  --release      stop if the update address is still the placeholder (F21)
  --no-start     skip the start check in step 5 (for a build machine where it cannot run)
  --iscc PATH    where Inno Setup's ISCC.exe is (Windows, if not found by itself)
  --out PATH     where the results go (default: dist/ in this kit)

Everything this script makes stays in this kit's work/ and dist/ folders; the
build folder you point it at is never changed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
CONFIG = json.loads((KIT / "kit.json").read_text("utf-8"))
UPDATE_PLACEHOLDER = "Paste update url here"

# The pinned versions come from the app's own pyproject.toml (kit 1.0.2,
# decided 13 November 2026), so the kit always builds with exactly the versions
# that app version pins (D4). These must be pinned there; cryptography too from
# the first version that checks signed updates (F22, scriptorum/core/signing.py).
REQUIRED_PINS = ("PySide6", "typst", "spylls")
PINS: dict = {}


# --- small helpers -------------------------------------------------------------------------------
def say(message: str) -> None:
    print(f"[build] {message}", flush=True)


def stop(message: str) -> None:
    print(f"\n[build] STOPPED: {message}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list, **kwargs) -> None:
    say("$ " + " ".join(str(c) for c in cmd))
    result = subprocess.run([str(c) for c in cmd], **kwargs)
    if result.returncode != 0:
        stop(f"this step failed (exit code {result.returncode}): {Path(str(cmd[0])).name}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def platform_id() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    stop(f"this kit builds on Linux, macOS and Windows, not on {sys.platform}")
    return ""


def arch_id(plat: str) -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return {"linux": "x86_64", "macos": "x86_64", "windows": "x64"}[plat]
    if machine in ("arm64", "aarch64"):
        return {"linux": "aarch64", "macos": "arm64", "windows": "arm64"}[plat]
    return machine


# --- 0. what the computer needs --------------------------------------------------------------
LINUX_LIBRARIES = {
    # Libraries Qt needs on the build computer. Most are carried inside the
    # AppImage. library file: (Debian/Ubuntu package, Fedora package)
    "libxcb-cursor.so.0": ("libxcb-cursor0", "xcb-util-cursor"),
    "libxkbcommon-x11.so.0": ("libxkbcommon-x11-0", "libxkbcommon-x11"),
    "libxcb-icccm.so.4": ("libxcb-icccm4", "xcb-util-wm"),
    "libxcb-image.so.0": ("libxcb-image0", "xcb-util-image"),
    "libxcb-keysyms.so.1": ("libxcb-keysyms1", "xcb-util-keysyms"),
    "libxcb-render-util.so.0": ("libxcb-render-util0", "xcb-util-renderutil"),
    "libxcb-shape.so.0": ("libxcb-shape0", "libxcb"),
    "libxcb-xkb.so.1": ("libxcb-xkb1", "libxcb"),
    "libnss3.so": ("libnss3", "nss"),
    "libnspr4.so": ("libnspr4", "nspr"),
    "libxkbfile.so.1": ("libxkbfile1", "libxkbfile"),
    "libXcomposite.so.1": ("libxcomposite1", "libXcomposite"),
    "libXdamage.so.1": ("libxdamage1", "libXdamage"),
    "libXrandr.so.2": ("libxrandr2", "libXrandr"),
    "libXtst.so.6": ("libxtst6", "libXtst"),
    "libxshmfence.so.1": ("libxshmfence1", "libxshmfence"),
    "libXi.so.6": ("libxi6", "libXi"),
    "libXfixes.so.3": ("libxfixes3", "libXfixes"),
    # Present on every desktop; the AppImage uses the user's own copies (see
    # LINUX_USE_SYSTEM), but the build's start check needs them here too.
    "libGL.so.1": ("libgl1", "libglvnd-glx"),
    "libEGL.so.1": ("libegl1", "libglvnd-egl"),
    "libgbm.so.1": ("libgbm1", "mesa-libgbm"),
    "libasound.so.2": ("libasound2", "alsa-lib"),
    "libfontconfig.so.1": ("libfontconfig1", "fontconfig"),
    "libdbus-1.so.3": ("libdbus-1-3", "dbus-libs"),
}


def linux_missing_libraries() -> list:
    # ldconfig sits in /sbin, which is not on an ordinary user's PATH on Debian.
    found: set = set()
    for tool in (shutil.which("ldconfig"), "/sbin/ldconfig", "/usr/sbin/ldconfig"):
        if tool and Path(tool).is_file():
            try:
                listing = subprocess.run([tool, "-p"], capture_output=True, text=True).stdout
            except OSError:
                continue
            found = set(re.findall(r"^\s*(\S+)\s", listing, re.M))
            if found:
                break
    # Also look in the usual library folders, in case ldconfig gave nothing.
    for folder in ("/lib", "/lib64", "/usr/lib", "/usr/lib64", "/usr/lib/x86_64-linux-gnu",
                   "/usr/lib/aarch64-linux-gnu", "/lib/x86_64-linux-gnu", "/lib/aarch64-linux-gnu"):
        try:
            found |= {p.name for p in Path(folder).iterdir()}
        except OSError:
            pass
    return [lib for lib in LINUX_LIBRARIES if lib not in found]


def find_iscc(given: str | None) -> Path | None:
    candidates = []
    if given:
        candidates.append(Path(given))
    on_path = shutil.which("iscc") or shutil.which("ISCC")
    if on_path:
        candidates.append(Path(on_path))
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidates.append(Path(base) / "Inno Setup 6" / "ISCC.exe")
    return next((c for c in candidates if c.is_file()), None)


def check_computer(plat: str, args) -> list:
    """Everything this computer lacks for a build, in plain words."""
    problems = []
    wanted = CONFIG["python"]
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    if have != wanted:
        problems.append(f"Python {wanted} is needed to run this script (this is Python {have}); see docs/BUILD-{plat.upper()}.md")
    try:
        import venv  # noqa: F401
        import ensurepip  # noqa: F401
    except ImportError:
        problems.append("Python's venv module is missing (Ubuntu/Debian: sudo apt install python3.13-venv)")
    free = shutil.disk_usage(KIT).free / 1e9
    if free < 4:
        problems.append(f"at least 4 GB of free disk space is needed here ({free:.1f} GB free)")
    if plat == "linux":
        missing = linux_missing_libraries()
        if missing:
            deb = sorted({LINUX_LIBRARIES[m][0] for m in missing})
            rpm = sorted({LINUX_LIBRARIES[m][1] for m in missing})
            problems.append("system libraries that the AppImage must carry are missing: " + ", ".join(missing)
                            + "\n      Ubuntu/Debian: sudo apt install " + " ".join(deb)
                            + "\n      Fedora:        sudo dnf install " + " ".join(rpm))
        if arch_id(plat) not in CONFIG["appimagetool"]:
            problems.append(f"no AppImage tool is listed for {platform.machine()}")
    if plat == "macos":
        for tool in ("codesign", "hdiutil", "ditto"):
            if not shutil.which(tool):
                problems.append(f"the macOS tool {tool} was not found")
        release = tuple(int(x) for x in (platform.mac_ver()[0] or "0").split(".")[:2])
        if release and release < (12, 0):
            problems.append("macOS 12 or newer is needed to build (Qt 6.8)")
    if plat == "windows":
        if arch_id(plat) != "x64":
            problems.append("the Windows build needs an x64 Python (PySide6 6.8.3 has no Windows Arm wheels)")
        if find_iscc(getattr(args, "iscc", None)) is None:
            problems.append("Inno Setup 6 was not found (winget install JRSoftware.InnoSetup, or --iscc PATH)")
    return problems


# --- 1. the build folder ---------------------------------------------------------------------
def read_version(src: Path) -> str:
    init = (src / "scriptorum" / "__init__.py").read_text("utf-8")
    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", init)
    if not match:
        stop("scriptorum/__init__.py has no __version__")
    return match.group(1)


def update_address_is_placeholder(text: str) -> bool:
    """F21: whether UPDATE_URL is still the placeholder. From 0.6.7 the file
    also names the placeholder as a constant, so only the value counts."""
    match = re.search(r'^UPDATE_URL\s*=\s*(.+)$', text, re.M)
    if not match:
        return UPDATE_PLACEHOLDER in text
    value = match.group(1).strip()
    return value == "PLACEHOLDER" or value.strip("\"'") == UPDATE_PLACEHOLDER


def read_pins(src: Path) -> dict:
    """The app's pinned dependencies (name==version) from its pyproject.toml."""
    pyproject = (src / "pyproject.toml").read_text("utf-8")
    block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", pyproject, re.M | re.S)
    pins = dict(re.findall(r'"([A-Za-z0-9_.\-]+)==([^"]+)"', block.group(1) if block else ""))
    needed = list(REQUIRED_PINS)
    if (src / "scriptorum" / "core" / "signing.py").is_file():
        needed.append("cryptography")
    missing = [name for name in needed if name not in pins]
    if missing:
        stop("pyproject.toml does not pin " + ", ".join(missing) + " with ==; the kit builds only pinned versions (D4)")
    return pins


def check_source(src: Path, release: bool) -> str:
    if not (src / "scriptorum" / "__init__.py").is_file():
        stop(f"{src} is not a Scriptorum build folder (no scriptorum/__init__.py). "
             "Point to the unpacked build, for example ~/Downloads/M6-0.6.5")
    needed = {
        "scriptorum/__main__.py": "the entry point",
        "scriptorum/ui/index.html": "the interface page",
        "scriptorum/ui/dist/app.js": "the built interface script (npm run build in ui-src)",
        "scriptorum/bundled/scriptorum.core/module.json": "the core element kit",
        "scriptorum/dictionaries": "the spelling dictionaries",
        "scriptorum/licences": "the licence texts (About window)",
        "scriptorum/examples": "the example adventure",
        "COPYING": "the GPL text",
        "pyproject.toml": "the project file",
    }
    for rel, what in needed.items():
        if not (src / rel).exists():
            stop(f"{rel} is missing from the build folder ({what})")
    if "--scriptorum-build-helper" not in (src / "scriptorum" / "__main__.py").read_text("utf-8"):
        stop("this build has no build-helper entry (F7.1, M6 part B); package M6-0.6.2 or newer")
    fonts = [p for p in (src / "scriptorum" / "bundled").rglob("*") if p.suffix.lower() in (".ttf", ".otf")]
    if not fonts:
        stop("the bundled modules hold no font files; unzip the complete build zip, not the project files")

    version = read_version(src)
    pyproject = (src / "pyproject.toml").read_text("utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    if not match or match.group(1) != version:
        stop(f"the version in pyproject.toml ({match.group(1) if match else 'none'}) is not __version__ ({version})")
    PINS.clear()
    PINS.update(read_pins(src))
    say("    pinned in pyproject.toml: " + ", ".join(f"{n} {v}" for n, v in PINS.items()))

    updates = src / "scriptorum" / "core" / "updates.py"
    if updates.is_file() and update_address_is_placeholder(updates.read_text("utf-8")):
        message = ("the update address is still the placeholder \"Paste update url here\" "
                   "(F21: paste the real address into UPDATE_URL in scriptorum/core/updates.py before a release)")
        if release:
            stop(message)
        say("NOTE: " + message + ". Fine for a test build.")
    return version


# --- 2. a clean copy ---------------------------------------------------------------------------
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git", ".mypy_cache", ".ruff_cache",
             ".venv", "venv", ".idea", ".vscode"}
SKIP_ROOT_SUFFIXES = {".scav", ".pdf", ".log", ".zip", ".png"}


def clean_copy(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    own = {(KIT / "work").resolve(), (KIT / "dist").resolve()}

    def ignore(folder: str, names: list) -> set:
        skipped = {n for n in names if n in SKIP_DIRS or n.endswith((".pyc", ".pyo")) or n == ".DS_Store"}
        # The kit lives in the repository (packaging/) from 1.0.2: never copy
        # its own work and results into the build's source.
        skipped |= {n for n in names if (Path(folder) / n).resolve() in own}
        if Path(folder).resolve() == src.resolve():
            # test output left in the build folder's top level (m1-basic.scav, net.log, ...)
            skipped |= {n for n in names if Path(n).suffix.lower() in SKIP_ROOT_SUFFIXES and (Path(folder) / n).is_file()}
        return skipped

    shutil.copytree(src, dest, ignore=ignore)


# --- 3. the tools ------------------------------------------------------------------------------
def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def make_tools(work: Path, with_tests: bool) -> Path:
    venv = work / "venv"
    wanted = [f"{n}=={v}" for n, v in PINS.items()]
    wanted += [f"{n}=={v}" for n, v in CONFIG["build_tools"].items()]
    if with_tests:
        wanted += ["pytest>=8", "pypdf>=5"]
    marker = venv / "scriptorum-kit.txt"
    if marker.is_file() and marker.read_text("utf-8").split() == wanted and venv_python(venv).is_file():
        say("tools: the private Python environment is ready (reused)")
        return venv_python(venv)
    if venv.exists():
        shutil.rmtree(venv)
    say("tools: making a private Python environment (the first time downloads about 600 MB)")
    run([sys.executable, "-m", "venv", venv])
    py = venv_python(venv)
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary", *wanted])
    marker.write_text("\n".join(wanted), "utf-8")
    return py


# --- 4. freeze ---------------------------------------------------------------------------------
def freeze(py: Path, copy: Path, work: Path, version: str, plat: str) -> Path:
    dist, build = work / "pyinstaller-dist", work / "pyinstaller-work"
    for folder in (dist, build):
        if folder.exists():
            shutil.rmtree(folder)
    env = dict(os.environ, SCRIPTORUM_SRC=str(copy), SCRIPTORUM_KIT=str(KIT),
               SCRIPTORUM_VERSION=version, SCRIPTORUM_PLATFORM=plat)
    env.pop("PYTHONPATH", None)
    run([py, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
         "--distpath", dist, "--workpath", build, KIT / "common" / "scriptorum.spec"], env=env)
    return dist


# Libraries every Linux desktop has, and which must match the computer's own
# graphics driver, sound system, fonts setup or desktop session. Carrying a copy
# from the build machine breaks them on other distributions, so the AppImage
# uses the computer's own (as the AppImage project's exclude list advises).
LINUX_USE_SYSTEM = (
    "libGL.so", "libGLX", "libGLdispatch", "libEGL", "libOpenGL", "libgbm", "libdrm",
    "libasound", "libpulse", "libfontconfig", "libfreetype", "libharfbuzz",
    "libX11.so", "libX11-xcb", "libxcb.so", "libdbus-1",
    "libstdc++", "libgcc_s", "libglib-2.0", "libgobject-2.0", "libgio-2.0", "libgmodule-2.0", "libgthread-2.0",
    "libwayland-client", "libwayland-cursor", "libwayland-egl", "libwayland-server",
)


def prune_linux(dist: Path) -> None:
    internal = dist / "Scriptorum" / "_internal"
    # Qt Quick (QML) plugins come along with Qt WebEngine's packaging, but the
    # app's window is Qt Widgets with a web view and never loads QML.
    qml = internal / "PySide6" / "Qt" / "qml"
    if qml.is_dir():
        shutil.rmtree(qml)
        say("    left out the Qt Quick (QML) plugins, which the app does not use")
    removed = []
    for path in internal.iterdir():
        if path.is_file() and path.name.startswith(LINUX_USE_SYSTEM):
            path.unlink()
            removed.append(path.name)
    say(f"    left to the computer's own copies: {', '.join(sorted(removed)) or 'none'}")


def program_in(dist: Path, plat: str) -> tuple:
    """(folder to check, the program to start)"""
    if plat == "macos":
        app = dist / "Scriptorum.app"
        return app, app / "Contents" / "MacOS" / "Scriptorum"
    folder = dist / "Scriptorum"
    return folder, folder / ("Scriptorum.exe" if plat == "windows" else "scriptorum")


# --- 6. package --------------------------------------------------------------------------------
def fetch_appimagetool(arch: str) -> Path:
    info = CONFIG["appimagetool"][arch]
    tools = KIT / "work" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    tool = tools / f"appimagetool-{CONFIG['appimagetool']['version']}-{arch}.AppImage"
    if not tool.is_file() or sha256(tool) != info["sha256"]:
        say(f"package: downloading appimagetool {CONFIG['appimagetool']['version']}")
        partial = tool.with_suffix(".part")
        urllib.request.urlretrieve(info["url"], partial)
        if sha256(partial) != info["sha256"]:
            partial.unlink()
            stop("the downloaded appimagetool does not match its checksum in kit.json; nothing was used")
        partial.replace(tool)
    tool.chmod(0o755)
    return tool


def package_linux(dist: Path, out: Path, version: str, arch: str) -> Path:
    work = dist.parent
    appdir = work / "Scriptorum.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    lib = appdir / "usr" / "lib" / "scriptorum"
    shutil.copytree(dist / "Scriptorum", lib, symlinks=True)
    linux = KIT / "linux"
    shutil.copy2(linux / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    share = appdir / "usr" / "share"
    (share / "applications").mkdir(parents=True)
    desktop = (linux / "scriptorum.desktop").read_text("utf-8").replace("@VERSION@", version)
    (appdir / "scriptorum.desktop").write_text(desktop, "utf-8")
    (share / "applications" / "scriptorum.desktop").write_text(desktop, "utf-8")
    (share / "mime" / "packages").mkdir(parents=True)
    shutil.copy2(linux / "scriptorum-mime.xml", share / "mime" / "packages" / "scriptorum.xml")
    icons = KIT / "icons" / "png"
    mime_icon = {"scav": CONFIG["file_types"]["scav"]["mime"], "scmod": CONFIG["file_types"]["scmod"]["mime"]}
    for png in icons.glob("*.png"):
        name, size = png.stem.rsplit("-", 1)
        if name == "scriptorum":
            target = share / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "scriptorum.png"
        else:
            target = share / "icons" / "hicolor" / f"{size}x{size}" / "mimetypes" / (mime_icon[name].replace("/", "-") + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png, target)
    shutil.copy2(KIT / "icons" / "scriptorum.png", appdir / "scriptorum.png")
    os.symlink("scriptorum.png", appdir / ".DirIcon")

    tool = fetch_appimagetool(arch)
    runtime = linux / "runtime" / f"runtime-{arch}"
    target = out / f"Scriptorum-{version}-linux-{arch}.AppImage"
    if target.exists():
        target.unlink()
    env = dict(os.environ, ARCH=arch, APPIMAGE_EXTRACT_AND_RUN="1", VERSION=version)
    run([tool, "--no-appstream", "--runtime-file", runtime, appdir, target], env=env)
    target.chmod(0o755)
    return target


# Mach-O magic numbers: 32- and 64-bit, either byte order, and universal ("fat") files.
MACHO_MAGIC = {bytes.fromhex(h) for h in ("feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca")}


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or path.suffix == ".class":
        return False
    try:
        with open(path, "rb") as f:
            return f.read(4) in MACHO_MAGIC
    except OSError:
        return False


def macos_signing_order(app: Path) -> list:
    """F10 (M6-0.6.9): what to sign, from the inside out. First every program
    and library file, deepest first; then every nested bundle, deepest first
    (a framework by its real version folders, since macOS refuses Qt's
    web-engine framework when it is signed as a whole); the app itself last.
    Signing the app in one pass with --deep stopped both macOS builds of
    v0.6.8 ("embedded framework contains modified or invalid version")."""
    def depth(p: Path) -> int:
        return len(p.relative_to(app).parts)

    contents = app / "Contents"
    files = sorted((p for p in contents.rglob("*") if is_macho(p)), key=lambda p: (-depth(p), str(p)))
    bundles = []
    for p in contents.rglob("*"):
        if p.is_symlink() or not p.is_dir():
            continue
        if p.suffix == ".app":
            bundles.append(p)
        elif p.suffix == ".framework":
            versions = p / "Versions"
            real = sorted(v for v in versions.iterdir() if v.is_dir() and not v.is_symlink()) if versions.is_dir() else []
            bundles.extend(real or [p])
    bundles.sort(key=lambda p: (-depth(p), str(p)))
    return files + bundles + [app]


def sign_macos_app(app: Path) -> None:
    """F10: an ad-hoc signature on every part, from the inside out, never
    with --deep; then the whole app is checked as macOS checks it."""
    order = macos_signing_order(app)
    say(f"signing {len(order)} parts of the app from the inside out")
    for part in order:
        run(["codesign", "--force", "--sign", "-", part], stdout=subprocess.DEVNULL)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])


def package_macos(dist: Path, out: Path, version: str, arch: str) -> Path:
    app = dist / "Scriptorum.app"
    resources = app / "Contents" / "Resources"
    for ext in CONFIG["file_types"]:
        shutil.copy2(KIT / "icons" / f"{ext}.icns", resources / f"{ext}.icns")
    # Unsigned (D6), but every Mac with Apple silicon needs at least an ad-hoc
    # signature to run a program; it is free and needs no Apple account.
    sign_macos_app(app)
    stage = dist.parent / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    run(["ditto", app, stage / "Scriptorum.app"])
    os.symlink("/Applications", stage / "Applications")
    shutil.copy2(KIT / "user-docs" / "INSTALL-macOS.txt", stage / "Read me first.txt")
    target = out / f"Scriptorum-{version}-macos-{arch}.dmg"
    if target.exists():
        target.unlink()
    run(["hdiutil", "create", "-volname", f"Scriptorum {version}", "-srcfolder", stage,
         "-fs", "HFS+", "-format", "UDZO", "-ov", target])
    return target


def package_windows(dist: Path, out: Path, version: str, args) -> Path:
    iscc = find_iscc(args.iscc)
    if iscc is None:
        stop("Inno Setup 6 was not found (winget install JRSoftware.InnoSetup, or give --iscc PATH)")
    base = f"Scriptorum-{version}-windows-x64-setup"
    target = out / f"{base}.exe"
    if target.exists():
        target.unlink()
    types = CONFIG["file_types"]
    run([iscc, "/Qp",
         f"/DAppVersion={version}",
         f"/DSourceDir={dist / 'Scriptorum'}",
         f"/DIconsDir={KIT / 'icons'}",
         f"/DOutputDir={out}",
         f"/DOutputBase={base}",
         f"/DInstallNotes={KIT / 'user-docs' / 'INSTALL-Windows.txt'}",
         f"/DScavProgId={types['scav']['progid']}",
         f"/DScmodProgId={types['scmod']['progid']}",
         f"/DMinVersion={CONFIG['windows_minimum']}",
         KIT / "windows" / "scriptorum.iss"])
    return target


# --- 7. finish ---------------------------------------------------------------------------------
def source_archive(copy: Path, out: Path, version: str) -> Path:
    """The source the installers were built from, with this kit, for the GPL (section 7)."""
    target = out / f"Scriptorum-{version}-source.zip"
    stamp = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        def add(root: Path, prefix: str, skip_top: set) -> None:
            for path in sorted(root.rglob("*")):
                rel = path.relative_to(root)
                if rel.parts and rel.parts[0] in skip_top:
                    continue
                if any(part in SKIP_DIRS for part in rel.parts) or not path.is_file():
                    continue
                info = zipfile.ZipInfo(f"{prefix}/{rel.as_posix()}", stamp)
                info.external_attr = (0o755 if os.access(path, os.X_OK) else 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())
        top = f"Scriptorum-{version}"
        add(copy, top, set())
        add(KIT, f"{top}/packaging", {"work", "dist"})
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Scriptorum installer for this computer (F10).")
    parser.add_argument("source", nargs="?", help="the unpacked Scriptorum build folder, e.g. ~/Downloads/M6-0.6.5")
    parser.add_argument("--check", action="store_true", help="only list what this computer still needs")
    parser.add_argument("--tests", action="store_true", help="run the app's automated tests before freezing")
    parser.add_argument("--release", action="store_true", help="stop if the update address is the placeholder")
    parser.add_argument("--no-start", action="store_true", help="skip the start check of the smoke test")
    parser.add_argument("--iscc", help="path to Inno Setup's ISCC.exe (Windows)")
    parser.add_argument("--out", help="where the results go (default: dist/ in this kit)")
    args = parser.parse_args()

    plat = platform_id()
    arch = arch_id(plat)
    say(f"Scriptorum packaging kit {CONFIG['kit_version']} on {plat} {arch}, Python {platform.python_version()}")
    if plat == "linux":
        glibc = platform.libc_ver()[1] or "?"
        say(f"glibc {glibc}: the AppImage will run on Linux with glibc {glibc} or newer"
            + (" (Ubuntu 22.04 has 2.35; build there to reach older systems, see docs/BUILD-LINUX.md)"
               if glibc != "?" and tuple(map(int, glibc.split("."))) > (2, 35) else ""))

    problems = check_computer(plat, args)
    if args.check:
        if problems:
            print("\nThis computer still needs:")
            for p in problems:
                print("  - " + p)
            return 1
        print("\nThis computer has everything the build needs.")
        return 0
    if problems:
        stop("this computer is not ready:\n  - " + "\n  - ".join(problems))
    if not args.source:
        parser.error("give the unpacked Scriptorum build folder, for example ~/Downloads/M6-0.6.5")

    src = Path(os.path.expanduser(args.source)).resolve()
    say(f"1/7 check: {src}")
    version = check_source(src, args.release)
    say(f"    Scriptorum {version}")

    work = KIT / "work" / f"{plat}-{arch}"
    work.mkdir(parents=True, exist_ok=True)
    out = Path(os.path.expanduser(args.out)).resolve() if args.out else KIT / "dist"
    out.mkdir(parents=True, exist_ok=True)

    copy = work / "source"
    say("2/7 copy: a clean copy of the build folder")
    clean_copy(src, copy)

    say("3/7 tools")
    py = make_tools(work, args.tests)
    if args.tests:
        say("    running the automated tests (python -m pytest)")
        run([py, "-m", "pytest", "-q"], cwd=copy)
        clean_copy(src, copy)  # package exactly the build folder, not the test output

    say("4/7 freeze: PyInstaller (a few minutes)")
    dist = freeze(py, copy, work, version, plat)
    if plat == "linux":
        prune_linux(dist)
    folder, program = program_in(dist, plat)
    if not program.is_file():
        stop(f"PyInstaller made no program at {program}")

    say("5/7 smoke test")
    env = dict(os.environ)
    if args.no_start:
        env["SCRIPTORUM_SKIP_START_CHECK"] = "1"
    run([sys.executable, KIT / "common" / "smoke_test.py", folder, program], env=env)

    say("6/7 package")
    if plat == "linux":
        target = package_linux(dist, out, version, arch)
        notes = "INSTALL-Linux.txt"
    elif plat == "macos":
        target = package_macos(dist, out, version, arch)
        notes = "INSTALL-macOS.txt"
    else:
        target = package_windows(dist, out, version, args)
        notes = "INSTALL-Windows.txt"

    say("7/7 finish")
    shutil.copy2(KIT / "user-docs" / notes, out / notes)
    source_zip = source_archive(copy, out, version)
    sums = out / f"SHA256SUMS-{plat}-{arch}.txt"
    sums.write_text("".join(f"{sha256(p)}  {p.name}\n" for p in (target, source_zip)), "utf-8")
    size = target.stat().st_size / 1e6
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    say(f"done {stamp}: {target} ({size:.0f} MB)")
    say(f"     {source_zip.name}, {sums.name} and {notes} are beside it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
