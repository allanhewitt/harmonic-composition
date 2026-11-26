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
(`fixtures.py`: C-F-G-C and any triad progression).

**Decided:** the TR-808 becomes a separate **drum family** (with the Groove drummer), not one of the sequencers.
Sequencers are aimed at soft synths (Diva, Repro-1, Repro-5 and others); the Model D bass stays its own family.

**Next, in order:** Euclidean, Polymetric; TB-303, Turing Machine, Metropolix; Marbles, René, Nodal.

1. **Line embellishments:** a harmonic-adherence setting per line; extensions, suspensions, passing and neighbour notes,
   appoggiaturas, anticipations. (Could come first, as Stage 1.1.)
2. **Per-section settings** in the script (`sections:`) and a sections table in the app.
3. **The remaining sequencer engines** (above), each a mechanism producing steps and abstract values on the shared
   framework; a pitch-assignment mode (values applied to another part's rhythm) comes with rhythm-first composition.
4. **Rhythm-first composition** (documents 03, 04, 06 and `composition.py`): multi-voice rhythmic counterpoint with density,
   participation and interdependence, then pitch assignment by any adapter.
5. **Instrument profiles**: the sequencer framework has mono synth, poly synth and no-velocity profiles; extend to named
   instruments (Model D, Kobol, Poly-800, Diva, Repro-1, Repro-5) across all families.
6. **Drum family:** TR-808-style pattern lanes (accents, A/B variations, fills) and the Groove drummer, on MIDI channel 10.
7. **Live mode:** the engine generates a bar or phrase ahead and streams events over a WebSocket; the browser plays them
   through Web MIDI with timestamps (Chrome or Edge). Parameter changes apply from the next bar or phrase.

## Sources

Design history: Music_Vault/Composition/Generative Composition (integration handoff 2026-11-20, documents 03, 04, 06,
source inventory 2026-11-25) and the Experiment 30-32 packages.
