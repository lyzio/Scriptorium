// 11.1 Scene: numbered automatically. Page starts and numbering are decided
// by the core element kit (F7.4); this renderer only draws the scene head:
// "SCENE 2 · CLIMAX" (the Type, from M4), the title, location and people.

#import "_style.typ": accent, label, blank, scene-number, scene-title, caps-label

#let render(f, body, labels) = {
  // Block spacing is dropped at the top of a page, so this only shows when
  // the scene follows on the same page.
  block(width: 100%, breakable: false, above: 2.2em, below: 0.9em, {
    scene-number([#label(labels, "print.scene") #context counter("scriptorum-scene").display()#if not blank(f.at("type", default: none)) [ · #f.type]])
    v(0.15em)
    // F7.7, F17 (M5): the title is the scene's heading (level 2): a PDF
    // bookmark, a line in the contents and a heading for screen readers.
    {
      show heading: it => scene-title(it.body)
      [#heading(level: 2, outlined: false, bookmarked: true, f.title)<scriptorum-scene-heading>]
    }
    v(0.25em)
    if not blank(f.location) {
      [#caps-label(label(labels, "print.location") + ":", size: 7.8pt) #f.location]
    }
    if not blank(f.location) and not blank(f.present) { linebreak() }
    if not blank(f.present) {
      [#caps-label(label(labels, "print.present") + ":", size: 7.8pt) #f.present]
    }
  })
  body
}
