# Scriptorum M6-0.6.8 — Changes

Base: **M6-0.6.7** (`main`, accepted and merged on 13 November 2026). This build moves the packaging kit into the repository and builds the installers on GitHub (M6 part D, decided 13 November 2026). The app itself is unchanged apart from its version.

- the packaging kit in `packaging/`, as kit 1.0.2
- the installers job: every tag `v<version>` builds the AppImage (Ubuntu 22.04), both .dmg files (macos-15, macos-15-intel) and the Windows setup program, and attaches them to the release; Run workflow builds test installers from any branch or tag
- the kit takes the pinned versions from the app's `pyproject.toml`, and carries cryptography into the installed app (F22)
- the kit's `--release` check reads the value of `UPDATE_URL`; before, it refused every build from 0.6.7 on
- the code-scanning findings fixed: three regular expressions of Cytoscape.js made safe while bundling, and a false alarm in the release script
- `CHANGELOG.md` holds what each version brings and describes each release; the README is a plain README; developer notes in `docs/DEVELOPING.md`
- the Windows installer is marked as not yet tested

Issues fixed: none (no open issue was planned for this build).

Every file not listed here is unchanged from M6-0.6.7.

## Added

| File | Why |
|---|---|
| `packaging/` | The packaging kit 1.0.1 as received from the project manager, changed as below (kit 1.0.2) |
| `.github/workflows/installers.yml` | The installers job on GitHub (F10, M6 part D) |
| `tests/test_m6d.py` | T-REL-09, T-REL-11 |
| `CHANGELOG.md` | What each version brings; each release's description |
| `docs/DEVELOPING.md` | Running the tests, trying things by hand, the interface build, the layout and developer notes, moved from the README |
| `ui-src/build.mjs` | The interface build, with the safe Cytoscape patterns |

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
| `ui-src/package.json` | `npm run build` runs `build.mjs` |
| `scriptorum/ui/dist/app.js` | Rebuilt: only the two Cytoscape lines differ |
| `tools/release.py` | The release description from CHANGELOG.md; two variables renamed for code scanning |
| `tests/test_m6c5.py` | T-UI-46 for narrower screens; T-REL-06's test versions |
| `README.md` | A plain README: what Scriptorum is, downloads, running from source, reporting problems, what it is built with, licence |
| `TEST-REPORT.md`, `CHANGES.md` | This build |
| `scriptorum/__init__.py`, `pyproject.toml` | Version 0.6.8 |

## Deleted

None.
