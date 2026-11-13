// 11.6 Countdown: the printed word "Countdown" and the title in ochre.

#import "_style.typ": ochre, label, small-caps-label, blank, spacing, frame-par

#let render(f, body, labels) = block(width: 100%, breakable: false, above: 1.1em, below: 1.1em, {
  small-caps-label(
    if blank(f.title) { label(labels, "print.countdown") } else [#label(labels, "print.countdown") · #f.title],
    fill: ochre,
  )
  v(spacing.small)
  frame-par(body)
})
