// F3.10 Clue overview at the end of the adventure PDF: each clue, its
// description and the scenes where it appears.

#import "_style.typ": accent, quiet, label, small-caps-label, blank

#let render(f, body, labels) = {
  pagebreak(weak: true)
  heading(level: 2, label(labels, "print.clue-overview"))
  for item in f.items {
    block(above: 0.9em, below: 0.6em, breakable: false, {
      text(weight: "bold", fill: accent, item.title)
      if item.description != none { block(above: 0.3em, below: 0.2em, item.description) }
      // F3 (M6 part C4): who knows the clue.
      if item.at("known-by", default: ()).len() > 0 {
        block(above: 0.2em, below: 0.2em, text(size: 8.5pt, fill: quiet)[#label(labels, "print.known-by"): #item.known-by.join(", ")])
      }
      if item.scenes.len() > 0 {
        text(size: 8.5pt, fill: quiet)[#label(labels, "print.appears-in"): #item.scenes.map(s =>
          if s.title == none { label(labels, "print.no-scene") } else [#label(labels, "print.scene") #s.number, #s.title]).join("; ")]
      }
    })
  }
}
