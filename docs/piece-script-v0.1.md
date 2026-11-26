# Piece script v0.1

**Status:** implemented (Stage 1). Checked by `tests/test_stage1_parts.py` and `tests/test_api.py`.

A piece script is a YAML file with up to ten sections. Only `piece` is required; anything left out takes its default.
Unknown sections are refused, so a typing mistake is reported rather than silently ignored. Unknown keys inside a section
are kept and passed to that stage.

```yaml
piece:          # step 1
  title: Night Transit
  key: A minor            # tonic + mode (major, minor, dorian, phrygian, lydian, mixolydian, locrian)
  tempo: 112              # beats per minute of the notated beat: dotted crotchet in 6/8 and 12/8, minim in 2/2;
                          # score and MIDI agree (MIDI is written in crotchets)
  meter: 4/4              # 4/4, 3/4, 6/8, 12/8, 2/4
  length: 64              # target in bars, or a range 64..96 (the form uses the nearest length it can fill)
  seed: 5                 # or auto; the resolved script saved with each run records the seed (and key, tempo,
                          # length) actually drawn, plus every effective harmony setting, so it rebuilds the piece
structure:      # step 2 (GCL Version One v0.3 form models)
  model: verse_chorus     # verse_chorus, aaba, cyclic, through_composed, evolving, arch, modular, auto, explicit
  sections: 5..9
  section_length: 8..24
  phrase_length: 4..8
  intro: true
  bridge: true
  outro: true
  recurrence: 70
  contrast: 40
  symmetry: 60
  repeats_keep_shape: true
  explicit: "intro 8\nverse 16\n..."   # used by model: explicit
harmony:        # step 3: any harmonic engine setting (see engine/harmonic_engine.py DEFAULT_SETTINGS)
  rates: ['1/4', '1/2']   # chords per bar allowed: 1/4 = four-bar chords ... 4 = quarter-bar chords
  interest: 0.5
  interest_contour: flat  # flat, rising, arch, contrast
pads:           # step 4
  pad2: {enabled: true, tones: 1-3, voicing: smooth, articulation: hold, low: 55, high: 76, velocity: 60}
  pad3: {enabled: true, voicing: smooth, articulation: hold, low: 55, high: 76, velocity: 60}
orchestration:  # the shared density plan (levels 1-5) used by pads, bass and lines
  constant: pad2          # this pad plays throughout
  contour: role           # role, rising, arch, flat
  randomness: 0.5
  phrase_changes: 0.5     # 0 = change only at section starts
  low: 1
  high: null              # null = the variable pad's top level
  velocity_step: 3
  seed: 1
bass:           # Moog 960-style sequencer bass
  enabled: true
  length: 8               # 3-16 steps
  grid: '8'               # '8' quavers, '16' semiquavers
  gate: 0.5
  transpose: fitted       # fitted or strict
  reset: section          # section, phrase, never
  mutation: 0.3
  low: 28
  high: 52
  seed: 1
lines:
  enabled: true
  seed: 1
  tenor:   {low: 45, high: 62}
  alto:    {low: 57, high: 72}
  descant: {low: 72, high: 88}
sequencers:     # one instance of each machine, each on unless enabled: false. Each has a fixed character:
                # the shared settings below, plus its signature control. Other keys are design defaults.
  m960:                     # Moog 960: one fixed 8-step pattern, fitted to each chord
    enabled: true
    follow: chords          # chords (fit each chord) or static (stay in the home key, ignore the chords)
    length: 8               # signature: 2-16 steps
    low: 60
    high: 84
    profile: mono_synth     # mono_synth, poly_synth, mono_hw_novel (no velocity)
    channel: 6              # 0-based; 9 (MIDI channel 10) is kept for drums
    seed: 1
    # script-only: harmonic, value_space, grid, rows {a, b, c}, skip_rate, stop_rate, time_rate, reset, mutation,
    # section_variants, anchor, velocity, accent, program
  euclid:  {cycle: 16}              # three lanes of evenly spread pulses; cycle 8, 12 or 16 steps (poly synth)
  poly:    {loops: 5-7-8}           # three loops drifting against the bar: 3-5-7, 5-6-7, 5-7-8, 7-9-11 (poly synth)
  tb303:   {slide: 0.25}            # 16-step phrase with rests, accents, octave jumps; share of slides 0-1
  turing:  {change: 0.3}            # 16-step loop; chance per pass of one step being rewritten 0-1
  metro:   {ratchet: 0.35}          # eight stages: holds, single hits, ratchets; share of ratchets 0-1
  marbles: {spread: 0.5}            # chance-driven notes near the last one, with deja vu; largest move 0-1
  rene:    {path: cartesian}        # 4 x 4 grid read along a path: cartesian, snake, diagonal
  nodal:   {branching: 0.5}         # phrases joined by weighted links; 0 = strongest link, 1 = all equally likely
  # every machine also takes enabled, follow, low, high, profile, channel and seed (channels 6-8, 10-15 by default)
rhythm:         # rhythmic counterpoint family: four voices, rhythm first then pitch (off by default)
  enabled: false
  follow: chords          # chords, or static (home key)
  grid: '8'               # onset spacing: '4', '8', '16'
  shortest: '16'          # shortest note
  conventionality: 50     # 0-100
  interdependence: 65     # 0-100
  evolution: coordinated  # coordinated, independent, steady
  window: 8               # bars between target changes
  cycle: 64               # bars per coordinated cycle
  repetition: 70          # 0-100
  seed: 1
  v1: {name: Voice 1, density: 45, density_change: 40, participation: 85, participation_change: 50,
       engine: markov, table: smooth, adherence: 0.4, pattern: [0, 2, 1, 2, 0, 3, 1, 2],
       low: 67, high: 84, velocity: 84, channel: 0, program: 73}
  v2: {density: 25, density_change: 30, participation: 75, participation_change: 40, low: 60, high: 76, channel: 1}
  v3: {density: 20, density_change: 50, participation: 80, participation_change: 60, low: 52, high: 69, channel: 3}
  v4: {density: 25, density_change: 20, participation: 90, participation_change: 30, low: 40, high: 57, channel: 4}
  # engine: markov or step; table: smooth, angular, narrow, wide, or a 9 x 9 list. See docs/rhythm-family-v0.1.md.
drums:          # drum family on MIDI channel 10, General MIDI map (off by default). See docs/drum-family-v0.1.md.
  machine: {enabled: false, name: Drum Machine, style: berlin, conclusiveness: 70, velocity: 96, seed: 1}
  drummer: {enabled: false, name: Drummer, style: motorik, feel: 0.4, conclusiveness: 75, velocity: 92, seed: 1}
  percussion: {enabled: false, name: Percussion, lanes: shakers_rims, conclusiveness: 30, evolution: plan,
               velocity: 80, seed: 1}
  # style: berlin, synthpop, motorik, four, halftime, pulse; lanes: shakers_rims, metals, toms_hands
  # map: {kick: 36, snare: 38, hatc: 42, ...}   change any note for another kit layout
density:        # final filter on pads, lines and sequencers (sequencers lose whole pattern steps)
  keep: 100               # 0-100
  mode: even              # even, flatten, contrast
  parts: {}               # per-part keep, e.g. {descant: 50, tb303: 60}; the mode does not apply to sequencers
  randomness: 0.3
  exempt: [constant]      # never thinned; 'constant' = the pad named in orchestration.constant
  seed: 1
output:         # command line only; the web app manages its own folders
  folder: piece_output
  stem: null
  score: true
  midi: true
```

## Reserved for v0.2

`sections:` will hold per-section overrides keyed by section label (for example `bridge 1: {density: {keep: 40}}`).
It is not accepted yet, so a v0.1 script cannot depend on it by mistake.
