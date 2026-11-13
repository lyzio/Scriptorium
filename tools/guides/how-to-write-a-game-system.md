# How to write a game system

A game system tells Scriptorum what an adventure for one game may contain: which elements the author can insert, what a creature's stat block shows, how dice are written, and which kinds of codex entry there are. It says nothing about appearance; that is the theme's job. This guide shows how to make a game system for your own game without reading Scriptorum's code. Its example is a small made-up game, Harbour Tales, built step by step, and its worked example from the app is the Vaesen game system.

## What a game system is

Scriptorum keeps three things apart:

- The core element kit, `scriptorum.core`, holds every element an adventure can use, whatever the game: scenes, read-aloud text, Information, person cards, creatures, countdowns, dice, checks, handouts, boxes, quotes, maps and more. It also holds the codex types Person, Place and Clue.
- A game system turns on the elements of the core element kit its game needs, fills in what is particular to the game (the creature's stats, the dice), and may add elements and codex types of its own.
- A theme draws all of it.

So most of a game system is a handful of small JSON files. You write Typst only for elements of your own.

## Start from a copy

Every bundled module is in your module library folder:

- Linux: `~/.local/share/scriptorum/modules`
- macOS: `~/Library/Application Support/Scriptorum/modules`
- Windows: `%APPDATA%\Scriptorum\modules`

Each module has a folder named after its id, with one folder per version. Read `scriptorum.free-league-vaesen/1.0.0` (Vaesen) and `scriptorum.plain-system/1.0.0` (Plain) beside this guide. The core element kit, `scriptorum.core/1.0.0`, has the full definition of every element in its `elements/` folder: the best reference when you write your own.

## The folder

```
module.json                 the manifest
LICENSE.txt                 the licence
elements.json               which elements of the core element kit are turned on
stat-blocks/creature.json   the creature's stats and sections
notation.json               how dice and checks are written
codex-types/<id>.json       codex types of its own, one file each
elements/<id>.json          elements of its own, one file each
typst/elements.typ          the Typst functions of its own elements
labels/en.json              names in the editor and English words printed in the PDF
```

Only `module.json` is required; leave out what your game does not need. Only JSON, Typst, SVG and PNG images, fonts and plain-text licence files are allowed.

## The manifest

```file: module.json
{
  "id": "yourname.harbour-tales",
  "kind": "game-system",
  "name": "Harbour Tales",
  "version": "1.0.0",
  "format": 1,
  "app": "1.0.0",
  "licence": "CC-BY-4.0",
  "authors": ["Your Name"],
  "description": "Harbour Tales: a d10 pool, ships in the codex, and rumours.",
  "requires": [{"id": "scriptorum.core", "version": "1.x"}]
}
```

- `id` is permanent: your own prefix, a dot and a name, in lower-case letters, digits and hyphens. The prefix `scriptorum` is reserved for the modules that come with the app.
- `version` is MAJOR.MINOR.PATCH. Adventures pin the exact version. Raise MAJOR only when an adventure would break: an element removed or a field renamed. Adding an element or a stat is MINOR, a fix is PATCH.
- `format` is 1, and `app` is the lowest Scriptorum version that can load it: 1.0.0.
- `requires` names the core element kit.

## Turning on elements

`elements.json` lists the elements of the core element kit your game uses. Only these appear in the editor's Insert menu and toolbar. The layout markers, the table of contents, the footnote and the handout marker are always on.

```file: elements.json
{
  "on": [
    "scene", "read-aloud", "information", "person", "creature",
    "dice", "check", "handout", "box", "mention", "see"
  ]
}
```

The ids are the names of the files in the core element kit's `elements/` folder. Vaesen turns on all eighteen; Plain turns on every one as well. Without an `elements.json`, every element is on.

## The creature stat block

`stat-blocks/creature.json` decides what a creature's stat block shows. The theme draws it, but the stats come from here.

```file: stat-blocks/creature.json
{
  "element": "creature",
  "stats": [
    {"id": "brawn", "label": "stat.brawn", "min": 1, "max": 5},
    {"id": "wits", "label": "stat.wits", "min": 1, "max": 5},
    {"id": "dread", "label": "stat.dread", "min": 0, "max": 10}
  ],
  "sections": ["attacks", "weaknesses"]
}
```

- Each stat has an `id`, a `label` key in `labels/en.json`, and the lowest and highest value. The editor offers a number field for each, and a value outside the range is reported on the author's line.
- `sections` picks the creature's text sections, in order, from: `skills`, `magic-powers`, `attacks`, `weaknesses`, `conditions` and `banishment`.
- A game with no fixed stats writes `"stats": []` and `"free_stats": true`, as Plain does. The author then types name-and-value lines such as "Strength 3".

The author writes a creature like this, and the editor fills in the same for them:

```
#creature(name: "The deep one", brawn: 4, wits: 2, dread: 6,
  attacks: [A grip like a winch.])
```

## Dice and checks

`notation.json` says how dice are written in your game.

```file: notation.json
{
  "dice": ["d10"],
  "pool": true,
  "success_on": [8, 9, 10]
}
```

- `dice` lists the dice the game uses. Writing any other die is reported on the author's line.
- `pool` is true when the game rolls a handful of dice and counts successes; `success_on` lists the faces that count, so a theme can mark them.
- `modifiers: true` allows a modifier such as `2d10+1`, as in Plain.

The author writes `#dice(dice: "3d10")` in a sentence. A check names a skill or attribute in free text with an optional difficulty: `#check(roll: "Wits", difficulty: "hard")[...]`.

## Codex types of its own

The codex already knows Person, Place and Clue. Add a type of your own in `codex-types/<id>.json`:

```file: codex-types/ship.json
{
  "id": "ship",
  "name": "codex.ship",
  "icon": "place",
  "title_field": "name",
  "fields": [
    {"name": "name", "kind": "text", "required": true,
     "label": "field.codex.name"},
    {"name": "captain", "kind": "text", "required": false,
     "label": "field.ship.captain"},
    {"name": "description", "kind": "rich", "required": false,
     "label": "field.codex.description"}
  ],
  "card_element": null
}
```

- `title_field` is the field that names the entry. `name` and the field `label`s are keys in `labels/en.json`.
- `card_element` is the element that prints the entry as a full card, or `null` for a plain card.
- A type can take its fields from an element instead: Vaesen's Creature uses `"fields_from_element": "creature"` and `"card_element": "creature"`, so a creature in the codex has exactly the stats of its stat block.

## Elements of its own

When the core element kit has nothing for an idea of your game, add an element. Harbour Tales adds a Rumour: something the characters hear, who told them, and whether it is true. An element needs three things: its definition, its Typst function, and its words.

The definition, `elements/rumour.json`:

```file: elements/rumour.json
{
  "id": "rumour",
  "name": "element.rumour",
  "category": "block",
  "body": "rich",
  "fields": [
    {"name": "heard-from", "kind": "text", "required": false,
     "label": "field.rumour.heard-from"},
    {"name": "truth", "kind": "choice", "options": ["yes", "no", "partly"],
     "required": true, "default": "partly", "label": "field.rumour.truth"}
  ],
  "variants": [],
  "page_start": "never",
  "never_split": true,
  "handout": false,
  "editor": "frame",
  "shortcut": null,
  "toolbar_group": "boxes"
}
```

- `id` is used in the author's text, so it is permanent. `name` is a key in `labels/en.json`.
- `category` is `block` (a box or section), `inline` (inside a sentence), `both`, or `layout`.
- `body` is `none`, `plain`, `rich` (the author's formatted text) or `blocks` (other elements inside, as in a scene). For `blocks`, `allow` can list which elements may go inside.
- `fields`: each has a `name`, a `kind`, whether it is `required`, a `default` and a `label`. Kinds include `text`, `rich`, `number` (with `min` and `max`), `choice` (with `options`), `bool`, `codex` and `codex-list` (a link to codex entries, with the allowed `types`), `element-ref`, `image` and `dice`.
- `variants` is an optional list of looks, such as Secret, Public and Hint for Information, each with an `id` and a `label`. The theme gives each variant its colour.
- `page_start` is `always`, `never` or `when-needed`; `never_split` keeps it on one page; `handout` offers "Handout also".
- `editor` is `frame`, `form` or `chip`; `shortcut` a suggested key such as `"Ctrl+Shift+R"`; `toolbar_group` the toolbar group it joins: `structure`, `boxes`, `people`, `rules` or `handouts`.

The Typst function, in `typst/elements.typ`. Its `make` function returns one function per element of your own. Each checks the author's fields and hands them to the theme's renderer for that element, `r.<id>`, with the body and the printed words:

```file: typst/elements.typ
// Harbour Tales: the element functions of its own element kinds.
// Each function checks its fields and hands them to the theme's renderer.

#let make(r, labels, game: (:)) = (
  rumour: (heard-from: none, truth: "partly", ..args) => {
    if truth not in ("yes", "no", "partly") {
      panic("SCRIPTORUM:range:rumour:truth")
    }
    let body = args.pos().at(0, default: none)
    (r.rumour)((heard-from: heard-from, truth: truth), body, labels)
  },
)
```

A check that fails stops the build with `panic("SCRIPTORUM:<problem>:<element>:<field>")`. Scriptorum turns it into a plain message on the author's line. The problems are `required` (a required field is empty), `range` (a value outside what is allowed), `field` (a field that does not exist), `variant` (an unknown variant) and `dice` (a die the game does not use). Never draw anything here: the function decides what is valid, and the theme decides how it looks.

The author writes:

```adventure
#scene(title: "The quay")[
The fishermen are mending nets.

#rumour(heard-from: "Old Maja", truth: "no")[The *Gull* sank with all hands.]

#creature(name: "The deep one", brawn: 4, wits: 2, dread: 6,
  attacks: [A grip like a winch.])

They roll #dice(dice: "3d10") to keep their nerve.
]
```

A theme that has no template for your element draws it in its plain frame and says so in the warnings panel. To give it a proper look, make a theme for your game with a `templates/rumour.typ`; How to write a theme explains templates. This one draws a coloured rule at the left, the word "Rumour" and who said it:

```theme: templates/rumour.typ
// Harbour Tales' Rumour: a rule at the left, the word "Rumour" and who said it.

#import "_style.typ": accent, quiet, label, blank, caps-label

#let render(f, body, labels) = block(
  width: 100%, breakable: false, inset: 8pt, above: 1em, below: 1em,
  stroke: (left: 2pt + accent),
  {
    caps-label(label(labels, "print.rumour"))
    if not blank(f.heard-from) [ #text(fill: quiet)[· #f.heard-from] ]
    parbreak()
    body
  },
)
```

## Labels and language modules

`labels/en.json` holds every word of your game system: names in the editor, and the English words printed in the PDF.

```file: labels/en.json
{
  "element.rumour": "Rumour",
  "field.rumour.heard-from": "Heard from",
  "field.rumour.truth": "Is it true?",
  "print.rumour": "Rumour",
  "stat.brawn": "Brawn",
  "stat.wits": "Wits",
  "stat.dread": "Dread",
  "codex.ship": "Ship",
  "field.ship.captain": "Captain"
}
```

- `element.<id>` and `field.<id>.<field>` are what the editor shows.
- `print.<word>` are words printed in the PDF. A template looks them up instead of writing them, so an adventure in another language prints them in that language.
- An adventure written in Swedish uses a Swedish adventure-language module, which carries a `labels/yourname.harbour-tales.json` with the same keys in Swedish. A word it lacks is printed in English, and the warnings panel says so.

The interface language, chosen in Scriptorum's settings, changes only the app's own menus and dialogs, never the printed words.

## Licence

Put a `LICENSE.txt` in the folder, and the SPDX name of the same licence in the manifest. A game system describes your rules: use only words and terms you may share. When it is for someone else's game, say in the description and in `LICENSE.txt` that it is unofficial and not affiliated with or endorsed by the game's publisher, and copy no text from the rulebook. Stat names and dice are facts of the game; the rulebook's prose is not yours to copy.

## Worked example: the Vaesen game system

Open `scriptorum.free-league-vaesen/1.0.0` in your module library:

- `elements.json` turns on every element of the core element kit.
- `stat-blocks/creature.json` sets the five attributes Might, Body Control, Magic, Manipulation and Fear, from 0 to 99, and the sections skills, magic powers, attacks, weaknesses, conditions and banishment.
- `notation.json` says Vaesen rolls a pool of d6 and a 6 is a success.
- `codex-types/creature.json` adds Creature to the codex, with its fields taken from the creature element.
- `labels/en.json` names the attributes and the codex type.
- `typst/elements.typ` returns no functions: Vaesen has no elements of its own.

That is a complete game system. Plain, in `scriptorum.plain-system/1.0.0`, is even smaller: it turns on every element, allows any die with modifiers, and lets a creature take free name-and-value lines.

## Testing

Install it through the module manager. Pack the folder as a `.scmod` file, as the next section shows, then choose File ▸ Settings… ▸ Modules ▸ Install module… and pick the file. Scriptorum checks the manifest, the file types and the required modules, and builds the game system with a test adventure. When a check fails it says why, and nothing is installed. There is no need to restart.

Changed something? One version number stands for one content, because adventures use exact versions. Either raise the version in `module.json` (1.0.0 to 1.0.1) and install again, or remove the old one in Settings ▸ Modules first.

Then:

- File ▸ New adventure… offers your game system, with every general theme.
- Insert each of your elements and fill in every field. Try a wrong value too: the message should appear on the right line.
- Write the example above into a scene and look at the preview. Your own elements are drawn in a plain frame until a theme gives them a template.
- Help ▸ Check installation ▸ Run the theme self-test builds a test adventure with every theme offered for your game system.
- Switch the theme on the adventure settings page; nothing in the text should change.

## Packing it as a .scmod file to share

A `.scmod` file is a zip archive of the module's folder, with `module.json` at the top of the archive, not inside another folder.

On Linux or macOS, in a terminal, from inside the folder:

```
zip -r ../yourname.harbour-tales-1.0.0.scmod .
```

On Windows, open the folder, select everything in it, choose Send to ▸ Compressed (zipped) folder, and rename the file to end in `.scmod`.

Once it is installed, Settings ▸ Modules ▸ Save as .scmod file… writes the same file again whenever you need it.

Whoever receives it installs it with File ▸ Settings… ▸ Modules ▸ Install module…. If you also made a theme for it, share both: the theme names your game system in its `requires`, so it is offered only for it. An adventure never carries its modules: send the `.scav` file together with the `.scmod` files it needs. Opened without them, the adventure lists the modules it needs.
