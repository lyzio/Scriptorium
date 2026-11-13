# Scriptorum M6-0.6.5 — Changes

Base: **M6-0.6.4**, which is laid on top of M6-0.6.3, M6-0.6.2, M6-0.6.1 and M5-0.5.4. This is part C3 of Milestone 6, after the project manager's tests of C2:
- sub-headings from anywhere and outside scenes, and End of scene;
- the editor's width, and coming back to the same place;
- numbered pins, the map key and lines;
- Only as handout.

Every file not listed here is unchanged from M6-0.6.4.

**In the project** this folder holds only the added and changed text files. Lay it on top of M6-0.6.4. Left out because a script writes it: `scriptorum/ui/dist/app.js` (`npm run build`). The zip `M6-0.6.5.zip` is complete.

## Added

| File | Why |
|---|---|
| `tests/test_m6c3.py` | T-SRC-19, T-BUILD-31, T-UI-40, T-UI-41, T-WORLD-27 … 29 |

## Changed

| File | Why |
|---|---|
| `scriptorum/core/source.py` | `skipped_headings` also checks sub-headings outside scenes; `retag_outside_headings` writes them one level higher, with their style label, in the build's copy (F4, F17) |
| `scriptorum/core/build.py` | Calls `retag_outside_headings`; the author's text is unchanged |
| `scriptorum/core/world.py` | Pins keep a number and a note; a new `line` item, between two pins or through points, solid or dashed; `pin_numbers`; the build places pin lines on their pins (F5) |
| `scriptorum/bundled/scriptorum.vaesen/templates/_page.typ` | Sub-headings outside a scene: tagged one level higher, drawn in their sub-heading style |
| `scriptorum/bundled/scriptorum.vaesen/templates/map.typ` | Numbered pins, lines with labels, the key beside or under the map (F5) |
| `scriptorum/bundled/scriptorum.vaesen/templates/handout.typ` | The `give-out` style: "Give out Handout n · title" (F6) |
| `scriptorum/bundled/scriptorum.{plain,legends-and-lattes,call-of-cthulhu}/templates/_page.typ`, `map.typ`, `handout.typ` | Written again by `tools/make_general_themes.py` |
| `scriptorum/bundled/scriptorum.core/elements/handout.json` | The Only as handout field (`only-handout`, off by default and never written while off) |
| `scriptorum/bundled/scriptorum.core/typst/elements.typ` | The handout prints the give-out line when Only as handout is ticked |
| `scriptorum/bundled/scriptorum.core/labels/en.json` | "Only as handout", "Give out Handout {n}" |
| `scriptorum/bundled/scriptorum.en/strings/editor.json`, `map.json`, `error.json` | End of scene, the Only as handout tag, the Line tool, pin number and note, line style and label (F15) |
| `scriptorum/bundled/scriptorum.en/strings/guide-theme.json`, `tools/guides/how-to-write-a-theme.md` | The theme guide describes the give-out style, numbered pins and lines (F19) |
| `ui-src/editor.ts` | Sub-headings allowed at the top level; their sections end at a scene; fold outside scenes; End of scene; the "End of scene" line; the Only as handout tag |
| `ui-src/app.ts` | End of scene in the Insert menu; outline items for sub-headings outside scenes; remembering and restoring the place in the text for each tab |
| `ui-src/shell.ts` | End of scene in the Structure group |
| `ui-src/world.ts` | The Line tool, numbered pins, pin number and note, line style and label; tells the editor when a view opens and closes |
| `scriptorum/ui/styles.css` | The editor fills its pane, with paragraphs at 100 characters and room for the fold buttons; End of scene line; map lines and pin numbers; the Only as handout tag |
| `tests/test_m6c2.py`, `tests/test_ui_m4.py` | Corrected tests (see TEST-REPORT.md) |
| `tests/scenarios/run_use_scenarios.py` | The C3 steps |
| `scriptorum/__init__.py`, `pyproject.toml`, `ui-src/package.json` | Version 0.6.5 |
| `scriptorum/ui/dist/app.js` | Rebuilt (zip only) |

## Deleted

None.
