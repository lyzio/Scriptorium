// 11.6 Countdown step: an empty square tick box, When in bold, then the
// text and the Go to pointer.

#import "_style.typ": ochre, blank, spacing, gap

#let render(f, body, labels) = block(above: gap(spacing.small), below: gap(spacing.small), {
  grid(
    columns: (0.95em, 1fr),
    column-gutter: 0.45em,
    box(baseline: 0.1em, rect(width: 0.72em, height: 0.72em, stroke: 0.7pt + ochre)),
    {
      if not blank(f.when) [#text(weight: "bold")[#f.when:] ]
      body
      if f.pointer != none [ #text(style: "italic", f.pointer)]
    },
  )
})
