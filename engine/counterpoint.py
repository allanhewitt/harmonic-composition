"""Rhythmic counterpoint family: four monophonic voices, composed rhythm first and given pitch afterwards.

Design: Music_Vault docs 03 (rhythmic counterpoint), 04 (pitch assignment) and 06 (decisions), and
docs/rhythm-family-v0.1.md. The family evolves independently of the other families: it reads the piece's
structure (phrases and section repeats) and harmony, but not the shared density plan.

Stage 1, rhythm (per voice)
  density        share of onset slots (on the `grid`) that start a note, 0-100
  density_change how far density moves over the piece (the full swing, in percentage points)
  participation  share of time sounding, 0-100; note lengths are solved to meet it (held to the next onset,
                 or short), and targets that the onsets cannot meet are reported, not silently changed
  participation_change  as density_change, for participation
Family settings
  conventionality  0-100: how strongly onsets favour strong beats, and how metrical the leading voice is
  interdependence  0-100: later voices avoid the onsets of earlier ones; in coordinated evolution, how strictly
                   the voices' cycles are offset so that one thins while another fills
  evolution        coordinated (offset cycles), independent (each voice drifts) or steady (no change)
  window, cycle    bars between changes of target, and bars per coordinated cycle
  repetition       0-100: how closely a returning section keeps its rhythm and intervals
A returning section's phrase keeps its onsets and gains or loses notes as density moves (weakest beats go first,
strongest join first), so change is gradual.

Stage 2, pitch (per voice; timing is never changed)
  engine     markov: first-order chain over intervals in scale steps (table: smooth, angular, narrow, wide or a
             9 x 9 list of rows); step: a pattern of chord-ladder values advanced only by notes (rests use none)
  adherence  0-1: pull towards chord tones on strong or long notes (0 ignores the chords)
Rhythm-to-pitch rules: quick successions favour steps; a note after a long gap may leap; the last note of a phrase
aims for a chord tone (the piece's last for the tonic); a rest of a bar or more resets the chain's direction;
returning phrases replay their intervals; no crossing below the voice above, no unison or octave on shared onsets,
contrary motion preferred; the lowest voice favours roots on strong notes.
follow: chords (the harmonic engine's progression) or static (the home key's scale and tonic triad).
All weights are DESIGN (agreed 26 November 2026), not measured.
"""
import copy, math, random
import harmonic_engine as H
import seqcore as S

VERSION = '0.1.0'
GRIDS = {'4': 480, '8': 240, '16': 120}
STATES = [-4, -3, -2, -1, 0, 1, 2, 3, 4]
VOICE_KEYS = ('v1', 'v2', 'v3', 'v4')


def voice(name, density, dchange, part, pchange, low, high, channel, program):
    return dict(name=name, density=density, density_change=dchange, participation=part, participation_change=pchange,
                engine='markov', table='smooth', adherence=0.4, pattern=[0, 2, 1, 2, 0, 3, 1, 2],
                low=low, high=high, velocity=84, channel=channel, program=program)


DEFAULTS = dict(
    enabled=False, follow='chords', grid='8', shortest='16', conventionality=50, interdependence=65,
    evolution='coordinated', window=8, cycle=64, repetition=70, seed=1,
    v1=voice('Voice 1', 45, 40, 85, 50, 67, 84, 0, 73),
    v2=voice('Voice 2', 25, 30, 75, 40, 60, 76, 1, 69),
    v3=voice('Voice 3', 20, 50, 80, 60, 52, 69, 3, 72),
    v4=voice('Voice 4', 25, 20, 90, 30, 40, 57, 4, 33))


