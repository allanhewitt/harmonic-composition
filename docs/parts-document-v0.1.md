# Parts document v0.1 (schema `gcl-parts-0.1`)

**Status:** implemented (Stage 1). The hand-over from step 4 (parts) to step 5 (score and MIDI).

```text
schema, version, ppq (480), tempo, meter, end_tick
chords:   [{start, end, triad (root, 3rd, 5th pitch classes), symbol, roman, section_index}]
parts:    [{id, name, kind (pad | bass | line | seq), channel (0-15), program, settings,
            notes: [{start, duration, pitch, velocity}], stats, ...}]
orchestration: {version, settings, plan: [{bar, section, first, level, target}], top}
thinning: {version, settings, report: {part id: {kept, target}}}
```

Rules every generator keeps:

- Times are ticks at 480 per quarter note; notes lie within `0 … end_tick`.
- Monophonic parts (bass, lines) never overlap; no part repeats a pitch while it is already sounding on its channel.
- Generators work forwards in time phrase by phrase with their own seeded state, and read the shared plan rather than
  deciding entries themselves. This keeps a later live (streaming) mode possible.
- Sequencer parts also list `slides` (indices of notes that overlap the next note so a mono synth glides) and
  `patterns` (the pattern used in each phrase).
- A part may add display hints for the score: `short` (staff name), `staccato` (sequencer steps), `annotations`.

## Step 5 conventions (from Experiments 30-32)

Type 1 MIDI at 480 PPQ; conductor track with tempo, meter, key signatures and section markers; one channel per part with a
program change; CC11 = 127 at tick 0 and a centred pitch wheel at the last tick of every part; note-offs before note-ons
on the same tick; same-pitch overlaps refused.
