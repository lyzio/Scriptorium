// F3.4 Codex card for any codex type without an element of its own (Place,
// Clue and the author's own types): the entry's name, its type and every
// filled-in field.

#import "_style.typ": accent, quiet, label, small-caps-label, blank, empty-body, in-card, fonts, spacing, frame-par, gap

#let render(f, body, labels) = block(
  width: 100%,
  breakable: false,
  stroke: (top: 1pt + accent, bottom: 0.6pt + accent),
  inset: (x: 2pt, y: 8pt),
  above: 1.1em,
  below: 1.1em,
  // F8 (M6 part C): spaced like the person card, left-aligned.
  frame-par({
    if not blank(f.type-name) { block(above: 0pt, below: 0pt, small-caps-label(f.type-name, fill: quiet)) }
    block(above: gap(0pt), below: 0pt,
      text(font: fonts.head, size: 11.5pt, weight: "bold", tracking: 0.06em, fill: accent, upper(f.title)))
    for item in f.fields {
      block(above: gap(spacing.small), below: 0pt, [#text(weight: "bold", fill: accent)[#item.label:] #item.value])
    }
    if not empty-body(body) {
      in-card.update(true)
      body
      in-card.update(false)
    }
  }),
)
