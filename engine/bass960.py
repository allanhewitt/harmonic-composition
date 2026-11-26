"""Moog 960-style bass sequencer (prototype), in the Tangerine Dream / Berlin School manner.

Techniques, each a rule here:
  1. A steady quaver ostinato as the bass: an L-step pattern (default 8) of short notes on a grid,
     mostly root, octave and fifth, with a few scale notes.
  2. Adding and dropping steps: the shared density level (1-5) sets how many steps are switched on
     (half the steps at level 1, all of them at level 5). Steps are
     switched on in a fixed priority order (step 1 first), so a rise in density adds steps to the
     pattern you already hear and a fall removes them.
  3. Pattern length: any length from 3 to 16 steps. Odd lengths run against the bar and drift (phase).
  4. Keyboard transposition: the pattern keeps running and moves to each chord. The chord's bass note is
     the transposition point (so slash chords transpose to their bass). 'fitted' maps each step to the
     chord and scale (a step written as the 3rd becomes the chord's own 3rd, other steps snap to the
     current scale); 'strict' keeps the pattern's exact intervals, as a 960 transposed from a keyboard.
  5. Switching between sequences: every section identity (verse, chorus...) gets its own variant of the
     seed pattern; repeated sections return to it, with occasional single-step changes (related repeats).
  6. Gradual development: at phrase starts a step may change pitch (`mutation`).
The pattern runs on without restarting at chord changes; `reset` restarts it at section starts (default)
or phrase starts, or never.

Model D profile: monophonic, one note at a time with a clear gap before the next note, so every step
restarts the envelopes (the classic chugging sound). Velocity carries a downbeat accent for other synths;
the Model D is not expected to respond to it.
All weights and rules here are DESIGN.
"""
import copy, random
import harmonic_engine as H

VERSION = '0.0.1'
DEFAULTS = dict(name='Bass 960', length=8, grid='8', gate=0.5, transpose='fitted', reset='section',
                mutation=0.3, low=28, high=52, velocity=100, accent=12, channel=2, program=38, seed=1)
GRIDS = {'8': 240, '16': 120}                       # ticks per step at 480 PPQ
DENSITY = {1: 0.5, 2: 0.625, 3: 0.75, 4: 0.875, 5: 1.0}  # share of steps on per shared level (8 steps: 4-8)
# step vocabulary: semitones above the transposition note, with weights (root, octave, fifth, 3rd, scale)
VOCAB = [(0, 34), (12, 20), (7, 18), (-5, 4), (3, 8), (10, 6), (5, 4), (2, 3), (19, 3)]


def make_seed_pattern(rng, length):
    steps = [0] + [rng.choices([v for v, w in VOCAB], [w for v, w in VOCAB])[0] for _ in range(length - 1)]
    # priority order for switching steps on: step 1, then a seeded order favouring steps on the beat
    rest = list(range(1, length))
    rng.shuffle(rest)
    rest.sort(key=lambda k: (k % 2, rng.random() * 0.8))
    return dict(intervals=steps, priority=[0] + rest)


def mutate(pattern, rng, n=1):
    p = copy.deepcopy(pattern)
    for _ in range(n):
        k = rng.randrange(1, len(p['intervals']))
        choices = [v for v, w in VOCAB if v != p['intervals'][k]]
        p['intervals'][k] = rng.choices(choices, [w for v, w in VOCAB if v != p['intervals'][k]])[0]
    return p


def fitted_pitch(iv, base, event):
    """Map a pattern interval onto the current chord and scale, starting from the chord's bass note."""
    root = event['root_pc']
    triad = sorted(event['intervals'])[:3]
    scale = H.scale_pcs(event['scale'])
    oct_, simple = divmod(iv, 12)
    if simple == 0:
        return base + 12 * oct_
    if simple in (3, 4):                                   # the 3rd: the chord's own 3rd (or sus note)
        pc = (root + triad[1]) % 12
    elif simple == 7:                                      # the 5th: the chord's own 5th
        pc = (root + triad[2]) % 12
    else:                                                  # other notes: nearest scale note
        target = (base + simple) % 12
        pc = min(scale, key=lambda s: (min((s - target) % 12, (target - s) % 12), (s - target) % 12))
    return base + 12 * oct_ + ((pc - base) % 12)


