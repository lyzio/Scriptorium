// 11.11 Quote: Framed (default), Scrap of paper or Plain, with an optional
// title, the signature right-aligned after a dash and a short description
// centred under the block in small capitals. Line breaks are kept, so verses
// stay verses. A tilt of −5° to +5° turns the quote; the room around it
// keeps clear. Never a handout. Screen readers read it as a quotation and
// skip the frame and the paper (F17.4).

#import "_style.typ": accent, quiet, blank, fonts, sizes, spaced-caps, secret-frame, quote-tint, hand-ink
#import "handout.typ": draw-sheet

// A pale parchment tint: allowed here, since a quote is never a handout
// (F6.5 applies to handouts only).
#let tint-colour = quote-tint

#let quote-text(f, body, centred: true, caps: false) = {
  set par(justify: false, spacing: 0.5em, leading: 0.5em)
  set align(center) if centred
  if f.handwriting != none {
    text(font: (f.handwriting, fonts.quote), size: f.hand-size, fill: hand-ink, body)
  } else if caps {
    text(font: fonts.quote, size: 11.5pt, weight: "medium", smallcaps(body))
  } else {
    text(font: fonts.quote, size: 12.5pt, style: "italic", body)
  }
}

#let signature(f) = if not blank(f.signature) {
  block(above: 0.6em, width: 100%, align(right, text(font: fonts.quote, size: 11pt, style: "italic", [— #f.signature])))
}

#let description(f) = if not blank(f.description) {
  block(above: 0.55em, width: 100%, align(center, spaced-caps([— #f.description], fill: quiet, size: 7.4pt, tracking: 0.14em)))
}

#let title(f) = if not blank(f.title) {
  align(center, spaced-caps(f.title, size: 8.4pt))
  v(0.3em)
}

#let scrap(f, body) = layout(size => {
  let w = size.width * 0.78
  let inner = block(width: w - 18mm, { title(f); quote-text(f, body); signature(f) })
  // Room at the foot for the curled corner, so it never covers the signature.
  let h = measure(inner).height + 27mm
  // A small torn sheet drawn like a handout: torn edge, inner line, curled
  // corner, a fold and a spot ring.
  let sheet = (paper: "letter", seed: f.seed)
  align(center, box(width: w, height: h, {
    draw-sheet(sheet, w, h, tint: if f.tint { tint-colour } else { none })
    place(top + left, dx: 9mm, dy: 9mm, inner)
  }))
})

#let render(f, body, labels) = {
  let look = f.at("look", default: "framed")
  let content = if look == "framed" {
    secret-frame(title: none, { title(f); quote-text(f, body, caps: true); signature(f) }, fill: f.at("fill", default: "grey"), above: 0pt, below: 0pt, labels: labels, stamp: false)
  } else if look == "scrap" {
    scrap(f, body)
  } else {
    pad(x: 8%, y: 0.6em, { title(f); quote-text(f, body); signature(f) })
  }
  block(width: 100%, breakable: false, above: 1.4em, below: 1.2em, {
    if f.tilt == 0 { content } else { align(center, rotate(f.tilt * 1deg, reflow: true, block(width: 92%, content))) }
    description(f)
  })
}
