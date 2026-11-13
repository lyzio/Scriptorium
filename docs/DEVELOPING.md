# Developing Scriptorum

How to run, test and change Scriptorum from its source. The [README](../README.md) says what Scriptorum is; the [changelog](../CHANGELOG.md) what each version brings.

## Running the tests

```
python -m pip install pytest pypdf
python -m pytest
python -m pytest -m "not ui"
```

The first runs everything; the second leaves out the window tests. The tests follow the project's Test Plan; each test name carries its plan ID, for example `test_T_FILE_08_…`. On Linux without a screen the window tests run headless (`QT_QPA_PLATFORM=offscreen` is set by the tests). The `tests` folder is a Python package, because spylls installs a package of its own called `tests`.

## Trying it by hand

Try the start-up step and Go back to version by hand (F22, 0.6.7), without the project's key and without a web server. `tools/try_update.py prepare` copies this app into a scratch folder as "the installed app" with a throwaway key, makes a signed update pack of it as version 9.9.9, and installs that into a scratch Scriptorum folder, as Download and install does after the download. `start` runs the installed app there: Help ▸ About shows 9.9.9, and the Help menu offers Go back to version 0.6.7. `prepare --broken` makes a 9.9.9 that fails to start, so Scriptorum goes back by itself and says so. `clean` removes it all. Nothing in this folder or in your own Scriptorum folder changes.


