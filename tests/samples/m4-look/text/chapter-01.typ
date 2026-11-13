= Akt ett: Kvarnen

= Akt två: Forsen

#scene(title: "Vid Kvarnån", place: "c-kvarnen", people: ("c-agda-holm",), type: "Encounter", id: "s-kvarnan")[
#quote(variant: "framed", title: "Ur en gammal visa", signature: "Okänd", description: "Sjungen vid Kvarnån")[
Näcken spelar i forsen blå,

ingen vet var hans strängar gå.
]

Sällskapet kommer till kvarnen i skymningen. Här står å, ä och ö i varje rad.

#read-aloud[
Forsen dånar under bron. Någonstans i dimman spelar en fiol, så sorgset att det gör ont.
]

#information(variant: "secret")[Ljuset under vattnet är Näckens lykta. Den som följer det drunknar.]

#information(variant: "hint")[Agda vet mer än hon säger.]

#information(variant: "public")[Ingen har malt säd här sedan i våras.]

#card(entry: "c-agda-holm")[
#information(variant: "secret")[Hon har själv hört fiolen.]
]

#person(name: "Drängen Olle", mood: "Rädd", description: [Ung dräng på kvarnen.])[
#information(variant: "public")[Han har sett en man i vattnet.]
]

#box(title: "Specialregel: Fiolen")[
*Huvudattribut:* Empati

- *Lyckat slag:* rollpersonen står emot lockelsen.
- Misslyckat slag: rollpersonen går mot vattnet.
]

#box[
#table(
  columns: 2,
  table.header([Svårighet], [Modifikation]),
  [Lätt], [+1],
  [Normal], [0],
  [Svår], [−1],
  [Mycket svår], [−2],
)
]

#pacing[Låt sällskapet leta vid ån i ungefär *tjugo minuter*. Har de inte hittat stålnålen då, visar Agda dem var den ligger.]

#check(roll: "Empati + Inspiration", difficulty: "svår")[Den som lyckas hör vad fiolen spelar.]

#dice(dice: "D6")[Slå en tärning varje runda: på en sexa hörs fiolen.]

#countdown(title: "Natten före allhelgona")[
#countdown-step(when: "Kl. 22")[Fiolen börjar spela.]
#countdown-step(when: "Kl. 02", go-to: "s-forsen")[Ljuset syns under bron.]
]

#card(entry: "c-nacken")[
]

#quote(variant: "scrap", signer: "c-agda-holm", tilt: -2)[
Gå inte till ån efter mörkrets inbrott.
]

#quote(variant: "scrap", tint: false, signature: "Drängen Olle")[
Han log mot mig ur vattnet.
]

#quote(variant: "plain", handwriting: "Pinyon Script", signature: "Wolf", description: "Ur krönikan")[
Och vattnet tog den som lyssnade.
]

#handout(title: "Agdas långa brev", writer: "c-agda-holm", paper: "letter", id: "h-agda")[
Kvarnån, den 3 November 1868.

Ärade herrar,

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den första natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den andra natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den tredje natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den fjärde natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den femte natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Jag skrifver åter, ty sedan mitt förra bref hafva underliga ting händt vid kvarnen. Den sjätte natten hörde jag åter fiolen i forsen, och ljuset under vattnet var starkare än förr. Pigan vägrar gå till ån efter mörkrets inbrott, och drängen säger att han sett en man i vattnet, med fiol under hakan och ögon som månsken.

Kom före söndagen, jag beder Eder.

Eder tillgifna Agda Holm
]
]

#scene(title: "Under bron", type: "Climax", id: "s-forsen")[
#handout(title: "Ur kvarnens räkenskapsbok", handwriting: "Pinyon Script", paper: "parchment", tilt: -1, id: "h-bok")[
Anno 1702. Kvarnen stod still i sju dagar, ty mjölnaren hade spelat med Näcken.
]

#handout(title: "En lapp på bron", handwriting: "TT2020 Style E", paper: "plain", tilt: 5, id: "h-lapp")[
Ingen fisk i natt.
]
]
