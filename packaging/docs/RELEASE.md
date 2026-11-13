# Release checklist

M6 is accepted one platform at a time (design document section 10): each installer is built and tested on its own platform and accepted when it is ready. Version 1 is released when all three are accepted.

## Before building

1. **The newest accepted build zip**, unpacked on each build computer. All three platforms build from the same zip; check that the folder name (and so the version) is the same everywhere.
2. **The update address (F21).** Paste the real address into `UPDATE_URL` in `scriptorum/core/updates.py` of that build, through a build of the app, not by editing one platform's copy. Until then every build prints a note, and `--release` stops. Test builds without `--release` are fine.
3. `python3.13 build.py --check` (Windows: `py -3.13 build.py --check`) on each build computer.

## Build and accept, one platform at a time

| Step | Linux | macOS | Windows |
|---|---|---|---|
| Build with `--release` (and `--tests` once per platform) | BUILD-LINUX.md | BUILD-MACOS.md | BUILD-WINDOWS.md |
| The build finishes and all three smoke-test lines pass (proposed as T-REL-04) | ☐ | ☐ | ☐ |
| T-REL-01: installs and runs on a clean computer without internet, exports the sample | ☐ | ☐ | ☐ |
| T-REL-02: no network connections | ☐ | ☐ | ☐ |
| T-REL-03: file types, icons; Linux first start | ☐ | ☐ | ☐ |
| Automated tests pass on that platform (from source or `--tests`) | ☐ | ☐ | ☐ |
| m1-basic sample PDF has the reference checksum (T-BUILD-03) | ☐ | ☐ | ☐ |

The macOS Intel .dmg (`…-macos-x86_64.dmg`) is tested the same way on an Intel Mac, if Intel Macs are to be supported.

## Publishing

Publish these together, on the same page, for every version:

- the installers: `…-linux-x86_64.AppImage`, `…-macos-arm64.dmg` (and `…-macos-x86_64.dmg`), `…-windows-x64-setup.exe`
- `Scriptorum-<version>-source.zip`
- the `SHA256SUMS-…txt` files
- the install notes (`INSTALL-Linux.txt`, `INSTALL-macOS.txt`, `INSTALL-Windows.txt`), or their text on the download page

**Why the source archive.** Scriptorum is under the GPL 3, and so it is passed on with its "Corresponding Source": the source code and the scripts used to build the installers. Offering the source archive from the same place as the installers meets that. Each build writes it (the build folder as packaged plus this kit under `packaging/`); the archives from the three platforms hold the same files, so one is enough. Qt and Qt WebEngine are under the LGPL 3: their libraries stay separate files inside every package, so a user can replace them, and their licence texts and notices are in Help › About (F9).

Parts of the packaging that end up inside the downloads, for the licence register (design document section 7): the PyInstaller bootloader (GPL 2.0 or later with an exception that allows any licence for the packaged program), the AppImage runtime (MIT, its licence is in `linux/runtime/`), and the Inno Setup installer and uninstaller (Inno Setup licence, free for any use). None of them limits Scriptorum's own licence.

**The update file (F21).** After publishing, update the file at the update address with the new version, its short note and the download page for each platform, in the format `scriptorum/core/updates.py` reads.

## Changing the kit

- **Pinned versions.** From kit 1.0.2 the kit takes every pinned version from the app's own `pyproject.toml` and installs exactly those; it stops if PySide6, typst, spylls (and, from 0.6.7, cryptography) are not pinned with `==`. Pins change only by decision (D4), in the app.
- **PyInstaller.** `kit.json` → `build_tools`. After a change, build all three platforms again before a release.
- **appimagetool.** `kit.json` → `appimagetool`: a new version needs its new address and SHA-256 checksum.
- **Icons.** Replace the drafts in `icons/source/` and run `common/make_icons.py` (see the README).
- **Names and file types.** `kit.json` → `bundle_id` and `file_types`. Changing a macOS type identifier or a Windows ProgID after a release leaves the old registration behind on users' computers, so settle them before version 1.
