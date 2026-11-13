# PyInstaller recipe for Scriptorum (design document F10). One recipe for all
# three platforms; build.py runs it with the settings below in the environment.
#
# The result is a folder (never a single file): Python, PySide6 with Qt
# WebEngine, Typst, spylls and the whole scriptorum package with its bundled
# modules, fonts, dictionaries, example adventure, licence texts and interface.
# Qt stays as separate shared libraries, so a user can replace them, as the
# LGPL asks (section 7).
# ruff: noqa  (this file is run by PyInstaller, which provides Analysis, EXE, ...)

import json
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

SRC = Path(os.environ["SCRIPTORUM_SRC"])          # a clean copy of the build folder
KIT = Path(os.environ["SCRIPTORUM_KIT"])          # this kit
VERSION = os.environ["SCRIPTORUM_VERSION"]
PLATFORM = os.environ["SCRIPTORUM_PLATFORM"]      # linux, macos or windows
CONFIG = json.loads((KIT / "kit.json").read_text("utf-8"))
ICONS = KIT / "icons"

sys.path.insert(0, str(SRC))

# --- what goes in ---------------------------------------------------------------------------
# Every non-Python file of the scriptorum package: ui/, bundled/ (modules, fonts),
# dictionaries/, examples/, licences/. Python files are compiled into the archive.
datas = collect_data_files("scriptorum", include_py_files=False, excludes=["**/__pycache__/**"])
datas += collect_data_files("spylls")
# The About window reads these versions with importlib.metadata (F9).
# From 0.6.7 the start-up step also compares these versions with the ones an
# update pack was made for (F22), so cryptography's metadata goes in too.
for dist in ("typst", "spylls", "PySide6", "shiboken6", "cryptography"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # an app version before 0.6.7 does not use cryptography
        pass
datas += [(str(SRC / "COPYING"), ".")]

# Parts of the app are imported only when used (the start-up checks, the build
# helper, dialogs), so the whole package is listed.
hiddenimports = collect_submodules("scriptorum") + collect_submodules("spylls")
try:  # F22: the signature check on update files and packs (0.6.7 and newer)
    import cryptography  # noqa: F401
    hiddenimports += collect_submodules("cryptography.hazmat.primitives")
except ImportError:
    pass
hiddenimports = [name for name in hiddenimports if ".tests" not in name]

binaries = []
if PLATFORM == "linux":
    # NSS (used by Qt WebEngine) loads these by name at run time, so PyInstaller
    # cannot see them. They sit beside libnss3, which is where NSS looks.
    for folder in ("/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu", "/usr/lib64", "/usr/lib",
                   "/usr/lib/x86_64-linux-gnu/nss", "/usr/lib/aarch64-linux-gnu/nss", "/usr/lib64/nss"):
        for name in ("libsoftokn3.so", "libfreebl3.so", "libfreeblpriv3.so", "libnssckbi.so"):
            candidate = Path(folder) / name
            if candidate.is_file() and not any(Path(b[0]).name == name for b in binaries):
                binaries.append((str(candidate), "."))

excludes = ["tkinter", "_tkinter", "pytest", "_pytest", "pypdf", "tests", "IPython", "matplotlib", "numpy"]

a = Analysis(
    [str(SRC / "scriptorum" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

# --- the program ------------------------------------------------------------------------------
version_info = None
if PLATFORM == "windows":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    numbers = tuple((list(int(p) for p in VERSION.split(".")[:3]) + [0, 0, 0, 0])[:4])
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("ProductName", "Scriptorum"),
                StringStruct("FileDescription", "Scriptorum"),
                StringStruct("FileVersion", VERSION),
                StringStruct("ProductVersion", VERSION),
                StringStruct("InternalName", "Scriptorum"),
                StringStruct("OriginalFilename", "Scriptorum.exe"),
                StringStruct("LegalCopyright", "Free software under the GNU GPL, version 3 or later"),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

icon = {"windows": ICONS / "scriptorum.ico", "macos": ICONS / "scriptorum.icns"}.get(PLATFORM)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scriptorum" if PLATFORM == "linux" else "Scriptorum",
    console=False,          # no terminal window; the build helper talks over pipes
    disable_windowed_traceback=False,
    argv_emulation=False,   # the app handles opened files itself (see the README)
    icon=str(icon) if icon else None,
    version=version_info,
    upx=False,
    codesign_identity=None,  # unsigned (D6); macOS gets an ad-hoc signature
    entitlements_file=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Scriptorum", upx=False)

# --- macOS: the .app with its file types -----------------------------------------------------
if PLATFORM == "macos":
    types = CONFIG["file_types"]
    app = BUNDLE(
        coll,
        name="Scriptorum.app",
        icon=str(ICONS / "scriptorum.icns"),
        bundle_identifier=CONFIG["bundle_id"],
        version=VERSION,
        info_plist={
            "CFBundleName": "Scriptorum",
            "CFBundleDisplayName": "Scriptorum",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": CONFIG["macos_minimum"],
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "NSHumanReadableCopyright": "Free software under the GNU GPL, version 3 or later",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": t["name"],
                    "CFBundleTypeRole": t["mac_role"],
                    "LSHandlerRank": "Owner",
                    "LSItemContentTypes": [t["uti"]],
                    "CFBundleTypeIconFile": f"{ext}.icns",
                }
                for ext, t in types.items()
            ],
            "UTExportedTypeDeclarations": [
                {
                    "UTTypeIdentifier": t["uti"],
                    "UTTypeDescription": t["name"],
                    "UTTypeConformsTo": ["public.data", "public.content"],
                    "UTTypeIconFile": f"{ext}.icns",
                    "UTTypeTagSpecification": {
                        "public.filename-extension": [ext],
                        "public.mime-type": [t["mime"]],
                    },
                }
                for ext, t in types.items()
            ],
        },
    )
