// F7.7 (M5): the table of contents. Act headings in the display face, scenes
// under them with a dotted leader to their page; every line is a link.

#import "_style.typ": accent, quiet, label, fonts, spaced-caps

#let render(f, body, labels) = block(width: 100%, above: 1.2em, below: 1.4em, {
  align(center, spaced-caps(label(labels, "print.contents"), size: 9pt))
  v(0.6em)
  set par(justify: false)
  for item in f.items {
    let line = if item.kind == "act" {
      block(above: 0.8em, below: 0.3em, text(font: fonts.head, weight: "bold", fill: accent, [#item.title #box(width: 1fr) #str(item.page)]))
    } else {
      block(above: 0.25em, below: 0.25em, inset: (left: 1em), [#item.title #box(width: 1fr, repeat[.#h(3pt)]) #text(fill: quiet, str(item.page))])
    }
    link(item.target, line)
  }
})
