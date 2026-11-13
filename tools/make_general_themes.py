"""Write the general themes from the Vaesen theme's templates (F8, M4; the
Plain theme from M5).

The three bundled themes share their templates: every template draws
through _style.typ, and each theme's _style.typ differs (colours, fonts,
frames, ornaments). This tool copies the Vaesen templates into
scriptorum.legends-and-lattes and scriptorum.call-of-cthulhu, writes their
_style.typ (the Vaesen file with the theme's own colours, fonts and frames),
and the vendored fletcher package for the relationship chart (D15).

Run it again after changing a shared template:  python tools/make_general_themes.py
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

BUNDLED = Path(__file__).resolve().parent.parent / "scriptorum" / "bundled"
BASE = BUNDLED / "scriptorum.vaesen"

HEADER = re.compile(r"// --- colours -.*?#let secret-text\(body\) = [^\n]*\n", re.S)

LATTES_HEAD = r'''// --- colours -------------------------------------------------------------------
// Legends and Lattes (approved mockup 12.8): coffee brown and cream with sage.
#let ink = rgb("#2E2620")
#let accent = rgb("#5A3A24")    // coffee brown
#let quiet = rgb("#6F6258")
#let rust = rgb("#8A4B2E")
#let ochre = rgb("#7E6330")
#let wine = rgb("#6E8B5E")      // sage green
#let sage = rgb("#6E8B5E")
#let band = rgb("#F6EFE1")
#let rule-tint = rgb("#C9B8A0")
#let fills = (grey: rgb("#F1EFEA"), beige: rgb("#F6EEDC"))
#let pacing-tint = rgb("#FBF6EC") // faint cream
#let box-fill = fills.grey
#let table-tint = band

#let variant-styles = (
  secret: (color: accent, tint: fills.grey),
  public: (color: sage, tint: rgb("#EDF1E8")),
  hint: (color: rgb("#7A6A3A"), tint: rgb("#F3EEDF")),
)

// --- fonts (SIL OFL, static weights) ----------------------------------------------
#let fonts = (
  body: "Lora",
  read: "Lora",
  head: "Fraunces 9pt",
  label: "Nunito",
  display: ("Fraunces 9pt",),
  quote: "Lora",
  easy: "Lora",
)
#let sizes = (body: 9.5pt, read: 10.5pt, label: 7.4pt, act: 26pt, scene: 14.5pt, title: 34pt)
#let secret-text(body) = text(font: fonts.read, size: 10pt, style: "italic", body)
'''

CTHULHU_HEAD = r'''// --- colours -------------------------------------------------------------------
// Call of Cthulhu (approved mockup 12.9): ink black and sepia with a single
// sickly-green accent.
#let ink = rgb("#1E1B18")
#let accent = rgb("#3B2F25")    // dark sepia
#let quiet = rgb("#665A4E")
#let rust = rgb("#7A3A22")
#let ochre = rgb("#6E5A33")
#let wine = rgb("#9A2A20")      // the red CLASSIFIED stamp
#let green = rgb("#5E7A2E")     // the one accent colour
#let band = rgb("#F1ECE2")
#let rule-tint = rgb("#B8AC98")
#let fills = (grey: rgb("#EDEBE6"), beige: rgb("#F1E6CC"))  // manila when beige
#let pacing-tint = rgb("#F1F1EF")
#let box-fill = fills.grey
#let table-tint = band

#let variant-styles = (
  secret: (color: wine, tint: fills.grey),
  public: (color: accent, tint: rgb("#EEEBE5")),
  hint: (color: green, tint: rgb("#ECF0E4")),
)

// --- fonts (SIL OFL; Special Elite Apache 2.0) ----------------------------------------
#let fonts = (
  body: "EB Garamond",
  read: "EB Garamond",
  head: "IM FELL English",
  label: "Special Elite",
  display: ("IM FELL English",),
  quote: "EB Garamond",
  easy: "EB Garamond",
)
#let sizes = (body: 10.5pt, read: 11.5pt, label: 7.8pt, act: 26pt, scene: 15pt, title: 36pt)
#let secret-text(body) = text(font: fonts.body, size: 10.5pt, body)
'''

LATTES_FRAMES = r'''
// --- Legends and Lattes frames (approved mockup 12.8) -------------------------------
#let bullet = box(baseline: 0.1em, ornament("bean.svg", height: 0.62em))
#let framed-text(body) = frame-par({
  set list(marker: bullet, body-indent: 0.5em)
  labelize(body)
})

// Rounded sage frames with a leaf sprig on the corner.
#let curl-frame(title: none, body, seed: 3, above: 1.1em, below: 1.1em, breakable: false) = block(
  width: 100%, breakable: breakable, above: above, below: below,
  stroke: 0.9pt + sage, radius: 7pt, inset: (x: 10pt, top: 10pt, bottom: 9pt), {
    place(top + right, dx: 13pt, dy: -14pt, ornament("leaf.svg", width: 20pt))
    if title != none { align(center, caps-label(title, fill: sage, size: 8.8pt)); v(0.25em) }
    framed-text(body)
  })

// The secret: a pinned, folded note with a pale coffee-ring stain.
#let secret-frame(title: none, body, fill: "grey", seed: 5, above: 1.3em, below: 1.1em, labels: (:), stamp: true) = {
  let paint = fills.at(if fill == "beige" { "beige" } else { "grey" })
  block(width: 100%, breakable: false, above: above, below: below, layout(size => {
    let w = size.width
    let inner = block(width: w - 26pt, {
      if title != none { align(center, spaced-caps(title)); v(0.35em) }
      framed-text(body)
    })
    let h = measure(inner).height + 30pt
    box(width: w, height: h, {
      pdf.artifact({
        place(top + left, polygon(fill: paint, stroke: 0.7pt + accent, (0pt, 0pt), (w - 16pt, 0pt), (w, 16pt), (w, h), (0pt, h)))
        place(top + left, polygon(fill: white, stroke: 0.7pt + accent, (w - 16pt, 0pt), (w - 16pt, 16pt), (w, 16pt)))
        place(top + left, dx: w - 34pt, dy: h - 40pt, circle(radius: 15pt, stroke: (paint: accent.transparentize(84%), thickness: 3pt)))
        place(top + left, dx: w / 2 - 4pt, dy: -4pt, circle(radius: 4pt, fill: rust, stroke: 0.5pt + accent))
      })
      place(top + left, dx: 13pt, dy: 17pt, inner)
    })
  }))
}

// Read-aloud on a dotted menu card.
#let read-aloud-frame(heading, body) = block(
  width: 100%, breakable: false, fill: rgb("#FFFDF7"), radius: 4pt,
  stroke: (paint: accent, thickness: 0.8pt, dash: "dotted"),
  inset: (x: 12pt, y: 8pt), above: 1.1em, below: 1.1em, {
    align(center, small-caps-label(heading))
    v(spacing.small)
    frame-par(text(font: fonts.read, size: sizes.read, style: "italic", body))
  })

// Pacing note: thin sage border with rounded corners, faint cream tint,
// coffee-brown hourglass.
#let pacing-frame(body) = block(
  width: 100%, breakable: false, fill: pacing-tint, stroke: 0.5pt + sage, radius: 5pt,
  inset: (x: 8pt, y: 7pt), above: 1em, below: 1em,
  grid(columns: (14pt, 1fr), column-gutter: 8pt, align: (center + horizon, left),
    ornament("hourglass.svg", width: 11pt), frame-par(text(size: 0.95em, body))))

// Act headings between two steaming coffee cups.
#let act-heading(body) = {
  set text(font: fonts.display, size: sizes.act, weight: "bold", fill: accent, hyphenate: false)
  set par(justify: false, leading: 0.4em)
  align(center, grid(columns: (auto, auto, auto), column-gutter: 10pt, align: horizon,
    ornament("cup.svg", width: 24pt), body, ornament("cup.svg", width: 24pt)))
}

// A small cup beside the page number.
#let page-number(n) = box({
  box(baseline: 0.2em, ornament("cup.svg", width: 9pt))
  h(4pt)
  text(font: fonts.label, size: 8pt, fill: quiet, n)
})
'''

CTHULHU_FRAMES = r'''
// --- Call of Cthulhu frames (approved mockup 12.9) ------------------------------------
#let bullet = box(baseline: 0.05em, ornament("diamond.svg", height: 0.55em))
#let framed-text(body) = frame-par({
  set list(marker: bullet, body-indent: 0.5em)
  labelize(body)
})

// Frames with corner brackets.
#let curl-frame(title: none, body, seed: 3, above: 1.1em, below: 1.1em, breakable: false) = block(
  width: 100%, breakable: breakable, above: above, below: below, inset: (x: 11pt, top: 11pt, bottom: 10pt), {
    let b = 12pt
    place(top + left, dx: -11pt, dy: -11pt, ornament("bracket.svg", width: b))
    place(top + right, dx: 11pt, dy: -11pt, pdf.artifact(rotate(90deg, image("../ornaments/bracket.svg", width: b))))
    place(bottom + right, dx: 11pt, dy: 10pt, pdf.artifact(rotate(180deg, image("../ornaments/bracket.svg", width: b))))
    place(bottom + left, dx: -11pt, dy: 10pt, pdf.artifact(rotate(270deg, image("../ornaments/bracket.svg", width: b))))
    if title != none { align(center, caps-label(title, size: 9pt)); v(0.25em) }
    framed-text(body)
  })

// The secret: a manila case file with a red CLASSIFIED stamp (a printed word).
#let secret-frame(title: none, body, fill: "grey", seed: 5, above: 1.3em, below: 1.1em, labels: (:), stamp: true) = {
  let paint = fills.at(if fill == "beige" { "beige" } else { "grey" })
  block(width: 100%, breakable: false, above: above + 6pt, below: below, layout(size => {
    let w = size.width
    let inner = block(width: w - 24pt, {
      if title != none { spaced-caps(title, size: 8pt); v(0.4em) }
      framed-text(body)
    })
    let h = measure(inner).height + 30pt
    box(width: w, height: h, {
      pdf.artifact({
        place(top + left, dx: 0pt, dy: -8pt, rect(width: 62pt, height: 12pt, fill: paint, stroke: 0.7pt + accent, radius: (top: 3pt)))
        place(top + left, rect(width: w, height: h, fill: paint, stroke: 0.8pt + accent))
        if stamp { place(top + right, dx: -10pt, dy: 6pt, rotate(-8deg, box(stroke: 1.2pt + wine.transparentize(15%), inset: (x: 5pt, y: 3pt),
          text(font: fonts.label, size: 9pt, tracking: 0.12em, fill: wine.transparentize(15%), upper(labels.at("print.classified", default: "Classified"))))))}
      })
      place(top + left, dx: 12pt, dy: 16pt, inner)
    })
  }))
}

// Read-aloud as a torn newspaper clipping.
#let read-aloud-frame(heading, body) = block(width: 100%, breakable: false, above: 1.2em, below: 1.2em, layout(size => {
  let w = size.width
  let inner = block(width: w - 22pt, {
    align(center, text(font: fonts.head, size: 11pt, fill: ink, upper(heading)))
    v(0.15em)
    line(length: 100%, stroke: 0.5pt + ink)
    v(0.25em)
    frame-par(text(font: fonts.read, size: 10pt, body))
  })
  let h = measure(inner).height + 22pt
  let n = calc.max(8, int(w / 7pt))
  let edge-top = range(n + 1).map(i => (w * i / n, if calc.even(i) { 0pt } else { 3pt } + _noise(seed-of(heading), i) * 2pt))
  let edge-bottom = range(n + 1).rev().map(i => (w * i / n, h - (if calc.even(i) { 0pt } else { 3pt }) - _noise(7, i) * 2pt))
  box(width: w, height: h, {
    pdf.artifact(place(top + left, polygon(fill: rgb("#FBFAF6"), stroke: 0.5pt + quiet, ..edge-top, ..edge-bottom)))
    place(top + left, dx: 11pt, dy: 12pt, inner)
  })
}))

// Pacing note: thin dashed sepia border, faint grey tint, ink-black
// hourglass with green sand.
#let pacing-frame(body) = block(
  width: 100%, breakable: false, fill: pacing-tint, stroke: (paint: accent, thickness: 0.5pt, dash: "dashed"),
  inset: (x: 8pt, y: 7pt), above: 1em, below: 1em,
  grid(columns: (14pt, 1fr), column-gutter: 8pt, align: (center + horizon, left),
    ornament("hourglass.svg", width: 11pt), frame-par(text(size: 0.95em, body))))

// Act headings under an occult sigil with a double rule.
#let act-heading(body) = {
  set text(font: fonts.display, size: sizes.act, weight: "regular", fill: ink, hyphenate: false)
  set par(justify: false, leading: 0.4em)
  align(center, ornament("sigil.svg", width: 30pt))
  align(center, block(width: 100%, above: 0.3em, below: 0.25em, body))
  align(center, box(width: 50%, height: 2.6pt, stroke: (top: 0.9pt + ink, bottom: 0.4pt + ink)))
}

#let page-number(n) = text(font: fonts.label, size: 8pt, fill: quiet, [— #n —])
'''

PLAIN_HEAD = r'''// --- colours -------------------------------------------------------------------
// Plain (F8, decided 11 November 2026, built in M5): black text on white with
// one mid-grey for rules and fills. Nothing here is a colour, so the theme
// prints sharply on any black-and-white printer.
#let ink = rgb("#000000")
#let grey = rgb("#6B6B6B")      // the one mid-grey: rules, frames, small labels
#let accent = ink
#let quiet = grey
#let rust = ink
#let ochre = ink
#let wine = ink
#let band = luma(243)
#let rule-tint = grey
#let fills = (grey: luma(236), beige: luma(236))  // the secret box is pale grey either way
#let pacing-tint = luma(246)
#let box-fill = fills.grey
#let table-tint = band

#let variant-styles = (
  secret: (color: ink, tint: fills.grey),
  public: (color: ink, tint: fills.grey),
  hint: (color: ink, tint: fills.grey),
)

// --- fonts (SIL OFL, static weights; the bundled fonts only) ---------------------------
#let fonts = (
  body: "Libre Baskerville",
  read: "Libre Baskerville",
  head: "Playfair Display",
  label: "Playfair Display",
  display: ("Playfair Display",),
  quote: "Libre Baskerville",
  easy: "Libre Baskerville",
)
#let sizes = (body: 9.5pt, read: 9.5pt, label: 7.4pt, act: 26pt, scene: 15pt, title: 36pt)
#let secret-text(body) = text(font: fonts.body, size: sizes.body, body)
'''

PLAIN_FRAMES = r'''
// --- Plain frames (F8): no ornaments, thin single rules ----------------------------------
#let quote-tint = luma(244)
#let hand-ink = ink
#let bullet = [•]
#let framed-text(body) = frame-par({
  set list(marker: bullet, body-indent: 0.5em)
  labelize(body)
})

// Frames are thin single rules.
#let curl-frame(title: none, body, seed: 3, above: 1.1em, below: 1.1em, breakable: false) = block(
  width: 100%, breakable: breakable, above: above, below: below,
  stroke: 0.7pt + grey, inset: (x: 9pt, top: 9pt, bottom: 8.5pt), {
    if title != none { align(center, caps-label(title, size: 8.8pt)); v(0.25em) }
    framed-text(body)
  })

// The secret box: a thin double rule on a pale grey fill, its title in spaced
// small capitals.
#let secret-frame(title: none, body, fill: "grey", seed: 5, above: 1.3em, below: 1.1em, labels: (:), stamp: true) = block(
  width: 100%, breakable: false, above: above, below: below,
  fill: fills.grey, stroke: 0.7pt + grey, inset: 2.4pt,
  block(width: 100%, stroke: 0.5pt + grey, inset: (x: 10pt, top: 9pt, bottom: 9pt), {
    if title != none { align(center, spaced-caps(title)); v(0.45em) }
    framed-text(body)
  }))

// Read-aloud text in italics with a rule at the left.
#let read-aloud-frame(heading, body) = block(
  width: 100%, breakable: false, stroke: (left: 1.4pt + grey),
  inset: (left: 10pt, right: 2pt, y: 4pt), above: 1.1em, below: 1.1em, {
    small-caps-label(heading, fill: quiet)
    v(spacing.small)
    frame-par(text(font: fonts.read, size: sizes.read, style: "italic", body))
  })

// Pacing note: a thin grey border and a faint grey tint; no hourglass, since
// the Plain theme has no ornaments.
#let pacing-frame(body) = block(
  width: 100%, breakable: false, fill: pacing-tint, stroke: 0.5pt + grey,
  inset: (x: 8pt, y: 7pt), above: 1em, below: 1em, frame-par(text(size: 0.95em, body)))

// Act headings: bold, centred, over a thin rule.
#let act-heading(body) = {
  set text(font: fonts.display, size: sizes.act, weight: "bold", fill: ink, hyphenate: false)
  set par(justify: false, leading: 0.4em)
  align(center, block(width: 100%, below: 0.3em, body))
  align(center, box(width: 40%, line(length: 100%, stroke: 0.7pt + grey)))
}

#let page-number(n) = text(font: fonts.head, size: 8pt, fill: quiet, n)
'''


def grey_of(colour: str) -> str:
    # The same lightness as a colour, as a grey (for the Plain theme's papers).
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    v = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return "#{0:02X}{0:02X}{0:02X}".format(v)


def write_plain_extras() -> None:
    # The Plain theme's fonts and papers come from the Vaesen theme: its text
    # and heading fonts with their licences, and its four papers in greys.
    target = BUNDLED / "scriptorum.plain"
    fonts = target / "fonts"
    shutil.rmtree(fonts, ignore_errors=True)
    fonts.mkdir(parents=True)
    for file in sorted((BASE / "fonts").iterdir()):
        if file.name.startswith(("LibreBaskerville", "PlayfairDisplay")):
            shutil.copy2(file, fonts / file.name)
    handouts = json.loads((BASE / "handouts.json").read_text("utf-8"))
    text = json.dumps(handouts, ensure_ascii=False, indent=2)
    text = re.sub(r"#[0-9A-Fa-f]{6}", lambda m: grey_of(m.group(0)), text)
    data = json.loads(text)
    data["rules"] = "F6.5: the paper is never filled with a colour. The Plain theme draws the Vaesen theme's four papers in greys, so they print on any black-and-white printer (F8)."
    (target / "handouts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


# A seed from a piece of content, for the clipping's torn edge.
SEED_OF = r'''
#let seed-of(c) = if type(c) == str { c.len() } else { 3 }
'''


def write_theme(theme_id: str, head: str, frames: str) -> None:
    target = BUNDLED / theme_id
    templates = target / "templates"
    shutil.rmtree(templates, ignore_errors=True)
    shutil.copytree(BASE / "templates", templates)
    style = (BASE / "templates" / "_style.typ").read_text("utf-8")
    style, count = HEADER.subn(lambda _m: head, style)
    assert count == 1, "the colour and font block of the Vaesen _style.typ was not found"
    style = style.replace("// Shared look of the Vaesen theme", f"// Shared look of the {theme_id} theme, written by tools/make_general_themes.py from the Vaesen theme", 1)
    # The Vaesen bullet loads nib.svg, which the other themes do not have.
    style = style.replace('#let bullet = box(baseline: 0.12em, ornament("nib.svg", height: 0.78em))\n', "")
    # The frames are appended: Typst exports the last definition of a name.
    style = style.replace("// Page furniture: the page number at the foot.\n#let page-number(n) = text(font: fonts.head, size: 8pt, fill: quiet, [· #n ·])\n", "")
    (templates / "_style.typ").write_text(style + SEED_OF + frames, "utf-8")
    shutil.rmtree(target / "vendor", ignore_errors=True)
    shutil.copytree(BASE / "vendor", target / "vendor")


def main() -> None:
    write_theme("scriptorum.legends-and-lattes", LATTES_HEAD, LATTES_FRAMES)
    write_theme("scriptorum.call-of-cthulhu", CTHULHU_HEAD, CTHULHU_FRAMES)
    write_theme("scriptorum.plain", PLAIN_HEAD, PLAIN_FRAMES)
    write_plain_extras()


if __name__ == "__main__":
    main()
