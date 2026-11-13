// Generic frame (9.6): used for any element kind this theme has no
// renderer for. The build reports a warning when it is used.

#import "_style.typ": accent, quiet, label, small-caps-label, blank

#let render(f, body, labels, kind: "") = block(
  width: 100%,
  breakable: false,
  stroke: 0.6pt + quiet,
  inset: 8pt,
  above: 1em,
  below: 1em,
  {
    small-caps-label(label(labels, "element." + kind), fill: quiet)
    for (key, value) in f {
      if not blank(value) and type(value) != bool {
        linebreak()
        [#text(weight: "bold")[#key:] #value]
      }
    }
    if not blank(body) {
      parbreak()
      body
    }
  },
)
