"""Lines (prototype): tenor, alto and descant, from rhythm-first composition plus pitch adapters.

Rhythm (rhythm-first, after documents 03 and 04)
  * Each line is written phrase by phrase, using the phrase lengths from step 2.
  * Density (share of grid slots that start a note) and participation (share of time sounding) come
    from the line's own ladder, indexed by the shared density level, so lines thin and thicken with the
    pads and bass.
  * Slots are weighted by metric strength (downbeats first); inner lines also favour chord changes.
  * Interdependence: a slot already used by a line written earlier is less likely (complementary
    rhythm), so the lines tend to answer rather than double each other.
  * Motif repetition: within a section the second phrase reuses the first phrase's rhythm with small
    changes; a repeated section returns to its rhythm (related repeats).
  * Phrase ends: the descant breathes (rests) at the end of a phrase; inner lines hold into the cadence.
Pitch
  * Guide tones (tenor, alto): chord tones chosen for smooth voice leading, preferring the 3rd and 7th,
    avoiding the pitch the other inner line is sounding.
  * Melodic (descant): a stepwise walk through the current scale; strong beats and phrase ends land on
    chord tones; a gentle rise then fall across each phrase.
Instrument profiles: every line is monophonic (Kobol is monophonic; Poly-800 and Diva play the line
mono here). Velocity is constant on the Poly-800 line (it is not expected to respond to velocity).
All weights and ladders are DESIGN.
"""
import copy, math, random
import harmonic_engine as H

VERSION = '0.0.1'
LINES = {
    'tenor':   dict(name='Tenor line (Kobol)', low=45, high=62, grid=480, channel=3, program=81, velocity=80,
                    vel_fixed=False, pitch='guide', prefer=(1, 3, 0, 2),
                    # per shared level 1-5: (density, participation, enters?)
                    ladder={1: (0.18, 0.95, True), 2: (0.2, 0.95, True), 3: (0.25, 0.9, True), 4: (0.3, 0.9, True), 5: (0.35, 0.85, True)}),
    'alto':    dict(name='Alto line (Poly-800)', low=57, high=72, grid=480, channel=4, program=50, velocity=90,
                    vel_fixed=True, pitch='guide', prefer=(3, 1, 2, 0),
                    ladder={1: (0.0, 0.0, False), 2: (0.22, 0.85, True), 3: (0.3, 0.85, True), 4: (0.38, 0.8, True), 5: (0.45, 0.8, True)}),
    'descant': dict(name='Descant (Diva)', low=72, high=88, grid=240, channel=5, program=73, velocity=78,
                    vel_fixed=False, pitch='melodic', prefer=None,
                    ladder={1: (0.0, 0.0, False), 2: (0.0, 0.0, False), 3: (0.18, 0.6, True), 4: (0.26, 0.65, True), 5: (0.34, 0.7, True)}),
}
ORDER = ('tenor', 'alto', 'descant')


def metric_weight(t, bt, beat):
    pos = t % bt
    if pos == 0:
        return 1.0
    if pos % (2 * beat) == 0 and bt % (2 * beat) == 0:
        return 0.7
    if pos % beat == 0:
        return 0.5
    return 0.25


