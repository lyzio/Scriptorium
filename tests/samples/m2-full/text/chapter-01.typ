= Act one: The bell in the fog

The fishing boats have stayed in port since Sunday. Åsa, Märta and Örjan wait on the jetty.

#scene(title: "The harbour", location: "Skärvik harbour, early morning", present: "Harbour master Lovisa Berg", id: "s-harbour")[
#read-aloud[
Fog lies thick over the water. Somewhere out in the bay a ship's bell rings, slow and steady, though no ship has been seen for three days.
]

Roll #dice(dice: "D6") when the bell rings; on a #dice(dice: "D6", face: 6) the fog lifts for a moment.

#information(variant: "secret")[The bell belongs to the Hoppet, which sank with all hands forty years ago.]

#person(name: "Lovisa Berg", mood: "Tired and stubborn", description: [Harbour master for twenty years. Lost a brother at sea.], linked-to: "The harbour, the Hoppet")[
#information(variant: "public")[No boat has gone out since Sunday.]
#information(variant: "secret")[She heard her brother's voice in the fog last night.]
]

#check(roll: "Vigilance", difficulty: "hard")[The characters hear oars that are not their own.]

#dice(dice: "D6")[Roll each round on the water: on a six a wave sweeps over the boat.]

#table(
  columns: 2,
  table.header([Day], [Event]),
  [Sunday], [The bell starts ringing],
  [Monday], [Lovisa closes the harbour],
)

#image("/assets/images/bell.png")
]

#scene(title: "The chapel", location: "The fishermen's chapel on the hill", present: "Sexton Nils Ek")[
#countdown(title: "The night of the bell")[
#countdown-step(when: "Dusk")[The bell rings for the first time.]
#countdown-step(when: "Midnight", go-to: "s-harbour")[The sexton runs down to the harbour.]
#countdown-step[The fog reaches the chapel.]
]

#creature(name: "The drowned bell-ringer", type: "Vaesen", might: 4, body-control: 2, magic: 3, manipulation: 3, fear: 2, description: [A sailor of the Hoppet, grey with salt and silent as the fog.], skills: [Stealth 3, Vigilance 2], magic-powers: [_Fog._ Calls the fog in from the sea.], attacks: [Cold grip: the victim is Exhausted.], weaknesses: [Daylight and church bells.], conditions: [Wet, Cold.], banishment: [Ring the chapel bell at dawn while his name is read aloud.])

#handout(title: "The sexton's note", written-by: "Nils Ek", paper: "plain")[
Come to the chapel before the bell rings again. Bring a candle for the drowned.
]
]