Pack the M6 part C4 sample, *The Ferryman's Debt*, with clues, a codex person with How to play, and loose cards to convert. Right-click Märta Holm's card and choose Convert to codex entry (it asks which type: Person, or the sample's own type River folk); right-click the second Ulrika to see the Link or new question. Try Insert ▸ Person, Insert ▸ Creature and Insert ▸ Clue:

```
python -c "from tests.conftest import pack_sample; from pathlib import Path; pack_sample('m6-clues', Path('.'))"
python -m scriptorum m6-clues.scav
```

Pack the example adventure and open it. Put the cursor in a scene and choose Insert ▸ End of scene, then add a Sub-heading 1 after it. Open a map in the Codex tab and try the Line tool. Tick Only as handout on a handout. Drag blocks by the strip at their left, into and out of a Box; drag an Information box into a person card. Right-click a sub-heading to raise or lower it, and drag sub-headings in the Outline tab. Open a person in the Codex tab, choose a Portrait and describe it; the card in the preview shows the picture in its corner. Insert ▸ Column break in a scene, and Help ▸ Check for updates…:

```
python -c "from tests.conftest import pack_sample; from pathlib import Path; pack_sample('example-jattens-skuld', Path('.'))"
python -m scriptorum example-jattens-skuld.scav
```

Make a module to install: a copy of the Plain theme under your own ID, packed as a `.scmod` file. Then open File ▸ Settings… ▸ Modules ▸ Install module… and pick `my-ink.scmod`:

```
python -c "from tests.test_m6a import theme_folder, scmod; from pathlib import Path; print(scmod(theme_folder(Path('try-m6'), module_id='my.ink', name='My Ink'), Path('.')).rename('my-ink.scmod'))"
```

Open Help ▸ How to write a theme and Help ▸ How to write a game system.

Pack the M5 part B sample, *The Lighthouse Keeper's Log*, which uses the table of contents, footnotes and every layout marker, then try File ▸ Export ▸ Booklet PDF… and Print-shop PDF…:

```
python -c "from tests.conftest import pack_sample; from pathlib import Path; pack_sample('m5-print', Path('.'))"
python -m scriptorum m5-print.scav
```

Pack the M5 part A sample, *The Bell at Skärvik* in the Plain game system and Plain theme, which uses every core element, and open it:

```
python -c "from tests.conftest import pack_sample; from pathlib import Path; pack_sample('m5-plain', Path('.'))"
python -m scriptorum m5-plain.scav
```

Try the zoom bar above the preview, Ctrl and the scroll wheel over a page, and Help ▸ Check installation….

Pack the M4 sample, which uses every element in its final frame, and open it:

```
python -c "from tests.conftest import pack_sample; from pathlib import Path; pack_sample('m4-look', Path('.'))"
python -m scriptorum m4-look.scav
```

Or start Scriptorum and choose **Open the example adventure** on the welcome screen. Try the themes in File ▸ Settings… ▸ Adventure, and dark mode with the switch at the right of the menu bar. Holding **Shift** while Scriptorum starts skips a palette's own stylesheet.

The M3 sample `m3-world` (codex, map, handouts) and the M2 sample `m2-full` still work as before.

Run the Game Master scenarios (T-USE-01 and T-USE-02). They write a log, screenshots, PDFs and findings into a folder:

```
python tests/scenarios/run_use_scenarios.py scenario-output
```

## Rebuilding the interface

The interface is TypeScript in `ui-src/`, bundled into `scriptorum/ui/dist/app.js`. The bundled file is included, so running the app needs no Node.js. Only changing the interface does:

```
cd ui-src
npm install
npm run check
npm run build
npm run build:test
```

`check` type-checks, `build` writes `scriptorum/ui/dist/app.js`, and `build:test` writes `tests/js/inline.cjs` for the escaping test.

## Layout

| Path | What it is |
|---|---|
| `scriptorum/core/scav.py` | The .scav file and unpacked folders: load, crash-safe save, migration (F1, F2.4) |
| `scriptorum/core/protect.py` | Recovery copies, snapshots and open-elsewhere locks (F2) |
| `scriptorum/core/modules.py` | Module library, validation, .scmod packages, game-system data (section 9) |
| `scriptorum/core/source.py` | Source format reader and writer, tables, images, inline dice, locked blocks (3.4) |
| `scriptorum/core/build.py` | Build assembler: turned-on elements, title page, page settings, positions (3.3, 9.6) |
| `scriptorum/core/world.py` | Codex, maps, relationship chart, handout list and the M2 upgrade (F3, F5, F6) |
| `scriptorum/core/session.py` | One open adventure: what the window needs from the core |
| `scriptorum/core/startup.py` | The start-up checks and Help ▸ Check installation (F9, M5) |
| `scriptorum/core/preflight.py` | Preflight, the booklet and the print-shop version (F7.5, F7.6, M5) |
| `scriptorum/core/viewstate.py` | The preview zoom remembered for each adventure, outside the file (F7.2, M5) |
| `scriptorum/app/startup_window.py` | The start-up window (F9, M5) |
| `ui-src/preview.ts` | The zoom bar and zoom keys of the live preview (F7.2, M5) |
| `scriptorum/core/fonts.py` | Font guard (F11) |
| `scriptorum/core/palettes.py`, `appsettings.py` | App palettes and their contrast check (F16); app settings (F18) |
| `scriptorum/core/spelling.py` | Spell check (F4.8) |
| `scriptorum/core/crashlog.py` | Local crash logs (F2.11) |
| `scriptorum/app/` | PySide6 window, tabs and the WebChannel bridge (D4) |
| `scriptorum/ui/` | Interface page, styles and the bundled script |
| `scriptorum/bundled/` | The modules that ship with the app (9.8) |
| `scriptorum/dictionaries/` | Swedish and English spell-check dictionaries, with their licences |
| `ui-src/` | Interface source (TypeScript); `world.ts` is the codex, maps, chart and handouts; `shell.ts` the palettes, Settings window and toolbar groups; `icons/` the Phosphor icons (MIT) |
| `scriptorum/examples/` | The example adventure *Jätten Finns skuld* (F20) |
| `tests/` | Automated tests, samples (`m1-basic`, `m1-locked`, `m2-full`, `m3-world`, `m3-handouts`, `m4-look`, `example-jattens-skuld`) and the scenario script |
| `scriptorum/bundled/scriptorum.*/vendor/` | Typst packages copied into each theme, pinned, with their licences: fletcher 0.5.8, CeTZ 0.3.4, oxifmt 0.2.1 (D15) |
| `tools/guides/`, `tools/make_guides.py` | The author guides as written (also in the project), and the tool that turns them into interface text (F19) |
| `ui-src/guide.ts` | The guide window of the Help menu (F19) |
| `tools/make_ornaments.py`, `tools/make_general_themes.py` | Draw the themes' ornaments; write the two general themes from the Vaesen templates |
| `linux-kit/`, `tools/make_linux_kit.py` | The Linux kit for testers |
| `tools/vendor_typst.py` | Copies a Typst package into a module and turns its package imports into relative paths |
| `scriptorum/boot.py` | The start-up step: runs a newer verified version from the author's folder, or the installed one (F22) |
| `scriptorum/core/packs.py`, `signing.py`, `update_key.py` | Update packs, the versions kept in the author's folder, the signature check and the project's public key (F22) |
| `tools/release.py` | The release script: the signing key once, then the pack and the signed update file (F22, D12) |
| `.github/workflows/release.yml` | The release job on GitHub: signs and attaches the update files when a tag v<version> is pushed (F22) |
| `tools/try_update.py` | A test update for trying the start-up step and Go back by hand, with a throwaway key |

## Notes for this version

- **Where an update goes.** A verified pack is unpacked into `<Scriptorum folder>/app-versions/<version>/` (the `scriptorum` package, `pack.json` with every file's checksum, and `pack.sig`). `state.json` beside them says which version runs, which one is the previous one, and which ones failed to start. At every start the folder is checked again file by file against its signed list, so a changed or damaged file means the installed version runs.
- **What counts as starting.** A version has started once its window is ready, or when it closes normally. A version that raises an error before that is set aside at once and the previous one starts in the same go; one that crashes is set aside at the next start. The details go into the crash log folder (`update-start-….log`).
- **Bundled modules in a pack** are the pack's own `scriptorum/bundled/`. During development they keep version 1.0.0, so the T-MOD-12 rule still applies: a changed bundled module replaces the installed copy at start-up, also when going back. From version 1 on, a changed bundled module gets a new version and is installed beside the old one.
- **The installers (part D)** must carry cryptography and spylls with their package metadata, since the start-up step compares the versions a pack was made for with the ones the app runs on.

Notes from M6 part C4 and earlier:


- **Dragging** is `ui-src/drag.ts`: pointer events, a ghost copy and a drop line, no native drag-and-drop. The window tests drag the same way, with `tests/drag_js.py`.
- **Skipped heading levels** are found by `skipped_headings` in `scriptorum/core/source.py` and reported by `Session.heading_warnings`.
- **The build helper** is `scriptorum/core/helper.py`. It runs `python -c … serve()` beside the app; an installed app (part D) runs it as `scriptorum --scriptorum-build-helper`. It talks to the app over its own standard input and output, and ends when the app ends.
- **Tests and eval.** The page policy forbids `eval`, which the window tests use to drive the window. A test window (`headless_test=True`) therefore loads the same page with `eval` allowed. T-UI-30 opens the real page, as the app does.
- **spylls is MPL 2.0, not MIT.** Its licence file says Mozilla Public License 2.0, while its package metadata says MIT. The licence file governs. MPL 2.0 is compatible with GPL 3, and the licence register is corrected.

Notes from M6 part A:

- **Where things live.** The module manager is `scriptorum/core/modmanager.py`; disabling, removal, the same-version rule, safe unpacking and the package-import check are in `scriptorum/core/modules.py`. Which modules are disabled is kept in `disabled.json` in the module library.
- **The compile check** builds the test adventure with only the elements the game system turns on, and its dice in the game system's own notation. Before, a game system that turned on only some elements could never pass.
- **Bundled modules keep their versions** during development, so a changed bundled module still replaces the installed copy at start-up (T-MOD-12). The same-version rule applies to every other module.

Notes from M5 part E and earlier:

- **Headings drawn by the theme.** The title page's title and each scene's title are real headings: the shared templates `title-page.typ` and `scene.typ` draw them with a show rule, labelled `<scriptorum-title-heading>` and `<scriptorum-scene-heading>`. A theme of one's own should do the same (the theme guide, F19, will say so); without the scene label it loses the scene bookmarks and contents lines.
- **Image descriptions in the text** are written as `#image("/assets/images/x.png", alt: "…")`. An image without one keeps its M4 form, so older adventures save unchanged.
- **The example adventure** jumped from a scene to a level-4 heading; since M6 part C2 those headings are Sub-heading 1, so its accessible PDF passes. The test sample keeps the old text.

Notes from M5 part B:

- **Preflight and the print variants** live in `scriptorum/core/preflight.py`. The booklet is a second Typst pass that places the finished pages on the larger sheets. The print-shop version is laid out in the first pass (a bigger page with the crop marks in its foreground), because Typst cannot place PDF pages inside a PDF/A file.
- **PDF/A needs a date.** The print-shop PDF carries the adventure's last-saved day, so the same file still exports the same PDF; the other exports carry no date.
- **Page starts and frames.** Typst cannot start a page inside a frame. A frame (box, quote, person card, countdown, Information, codex card, full-width section, never split) switches page and column breaks off inside it, so a rule can never break the build.
- **Scene bookmarks** come from a hidden heading in each scene; that is why the `m1-basic` checksum changed.
- **The preview window** is `scriptorum/ui/preview.html` with its own small script (`ui-src/preview-window.ts`, built into `dist/preview-window.js`). It shares the main window's offline profile, so it cannot reach the network either.
- **Margins** may be the same on both sides (`x`) or `inside` and `outside`; the shared page template `_page.typ` takes either, with the header and footer lines.

Notes from M5 part A:

- **Plain theme from the shared templates.** Like the other general themes it is written by `tools/make_general_themes.py` from the Vaesen templates, with its own `_style.typ` head and frames, the Vaesen text and heading fonts, and the Vaesen papers turned to greys. The Quote's scrap tint and the ink of a handwritten quote moved into `_style.typ` (`quote-tint`, `hand-ink`), so the Plain theme prints them in grey; the other themes print exactly as before.
- **Free stat lines.** A game system's `stat-blocks/creature.json` may say `"free_stats": true`: the creature then gets one text field, `stat-lines`, written one line per stat. Dice notation may allow a modifier (`"modifiers": true` in `notation.json`).
- **Standard modules.** A module whose manifest says `"standard": true` is offered first in File ▸ New adventure.
- **Start-up checks** live in `scriptorum/core/startup.py`; the window is `scriptorum/app/startup_window.py`. `SCRIPTORUM_DICTIONARIES` points spell check at another folder, which the tests use to show a missing dictionary.
- **Typing on the page** (F12 stage 2) was moved to a later version on 11 November 2026 (L12, design document section 6). Version 1 has no Rust and no compiled add-on of its own.

Notes from M4:

- **One set of templates for three themes.** Every template draws through the theme's `_style.typ`. `tools/make_general_themes.py` copies the Vaesen templates into the two general themes and writes their `_style.typ` (colours, fonts, frames). After changing a shared template, run it again; a test checks that the copies match.
- **Static font weights.** Each font is the static weight its own project ships. For Playfair Display that project now ships only a variable font, so the static weights come from Google Fonts' instances (`@expo-google-fonts/playfair-display` 0.4.2). Berolina was supplied by the project manager (Peter Wiegel, GPL and SIL OFL).
- **Long handouts** flow from sheet to sheet: each sheet is a page of its own with its drawn paper behind the text. A handout on several sheets is not tilted (the tilt applies to one-sheet handouts).
- **Box and Quote** hold paragraphs (and a Box also tables); a list inside them is kept as written, as a locked block, like lists elsewhere in the editor.
- **App settings** are kept in `app-settings.json` in Scriptorum's own folder; a palette made with the colour pickers is saved in the module library as `my.<name>`.

Notes from M3-0.3.2:


- **Handout look (F6.5, F6.6, revised 6 November 2026).** Drawn after the project manager's four reference examples. Paper styles live in `scriptorum.vaesen/handouts.json`: outline and inner line colours, how torn the edge is, folds, spots, stains and tears, and the ink. The handwriting fonts are in the theme's `fonts/` folder with their licences.
- **"GM book" is now the adventure PDF** everywhere, in the menus too: Export adventure PDF…, Show the adventure.
- **Linux kit** (`linux-kit/`, `tools/make_linux_kit.py`): a wheel, `setup.sh`, `uninstall.sh`, a menu entry, the `.scav` file type and an icon. The launcher switches the web view's Chromium sandbox off only as root or where AppArmor blocks it (Ubuntu 23.10 and later); the view shows only the app's own pages.

Notes from M3-0.3.1:

- **Storage (design doc section 4).** One JSON file per codex entry (`codex/<id>.json`), author-defined types in `codex/types/`, chart positions in `codex/relationship-chart.json`, and each map in `maps/<id>/` with `map.json` and its base image. All of it is plain UTF-8 JSON, so Git shows the changes line by line.
- **Built-in codex types** Person, Place and Clue live in the core element kit (`codex-types/`); Creature comes from the Vaesen game system and takes its fields from the creature stat block.
- **Typst packages** are copied into the Vaesen theme (`vendor/`); their `@preview` imports are rewritten as relative paths. Nothing is fetched from the internet (D9, D15).
- **Cytoscape.js 3.34.0** (MIT) draws the relationship chart in the window; it is bundled into `scriptorum/ui/dist/app.js`.

Notes from M2:


- **Every element in the core kit.** As approved on 5 November, all elements live in `scriptorum.core`. The Vaesen game system turns them on in `elements.json`, sets the creature's stats in `stat-blocks/creature.json` and the dice in `notation.json`. The adventure text calls elements by name only, so files saved with M1 open and save unchanged.
- **Bundled modules keep version 1.0.0** until version 1. When an app build ships a bundled module whose files changed, it replaces the installed copy at start-up.
- **Pagination lives in the core kit.** When a scene starts a new page, and an act heading sharing its first scene's page (F7.4), are decided in the core element kit, so every theme behaves the same.
- **Scene links.** A scene gets a permanent link name (`id: "s-…"`) only the first time a countdown step points to it, so other scenes' text never changes.
- **Fonts.** The Vaesen theme still uses Libertinus Serif (SIL OFL, built into Typst) until the final theme fonts arrive in M5.
