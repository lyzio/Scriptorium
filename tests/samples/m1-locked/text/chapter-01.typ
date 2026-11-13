= Locked code

A normal paragraph before the unknown code.

#let flourish(body) = text(fill: rgb("#4A2F24"), body)
#flourish[Made with a home-made function: ] and some text after it.

// A comment the author wrote for themselves.

#table(columns: 2, [Day], [Event], [Monday], [The wheel stops])

- A list item (lists arrive in M2)
- Another item

#scene(title: "Still editable")[
Text inside a scene with #emph[inline code] stays locked, the rest is editable.

#read-aloud[Read this aloud.]
]