# ------------------------------------------------------------------------------------------------ Markov tables
def make_table(step=0.30, third=0.13, fourth=0.05, leap=0.03, repeat=0.06, carry=1.6, recover=2.5):
    """Rows: previous interval; columns: next interval (scale steps, +-4 = 4 or more). Rows sum to 1."""
    table = []
    for prev in STATES:
        row = []
        for nxt in STATES:
            same = prev != 0 and nxt != 0 and (prev > 0) == (nxt > 0)
            w = {0: repeat, 1: step, 2: third, 3: fourth, 4: leap}[abs(nxt)]
            if abs(prev) == 1:
                w *= carry if same and abs(nxt) == 1 else 0.9 if same else 1.0       # runs carry on
            elif abs(prev) >= 3:
                w *= recover if not same and abs(nxt) == 1 else 0.3 if same else 0.8  # leaps step back
            elif abs(prev) == 2:
                w *= 1.3 if not same and abs(nxt) <= 2 else 1.0
            elif prev == 0 and nxt == 0:
                w *= 0.6
            row.append(w)
        s = sum(row)
        table.append([round(x / s, 4) for x in row])
    return table


TABLES = {
    'smooth': make_table(),
    'angular': make_table(step=0.18, third=0.2, fourth=0.14, leap=0.09, carry=1.1, recover=1.8),
    'narrow': make_table(step=0.32, third=0.08, fourth=0.02, leap=0.01, repeat=0.16, carry=1.3),
    'wide': make_table(step=0.2, third=0.2, fourth=0.1, leap=0.06, carry=1.4, recover=2.2),
}


def table_for(spec, name):
    if isinstance(spec, str):
        if spec not in TABLES:
            raise ValueError(f"{name}: table must be one of {', '.join(TABLES)} or a 9 x 9 list.")
        return TABLES[spec]
    rows = [list(map(float, r)) for r in spec]
    if len(rows) != 9 or any(len(r) != 9 or min(r) < 0 or sum(r) <= 0 for r in rows):
        raise ValueError(f'{name}: a custom table needs 9 rows of 9 non-negative numbers.')
    return [[x / sum(r) for x in r] for r in rows]


# ------------------------------------------------------------------------------------------------ settings
def defaults():
    return copy.deepcopy(DEFAULTS)


def resolve(settings):
    cfg = defaults()
    for k, v in (settings or {}).items():
        if k in VOICE_KEYS:
            cfg[k] = dict(cfg[k], **(v or {}))
        else:
            cfg[k] = v
    if cfg['follow'] not in ('chords', 'static'):
        raise ValueError("Rhythm family: follow must be 'chords' or 'static'.")
    if str(cfg['grid']) not in GRIDS or str(cfg['shortest']) not in GRIDS:
        raise ValueError('Rhythm family: grid and shortest must be 4, 8 or 16.')
    if GRIDS[str(cfg['shortest'])] > GRIDS[str(cfg['grid'])]:
        raise ValueError('Rhythm family: the shortest note cannot be longer than the grid spacing.')
    if cfg['evolution'] not in ('coordinated', 'independent', 'steady'):
        raise ValueError('Rhythm family: evolution must be coordinated, independent or steady.')
    for k in ('conventionality', 'interdependence', 'repetition'):
        if not 0 <= float(cfg[k]) <= 100:
            raise ValueError(f'Rhythm family: {k} must be 0-100.')
    if int(cfg['window']) < 1 or int(cfg['cycle']) < 2:
        raise ValueError('Rhythm family: window must be at least 1 bar and cycle at least 2.')
    for k in VOICE_KEYS:
        v = cfg[k]
        for f in ('density', 'participation'):
            if not 0 < float(v[f]) <= 100:
                raise ValueError(f"{v['name']}: {f} must be above 0 and at most 100.")
        for f in ('density_change', 'participation_change'):
            if not 0 <= float(v[f]) <= 100:
                raise ValueError(f"{v['name']}: {f} must be 0-100.")
        if v['engine'] not in ('markov', 'step'):
            raise ValueError(f"{v['name']}: engine must be markov or step.")
        table_for(v['table'], v['name'])
        if not 0 <= float(v['adherence']) <= 1:
            raise ValueError(f"{v['name']}: adherence must be 0-1.")
        if not v['pattern'] or any(int(x) < 0 for x in v['pattern']):
            raise ValueError(f"{v['name']}: the step pattern needs at least one value of 0 or more.")
        lo, hi = int(v['low']), int(v['high'])
        if not 0 <= lo < hi <= 127 or hi - lo < 12:
            raise ValueError(f"{v['name']}: the register must span at least an octave within MIDI 0-127.")
        if not 0 <= int(v['channel']) <= 15:
            raise ValueError(f"{v['name']}: channel must be 0-15.")
    return cfg


