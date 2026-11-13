// F3.9 Relationship chart: entries and the links between them, at the
// positions saved in the adventure, drawn with the fletcher package
// (MIT, pinned at 0.5.8 and copied into this theme, D15).

#import "../vendor/fletcher-0.5.8/src/exports.typ" as fletcher: diagram, node, edge
#import "_style.typ": accent, quiet, label, small-caps-label, blank

#let shapes = (person: "rect", place: "pill", clue: "rect", creature: "rect")

#let render(f, body, labels) = block(
  width: 100%,
  breakable: false,
  above: 1.1em,
  below: 1.1em,
  {
    small-caps-label(label(labels, "print.relationship-chart"), fill: quiet)
    v(0.5em)
    if f.nodes.len() > 0 { layout(size => {
      let w = size.width * 0.86
      let h = w * 0.6
      align(center, diagram(
        spacing: 0pt,
        node-stroke: 0.6pt + accent,
        node-inset: 4pt,
        edge-stroke: 0.6pt + quiet,
        ..f.nodes.map(n => node(
          (n.x * w, -n.y * h),
          text(size: 8pt, fill: accent, n.title),
          name: std.label("rel-" + n.id),
          corner-radius: if n.type == "place" { 6pt } else { 1.5pt },
          fill: if n.type == "clue" { luma(244) } else { white },
        )),
        ..f.edges.map(e => edge(std.label("rel-" + e.from), std.label("rel-" + e.to), "-")),
      ))
    }) }
  },
)
