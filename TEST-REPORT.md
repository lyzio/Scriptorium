# Scriptorum M6-0.6.6 — Test Report

| | |
|---|---|
| Version | 0.6.6 (Milestone 6: Modules and release, part C4: the codex points of F3, the Clue field, How to play) |
| Platform | Linux 6.18 (x86-64), headless (`QT_QPA_PLATFORM=offscreen`) |
| Python | 3.13.18 |
| Pinned versions | PySide6 6.8.3 (Qt 6.8 LTS) · typst 0.15.0 · spylls 0.1.7 |
| Date | 13 November 2026 |
| Result | **328 passed**, 0 failed, 0 skipped (on the project manager's machine the Node-based escaping test is skipped: 327 passed, 1 skipped) |

## This build

Part C4 of M6. The 317 tests of M6-0.6.5 passed before any change. 11 tests are new, in `tests/test_m6c4.py`, with the new sample `m6-clues`. One existing test was corrected, because the design changed what it checks (below, and in the Test Plan's change log). The m1-basic checksum is unchanged.

## Results

| ID | Result | Notes |
|---|---|---|
| T-FILE-01 … 15, T-SRC-01 … 19 | Pass | |
| T-SRC-20 | Pass | New. A clue Information with an empty body, a person card with How to play and a card keeping two fields parse and write back byte-identical; after an edit they are written again with their values; four older samples are unchanged |
| T-BUILD-01, 02, 04 … 31 | Pass | |
| T-BUILD-03 | Pending | Compare the checksum below on the Mac |
| T-MOD-01 … 25 | Pass | T-MOD-20 retired |
| T-UI-01 … 41 | Pass | T-UI-06 by eye (Pending) |
| T-UI-42 | Pass | New, three window tests. The Person picker lists the codex people, narrows as you type, Enter inserts the card; New codex person… makes the entry and card, and one Undo removes both; Write a loose card here inserts a loose card. New codex creature… works the same. Insert ▸ Clue sits right after Information in the Insert menu and puts a Hint inside the person card holding the cursor; the editor shows the clue's text. The Codex card lists only places and clues. Right-click offers Convert to codex entry on a loose card, not on a codex card; with two fitting types it asks which; a taken name asks Link or New and lists "Mood: card says ‘nervous’, entry says ‘calm’"; one Undo brings everything back |
| T-UI-43 | Pass | New. A codex action that fails unexpectedly says "Scriptorum could not do that in the codex…", writes a crash log with the error and changes nothing; the window shows the message. Read-only: "This adventure is read-only" |
| T-WORLD-01 … 29, T-FONT-01 … 03, T-LOOK-01 … 06, 08 … 12 | Pass | T-WORLD-09 corrected |
| T-WORLD-30 | Pass | New. A loose person card, a creature and a card of an own type (River folk, shown as a person card) become entries; the PDF's text is identical before and after the three conversions; the own type keeps Description on the card; the Information stays inside the card; a codex card is refused; three undos restore the text and codex exactly |
| T-WORLD-31 | Pass | New. Two fitting types listed; the taken name with its one differing value; Link keeps "calm" and fills Description; one undo; New makes `c-ulrika-2` |
| T-WORLD-32 | Pass | New, three tests. The clue's text prints with its name, in full where written and as "Hint: The broken oar → p. 2" on Anders's card; renaming and editing the clue changes every place; no empty-element warning; the accessible PDF builds; a clue in use cannot be deleted; m1-basic prints byte-identically |
| T-WORLD-33 | Pass | New. How to play under Mood with its label, for a loose card and a codex person; Ulrika's Clues line lists the ledger and the oar with their pages; cards without them have no such line; the Clue entry and the overview say Anders Lind and Ulrika know the oar; the handouts PDF holds no How to play |
| T-LOOK-07 | Pending | By eye: the clue mark, How to play and the Clues line on a page (sample `m6-clues`) |
| T-REL-01, T-REL-03 | Not run | M6 part D |
| T-REL-02 | Pending | Network check on your machine. Here: the app ran 25 s under `strace` with no AF_INET or AF_INET6 connection |
| T-USE-01, T-USE-02 | Pass | Both goals reached; all scenario checks passed. New C4 steps: write a loose card, give it How to play, Convert to codex entry, Insert ▸ Person ▸ New codex person…, Insert ▸ Clue ▸ New clue…, and the export |

## Problems found and fixed while building

- None in earlier code. Three of my own first test drafts were wrong and were fixed before the report: a wrong block index, a count that missed `#person[` (a new empty card has no brackets, as before), and an expectation that Information written in one card of a person would be pointed to from that person's other cards, which the design does not ask for.

## Correction to an existing test

- **T-WORLD-09** (`tests/test_ui_m3.py`): the M2 sample's person card has Linked to as plain text, which the Person codex type has no field for. Before this build that text was dropped by the conversion; now it stays on the card (F3: nothing is lost), so the test expects `#card(entry: "c-lovisa-berg", linked-to: "The harbour, the Hoppet")[`.

## T-USE findings

| Kind | Finding | Milestone |
|---|---|---|
| friction | A new clue starts without a description. Text typed into its Information item stays with that item and is not saved as the clue's description, so a second item showing the same clue prints only its name until the clue is given a text in the codex | later (issue #7) |
| friction | Labels typed in pasted text stay after converting | later, with import (issue #2, already open) |
| friction | Adding a map always goes through a file dialog | later (issue #3, already open) |

## Tests added

T-SRC-20 (1 test), T-WORLD-30 (1), T-WORLD-31 (1), T-WORLD-32 (3), T-WORLD-33 (1), T-UI-42 (3), T-UI-43 (1): 11 in all. The Test Plan got these IDs, and the sample `m6-clues`, before the build.

## Hand checks for the project manager

1. **Convert.** Open `m6-clues`, right-click Märta Holm's card ▸ Convert to codex entry ▸ Person. The card now shows the codex entry; the page looks the same. Undo once: the loose card is back and the entry is gone.
2. **Link.** Right-click the second Ulrika ▸ Convert to codex entry ▸ Person ▸ Link to the existing ▸ read the difference ▸ Link.
3. **Pickers.** Insert ▸ Person: type part of a name, press Enter. Insert ▸ Clue with the cursor in a person card.
4. **On the page.** How to play under Mood, the clue mark and name, and Ulrika's Clues line.
5. **Your adventure.** In *Oroligt i Widtsköfle*, try New entry ▸ Creature again: if it still does nothing, it now should say why. Please add what it says to issue #1.

## Sample checksum (Linux)

`m1-basic.pdf`: `8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69`

Unchanged from 0.6.4 and 0.6.5. Information without a clue and a person card without How to play print byte-identically.
