# Piece script v0.1

**Status:** implemented (Stage 1). Checked by `tests/test_stage1_parts.py` and `tests/test_api.py`.

A piece script is a YAML file with up to ten sections. Only `piece` is required; anything left out takes its default.
Unknown sections are refused, so a typing mistake is reported rather than silently ignored. Unknown keys inside a section
are kept and passed to that stage.

```yaml
piece:          # step 1
  title: Night Transit
  key: A minor            # tonic + mode (major, minor, dorian, phrygian, lydian, mixolydian, locrian)
  tempo: 112
  meter: 4/4              # 4/4, 3/4, 6/8, 12/8, 2/4
  length: 64              # target in bars, or a range 64..96 (the form uses the nearest length it can fill)
  seed: 5
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
sequencers:     # one instance of each sequencer engine; each is on unless enabled: false
  m960:
    enabled: true
    harmonic: adapted       # adapted (fit each chord), transposed (keep shape, move with the root), independent
    value_space: chord      # chord (root, 3rd, 5th, 7th ...) or scale (scale steps from the chord root)
    grid: '16'              # '4', '8', '16', '32'
    length: 8               # 2-16 steps
    rows: {a: pitch, b: gate, c: time}   # each row controls pitch, gate, velocity (accent) or time (step length)
    skip_rate: 0.08         # share of Skip steps (take no time)
    stop_rate: 0.0          # chance of a Stop step (halts until the next restart)
    time_rate: 0.2          # share of double-length steps when a row controls time
    reset: section          # section, phrase, never
    mutation: 0.25
    low: 60
    high: 84
    anchor: 64              # the ladder's root is placed nearest this note
    profile: mono_synth     # mono_synth, poly_synth, mono_hw_novel (no velocity)
    velocity: 84
    accent: 16
    channel: 6              # 0-based; 9 (MIDI channel 10) is kept for drums
    program: 81
    seed: 1
density:        # final filter on pads and lines (sequencers are not thinned)
  keep: 100               # 0-100
  mode: even              # even, flatten, contrast
  parts: {}               # per-part keep, e.g. {descant: 50}
  randomness: 0.3
  exempt: [pad2]
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
