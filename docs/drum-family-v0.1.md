# Drum family v0.1

Status: implemented in `engine/drums.py` (26 November 2026), from the mock-ups agreed the same day. References:
Tangerine Dream (machine-exact, sequenced, often sparse), The War on Drugs (driving motorik kit that builds), Future
Islands (drum-machine synth-pop), and ambient, unresolved percussion. All weights are design choices.

## Three engines with fixed characters

| Engine | Character | Signature control |
|---|---|---|
| Drum Machine | exact grid; accents only on accent steps; machine fills (snare roll rising in velocity, ending on a tom) | `style` |
| Drummer | the same skeleton played: hats slightly ahead, snare behind (by `feel`); dynamics rise with the density level; ghost notes and the ride at full level; open hat at phrase ends; tom fills that grow before arrivals. Written for Superior Drummer 3. | `feel` (0-1) |
| Percussion | three to five interlocking lanes (Euclidean, polymetric, chance with deja vu); slow velocity swells | `lanes` |

Styles (Drum Machine and Drummer): `berlin` (semiquaver hats, kick on the strong beats, backbeat), `synthpop`
(quaver hats, pushed kick, snare and clap, tambourine), `motorik` (quaver hats, kick on 1, the and of 2, 3 and the
and of 3), `four` (four on the floor, off-beat hats, clap backbeat), `halftime`, `pulse` (hats and an occasional
sidestick only). Lane sets (Percussion): `shakers_rims`, `metals`, `toms_hands`.

Styles adapt to the meter: hats follow the step grid; the kick takes the strong beats (1, and the middle beat in four
beats); the backbeat takes the weak beats (2 and 4 in 4/4, 2 and 3 in 3/4, the second dotted crotchet in 6/8).

## Shared control: conclusiveness (0-100)

| | High | Low (ambient) |
|---|---|---|
| Downbeat | kick on 1 | no kick on 1 (below 40) |
| Backbeat | snare | occasional sidesticks only (below 30) |
| Section starts | crash (above 50; the piece's start above 70) | none |
| Fills | before phrase ends, more likely and longer before section arrivals or rising density (above 30) | none |
| Percussion cycles | divide the bar | do not divide the bar (e.g. 13, 5, 7, 11 steps); no weight on the downbeat |
| Ending | a final hit (kick and crash) | the last two bars fade |

## Density

The Drum Machine and Drummer follow the shared density plan: level 1 hats only, 2 adds the kick, 3 the snare,
4 the extras (clap, open hat, tambourine, extra kick), 5 ghost notes and (Drummer) the ride. Percussion lanes join
one per level, following the plan (`evolution: plan`) or a slow walk of their own (`evolution: independent`).
The density filter does not thin drums.

## Output

Parts `drums_machine`, `drums_drummer`, `drums_percussion`, kind `drums`, on MIDI channel 10 with no program change.
Notes use the General MIDI drum map (kick 36, sidestick 37, snare 38, clap 39, closed hat 42, pedal hat 44, open hat
46, toms 41-50, crash 49, ride 51 ...), which Superior Drummer 3, Drum Machine Designer and Drum Kit Designer play
without setup. `drums.map` in the script changes any note, for example to use Superior Drummer's extra hi-hat
articulations. Each note keeps its instrument name (`inst`) and grid step (`step`). Scores use a drum staff (hands
above, feet below) on the step grid; ghost notes are bracketed; the Drummer's timing offsets are in the MIDI only.

## Later

Superior Drummer articulation profile (hat edge, shank, snare rimshots); hi-hat openness by controller; more styles
(shuffle, brushes); fills chosen from a phrase bank; per-section style changes; drums as a voice in the rhythm family.
