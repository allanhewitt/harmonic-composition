# Rhythmic counterpoint family v0.1

Status: implemented in `engine/counterpoint.py` (26 November 2026). Design sources: Music_Vault docs 03 (Rhythmic
Counterpoint), 04 (Pitch Assignment and Generator Integration) and 06 (Decisions and Experiments), and the
mock-ups agreed on 26 November 2026. All weights are design choices, not measured values.

## Purpose

Reconstructs the rhythm-first, pitch-later method: four monophonic voices are composed as rhythm, then given pitch.
The interplay between the voices is the musical subject. The family stands on its own: a piece can use only these
voices, with or without the 960 bass. It reads the piece's structure (phrases, section repeats) and harmony, but
**evolves independently** of the shared density plan used by pads, lines, bass and sequencers. It is off by default
(`rhythm: {enabled: true}` turns it on). Voices are written for soft synths and sampled instruments.

## Stage 1: rhythm

| Setting | Meaning |
|---|---|
| `density` (per voice) | share of onset slots (on `grid`) that start a note |
| `density_change` | the full swing of density over the piece, in percentage points |
| `participation` | share of time sounding |
| `participation_change` | the full swing of participation |
| `grid` / `shortest` | onset spacing and shortest note (crotchet, quaver, semiquaver) |
| `conventionality` | 0-100: how strongly onsets favour strong beats; the leading voice is the most metrical |
| `interdependence` | 0-100: later voices avoid earlier voices' onsets; how strictly coordinated cycles are offset |
| `evolution` | `coordinated` (offset cycles: one voice thins as another fills), `independent` (each drifts), `steady` |
| `window`, `cycle` | bars between target changes; bars per coordinated cycle |
| `repetition` | 0-100: how closely returning sections keep their rhythm and intervals |

Decisions on the open questions in doc 06:

- **Density** counts onsets on the grid; **participation** counts sounding time. They are independent: a dense voice
  can be detached, a sparse one sustained.
- **DensityChange / ParticipationChange** are the full swing around the target. The current value is set per phrase
  from the voice's trajectory, sampled every `window` bars.
- **Feasibility**: each note is either held to the next onset or short (one grid step, or the shortest note when
  needed). Strong-beat notes are held first until participation is met. If the onsets cannot reach the target, the
  phrase is reported in the part's `warnings`; targets are never silently changed.
- **Conventionality** shapes onset choice (metric weighting) and the leading voice's anchoring on phrase starts.
  Phrase structure comes from the piece's structure, not from separate settings.
- **Interdependence** works at two time scales: onset avoidance within the bar, and offset trajectories across the
  piece.
- **Motifs**: the first time a section's phrase is written its onsets are stored; when the section returns, the
  phrase keeps those onsets, varies a few (less as `repetition` rises), and gains or loses notes to meet the current
  density. Weakest beats go first; strongest beats join first. Change is gradual.

## Stage 2: pitch

The agreed interface: each voice's notes go to a pitch engine, which returns one pitch per note and changes nothing
else. Engines can use the harmony (or a static home key), the register, previous pitches, phrase position and the
pitches of the voices above.

| Engine | Method |
|---|---|
| `markov` (default) | first-order chain over intervals in scale steps; the table gives the chance of the next interval given the previous one |
| `step` | a pattern of chord-ladder values (root, 3rd, 5th, 7th, octave ...), advanced only by notes; rests use no steps |
| arpeggiator, random walk, learned tables | later |

Markov tables: `smooth` (default), `angular`, `narrow`, `wide`, or a custom 9 x 9 list in the script (rows: previous
interval -4..+4, columns: next interval; ±4 means four or more steps; rows are normalised). The default:

| prev \ next | ≤−4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | ≥+4 |
|---|---|---|---|---|---|---|---|---|---|
| ≤−4, −3 | .01 | .01 | .03 | .08 | .04 | .67 | .09 | .04 | .02 |
| −2 | .02 | .04 | .11 | .24 | .06 | .32 | .14 | .04 | .02 |
| −1 | .02 | .04 | .09 | .39 | .05 | .24 | .10 | .04 | .02 |
| 0 | .03 | .05 | .12 | .28 | .03 | .28 | .12 | .05 | .03 |
| +1 | .02 | .04 | .10 | .24 | .05 | .39 | .09 | .04 | .02 |
| +2 | .02 | .04 | .14 | .32 | .06 | .24 | .11 | .04 | .02 |
| +3, ≥+4 | .02 | .04 | .09 | .67 | .04 | .08 | .03 | .01 | .01 |

### How the rhythm shapes the pitch

| Rhythmic information | Effect on pitch |
|---|---|
| Beat strength and length | strong or long notes are pulled to chord tones by `adherence` (0-1, default 0.4); weak short notes are free |
| Gap before the note | quick successions favour steps; a note after half a bar or more may leap |
| Phrase position | the last note of a phrase aims for a chord tone; the piece's last note aims for the tonic |
| Returning phrases | replay their interval sequence from a new starting note (`repetition`) |
| Shared onsets | no unison or octave with a voice above; contrary motion preferred |
| Simultaneous notes | a voice never sounds at or above the voice above it |
| Lowest voice | favours chord roots on strong notes |
| Rest of a bar or more | the chain's direction resets |

`follow: chords` uses the harmonic engine's progression; `follow: static` uses the home key's scale and tonic triad,
for voices over a drone or bass alone.

## Output

Parts have kind `voice` (ids `rv1`-`rv4`), default channels 0, 1, 3 and 4 (shared with pads and lines in the combined
file when those families are also on; per-part files are separate). Each part also carries `targets` (phrase start,
density and participation targets) and `warnings` (infeasible phrases). The density filter does not thin the voices:
the family has its own density.

## Later

Range following the density curve; arpeggiator and random-walk engines; any of the nine sequencers as a pitch engine
for a voice; second-order or learned tables (from the user's own MIDI or ABC melodies); per-section settings.
