// 11.10 Box: the open curl frame with an optional title in bold capitals;
// pen-nib bullets; bold text at the start of a line is a label (F8).

#import "_style.typ": curl-frame

#let render(f, body, labels) = curl-frame(title: f.title, body, seed: 31)
