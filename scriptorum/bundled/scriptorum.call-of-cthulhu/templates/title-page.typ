// F7.9 Title page: the theme decides how it looks. Every field except the
// title is optional and printed only when filled in. The extra row sits at
// the bottom of the page. The title is set in the display face (F8).

#import "_style.typ": accent, quiet, blank, fonts, sizes, spaced-caps

#let render(f, labels) = {
  set align(center)
  set par(justify: false)
  v(1fr)
  if not blank(f.header) {
    spaced-caps(f.header, fill: quiet, size: 9pt)
    v(1.2em)
  }
  // F17 (M5): the title is the document's first heading (level 1) for screen
  // readers and PDF/UA; it looks exactly as before.
  {
    show heading: it => text(font: fonts.display, size: sizes.title, fill: accent, hyphenate: false, weight: "regular", it.body)
    [#heading(level: 1, outlined: false, bookmarked: false, f.title)<scriptorum-title-heading>]
  }
  if not blank(f.subtitle) {
    v(0.6em)
    text(font: fonts.head, size: 14pt, style: "italic", fill: accent, f.subtitle)
  }
  v(1.4em)
  line(length: 30%, stroke: 0.8pt + accent)
  if not blank(f.author) {
    v(1em)
    text(font: fonts.head, size: 12pt, f.author)
  }
  if not blank(f.description) {
    v(2em)
    block(width: 70%, text(font: fonts.quote, size: 13pt, style: "italic", fill: accent, f.description))
  }
  v(2fr)
  if not blank(f.extra) {
    block(width: 85%, text(size: 9.5pt, fill: quiet, f.extra))
  }
}
