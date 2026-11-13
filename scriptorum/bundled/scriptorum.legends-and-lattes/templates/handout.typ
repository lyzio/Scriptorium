// 11.9 and F6 Handout (look revised 6 Nov 2026; tilt, Parchment and long
// handouts on several sheets decided 6 and 8 Nov 2026, built in M4).
//
// style "gm":     in the adventure PDF, where it is written, in the
//                 adventure's plain style, with its number (F6.1, F6.3). A
//                 long one continues onto the next page like ordinary text.
// style "player": in the handouts PDF, a drawn sheet of paper with the text
//                 on it and a caption under it (F6.5), each on a page of its
//                 own; a long one on several sheets.
// style "easy":   the easy-read copy: the same sheet, but a clear italic
//                 serif instead of handwriting (F6.6), split on its own.
//
// The paper is never filled with a colour; only the outline, the inner line,
// folds, marks and the ink are coloured (F6.5). Everything that varies comes
// from f.seed (the handout's name plus its "look" number) and the sheet
// number, so a handout looks the same on every build (F7.8).

#import "_style.typ": accent, quiet, label, small-caps-label, blank, empty-body, fonts, spacing, frame-par, gap

#let papers = json("../handouts.json").papers

#let paper-style(id) = {
  let found = papers.filter(p => p.id == id)
  if found.len() == 0 { papers.first() } else { found.first() }
}

// Park–Miller random numbers in [0, 1), the same for the same seed.
#let randoms(seed, n) = {
  let x = calc.rem(calc.abs(seed), 2147483646) + 1
  let out = ()
  for _ in range(n) {
    x = calc.rem(x * 48271, 2147483647)
    out.push(x / 2147483647)
  }
  out
}

#let pick(pair, r) = {
  let (lo, hi) = pair
  lo + calc.floor(r * (hi - lo + 1 - 0.0001))
}

// Page geometry of a handout page in the handouts PDF.
#let page-margin = 14mm
#let pad = 16mm          // from the sheet's edge to its text
#let caption-room = 9mm  // the caption under the sheet

#let gm(f, body, labels) = block(
  width: 100%,
  // F6.5: in the adventure PDF a long handout continues like ordinary text.
  breakable: true,
  stroke: 0.6pt + quiet,
  inset: (x: 10pt, y: 9pt),
  above: 1.1em,
  below: 1.1em,
  // F8 (M6 part C): the in-place copy is spaced and aligned like other frames.
  frame-par({
    small-caps-label([#label(labels, "print.handout-number").replace("{n}", "")#f.number], fill: quiet)
    linebreak()
    text(font: fonts.head, size: 11pt, weight: "bold", fill: accent, f.title)
    if not blank(f.written-by) {
      linebreak()
      text(size: 9pt, fill: quiet)[#label(labels, "print.written-by"): #f.written-by]
    }
    if not blank(f.image) {
      block(above: gap(spacing.medium), below: 0pt, width: 100%, image(f.image, width: 100%))
    }
    if not empty-body(body) {
      block(above: gap(spacing.medium), body)
    }
  }),
)

#let hand-of(f, easy) = if easy or blank(f.handwriting) { none } else { f.handwriting }

// The text on the sheet: handwriting when there is one, otherwise an italic
// serif; the easy-read copy always uses the clear italic serif. `scale`
// sets the text smaller (down to 85 %) so a slightly long letter still fits
// one sheet (F6.5).
#let sheet-text(f, body, ink, easy, scale: 1) = {
  set text(fill: ink)
  set par(justify: false, leading: 0.72em, spacing: 1.1em, first-line-indent: (amount: 1.4em, all: false))
  let hand = hand-of(f, easy)
  let size = if hand != none { f.at("hand-size", default: 13pt) } else { 13pt }
  set text(font: (hand, fonts.easy), size: size * scale) if hand != none
  set text(font: fonts.easy, style: "italic", size: size * scale) if hand == none
  set par(leading: 0.95em) if hand != none
  if not blank(f.image) { block(below: 0.9em, width: 100%, image(f.image, width: 100%)) }
  if not blank(body) { body }
}

// The height of one more line of this handout's text.
#let line-pitch(f, ink, easy) = {
  let one = measure(sheet-text(f, [Åg], ink, easy)).height
  let two = measure(sheet-text(f, [Åg \ Åg], ink, easy)).height
  two - one
}

