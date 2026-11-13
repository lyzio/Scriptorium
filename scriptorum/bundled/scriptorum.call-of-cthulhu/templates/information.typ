// 11.3 Information: Secret, Public or Hint. A secret is drawn in the secret
// box, a hint or public information in the open curl frame (F8). Inside a
// person card it is a short line with the variant's icon.

#import "_style.typ": variant-styles, label, small-caps-label, icon, in-card, curl-frame, secret-frame, secret-text, spacing, gap

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
      body
    })
  } else if f.variant == "secret" {
    secret-frame(title: name, secret-text(body), fill: f.at("fill", default: "grey"), labels: labels)
  } else {
    curl-frame(title: name, body, seed: if f.variant == "hint" { 11 } else { 17 })
  }
}
