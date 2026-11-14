# Scriptorum M6-0.6.9 — Changes

Base: **M6-0.6.8** (`main`, accepted and merged on 13 November 2026). A fix build before macOS and Windows are accepted (design document section 10, "M6 fix build 0.6.9", decided 14 November 2026):

- **Change game system (F14):** File ▸ Settings… ▸ Adventure lists every installed game system; a list says what does not fit before the preview; Apply changes only the manifest's game system, theme and module lines, in one undo step; what does not fit is kept, warned about on its line, and left out of the build's own copy only (creature fields the stat block lacks; dice outside the notation print as plain text)
- **every empty required field is listed at once** (issue #12, F4.10): Scriptorum's own check, since Typst stops at the first; every error line is marked in Source mode
- **a clue's text from its Information item** (issue #7, F3): while the clue has no description, text typed into the item becomes the description when the author leaves the box
- **Raise all** in the warnings panel (issue #6, F4)
- **installers:** the macOS app signed part by part from the inside out (kit 1.0.3), since `codesign --deep` refused Qt's web-engine framework and stopped both macOS builds of v0.6.8; the attach job runs when one platform failed
- **issue #11:** the map editor test T-WORLD-28 waits for the pin settings instead of a fixed time

Issues fixed: #6, #7, #11, #12. Issue #1 stays open for a later build (the project manager's adventure uses Plain, which has no Creature codex type by design).

Every file not listed here is unchanged from M6-0.6.8.

## Added

| File | Why |
|---|---|
| `tests/test_m6e.py` | T-MOD-26, T-BUILD-32, T-UI-48, T-WORLD-34, T-REL-12 |

## Changed

| File | Why |
|---|---|
| `scriptorum/core/session.py` | Change game system: fit list, preview, apply in one undo step, fit warnings on every build (F14); `required_fields` lists every empty required field (#12); world undo restores the game system, theme and module lines |
| `scriptorum/core/source.py` | `fit_to_game_system` and `dice_fits`: the build's own copy of text written for another game system (F14) |
| `scriptorum/core/build.py` | The build runs the fit step on its copy of each chapter |
| `scriptorum/app/bridge.py` | `gameSystemFit`, `previewGameSystem` |
| `scriptorum/ui/index.html` | The game system list on the settings page |
| `ui-src/app.ts` | Change game system on the settings page; Raise all (#6); a clue's text adopted (#7); every error line marked (#12); undo after a game system change reloads the elements |
| `ui-src/editor.ts` | `setLevels` (Raise all in one undo step); a clue item's text saved on leaving the box; several error lines in Source mode |
| `scriptorum/ui/dist/app.js` | Built from `ui-src/` |
| `scriptorum/bundled/scriptorum.en/strings/*.json` | Texts for Change game system, the fit warnings, Raise all and the adopted clue text |
| `packaging/build.py`, `packaging/kit.json` | Kit 1.0.3: a stray `Versions/Resources` in Qt's web-engine framework is moved into `Versions/A`; macOS signed from the inside out, never with --deep |
| `packaging/README.md`, `packaging/docs/BUILD-MACOS.md` | Kit 1.0.3 and the signing |
| `.github/workflows/installers.yml` | The attach job runs unless the run is cancelled, and says so when nothing built |
| `tests/test_m5.py` | T-MOD-13: a die outside Vaesen's notation now prints as text with a warning (corrected, F14) |
| `tests/test_m6d.py` | T-REL-09: the new attach condition and kit 1.0.3 (corrected) |
| `tests/test_m6c3.py` | T-WORLD-28 waits for the pin settings (#11) |
| `tests/test_m6c5.py` | T-UI-46: the 100-character check goes by the editor column's real width (failed on the project manager's Mac) |
| `tests/scenarios/run_use_scenarios.py` | The Change game system steps |
| `CHANGELOG.md` | The 0.6.9 section |
| `CHANGES.md`, `TEST-REPORT.md` | This build |
| `scriptorum/__init__.py`, `pyproject.toml`, `ui-src/package.json` | Version 0.6.9 |

## Deleted

None.