def place(p, lo, hi):
    while p < lo:
        p += 12
    while p > hi:
        p -= 12
    return p


def generate(doc, result, plan, settings=None):
    """Bass part for the parts document. `plan` is the density plan (orchestration.plan_levels output)."""
    cfg = dict(DEFAULTS, **(settings or {}))
    L = int(cfg['length'])
    if not 3 <= L <= 16:
        raise ValueError('Pattern length must be 3-16 steps.')
    if cfg['transpose'] not in ('fitted', 'strict'):
        raise ValueError("Transposition must be 'fitted' or 'strict'.")
    lo, hi = int(cfg['low']), int(cfg['high'])
    if hi - lo < 12:
        raise ValueError('The bass register needs at least an octave.')
    step_t = GRIDS[str(cfg['grid'])]
    gate = max(30, min(step_t - 30, int(step_t * float(cfg['gate']))))
    rng = random.Random(f"bass960-{cfg['seed']}")
    seed_pat = make_seed_pattern(rng, L)
    bt = H.bar_ticks(doc['meter'])
    end = doc['end_tick']
    events = sorted(result['events'], key=lambda e: e['start_tick'])
    sections = result['sections']
    # pattern per phrase: identity variants, related repeats, gradual mutation at phrase starts
    bank, phrase_pat = {}, []
    for st in plan:
        sec = sections[st['section']]
        ident = sec['identity']
        if st['first']:
            if ident not in bank:
                bank[ident] = seed_pat if not bank else mutate(seed_pat, rng, 2)
            elif rng.random() < float(cfg['mutation']):
                bank[ident] = mutate(bank[ident], rng, 1)       # related repeat: at most one step changes
            pat = bank[ident]
        else:
            pat = phrase_pat[-1][1]
            if rng.random() < float(cfg['mutation']):
                pat = mutate(pat, rng, 1)
        phrase_pat.append((st, pat))
    starts = [st['bar'] * bt for st, _ in phrase_pat] + [end]
    notes, step_no, ei = [], 0, 0
    for k, (st, pat) in enumerate(phrase_pat):
        a, b = starts[k], starts[k + 1]
        if cfg['reset'] == 'phrase' or (cfg['reset'] == 'section' and st['first']):
            step_no = 0
        n_on = max(1, round(L * DENSITY[st['level']]))
        active = set(pat['priority'][:n_on])
        for t in range(a, b, step_t):
            idx = step_no % L
            step_no += 1
            if idx not in active:
                continue
            while ei + 1 < len(events) and events[ei + 1]['start_tick'] <= t:
                ei += 1
            ev = events[ei]
            base = place(ev['bass_pc'] + 12 * (lo // 12), lo, lo + 11)
            iv = pat['intervals'][idx]
            p = base + iv if cfg['transpose'] == 'strict' else fitted_pitch(iv, base, ev)
            p = place(p, lo, hi)
            vel = min(127, int(cfg['velocity']) + (int(cfg['accent']) if (t % bt) == 0 else 0)) - (0 if idx == 0 else 6)
            notes.append(dict(start=t, duration=min(gate, end - t), pitch=p, velocity=max(1, vel), step=idx))
    stats = dict(notes=len(notes), lowest=min(n['pitch'] for n in notes), highest=max(n['pitch'] for n in notes),
                 patterns=len({tuple(p['intervals']) for _, p in phrase_pat}))
    return dict(id='bass', name=cfg['name'], kind='bass', channel=int(cfg['channel']), program=int(cfg['program']),
                settings=cfg, notes=notes, stats=stats, staccato=True,
                patterns=[dict(bar=st['bar'] + 1, level=st['level'], intervals=p['intervals'],
                               active=sorted(p['priority'][:max(1, round(L * DENSITY[st['level']]))]))
                          for st, p in phrase_pat])
