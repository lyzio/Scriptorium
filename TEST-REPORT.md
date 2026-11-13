# Scriptorum M6-0.6.5 — Test Report

| | |
|---|---|
| Version | 0.6.5 (Milestone 6: Modules and release, part C3: fixes and additions after the C2 tests) |
| Platform | Linux 6.18 (x86-64), headless (`QT_QPA_PLATFORM=offscreen`) |
| Python | 3.13.18 |
| Pinned versions | PySide6 6.8.3 (Qt 6.8 LTS) · typst 0.15.0 · spylls 0.1.7 |
| Date | 13 November 2026 |
| Result | **317 passed**, 0 failed, 0 skipped (on the project manager's machine the Node-based escaping test is skipped: 316 passed, 1 skipped) |

## This build

Part C3 of M6. The 299 tests of M6-0.6.4 passed before any change. 18 tests are new, in `tests/test_m6c3.py`. Two existing tests were corrected, because the design changed what they check (below, and in the Test Plan's change log). The m1-basic checksum is unchanged.

## Results

| ID | Result | Notes |
|---|---|---|
| T-FILE-01 … 15, T-SRC-01 … 18 | Pass | |
| T-SRC-19 | Pass | New, three tests. With the cursor in a Box, a check, a person card's Information and a Box's title field, Insert ▸ Sub-heading 1 lands in the scene just after that block, one undo step each. Outside a scene it lands where the cursor is. End of scene moves the blocks after the cursor out of the scene in one undo step, writes no marker, and undo brings them back; with the cursor on the last block it opens an empty paragraph after the scene; outside a scene it says why and changes nothing. The Structure group and the Insert menu list it. Text that never used it writes back byte-identical |
| T-BUILD-01, 02, 04 … 30 | Pass | |
| T-BUILD-03 | Pending | Compare the checksum below on the Mac |
| T-BUILD-31 | Pass | New, six tests. In all four themes: sub-headings before the first scene, after an act heading and between scenes are tagged H2 and H3 and nest under their act in the bookmarks; those in scenes stay H3; the table of contents lists only acts and scenes; the author's text is unchanged. The build's copy changes only those lines and keeps every line where it was. A skipped level outside a scene is found and offered the right level |
| T-MOD-01 … 25 | Pass | T-MOD-20 retired |
| T-UI-01 … 39 | Pass | T-UI-06 by eye (Pending); T-UI-17 corrected |
| T-UI-40 | Pass | New. At 1440 and 2400 pixels wide, and with the preview hidden: the editor column fills its pane, the scene frame spans it, paragraphs stop at 100 characters, field rows use the width, and nothing sticks out sideways |
| T-UI-41 | Pass | New, two tests. Back from a codex entry and from the relationship chart: same scroll position, same block, same caret. Switching to another adventure tab and back: the same |
| T-WORLD-01 … 26, T-FONT-01 … 03, T-LOOK-01 … 06, 08 … 12 | Pass | |
| T-WORLD-27 | Pass | New, two tests (plus the window test below). Pins print their numbers; an older pin without a number gets the next free one; a typed number is kept; the key prints name — note; the handouts PDF lists only handout-layer pins; saving without edits leaves the map file unchanged; the key sits beside an upright map and under a wide one |
| T-WORLD-28 | Pass | New, two tests. A pin line stores its two pins and follows a moved pin; a free line keeps its points; dashed and labels print; the handouts PDF has only the line on the handout layer; one undo step per change; a free line with one point is refused. In the window: a placed pin gets the next number and shows it, the number can be changed, the Line tool joins two pins and draws a free line ended by a double-click |
| T-WORLD-29 | Pass | New, two tests. Ticked, the adventure PDF prints "Give out Handout 1 · title" instead of the text; the handouts PDF is byte-identical to before; the accessible PDF builds; unticked again, the adventure PDF is byte-identical to before; the field is never written while unticked. The editor keeps the full text and shows the tag |
| T-LOOK-07 | Pending | By eye: the map key, numbered pins, lines and the give-out line |
| T-REL-01, T-REL-03 | Not run | M6 part D |
| T-REL-02 | Pending | Network check on your machine. Here: the app ran 25 s under `strace` with no AF_INET or AF_INET6 connection |
| T-USE-01, T-USE-02 | Pass | Both goals reached; all 99 scenario checks passed. New C3 steps: End of scene, a sub-heading after the scene, a handout ticked Only as handout, and the export |

## What I found

- **Inserting a sub-heading from inside a Box already worked** in 0.6.4 when the cursor was inside a scene. It was refused only outside any scene, as on your info page; that is what this build opens up.
- **End of scene needs no marker.** A scene's text already ends at its closing bracket, so End of scene moves the blocks out instead of writing `#scene-end()`. Same result for you, and the text format does not change. The design document is corrected.
- **A horizontal scroll bar in the editor.** The fold buttons sat 4 pixels past the editor's right margin. The margin is now wide enough, and T-UI-40 checks for it.
- **A delayed restore could undo the author's own scroll.** Going back to the place in the text runs once more after the editor has laid itself out; it now skips that if you have already scrolled or moved on.

## Tests corrected

- T-UI-36: Alt+↑ at the top of a scene now steps a sub-heading out of the scene, since sub-headings may stand outside scenes (F4, C3). Before, it stayed put.
- T-UI-17: the Structure group also lists End of scene.

## T-USE findings

| Kind | Finding | Milestone |
|---|---|---|
| friction | After converting pasted lines, the labels typed in the original text stay | later (import, L3) |
| friction | Adding a map always goes through a file dialog | later |
| friction | A footnote is edited by deleting its chip and inserting a new one, or in Source mode | later |
| friction | A list is still a locked block: its items are edited in Source mode | later |
| friction | Raising headings from the warnings panel is one at a time | later |

## Tests added

T-SRC-19 (3 tests), T-BUILD-31 (6), T-UI-40 (1), T-UI-41 (2), T-WORLD-27 (2), T-WORLD-28 (2), T-WORLD-29 (2): 18 in all. The Test Plan got these IDs before the build.

## Hand checks for the project manager

1. **Your own adventure.** Open the adventure in your screenshot. Put the cursor in the Box in scene 3 and choose Structure ▸ Sub-heading 1: it lands after the Box. Click into the paragraph on your info page before the first scene and do the same.
2. **End of scene.** Put the cursor in a block in the middle of a scene and choose Structure ▸ End of scene: the rest of the scene moves out, below the "End of scene" line.
3. **Full screen.** Press F11: the editor fills the width; long paragraphs stop at a comfortable width.
4. **Back from the Codex.** Scroll down, click into a paragraph, open a codex entry, press Back: you are where you were.
5. **Maps.** Open a map, place pins (they get numbers), give one a note, use Line to join two pins, then a free line with a double-click at the end; set one dashed and give it a label. Look at the printed map and its key.
6. **Only as handout.** Tick it on a handout; the adventure PDF shows the give-out line, the handouts PDF the full sheet.

## Sample checksum (Linux)

`m1-basic.pdf`: `8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69`

Unchanged from 0.6.4. Two exports on this machine are byte-identical.
