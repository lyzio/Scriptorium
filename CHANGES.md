# Scriptorum M6-0.6.8 — Changes

Base: **M6-0.6.7** (`main`, accepted and merged on 13 November 2026). This build moves the packaging kit into the repository and builds the installers on GitHub (M6 part D, decided 13 November 2026). The app itself is unchanged apart from its version.

- the packaging kit in `packaging/`, as kit 1.0.2
- the installers job: every tag `v<version>` builds the AppImage (Ubuntu 22.04), both .dmg files (macos-15, macos-15-intel) and the Windows setup program, and attaches them to the release; Run workflow builds test installers from any branch or tag
- the kit takes the pinned versions from the app's `pyproject.toml`, and carries cryptography into the installed app (F22)
- the kit's `--release` check reads the value of `UPDATE_URL`; before, it refused every build from 0.6.7 on

Issues fixed: none (no open issue was planned for this build).

Every file not listed here is unchanged from M6-0.6.7.

## Added

| File | Why |
|---|---|
| `packaging/` | The packaging kit 1.0.1 as received from the project manager, changed as below (kit 1.0.2) |
| `.github/workflows/installers.yml` | The installers job on GitHub (F10, M6 part D) |
| `tests/test_m6d.py` | T-REL-09 |

## Changed (inside `packaging/`, from kit 1.0.1)

| File | Why |
|---|---|
| `packaging/build.py` | The pins come from the app's `pyproject.toml` (cryptography needed from 0.6.7); the release check reads `UPDATE_URL`'s value; the kit's own `work/` and `dist/` are never copied into the build's source |
| `packaging/common/scriptorum.spec` | cryptography's code and package metadata go into the app (F22) |
| `packaging/kit.json` | Kit 1.0.2; no pins of its own |
| `packaging/README.md`, `packaging/docs/*.md` | The kit in the repository, on GitHub, and the pins from the app |

## Changed

| File | Why |
|---|---|
| `.gitignore` | `packaging/work/`, `packaging/dist/` |
| `README.md`, `TEST-REPORT.md`, `CHANGES.md` | This build |
| `scriptorum/__init__.py`, `pyproject.toml`, `ui-src/package.json` | Version 0.6.8 |

## Deleted

None.