# ------------------------------------------------------------------------------------------------ rhythm
class Clock:
    def __init__(self, doc):
        self.bar = H.bar_ticks(doc['meter'])
        num, den = (int(x) for x in doc['meter'].split('/'))
        self.beat = doc['ppq'] * 4 // den
        self.num = num

    def weight(self, t):
        pos = t % self.bar
        if pos == 0:
            return 1.0
        if self.num % 2 == 0 and self.num > 2 and pos == self.bar // 2:
            return 0.8
        if pos % self.beat == 0:
            return 0.6
        if pos % (self.beat // 2) == 0:
            return 0.35
        return 0.2


def phrases(result, bar):
    out = []
    for sec in result['sections']:
        b = sec['start'] * bar
        for j, n in enumerate(sec['phrases']):
            out.append(dict(start=b, end=b + n * bar, label=(sec['identity'], j), last_section=False))
            b += n * bar
    return out


def shapes(cfg, nwin, rng):
    nv = len(VOICE_KEYS)
    strict = float(cfg['interdependence']) / 100
    out = []
    for v in range(nv):
        if cfg['evolution'] == 'steady':
            out.append([0.0] * nwin)
        elif cfg['evolution'] == 'coordinated':
            phase = 2 * math.pi * v / nv * strict + rng.uniform(0, 2 * math.pi) * (1 - strict)
            wobble = 0.0
            row = []
            for w in range(nwin):
                wobble = 0.7 * wobble + rng.uniform(-0.12, 0.12)          # so later cycles are not identical
                t = (w + 0.5) * int(cfg['window']) / int(cfg['cycle'])
                row.append(max(-1, min(1, math.cos(2 * math.pi * t + phase) + wobble)))
            out.append(row)
        else:
            x, row = rng.uniform(-1, 1), []
            for w in range(nwin):
                x = max(-1, min(1, 0.8 * x + rng.uniform(-0.6, 0.6)))
                row.append(x)
            out.append(row)
    return out


def choose(rng, slots, k, conv, clock, others, inter, anchor):
    chosen = {slots[0]} if anchor and k else set()
    pool = [s for s in slots if s not in chosen]
    while len(chosen) < k and pool:
        w = [max(1e-4, clock.weight(s) ** (3 * conv) * (1 - 0.85 * inter * (s in others))) for s in pool]
        s = rng.choices(pool, w)[0]
        chosen.add(s)
        pool.remove(s)
    return sorted(chosen)


def adjust(onsets, slots, k, conv, clock, others, inter, rng, vary):
    ons = sorted(set(o for o in onsets if o in slots))
    key = lambda s: (clock.weight(s) ** (3 * conv) + rng.random() * 0.15) * (1 - 0.85 * inter * (s in others))
    for o in list(ons[1:]):                                    # light variation on return
        if rng.random() < vary:
            ons.remove(o)
            free = [s for s in slots if s not in ons]
            ons.append(rng.choice(free) if free else o)
    ons.sort()
    while len(ons) > k and len(ons) > 1:
        ons.remove(min(ons[1:], key=key))                     # the first onset (the anchor) stays
    free = [s for s in slots if s not in ons]
    while len(ons) < k and free:
        s = max(free, key=key)
        ons.append(s)
        free.remove(s)
    return sorted(ons)


def lengths(rng, onsets, b, target, short, clock, conv):
    gaps = [y - x for x, y in zip(onsets, onsets[1:] + [b])]
    durs = [min(short, g) for g in gaps]
    lo, hi = sum(durs), sum(gaps)
    order = sorted(range(len(onsets)), key=lambda i: -(clock.weight(onsets[i]) * conv + rng.random() * (1 - conv)))
    for i in order:
        total = sum(durs)
        if total >= target:
            break
        gain = gaps[i] - durs[i]
        if total + gain <= target or abs(total + gain - target) <= abs(total - target):
            durs[i] = gaps[i]
    return durs, lo, hi


def rhythm(doc, result, cfg):
    clock = Clock(doc)
    rng = random.Random(f"rhythm-{cfg['seed']}")
    sp, md = GRIDS[str(cfg['grid'])], GRIDS[str(cfg['shortest'])]
    conv, inter = float(cfg['conventionality']) / 100, float(cfg['interdependence']) / 100
    vary = (1 - float(cfg['repetition']) / 100) * 0.5
    win = int(cfg['window']) * clock.bar
    nwin = max(1, -(-doc['end_tick'] // win))
    sh = shapes(cfg, nwin, rng)
    voices = [cfg[k] for k in VOICE_KEYS]
    out = [[] for _ in voices]
    motif, warnings, targets = {}, [[] for _ in voices], [[] for _ in voices]
    phs = phrases(result, clock.bar)
    for ph in phs:
        a, b = ph['start'], min(ph['end'], doc['end_tick'])
        slots = list(range(a, b, sp))
        if not slots:
            continue
        w = min(nwin - 1, ((a + b) // 2) // win)
        others = set()
        for v, vc in enumerate(voices):
            d = max(0.03, min(1.0, (float(vc['density']) + sh[v][w] * float(vc['density_change']) / 2) / 100))
            part = max(0.03, min(1.0, (float(vc['participation']) + sh[v][w] * float(vc['participation_change']) / 2) / 100))
            targets[v].append((a, round(100 * d), round(100 * part)))
            k = max(1, round(d * len(slots)))
            v_conv = conv if v == 0 else conv * 0.6                       # the leading voice is the most metrical
            key = (v, ph['label'])
            if key in motif:
                ons = adjust([a + r for r in motif[key]], slots, k, v_conv, clock, others if v else set(),
                             inter if v else 0, rng, vary)
            else:
                ons = choose(rng, slots, k, v_conv, clock, others if v else set(), inter if v else 0,
                             anchor=rng.random() < conv)
            motif[key] = [o - a for o in ons]
            target = part * (b - a)
            durs, lo, hi = lengths(rng, ons, b, target, sp, clock, v_conv)
            if lo > target:
                durs, lo, hi = lengths(rng, ons, b, target, md, clock, v_conv)
            if not lo <= target <= hi:
                warnings[v].append(dict(bar=a // clock.bar + 1, target=round(100 * part),
                                        possible=[round(100 * lo / (b - a)), round(100 * hi / (b - a))]))
            for o, d_ in zip(ons, durs):
                out[v].append(dict(start=o, duration=d_, phrase=ph['label'], rel=o - a, phrase_end=b,
                                   strength=clock.weight(o)))
            others |= set(ons)
    return out, warnings, targets, clock


# ------------------------------------------------------------------------------------------------ pitch
def harmony_at(ctx, cfg, t):
    """(scale pitch classes, chord pitch classes, root pc) at tick t."""
    if cfg['follow'] == 'static':
        tonic, mode = H.parse_key(ctx.home_key)
        sc = sorted(H.scale_pcs(ctx.home_key))
        lad = S.scale_ladder(tonic, ctx.home_key)
        return sc, {tonic % 12, (tonic + lad[2]) % 12, (tonic + lad[4]) % 12}, tonic % 12
    ev = ctx.chord_at(t)
    sc = sorted(H.scale_pcs(ev['scale']))
    chord = {(ev['root_pc'] + i) % 12 for i in S.chord_ladder(ev)}
    return sorted(set(sc) | chord), chord, ev['root_pc'] % 12


def step_from(p, n, scale):
    """Move n scale steps from pitch p (snapping p into the scale first)."""
    sc = set(scale)
    while p % 12 not in sc:
        p -= 1
    d = 1 if n > 0 else -1
    for _ in range(abs(n)):
        p += d
        while p % 12 not in sc:
            p += d
    return p


def markov_voice(ctx, cfg, v, vc, notes, placed, rng, clock):
    lo, hi = int(vc['low']), int(vc['high'])
    table = table_for(vc['table'], vc['name'])
    adh = float(vc['adherence'])
    rep = float(cfg['repetition']) / 100
    inter = float(cfg['interdependence']) / 100
    lowest = v == len(VOICE_KEYS) - 1
    tonic = H.parse_key(ctx.home_key)[0] % 12
    centre = (lo + hi) // 2
    memory = {}
    prev, state, prev_end = None, 0, None
    for i, n in enumerate(notes):
        t = n['start']
        scale, chord, root = harmony_at(ctx, cfg, t)
        strong = n['strength'] >= 0.6 or n['duration'] >= clock.beat * 2
        gap = t - notes[i - 1]['start'] if i else None
        if prev_end is not None and t - prev_end >= clock.bar:
            state = 0                                                  # a long rest: start afresh
        phrase_last = i + 1 == len(notes) or notes[i + 1]['start'] >= n['phrase_end']
        piece_last = i + 1 == len(notes)
        above = [(q['start'] == t, q['pitch'], q.get('move', 0)) for u in range(v) for q in placed[u]
                 if q['start'] <= t < q['start'] + q['duration']]
        ceiling = min((p for _, p, _ in above), default=128)
        mem = memory.get((n['phrase'], n['rel']))
        cands = []
        for iv in STATES:
            if prev is None:
                cand = min((c for c in range(lo, hi + 1) if c % 12 in chord), key=lambda c: abs(c - centre),
                           default=centre)
                w = 1.0 if iv == 0 else 0.0
            else:
                size = iv if abs(iv) < 4 else iv + (rng.choice([0, 1]) if iv > 0 else -rng.choice([0, 1]))
                cand = step_from(prev, size, scale) if size else step_from(prev, 0, scale)
                w = table[STATES.index(state)][STATES.index(iv)]
                if gap is not None and gap <= GRIDS[str(cfg['grid'])] and abs(iv) >= 3:
                    w *= 0.4                                           # quick notes: steps
                elif gap is not None and gap >= clock.bar // 2 and abs(iv) >= 2:
                    w *= 1.5                                           # after a long gap: leaps welcome
                if mem is not None:
                    w *= 1 + 7 * rep if iv == mem else 1 - 0.6 * rep   # a returning phrase replays its intervals
            if w <= 0:
                continue
            strength = 1.0 if strong else 0.4
            if cand % 12 in chord:
                w *= 1 + adh * strength * 4
            if phrase_last and cand % 12 in chord:
                w *= 4                                                 # phrases end on a chord tone
            if piece_last and cand % 12 == tonic:
                w *= 6                                                 # the piece ends on the tonic
            if lowest and strong and cand % 12 == root:
                w *= 3                                                 # the lowest voice favours roots
            if not lo <= cand <= hi:
                w *= 0.02
            elif (cand - lo < 3 and iv < 0) or (hi - cand < 3 and iv > 0):
                w *= 0.4
            if cand >= ceiling:
                w *= 0.02                                              # stay below the voice above
            for same, p2, mv in above:
                if same and cand % 12 == p2 % 12:
                    w *= 0.15                                          # no unisons or octaves on shared onsets
                if same and mv and prev is not None and (cand - prev) * mv < 0:
                    w *= 1 + 0.5 * inter                               # contrary motion
            cands.append((iv, cand, w))
        iv, pitch, _ = rng.choices(cands, [c[2] for c in cands])[0]
        while pitch > hi:
            pitch -= 12
        while pitch < lo:
            pitch += 12
        if pitch >= ceiling and pitch - 12 >= lo:
            pitch -= 12
        if pitch >= ceiling:                                           # still not below: nearest scale tone below
            below = [c for c in range(lo, min(ceiling, hi + 1)) if c % 12 in set(scale)]
            pitch = below[-1] if below else pitch
        move = 0 if prev is None else (pitch > prev) - (pitch < prev)
        if prev is not None:
            sc = set(scale)
            steps = sum(1 for x in range(min(prev, pitch) + 1, max(prev, pitch) + 1) if x % 12 in sc)
            state = max(-4, min(4, steps * move))
        memory.setdefault((n['phrase'], n['rel']), state)
        n.update(pitch=pitch, move=move)
        prev, prev_end = pitch, t + n['duration']


def step_voice(ctx, cfg, v, vc, notes, placed, clock):
    lo, hi = int(vc['low']), int(vc['high'])
    pattern = [int(x) for x in vc['pattern']]
    prev = None
    for i, n in enumerate(notes):                                       # one step per note: rests use none
        t = n['start']
        if cfg['follow'] == 'static':
            _, chord, root = harmony_at(ctx, cfg, t)
            lad = sorted((pc - root) % 12 for pc in chord)
        else:
            ev = ctx.chord_at(t)
            root, lad = ev['root_pc'] % 12, S.chord_ladder(ev)
        val = pattern[i % len(pattern)]
        pc = (root + lad[val % len(lad)]) % 12
        centre = prev if prev is not None else (lo + hi) // 2
        p = min((c for c in range(lo, hi + 1) if c % 12 == pc), key=lambda c: abs(c - centre))
        if val >= len(lad) and p + 12 <= hi:
            p += 12
        above = [q for u in range(v) for q in placed[u] if q['start'] <= t < q['start'] + q['duration']]
        if above:
            ceil = min(q['pitch'] for q in above)
            while p >= ceil and p - 12 >= lo:
                p -= 12
            if p >= ceil:
                below = [c for c in range(lo, min(ceil, hi + 1)) if (c - root) % 12 in lad]
                p = below[-1] if below else p
            if any(q['start'] == t and q['pitch'] % 12 == p % 12 for q in above):
                below = [c for c in range(lo, p) if (c - root) % 12 in lad]
                p = below[-1] if below else p
        n.update(pitch=p, move=0 if prev is None else (p > prev) - (p < prev))
        prev = p


# ------------------------------------------------------------------------------------------------ parts
def generate(doc, result, plan, settings=None):
    cfg = resolve(settings)
    if not cfg['enabled']:
        return []
    ctx = S.Context(doc, result, plan)
    rhythms, warnings, targets, clock = rhythm(doc, result, cfg)
    rng = random.Random(f"pitch-{cfg['seed']}")
    parts = []
    for v, key in enumerate(VOICE_KEYS):
        vc = cfg[key]
        notes = rhythms[v]
        if vc['engine'] == 'markov':
            markov_voice(ctx, cfg, v, vc, notes, rhythms, rng, clock)
        else:
            step_voice(ctx, cfg, v, vc, notes, rhythms, clock)
        clean = []
        for n in notes:
            vel = int(vc['velocity']) + (10 if n['strength'] >= 1.0 else 4 if n['strength'] >= 0.6 else 0)
            clean.append(dict(start=n['start'], duration=min(n['duration'], doc['end_tick'] - n['start']),
                              pitch=n['pitch'], velocity=max(1, min(127, vel))))
        total = doc['end_tick']
        slots = total // GRIDS[str(cfg['grid'])]
        stats = dict(notes=len(clean), density=round(100 * len(clean) / max(1, slots)),
                     participation=round(100 * sum(n['duration'] for n in clean) / total),
                     lowest=min((n['pitch'] for n in clean), default=None),
                     highest=max((n['pitch'] for n in clean), default=None),
                     infeasible_phrases=len(warnings[v]))
        parts.append(dict(id=f'rv{v + 1}', name=vc['name'], kind='voice', short=f'V{v + 1}',
                          channel=int(vc['channel']), program=int(vc['program']),
                          settings=dict({k: cfg[k] for k in cfg if k not in VOICE_KEYS}, **copy.deepcopy(vc)),
                          notes=clean, stats=stats, targets=targets[v], warnings=warnings[v]))
    return parts
