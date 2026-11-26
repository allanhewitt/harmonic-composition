"""Step 4 of the Harmonic Composition Generator: parts.

Turns an accepted harmony (harmonic_engine.generate result) into MIDI-ready parts. This first
release has pads only:

  * 2-note pad: two of the chord's 1st, 3rd and 5th (1-3, 1-5 or 3-5).
  * 3-note pad: 1st, 3rd and 5th.

A pad changes only when the chord changes. "Third" and "fifth" are the chord's own: the 2nd or 4th
of a sus chord, the flat fifth of a diminished chord, the sharp fifth of an augmented chord.
Sevenths, sixths and added notes are ignored.

Settings per pad
  voicing      'root'   always root position (lowest note is the 1st, or the 3rd for a 3-5 dyad),
                        placed in the octave nearest the middle of the register.
               'smooth' any inversion within the register, chosen to move as little as possible
                        from the previous chord (with a pull towards the middle of the register so
                        the line cannot drift to one end).
  articulation 'clean'  every note re-struck on every chord change.
               'hold'   notes shared with the previous chord keep sounding; only notes that change
                        are struck.
  register     lowest and highest MIDI note the pad may use. Default for both pads: G3 to E5
               (MIDI 55-76), from the G below middle C to the E an octave and a third above it.

Pads are deterministic: the same harmony and settings always give the same notes.
The output is a parts document (schema gcl-parts-0.1) that step 5 (midi_export) writes to MIDI.
"""
import copy

VERSION = '0.1.0'
SCHEMA = 'gcl-parts-0.1'
PPQ = 480

DYAD_TONES = {'1-3': (0, 1), '1-5': (0, 2), '3-5': (1, 2)}
VOICINGS = ('root', 'smooth')
ARTICULATIONS = ('clean', 'hold')
CENTRE_PULL = 0.35          # cost per semitone that a voicing's centre sits away from the register middle (smooth)
CLEAN_GAP = 10              # ticks of silence before a re-struck note, so synths retrigger cleanly

PAD_DEFAULTS = {
    'pad2': dict(name='Pad 2-note', voices=2, tones='1-3', voicing='smooth', articulation='hold',
                 low=55, high=76, velocity=60, channel=1, program=89, enabled=True),
    'pad3': dict(name='Pad 3-note', voices=3, tones='1-3-5', voicing='smooth', articulation='hold',
                 low=55, high=76, velocity=60, channel=0, program=89, enabled=True),
}


def default_settings():
    return copy.deepcopy(PAD_DEFAULTS)


def chord_triad(e):
    """Pitch classes of the chord's 1st, 3rd and 5th, in that order."""
    ivs = sorted(e['intervals'])[:3]
    if len(ivs) < 3:
        raise ValueError(f"Chord {e.get('chord_symbol')} has fewer than three notes.")
    return tuple((e['root_pc'] + i) % 12 for i in ivs)


def chord_timeline(result):
    """Chord spans in ticks, merging neighbours whose 1st-3rd-5th are the same (Cmaj7 to C is no change)."""
    spans = []
    for e in sorted(result['events'], key=lambda x: x['start_tick']):
        triad = chord_triad(e)
        start, end = e['start_tick'], e['start_tick'] + e['duration_ticks']
        if spans and spans[-1]['triad'] == triad and spans[-1]['end'] == start:
            spans[-1]['end'] = end
            continue
        if spans and spans[-1]['end'] != start:
            raise ValueError(f'Harmony has a gap or overlap at tick {start}.')
        spans.append(dict(start=start, end=end, triad=triad, symbol=e['chord_symbol'], roman=e.get('roman', ''),
                          section_index=e['section_index']))
    return spans


def check_pad(cfg):
    if cfg['voices'] not in (2, 3):
        raise ValueError('A pad has 2 or 3 notes.')
    if cfg['voices'] == 2 and cfg['tones'] not in DYAD_TONES:
        raise ValueError(f"2-note pad tones must be one of {', '.join(DYAD_TONES)}.")
    if cfg['voicing'] not in VOICINGS:
        raise ValueError(f"Voicing must be one of {', '.join(VOICINGS)}.")
    if cfg['articulation'] not in ARTICULATIONS:
        raise ValueError(f"Articulation must be one of {', '.join(ARTICULATIONS)}.")
    lo, hi = int(cfg['low']), int(cfg['high'])
    if not 0 <= lo < hi <= 127:
        raise ValueError(f"{cfg['name']}: register must run upwards within MIDI 0-127.")
    if hi - lo < 11:
        raise ValueError(f"{cfg['name']}: register needs at least an octave (low {lo}, high {hi}).")
    if not 1 <= int(cfg['velocity']) <= 127:
        raise ValueError(f"{cfg['name']}: velocity must be 1-127.")


def pad_pcs(triad, cfg):
    """The pitch classes this pad plays, lowest-in-root-position first."""
    if cfg['voices'] == 3:
        return list(triad)
    return [triad[i] for i in DYAD_TONES[cfg['tones']]]


