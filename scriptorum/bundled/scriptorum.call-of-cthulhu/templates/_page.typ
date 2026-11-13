// Page setup and running text. The build assembler passes the page setup in
// as `cfg`: the theme's page.json, overridden by the adventure settings page
// (F7.3). The look comes from _style.typ (F8).

#import "_style.typ": ink, accent, quiet, fonts, sizes, table-style, act-heading, page-number, spacing, sub-heading-style, sub-heading-space

#let setup(cfg, labels, doc) = {
  // F7.3 (M5): margins are the same on both sides (x), or inside and
  // outside for a book whose pages face each other; a header line, a footer
  // line and the page numbers can be set on the adventure settings page.
  let m = cfg.margin_mm
  let margin = if "inside" in m {
    (top: m.top * 1mm, bottom: m.bottom * 1mm, inside: m.inside * 1mm, outside: m.outside * 1mm)
  } else {
    (top: m.top * 1mm, bottom: m.bottom * 1mm, x: m.x * 1mm)
  }
  let header-text = cfg.at("header", default: "")
  let footer-text = cfg.at("footer", default: "")
  set page(
    paper: cfg.paper,
    flipped: cfg.at("orientation", default: "portrait") == "landscape",
    columns: cfg.columns,
    margin: margin,
    numbering: if cfg.page_numbers { "1" } else { none },
    header: if header-text != "" {
      align(center, text(font: fonts.head, size: 7.5pt, fill: quiet, tracking: 0.08em, header-text))
    } else { none },
    footer: if cfg.page_numbers or footer-text != "" {
      context grid(columns: (1fr, auto, 1fr), align: (left + horizon, center + horizon, right),
        text(size: 7.5pt, fill: quiet, footer-text),
        if cfg.page_numbers { page-number(counter(page).display()) },
        [])
    } else { none },
  )
  set columns(gutter: cfg.column_gap_mm * 1mm)
  set text(font: (cfg.font, fonts.body), size: cfg.font_size_pt * 1pt, fill: ink, lang: cfg.at("lang", default: "en"))
  // F8 (M6 part C): line and paragraph spacing come from the theme's
  // spacing in _style.typ (about 0.8 em and 1.2 em; was 0.62 em and 0.9 em).
  set par(justify: true, leading: spacing.leading, spacing: spacing.paragraph)
  // F4.5: the header row repeats on every page; F8: bands and brown rules.
  show: table-style
  // A chapter (act) title spans both columns and is never hyphenated (F7.4).
  // F17 (M5): the title page's title is a heading the title page draws itself.
  show heading.where(level: 1): it => if it.has("label") and it.label == <scriptorum-title-heading> { it } else { place(
    top + center,
    scope: "parent",
    float: true,
    clearance: 1.4em,
    act-heading(it.body),
  ) }

  show heading: set text(hyphenate: false)
  // F4, F7.7 (M6 part C): Sub-heading 1, 2 and 3. Each is a real heading
  // (levels 3 to 5), so it is a bookmark nested under its scene and a tagged
  // heading for screen readers (F17); sticky keeps it with what follows.
  // M6 part C3: outside a scene the build writes a sub-heading one level
  // higher with a label naming its style, so it sits under its act with no
  // level skipped and still looks like a sub-heading.
  let sub-block(n, body) = block(above: sub-heading-space.at(n - 3).above, below: sub-heading-space.at(n - 3).below,
    sticky: true, sub-heading-style(n, body))
  let sub-of(it) = if it.has("label") {
    ("scriptorum-sub-1": 3, "scriptorum-sub-2": 4, "scriptorum-sub-3": 5).at(str(it.label), default: none)
  } else { none }
  show heading.where(level: 2): it => {
    let s = sub-of(it)
    if s != none { sub-block(s, it.body) } else {
      set text(font: fonts.head, size: 13pt, weight: "bold", fill: accent)
      block(above: 0.9em, below: 0.5em, it.body)
    }
  }
  show heading.where(level: 3): it => { let s = sub-of(it); sub-block(if s != none { s } else { 3 }, it.body) }
  show heading.where(level: 4): it => { let s = sub-of(it); sub-block(if s != none { s } else { 4 }, it.body) }
  show heading.where(level: 5): it => sub-block(5, it.body)
  doc
}
