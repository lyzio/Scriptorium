# How to write a theme

A theme decides how a printed adventure looks: its fonts, colours, frames, ornaments, page setup and handout papers. It never changes what the author wrote. Switching an adventure to another theme redraws every page at once and leaves the text, the codex and the maps untouched. This guide shows how to make your own theme without reading Scriptorum's code. You need a text editor and, for the drawings, any program that saves SVG.

## What a theme is and what it may change

Every module has one job. The game system says what an adventure may contain: which elements are turned on, the creature's stats, the dice. The theme says only how those things look. That split keeps an adventure's text free of appearance, and a theme free of rules.

A theme may change:

- the fonts and their sizes, and the colours of text, rules and fills
- the frame of every element: the secret box, read-aloud text, boxes, person cards, creature stat blocks and so on
- ornaments, bullets and the page furniture: page numbers, header and footer lines, the act headings and the title page
- the default page setup: paper, columns, margins, body font and size
- the handout papers: outline, marks, folds and ink colour
- the words the theme itself prints, such as "Page"

A theme may not:

- add, remove or rename elements or fields; that belongs to a game system
- fill a handout sheet with colour, or print marks too dark for a black-and-white printer (see Handout papers)
- reach the internet, or contain any program code other than Typst

## A general theme or one for a single game system

A general theme requires only the core element kit, `scriptorum.core`. It is offered for every game system, so it must draw every element of the core element kit, Box and Quote included. Legends and Lattes, Call of Cthulhu and Plain are general themes.

A theme for a single game system requires that game system. It is offered only for that one, and it can also draw the game system's own elements. The Vaesen theme requires the Vaesen game system.

The game system and the theme are two separate choices on the adventure settings page. When you are unsure, make a general theme: more adventures can use it.

## Start from a copy

The quickest way to a good theme is to copy one that already works and change it. Every bundled module is in your module library folder:

- Linux: `~/.local/share/scriptorum/modules`
- macOS: `~/Library/Application Support/Scriptorum/modules`
- Windows: `%APPDATA%\Scriptorum\modules`

Inside it, each module has a folder named after its id, with one folder per version. Copy `scriptorum.plain/1.0.0` somewhere of your own, for example to a folder named `yourname.harbour-ink`. Plain is the best start: it has the fewest decorations, so you add what you want instead of removing what you don't.

## The folder

A theme is a folder with these parts:

```
module.json            the manifest: id, name, version, licence, what it requires
LICENSE.txt            the theme's licence and its attribution
page.json              the default page setup
settings.json          the values the visual theme editor may change
handouts.json          the handout papers
labels/en.json         words the theme itself prints
templates/             one Typst template per element kind, plus the shared files
fonts/                 the fonts, each with its licence file
ornaments/             SVG drawings: frames, curls, bullets
vendor/                Typst packages copied in, each with its licence file
```

Only these kinds of file are allowed: JSON, Typst (`.typ`), SVG and PNG images, fonts (OTF, TTF, WOFF2) and plain-text licence files. A theme with any other file is refused when it is installed.

## The manifest

`module.json` describes the theme. This is the manifest of a general theme made from a copy of Plain:

```file: module.json
{
  "id": "yourname.harbour-ink",
  "kind": "theme",
  "name": "Harbour Ink",
  "version": "1.0.0",
  "format": 1,
  "app": "1.0.0",
  "licence": "GPL-3.0-or-later",
  "authors": ["Your Name"],
  "description": "Navy ink on white with a sea-green accent, built from Plain.",
  "requires": [{"id": "scriptorum.core", "version": "1.x"}]
}
```

