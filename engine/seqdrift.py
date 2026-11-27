"""Seq Drift: four lanes of sixteen-ish steps that arrive at each new chord one step at a time.

Ported from the browser Drift sequencer (26 November 2026) to the sequencer framework. The browser version chose
its own chords; here the chords come from Stage 2, so Drift is a machine for SLOW harmony, where there is time to
hear a chord arrive.

Mechanism
  * Four lanes (Bass, Pad, Line, Top), each with its own register, read over a loop of one bar (16 steps in 4/4).
    Steps hold a gate and an index into the lane's values (chord-ladder positions; the bass uses root and fifth).
  * At each return to step 1 (each bar) a step may flip its gate (`flip`, balanced so the lane settles around a
    density target) or move to a neighbouring chord tone (`move`, the bass at a third of that rate). Both are
    scaled by a slowly wandering pace (`drift`): long still stretches, then movement.
  * When the harmony changes, every step stays on the chord it was reading. At each following loop point a step
    crosses to the nearest note of the new chord with a chance set so that the whole pattern has arrived after
    `arrival` of the chord's length (0.6 = a little over half): a four-bar chord drifts in over about two bars,
    an eight-bar chord over about five. A pitch move also brings a step across.
  * Bass pedal lag (`lag`): the bass holds the old root until this share of the upper steps has arrived.
  * Slow harmony only (`min_chord_bars`): Drift sounds only over chords at least this long, and rests elsewhere,
    keeping its place, so the next slow chord drifts in from the last one it played. 0 = every chord.
  * Density: the shared plan's level scales the lanes' density target (level 3 is the base `density`).
  * It follows the chords by definition (follow: chords); the other harmonic modes are refused.
Off by default: with the default harmony (one- and two-bar chords) it would rest throughout. Switch it on with
slower chord rates (the harmony engine's slowest is four bars; eight-bar chords are not written yet).
All numbers are DESIGN, taken from the browser prototype.
"""
import copy, random
import seqcore as S

VERSION = '0.1.0'
ID, NAME = 'drift', 'Seq Drift'
S16 = S.GRIDS['16']
EPS = 0.05          # share of steps still on the old chord when the arrival window ends
LANES = (
    dict(name='Bass', reg=(33, 52, 40), vals=(0, 2), hold=4, gate=0.9, ymul=0.33),
    dict(name='Pad', reg=(52, 67, 55), vals=(0, 1, 2, 3, 4), hold=4, gate=0.95, ymul=0.7),
    dict(name='Line', reg=(60, 77, 64), vals=tuple(range(7)), hold=1, gate=0.55, ymul=1.0),
    dict(name='Top', reg=(67, 86, 72), vals=tuple(range(7)), hold=1, gate=0.5, ymul=1.0),
)
DEFAULTS = dict(S.COMMON_DEFAULTS, mutation=0.0, name=NAME, enabled=False, follow='chords', harmonic='adapted',
                value_space='chord', profile='poly_synth', low=33, high=86, anchor=55, channel=S.CHANNELS[-1],
                program=81, arrival=0.6, lag=0.75, min_chord_bars=2, density=0.45, flip=0.08, move=0.15, drift=True)


def prepare(settings):
    cfg = dict(copy.deepcopy(DEFAULTS), **(settings or {}))
    if cfg.get('follow', 'chords') != 'chords' or cfg.get('harmonic', 'adapted') != 'adapted':
        raise ValueError(f'{NAME} drifts from one chord to the next, so it needs the chords: '
                         "follow must be 'chords' (and harmonic 'adapted').")
    cfg.update(follow='chords', harmonic='adapted', value_space='chord')
    S.check_common(cfg, NAME)
    for key, lo, hi in (('arrival', 0.05, 1), ('lag', 0, 1), ('density', 0.05, 0.95), ('flip', 0, 0.5), ('move', 0, 0.6),
                        ('min_chord_bars', 0, 32)):
        if not lo <= float(cfg[key]) <= hi:
            raise ValueError(f'{NAME}: {key} must be between {lo} and {hi}.')
    return cfg


