# Scriptorum — M6-0.6.8 (Milestone 6: Modules and release, part D on GitHub)

Scriptorum is a desktop text processor for game masters writing their own adventures, with pixel-perfect PDF output through Typst. This folder is all of Milestone 5 plus **parts A, B, C1 to C5 of Milestone 6, and the installers of part D built on GitHub** of the design document (section 10).

Licence: GPL-3.0-or-later (see `COPYING`).

## What 0.6.8 adds: installers built on GitHub (M6 part D)

- **The packaging kit is in the repository,** in `packaging/` (kit 1.0.2). Its README says how to build an installer by hand on each platform, as before; you can now point it at this folder itself.
- **Every tag builds every installer.** Pushing a tag `v<version>` on main runs `.github/workflows/installers.yml`: the AppImage on Ubuntu 22.04, the .dmg for Apple Silicon (macos-15) and for Intel Macs (macos-15-intel), and the Windows setup program, each with the kit's own seven steps and smoke test. They are attached to the release v<version>, beside the signed update files of the release job. GitHub's standard machines are free for a public repository.
- **Test installers from any branch or tag:** Actions ▸ Installers ▸ Run workflow. The results are downloads of that run; tick "attach" with a tag to add them to that tag's release (this is how v0.6.7 gets its installers).
- **The kit always uses the app's own pins.** It reads PySide6, typst, spylls and cryptography from this `pyproject.toml` and installs exactly those, so it can never fall out of step with an app version. cryptography and its package metadata now go into the installed app, so updates (F22) work there.
- **Fixed in the kit:** `--release` refused every build from 0.6.7 on, because it found the placeholder text in `updates.py`, where it stays as a constant; it now checks the value of `UPDATE_URL`.

## What M6 part C5 added

- **Download and install (F22).** When Help ▸ Check for updates… finds a newer version made for this app's Python, Qt and Typst, it offers Download and install beside the download page. Nothing is downloaded until you click. The pack is checked (size, checksum and the project's signature) and unpacked into your own Scriptorum folder, in `app-versions/`, and the window says "Ready. The update is installed the next time Scriptorum starts." Open adventures are not interrupted, and the installed app itself is never changed. A version that needs a newer Python, Qt or Typst says "This version needs a new installer" and offers only the download page.
- **Signed updates (F22).** Every update file and every pack is signed with the project's private Ed25519 key, which is kept outside the app and the repository; the app holds the public key in `scriptorum/core/update_key.py` and uses nothing that is not signed with it. The signature library is cryptography 48.0.1 (Apache-2.0 OR BSD-3-Clause), the newest version that still runs on Intel Macs with macOS 12. **The project's key** was made by the project manager on 13 November 2026: its public key is built in, and the private key is kept outside the repository and as the GitHub secret `UPDATE`.
- **The start-up step (F22).** `python -m scriptorum` (and the `scriptorum` command) first looks in your own folder for a newer verified version made for this Python, Qt and Typst, and runs it from there; otherwise it runs its own version as before. A version that fails to start is set aside: Scriptorum goes back to the previous one (at once after an error, or at the next start after a crash) and says so. Help ▸ Go back to version X does the same by hand, and is offered only while a version from your folder runs. Only the newest and the previous version are kept. Adventures, modules, palettes and settings are never touched.
- **The update address (F21, F22).** The built-in address is now the GitHub release address, `https://github.com/lyzio/Scriptorum/releases/latest/download/scriptorium-update.json`. Settings ▸ Application ▸ Updates has an Update address field: an https address entered there is used instead, for the check and the download; anything else is refused with a plain message, and Use built-in address clears it. The Check for updates window names the address it used. A signed update file may say that the address has moved; Scriptorum then asks whether to use the new one.
- **Releases are made on GitHub (F22, D12, decided 13 November 2026).** Pushing an accepted build's tag on main, `git tag -a v0.6.8 -m "What is new."` then `git push origin v0.6.8`, starts the release job (`.github/workflows/release.yml`). It runs in the environment `release` (where you can require your approval), signs with the key kept as the repository secret `UPDATE` (the whole key file, BEGIN and END lines included), and attaches the update pack and the signed `scriptorum-update.json` to the release v0.6.8; you add the installers after. The release is never marked pre-release, since GitHub's "latest" address skips those. It runs on a standard GitHub runner, free for a public repository, and builds nothing else. The same script runs on your own machine too: `python tools/release.py keygen` makes the key once, and `python tools/release.py 0.6.8 --note "…"` on the tagged commit of main writes the files into `dist-release/` (`--publish` uploads them). It refuses an untagged commit, changed files, a version that is not the app's, a key kept inside the repository, and a missing or wrong secret.
- **Paragraphs fill the editor's width (issue #8).** In a wide window, in full screen and with the preview hidden, running paragraphs and headings now use the full width of the editor column, like the frames.
- **A short block's menu stays usable (issue #9).** The ↑ ↓ + × buttons sit in a 2 × 2 square beside the block, and while the pointer is on them no other block's menu shows, so a one-line block's lower buttons no longer hand over to the next block.