- `id` is permanent: your own prefix, a dot and a name, in lower-case letters, digits and hyphens. The prefix `scriptorum` is reserved for the modules that come with the app.
- `name` is what the adventure settings page shows. `description` is one or two sentences.
- `version` is MAJOR.MINOR.PATCH. Raise PATCH for a fix, MINOR when you add something, and MAJOR only when an adventure could look broken after the change. Adventures pin the exact version they use.
- `format` is 1, and `app` is the lowest Scriptorum version that can load the theme: 1.0.0.
- `licence` is the SPDX name of your licence, such as `GPL-3.0-or-later`, `CC-BY-4.0` or `MIT`.
- `requires` names the core element kit for a general theme, or a game system with its version range, such as `{"id": "scriptorum.free-league-vaesen", "version": "1.x"}`, for a theme of that game.

When you copy Plain, remove its line `"standard": true`. It is how the New adventure dialog knows to offer the bundled Plain theme first.

## The templates

The `templates/` folder holds one Typst file per element kind, named after the element: `scene.typ`, `read-aloud.typ`, `information.typ` and so on. Each file defines one function, `render`, that receives what the author filled in and draws it.

```
#let render(f, body, labels) = ...
```

- `f` holds the element's fields, already checked by the game system. A field the author left empty is `none`.
- `body` is the author's text inside the element, ready to place, or `none` for an element without a body.
- `labels` holds the printed words. Look a word up with `label(labels, "print.read-aloud")` instead of writing it in the template, so an adventure in another language prints it in that language.

What each template receives in `f`:

