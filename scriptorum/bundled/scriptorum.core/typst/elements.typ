// Core element kit (design document 9.3 and section 11, amended 5 Nov 2026).
//
// Every element kind lives here, for any game system. A game system turns on
// the ones it needs (elements.json); the build assembler only exposes those.
// Each function checks the element's fields and hands them, with the body,
// to the theme's renderer for that kind (9.6). Appearance lives only in the
// theme; pagination rules (F7.4) and numbering live here, so they are the
// same whatever the theme.
//
// Problems are raised as "SCRIPTORUM:<problem>:<element>:<field>" so the app
// can explain them in the interface language (F15).
//
// `game` carries the game system's data: its stat blocks (11.5) and its dice
// notation (11.7). `world` (Milestone 3) carries the codex entries and types,
// the maps, the relationship chart and whether this is the adventure PDF or the
// player PDF (F3, F5, F6), written by the build assembler as /world.json.

#let _blank(value) = value == none or value == "" or value == [] or value == ()

#let _required(element, field, value) = {
  if _blank(value) {
    panic("SCRIPTORUM:required:" + element + ":" + field)
  }
}

#let _variants = ("secret", "public", "hint")

// F7.4: true between an act heading and its first scene, so that scene
// shares the act heading's page instead of starting another one.
#let act-open = state("scriptorum-act-open", false)

// F7.4 (M5): Typst cannot start a page inside a frame, so a frame switches
// off page and column breaks (and their "Show breaks" marks) inside it.
#let _framed(body) = {
  show pagebreak: none
  show colbreak: none
  show <scriptorum-break-mark>: none
  body
}

// 11.1: scenes are numbered automatically.
#let scene-counter = counter("scriptorum-scene")
// The title of the scene being laid out, for "appears in" lists (F3.10).
#let scene-current = state("scriptorum-scene-title", none)
// F6.2: handouts are numbered #1, #2 ... in adventure order. The player PDF
// holds the same handouts in the same order, so the numbers match.
#let handout-counter = counter("scriptorum-handout")
// F3.4: the codex card being laid out, so Information written inside it is
// known by that entry automatically (11.3).
#let card-open = state("scriptorum-card-open", none)
// F3 (M6 part C4): a loose person card being laid out, by its number and
// name, so a clue written inside it is listed on its Clues line and in the
// clue overview.
#let person-counter = counter("scriptorum-person")
#let loose-open = state("scriptorum-loose-person", none)

// F12 stage 1: an invisible mark with the element's kind and its position on
// the page, so a click on a preview page can be traced to its element.
#let _mark(kind) = context [#metadata((k: kind, pos: here().position()))<scriptorum-el>]

// F3.6: where a codex entry is used, for backlinks, the index and the clue
// overview (F3.10).
#let _ref(id, how) = context [#metadata((id: id, how: how, page: counter(page).get().first()))<scriptorum-ref>]

#let _label(labels, key, fallback) = labels.at(key, default: fallback)

// F7.7 (M5): a scene's hidden heading carries this label; act headings do not.
#let _is-scene-heading(h) = h.has("label") and h.label == <scriptorum-scene-heading>

// Plain text of a piece of content, for the short pointers on a person card
// (11.4: "Secret: the light under the water → p. 4").
#let _plain(c) = {
  if c == none { "" } else if type(c) == str { c } else if c.has("text") {
    if type(c.text) == str { c.text } else { _plain(c.text) }
  } else if c.has("children") { (c.children.map(_plain) + ("",)).join("") } else if c.has("body") { _plain(c.body) } else if c.func() == [ ].func() { " " } else { "" }
}

#let _summary(c, limit: 60) = {
  let words = str(_plain(c)).split(regex("\s+")).filter(w => w != "")
  let out = ""
  for w in words {
    if out.len() + w.len() + 1 > limit {
      return out + " …"
    }
    out = if out == "" { w } else { out + " " + w }
  }
  out
}

