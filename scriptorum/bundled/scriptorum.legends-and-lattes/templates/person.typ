// 11.4 Person: name, mood, short description, links, and what they know.
// What they know is gathered from the Information lines in the card body.
// No stats, no quote, no handwriting on the card.
//
// M6 part C (decided 12 November 2026): the theme's spacing (F8): a small gap
// after the name and after the mood, about 5 pt before Linked to, a medium
// gap before What they know and a small gap between the things the person
// knows; the text is left-aligned. "What they know" is printed only when
// something is under it. An optional portrait (11.4) sits in the card's
// top-right corner at about a third of its width, its height following the
// picture, never cropped, in the theme's thin frame; the name, mood and
// description sit beside it, and everything after them runs at full width
// under it. A card without a portrait prints as before.

#import "_style.typ": accent, quiet, label, small-caps-label, blank, empty-body, in-card, icon, variant-styles, fonts, spacing, frame-par, portrait-width, portrait-frame, gap, clue-mark

// M3: a person from the codex also lists Information written elsewhere that
// they know, as a short pointer with its page, so the same text is never
// printed twice (11.4, T-WORLD-03).
#let pointers(items, labels) = for item in items {
  let style = variant-styles.at(item.variant)
  block(above: gap(spacing.small), below: 0pt, link(item.target, {
    icon(item.variant, style.color)
    h(0.35em)
    small-caps-label(label(labels, "print.information." + item.variant), fill: style.color)
    h(0.45em)
    // F3 (M6 part C4): a clue known here prints its mark and name.
    let what = if item.at("clue", default: none) != none { [#clue-mark(style.color)#h(0.3em)#item.clue] } else { item.summary }
    [#what #label(labels, "print.see-page").replace("{page}", str(item.page))]
  }))
}

// 11.4 (M6 part C4): the Clues line, each clue once with its page pointer.
#let clues-line(items, labels) = if items.len() > 0 {
  block(above: gap(spacing.medium), below: 0pt, {
    [#text(weight: "bold", fill: accent)[#label(labels, "print.clues"):] ]
    items.map(c => {
      let page = if c.page == none { [] } else { [ #label(labels, "print.see-page").replace("{page}", str(c.page))] }
      if c.target == none [#c.title] else { link(c.target)[#c.title#page] }
    }).join(", ")
  })
}

// The name, the mood and the description: beside the portrait, if any.
#let head(f, labels) = {
  block(above: 0pt, below: 0pt,
    text(font: fonts.head, size: 11.5pt, weight: "bold", tracking: 0.06em, fill: accent, upper(f.name)))
  if not blank(f.mood) {
    block(above: gap(spacing.small), below: 0pt,
      [#text(weight: "bold", fill: accent)[#label(labels, "print.mood"):] #emph(f.mood)])
  }
  // 11.4 (M6 part C4): How to play, right under Mood, with a small label.
  let how = f.at("how-to-play", default: none)
  if not blank(how) {
    block(above: gap(spacing.small), below: 0pt, {
      small-caps-label(label(labels, "print.how-to-play"), fill: quiet)
      h(0.45em)
      how
    })
  }
  if not blank(f.description) {
    block(above: gap(spacing.small), below: 0pt, f.description)
  }
}

#let portrait(f) = {
  let alt = f.at("portrait-description", default: none)
  portrait-frame(image(f.portrait, width: 100%, alt: if blank(alt) { none } else { alt }))
}

#let render(f, body, labels) = block(
  width: 100%,
  breakable: false,
  stroke: 0.6pt + accent,
  inset: (x: 10pt, y: 9pt),
  above: 1.1em,
  below: 1.1em,
  frame-par({
    if blank(f.at("portrait", default: none)) {
      head(f, labels)
    } else {
      grid(columns: (1fr, portrait-width), column-gutter: spacing.large, head(f, labels), portrait(f))
    }
    if not blank(f.linked-to) {
      // About 5 pt: slightly more than small, so it does not touch the description.
      block(above: gap(5pt), below: 0pt,
        [#text(weight: "bold", fill: accent)[#label(labels, "print.linked-to"):] #f.linked-to])
    }
    let known = f.at("known", default: none)
    let has-body = not empty-body(body)
    if has-body or known != none {
      context {
        let items = if known == none { () } else { known() }
        if has-body or items.len() > 0 {
          block(above: gap(spacing.medium), below: 0pt,
            small-caps-label(label(labels, "print.what-they-know"), fill: quiet))
        }
        in-card.update(true)
        if has-body { body }
        in-card.update(false)
        pointers(items, labels)
      }
    }
    let clues = f.at("clues", default: none)
    if clues != none { context clues-line(clues(), labels) }
  }),
)
