# Scriptorum packaging kit

This kit turns a finished Scriptorum build (for example `M6-0.6.5.zip`, unpacked) into the three downloads of design document F10:

| Platform | Result | Built on |
|---|---|---|
| Linux | `Scriptorum-<version>-linux-x86_64.AppImage` | Linux (Ubuntu 22.04 recommended) |
| macOS | `Scriptorum-<version>-macos-arm64.dmg` (and `-x86_64.dmg` for Intel Macs) | a Mac with macOS 12 or newer |
| Windows | `Scriptorum-<version>-windows-x64-setup.exe` | Windows 10 or 11, 64-bit |

Each download holds everything F10 lists: the Python runtime, PySide6 with Qt WebEngine, Typst, the bundled fonts, the spelling dictionaries, all bundled modules (Vaesen game system and theme included), the example adventure and the licence texts. It runs without installing anything else and without internet. Builds are unsigned (D6); the install notes explain the first-launch warning.

From kit 1.0.2 the kit lives in the app's repository, in `packaging/` (decided 13 November 2026), so a tag builds the app and its installers from the same commit, and the scripts that build each installer are part of its source, as the GPL asks. It is also copied into the source archive that every build writes (see docs/RELEASE.md).

**On GitHub.** Pushing a tag `v<version>` on main builds every installer on GitHub's machines (`.github/workflows/installers.yml`): the AppImage on Ubuntu 22.04, the .dmg for Apple Silicon (macos-15) and for Intel Macs (macos-15-intel), and the Windows setup program, and attaches them to the release. Actions ▸ Installers ▸ Run workflow builds test installers from any branch or tag, as downloads of the run; tick "attach" to add them to an existing tag's release.

## Quick start

Each platform is built on that platform. The first build downloads about 600 MB (Python packages) and takes 5 to 15 minutes; later builds reuse them.

1. Check the computer. It lists anything missing, with the command that installs it:
   - Linux and macOS: `python3.13 build.py --check`
   - Windows: `py -3.13 build.py --check`
2. Build, pointing at the unpacked build folder (or at the repository folder itself; the kit's own `work/` and `dist/` are left out):
   - Linux: `./linux/build-linux.sh ~/Downloads/M6-0.6.5`
   - macOS: `./macos/build-macos.sh ~/Downloads/M6-0.6.5`
   - Windows: `powershell -ExecutionPolicy Bypass -File windows\build-windows.ps1 $env:USERPROFILE\Downloads\M6-0.6.5` (in PowerShell)
3. The results are in `dist/`: the installer, `Scriptorum-<version>-source.zip`, a `SHA256SUMS-…txt` and the user's install notes.

What each computer needs, step by step: [docs/BUILD-LINUX.md](docs/BUILD-LINUX.md), [docs/BUILD-MACOS.md](docs/BUILD-MACOS.md), [docs/BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md). Before publishing: [docs/RELEASE.md](docs/RELEASE.md).

## What a build does

`build.py` does the same seven steps on every platform and stops with a plain message at the first problem:

1. **check** that the build folder is complete (interface, modules, fonts, dictionaries, example, licences), and read its pinned versions (PySide6, typst, spylls and cryptography) from its own `pyproject.toml`
2. **copy** the build folder, leaving out caches and test output; the original is never changed
3. **tools**: a private Python environment in `work/` with the pinned packages and PyInstaller 6.22.3
4. **freeze**: PyInstaller turns the app into one folder that needs nothing installed (a folder, not a single file, so Qt stays replaceable as the LGPL asks)
5. **smoke test** of the frozen app: its contents, a real Typst build through its own build helper (F7.1), and a 25-second start without a screen
6. **package**: AppImage (appimagetool), .dmg (hdiutil) or setup program (Inno Setup), with the file types and icons
7. **finish**: checksums, install notes and the source archive in `dist/`

Options: `--tests` runs the app's automated tests first; `--release` refuses a build whose update address is still the placeholder (F21); `--no-start` skips the start check; `--out PATH` puts the results elsewhere.

## File types and icons

`.scav` adventures and `.scmod` modules get their own icons (drafts from the UX canvas, D16) and are registered: a document-type declaration in the Mac app, registry entries in the Windows setup, and a desktop entry plus MIME types inside the AppImage. When the final logo is chosen, replace the SVG drafts in `icons/source/` and run `python common/make_icons.py --font <Cormorant Garamond Bold>` with the build environment's Python; the finished icons are kept in the kit.

## What the app itself still needs for F10

The kit registers the file types, but three things only the app can do. They are app code, not packaging, and are not in any build yet:

1. **macOS: opening a file that is double-clicked.** macOS hands the file to the app as an "open document" event, not on the command line. The app must handle Qt's `QFileOpenEvent` (also when it is already running). Until then, a double-clicked `.scav` starts Scriptorum without opening it.
2. **`.scmod` from a double-click** (all platforms). The app receives the path like an adventure's and must offer to install it (F14.2) instead of opening it as an adventure.
3. **Linux: the first-start offer** (F10, T-REL-03). The AppImage cannot register file types by itself. On first start the app should offer to copy the desktop entry, MIME types and icons into `~/.local/share` with `Exec=` pointing at the AppImage. Everything it needs is inside the AppImage: `AppRun` exports `SCRIPTORUM_APPDIR`, and the files are under `$SCRIPTORUM_APPDIR/usr/share/` (`applications/`, `mime/packages/`, `icons/hicolor/`); the AppImage's own path is in `APPIMAGE`.

## Layout

```
build.py                 the build, all platforms
kit.json                 names, file types, tool versions and checksums (the app's pins come from its pyproject.toml)
common/scriptorum.spec   the PyInstaller recipe
common/smoke_test.py     checks the frozen app
common/make_icons.py     makes .png/.ico/.icns from icons/source/*.svg
icons/                   the finished icons and their SVG sources
linux/                   AppRun, desktop entry, MIME types, AppImage runtimes, build-linux.sh
macos/build-macos.sh
windows/                 build-windows.ps1, scriptorum.iss (Inno Setup)
user-docs/               the install notes that go beside each download
docs/                    how to build on each platform, and the release checklist
work/, dist/             made by builds (safe to delete)
```

Kit version 1.0.2, 13 November 2026, for M6 part D. 1.0.2: the kit lives in the repository and builds on GitHub; the pinned versions come from the app's pyproject.toml; cryptography (F22) is carried into the app. 1.0.1: the library check works when ldconfig is not on the PATH (Debian).
