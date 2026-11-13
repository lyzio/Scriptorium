# Scriptorum M6-0.6.8 — Test Report

| | |
|---|---|
| Version | 0.6.8 (Milestone 6, part D on GitHub: the packaging kit in the repository and the installers job) |
| Platform | Linux 6.18 (x86-64), headless (`QT_QPA_PLATFORM=offscreen`) |
| Python | 3.13.18 |
| Pinned versions | PySide6 6.8.3 (Qt 6.8 LTS) · typst 0.15.0 · spylls 0.1.7 · cryptography 48.0.1 |
| Date | 13 November 2026 |
| Result | **347 passed**, 0 failed, 0 skipped |

## This build

Built on M6-0.6.7 (accepted). The app is unchanged apart from its version; the build adds the packaging kit (kit 1.0.2) in `packaging/`, the installers job on GitHub and 5 new tests in `tests/test_m6d.py`. One test of 0.6.7 was corrected (below). The m1-basic checksum is unchanged.

## Results

| ID | Result | Notes |
|---|---|---|
| T-FILE, T-SRC, T-BUILD (but 03), T-MOD, T-UI, T-WORLD, T-FONT, T-LOOK (but 07) | Pass | As in 0.6.7 |
| T-BUILD-03 | Pending | Compare the checksum below on your machine |
| T-REL-02 | Pending | Network check on your machine |
| T-REL-04 … 07 | Pass | T-REL-06 corrected (below) |
| T-REL-08 | Pending on GitHub | Passes here; runs for real on your next tag |
| T-REL-09 | Pass | New, five tests. The workflow builds for a tag and from Run workflow on ubuntu-22.04, macos-15, macos-15-intel and windows-2022 with Python 3.13, with `--release` only for a tag, keeps every result as a download, attaches only for a tag or when asked, waits for the release, never a pre-release, and may only write where it attaches; it installs the kit's own list of Linux libraries. The kit reads all four pins from `pyproject.toml` and holds no copy of any; a build without cryptography pinned is refused from 0.6.7 on; the release check reads `UPDATE_URL`'s value; the recipe carries cryptography's code and metadata; the kit's `work/` and `dist/` stay out of the copied source |
| T-REL-10 | Pending | The first installers from GitHub, on real computers (below) |
| T-REL-01, T-REL-03 | Pending | Per platform, with the installers from GitHub |
| T-USE-01, T-USE-02 | Not run | Nothing the scenarios use changed in this build (the app is unchanged) |

## By hand here

- **A full Linux build with the kit from `packaging/`,** pointed at the repository folder itself, with `--release`: the pins read from `pyproject.toml` (cryptography 48.0.1 included), PyInstaller, the kit's smoke test (contents, a real Typst build through the build helper, a 25-second start), and `Scriptorum-0.6.8-linux-x86_64.AppImage` (236 MB) with its source archive and checksums. The frozen app holds `cryptography` and `cryptography-48.0.1.dist-info`, `spylls` and its metadata.
- **Updates in the installed app.** PyInstaller 6.22.3 registers its loader for bundled code in `sys.path_hooks`, not ahead of Python's own search, so the start-up step's version folder, put first on the path, is found before the bundled code (F22). A real run with a downloaded update needs a pack signed with the project's key, so it is part of T-REL-10.

## Problems found and fixed while building

- **The kit's `--release` refused every build from 0.6.7 on.** It looked for the placeholder text anywhere in `updates.py`, where it stays as a constant beside the real address. It now checks the value of `UPDATE_URL`. Without this fix every tagged build on GitHub would have stopped.
- **The kit would have left cryptography out of the installed app** (kit 1.0.1), so updates could never be checked there. It is now carried, with its metadata.

## Correction to an existing test

- **T-REL-06** (`tests/test_m6c5.py`): the made-up "newer" versions 0.6.8, 0.6.9 and 0.7.0 were only newer while the app was 0.6.7. They are now 9.0.8, 9.0.9 and 9.1.0. The test itself was wrong, not the app.

## Tests added

T-REL-09 (5 tests). T-REL-10 is manual. Both are in the Test Plan, added before the build.

## Hand checks for the project manager (T-REL-10)

1. Once this build is in main, run Installers for `v0.6.7` with "attach" ticked, and from then on every tag builds its installers by itself.
2. Install each installer on a real computer of its kind, without internet: it starts and exports m1-basic with the checksum below.
3. The Intel .dmg on a Mac with macOS 12 (D2).

## Sample checksum (Linux)

`m1-basic.pdf`: `8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69`

Unchanged since 0.6.4.
