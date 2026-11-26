"""Sequencer framework: what every sequencer engine shares.

An engine (seq960.py and later ones) decides only its mechanism: when steps happen and how (gate length, accent,
slide, ratchet), and an abstract VALUE for each step. This module turns those steps into notes:

Values and harmonic modes (handoff section 6)
  A value is an integer position in a ladder built from the current chord or scale ('value_space'):
    chord space: 0 = root, 1 = 3rd, 2 = 5th, 3 = the 7th if the chord has one, then the ladder repeats an octave
                 higher (so with a plain triad 3 = root an octave up); negative values go below the root.
    scale space: 0 = chord root, 1 = the next scale note above it, ... 7 = the root an octave up.
  'adapted'      the ladder is rebuilt from every chord, so the line fits each chord and the current scale
                 (in scale space, a note that starts with a new chord is pulled to the nearest chord tone).
  'transposed'   the pattern keeps its exact intervals (taken from a major-scale ladder) and moves to each chord
                 root, as a 960 transposed from a keyboard: the shape stays, the notes may leave the key.
  'independent'  the ladder comes from the home key's tonic and scale and ignores the chords: fixed pitches.
  Chord changes never restart a pattern; restarting at section or phrase starts is the engine's 'reset' setting.
Register and profile
  'low' / 'high' bound the part; 'anchor' is where the ladder's root is placed (nearest octave); notes outside the
  register move by octaves. Profiles describe the instrument: mono (one note at a time; a slide becomes a short
  overlap so a synth in legato/glide mode slides), velocity (whether accents use velocity).
Density
  The shared plan's level (1-5) at a step is available to the engine; each engine maps it to its own control.
Form
  Engines get the plan's phrases (start, end, level, section identity, first phrase of a section) and helpers for
  per-section pattern variants (related repeats) and gradual mutation.
All mappings are DESIGN.
"""
import copy, random
import harmonic_engine as H

VERSION = '0.1.0'
MODES = ('adapted', 'transposed', 'independent')
SPACES = ('chord', 'scale')
MAJOR = [0, 2, 4, 5, 7, 9, 11]
GRIDS = {'4': 480, '8': 240, '16': 120, '32': 60}
# Channels for sequencer parts (0-based): 6-8 and 10-15; 9 (MIDI channel 10) is kept for the drum family.
CHANNELS = [6, 7, 8, 10, 11, 12, 13, 14, 15]
PROFILES = {
    'mono_synth':  dict(mono=True, velocity=True, slide_overlap=40),      # Diva, Repro-1, other mono soft synths
    'poly_synth':  dict(mono=False, velocity=True, slide_overlap=0),      # Repro-5 and other poly synths
    'mono_hw_novel': dict(mono=True, velocity=False, slide_overlap=40),   # hardware mono synth without velocity
}
COMMON_DEFAULTS = dict(enabled=True, harmonic='adapted', value_space='chord', low=60, high=84, anchor=64,
                       profile='mono_synth', velocity=84, accent=16, grid='16', reset='section', mutation=0.25, seed=1)


def check_common(cfg, name):
    if cfg['harmonic'] not in MODES:
        raise ValueError(f"{name}: harmonic mode must be one of {', '.join(MODES)}.")
    if cfg['value_space'] not in SPACES:
        raise ValueError(f"{name}: value space must be 'chord' or 'scale'.")
    if str(cfg['grid']) not in GRIDS:
        raise ValueError(f"{name}: step must be one of {', '.join(GRIDS)} (quarter, eighth, sixteenth, 32nd notes).")
    if cfg['reset'] not in ('section', 'phrase', 'never'):
        raise ValueError(f"{name}: reset must be section, phrase or never.")
    if cfg['profile'] not in PROFILES:
        raise ValueError(f"{name}: profile must be one of {', '.join(PROFILES)}.")
    lo, hi = int(cfg['low']), int(cfg['high'])
    if not 0 <= lo < hi <= 127 or hi - lo < 12:
        raise ValueError(f'{name}: the register must span at least an octave within MIDI 0-127.')


class Context:
    """Everything an engine needs to know about the piece, with time lookups."""

    def __init__(self, doc, result, plan):
        self.doc, self.result, self.plan = doc, result, plan
        self.ppq = doc['ppq']
        self.bar = H.bar_ticks(doc['meter'])
        self.beat = self.ppq * 4 // int(doc['meter'].split('/')[1])
        self.end = doc['end_tick']
        self.events = sorted(result['events'], key=lambda e: e['start_tick'])
        self.starts = [e['start_tick'] for e in self.events]
        self.sections = result['sections']
        self.home_key = result['keys'][0] if result.get('keys') else self.events[0]['scale']
        bounds = [st['bar'] * self.bar for st in plan] + [self.end]
        self.phrases = [dict(start=bounds[i], end=bounds[i + 1], level=st['level'], first=st['first'],
                             section=st['section'], identity=self.sections[st['section']]['identity'],
                             occurrence=self.sections[st['section']]['occurrence'])
                        for i, st in enumerate(plan)]

    def chord_at(self, t):
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= t:
                lo = mid
            else:
                hi = mid - 1
        return self.events[lo]

    def level_at(self, t):
        for ph in self.phrases:
            if ph['start'] <= t < ph['end']:
                return ph['level']
        return self.phrases[-1]['level']


def chord_ladder(ev):
    """Root, 3rd, 5th and the chord's 7th (or 6th) if it has one: value 3 is then the 7th, otherwise the octave."""
    ivs = sorted(ev['intervals'])
    seventh = [i for i in ivs if i in (9, 10, 11)]
    return ivs[:3] + seventh[:1]


