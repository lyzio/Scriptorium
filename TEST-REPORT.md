# Scriptorum M6-0.6.9 — Test Report

| | |
|---|---|
| Version | 0.6.9 (Milestone 6, fix build: Change game system, issues #6, #7, #11, #12, and the macOS installers) |
| Platform | Linux 6.18 (x86-64), headless (`QT_QPA_PLATFORM=offscreen`) |
| Python | 3.13.18 |
| Pinned versions | PySide6 6.8.3 (Qt 6.8 LTS) · typst 0.15.0 · spylls 0.1.7 · cryptography 48.0.1 |
| Date | 14 November 2026 |
| Result | **359 passed**, 0 failed, 0 skipped |

## This build

Built on M6-0.6.8 (accepted). Before any change, the 0.6.8 suite ran here and passed up to the one test that checks the installers workflow word for word (T-REL-09), which this build changes on purpose (below). The build adds 10 tests in `tests/test_m6e.py`; three tests of earlier builds were corrected (below). The m1-basic checksum is unchanged.

## Results

| ID | Result | Notes |
|---|---|---|
| T-FILE, T-SRC, T-BUILD (but 03), T-MOD, T-UI, T-WORLD, T-FONT, T-LOOK (but 07) | Pass | As in 0.6.8, with the corrections below |
| T-BUILD-32 | Pass | New (issue #12). Three empty required fields (a scene title, a person's name, a handout title) are all reported after one build, each on its line, in the warnings panel; with one filled in, the other two are still listed. Every error line is marked in Source mode |
| T-MOD-26 | Pass | New, four tests. m5-plain from Plain to Vaesen: the list before the preview names the d20, 2d10+1 and d100 and the creature's free stat lines, each with its line; Cancel changes nothing; Apply changes only the game system, theme and module lines, and every other file is byte-identical; it builds and exports with the four warnings; one undo brings Plain back; changing back gives the same manifest and no warnings. m4-look from Vaesen to Plain: the Vaesen theme is not offered, so the Plain theme is used; the Creature entry is kept with a warning. A read-only adventure says so |
| T-UI-48 | Pass | New (issue #6). Three headings that skip a level: Raise all raises all three in one undo step; with one such heading there is no Raise all |
| T-WORLD-34 | Pass | New (issue #7). Text typed into a new clue's item becomes the clue's description when leaving the box; a second item of the clue shows it; undo takes it back; a clue with a description is never overwritten |
| T-WORLD-28 | Pass | Issue #11: run three more times together with the C2 tests, 36 passed each time |
| T-REL-12 | Pass (GitHub: built; Mac start Pending) | New, three tests. A first test run on GitHub of this branch found the real cause: Qt's web-engine framework has a stray `Versions/Resources` beside `Versions/A`, which macOS cannot sign; the kit now moves it into `Versions/A`, keeping every link inside it. A second test run (Actions run 43568919050, Run workflow on `build/0.6.9`, nothing attached) built all four installers; both .dmg files report "valid on disk" and "satisfies its Designated Requirement" (438 parts signed). The kit's smoke test runs before this step, so the moved folder is checked by starting the app on a real Mac (hand check 5) The macOS signing order is from the inside out (libraries and helper programs, then bundles, a framework by its version folder, the app last) and never uses --deep; the attach job runs unless the run is cancelled. Whether both .dmg files now build is seen on GitHub (below) |
| T-REL-04 … 09, T-REL-11 | Pass | T-REL-09 corrected (below) |
| T-BUILD-03 | Pending | Compare the checksum below on your machine |
| T-REL-02 | Pending | Network check on your machine |
| T-REL-01, T-REL-03, T-REL-10 | Pending | Per platform, with the installers from GitHub |
| T-USE-01, T-USE-02 | Pass | 78 and 270 actions; every check passed. New steps: Change game system from Vaesen to Plain (the list, the preview bar, Apply, the text unchanged, it builds, one undo), and the clue text from its item (issue #7, now a check instead of a finding) |

## T-USE findings

| Finding | Kind | Milestone |
|---|---|---|
| Labels typed in pasted text stay after converting it | friction | later, with import (L3); issue #2 |
| A new map always goes through a file dialog | friction | later; issue #3 |

The clue finding of 0.6.6 is fixed (issue #7). No new issues were opened.

## Corrections to existing tests

- **T-MOD-13** (`tests/test_m5.py`): its last check expected a Vaesen adventure with a 2d10+1 to fail to build. From 0.6.9 a die outside the game system's notation prints as plain text with a warning on its line (F14, Change game system), so the check now expects that warning. The design changed, not the app's correctness.
- **T-REL-09** (`tests/test_m6d.py`): it checked the attach job's old condition word for word, and kit 1.0.2. The attach job now runs unless the run is cancelled (T-REL-12), and the kit is 1.0.3.
- **T-UI-46** (`tests/test_m6c5.py`), found in your Mac run of 0.6.9: it decided whether the window was wide from the 2400 px it asked for, which macOS reports even when the screen gives the editor column only about 970 px, so it expected text wider than the column. The paragraph did fill the column (the check before it passed). The 100-character check now goes by the column's real width. Not a fault in the app.
- **T-WORLD-28** (`tests/test_m6c3.py`, issue #11): it waited a fixed 0.2 s for the new pin's settings; it now waits until they are shown.

## Tests added

T-MOD-26 (4 tests), T-BUILD-32, T-UI-48, T-WORLD-34, T-REL-12 (3). All are in the Test Plan, added before the build.

## Hand checks for the project manager

1. **Change game system** on your Plain adventure *Oroligt i Widtsköfle*: File ▸ Settings… ▸ Adventure, pick Vaesen. Read the list, try it in the preview, Apply, and look at the Codex panel: Creature is now a type you can use. Undo once and Plain is back.
2. **Issue #12:** empty a scene title and a person's name, and check that both errors show at once.
3. **Issue #7:** Insert ▸ Clue ▸ New clue…, type into the item, click elsewhere, then insert the same clue again.
4. **Issue #6:** in an adventure with several headings that skip a level, open the warnings and press Raise all.
5. **The installers on a Mac:** the test run's downloads (Actions ▸ Installers ▸ run 43568919050 ▸ Artifacts) hold both .dmg files of this build. Install one on your Mac and check that it starts, that the live preview shows pages, and that a .scav opens by double-click: Qt's web engine reads its files from the folder the kit moved. Then T-REL-10, including the Intel .dmg on macOS 12. Once merged and tagged, the Installers run attaches all four to the release.

## Sample checksum (Linux)

`m1-basic.pdf`: `8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69`

Unchanged since 0.6.4.