// F6.5 long handouts: how the text goes on the sheets. Returns the text
// scale, the number of sheets and the text height of every sheet.
#let sheet-plan(f, body, easy, page-w, page-h) = {
  let style = paper-style(f.paper)
  let ink = rgb(style.at("ink", default: "#1F1B18"))
  let width = page-w - 2 * page-margin - 2 * pad
  let room = page-h - 2 * page-margin - caption-room - 2 * pad - 4mm
  let height(scale) = measure(block(width: width, sheet-text(f, body, ink, easy, scale: scale))).height
  let full = height(1)
  if full <= room { return (scale: 1, sheets: 1, room: room, width: width) }
  // Set up to 15 % smaller, so a second sheet never holds only a line or two.
  for step in range(1, 16) {
    let s = 1 - step / 100
    if height(s) <= room { return (scale: s, sheets: 1, room: room, width: width) }
  }
  // Further sheets at the normal size. The last holds at least 5 % of the
  // lines and never fewer than 3; otherwise lines move to it from the sheets
  // before, spread evenly (every sheet then ends equally short).
  let pitch = line-pitch(f, ink, easy)
  let lines = calc.ceil(full / pitch)
  let per = calc.max(4, calc.floor(room / pitch))
  let n = calc.ceil(lines / per)
  let last = lines - (n - 1) * per
  let least = calc.max(3, calc.ceil(lines * 0.05))
  if last < least and n > 1 {
    per = per - calc.ceil((least - last) / (n - 1))
  }
  (scale: 1, sheets: n, room: per * pitch, width: width)
}

// Points along the edge of the sheet, `inset` in from the box, jagged by
// `amp`, with the bottom-right corner cut off for the curl. Tears are deeper
// nicks on some sides. `round` rounds the corners unevenly (Parchment).
#let edge-points(w, h, inset, amp, step, corner, rnd, tears: (), round: 0pt) = {
  let pts = ()
  let k = 0
  let c = corner
  let r = round
  // (start, end, outward normal, side number)
  let sides = (
    ((inset + r, inset), (w - inset - r, inset), (0, -1), 0),
    ((w - inset, inset + r), (w - inset, h - inset - calc.max(c, r)), (1, 0), 1),
    ((w - inset - calc.max(c, r), h - inset), (inset + r, h - inset), (0, 1), 2),
    ((inset, h - inset - r), (inset, inset + r), (-1, 0), 3),
  )
  // Corner arcs for a rounded sheet: (centre, start angle).
  let arcs = (
    (w - inset - r, inset + r, -90deg),
    (w - inset - r, h - inset - r, 0deg),
    (inset + r, h - inset - r, 90deg),
    (inset + r, inset + r, 180deg),
  )
  for ((x0, y0), (x1, y1), (nx, ny), s) in sides {
    let length = calc.max(calc.abs((x1 - x0) / 1pt), calc.abs((y1 - y0) / 1pt)) * 1pt
    let n = calc.max(2, int(length / (step * (0.8 + rnd.at(calc.rem(200 + s, rnd.len())) * 0.4))))
    let tear-at = if s in tears { calc.floor(n * (0.25 + rnd.at(calc.rem(40 + s, rnd.len())) * 0.5)) } else { -1 }
    for i in range(n) {
      let t = i / n
      let q = rnd.at(calc.rem(k, rnd.len()))
      k += 1
      // A sawtooth with some randomness, like a hand-drawn torn edge.
      let d = (if calc.rem(i, 2) == 0 { 0.3 } else { -0.3 }) * amp + (q - 0.5) * 1.6 * amp
      if i == tear-at { d = -(2.6mm + q * 2.2mm) }
      pts.push((x0 + (x1 - x0) * t + nx * d, y0 + (y1 - y0) * t + ny * d))
    }
    pts.push((x1, y1))
    if r > 0pt and not (s == 1 and c > 0pt) {
      let (cx, cy, a0) = arcs.at(s)
      let rr = r * (0.75 + rnd.at(calc.rem(220 + s, rnd.len())) * 0.5)
      for j in range(1, 4) {
        let a = a0 + 90deg * j / 4
        pts.push((cx + rr * calc.cos(a), cy + rr * calc.sin(a)))
      }
    }
  }
  pts
}