class Drift:
    ID, NAME, DEFAULTS = ID, NAME, DEFAULTS

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(settings)
        rng = random.Random(f"drift-{cfg['seed']}")
        n = ctx.bar // S16                                   # steps per loop: one bar
        spb = max(1, ctx.beat // S16)                        # steps per beat
        min_ticks = float(cfg['min_chord_bars']) * ctx.bar
        arrival, lag, dens0 = float(cfg['arrival']), float(cfg['lag']), float(cfg['density'])
        flip, move, wander = float(cfg['flip']), float(cfg['move']), bool(cfg['drift'])
        lane_cfg = [dict(cfg, low=L['reg'][0], high=L['reg'][1], anchor=L['reg'][2]) for L in LANES]

        def pitch(li, idx, ct):
            return S.value_to_pitch(ctx, lane_cfg[li], ct, LANES[li]['vals'][idx], False)

        def arrive(li, st):
            """Move a step to the nearest note of the chord now current."""
            old = pitch(li, st['i'], st['ct'])
            st['i'] = min(range(len(LANES[li]['vals'])), key=lambda j: abs(pitch(li, j, cur_t) - old) + rng.random() * 0.5)
            st['ct'] = cur_t

        grid, cur_t, pace, p_arr, drifted, started = None, None, 1.0, 0.0, 0, False
        steps, timeline = [], []
        for t0 in range(0, ctx.end, ctx.bar):
            ev0 = ctx.chord_at(t0)
            if ev0['duration_ticks'] >= min_ticks:                          # slow harmony: drift state moves on
                if not started:                                             # first slow chord: start settled on it
                    started, cur_t = True, ev0['start_tick']
                    grid = [[dict(on=rng.random() < ((0.8 if i % spb == 0 else 0.15) if li == 0 else dens0),
                                  i=(0 if rng.random() < 0.7 else 1) if li == 0 else rng.randrange(len(L['vals'])),
                                  ct=cur_t) for i in range(n)] for li, L in enumerate(LANES)]
                elif ev0['start_tick'] != cur_t:                            # a new chord: everything stays behind
                    cur_t, drifted = ev0['start_tick'], drifted + 1
                    span = max(1.0, ev0['duration_ticks'] / ctx.bar)
                    p_arr = 1 - EPS ** (1 / max(1.0, arrival * span))
                if wander:
                    pace = max(0.05, min(1.6, pace + (rng.random() - 0.5) * 0.3))
                upper = [st for row in grid[1:] for st in row]
                progress = sum(st['ct'] == cur_t for st in upper) / len(upper)
                bass_ok = progress >= lag
                for li, row in enumerate(grid):                             # arrivals
                    for st in row:
                        if st['ct'] != cur_t and (li > 0 or bass_ok) and rng.random() < p_arr:
                            arrive(li, st)
                d = min(0.95, max(0.05, dens0 * S.DENSITY[ctx.level_at(t0)] / S.DENSITY[3]))
                x, y = flip * pace, move * pace
                p_on = min(1.0, x * d / (1 - d))
                for li, (L, row) in enumerate(zip(LANES, grid)):            # mutation
                    for st in row:
                        if rng.random() < (x if st['on'] else p_on):
                            st['on'] = not st['on']
                        if rng.random() < y * L['ymul']:
                            if st['ct'] != cur_t and (li > 0 or bass_ok):
                                arrive(li, st)
                            else:
                                dl = (1 if rng.random() < 0.8 else 2) * (-1 if rng.random() < 0.5 else 1)
                                st['i'] = max(0, min(len(L['vals']) - 1, st['i'] + dl))
                timeline.append(dict(bar=t0 // ctx.bar, chord_t=cur_t, progress=round(progress, 3), bass_released=bass_ok,
                                     arrived=round(sum(st['ct'] == cur_t for r in grid for st in r) / (4 * n), 3),
                                     pace=round(pace, 2)))
            if grid is None:
                continue
            for li, (L, row) in enumerate(zip(LANES, grid)):                # play this loop from the current state
                for i, st in enumerate(row):
                    t = t0 + i * S16
                    if not st['on'] or t >= ctx.end or ctx.chord_at(t)['duration_ticks'] < min_ticks:
                        continue
                    length = 1
                    while length < L['hold'] and i + length < n and not row[i + length]['on']:
                        length += 1
                    steps.append(dict(t=t, dur=max(1, int(S16 * length * L['gate'])), value=L['vals'][st['i']],
                                      accent=i % spb == 0, step=(li, i), chord_t=st['ct'], reg=L['reg']))
        keys = [(li, i) for li in range(len(LANES)) for i in range(n)]
        priority = sorted(keys, key=lambda k: (0 if k[1] % spb == 0 else 1 if k[1] % max(1, spb // 2) == 0 else 2, k[0], k[1]))
        info = dict(chords_drifted=drifted, loops=len(timeline), bars=ctx.end // ctx.bar, timeline=timeline,
                    min_chord_bars=cfg['min_chord_bars'])
        return S.realise(ctx, cfg, ID, NAME, steps, extra=dict(step_priority=priority, drift=info))