## What M6 part C4 added

- **Convert to codex entry, everywhere it fits (F3).** Right-click a person card, a creature, or any block whose kind is the card element of a codex type, and choose Convert to codex entry. A new entry gets every field the block has; a field the codex type lacks stays on the card in the text (in the editor under "Kept on this card"), so nothing is lost. The block becomes a card of the entry and prints as before. Information written inside a person card stays inside and is known by the entry. One Undo brings back both the card and the codex. A codex card does not offer it.
- **A taken name, and several fitting types (F3).** If an entry of that type has the same name, you are asked "Link to the existing Ulrika, or make a new entry?". Link first lists every value that differs ("Mood: card says ‘nervous’, entry says ‘calm’"), keeps the entry's values and fills its empty fields from the card. When several types fit, you pick the type first.
- **Pickers for Person, Creature and Clue (F3).** Insert ▸ Person and Insert ▸ Creature open a small picker: the codex's people (or creatures) first, narrowed as you type (Enter takes the first), then New codex person… (or creature), then Write a loose card here. A new entry and its card are one undo step. The Codex card item lists only places, clues and your own types.
- **Clues as Information (F3, 11.3).** Information has a Clue field. Insert ▸ Clue (in the Insert menu, after Information) picks or makes a clue and inserts a Hint linked to it, inside the person card when the cursor is in one. It prints the clue's description, with a small clue mark and the clue's name; on the cards of others who know it, as a pointer with its page. The editor shows the clue's text with an Edit the clue button. A Clue entry shows who knows it, and the clue overview lists that too.
- **How to play and the Clues line (11.4).** A person (card and codex entry) has How to play, printed right under Mood with a small HOW TO PLAY label. A Clues line lists each clue connected to the person, through clue Information they know or through Linked to, with its page. Neither prints when empty, so other cards print exactly as before.
- **Codex actions never fail silently (F3).** A read-only adventure says "This adventure is read-only"; an unexpected error says so in plain words and writes the details to a crash log in the app's own folder.
- **Own codex types.** The New type editor has "Shown in the text as": a codex card, a person card or a creature. A type shown as a person card is offered by Convert to codex entry on person cards.

## What M6 part C3 adds

- **Sub-headings from anywhere, and outside scenes (F4).** Insert ▸ Sub-heading 1, 2 and 3 works wherever the cursor is. Inside a scene the sub-heading goes into the scene just after the Box, card or check that holds the cursor. Outside any scene (an info page before the first scene, or after an act heading) it goes where the cursor is. Outside a scene they print in the same styles but are tagged one level higher, so the accessible PDF and the bookmarks have them under their act with no level skipped. The outline lists them, and they fold and drag like the others.
- **End of scene (F4).** Insert ▸ Structure ▸ End of scene moves everything after the cursor out of the scene, just after it, so you can write an info page between two scenes. No marker is written: a scene's text already ends at its closing bracket. Each scene now ends with a thin "End of scene" line in the editor; Alt+→ / Alt+← and dragging move blocks into and out of a scene.
- **The editor fills its pane (F4).** The editor column now follows the window, in full screen and with the preview hidden. Paragraphs stop at about 100 characters; field rows use the full width.
- **Back to the same place (F4).** Coming back from the Codex, a map, the relationship chart, or another adventure tab returns to the same scroll position, block and caret.
- **Numbered pins and a map key (F5).** Pins show a number; the key beside the map (or under a wide one) lists number, name and the pin's note. Numbers follow the order placed and can be changed. The handout version lists only the pins of handout layers.
- **Lines on maps (F5).** The Line tool joins two pins (the line follows them) or draws a free line ended by a double-click. Solid or dashed, with an optional label along it; each line follows its layer's Show in handout.
- **Only as handout (F6).** Tick it on a handout and the adventure PDF prints only "Give out Handout 1 · title" in its place; the handouts PDF is unchanged.

