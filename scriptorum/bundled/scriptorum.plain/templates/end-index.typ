// F3.10 Index of people and places at the end of the adventure PDF, with the
// pages each one appears on.

#import "_style.typ": accent, quiet, label, small-caps-label, blank

#let render(f, body, labels) = {
  pagebreak(weak: true)
  heading(level: 2, label(labels, "print.index"))
  set par(justify: false)
  for item in f.items {
    block(above: 0.35em, below: 0.35em, [#item.title #box(width: 1fr, repeat[.#h(2pt)]) #item.pages.map(str).join(", ")])
  }
}
