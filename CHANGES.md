# Scriptorum M6-0.6.7 — Changes

Base: **M6-0.6.6** (`main`, accepted and merged on 13 November 2026). This is part C5 of Milestone 6 (decided 13 November 2026): installing updates (F22) with signed update packs, the start-up step that runs a newer version from the author's folder, going back to the previous version, and the release script; and the two issues found in the project manager's tests of 0.6.6.

- Download and install from Help ▸ Check for updates…, only when the author clicks it; the pack is checked and unpacked into the author's own folder for the next start
- every update file and pack signed with the project's Ed25519 key (cryptography 48.0.1); the app uses nothing that is not signed
- the start-up step: a newer verified version made for this Python, Qt and Typst runs from the author's folder; a version that fails to start is set aside and Scriptorum goes back by itself and says so; Help ▸ Go back to version X; only two versions kept
- the built-in update address is the GitHub release address; Settings ▸ Application ▸ Updates ▸ Update address, https only; a signed update file may move the address
- the release script, `tools/release.py`, and a hand-test tool, `tools/try_update.py`
- releases made on GitHub: a release job signs with the key kept as the repository secret `UPDATE` when an accepted build's tag is pushed (decided 13 November 2026)
- the project's public key is built in
- paragraphs and headings fill the editor's width (issue #8)
- a short block's ↑ ↓ + × menu is a 2 × 2 square and stays on top while the pointer is on it (issue #9)

Issues fixed: #8 (Fullscreen not fullscreening), #9 (Block menu problem).

Every file not listed here is unchanged from M6-0.6.6.

## Added

| File | Why |
|---|---|
| `scriptorum/boot.py` | The start-up step: chooses and runs a kept version or the installed one; a failed start goes back (F22.4, F22.5) |
| `scriptorum/core/packs.py` | Update packs: safe unpacking, the signed file list, the runtime check, and the versions kept in the author's folder with `state.json` (F22, 9.7) |
| `scriptorum/core/signing.py` | Ed25519 signatures on update files and packs (F22) |
| `scriptorum/core/update_key.py` | The project's public key, made by the project manager with `tools/release.py keygen` (F22) |
| `scriptorum/licences/parts/cryptography.txt` | cryptography's licence for About ▸ Under the hood (F9, section 7) |
| `tools/release.py` | The release script: the key once, then the pack and the signed update file from the tagged commit of main; on GitHub the key comes from the secret and the note from the tag; never a pre-release (F22, D12) |
| `.github/workflows/release.yml` | The release job on GitHub: signs with the repository secret `UPDATE` when a tag v<version> is pushed (F22) |
| `tools/try_update.py` | Try the start-up step and Go back by hand with a throwaway key |
| `tests/test_m6c5.py` | T-REL-04 to 08, T-UI-44 to 47 |
| `tests/update_keys.py` | The tests' own signing keys |

## Changed

| File | Why |
|---|---|
| `scriptorum/core/updates.py` | UPDATE_URL is the GitHub release address; the update file must be signed; Download and install; the Update address in use; a moved address (F21, F22) |
| `scriptorum/core/appsettings.py` | `update_address`, https only (F22) |
| `scriptorum/core/about.py` | cryptography in Under the hood (F9) |
| `scriptorum/app/bridge.py` | `installUpdate`, `setUpdateAddress`, `useMovedAddress`, `versionInfo`, `goBack`; a version reports that it started when its window is ready (F22) |
| `scriptorum/app/main.py` | Reuses the application object when a failed version handed over to the installed one (F22.5) |
| `scriptorum/__main__.py` | Runs the start-up step first; the build helper runs from the same version folder (F22) |
| `scriptorum/bundled/scriptorum.en/strings/update.json`, `menu.json`, `settings.json`, `about.json` | The words of this build (F15) |
| `scriptorum/ui/index.html`, `styles.css` | Download and install and the address in the update dialog; the Update address field; a wider update dialog; the 2 × 2 block menu (#9); no 100-character limit on paragraphs (#8) |
| `ui-src/app.ts` | Download and install, the moved address, Help ▸ Go back to version, the start notice |
| `ui-src/shell.ts` | The Update address field in Settings ▸ Application |
| `ui-src/editor.ts` | The block menu stays on top while the pointer is on it (#9) |
| `scriptorum/ui/dist/app.js` | Rebuilt |
| `pyproject.toml` | Version 0.6.7; cryptography 48.0.1; the `scriptorum` command runs the start-up step |
| `tests/conftest.py` | The tests trust their own key; no test starts a kept version |
| `tests/test_m6c.py` | T-UI-32 signs its update files and asks the placeholder explicitly (the design changed: F22) |
| `tests/test_m6c3.py` | T-UI-40 no longer expects paragraphs to stop at 100 characters (issue #8; T-UI-46 checks them) |
| `tests/test_m6b.py` | T-UI-34 expects cryptography in Under the hood |
| `tests/scenarios/run_use_scenarios.py` | The C5 steps: the Update address, Check for updates, Download and install, the full-width paragraph; the C1 step sets the placeholder itself, since the built-in address is now real |
| `.gitignore` | `dist-release/` |
| `README.md`, `TEST-REPORT.md`, `CHANGES.md` | This build |
| `scriptorum/__init__.py`, `ui-src/package.json` | Version 0.6.7 |

## Deleted

None.
