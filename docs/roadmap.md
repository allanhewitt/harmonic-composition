# Roadmap

## Stage 1: done

Song, structure and harmony (engine v0.7, generator v0.3); pads (2-note and 3-note, root or smooth, clean or hold, G3-E5);
shared density plan with a constant pad and the other pad entering voice by voice; Moog 960 bass (Berlin School techniques:
step add/drop by density, odd lengths, transposition fitted or strict, pattern bank per section, gradual mutation);
tenor, alto and descant lines (rhythm by phrase, guide-tone and melodic pitch); density filter (even, flatten, contrast;
constant pad exempt); LilyPond score; MIDI; piece scripts; web app.

## Stage 2: in progress

**Done:** the sequencer framework (`seqcore.py`: abstract values in chord or scale space; adapted, transposed and
independent harmonic modes; register and instrument profiles; density from the shared plan; section variants, resets and
gradual change; monophony and slides) and the first engine, **Seq 960** (`seq960.py`: three assignable rows, Play / Rest /
Skip / Stop). One instance of each sequencer, each on by default (script section `sequencers:`). Test fixtures
(`fixtures.py`: C-F-G-C and any triad progression). The other eight engines (`seqengines.py`): **Euclidean,
Polymetric, TB-303, Turing Machine, Metropolix, Marbles, René, Nodal**, each with a fixed character and one
signature control. Every sequencer can follow the chords or stay static in the home key, and the density filter
thins sequencers by pattern step, so the same steps fall silent throughout.

**Decided:** the TR-808 becomes a separate **drum family** (with the Groove drummer), not one of the sequencers.
Sequencers are aimed at soft synths (Diva, Repro-1, Repro-5 and others); the Model D bass stays its own family.

**Done (26 November 2026):** the **rhythmic counterpoint family** (`counterpoint.py`, design in
`docs/rhythm-family-v0.1.md`): four voices composed rhythm first (density, participation, their change, conventionality,
interdependence, coordinated or independent evolution, motif repetition by section) and then given pitch by a Markov
interval chain or a step pattern advanced by notes. It evolves independently of the shared density plan.

**Plan agreed 26 November 2026:**

1. **Drum family:** done 26 November 2026 (`drums.py`, design in `docs/drum-family-v0.1.md`): Drum Machine, Drummer
   (for Superior Drummer) and Percussion, with conclusiveness from conclusive to ambient.
2. **Listening sessions in Logic:** run the generator, audition the files with real instruments, and note what sounds
   wrong, dull or promising. Most output so far has been checked by tests and scores, not by ear.
3. **Gap review:** set the next priorities from the listening notes.

Candidates already identified for after the gap review (to be weighed against the listening notes):

- **Regenerate one part, keep the rest:** lock and new-seed controls per family or part in the app, using the
  engine's existing staged acceptance and locks.
- **Quick preview in the browser:** simple playback with per-part mute and a play position on the score; a first step
  towards live mode.
- **Per-section settings** (item 2 below).
- **Run library:** past runs with a rating and a short note, so good results are easy to find again.
- Held back for now: MIDI controller curves for sequencers (e.g. filter sweeps following the density plan), more pitch
  engines and learned tables.


1. **Line embellishments:** a harmonic-adherence setting per line; extensions, suspensions, passing and neighbour notes,
   appoggiaturas, anticipations. (Could come first, as Stage 1.1.)
2. **Per-section settings** in the script (`sections:`) and a sections table in the app.
3. **More pitch engines for the rhythm family:** any of the nine sequencers as a voice's pitch engine, an arpeggiator,
   a random walk, learned or second-order Markov tables.
4. **Rhythm family refinements:** range following the density curve, per-voice relationships (parallel, responsive),
   per-section settings.
5. **Instrument profiles**: the sequencer framework has mono synth, poly synth and no-velocity profiles; extend to named
   instruments (Model D, Kobol, Poly-800, Diva, Repro-1, Repro-5) across all families.
6. **Drum family:** TR-808-style pattern lanes (accents, A/B variations, fills) and the Groove drummer, on MIDI channel 10.
7. **Live mode:** the engine generates a bar or phrase ahead and streams events over a WebSocket; the browser plays them
   through Web MIDI with timestamps (Chrome or Edge). Parameter changes apply from the next bar or phrase.

## Sources

Design history: Music_Vault/Composition/Generative Composition (integration handoff 2026-11-20, documents 03, 04, 06,
source inventory 2026-11-25) and the Experiment 30-32 packages.