def scale_ladder(root_pc, scale_name):
    """The current scale's notes from the chord root upwards (the root first, even if borrowed)."""
    above = sorted({(pc - root_pc) % 12 for pc in H.scale_pcs(scale_name)} - {0})
    return [0] + above


def fold(p, lo, hi):
    while p > hi:
        p -= 12
    while p < lo:
        p += 12
    return p


def ladder_for(ctx, cfg, t):
    """(root pitch class, ladder of semitone offsets) for the part's harmonic mode and value space at tick t."""
    mode, space = cfg['harmonic'], cfg['value_space']
    if mode == 'independent':
        tonic_pc, _ = H.parse_key(ctx.home_key)
        sc = scale_ladder(tonic_pc, ctx.home_key)
        return tonic_pc, (sc if space == 'scale' else [sc[0], sc[2], sc[4]])
    ev = ctx.chord_at(t)
    if mode == 'transposed':
        return ev['root_pc'], (MAJOR if space == 'scale' else [0, 4, 7])
    return ev['root_pc'], (chord_ladder(ev) if space == 'chord' else scale_ladder(ev['root_pc'], ev['scale']))


def value_to_pitch(ctx, cfg, t, v, chord_start=False):
    """MIDI pitch for abstract value v at tick t."""
    lo, hi, anchor = int(cfg['low']), int(cfg['high']), int(cfg['anchor'])
    root_pc, ladder = ladder_for(ctx, cfg, t)
    octv, idx = divmod(int(v), len(ladder))
    base = anchor + ((root_pc - anchor) % 12)          # the root at or above the anchor ...
    if base - anchor > 6:
        base -= 12                                     # ... or just below it, whichever is nearer
    p = base + ladder[idx] + 12 * octv
    if cfg['harmonic'] == 'adapted' and cfg['value_space'] == 'scale' and chord_start:
        ev = ctx.chord_at(t)
        tones = {(ev['root_pc'] + i) % 12 for i in ev['intervals']}
        if p % 12 not in tones:                        # a note that starts with a new chord lands on a chord tone
            p = min((q for q in range(p - 2, p + 3) if q % 12 in tones), key=lambda q: (abs(q - p), q), default=p)
    return fold(p, lo, hi)


def variant_bank(ctx, rng, make, mutate, mutation, section_variants=True):
    """One pattern per phrase. With `section_variants`, each section identity gets its own variant of the first
    pattern (otherwise every section uses the same pattern); a repeated section returns to its pattern (one change at
    most, with probability `mutation`); later phrases of a section may change one value (gradual development).
    With section_variants off and mutation 0 the pattern is the same throughout the piece."""
    bank, out, seed_pat = {}, [], make()
    for ph in ctx.phrases:
        if ph['first']:
            if ph['identity'] not in bank:
                bank[ph['identity']] = mutate(seed_pat, 2) if (bank and section_variants) else seed_pat
            elif rng.random() < mutation:
                bank[ph['identity']] = mutate(bank[ph['identity']], 1)
            pat = bank[ph['identity']]
        else:
            pat = out[-1]
            if rng.random() < mutation:
                pat = mutate(pat, 1)
        out.append(pat)
    return out


def realise(ctx, cfg, part_id, name, steps, extra=None):
    """Turn engine steps into a part. Each step: t, dur, value, accent, slide (and optional chord_start).
    Monophonic profiles never overlap except a short overlap into the next note after a slide."""
    prof = PROFILES[cfg['profile']]
    notes = []
    for s in sorted(steps, key=lambda s: s['t']):
        if s['t'] >= ctx.end or s['dur'] <= 0:
            continue
        cs = s.get('chord_start', s['t'] in set(ctx.starts))
        p = value_to_pitch(ctx, cfg, s['t'], s['value'], cs)
        vel = int(cfg['velocity']) + (int(cfg['accent']) if s.get('accent') else 0) if prof['velocity'] else int(cfg['velocity'])
        notes.append(dict(start=s['t'], duration=min(s['dur'], ctx.end - s['t']), pitch=p, velocity=max(1, min(127, vel)),
                          slide=bool(s.get('slide'))))
    if prof['mono']:
        for a, b in zip(notes, notes[1:]):
            limit = b['start'] - a['start']
            if a['slide'] and prof['slide_overlap'] and a['pitch'] != b['pitch'] and b['start'] - (a['start'] + a['duration']) < ctx.ppq:
                a['duration'] = limit + prof['slide_overlap']                   # legato overlap: the synth glides
            elif a['duration'] >= limit:
                a['duration'] = max(1, limit - 10)                              # a small gap retriggers cleanly
    else:
        open_ = {}
        for n in notes:                                                         # same pitch: end the earlier note first
            prev = open_.get(n['pitch'])
            if prev and prev['start'] + prev['duration'] > n['start']:
                prev['duration'] = max(1, n['start'] - prev['start'] - 10)
            open_[n['pitch']] = n
    notes = [n for n in notes if n['duration'] > 0]
    for n in notes:
        n['duration'] = min(n['duration'], ctx.end - n['start'])
    stats = dict(notes=len(notes), lowest=min((n['pitch'] for n in notes), default=None),
                 highest=max((n['pitch'] for n in notes), default=None), slides=sum(n['slide'] for n in notes))
    part = dict(id=part_id, name=name, kind='seq', channel=int(cfg['channel']), program=int(cfg.get('program', 81)),
                settings=copy.deepcopy(cfg), notes=[{k: v for k, v in n.items() if k != 'slide'} for n in notes],
                slides=[i for i, n in enumerate(notes) if n['slide']], stats=stats)
    part.update(extra or {})
    return part