// A whole number from a text, the same on every build (F6.5, F7.8).
#let _hash(s) = {
  let h = 7
  for c in str(s).codepoints() {
    h = calc.rem(h * 31 + str.to-unicode(c), 2147483647)
  }
  h
}

// The page a location prints on, as the page counter shows it.
#let _page-of(loc) = counter(page).at(loc).first()

// F6.7, F8 (M4): the six handwriting hands live in this kit, so every theme
// offers them. Each has its own size so the hands read alike; a hand the
// author added to the adventure (F11) is set at 13 pt.
#let _hands = json("../handwriting.json").hands
#let _hand-size(family) = {
  let found = _hands.filter(h => h.family == family)
  if found.len() == 0 { 13pt } else { found.first().size_pt * 1pt }
}

// F6.5, 11.11: a tilt is a whole number of degrees from -5 to +5.
#let _tilt(element, value) = {
  if value == none { return 0 }
  if type(value) != int or value < -5 or value > 5 { panic("SCRIPTORUM:range:" + element + ":tilt") }
  value
}

#let make(r, labels, game: (:), world: (:)) = {
  let notation = game.at("notation", default: (:))
  let stat-blocks = game.at("stat-blocks", default: (:))
  let entries = world.at("entries", default: (:))
  let types = world.at("types", default: (:))
  let maps = world.at("maps", default: (:))
  let player = world.at("mode", default: "gm") == "player"
  let easy-read = world.at("easy_read", default: false)
  // F7.3 (M4): the fill of the secret box, chosen once per adventure.
  let secret-fill = world.at("secret_fill", default: "grey")
  // F7.4 (M5): page-start rules per element kind, compact mode already
  // applied by the core, and "Show breaks" (preview only, F7.2).
  let layout = world.at("layout", default: (:))
  let page-start = layout.at("page_start", default: (:))
  let show-breaks = layout.at("show_breaks", default: false)
  let break-mark(key, fallback) = if show-breaks {
    [#place(right, dx: 2mm, box(fill: rgb("#B03060").transparentize(86%), inset: (x: 3pt, y: 1.5pt), radius: 2pt,
      text(size: 6.5pt, fill: rgb("#B03060"), style: "normal", weight: "regular", tracking: 0pt, _label(labels, key, fallback))))<scriptorum-break-mark>]
  }
  // A kind set to "always" starts a new page (not inside a frame, _framed).
  let start(kind) = if page-start.at(kind, default: "") == "always" {
    break-mark("print.break.start", "new page")
    pagebreak(weak: true)
  }

  let entry-title(id) = {
    let e = entries.at(str(id), default: none)
    if e == none { "?" } else { e.title }
  }

  // A link to the first codex card of an entry, when it has one.
  let card-target(id) = {
    let found = query(label("scriptorum-card-" + str(id)))
    if found.len() == 0 { none } else { found.first().location() }
  }

  let name-of(id) = context {
    let target = card-target(id)
    if target == none { entry-title(id) } else { link(target, entry-title(id)) }
  }

  // F3.4 a mention prints the entry's name inline.
  let mention(entry: none) = {
    _required("mention", "entry", entry)
    _mark("mention")
    _ref(entry, "mention")
    name-of(entry)
  }

  // F3.4 a "see page" line points to where the entry is described.
  let see(entry: none) = {
    _required("see", "entry", entry)
    _mark("see")
    _ref(entry, "see")
    context {
      let target = card-target(entry)
      if target == none { entry-title(entry) } else {
        link(target)[#entry-title(entry) #_label(labels, "print.see-page", "→ p. {page}").replace("{page}", str(_page-of(target)))]
      }
    }
  }

  // 11.7 Dice: inline in a sentence, or a block with the rule it belongs to.
  let dice(dice: "D6", face: none, ..args) = {
    let body = args.pos().at(0, default: none)
    // F8 Plain game system: its notation.json allows a modifier, as in 2d10+1.
    let m = str(dice).match(regex("^(\d*)[Dd](\d+)([+\-−]\d+)?$"))
    if m == none { panic("SCRIPTORUM:dice:dice:dice") }
    let modifier = m.captures.at(2)
    if modifier != none and not notation.at("modifiers", default: false) { panic("SCRIPTORUM:dice:dice:dice") }
    let count = if m.captures.at(0) == "" { 1 } else { int(m.captures.at(0)) }
    let sides = int(m.captures.at(1))
    let allowed = notation.at("dice", default: ("d6",))
    if ("d" + str(sides)) not in allowed { panic("SCRIPTORUM:dice:dice:dice") }
    if face != none and (type(face) != int or face < 1 or face > sides) {
      panic("SCRIPTORUM:range:dice:face")
    }
    let text = (if count > 1 { str(count) } else { "" }) + _label(labels, "print.dice.d", "D") + str(sides) + (if modifier != none { modifier } else { "" })
    _mark("dice")
    (r.dice)(
      (
        count: count,
        sides: sides,
        face: face,
        success: notation.at("success_on", default: ()),
        notation: text,
        inline: body == none,
      ),
      body,
      labels,
    )
  }

  // Rich text stored in a codex entry is Typst markup like the chapters
  // (D11); it may hold mentions and dice.
  let rich(value) = if _blank(value) { none } else {
    eval(str(value), mode: "markup", scope: (mention: mention, see: see, dice: dice))
  }

  // 11.1 Scene: works like a chapter; its body holds the scene's content.
  // From M3 the location and the people present are codex entries (F3.5);
  // text written in M2 still prints as text (F3.12).
  let scene(title: none, location: none, present: none, place: none, people: (), type: none, id: none, new-page: true, ..args) = {
    _required("scene", "title", title)
    let body = args.pos().at(0, default: [])
    // F7.4: a scene starts a new page unless switched off, or unless it is
    // the first scene after an act heading. Its rule can be changed on the
    // settings page, and compact mode turns it off (M5).
    let rule = page-start.at("scene", default: "always")
    context {
      if new-page != false and rule == "always" and not act-open.get() { break-mark("print.break.start", "new page"); pagebreak(weak: true) }
    }
    act-open.update(false)
    scene-counter.step()
    scene-current.update(title)
    _mark("scene")
    // F7.7, F17 (M5): the theme draws the scene's title as a level-2 heading
    // labelled <scriptorum-scene-heading>: a bookmark, a contents line and a
    // heading for screen readers (templates/scene.typ).
    // 9.4 element reference: a scene with an ID can be pointed to (11.6).
    if not _blank(id) {
      [#metadata((title: title, id: id))#label("scriptorum-scene-" + id)]
    }
    let where = if not _blank(place) { _ref(place, "scene.place"); name-of(place) } else { location }
    let present-list = (people.map(p => { _ref(p, "scene.people"); name-of(p) }) + if _blank(present) { () } else { (present,) })
    (r.scene)(
      (
        title: title,
        location: where,
        present: if present-list.len() == 0 { none } else { present-list.join(", ") },
        // 11.1 (M4): a word such as "Climax", printed beside the scene number.
        type: if _blank(type) { none } else { type },
        new-page: new-page,
      ),
      body,
      labels,
    )
  }

  // 11.2 Read-aloud: free text only.
  let read-aloud(..args) = {
    let body = args.pos().at(0, default: [])
    _mark("read-aloud")
    (r.read-aloud)((:), body, labels)
  }

  // 11.3 Information: Secret (default), Public or Hint. It can be linked to
  // the people who know it; inside a codex card it is known by that entry.
  // F3 (M6 part C4): with a Clue it prints the clue's description, so the
  // text is written once, with a small clue mark and the clue's name.
  let information(variant: "secret", known-by: (), clue: none, ..args) = {
    if variant not in _variants {
      panic("SCRIPTORUM:variant:information:" + str(variant))
    }
    let body = args.pos().at(0, default: [])
    let found = if _blank(clue) { none } else { entries.at(str(clue), default: none) }
    let text = if found != none and not _blank(found.fields.at("description", default: none)) {
      rich(found.fields.description)
    } else { body }
    _mark("information")
    for k in known-by { _ref(k, "information.known-by") }
    if not _blank(clue) { _ref(clue, "information.clue") }
    context [#metadata((known-by: known-by, inside: card-open.get(), loose: loose-open.get(), variant: variant,
      summary: _summary(text), clue: if _blank(clue) { none } else { str(clue) },
      clue-title: if _blank(clue) { none } else { entry-title(clue) }))<scriptorum-info>]
    let f = (variant: variant, fill: secret-fill)
    if not _blank(clue) { f.insert("clue", name-of(clue)) }
    (r.information)(f, text, labels)
  }

  // The short lines on a person card for Information written elsewhere and
  // known by the person (11.4, T-WORLD-03).
  let known-elsewhere(id) = query(<scriptorum-info>)
    .filter(m => str(id) in m.value.known-by and m.value.inside != str(id))
    .map(m => (variant: m.value.variant, summary: m.value.summary, page: _page-of(m.location()), target: m.location(),
      clue: m.value.at("clue-title", default: none)))

  // F3 (M6 part C4): where a clue is written in full: its first Information
  // item, or else its first codex card.
  let clue-target(id) = {
    let found = query(<scriptorum-info>).filter(m => m.value.at("clue", default: none) == str(id))
    if found.len() > 0 { found.first().location() } else { card-target(id) }
  }

  // 11.4 (M6 part C4): the Clues line of a person card: every clue connected
  // to the person, through clue Information they know (or that is written in
  // their card) or through Linked to, each once, with its page pointer.
  let clues-of(entry, linked, loose) = {
    let ids = ()
    for m in query(<scriptorum-info>) {
      let v = m.value
      let c = v.at("clue", default: none)
      if c == none { continue }
      let known = (entry != none and (str(entry) in v.known-by or v.inside == str(entry))) or (loose != none and v.at("loose", default: none) == loose)
      if known and c not in ids { ids.push(c) }
    }
    for l in linked {
      let e = entries.at(str(l), default: none)
      if e != none and e.type == "clue" and str(l) not in ids { ids.push(str(l)) }
    }
    ids.map(i => {
      let target = clue-target(i)
      (title: entry-title(i), target: target, page: if target == none { none } else { _page-of(target) })
    })
  }

  // 11.4 Person: the body holds the Information lines the person knows.
  // M6 part C: an optional portrait (JPEG or PNG) with its description for
  // screen readers (F17.3); the theme prints it in the card's corner.
  // M6 part C4: How to play, printed under Mood, and the Clues line.
  let person(name: none, mood: none, how-to-play: none, description: none, portrait: none, portrait-description: none, linked-to: none, links: (), ..args) = {
    _required("person", "name", name)
    let body = args.pos().at(0, default: none)
    _mark("person")
    let linked = links.map(l => { _ref(l, "person.links"); name-of(l) }) + if _blank(linked-to) { () } else { (linked-to,) }
    person-counter.step()
    context loose-open.update((number: person-counter.get().first(), name: name))
    let f = (name: name, mood: mood, description: description,
        portrait: if _blank(portrait) { none } else { portrait },
        portrait-description: portrait-description,
        linked-to: if linked.len() == 0 { none } else { linked.join(", ") },
        clues: () => clues-of(none, links, loose-open.get()))
    if not _blank(how-to-play) { f.insert("how-to-play", how-to-play) }
    (r.person)(f, body, labels)
    loose-open.update(none)
  }

  // 11.5 Creature: the game system's stat block decides the stats and the
  // sections (stat-blocks/creature.json).
  let creature-fields(name, named) = {
    let block = stat-blocks.at("creature", default: (stats: (), sections: ()))
    let stat-ids = block.stats.map(s => s.id)
    let section-ids = block.at("sections", default: ())
    // F8 Plain game system: no fixed stats; the author writes free
    // name-and-value lines, one per line, such as "Strength 3".
    let free = block.at("free_stats", default: false)
    for (key, value) in named {
      if key not in ("type", "description") and key not in stat-ids and key not in section-ids and not (free and key == "stat-lines") {
        panic("SCRIPTORUM:field:creature:" + key)
      }
    }
    let stats = block.stats.map(s => {
      let value = named.at(s.id, default: none)
      if value != none and (type(value) != int or value < s.min or value > s.max) {
        panic("SCRIPTORUM:range:creature:" + s.id)
      }
      (id: s.id, label: _label(labels, s.label, s.id), value: value)
    })
    if free {
      let lines = str(named.at("stat-lines", default: "")).split(regex("[\n;]")).map(l => l.trim()).filter(l => l != "")
      stats = lines.enumerate().map(((i, l)) => {
        let m = l.match(regex("^(.*\S)\s+(\S+)$"))
        if m == none { (id: "line-" + str(i), label: l, value: "") } else { (id: "line-" + str(i), label: m.captures.at(0), value: m.captures.at(1)) }
      })
    }
    let sections = section-ids
      .filter(key => not _blank(named.at(key, default: none)))
      .map(key => (id: key, label: _label(labels, "print.creature." + key, key), body: named.at(key)))
    (
      name: name,
      type: named.at("type", default: none),
      description: named.at("description", default: none),
      stats: stats,
      sections: sections,
    )
  }

  let creature(name: none, ..args) = {
    _required("creature", "name", name)
    let f = creature-fields(name, args.named())
    _mark("creature")
    (r.creature)(f, none, labels)
  }

  // F3.4 a card prints the full codex entry. A Person prints as a person
  // card with what they know (11.4); a Creature as its stat block (11.5);
  // any other type in the theme's codex card.
  let card(entry: none, ..args) = {
    _required("card", "entry", entry)
    let body = args.pos().at(0, default: none)
    // F3 (M6 part C4): fields its codex type lacks stay on the card, as they
    // were written, and print as before.
    let own = args.named()
    let e = entries.at(entry, default: none)
    _mark("card")
    [#metadata((id: entry))#label("scriptorum-card-" + entry)]
    _ref(entry, "card")
    let e = if e == none { (id: entry, type: none, title: "?", fields: (:)) } else { e }
    let t = types.at(str(e.type), default: (card: none, fields: ()))
    let fields = e.fields
    card-open.update(entry)
    if t.card == "person" {
      let pick(key) = { let v = fields.at(key, default: none); if _blank(v) { own.at(key, default: none) } else { v } }
      let pick-rich(key) = { let v = fields.at(key, default: none); if _blank(v) { own.at(key, default: none) } else { rich(v) } }
      let link-ids = fields.at("linked-to", default: ()) + own.at("links", default: ())
      let linked = link-ids.map(l => { _ref(l, "person.links"); name-of(l) })
      let legacy = own.at("linked-to", default: none)
      if type(legacy) != array and not _blank(legacy) { linked.push(legacy) }
      let f = (
          name: e.title,
          mood: pick("mood"),
          description: pick-rich("description"),
          // 11.4 (M6 part C): the portrait follows the person into every card.
          portrait: if _blank(pick("portrait")) { none } else { pick("portrait") },
          portrait-description: pick("portrait-description"),
          linked-to: if linked.len() == 0 { none } else { linked.join(", ") },
          known: () => known-elsewhere(entry),
          clues: () => clues-of(entry, link-ids, none),
        )
      let how = pick-rich("how-to-play")
      if not _blank(how) { f.insert("how-to-play", how) }
      (r.person)(f, body, labels)
    } else if t.card == "creature" {
      let named = (:)
      for (key, value) in fields {
        if key == "name" { continue }
        named.insert(key, if type(value) == str and key not in ("type", "stat-lines") { rich(value) } else { value })
      }
      for (key, value) in own {
        if key not in named { named.insert(key, value) }
      }
      (r.creature)(creature-fields(e.title, named), none, labels)
    } else {
      let shown = t.fields
        .filter(f => f.name != t.at("title_field", default: "name") and not _blank(fields.at(f.name, default: none)))
        .map(f => {
          let value = fields.at(f.name)
          (label: f.label, value: if f.kind == "rich" { rich(value) } else if f.kind == "link" {
            value.map(l => { _ref(l, "entry.link"); name-of(l) }).join(", ")
          } else { str(value) })
        })
      (r.codex-card)((title: e.title, type: e.type, type-name: t.at("name", default: none), fields: shown), body, labels)
    }
    card-open.update(none)
  }

  // 11.10 Box: a framed text box with an optional title. Bold text at the
  // start of a line or list item prints as a label (the theme decides how).
  let box-el(title: none, ..args) = {
    let body = args.pos().at(0, default: [])
    _mark("box")
    (r.box)((title: if _blank(title) { none } else { title }), body, labels)
  }

  // 11.11 Quote: Framed (default), Scrap of paper or Plain. A signer from the
  // codex prints their current name (F3.4) and lends their handwriting
  // unless a Handwriting is chosen; no hand means the theme's quote face.
  let quote-el(variant: "framed", title: none, signer: none, signature: none, description: none,
               handwriting: none, tilt: 0, tint: true, ..args) = {
    if variant not in ("framed", "scrap", "plain") { panic("SCRIPTORUM:variant:quote:" + str(variant)) }
    let body = args.pos().at(0, default: [])
    let tilt = _tilt("quote", tilt)
    let who = if _blank(signer) { none } else { entries.at(signer, default: none) }
    if who != none { _ref(signer, "quote.signer") }
    let hand = if not _blank(handwriting) { handwriting } else if who != none {
      who.fields.at("handwriting", default: none)
    } else { none }
    let sign = if who != none { name-of(signer) } else if _blank(signature) { none } else { signature }
    _mark("quote")
    (r.quote)(
      (
        look: variant,
        title: if _blank(title) { none } else { title },
        signature: sign,
        description: if _blank(description) { none } else { description },
        handwriting: if _blank(hand) { none } else { hand },
        hand-size: if _blank(hand) { none } else { _hand-size(hand) },
        tilt: tilt,
        tint: tint != false,
        fill: secret-fill,
        seed: _hash(_plain(body)),
      ),
      body,
      labels,
    )
  }

  // 11.12 Pacing note: how long a part should take and what happens next.
  let pacing(..args) = {
    let body = args.pos().at(0, default: [])
    _mark("pacing")
    (r.pacing)((:), body, labels)
  }

  // 11.6 Countdown: its body holds the countdown steps.
  let countdown(title: none, ..args) = {
    let body = args.pos().at(0, default: [])
    _mark("countdown")
    (r.countdown)((title: title), body, labels)
  }

  // 11.6 Countdown step: when, what happens, and where the GM goes next.
  let countdown-step(when: none, go-to: none, ..args) = {
    let body = args.pos().at(0, default: [])
    let pointer = if _blank(go-to) { none } else {
      context {
        let found = query(label("scriptorum-scene-" + go-to))
        if found.len() == 0 { [→ ?] } else {
          let target = found.first()
          let where = target.location()
          let number = scene-counter.at(where).first()
          let page = counter(page).at(where).first()
          link(where)[→ #_label(labels, "print.scene", "Scene") #number, #target.value.title, #_label(labels, "print.page-short", "p.") #page]
        }
      }
    }
    _mark("countdown-step")
    (r.countdown-step)((when: when, go-to: go-to, pointer: pointer), body, labels)
  }

  // 11.8 Check: the roll and difficulty print exactly as written.
  let check(roll: none, difficulty: none, ..args) = {
    _required("check", "roll", roll)
    let body = args.pos().at(0, default: none)
    _mark("check")
    (r.check)((roll: roll, difficulty: difficulty), body, labels)
  }

  // 11.9 and F6 Handout. In the adventure PDF it prints where it is written, in
  // the adventure's plain style with its number (F6.1, F6.3). In the player PDF it
  // prints in the handout style on a page of its own, followed by its
  // easy-read copy when the adventure asks for one (F6.2, F6.6).
  let handout(title: none, written-by: none, writer: none, handwriting: none, paper: "letter", image: none, tilt: 0, id: none, look: 0, only-handout: false, ..args) = {
    _required("handout", "title", title)
    let tilt = _tilt("handout", tilt)
    let body = args.pos().at(0, default: none)
    handout-counter.step()
    _mark("handout")
    let who = if _blank(writer) { none } else { entries.at(writer, default: none) }
    if who != none { _ref(writer, "handout.writer") }
    let hand = if not _blank(handwriting) { handwriting } else if who != none {
      who.fields.at("handwriting", default: none)
    } else { none }
    let f = (
      title: title,
      written-by: if who != none { who.title } else { written-by },
      handwriting: hand,
      hand-size: if hand == none { none } else { _hand-size(hand) },
      paper: if _blank(paper) { "letter" } else { paper },
      tilt: tilt,
      image: image,
      number: context handout-counter.get().first(),
      seed: _hash(if _blank(id) { title } else { id }) + (if look == none { 0 } else { look }) * 7919,
    )
    if player {
      (r.handout)(f + (style: "player"), body, labels)
      if easy-read {
        pagebreak(weak: true)
        (r.handout)(f + (style: "easy"), body, labels)
      }
    } else if only-handout == true {
      // F6 (M6 part C3): Only as handout. The adventure PDF prints one line
      // where the handout is given out; the player PDF is unchanged.
      (r.handout)(f + (style: "give-out"), none, labels)
    } else {
      (r.handout)(f + (style: "gm"), body, labels)
    }
  }

  // F5 Map: a base image with layers. The adventure PDF prints every layer; a map
  // marked "Handout also" is numbered like a handout, and its player copy
  // prints only the layers set to show in handouts (F5.2, F5.5, T-WORLD-04).
  let map(map: none, handout-also: false, ..args) = {
    _required("map", "map", map)
    let m = maps.at(map, default: none)
    if handout-also { handout-counter.step() }
    _mark("map")
    let m = if m == none { (title: "?", image: none, aspect: 0.6, layers: ()) } else { m }
    for layer in m.layers {
      for item in layer.items {
        if item.at("entry", default: none) != none { _ref(item.entry, "map.pin") }
      }
    }
    let layers = if player { m.layers.filter(l => l.show_in_handout) } else { m.layers }
    (r.map)(
      (
        title: m.title,
        image: m.image,
        // F17.3 (M5): read by screen readers in place of the picture.
        description: m.at("description", default: ""),
        aspect: m.aspect,
        layers: layers,
        handout: player,
        number: if handout-also { context handout-counter.get().first() } else { none },
      ),
      none,
      labels,
    )
  }

  // F3.9 Relationship chart: the entries and their links, laid out at the
  // positions saved in the adventure.
  let relationship-chart(..args) = {
    _mark("relationship-chart")
    (r.relationship-chart)(world.at("chart", default: (nodes: (), edges: ())), none, labels)
  }

  // F3.10 End-of-book material, each switched on in the adventure settings.
  let end-clues() = context {
    let refs = query(<scriptorum-ref>)
    let items = entries.values().filter(e => e.type == "clue").sorted(key: e => lower(e.title)).map(e => {
      let scenes = ()
      for m in refs.filter(m => m.value.id == e.id) {
        let number = scene-counter.at(m.location()).first()
        let title = scene-current.at(m.location())
        let item = (number: number, title: title)
        if item not in scenes { scenes.push(item) }
      }
      // F3 (M6 part C4): who knows the clue, each once.
      let knowers = ()
      for m in query(<scriptorum-info>).filter(m => m.value.at("clue", default: none) == e.id) {
        let names = m.value.known-by.map(k => entry-title(k))
        if m.value.inside != none { names.push(entry-title(m.value.inside)) }
        let loose = m.value.at("loose", default: none)
        if loose != none { names.push(loose.name) }
        for n in names { if n not in knowers { knowers.push(n) } }
      }
      for p in entries.values() {
        if e.id in p.fields.at("linked-to", default: ()) and p.title not in knowers { knowers.push(p.title) }
      }
      (title: e.title, description: rich(e.fields.at("description", default: none)), scenes: scenes, known-by: knowers)
    })
    (r.end-clues)((items: items), none, labels)
  }

  let end-index() = context {
    let refs = query(<scriptorum-ref>)
    let items = entries.values().filter(e => e.type in ("person", "place")).sorted(key: e => lower(e.title)).map(e => {
      let pages = refs.filter(m => m.value.id == e.id).map(m => _page-of(m.location())).dedup().sorted()
      (title: e.title, type: e.type, pages: pages)
    })
    (r.end-index)((items: items), none, labels)
  }

  // F7.4 (M5) layout markers with a body: a full-width section spans every
  // column and floats to the top or bottom of its page; "never split this"
  // keeps what it holds on one page and in one column.
  let full-width(..args) = {
    let body = args.pos().at(0, default: [])
    _mark("full-width")
    place(auto, scope: "parent", float: true, clearance: 1.2em, block(width: 100%, _framed(body)))
  }
  let keep-together(..args) = {
    let body = args.pos().at(0, default: [])
    _mark("keep-together")
    block(width: 100%, breakable: false, _framed(body))
  }

  // F7.7 (M5): the table of contents: every act heading and scene, with its
  // page, each line a link. The theme draws it (templates/contents.typ).
  let contents(..args) = {
    _mark("contents")
    context {
      // The title page's heading (F17) is not a line of the contents.
      let found = query(selector(heading.where(level: 1)).or(<scriptorum-scene-heading>))
        .filter(h => not (h.has("label") and h.label == <scriptorum-title-heading>))
      let items = found.map(h => (
        kind: if _is-scene-heading(h) { "scene" } else { "act" },
        title: h.body,
        page: _page-of(h.location()),
        target: h.location(),
      ))
      (r.contents)((items: items), none, labels)
    }
  }

  // F7.4 (M5): every block kind is wrapped with its page-start rule; the
  // frames that hold other elements mark their body as contained.
  let frames = ("box", "quote", "person", "countdown", "information", "card")
  let wrap(kind, f) = (..args) => {
    start(kind)
    if kind in frames { _framed(f(..args)) } else { f(..args) }
  }

  let elements = (
    scene: scene,
    read-aloud: read-aloud,
    information: information,
    person: person,
    creature: creature,
    countdown: countdown,
    countdown-step: countdown-step,
    dice: dice,
    check: check,
    handout: handout,
    box: box-el,
    quote: quote-el,
    pacing: pacing,
    card: card,
    mention: mention,
    see: see,
    map: map,
    relationship-chart: relationship-chart,
    // F7.4 layout markers: pagination, not appearance, so no renderer.
    page-break: (..args) => { break-mark("print.break.page", "page break"); pagebreak(weak: true) },
    column-break: (..args) => { break-mark("print.break.column", "column break"); colbreak(weak: true) },
    // F7.7 (M5): a footnote inside a sentence; Typst numbers it and sets
    // it at the foot of the page, linked both ways.
    footnote: (text: none) => {
      _required("footnote", "text", text)
      _mark("footnote")
      std.footnote(text)
    },
    full-width: full-width,
    keep-together: keep-together,
    contents: contents,
    // F3.10: called by the entry file, not written by the author.
    _end-clues: end-clues,
    _end-index: end-index,
  )
  let blocks = ("read-aloud", "information", "person", "creature", "countdown", "check", "handout", "box", "quote",
    "pacing", "card", "map", "relationship-chart", "contents")
  for kind in blocks {
    if kind in elements and (kind in frames or page-start.at(kind, default: "") == "always") { elements.insert(kind, wrap(kind, elements.at(kind))) }
  }
  elements
}
