= Act one: The harbour

#scene(title: "Fog over the quay", place: "c-skarvik-harbour", people: ("c-lovisa-berg",), type: "Encounter", id: "s-quay")[
#quote(variant: "framed", title: "From an old hymn", signature: "Unknown", description: "Sung in the chapel")[
The bell that sleeps beneath the sea

shall wake the drowned to call for thee.
]

The bell rings over #mention(entry: "c-skarvik-harbour") every night. Roll #dice(dice: "d20") to hear where it comes from.

#read-aloud[
The fog lies thick over the quay. Somewhere out in the bay a bell tolls, slow and far too deep. Åsa, Örjan and Märta stop to listen.
]

#information(variant: "secret")[The bell is the ship's bell of the Hoppet, lost forty years ago.]

#information(variant: "hint")[Lovisa knows more than she says.]

#information(variant: "public")[No boat has left the harbour since Tuesday.]

#card(entry: "c-lovisa-berg")[
#information(variant: "secret")[She cut the mooring herself.]
]

#person(name: "Olle the deckhand", mood: "Afraid", description: [A young deckhand who sleeps in the boathouse.])[
#information(variant: "public")[He has seen a light under the water.]
]

#creature(name: "The drowned bell-ringer", type: "Restless dead", stat-lines: "Strength 4\nAgility 2\nWits 3\nArmour 1", description: [A grey shape that climbs the chapel hill at night.], attacks: [*Cold grip:* 2d6 damage.], weaknesses: [Daylight and the sound of the chapel bell.])

#box(title: "Special rule: The tolling")[
*Main skill:* Composure

- *Success:* the character stands firm.
- Failure: the character walks towards the water.
]

#box[
#table(
  columns: 2,
  table.header([Difficulty], [Target]),
  [Easy], [8],
  [Normal], [12],
  [Hard], [16],
)
]

#pacing[Let the characters search the harbour for about *twenty minutes*. If they have not found the oar marks by then, Lovisa points them out.]

#check(roll: "Perception", difficulty: "hard, 16")[On a success the character hears that the bell tolls from under the water.]

#dice(dice: "2d10+1")[Roll for the hour at which the fog lifts.]

#dice(dice: "d100")[Roll under the character's Luck to find a dry match.]

#countdown(title: "The night of the storm")[
#countdown-step(when: "10 pm")[The bell begins to toll.]
#countdown-step(when: "2 am", go-to: "s-chapel")[A light shows under the quay.]
]

For the bell itself, see #see(entry: "c-the-hoppet-bell").

#map(map: "m-skarvik", handout-also: true)

#quote(variant: "scrap", signer: "c-lovisa-berg", tilt: -2)[
Do not go down to the quay after dark.
]

#quote(variant: "plain", handwriting: "Pinyon Script", signature: "Wolf", description: "From the chronicle")[
And the water took the one who listened.
]

#handout(title: "Lovisa's letter", writer: "c-lovisa-berg", paper: "letter", id: "h-letter")[
Skärvik, 3 November.

Dear Sirs,

I write again, for strange things have happened at the harbour. Come before Sunday, I beg you.

Lovisa Berg
]
]

#page-break()

= Act two: The chapel

#scene(title: "The chapel on the hill", place: "c-the-chapel", type: "Climax", id: "s-chapel")[
The chapel stands dark. The characters find the old parish book.

#column-break()

#handout(title: "From the parish book", handwriting: "TT2020 Style E", paper: "parchment", tilt: -1, id: "h-book")[
Anno 1702. The bell was cast from the silver of the drowned.
]

#relationship-chart()
]