- `scene.typ`: `title`, `location`, `present` (the people, joined with commas), `type` (such as "Climax") and `new-page`
- `read-aloud.typ`, `pacing.typ`: nothing; only `body`
- `information.typ`: `variant` (secret, public or hint) and `fill` (grey or beige, the secret box fill chosen on the adventure settings page), and `clue` when the Information shows a clue from the codex: the clue's name, to print with a small clue mark before the text. The text it receives is then the clue's description.
- `person.typ`: `name`, `mood`, `description`, `portrait`, `portrait-description` and `linked-to`, and `known` on a card from the codex. `how-to-play` is there only when the author filled it in: print it right under the mood, with a small How to play label. `clues` is a function to call inside `context`; it gives the clues connected to the person, each with `title`, `target` and `page`, for a Clues line; print nothing when it gives none. `portrait` is the path of the person's picture, or `none`. Print it at about a third of the card's width in the card's top-right corner, never cropped, with `portrait-description` as its `alt` text; you may change its size and frame, but never leave it out. A card without a portrait should look as it always did.
- `creature.typ`: `name`, `type`, `description`, `stats` (a list, each with `id`, `label` and `value`) and `sections` (each with `id`, `label` and `body`). The game system decides which stats and sections there are; the theme only draws them.
- `box.typ`: `title`. `quote.typ`: `look`, `title`, `signature`, `description`, `handwriting` and `hand-size`
- `countdown.typ`: `title`. `countdown-step.typ`: `when`, `go-to` and `pointer`
- `dice.typ`: `count`, `sides`, `face`, `success`, `notation` and `inline`. `check.typ`: `roll` and `difficulty`
- `handout.typ`: `title`, `written-by`, `handwriting`, `hand-size`, `paper`, `tilt`, `image`, `number`, `seed` and `style`. The style is `gm` in the adventure PDF, `player` in the player PDF and `easy` for an easy-read copy. When the author ticks Only as handout, the adventure PDF gets the style `give-out` and no body: print one short line, such as "Give out Handout 1 · title", with the words from `label(labels, "print.give-out")`.
- `map.typ`: `title`, `image`, `description`, `aspect`, `layers`, `handout` and `number`. Give the picture the description as its `alt` text, so screen readers can read it. Each layer holds `items`: a `pin` has `x`, `y`, its `number` and, when it has them, `title` (its codex entry's name), `text` and `note`; print the number on the pin and list the pins in a key beside or under the map. A `line` has `points` (already placed on its pins when it joins two), `style` (`dashed`, or none for solid) and `text`, its label. `label`, `area` and `note` items are as before.
- `relationship-chart.typ`: `nodes` and `edges`. `codex-card.typ`: `title`, `type`, `type-name` and `fields`
- `contents.typ`, `end-clues.typ`, `end-index.typ`: `items`, a list of lines to print
- `title-page.typ` is the one exception: `render(f, labels)` receives `header`, `title`, `subtitle`, `author`, `description` and `extra`, and no body.

Besides the element templates, three shared files hold the rest:

- `_page.typ` sets up the page. Its function `setup(cfg, labels, doc)` receives the page setup in `cfg` (the theme's `page.json`, changed by anything the author set on the adventure settings page), and draws the header, the footer, the page numbers and the act headings.
- `_generic.typ` draws any element the theme has no template for, in a plain frame. Keep it: a game system may have elements you have never heard of. When it is used, the warnings panel says which element was drawn in the plain frame.
- `_style.typ` is where every template gets its colours, fonts, sizes and frames from. The bundled themes share their element templates and differ mainly in this file.

Two headings must stay real headings with their labels, because the PDF bookmarks, the table of contents and screen readers find them that way. `title-page.typ` draws the title as a level-1 heading labelled `<scriptorum-title-heading>`, and `scene.typ` draws the scene title as a level-2 heading labelled `<scriptorum-scene-heading>`. Change how they look with a `show heading` rule, as the bundled templates do, but keep the heading and its label.

```
{
  show heading: it => scene-title(it.body)
  [#heading(level: 2, outlined: false, bookmarked: true,
    f.title)<scriptorum-scene-heading>]
}
```

## Your first change: colours and one template

Open `templates/_style.typ` of your copy. Near the top are the colours. Change the ink to a navy and the accent, used for rules, frames and headings, to a sea green:

```
#let ink = rgb("#1F2A44")
#let accent = rgb("#2F6F6A")
```

Then give read-aloud text a look of its own. Replace `templates/read-aloud.typ` with:

```file: templates/read-aloud.typ
// Read-aloud text: a coloured rule at the left, the printed word
// "Read aloud" in small capitals, and the text in italics.

#import "_style.typ": accent, label, caps-label

#let render(f, body, labels) = block(
  width: 100%, breakable: false, above: 1em, below: 1em,
  inset: (left: 10pt, y: 4pt),
  stroke: (left: 1.5pt + accent),
  {
    caps-label(label(labels, "print.read-aloud"))
    parbreak()
    text(style: "italic", body)
  },
)
```

Install the theme (see Testing your theme), open an adventure, choose Harbour Ink on the adventure settings page, and the preview shows the new look at once.

## Page setup and settings.json

`page.json` holds the default page setup. The author can change paper, orientation, columns, margins, header, footer and page numbers for one adventure on its settings page; the rest comes only from the theme.

```
{
  "paper": "a4",
  "columns": 2,
  "column_gap_mm": 7,
  "margin_mm": {"top": 18, "bottom": 22, "x": 17},
  "font": "Libre Baskerville",
  "font_size_pt": 9.5,
  "page_numbers": true
}
```

- `paper` is `a4`, `a5` or `us-letter`. `columns` is 1, 2 or 3.
- `margin_mm` has `top`, `bottom` and `x` for the same margin on both sides, or `inside` and `outside` instead of `x` for a book whose pages face each other.
- Keep each column at least 45 mm wide; the adventure settings page warns when a column is narrower.

`settings.json` lists the values the visual theme editor will let an author change, such as a colour or a font size. Until your theme offers any, keep it as `{"settings": []}`.

## Spacing

A theme sets its spacing once, at the top of `_style.typ`, and every template uses those values. Change spacing there, and cards, boxes, read-aloud text and lists change together.

```
#let spacing = (small: 3pt, medium: 6pt, large: 10pt, leading: 0.8em,
  paragraph: 1.2em, in-frame: 10pt, label: 0.5em)
```

- `small`, `medium` and `large` are the spacing scale, used between the parts of a card: a small gap after a person's name and mood, a medium gap before What they know.
- `leading` is the line spacing, in running text and inside cards and boxes alike. `paragraph` is the space between paragraphs in running text, and `in-frame` the same inside a frame.
- `label` is the tighter line spacing of one-line labels such as "WHAT THEY KNOW".

`_page.typ` uses `leading` and `paragraph` for running text, which stays justified. Inside cards, boxes and other frames, wrap the text in `frame-par(...)`: it keeps the same line spacing and sets the text left-aligned, so no wide gaps open between words in a narrow frame. `gap(spacing.small)` is one line's spacing plus a small step, for the space between two parts of a card.

Sub-headings inside a scene (Sub-heading 1, 2 and 3, which are heading levels 3, 4 and 5) are drawn by `sub-heading-style(level, body)` in `_style.typ`, with the space above and below each in `sub-heading-space`. Keep them smaller than a scene's title. `_page.typ` draws each as a real heading in a block with `sticky: true`, so it is never left alone at the foot of a page or column; keep it a real heading, so it stays a bookmark and a heading for screen readers.

## Fonts

Put every font file in `fonts/`, with its licence file beside it, for example `Lora-Regular.ttf` and `Lora-OFL.txt`. Scriptorum's font guard accepts only fonts that may be shared, under the SIL Open Font Licence or the Apache Licence, and it checks the licence written inside the font file itself. A font under any other licence is refused, so a theme can be passed on without passing on a commercial font by accident.

- Use static weights: one file each for regular, bold, italic and bold italic. Typst does not use the weights of a variable font.
- Check that the font has the letters your readers need, such as å, ä and ö.
- Name the font in `_style.typ` by its family name, the name its makers gave it, not the file name.
- The six handwriting hands live in the core element kit, so every theme offers them. Don't copy them into your theme.

## Ornaments as SVG

Frames, curls, bullets and other decoration are SVG drawings in `ornaments/`. Draw them yourself, or use drawings whose licence lets you share them, and never copy or trace a publisher's artwork.

Place an ornament through the `ornament` helper in `_style.typ`. It marks the drawing as decoration, so screen readers skip it and the accessible PDF stays clean:

```
ornament("cup.svg", width: 10pt)
```

Keep drawings simple, a few kilobytes each, in colours that still read in black and white.

## Handout papers

`handouts.json` lists the papers a handout can be printed on. The handout's Paper field offers them by their labels.

```
{
  "papers": [
    {
      "id": "letter",
      "label": "paper.letter",
      "outline": "#5A4632",
      "inner": "#C9AE84",
      "edge_mm": 1.3,
      "folds": [1, 2],
      "marks": {"colour": "#C9AE84", "spots": [2, 4],
                "stains": [0, 0], "tears": [0, 0]},
      "ink": "#2A3550"
    }
  ]
}
```

- `outline` and `inner` are the colours of the torn edge and the thin line just inside it. `edge_mm` is how uneven the edge is.
- `folds` and the numbers under `marks` are ranges, from fewest to most. Each handout picks its own number from its id, so it looks the same on every build.
- `ink` is the colour of the handwriting. `label` is a key in `labels/en.json`, such as `"paper.letter": "Letter paper"`.
- Paper styles may also use `corner` (`round`), `edge` (`soft`), `ruled` lines with a `colour` and `gap_mm`, and more marks such as `rings` or `hatch`. Legends and Lattes' recipe card and Call of Cthulhu's telegram show them.

The print-friendly rules. A handout is handed to players and printed on any printer, so:

- the paper is never filled with a colour; the sheet stays white
- the outline, the inner line, the folds, the marks and the ink may be coloured
- stains and marks stay pale: an `opacity` of at most 0.2

A paper that breaks these rules still prints, but the warnings panel says which paper and why.

## Labels

`labels/en.json` holds the words the theme itself prints, such as `"print.page": "Page"`, and the names of its papers. Words of the elements, such as "Read aloud" or "Secret", come from the core element kit and the game system; a theme can override one of them by giving the same key. When an adventure is written in another language, an adventure-language module replaces these words, so never write a printed word straight into a template.

## Licence and attribution

Put a `LICENSE.txt` in the theme's folder. Say who made the theme, under which licence it may be shared, and where its fonts, drawings and copied Typst packages come from, each with its own licence.

When a theme is named after someone else's game, book or world, say plainly that it is unofficial. Put the same sentence in the manifest's `description` and in `LICENSE.txt`:

```
An unofficial, fan-made look, not affiliated with or endorsed
by the owners of the work or game it is named after.
```

Use no text, artwork or logos from the publisher. A theme captures a mood with your own drawings and open-licence fonts, as Legends and Lattes and Call of Cthulhu do.

## Worked examples: Legends and Lattes and Call of Cthulhu

Both are general themes, made from the same element templates as the Vaesen theme. Open their folders in your module library beside this guide.

Legends and Lattes is cozy fantasy:

- `_style.typ` sets coffee brown and cream with a sage green accent, Fraunces headings, Lora text and Nunito labels.
- `ornaments/` holds steaming coffee cups for the act headings, coffee beans for bullets and a leaf sprig for the frame corners.
- `handouts.json` has a recipe card with ruled lines and a café napkin, now and then with a pale ring stain.
- `labels/en.json` names the two papers; `LICENSE.txt` and the description carry the unofficial notice.

Call of Cthulhu is 1920s cosmic horror:

- `_style.typ` sets ink black and sepia with one sickly-green accent, IM Fell English headings, EB Garamond text and Special Elite typewriter labels.
- `ornaments/` holds an occult sigil, corner brackets for the frames and small green diamond bullets.
- `handouts.json` has a telegram and a torn notebook page; the Typewriter hand suits it.
- Special Elite is under the Apache Licence and the other fonts under the SIL OFL, each with its licence file in `fonts/`.

What they share tells you where to work: the element templates are the same, and the look lives in `_style.typ`, the fonts, the ornaments, the papers and the page setup.

## Testing your theme

Install it through the module manager. Pack the theme's folder as a `.scmod` file, as the next section shows, then choose File ▸ Settings… ▸ Modules ▸ Install module… and pick the file. Scriptorum checks the manifest, the file types, the fonts and the required modules, and builds the theme with a test adventure. When a check fails it says why, and nothing is installed. There is no need to restart.

Changed something? One version number stands for one content, because adventures use exact versions. Either raise the version in `module.json` (1.0.0 to 1.0.1) and install again, or remove the old one in Settings ▸ Modules first. Both versions can stay installed side by side.

Then check it:

- Help ▸ Check installation ▸ Run the theme self-test builds a test adventure with every theme and every game system it is offered for, and names any theme that fails.
- Help ▸ Open the example adventure, and choose your theme on the adventure settings page. Jätten Finns skuld uses nearly every element.
- Look at the warnings panel after each build. It names any element drawn in the plain frame, papers that break the handout rules, and, after an export, any font that could not be embedded in the PDF.
- Export the adventure PDF and the handouts PDF, and print a page or two on a black-and-white printer.
- Export the accessible PDF too, and check that your headings and pictures still pass.

## Packing it as a .scmod file to share

A `.scmod` file is a zip archive of the theme's folder, with `module.json` at the top of the archive, not inside another folder.

On Linux or macOS, in a terminal, from inside the theme's folder:

```
zip -r ../yourname.harbour-ink-1.0.0.scmod .
```

On Windows, open the theme's folder, select everything in it, choose Send to ▸ Compressed (zipped) folder, and rename the file to end in `.scmod`.

Once it is installed, Settings ▸ Modules ▸ Save as .scmod file… writes the same file again whenever you need it.

Whoever receives it installs it with File ▸ Settings… ▸ Modules ▸ Install module…. Scriptorum checks the manifest, the file types, the fonts and the required modules, and compiles the theme against a test adventure before it accepts it. An adventure never carries its modules: send the `.scav` file together with the `.scmod` files of every module it uses that did not come with Scriptorum. Opened without them, the adventure lists the modules it needs.