// The drawn sheet, w by h, without its text. `sheet` numbers the sheets of a
// long handout, so every sheet has its own edge, folds and marks.
#let draw-sheet(f, w, h, sheet: 1, tint: none) = {
  let style = paper-style(f.paper)
  let outline-colour = rgb(style.at("outline", default: "#5A4632"))
  let inner-colour = rgb(style.at("inner", default: "#C9AE84"))
  let marks = style.at("marks", default: (:))
  let mark-colour = rgb(marks.at("colour", default: "#C9AE84"))
  let rnd = randoms(f.seed + (sheet - 1) * 104729, 320)
  let soft = style.at("edge", default: "torn") == "soft"
  let amp = style.at("edge_mm", default: 0.8) * 1mm
  let curl = style.at("corner", default: "curl") == "curl"
  let corner = if curl { 11mm + rnd.at(1) * 5mm } else { 0pt }
  let round = if style.at("corner", default: "curl") == "round" { 5mm } else { 0pt }
  let spots = pick(marks.at("spots", default: (0, 0)), rnd.at(2))
  let spot-size = marks.at("spot_mm", default: 1.1) * 1mm
  let stains = pick(marks.at("stains", default: (0, 0)), rnd.at(3))
  let rings = pick(marks.at("rings", default: (0, 0)), rnd.at(7))
  let hatch = pick(marks.at("hatch", default: (0, 0)), rnd.at(8))
  let tear-count = pick(marks.at("tears", default: (0, 0)), rnd.at(4))
  let folds = pick(style.at("folds", default: (0, 0)), rnd.at(5))
  let tears = range(tear-count).map(i => calc.rem(calc.floor(rnd.at(6 + i) * 4) + i, 4))
  let opacity = calc.min(0.2, marks.at("opacity", default: 0.12))
  // Decoration: screen readers skip it (F17.4).
  pdf.artifact({
    // A tint (allowed only on a quote's scrap of paper, never on a handout,
    // F6.5) follows the torn edge.
    if tint != none {
      place(top + left, polygon(fill: tint, stroke: none,
        ..edge-points(w, h, 0.8mm, amp, if soft { 7.5mm } else { 4.2mm }, corner, rnd.slice(160), tears: tears, round: round)))
    }
    // Ruled lines, as on a notebook page (a paper style may ask for them).
    let ruled = style.at("ruled", default: none)
    if ruled != none {
      let gap = ruled.at("gap_mm", default: 7) * 1mm
      let y = 14mm
      while y < h - 8mm {
        place(top + left, dx: 5mm, dy: y, line(length: w - 10mm, stroke: 0.4pt + rgb(ruled.colour)))
        y += gap
      }
    }
    // A printed head, such as a telegram form (paper style "head").
    let head = style.at("head", default: none)
    if head != none {
      place(top + left, dx: 0pt, dy: 6mm, box(width: w, align(center,
        text(font: fonts.label, size: 9pt, tracking: 0.35em, fill: outline-colour, upper(head)))))
      place(top + left, dx: 8mm, dy: 12mm, line(length: w - 16mm, stroke: 0.5pt + outline-colour))
    }
    // Fold lines: light and dashed. A long letter also gets a vertical one.
    let fold = (paint: luma(185), thickness: 0.5pt, dash: (array: (3pt, 3pt), phase: 0pt))
    if folds >= 1 {
      let y = h * (0.46 + rnd.at(10) * 0.08)
      place(top + left, dx: 3mm, dy: y, line(length: w - 6mm, stroke: fold))
    }
    if folds >= 2 {
      if h > w * 0.9 {
        let x = w * (0.47 + rnd.at(11) * 0.06)
        place(top + left, dx: x, dy: 3mm, line(length: h - 6mm, angle: 90deg, stroke: fold))
      } else {
        let y = h * (0.22 + rnd.at(12) * 0.06)
        place(top + left, dx: 3mm, dy: y, line(length: w - 6mm, stroke: fold))
      }
    }
    // Pale stains: colour on the mark only, never on the paper.
    for i in range(stains) {
      let r = rnd.slice(60 + 4 * i, 64 + 4 * i)
      let rx = 7mm + r.at(2) * 9mm
      let x = w * (0.15 + r.at(0) * 0.7)
      let y = h * (0.15 + r.at(1) * 0.7)
      place(top + left, dx: x - rx, dy: y - rx * 0.7, ellipse(width: rx * 2, height: rx * 1.4,
        fill: mark-colour.transparentize(100% - opacity * 100%), stroke: none))
    }
    // A pale ring stain, as from a cup (Legends and Lattes papers).
    for i in range(rings) {
      let r = rnd.slice(230 + 3 * i, 233 + 3 * i)
      let radius = 9mm + r.at(2) * 5mm
      let x = w * (0.62 + r.at(0) * 0.25)
      let y = h * (0.12 + r.at(1) * 0.3)
      place(top + left, dx: x - radius, dy: y - radius, circle(radius: radius,
        stroke: (paint: mark-colour.transparentize(100% - opacity * 100%), thickness: 2.4pt)))
    }
    // Small spot rings.
    for i in range(spots) {
      let r = rnd.slice(90 + 3 * i, 93 + 3 * i)
      let radius = spot-size + r.at(2) * spot-size
      let x = w * (0.08 + r.at(0) * 0.84)
      let y = h * (0.08 + r.at(1) * 0.84)
      place(top + left, dx: x - radius, dy: y - radius, circle(radius: radius, stroke: 0.7pt + mark-colour))
    }
    // Short hatch strokes along the edges, to suggest age (Parchment).
    for i in range(hatch) {
      let r = rnd.slice(240 + 2 * i, 242 + 2 * i)
      let side = calc.rem(i, 4)
      let t = 0.1 + r.at(0) * 0.8
      let len = 2.5mm + r.at(1) * 3mm
      let (x, y, angle) = if side == 0 { (w * t, 2.2mm, 80deg) } else if side == 1 { (w - 2.2mm, h * t, 170deg) } else if side == 2 { (w * t, h - 2.2mm, -100deg) } else { (2.2mm, h * t, -10deg) }
      for j in range(3) {
        place(top + left, dx: x + j * 1.1mm * (if side in (0, 2) { 1 } else { 0 }), dy: y + j * 1.1mm * (if side in (1, 3) { 1 } else { 0 }),
          line(length: len * (1 - j * 0.2), angle: angle, stroke: (paint: outline-colour.transparentize(35%), thickness: 0.45pt, cap: "round")))
      }
    }
    // The thin line just inside the edge.
    place(top + left, polygon(stroke: (paint: inner-colour, thickness: 0.7pt, join: "round"),
      ..edge-points(w, h, 3.8mm, amp * 0.3, if soft { 14mm } else { 9mm }, corner * 0.78, rnd.slice(120), round: round * 0.8)))
    // The outline: torn, or soft and uneven on Parchment.
    place(top + left, polygon(stroke: (paint: outline-colour, thickness: if soft { 1.2pt } else { 1.4pt }, join: "round"),
      ..edge-points(w, h, 0.8mm, amp, if soft { 7.5mm } else { 4.2mm }, corner, rnd.slice(160), tears: tears, round: round)))
    // The curled corner: the flap folded back over the sheet. It stays white
    // like the paper; only its outline and a shade line are drawn.
    if curl {
      let ax = w - 0.8mm - corner
      let ay = h - 0.8mm
      let bx = w - 0.8mm
      let by = h - 0.8mm - corner
      let tx = ax + corner * 0.06
      let ty = by + corner * 0.06
      place(top + left, curve(
        fill: white,
        stroke: (paint: outline-colour, thickness: 1pt, join: "round"),
        curve.move((ax, ay)),
        curve.quad((ax - corner * 0.08, ay - corner * 0.55), (tx, ty)),
        curve.quad((bx - corner * 0.55, by - corner * 0.08), (bx, by)),
        curve.close(),
      ))
      place(top + left, curve(
        stroke: (paint: inner-colour, thickness: 0.6pt, cap: "round"),
        curve.move((ax + corner * 0.22, ay - corner * 0.1)),
        curve.quad((ax + corner * 0.25, by + corner * 0.3), (bx - corner * 0.1, by + corner * 0.22)),
      ))
    }
  })
}

