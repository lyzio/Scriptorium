# Scriptorum M6-0.6.6 — Changes

Base: **M6-0.6.5** (`main`). This is part C4 of Milestone 6 (decided 13 November 2026): the codex points of F3, the Clue field on Information (11.3), and How to play and the Clues line on the person card (11.4).

- Convert to codex entry everywhere it fits, with a taken name (Link or new, with the differing values listed) and several fitting types
- pickers for Insert ▸ Person, Creature and Clue; the Codex card item lists only entries without a card of their own
- codex actions never fail silently
- clues as Information, with Insert ▸ Clue; a Clue entry and the clue overview say who knows it
- How to play and the Clues line on the person card

Issues fixed: none. No open issue was planned for this build; #1 (New entry ▸ Creature does nothing) is planned for a later build, and this build only makes such a failure say why.

Every file not listed here is unchanged from M6-0.6.5.

## Added

| File | Why |
|---|---|
| `tests/test_m6c4.py` | T-SRC-20, T-WORLD-30 … 33, T-UI-42, T-UI-43 |
| `tests/samples/m6-clues/` | Sample *The Ferryman's Debt*: loose cards to convert, a codex person with How to play, clues inside and outside cards, a creature, an own codex type shown as a person card, the clue overview |

## Changed

| File | Why |
|---|---|
| `scriptorum/core/world.py` | Convert to codex entry (fitting types, field mapping, fields kept on the card, a taken name with its differences, linking); who knows a clue; an own type may name the element that shows it (F3) |
| `scriptorum/core/session.py` | `convert_info` and `convert_to_entry` as one undo step; a codex change that fails is undone; the codex list carries a clue's text and the elements an own type may be shown as; a Clue entry lists who knows it; a clue Information gives no empty-element warning |
| `scriptorum/core/source.py` | A codex card keeps fields its codex type lacks, as written, and writes them back (F3) |
| `scriptorum/app/bridge.py` | `convertInfo`, `convertToEntry`; every codex call says why it failed, and an unexpected error is written to a crash log (F3, F2.11) |
| `scriptorum/bundled/scriptorum.core/elements/person.json`, `codex-types/person.json` | How to play (11.4) |
| `scriptorum/bundled/scriptorum.core/elements/information.json` | The Clue field (11.3) |
| `scriptorum/bundled/scriptorum.core/elements/card.json` | `keeps_extra_fields` |
| `scriptorum/bundled/scriptorum.core/typst/elements.typ` | A clue Information prints the clue's description and name; How to play; the Clues line; a card prints the fields kept on it; the clue overview says who knows each clue |
| `scriptorum/bundled/scriptorum.core/labels/en.json` | How to play, Clue, Clues, Known by |
| `scriptorum/bundled/scriptorum.vaesen/templates/_style.typ`, `information.typ`, `person.typ`, `end-clues.typ` | The clue mark, the clue's name, How to play, the Clues line, Known by in the overview |
| `scriptorum/bundled/scriptorum.{plain,legends-and-lattes,call-of-cthulhu}/templates/…` | Written again by `tools/make_general_themes.py` |
| `scriptorum/bundled/scriptorum.en/strings/codex.json`, `error.json`, `menu.json` | The words of this build (F15) |
| `scriptorum/bundled/scriptorum.en/strings/guide-theme.json`, `tools/guides/how-to-write-a-theme.md` | The theme guide describes `clue`, `how-to-play` and `clues` (F19) |
| `ui-src/app.ts` | Convert to codex entry with its questions; the picker; Insert ▸ Clue; no silent failures |
| `ui-src/editor.ts` | A clue Information shows the clue's text; fields kept on a card; the Codex card lists only entries without a card of their own; Information in a codex card shows that person in Known by |
| `ui-src/world.ts` | No silent failures; a Clue entry shows who knows it; the type editor's Shown in the text as |
| `ui-src/model.ts` | Fields kept on a card |
| `scriptorum/ui/index.html`, `styles.css` | The picker dialog; clue text and kept fields in the editor |
| `scriptorum/ui/dist/app.js` | Rebuilt |
| `tests/test_ui_m3.py` | T-WORLD-09 corrected: the Linked to text of the M2 sample now stays on the card |
| `tests/scenarios/run_use_scenarios.py` | The C4 steps; Insert ▸ Person and Creature write a loose card through the picker |
| `README.md`, `TEST-REPORT.md`, `CHANGES.md` | This build |
| `scriptorum/__init__.py`, `pyproject.toml`, `ui-src/package.json` | Version 0.6.6 |

## Deleted

None.
