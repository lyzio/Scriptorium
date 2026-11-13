// 11.3 Information: Secret, Public or Hint. A secret is drawn in the secret
// box, a hint or public information in the open curl frame (F8). Inside a
// person card it is a short line with the variant's icon.

#import "_style.typ": variant-styles, label, small-caps-label, icon, in-card, curl-frame, secret-frame, secret-text, spacing, gap, clue-mark

// F3 (M6 part C4): a clue Information shows the small clue mark and the
// clue's name before its text. Without a clue nothing changes.
#let clue-line(f, color) = {
  let name = f.at("clue", default: none)
  if name != none { [#clue-mark(color)#h(0.3em)#text(weight: "bold", fill: color, name)] }
}

#let render(f, body, labels) = context {
  let style = variant-styles.at(f.variant)
  let name = label(labels, "print.information." + f.variant)
  if in-card.get() {
    // A small gap between the things a person knows (F8, M6 part C).
    block(above: gap(spacing.small), below: 0pt, {
      icon(f.variant, style.color)
      h(0.35em)
      small-caps-label(name, fill: style.color)
      h(0.45em)
      if f.at("clue", default: none) != none { clue-line(f, style.color); h(0.4em) }
      body
    })
  } else if f.variant == "secret" {
    let inner = if f.at("clue", default: none) == none { secret-text(body) } else {
      secret-text[#clue-line(f, style.color)#parbreak()#body]
    }
    secret-frame(title: name, inner, fill: f.at("fill", default: "grey"), labels: labels)
  } else {
    let inner = if f.at("clue", default: none) == none { body } else [#clue-line(f, style.color)#parbreak()#body]
    curl-frame(title: name, inner, seed: if f.variant == "hint" { 11 } else { 17 })
  }
}