// The caption under a sheet: "HANDOUT 1 · title · 1 of 2" (F6.5).
#let caption(f, labels, easy, i: 1, n: 1) = {
  small-caps-label([#label(labels, "print.handout-caption").replace("{n}", "")#f.number#if easy [ · #label(labels, "print.easy-read")]], fill: quiet)
  text(size: 8pt, fill: quiet)[ · #emph(f.title)]
  if n > 1 {
    text(size: 8pt, fill: quiet)[ · #label(labels, "print.sheet-of").replace("{i}", str(i)).replace("{n}", str(n))]
  }
}

// A handout that fits one sheet, sized to its text: a short note gives a
// wide, low sheet. The tilt turns the sheet and its text together; the room
// around it keeps clear (reflow).
#let single-sheet(f, body, labels, easy, plan) = layout(size => {
  let style = paper-style(f.paper)
  let ink = if easy { rgb("#1F1B18") } else { rgb(style.at("ink", default: "#1F1B18")) }
  let tilt = f.at("tilt", default: 0)
  let full = size.width * (1 - calc.abs(tilt) * 0.035)
  let first = measure(block(width: full - 2 * pad, sheet-text(f, body, ink, easy, scale: plan.scale))).height
  let w = if first < 34mm { full * 0.62 } else { full }
  let inner = block(width: w - 2 * pad, sheet-text(f, body, ink, easy, scale: plan.scale))
  let limit = size.height - caption-room - 2mm - w * calc.abs(calc.sin(tilt * 1deg))
  let h = calc.min(limit, calc.max(w * 0.5, measure(inner).height + 2 * pad + 4mm))
  let sheet = box(width: w, height: h, {
    draw-sheet(f, w, h)
    place(top + left, dx: pad, dy: pad, inner)
  })
  align(center, if tilt == 0 { sheet } else { rotate(tilt * 1deg, reflow: true, sheet) })
  align(center, block(above: 3mm, width: w, align(left, caption(f, labels, easy))))
})

// A long handout on several sheets: the text flows from sheet to sheet, each
// on a page of its own with its own drawn sheet; it breaks only between
// lines, and each sheet but the last ends with "./." in the handwriting.
#let long-sheets(f, body, labels, easy, bottom, key) = {
  let start = std.label(key + "-start")
  let end = std.label(key + "-end")
  let style = paper-style(f.paper)
  let ink = if easy { rgb("#1F1B18") } else { rgb(style.at("ink", default: "#1F1B18")) }
  page(
    // The text area of every sheet is the plan's height; the bottom margin
    // makes up the rest of the page.
    margin: (x: page-margin + pad, top: page-margin + pad, bottom: bottom),
    header: none,
    footer: none,
    background: context {
      let first = query(start)
      let last = query(end)
      if first.len() == 0 or last.len() == 0 { return }
      let s = first.first().location().page()
      let e = last.first().location().page()
      let i = here().page() - s + 1
      let n = e - s + 1
      let w = page.width - 2 * page-margin
      let h = page.height - 2 * page-margin - caption-room
      place(top + left, dx: page-margin, dy: page-margin, box(width: w, height: h, draw-sheet(f, w, h, sheet: i)))
      if i < n {
        let hand = hand-of(f, easy)
        place(top + left, dx: page.width - page-margin - pad - 14mm, dy: page-margin + h - pad + 2mm,
          text(font: if hand != none { (hand, fonts.easy) } else { fonts.easy }, style: if hand == none { "italic" } else { "normal" },
            size: 12pt, fill: ink, label(labels, "print.continued")))
      }
      place(top + left, dx: page-margin, dy: page-margin + h + 3mm, caption(f, labels, easy, i: i, n: n))
    },
  )[
    #metadata(none)#start
    #sheet-text(f, body, ink, easy)
    #metadata(none)#end
  ]
}

