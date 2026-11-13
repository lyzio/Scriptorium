// 11.2 Read-aloud: the heading "Read aloud" (a printed word, D14) above the
// text, which is set in the theme's read-aloud face (F8).

#import "_style.typ": label, read-aloud-frame

#let render(f, body, labels) = read-aloud-frame(label(labels, "print.read-aloud"), body)