def stack(pcs, bottom):
    """Close position upwards from `bottom`, keeping the given order of pitch classes."""
    notes = [bottom]
    for pc in pcs[1:]:
        notes.append(notes[-1] + ((pc - notes[-1]) % 12 or 12))
    return notes


def candidates(pcs, lo, hi, voicing):
    """All placements of the pad inside the register: root position only, or every inversion."""
    orders = [pcs] if voicing == 'root' else [pcs[i:] + pcs[:i] for i in range(len(pcs))]
    out = []
    for order in orders:
        for bottom in range(lo, hi + 1):
            if bottom % 12 != order[0]:
                continue
            notes = stack(order, bottom)
            if notes[-1] <= hi:
                out.append(notes)
    return out


def choose(pcs, cfg, prev):
    lo, hi = int(cfg['low']), int(cfg['high'])
    middle = (lo + hi) / 2
    pool = candidates(pcs, lo, hi, cfg['voicing'])
    if not pool:
        raise ValueError(f"{cfg['name']}: no {cfg['voicing']} voicing fits between {lo} and {hi}.")
    centre = lambda v: sum(v) / len(v)
    if cfg['voicing'] == 'root' or prev is None:
        return min(pool, key=lambda v: (abs(centre(v) - middle), v))
    move = lambda v: sum(abs(a - b) for a, b in zip(v, prev))
    return min(pool, key=lambda v: (move(v) + CENTRE_PULL * abs(centre(v) - middle), v))


def make_pad(spans, cfg, part_id):
    """Voicings per chord span, then notes: re-struck every change (clean) or tied over common tones (hold)."""
    check_pad(cfg)
    voicings, prev = [], None
    for sp in spans:
        prev = choose(pad_pcs(sp['triad'], cfg), cfg, prev)
        voicings.append(prev)
    vel = int(cfg['velocity'])
    notes = []
    if cfg['articulation'] == 'clean':
        for sp, v in zip(spans, voicings):
            gap = CLEAN_GAP if sp['end'] - sp['start'] > 4 * CLEAN_GAP else 0
            notes += [dict(start=sp['start'], duration=sp['end'] - sp['start'] - gap, pitch=p, velocity=vel) for p in v]
    else:
        sounding = {}
        for sp, v in zip(spans, voicings):
            for p in [p for p in sounding if p not in v]:
                notes.append(dict(start=sounding[p], duration=sp['start'] - sounding.pop(p), pitch=p, velocity=vel))
            for p in v:
                sounding.setdefault(p, sp['start'])
        end = spans[-1]['end'] if spans else 0
        notes += [dict(start=s, duration=end - s, pitch=p, velocity=vel) for p, s in sounding.items()]
    notes.sort(key=lambda n: (n['start'], n['pitch']))
    moves = [sum(abs(a - b) for a, b in zip(v, w)) for v, w in zip(voicings, voicings[1:])]
    strikes = sum(1 for n in notes)
    stats = dict(chords=len(spans), notes=strikes, lowest=min(min(v) for v in voicings), highest=max(max(v) for v in voicings),
                 mean_movement=round(sum(moves) / len(moves), 2) if moves else 0.0,
                 largest_leap=max((max(abs(a - b) for a, b in zip(v, w)) for v, w in zip(voicings, voicings[1:])), default=0),
                 inversions=sum(1 for sp, v in zip(spans, voicings) if v[0] % 12 != pad_pcs(sp['triad'], cfg)[0]))
    return dict(id=part_id, name=cfg['name'], kind='pad', channel=int(cfg['channel']), program=int(cfg['program']),
                settings=copy.deepcopy(cfg), voicings=voicings, notes=notes, stats=stats)


def generate_parts(result, settings=None):
    """Step 4: the parts document for an accepted harmony."""
    cfgs = default_settings()
    for k, v in (settings or {}).items():
        if k not in cfgs:
            raise ValueError(f'Unknown part {k!r}.')
        cfgs[k].update(v)
    spans = chord_timeline(result)
    s = result['settings']
    parts = [make_pad(spans, cfg, pid) for pid, cfg in cfgs.items() if cfg.get('enabled', True)]
    return dict(schema=SCHEMA, version=VERSION, ppq=PPQ, tempo=s['tempo'], meter=s['meter'],
                end_tick=spans[-1]['end'] if spans else 0, chords=spans, parts=parts, settings=cfgs)


NOTE_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
def note_name(n):
    return f'{NOTE_NAMES[n % 12]}{n // 12 - 1}'


def preview(doc, limit=16):
    """Text listing of the first chords and each pad's voicing, lowest note first."""
    lines = []
    for i, sp in enumerate(doc['chords'][:limit]):
        cells = [f"{sp['symbol']:<7}"] + [' '.join(note_name(n) for n in p['voicings'][i]) for p in doc['parts']]
        lines.append(' | '.join(f'{c:<12}' for c in cells))
    return '\n'.join(lines)
