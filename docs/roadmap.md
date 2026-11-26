# Roadmap

## Stage 1: done

Song, structure and harmony (engine v0.7, generator v0.3); pads (2-note and 3-note, root or smooth, clean or hold, G3-E5);
shared density plan with a constant pad and the other pad entering voice by voice; Moog 960 bass (Berlin School techniques:
step add/drop by density, odd lengths, transposition fitted or strict, pattern bank per section, gradual mutation);
tenor, alto and descant lines (rhythm by phrase, guide-tone and melodic pitch); density filter (even, flatten, contrast;
constant pad exempt); LilyPond score; MIDI; piece scripts; web app.

## Stage 2: planned

1. **Line embellishments:** a harmonic-adherence setting per line; extensions, suspensions, passing and neighbour notes,
   appoggiaturas, anticipations. (Could come first, as Stage 1.1.)
2. **Per-section settings** in the script (`sections:`) and a sections table in the app.
3. **The ten sequencer models** from Experiment 32 (Moog 960, TR-808, TB-303, Euclidean, polymetric, Turing Machine,
   Marbles, René, Metropolix, Nodal), each as rhythm generator plus pitch selector, with standalone and pitch-assignment modes.
4. **Rhythm-first composition** (documents 03, 04, 06 and `composition.py`): multi-voice rhythmic counterpoint with density,
   participation and interdependence, then pitch assignment by any adapter.
5. **Instrument profiles** (Model D, Kobol, Poly-800, Diva): polyphony, overlap handling, velocity response, range.
6. **Live mode:** the engine generates a bar or phrase ahead and streams events over a WebSocket; the browser plays them
   through Web MIDI with timestamps (Chrome or Edge). Parameter changes apply from the next bar or phrase.

## Sources

Design history: Music_Vault/Composition/Generative Composition (integration handoff 2026-11-20, documents 03, 04, 06,
source inventory 2026-11-25) and the Experiment 30-32 packages.
