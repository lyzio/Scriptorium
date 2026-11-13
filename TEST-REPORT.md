# Scriptorum M6-0.6.7 — Test Report

| | |
|---|---|
| Version | 0.6.7 (Milestone 6: Modules and release, part C5: install updates, F22; issues #8 and #9) |
| Platform | Linux 6.18 (x86-64), headless (`QT_QPA_PLATFORM=offscreen`) |
| Python | 3.13.18 |
| Pinned versions | PySide6 6.8.3 (Qt 6.8 LTS) · typst 0.15.0 · spylls 0.1.7 · cryptography 48.0.1 (new) |
| Date | 13 November 2026 |
| Result | **341 passed**, 0 failed, 0 skipped |

## This build

Part C5 of M6, built on M6-0.6.6 (accepted and merged into `main` while this build was made; the two trees are identical). The 328 tests of 0.6.6 passed before any change. 13 tests are new, in `tests/test_m6c5.py`. Three existing tests were corrected, because the design changed what they check (below, and in the Test Plan's change log). The m1-basic checksum is unchanged.

The full suite ran twice at the end. The first run had one failure, T-WORLD-28 (the map editor's pin number field did not appear within 5 seconds); the test passed on its own, in its module, and in the second full run (341 passed). I take it as a one-off timing failure under load; the build does not touch the map editor. If you see it on your machine, tell me and I will open an issue.

## Results

| ID | Result | Notes |
|---|---|---|
| T-FILE-01 … 15, T-SRC-01 … 20 | Pass | |
| T-BUILD-01, 02, 04 … 31 | Pass | |
| T-BUILD-03 | Pending | Compare the checksum below on your machine |
| T-MOD-01 … 25 | Pass | T-MOD-20 retired |
| T-UI-01 … 43 | Pass | T-UI-06 by eye (Pending). T-UI-32, T-UI-34 and T-UI-40 corrected (below) |
| T-UI-44 | Pass | New. http, text and ftp are refused with "Only a secure https address can be used…" and nothing is stored; an https address is stored, used even while the placeholder is built in, and named in the window "(entered in Settings)"; Use built-in address clears it and the GitHub address is used "(built in)"; a file signed with another key is ignored |
| T-UI-45 | Pass | New. "The update address has moved to https://updates.example.org/…. Use the new address?"; Keep the old one changes nothing; Use the new address stores it and the next check asks only there; an unsigned file and one signed with another key are ignored with no question |
| T-UI-46 | Pass | New (issue #8). A long paragraph and a heading are as wide as their scene and block in a 1000 px window, a 2400 px window, with the preview hidden and in full screen; in the wide window the paragraph is wider than 100 characters. Fails on 0.6.6 |
| T-UI-47 | Pass | New (issue #9). With the real mouse (Qt's test mouse, so hover works as for a person): on a one-line paragraph and on a one-line block inside a scene, the four buttons form a 2 × 2 square about 46 px tall beside the 25 px block; moving over each button keeps only that block's menu shown and the button under the pointer belongs to it; ↓ moves the hovered block, not the next one; moving away lets go. Fails on 0.6.6 |
| T-WORLD-01 … 33, T-FONT-01 … 03, T-LOOK-01 … 06, 08 … 12 | Pass | |
| T-LOOK-07 | Pending | By eye: nothing printed changed in this build |
| T-REL-01, T-REL-03 | Pending | Part D, per platform (Linux accepted on 13 November) |
| T-REL-02 | Pending | Network check on your machine. Here: the app ran 25 s under `strace` with no AF_INET or AF_INET6 connection |
| T-REL-04 | Pass | New, three tests. Update file: unsigned, signed with another key, changed after signing, cut short, and a copy without a key are each refused. Packs: wrong signature, a file changed after signing, a file not in the signed list, `../`, an absolute path, a link, a `.exe`, another Python/Qt, and a cut-short zip are each refused with their reason, and the author's folder is byte-identical afterwards. Download: wrong size or checksum, wrong signature, unreachable and wrong version change nothing |
| T-REL-05 | Pass | New. Download and install is shown beside the download page; nothing is downloaded until it is clicked; then the only requests are the update file and the pack; "Ready. The update is installed the next time Scriptorum starts."; the open adventure's unsaved text is untouched; the installed app's files are unchanged; a damaged download is refused; a version for another Qt says "This version needs a new installer" and offers only the download page |
| T-REL-06 | Pass | New, four tests, each start in its own process as the installed app does. A newer verified version runs from its folder; damaged, missing, made for another Python and Qt, not newer, or signed with another key: the installed version runs. A version that raises an error goes back at once to the previous one; one that crashes goes back at the next start; both leave the notice and a log in the crash-log folder and are not run again. Go back to version X; only two versions kept; modules, settings and recent files byte-identical. In the window: Go back is offered only while a kept version runs, and the notice is shown once |
| T-REL-07 | Pass | New. Run on a copy of this repository as its own git repository: keygen writes the key outside the repository (mode 600) and the public key into the app, and refuses to replace it; the release is refused when untagged, with changed files, for another version, with the key inside the repository, and when a test release would be published; the real one writes the pack and the signed update file, which the app accepts, installs and runs at the next start from the author's folder; two runs give the same pack byte for byte |
| T-USE-01, T-USE-02 | Pass | Both goals reached; all 115 scenario checks passed. New C5 steps: the Update address (http refused, https stored), Check for updates without a key and with one, Download and install with the adventure open, a long paragraph at full width |

## By hand here (not automated)

- **Hand-test tool.** `tools/try_update.py prepare` then `start`: the window ran from the 9.9.9 folder (its code was loaded there, none from the installed copy) and reported that it started. With `prepare --broken`, the installed version ran, 9.9.9 was marked as failed, the notice was shown, and `update-start-….log` was written.
- **Entry point.** `python -m scriptorum m1-basic.scav` started and kept running for 15 s.
- **Screens.** The update dialog with Download and install and the address used; the unsigned-file message; Settings ▸ Application ▸ Updates with the address field; the editor with the 2 × 2 menus and a full-width paragraph. The update dialog was widened (600 px) so its buttons do not wrap.

## Problems found and fixed while building

- The `scriptorum` command made by `pip install` started the window directly, so it would have skipped the start-up step. It now runs the start-up step first, as `python -m scriptorum` does.
- A version that failed to start could not write its log, because the failed version's code had already replaced the app's in memory. The log folder is now found before any version is loaded.
- A failed version handing over to the installed one in the same go needs the application object it already made; `main` now reuses it.
- The repository was renamed to lyzio/Scriptorum while I built; the update address, the release script and the docs use the new name, and the release script reads the repository from the update address, the only place the code names it.

## Corrections to existing tests

- **T-UI-32** (`tests/test_m6c.py`): from F22 the app uses nothing in an update file that is not signed with the project's key, so the tests sign their files with a test key; the built-in address is now the GitHub address, so the placeholder case asks the placeholder explicitly.
- **T-UI-40** (`tests/test_m6c3.py`): no longer expects paragraphs to stop at about 100 characters (issue #8); T-UI-46 checks the paragraphs.
- **T-UI-34** (`tests/test_m6b.py`): expects cryptography in About ▸ Under the hood (section 7).
- The scenario script's C1 step expected the placeholder message from the built-in address; it now sets the placeholder for that step, so the run never reaches the internet.

## T-USE findings

| Kind | Finding | Milestone |
|---|---|---|
| friction | Until you run `python tools/release.py keygen` and commit `scriptorum/core/update_key.py`, Check for updates… can only say that this copy holds no update key | by hand, before the first release (no issue: a step for you) |
| friction | Labels typed in pasted text stay after converting | later, with import (issue #2, already open) |
| friction | Adding a map always goes through a file dialog | later (issue #3, already open) |
| friction | A new clue's text typed into its Information item is not saved as the clue's description | later (issue #7, already open) |

## Tests added

T-REL-04 (3 tests), T-REL-05 (1), T-REL-06 (4), T-REL-07 (1), T-UI-44 (1), T-UI-45 (1), T-UI-46 (1), T-UI-47 (1): 13 in all. The Test Plan got these IDs before the build.

## Hand checks for the project manager

1. **Issue #8.** Open the example adventure in full screen with the preview hidden: paragraphs run the full width, like the frames.
2. **Issue #9.** Hover a one-line paragraph and move down onto ↓, + and ×: the menu stays, and each button acts on that paragraph.
3. **The start-up step and Go back**, with `tools/try_update.py` (commands in the README and the final message): About shows 9.9.9, Help ▸ Go back to version 0.6.7, restart, About shows 0.6.7 and says it went back; then `prepare --broken` and `start`: it says 9.9.9 did not start.
4. **Settings ▸ Application ▸ Updates.** Type an http address: refused. Type an https one, Help ▸ Check for updates…: the window names it. Use built-in address.
5. **Before the first release:** `python tools/release.py keygen`, keep the key safe, and commit `scriptorum/core/update_key.py`.

## Sample checksum (Linux)

`m1-basic.pdf`: `8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69`

Unchanged from 0.6.4 to 0.6.6: nothing printed changed.