#let sheet(f, body, labels, easy: false) = context {
  let plan = sheet-plan(f, body, easy, page.width, page.height)
  let key = "scriptorum-sheets-" + str(f.seed) + (if easy { "-e" } else { "-p" }) + "-" + str(counter("scriptorum-sheet-key").get().first())
  counter("scriptorum-sheet-key").step()
  // F6.5: the Handouts tab shows how many sheets a handout needs, and
  // preflight warns above 4 (F7.5.7).
  if not easy [#metadata((number: counter("scriptorum-handout").get().first(), sheets: plan.sheets))<scriptorum-sheets>]
  if plan.sheets == 1 {
    page(margin: page-margin, header: none, footer: none, single-sheet(f, body, labels, easy, plan))
  } else {
    long-sheets(f, body, labels, easy, page.height - page-margin - pad - plan.room, key)
  }
}

// F6 (M6 part C3): Only as handout. One line in the adventure PDF where the
// handout is given out: "Give out Handout 1 · title".
#let give-out(f, labels) = block(above: 1.1em, below: 1.1em, breakable: false, {
  text(size: 9pt, fill: accent, weight: "bold", sym.arrow.r + " ")
  small-caps-label([#label(labels, "print.give-out").replace("{n}", "")#f.number], fill: accent)
  text(size: 9.5pt, fill: accent)[ · #emph(f.title)]
})

#let render(f, body, labels) = {
  let style = f.at("style", default: "gm")
  if style == "player" { sheet(f, body, labels) } else if style == "easy" { sheet(f, body, labels, easy: true) } else if style == "give-out" {
    give-out(f, labels)
  } else {
    gm(f, body, labels)
  }
}
