// F5 Map: the base image with its layers drawn on top as vectors (pins,
// labels, areas and notes). In the adventure PDF every layer prints; the handout
// copy gets only the layers set to show in handouts (the core element kit
// filters them). Colours stay light so maps print well.

#import "_style.typ": accent, quiet, label, small-caps-label, blank

#let halo(body, size: 7.5pt, weight: "regular") = box(
  fill: white.transparentize(15%), inset: (x: 2pt, y: 1.2pt), radius: 1.5pt,
  text(size: size, weight: weight, fill: accent, body),
)

// Place something with its centre on a point of the map.
#let centred(x, y, body) = context {
  let size = measure(body)
  place(top + left, dx: x - size.width / 2, dy: y - size.height / 2, body)
}

#let draw-item(item, w, h) = {
  let t = item.at("title", default: none)
  let text-of = if t != none { t } else { item.at("text", default: "") }
  if item.type == "area" {
    let pts = item.points.map(p => (p.at(0) * w, p.at(1) * h))
    place(top + left, polygon(fill: accent.transparentize(88%), stroke: 0.9pt + accent, ..pts))
    if text-of != "" {
      let cx = pts.map(p => p.at(0)).sum() / pts.len()
      let cy = pts.map(p => p.at(1)).sum() / pts.len()
      centred(cx, cy, halo(text-of))
    }
  } else if item.type == "pin" {
    // F5 (M6 part C3): a pin shows its number; its name goes in the key.
    let x = item.x * w
    let y = item.y * h
    let n = item.at("number", default: none)
    if n == none {
      place(top + left, dx: x - 3pt, dy: y - 3pt, circle(radius: 3pt, fill: accent, stroke: 0.8pt + white))
    } else {
      centred(x, y, box(
        circle(radius: 5.2pt, fill: accent, stroke: 0.8pt + white,
          align(center + horizon, text(size: 6.4pt, weight: "bold", fill: white, str(n)))),
      ))
    }
  } else if item.type == "line" {
    // F5 (M6 part C3): a line between pins or through points, solid or
    // dashed, with its label along it when it has one.
    let pts = item.points.map(p => (p.at(0) * w, p.at(1) * h))
    let dashed = item.at("style", default: "solid") == "dashed"
    let stroke = (paint: accent, thickness: 1.1pt, cap: "round", join: "round", dash: if dashed { "dashed" } else { none })
    place(top + left, curve(stroke: stroke, curve.move(pts.first()), ..pts.slice(1).map(p => curve.line(p))))
    if text-of != "" {
      let i = calc.max(0, calc.floor((pts.len() - 1) / 2))
      let a = pts.at(i)
      let b = pts.at(i + 1)
      let mid = ((a.at(0) + b.at(0)) / 2, (a.at(1) + b.at(1)) / 2)
      let angle = calc.atan2((b.at(0) - a.at(0)) / 1pt, (b.at(1) - a.at(1)) / 1pt)
      // Keep the words upright.
      let angle = if angle > 90deg { angle - 180deg } else if angle < -90deg { angle + 180deg } else { angle }
      centred(mid.at(0), mid.at(1), rotate(angle, reflow: true, halo(text-of, size: 7pt)))
    }
  } else if item.type == "label" {
    centred(item.x * w, item.y * h, halo(text-of, size: 8.5pt, weight: "bold"))
  } else if item.type == "note" {
    place(top + left, dx: item.x * w, dy: item.y * h, box(
      width: calc.min(w * 0.32, 4.2cm), fill: white, stroke: 0.6pt + quiet, inset: 3pt, radius: 1.5pt,
      text(size: 7pt, fill: accent, text-of),
    ))
  }
}

#let render(f, body, labels) = block(
  width: 100%,
  breakable: false,
  above: 1.1em,
  below: 1.1em,
  {
    // In the handouts PDF the caption sits under the map, as under every
    // other handout: "HANDOUT 1 · title" (F6.5).
    let player = f.at("handout", default: false) and f.number != none
    let caption = if player {
      [#label(labels, "print.handout-caption").replace("{n}", "")#f.number]
    } else if f.number != none {
      [#label(labels, "print.handout-number").replace("{n}", "")#f.number · #f.title]
    } else { [#label(labels, "print.map") · #f.title] }
    if not player {
      small-caps-label(caption, fill: quiet)
      v(0.3em)
    }
    // F5 (M6 part C3): the key lists each pin's number with its entry's
    // name (or its own text) and its note. It sits beside the map when the
    // map is upright and there is room, otherwise under it.
    let pins = f.layers.map(l => l.items.filter(i => i.type == "pin" and i.at("number", default: none) != none)).flatten()
      .sorted(key: i => i.number)
    let key-lines = pins.map(i => {
      let name = i.at("title", default: none)
      let name = if name == none or name == "" { i.at("text", default: "") } else { name }
      let note = i.at("note", default: "")
      (i.number, name, note)
    }).filter(k => k.at(1) != "" or k.at(2) != "")
    let key = if key-lines.len() == 0 { none } else {
      grid(columns: (auto, 1fr), column-gutter: 4pt, row-gutter: 3pt,
        ..key-lines.map(((n, name, note)) => (
          box(circle(radius: 4.4pt, fill: accent, stroke: none,
            align(center + horizon, text(size: 5.8pt, weight: "bold", fill: white, str(n))))),
          text(size: 7.5pt, fill: accent, {
            strong(name)
            if note != "" { if name != "" [ — ]; note }
          }),
        )).flatten())
    }
    let draw-map(w) = {
      let h = w * f.aspect
      box(width: w, height: h, stroke: 0.4pt + quiet, {
        // F17.3 (M5): the map's description is its alt text for screen readers.
        let alt = f.at("description", default: "")
        if f.image != none { place(top + left, image(f.image, width: w, height: h, fit: "stretch", alt: if alt == "" { none } else { alt })) }
        for layer in f.layers {
          for item in layer.items.filter(i => i.type == "area") { draw-item(item, w, h) }
          for item in layer.items.filter(i => i.type == "line") { draw-item(item, w, h) }
        }
        for layer in f.layers {
          for item in layer.items.filter(i => i.type != "area" and i.type != "line") { draw-item(item, w, h) }
        }
      })
    }
    layout(size => {
      let beside = key != none and f.aspect >= 0.9
      if beside {
        grid(columns: (68%, 1fr), column-gutter: 4%, draw-map(size.width * 0.68), align(top, key))
      } else {
        draw-map(size.width)
        if key != none { block(above: 2.5mm, columns(if key-lines.len() > 4 { 2 } else { 1 }, gutter: 5mm, key)) }
      }
    })
    if player {
      block(above: 3mm, {
        small-caps-label(caption, fill: quiet)
        text(size: 8pt, fill: quiet)[ · #emph(f.title)]
      })
    }
  },
)
