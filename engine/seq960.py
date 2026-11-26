"""Moog 960 sequencer (Model 1 of the handoff): three rows of values across 8 steps, with per-step modes.

Mechanism
  * `length` steps (default 8). Three rows of per-step values; what each row controls is assignable
    (`rows`, default a = pitch, b = gate, c = time):
      pitch     the step's abstract value (see seqcore: chord or scale ladder)
      gate      how much of the step sounds (0.3 = short, 0.95 = nearly legato)
      velocity  accent on or off for the step
      time      the step's length in grid units (1 or 2): the 960's third-row timing trick
  * Step modes: Play (sound), Rest (time passes, no note), Skip (the step is passed over and takes no time),
    Stop (the sequence halts until its next restart: a section start, or a phrase start with reset 'phrase').
  * Density: the shared level sets how many of the playable steps Play rather than Rest (40 % at level 1,
    all at level 5), switched on in a fixed priority order so a rise adds to what you already hear.
  * Form: each section identity gets its own variant of the pattern; repeats return to it (related repeats); a
    phrase may change one step's value (gradual change). The pattern runs across chord changes; `reset` says
    whether it restarts at each section, each phrase, or never.
DESIGN throughout; Experiment 32's 960 sketch (8 gated quaver steps on chord tones) is the starting point.
"""
import copy, random
import seqcore as S

VERSION = '0.1.0'
ID, NAME = 'm960', 'Seq 960'
ROW_TARGETS = ('pitch', 'gate', 'velocity', 'time')
DEFAULTS = dict(S.COMMON_DEFAULTS, length=8, rows=dict(a='pitch', b='gate', c='time'), skip_rate=0.08,
                stop_rate=0.0, time_rate=0.2, channel=S.CHANNELS[0], program=81, name=NAME)
DENSITY = {1: 0.4, 2: 0.55, 3: 0.7, 4: 0.85, 5: 1.0}
PITCH_VOCAB = [(0, 30), (1, 14), (2, 18), (3, 10), (4, 12), (5, 6), (6, 4), (-1, 6)]
GATES = [(0.3, 2), (0.5, 4), (0.75, 3), (0.95, 1)]


def check(cfg):
    S.check_common(cfg, NAME)
    if not 2 <= int(cfg['length']) <= 16:
        raise ValueError(f'{NAME}: length must be 2-16 steps.')
    targets = list(cfg['rows'].values())
    if sorted(cfg['rows']) != ['a', 'b', 'c'] or any(t not in ROW_TARGETS for t in targets):
        raise ValueError(f"{NAME}: rows a, b and c each control one of {', '.join(ROW_TARGETS)}.")
    if targets.count('pitch') != 1:
        raise ValueError(f'{NAME}: exactly one row must control pitch.')


def make_pattern(rng, cfg):
    L = int(cfg['length'])
    pick = lambda vocab: rng.choices([v for v, w in vocab], [w for v, w in vocab])[0]
    values = {'pitch': [0] + [pick(PITCH_VOCAB) for _ in range(L - 1)],
              'gate': [pick(GATES) for _ in range(L)],
              'velocity': [rng.random() < 0.3 for _ in range(L)],
              'time': [1] + [2 if rng.random() < float(cfg['time_rate']) else 1 for _ in range(L - 1)]}
    values['velocity'][0] = True
    modes = ['play'] + ['skip' if rng.random() < float(cfg['skip_rate']) else 'play' for _ in range(L - 1)]
    if float(cfg['stop_rate']) > 0:
        for k in range(L // 2, L):
            if modes[k] == 'play' and rng.random() < float(cfg['stop_rate']):
                modes[k] = 'stop'
                break
    playable = [k for k in range(1, L) if modes[k] == 'play']
    rng.shuffle(playable)
    playable.sort(key=lambda k: (k % 2, rng.random() * 0.8))           # steps on the beat tend to come first
    return dict(values=values, modes=modes, priority=[0] + playable)


def mutate_with(rng):
    def mutate(pat, n):
        p = copy.deepcopy(pat)
        L = len(p['modes'])
        for _ in range(n):
            k = rng.randrange(1, L) if L > 1 else 0
            cur = p['values']['pitch'][k]
            p['values']['pitch'][k] = rng.choices([v for v, w in PITCH_VOCAB if v != cur],
                                                  [w for v, w in PITCH_VOCAB if v != cur])[0]
        return p
    return mutate


def row(pat, cfg, target, k, default):
    """The value a step takes for a target (pitch/gate/velocity/time), or the default if no row controls it."""
    if target not in cfg['rows'].values():
        return default
    return pat['values'][target][k]


def generate(ctx, settings=None):
    cfg = dict(copy.deepcopy(DEFAULTS), **(settings or {}))
    check(cfg)
    rng = random.Random(f"seq960-{cfg['seed']}")
    L, grid = int(cfg['length']), S.GRIDS[str(cfg['grid'])]
    pats = S.variant_bank(ctx, rng, lambda: make_pattern(rng, cfg), mutate_with(rng), float(cfg['mutation']))
    steps, idx, stopped = [], 0, False
    for ph, pat in zip(ctx.phrases, pats):
        if cfg['reset'] == 'phrase' or (cfg['reset'] in ('section', 'never') and ph['first']):
            if cfg['reset'] != 'never':
                idx = 0
            stopped = False                                  # a Stop lasts until the next restart point
        n_play = max(1, round(len(pat['priority']) * DENSITY[ph['level']]))
        active = set(pat['priority'][:n_play])
        t = ph['start']
        while t < ph['end']:
            if stopped:
                break
            guard = 0
            while pat['modes'][idx] == 'skip' and guard < L:   # Skip: passed over, takes no time
                idx = (idx + 1) % L
                guard += 1
            mode = pat['modes'][idx]
            if mode == 'stop':
                stopped = True
                idx = 0
                break
            dur = grid * int(row(pat, cfg, 'time', idx, 1))
            dur = min(dur, ph['end'] - t)
            if mode == 'play' and idx in active:
                steps.append(dict(t=t, dur=max(1, int(dur * row(pat, cfg, 'gate', idx, 0.5))),
                                  value=row(pat, cfg, 'pitch', idx, 0), accent=bool(row(pat, cfg, 'velocity', idx, idx == 0)),
                                  step=idx))
            t += dur
            idx = (idx + 1) % L
    patterns = [dict(start_bar=ph['start'] // ctx.bar + 1, level=ph['level'], values=p['values'], modes=p['modes'])
                for ph, p in zip(ctx.phrases, pats)]
    return S.realise(ctx, cfg, ID, cfg['name'], steps, extra=dict(patterns=patterns))