## What M6 part C2 added

- **Three levels of sub-heading inside a scene (F4).** Sub-heading 1, 2 and 3 are in the toolbar's Structure group, Format ▸ Style and Convert to. In the text they are `===`, `====` and `=====`. Right-click ▸ Raise or Lower, or Shift+Tab and Tab in the heading, changes the level; Lower is not offered where it would skip a level. A sub-heading moves with everything under it, up to the next sub-heading of the same level or higher. They fold like scenes, and the outline shows them indented under their scene.
- **Sub-headings in print (F7.4, F7.7, F17).** Each level has its own smaller heading style in every theme (set in the theme's `_style.typ` with `sub-heading-style` and `sub-heading-space`). A sub-heading never starts a page by itself and is never left alone at the foot of a page or column. PDF bookmarks nest acts, scenes and sub-headings; the table of contents still lists only acts and scenes. The accessible PDF tags them as levels 3, 4 and 5.
- **Older text with a skipped level.** An adventure with `====` directly under a scene opens unchanged; the warnings panel says which heading skips a level and has a button to raise it. The example adventure's five such headings are raised, so its accessible PDF now passes.
- **A bigger grip and Scriptorum's own dragging (F4.13).** A grab strip runs down each block's left side. Dragging shows a faint copy of the block and a drop line where it will land; where it is not allowed there is no line, the pointer says not allowed, and the status bar says why. The editor scrolls near its top and bottom edge. Esc, or letting go outside the editor, cancels. The system's drag-and-drop is no longer used, so the window can no longer lock up during a drag.
- **Into and out of containers (F4.13).** At the edge of a Box, quote or other container, move the pointer right to go one level in and left to come out: every 24 pixels is one level, and the drop line moves with it. An empty Box shows "Drop here" while you drag. Alt+→ moves a block into the container just above it, Alt+← moves it out; ↑ ↓ and Alt+↑ / Alt+↓ step out at a container's edge. A block goes only where it is allowed: a person card holds only Information.
- **Information keeps who knows it (11.4, F3.6).** Dragging an Information box into a codex person's card moves that person from Known by to the card; dragging it out puts them back in Known by. Between two cards the knowledge moves from one person to the other. Out of a loose person card, the status bar says that person no longer knows it.

## What M6 part C1 added

- **Breaks that break (F4, F7.4).** A column break, page break, table of contents or relationship chart inserted in the editor is now written with its brackets, `#column-break()`. Before, it was written `#column-break`, so Typst printed "(..) => .." and did not break. Every element with no body and no fields filled in is written this way. An older adventure that still has `#column-break` without brackets prints correctly too: the build adds the brackets in its own copy, and your file stays unchanged until you edit that block.
- **More air in every theme (F8).** Line spacing in running text is about 0.8 em (was 0.62) and paragraph spacing about 1.2 em (was 0.9). Text inside cards and boxes uses the same line spacing and is left-aligned, so no wide gaps open between words in narrow frames; running text stays justified. Table cells are left-aligned for the same reason. Each theme sets its spacing once, at the top of its `_style.typ`; How to write a theme has a new Spacing section. On the person card there is a small gap after the name and after Mood, a little more before Linked to, a medium gap before What they know and a small gap between the things the person knows; creature and codex cards are spaced the same way. The example adventure grows from 8 to 9 pages, and its people page moves from page 3 to page 4.
- **"What they know" only when there is something under it (11.4).** A person card with nothing known no longer prints the heading.
- **Person portraits (11.4).** A codex Person has a Portrait field, so the picture follows the person into every card; a loose person card has its own. Choose a JPEG or PNG; other files are refused. It prints in the card's top-right corner at about a third of the card's width, never cropped, in the theme's thin frame, with the name, mood and description beside it and the rest under it. Give it a description for screen readers: preflight warns when it is missing (the accessible PDF stops), and when the picture is below 300 dpi at its printed size. A card without a portrait prints as before. Portraits never go into the handouts PDF.
- **Help ▸ Check for updates… (F21).** Reads one small file over https from a fixed address. Until the project chooses that address, the app holds the placeholder "Paste update url here" and says that no update address is set yet, without making any request. With an address: a newer version shows its number, what is new and a button that opens the download page in your own browser; otherwise it says Scriptorum is up to date, or that the address could not be reached. At first start Scriptorum asks once whether to check every week; the answer is off by default. The weekly check can be switched in File ▸ Settings… ▸ Application. This is the only network request the app can make; the web view, Typst builds, modules and palettes stay offline.

## What M6 part B added

- **Safer builds (F7.1).** Every Typst build runs in a separate helper process that starts with the app and is reused, so the preview is as fast as before. A build that takes longer than 60 seconds is stopped, and the status bar says: "The last build was stopped after 60 seconds, probably because of a theme or module." The preview keeps its last good pages, and the next edit tries again. Exports have the same limit and write no file when stopped. If Typst crashes, only the helper goes down: your text is untouched, and the next build starts a new helper.
- **Module checks with the same limit (9.7).** Installing a module whose build never finishes is refused within 60 seconds. Help ▸ Check installation's theme self-test finishes and names such a theme instead of hanging.
- **Page script policy (F9).** Both of the app's pages carry a Content-Security-Policy: only Scriptorum's own two script files may run. Inline scripts, scripts from anywhere else and `eval` are refused.
- **Full screen (F9).** The button at the right end of the toolbar, View ▸ Enter full screen, or F11 (Ctrl+⌘+F on the Mac). The menu bar, toolbar and status bar stay. The button, the menu or Esc go back. Scriptorum remembers it for the next start.
- **About window (F9).** Help ▸ About Scriptorum has three tabs:
  - **About:** the version, "Idea by lyzio · lyzio.net" and the GPL, with its full text.
  - **Under the hood:** every part Scriptorum is built on, with its version, what it does and its licence. Click a row for the full text.
  - **Licences:** the full text of each licence used.
  Everything is stored in `scriptorum/licences/`, so it works offline. lyzio.net opens in your own browser.
- **Fixes after part A:** leftover milestone texts are gone, including "Margins, headers and footers … arrive in M5". The greyed File ▸ Save for sharing… is gone. The empty Insert menu now says "Open or create an adventure first", or "This adventure is read-only".

## What M6 part A added

- **File ▸ Settings… ▸ Modules is the module manager.** It lists every installed module with its kind, version, ID and description, and, for game systems, themes and element kits, which adventures on your Recent files list use it.
  - **Install module…** installs a `.scmod` file. It first checks the manifest, the file types, every font (the font guard), the required modules, that no Typst file imports a package by name, that a theme has a template or the generic frame for every element, and that the module builds with a test adventure. When a check fails it says why, in plain words, and nothing is left behind. The same file twice says it is already installed. The same ID and version with other content is refused, since adventures use exact versions.
  - **Disable / Enable.** A disabled module stays on the computer but is offered nowhere. An open adventure that uses it switches to protected mode at once, and back when it is enabled. Disabling asks first and names the adventures that use it.
  - **Remove** asks first, naming the adventures that use it. Modules that come with Scriptorum can be disabled but not removed. Core elements, English and Claret & Ink can be neither. A palette or interface language in use must be swapped first.
  - **Save as .scmod file…** writes an installed module as one file, to send along with an adventure. Modules that come with Scriptorum need no file.
- **Sharing an adventure.** An adventure never carries its modules. Send the `.scav` file and the `.scmod` files of every module it uses that did not come with Scriptorum. Opened without them, the adventure opens in protected mode, and its message lists every missing or disabled module by name, ID and version: "You need these modules to edit or export this adventure: …". Once they are installed, it opens normally.
- **Versions.** Settings ▸ Adventure has a version choice beside the game system and the theme. Picking another installed version shows it in the preview with a bar: "Previewing Ink 1.1.0. Nothing in the adventure has changed yet.", with Cancel and Apply. Only Apply changes the adventure, and only its module lines. An export never uses a version on trial. A new main version (2.0 after 1.x) warns first that the adventure may use things it lacks; those are drawn in a plain frame with a warning.
- **Safer .scmod files.** A file whose entries would land outside its own folder (`../`, an absolute path, a link) is refused whole, with the entry named. The check compares resolved paths, not path text.
- **No packages by name.** A module whose Typst imports `@preview/…` or any other `@namespace/…` is refused at installation, and every build checks again before compiling. The file and line are named in both cases.
- **The author guides** now install through Settings ▸ Modules in their Testing and Packing sections, with no copying by hand and no restart.

## What M5 part E added

- **Help ▸ How to write a theme** and **Help ▸ How to write a game system** open a guide inside the app, with contents at the left that jump to each section, and a button at the foot that opens the other guide. They need no internet access.
- The guides' text is interface text in `scriptorum.en` (`strings/guide-theme.json` and `strings/guide-game-system.json`), so a translation of the interface translates them too (F15). They are written in `tools/guides/*.md`, the same files kept in the project as documents, and `python tools/make_guides.py` turns them into the interface text; a test fails when the two differ.
- The theme guide covers the folder and manifest, every template and what it receives, page setup, fonts, ornaments, handout papers and the print-friendly rules, labels, licence and the unofficial notice, testing and packing, with Legends and Lattes and Call of Cthulhu as worked examples. The game-system guide covers turning on elements, the creature stat block, dice, codex types, elements of its own, labels and language modules, licence, testing and packing, with Vaesen as the worked example.
- The guides' own examples (a game system called Harbour Tales with an element of its own, and a theme made from a copy of Plain) are built by the tests exactly as written, so a reader who follows a guide gets a module that installs and prints.

## What M5 part C added

- **Every PDF is tagged** for screen readers: headings, reading order, lists, table header cells and the document language. The title on the title page is the first heading (level 1), act headings are level 1, and scene titles are level 2, drawn exactly as before. Ornaments, frames, stains and folds are marked as decoration, which screen readers skip.
- **Document language** (Settings ▸ Adventure, under the look). English by default; Swedish and the language of any installed adventure-language module are offered. It is written into the PDF, sets hyphenation, chooses the spell-check dictionaries (Swedish only, or English only), and chooses the module for the printed words.
- **Descriptions.** Every image in the text has a "Description for screen readers" field under it, and every map one in the map editor. Preflight warns when one is missing.
- **File ▸ Export ▸ Accessible PDF (PDF/UA)…** writes a PDF/UA-1 file. It needs every image and map described, and headings that do not skip a level; when something is missing it says what and where, on the author's line.
- PDF/A-2b and PDF/UA-1 can be combined with the pinned Typst 0.15.0 (checked in a test). The print-shop version stays PDF/A-2b.

## What M5 part B added

- **Page settings (F7.3).** Settings ▸ Adventure now also sets the margins (top, bottom, inside, outside), a header line, a footer line and page numbers, each showing where its value comes from. **Classical proportions** fills in margins in the classic 2 : 3 : 4 : 6 proportions for the paper. The page says how wide a column is, and warns when it is narrower than 45 mm.
- **Page starts (F7.4).** For each element kind: always a new page, only when needed, or never. **Compact** lets nothing start a page by itself. Two new layout markers in Structure: **Full-width section** (spans every column, floats to the top or bottom of its page) and **Never split** (keeps what it holds together). Typst's own rules already keep headings with what follows and avoid single stray lines.
- **Show breaks (F7.2).** View ▸ Show breaks marks page breaks, column breaks and forced page starts in the preview. Exports never show them.
- **Two pages and Own window (F7.2).** The zoom bar has **Two pages** (a printed book's spread: page 1 alone on the right) and **Own window** (the preview in a window of its own, with the same zoom bar, following every build). Both are also in the View menu.
- **Exports (F7.6).** File ▸ Export adds **Booklet PDF** (two pages per sheet on the next size up, A4 on A3 or A5 on A4, in fold order or side by side, without links or bookmarks) and **Print-shop PDF** (3 mm bleed by default, crop marks, PDF/A-2b). The booklet's order and sheet and the bleed are set under Printing in Settings ▸ Adventure.
- **Preflight (F7.5).** Every export checks that all fonts are embedded (else it stops), that each font has å, ä and ö, and that every image prints at 300 dpi or more (warning with its line). Warnings are counted in the status bar; a click opens the warnings panel, and a warning with a line takes you there.
- **Navigation (F7.7).** **Table of contents** (Insert menu) lists acts and scenes with their pages, each a link. **Footnote** (Insert menu) asks for its text and goes into the sentence as a chip; it prints at the foot of the page. The PDF has bookmarks for acts and scenes.

## What M5 part A added

- **Plain game system and Plain theme (F8).** The standard choice for an adventure written for no particular published game. File ▸ New adventure offers them first and preselects them; Vaesen and the other themes can still be picked.
  - *Plain game system* (`scriptorum.plain-system`) turns on every element of the core element kit. Dice use plain notation: `d6`, `2d10+1`, `d100`. A creature has no fixed stats: you write free lines such as "Strength 3", one per line, plus the usual sections. A check is free text with an optional difficulty.
  - *Plain theme* (`scriptorum.plain`) is a general theme, offered for every game system. Black text on white with one mid-grey; Libre Baskerville text and Playfair Display headings; thin single rules, no ornaments; the secret box is a thin double rule on pale grey; read-aloud text is italic with a rule at the left. Its handout papers are the Vaesen papers in greys. It prints sharply on any black-and-white printer.
- **Start-up window with checks (F9).** A small window in your palette comes first and ticks five checks: modules, fonts, spelling dictionaries, a one-line Typst page, and Scriptorum's own folders. When all pass it closes by itself and the main window opens (with the adventure you double-clicked, if any). When one fails, the window stays open and gives the reason in plain words. **Continue anyway** opens the app without that part, and a quiet bar in the window names what is missing. **Copy details** copies the results. **Help ▸ Check installation…** shows the same list on demand and can run the slower theme self-test. The dictionaries are loaded by the start-up window, so spell check is ready at once; without them spell check says it is unavailable instead of waiting.
- **Zoom in the live preview (F7.2).** A zoom bar on top of the preview: − and +, the size ("125 %"), Fit width and Whole page. Ctrl and the scroll wheel (⌘ on the Mac) zoom around the pointer; Ctrl + plus, Ctrl + minus and Ctrl + 0 work while the preview has focus. 50 % to 400 %, always sharp (the pages are SVG). The zoom holds while you type, and each adventure opens at the size you left it; this is kept in Scriptorum's own folder (`view-state.json`), never in the .scav file.
- **Palette editor: Save next to Done (F16).** While a new palette is edited, its Save and Cancel sit at the foot of the Settings window next to Done, always in view. Closing Settings with unsaved colours asks Save, Don't save or Keep editing; a save that fails shows its reason there.

## What M4 added (Milestone 4: Vaesen look)

Everything M3 did, plus:

**The Vaesen look (F8, D16, approved mockups 12.2 to 12.4)**
- The final fonts, all open-licence static weights bundled in the theme: **Berolina** for the title page and act headings, **Playfair Display** for scene titles and headings, **Libre Baskerville** for the text, **Cormorant Garamond** for read-aloud text and the secret box (Medium on the fill), **Acme** for labels and box titles.
- The **secret box**: a double frame with a red scroll and a pale grey or pale beige fill, chosen in Settings ▸ Adventure (F7.3).
- The **open curl frame** around Hints, Public information, checks, creature stat blocks and Boxes. Lists get a **pen-nib bullet**, bold at the start of a line prints as a **label in capitals**, tables get **beige bands**.
- Frames, curls, the scroll, bullets and the hourglass are the project's own drawings (`ornaments/`, made by `tools/make_ornaments.py`).

**New elements (section 11)**
- **Box** (11.10): a framed text box with an optional title; paragraphs and tables.
- **Quote** (11.11): Framed, Scrap of paper or Plain; title, signature (text or a codex person, whose handwriting it borrows), description, handwriting, tilt −5° to +5°, tint on the scrap.
- **Pacing note** (11.12): a small hourglass and a note about time for the Game Master.
- A scene's **Type** (11.1): "SCENE 2 · CLIMAX".

**Handouts (F6.5)**
- **Six hands** in the core element kit, so every theme offers them: Everyday hand, Copperplate, Flowing hand, Note hand, School hand, Typewriter. Files still store the font's name.
- **Tilt** −5° to +5° and the **Parchment** paper.
- **Long handouts on several sheets**: a slightly long letter is set up to 15 % smaller; a longer one continues on further sheets with "1 of 2" captions and "./." at the foot of each sheet but the last. The Handouts tab shows the number of sheets; more than 4 gives a warning.

**Two general themes (F8)**: **Legends and Lattes** (cozy fantasy) and **Call of Cthulhu** (1920s cosmic horror). A theme that needs only the core element kit is offered for every game system. Change the theme in Settings ▸ Adventure: the adventure re-renders at once, and its text, codex and maps never change.

**The app (F9, F16, F18)**
- **Claret & Ink** palette in **light and dark mode**, with a small Light / Dark switch at the right of the menu bar, and Follow the computer.
- **Six menus**: File, Edit, View, Insert, Format, Help. Export is under File ▸ Export.
- **The toolbar's insert groups**: Structure, Boxes, People, Rules, Handouts (Phosphor Light icons), plus Table and Image and the paragraph style. A group lists only what the game system turns on.
- **File ▸ Settings… (Ctrl+,)**: Application (spell-check language, start mode, snapshots, crash logs, interface language), Colours (palette, light/dark, text sizes, **New palette from this one** with a colour picker for every colour, Reset to Claret & Ink), Modules (the installed modules) and Adventure (the former adventure settings page, plus theme, secret-box fill and Add font).

**The example adventure (F20)**: *Jätten Finns skuld*, a Vaesen adventure in Lund at All Saints' 1868. Open it from the welcome screen or Help; a copy is saved in your documents.

**Also:** act headings in a row share a page with the first scene (F7.4); a new adventure starts with its first scene and no title line (F7.9).

## What M3 added (Milestone 3: World-building)

Everything M2 did, plus the codex, maps and handouts (design document F3, F5, F6). Each one is written once and used everywhere.

**Codex (F3)**
- The **Codex** tab lists every entry by type and folder, with a search box. The built-in types are Person, Place, Clue and Creature. Item and Faction come later (L10, L11), and **New type** lets you make your own type with text, formatted text, number, image, link and choice fields.
- An entry opens in place of the editor: its fields, folder, tags, and **where it is used**. That covers the scenes it appears in, the pages it printed on and the entries that link to it. **← Back to the text** returns to the editor.
- In the text an entry appears as a **mention** (its name), a **card** (the whole entry) or a **"see page"** line (its name and the page of its card). Use the entry's buttons or Insert → Mention / Codex card / See page.
- A scene's Location and People present, a person's Linked to, Information's Known by and a handout's Written by are **codex links**. Type or paste a name: a known name is linked, and a new name becomes a new entry.
- **Renaming** an entry changes every printed name; the text itself never changes. An entry that is still used cannot be deleted, and the message says where it is used.
- Right-click selected text → **Make a codex entry of the selected text**. Right-click an M2 person card → **Turn this person into a codex entry**.
- Information known by a person is listed on their card: **in full where it is written**, as a **short pointer with its page** elsewhere.
- The **relationship chart** (Codex → Relationship chart) lays out the entries that link to each other. Drag them where you want; the printed chart (Insert → Relationship chart) uses the same places.
- **Clue overview** and **Index of people and places** at the end of the adventure PDF, each switched on in Adventure settings.
- The **"In this scene"** panel under the sidebar lists the codex entries of the scene the cursor is in.
- **M2 adventures:** a banner offers to turn the text in Location, People present, Linked to and Written by into codex links. You choose what to link; the rest stays text. One Undo takes it all back.

**Maps (F5)**
- **New map** from a JPEG or PNG picture. The map editor has layers with **Show in handout**, and tools for pins (linked to codex entries), labels, areas (3 to 15 corners) and notes. In **Browse**, a click on a pin opens its entry.
- Put a map in the text; tick **Handout also** to make it a handout. The adventure PDF prints every layer; the players' copy only the layers set to show in handouts.
- A map image that is below 300 dpi at its printed size gives a warning.

**Handouts (F6)**
- Handouts are numbered #1, #2… in adventure order. In the adventure PDF each one shows its number where it is given out.
- The **player PDF** (Export → Export handouts PDF…) holds only the handouts, one per page. Each sits on a drawn sheet of paper (F6.5, revised 6 November): a torn, hand-drawn outline in dark brown with a thin tan line inside it, a curled corner, dashed fold lines and small spot rings; worn paper adds pale stains and deeper tears. The lines and marks may be coloured, but **the paper itself is never filled**, so it prints well. The look differs per handout but is the same on every build. **New look** gives a handout another look without touching the text. Under each sheet is its caption, "HANDOUT 1 · title".
- Three papers: **Letter** (the default for new handouts), **Worn** and **Plain**.
- Two handwriting fonts ship with the Vaesen theme: **Homemade Apple** (Apache 2.0) and **Pinyon Script** (SIL OFL). A person's handwriting is used on handouts they wrote.
- **Easy-read copies** (Adventure settings) follow each handout in the player PDF; they are off by default.
- **Handouts only** (toolbar or View menu) shows exactly what the players will get in the preview. The **Handouts** tab lists them in order.

**Also new**
- Each change in the codex, a map or the chart is **one undo step** (Edit → Undo).
- An adventure language module can replace the printed words (9.6.6). None is bundled; the setting arrives with the document language in M4.

## What M2 added

Everything M1 did, plus:

**Writing (F4, F8.3)**
- **Every element** from section 11, all in the core element kit and turned on by the Vaesen game system: scene, read-aloud, Information, person, creature (with Vaesen's Might, Body Control, Magic, Manipulation and Fear), countdown with its steps, dice (in a sentence or as a rule of their own), check and handout.
- **Hybrid mode**: the formatted text, with the source of the block under the cursor in an editable box below it (F4.1).
- **Right-click → Convert to and Insert after** (F4.2). A pasted line becomes a scene, read-aloud, Information, person or act heading in one undoable step; a scene takes in everything up to the next scene.
- **Insert menu** with act headings, every element, tables, images and layout markers, with shortcuts. Ctrl+D asks whether you want dice or a check (F4.4).
- **Tables**: Tab moves between cells, Tab in the last cell adds a row, and cells pasted from a spreadsheet fill the table. The header row repeats on every page (F4.5).
- **Images**: drag a picture into the editor, or Insert → Image…; it is copied into the adventure (F4.6).
- **Find and replace** across the whole adventure (F4.7). Link names are never changed.
- **Spell check** in Swedish and English (British and American), with suggestions on right-click (F4.8).
- **Outline** with acts and scenes: drag them to reorder (F4.9).
- **Moving blocks**: the "::" grip handle (drag), ↑ and ↓, and Alt+↑ / Alt+↓. Each move is one undo step and only goes where it is allowed (F4.13).
- Pasting text of several lines gives one paragraph per line straight away.

**Safety (F2)**
- Several adventures open at the same time, in tabs (F2.2).
- An adventure already open in another window opens **read-only** there; Save as still works (F2.3).
- Open and save an **unpacked folder**, for authors who use Git; only changed files are rewritten (F2.4).
- A **recovery copy** at each pause in typing; after a crash the next start offers to restore it (F2.5, F2.8).
- A **snapshot** every 15 minutes while there are changes; File → Revert to previous version (F2.6, F2.7).
- **Protected mode** when a module is missing: nothing is changed and export is switched off (F2.9).
- Adventures cannot reach files outside themselves (F2.10). Crash logs stay on this computer (F2.11).

**Print and settings**
- A **title page** from the adventure's details (F7.9), and act headings that share their first scene's page (F7.4).
- **Adventure → Adventure settings…**: title-page fields, page size, orientation and columns, each showing where its value comes from. Page setup is no longer in the toolbar (F7.3).
- **Editing on the page**: click an element in the preview to edit it in a popover (F12 stage 1).
- **Font guard**: Adventure → Add font… accepts only fonts under an open licence and stores the licence with them (F11).

## Running it

### On Linux, for testers: the kit

`Scriptorum-0.5.1-linux.tar.gz` installs the app for one user, in a private virtual environment, with a menu entry and the sample adventures. Unpack it and run `./setup.sh`; see `linux-kit/README-LINUX.txt`. Build the kit with `python tools/make_linux_kit.py [output-folder]`.

### From this folder

Requirements: Python 3.11–3.13 (not 3.14 or newer), and Linux, macOS 12 or newer, or Windows 10 or newer.

Install the pinned dependencies:

```
pip install "PySide6==6.8.3" "typst==0.15.0" "spylls==0.1.7" "cryptography==48.0.1"
```

Start Scriptorum:

```
python -m scriptorum
```

Or open an adventure directly:

```
python -m scriptorum path/to/adventure.scav
```

Scriptorum keeps its own data (the module library, recent files, recovery copies, snapshots, crash logs, build scratch space) in one folder per user:

| Platform | Folder |
|---|---|
| Linux | `~/.local/share/scriptorum` |
| macOS | `~/Library/Application Support/Scriptorum` |
| Windows | `%APPDATA%\Scriptorum` |

Setting `SCRIPTORUM_HOME` overrides it. Updates installed from inside the app live there too, in `app-versions/`; setting `SCRIPTORUM_NO_UPDATES=1` makes Scriptorum run its own version and ignore them.

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