def phrase_rhythm(rng, a, b, cfg, level, chord_starts, taken, bt, beat):
    """Onsets and durations for one phrase [a, b)."""
    dens, part, on = cfg['ladder'][level]
    if not on:
        return []
    slots = list(range(a, b, cfg['grid']))
    n = max(1, round(dens * len(slots)))
    weights = []
    for t in slots:
        w = metric_weight(t, bt, beat)
        if cfg['pitch'] == 'guide' and t in chord_starts:
            w *= 3.0
        if t in taken:
            w *= 0.3                                         # interdependence: complementary rhythm
        if cfg['pitch'] == 'melodic' and t >= b - bt // 2:
            w *= 0.15                                        # descant breathes at the phrase end
        weights.append(w)
    chosen = set()
    if cfg['pitch'] == 'guide':
        chosen.add(a)                                        # inner lines sound from the phrase start
    pool = [(t, w) for t, w in zip(slots, weights) if t not in chosen]
    while len(chosen) < n and pool:
        t = rng.choices([p for p, _ in pool], [w for _, w in pool])[0]
        chosen.add(t)
        pool = [(p, w) for p, w in pool if p != t]
    onsets = sorted(chosen)
    out = []
    for i, t in enumerate(onsets):
        nxt = onsets[i + 1] if i + 1 < len(onsets) else b
        span = nxt - t
        if cfg['pitch'] == 'melodic' and i + 1 == len(onsets):
            span = min(span, max(cfg['grid'], (b - t) // 2))  # last descant note leaves a breath
        g = cfg['grid']
        if cfg['pitch'] == 'guide':
            dur = span - g if (span > g and rng.random() > part) else span
        else:
            dur = max(g, int(span * part) // g * g)
        out.append((t - a, min(dur, span)))
    return out


def chord_at(events, t):
    lo, hi = 0, len(events) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if events[mid]['start_tick'] <= t:
            lo = mid
        else:
            hi = mid - 1
    return events[lo]


def chord_tone_pcs(ev):
    ivs = sorted(ev['intervals'])
    tri = ivs[:3]
    seventh = [i for i in ivs if i in (10, 11, 9)]
    # degree index: 0 root, 1 3rd, 2 5th, 3 7th (or 6th); missing 7th falls back to the 3rd
    pcs = [(ev['root_pc'] + i) % 12 for i in tri]
    pcs.append((ev['root_pc'] + seventh[0]) % 12 if seventh else pcs[1])
    return pcs


def guide_pitch(ev, prev, cfg, avoid, rng, move_on=False):
    pcs = chord_tone_pcs(ev)
    lo, hi = cfg['low'], cfg['high']
    centre = (lo + hi) / 2
    cands = []
    for rank, deg in enumerate(cfg['prefer']):
        for p in range(lo, hi + 1):
            if p % 12 == pcs[deg] and p != avoid and not (move_on and p == prev):
                move = abs(p - prev) if prev is not None else abs(p - centre)
                cands.append((move + 1.5 * rank + 0.15 * abs(p - centre) + rng.random() * 0.8, p))
    if not cands:                                            # nothing else fits: stay
        return prev
    return min(cands)[1]


def melodic_pitch(ev, prev, cfg, strong, last, x, rng):
    lo, hi = cfg['low'], cfg['high']
    scale = H.scale_pcs(ev['scale'])
    chord = chord_tone_pcs(ev)[:3]
    pool = [p for p in range(lo, hi + 1) if p % 12 in (chord if (strong or last) else scale)]
    if prev is None:
        prev = (lo + hi) // 2
    lean = 1.5 * math.cos(math.pi * x)                        # rise early in the phrase, fall later
    weights = []
    for p in pool:
        d = p - prev
        step = abs(d)
        w = {0: 0.6, 1: 5, 2: 6, 3: 3, 4: 3, 5: 2, 7: 1.2}.get(step, 0.3 if step < 10 else 0.05)
        w *= math.exp(0.25 * lean * (1 if d > 0 else -1 if d < 0 else 0))
        weights.append(w)
    return rng.choices(pool, weights)[0]


def generate(doc, result, plan, settings=None):
    """The three line parts. `plan` is the shared density plan."""
    cfgs = copy.deepcopy(LINES)
    for k, v in (settings or {}).items():
        if k in cfgs:
            cfgs[k].update(v)
        elif k != 'seed':
            raise ValueError(f'Unknown line {k!r}.')
    seed = (settings or {}).get('seed', 1)
    bt = H.bar_ticks(doc['meter'])
    beat = doc['ppq'] * 4 // int(doc['meter'].split('/')[1])
    end = doc['end_tick']
    events = sorted(result['events'], key=lambda e: e['start_tick'])
    chord_starts = {e['start_tick'] for e in events}
    sections = result['sections']
    bounds = [st['bar'] * bt for st in plan] + [end]
    taken, parts, sounding_by_line = set(), [], {}
    for lid in ORDER:
        cfg = cfgs[lid]
        rng = random.Random(f'lines-{lid}-{seed}')
        bank, first_rhythm, notes, prev = {}, None, [], None
        for k, st in enumerate(plan):
            a, b = bounds[k], bounds[k + 1]
            sec = sections[st['section']]
            key = (sec['identity'], b - a, st['level'], st['first'])
            if key in bank and rng.random() < 0.8:
                rhythm = bank[key]                           # related repeat / motif repetition
            elif not st['first'] and first_rhythm and first_rhythm[0] == (b - a, st['level']) and rng.random() < 0.6:
                rhythm = [r for r in first_rhythm[1] if rng.random() > 0.15] or first_rhythm[1]
            else:
                rhythm = phrase_rhythm(rng, a, b, cfg, st['level'], chord_starts, taken, bt, beat)
            bank.setdefault(key, rhythm)
            if st['first']:
                first_rhythm = ((b - a, st['level']), rhythm)
            for i, (off, dur) in enumerate(rhythm):
                t = a + off
                ev = chord_at(events, t)
                if cfg['pitch'] == 'guide':
                    avoid = next((n['pitch'] for n in sounding_by_line.get('tenor', []) if n['start'] <= t < n['start'] + n['duration']), None) \
                        if lid == 'alto' else None
                    same_chord = bool(notes) and chord_at(events, notes[-1]['start'])['start_tick'] == ev['start_tick']
                    p = guide_pitch(ev, prev, cfg, avoid, rng, move_on=same_chord)
                    if notes and p == notes[-1]['pitch'] and notes[-1]['start'] + notes[-1]['duration'] >= t - cfg['grid']:
                        notes[-1]['duration'] = t + min(dur, end - t) - notes[-1]['start']      # hold the common tone
                        prev = p
                        continue
                else:
                    strong = metric_weight(t, bt, beat) >= 0.7
                    p = melodic_pitch(ev, prev, cfg, strong, i == len(rhythm) - 1, off / max(1, b - a), rng)
                vel = cfg['velocity'] if cfg['vel_fixed'] else max(1, min(127, cfg['velocity'] + 4 * (st['level'] - 3)
                                                                          + (6 if t % bt == 0 else 0)))
                if notes and notes[-1]['start'] + notes[-1]['duration'] > t:
                    notes[-1]['duration'] = t - notes[-1]['start']      # monophonic
                notes.append(dict(start=t, duration=min(dur, end - t), pitch=p, velocity=vel))
                prev = p
            taken |= {a + off for off, _ in rhythm}
        notes = [n for n in notes if n['duration'] > 0]
        sounding_by_line[lid] = notes
        stats = dict(notes=len(notes), lowest=min((n['pitch'] for n in notes), default=0),
                     highest=max((n['pitch'] for n in notes), default=0),
                     sounding=round(sum(n['duration'] for n in notes) / end, 2))
        parts.append(dict(id=lid, name=cfg['name'], kind='line', channel=cfg['channel'], program=cfg['program'],
                          settings={k: v for k, v in cfg.items() if k != 'ladder'}, notes=notes, stats=stats))
    return parts
