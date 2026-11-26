"""Eight sequencer engines with fixed characters (handoff models 4-10 and the TB-303; the TR-808 belongs to the drum
family). Each exposes only its signature control(s) plus the shared settings (on/off, follow chords or static,
register, instrument, channel, seed). Everything else is part of the machine's character.

  Euclidean   three interlocking lanes, pulses spread as evenly as possible     signature: cycle (steps)
  Polymetric  three short loops of different lengths drifting against the bar   signature: loop lengths
  TB-303      a 16-step phrase with rests, accents, octave jumps and slides     signature: slide amount
  Turing      a 16-step loop that slowly changes while keeping its identity     signature: change amount
  Metropolix  eight stages of different lengths: holds, single hits, ratchets   signature: ratchet amount
  Marbles     probabilistic notes around chord tones, with deja vu memory       signature: spread
  René        a 4 x 4 grid read along a path, so the order is not linear        signature: path
  Nodal       a network of short phrases joined by weighted links               signature: branching

Density: each machine's steps carry a key and a priority; the shared density plan switches on the first share of
them for each phrase's level (Euclidean redistributes its pulses instead, Marbles scales its trigger chance).
Patterns restart at section starts, except the Turing Machine, whose loop keeps evolving through the piece.
All weights are DESIGN, taken from the C-major mock-ups agreed on 26 November 2026.
"""
import copy, random
import seqcore as S

S16, S8 = S.GRIDS['16'], S.GRIDS['8']


def base(**kw):
    return dict(S.COMMON_DEFAULTS, mutation=0.0, **kw)


def sections(ctx):
    starts = [ph['start'] for ph in ctx.phrases if ph['first']] + [ctx.end]
    return list(zip(starts, starts[1:]))


def pick(rng, vocab):
    return rng.choices([v for v, w in vocab], [w for v, w in vocab])[0]


def finish(ctx, cfg, eid, steps, priority, own_density=False, extra=None):
    if not own_density:
        steps = S.mask_steps(ctx, steps, priority)
    return S.realise(ctx, cfg, eid, cfg['name'], steps, extra=dict(step_priority=priority, **(extra or {})))


def prepare(module, settings):
    cfg = S.resolve(dict(copy.deepcopy(module.DEFAULTS), **(settings or {})))
    S.check_common(cfg, cfg['name'])
    return cfg


# ------------------------------------------------------------------------------------------------ Euclidean
class Euclidean:
    ID, NAME = 'euclid', 'Seq Euclidean'
    DEFAULTS = base(name=NAME, cycle=16, low=48, high=88, anchor=55, profile='poly_synth', channel=S.CHANNELS[1], program=81)
    LANES = [(3 / 16, 0, [0], 0), (5 / 16, 2, [1, 2], 3), (7 / 16, 5, [2, 3, 4], 3)]   # share, rotation, values, octave

    @staticmethod
    def pattern(k, n, rot):
        return [((i + rot) * k) % n < k for i in range(n)]

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        n = int(cfg['cycle'])
        if n not in (8, 12, 16):
            raise ValueError(f'{cls.NAME}: cycle must be 8, 12 or 16 steps.')
        steps, ranked = [], []
        for lane, (share, rot, vals, octv) in enumerate(cls.LANES):
            seen = []
            for k in range(1, n + 1):                   # positions in the order they join as pulses are added
                seen += [(lane, i) for i, on in enumerate(cls.pattern(k, n, rot)) if on and (lane, i) not in seen]
            ranked.append(seen)
        priority = [key for rank in zip(*ranked) for key in rank]
        for lane, (share, rot, vals, octv) in enumerate(cls.LANES):
            k_full = max(1, round(n * share))
            for a, b in sections(ctx):
                hit = 0
                for j, t in enumerate(range(a, b, S16)):
                    k = max(1, round(k_full * S.DENSITY[ctx.level_at(t)]))        # density: fewer, still even, pulses
                    if cls.pattern(k, n, rot)[j % n]:
                        steps.append(dict(t=t, dur=int(S16 * 0.6), value=vals[hit % len(vals)] + octv, accent=j % n == 0,
                                          step=(lane, j % n)))
                        hit += 1
        return finish(ctx, cfg, cls.ID, steps, priority, own_density=True)


# ------------------------------------------------------------------------------------------------ Polymetric
class Polymetric:
    ID, NAME = 'poly', 'Seq Polymetric'
    LOOPS = {'3-5-7': (3, 5, 7), '5-7-8': (5, 7, 8), '5-6-7': (5, 6, 7), '7-9-11': (7, 9, 11)}
    DEFAULTS = base(name=NAME, loops='5-7-8', low=52, high=88, anchor=60, profile='poly_synth', channel=S.CHANNELS[2], program=81)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        if cfg['loops'] not in cls.LOOPS:
            raise ValueError(f"{cls.NAME}: loops must be one of {', '.join(cls.LOOPS)}.")
        rng = random.Random(f"poly-{cfg['seed']}")
        loops = []
        for li, L in enumerate(cls.LOOPS[cfg['loops']]):
            octv = 0 if li == 0 else 3
            vals = [rng.choice([0, 1, 2, 3]) if (k == 0 or rng.random() < 0.4) else None for k in range(L)]
            loops.append((L, vals, octv))
        priority = []
        for li, (L, vals, _) in enumerate(loops):
            on = [k for k in range(L) if vals[k] is not None]
            priority += [(li, on[0])]
        for li, (L, vals, _) in enumerate(loops):
            rest = [(li, k) for k in range(L) if vals[k] is not None and (li, k) not in priority]
            rng.shuffle(rest)
            priority += rest
        steps = []
        for a, b in sections(ctx):
            for i, t in enumerate(range(a, b, S16)):
                for li, (L, vals, octv) in enumerate(loops):
                    v = vals[i % L]
                    if v is not None:
                        steps.append(dict(t=t, dur=int(S16 * 0.8), value=v + octv, accent=i % L == 0, step=(li, i % L)))
        return finish(ctx, cfg, cls.ID, steps, priority)


# ------------------------------------------------------------------------------------------------ TB-303
class TB303:
    ID, NAME = 'tb303', 'Seq TB-303'
    DEFAULTS = base(name=NAME, slide=0.25, value_space='scale', low=40, high=76, anchor=48, channel=S.CHANNELS[3], program=39)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        cfg['value_space'] = 'scale'
        slide = float(cfg['slide'])
        if not 0 <= slide <= 1:
            raise ValueError(f'{cls.NAME}: slide must be between 0 and 1.')
        rng = random.Random(f"303-{cfg['seed']}")
        phrase = []
        for k in range(16):
            phrase.append(dict(v=0 if k == 0 else pick(rng, [(0, 3), (2, 1), (4, 1), (6, 1), (-3, 1), (7, 1)]),
                               rest=k > 0 and rng.random() < 0.3, accent=k == 0 or rng.random() < 0.35,
                               slide=rng.random() < slide, up=k > 0 and rng.random() < 0.2))
        live = [k for k in range(16) if not phrase[k]['rest']]
        priority = [0] + [k for k in live if k and phrase[k]['accent']] + [k for k in live if k and not phrase[k]['accent']]
        steps = []
        for a, b in sections(ctx):
            for i, t in enumerate(range(a, b, S16)):
                s = phrase[i % 16]
                if s['rest']:
                    continue
                steps.append(dict(t=t, dur=int(S16 * (0.95 if s['slide'] else 0.55)), value=s['v'] + (7 if s['up'] else 0),
                                  accent=s['accent'], slide=s['slide'], step=i % 16))
        return finish(ctx, cfg, cls.ID, steps, priority, extra=dict(phrase=phrase))


# ------------------------------------------------------------------------------------------------ Turing Machine
class Turing:
    ID, NAME = 'turing', 'Seq Turing'
    DEFAULTS = base(name=NAME, change=0.3, value_space='scale', channel=S.CHANNELS[4], program=81)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        cfg['value_space'] = 'scale'
        change = float(cfg['change'])
        if not 0 <= change <= 1:
            raise ValueError(f'{cls.NAME}: change must be between 0 and 1.')
        rng = random.Random(f"turing-{cfg['seed']}")
        reg = [rng.randrange(0, 8) for _ in range(16)]
        gates = [k == 0 or rng.random() < 0.65 for k in range(16)]
        others = [k for k in range(1, 16)]
        rng.shuffle(others)
        others.sort(key=lambda k: (k % 4 != 0, rng.random() * 0.5))
        priority = [0] + others
        steps, changes = [], 0
        for i, t in enumerate(range(0, ctx.end, S16)):          # the loop runs through the whole piece
            j = i % 16
            if j == 0 and i and rng.random() < change:           # at most one step rewritten per pass
                k = rng.randrange(1, 16)
                reg[k], gates[k] = rng.randrange(0, 8), rng.random() < 0.65
                changes += 1
            if gates[j]:
                steps.append(dict(t=t, dur=int(S16 * 0.7), value=reg[j], accent=j % 4 == 0, step=j))
        return finish(ctx, cfg, cls.ID, steps, priority, extra=dict(changes=changes))


# ------------------------------------------------------------------------------------------------ Metropolix
class Metropolix:
    ID, NAME = 'metro', 'Seq Metropolix'
    DEFAULTS = base(name=NAME, ratchet=0.35, channel=S.CHANNELS[5], program=81)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        amount = float(cfg['ratchet'])
        if not 0 <= amount <= 1:
            raise ValueError(f'{cls.NAME}: ratchet must be between 0 and 1.')
        rng = random.Random(f"metro-{cfg['seed']}")
        stages = []
        for k in range(8):
            pulses = pick(rng, [(1, 4), (2, 4), (3, 2), (4, 1)])
            u = rng.random()
            if k == 0:
                gate = 'hold' if pulses > 1 else 'single'
            elif u < 0.1:
                gate = 'rest'
            elif u < 0.1 + amount:
                gate = f'ratchet{pick(rng, [(2, 2), (3, 1)])}'
                pulses = max(pulses, 2)
            elif u < 0.25 + amount:
                gate = 'hold'
            else:
                gate = 'single'
            stages.append(dict(v=0 if k == 0 else pick(rng, [(0, 2), (1, 2), (2, 2), (3, 1), (4, 1), (5, 1)]),
                               pulses=pulses, gate=gate))
        live = [k for k in range(8) if stages[k]['gate'] != 'rest']
        rank = {'hold': 0, 'ratchet2': 1, 'ratchet3': 1, 'single': 2}
        priority = [0] + sorted((k for k in live if k), key=lambda k: (rank[stages[k]['gate']], k))
        steps = []
        for a, b in sections(ctx):
            t = a
            while t < b:
                for k, st in enumerate(stages):
                    if t >= b:
                        break
                    length = min(st['pulses'] * S16, b - t)
                    g = st['gate']
                    if g == 'hold':
                        steps.append(dict(t=t, dur=max(30, length - 10), value=st['v'], accent=True, step=k))
                    elif g == 'single':
                        steps.append(dict(t=t, dur=int(S16 * 0.6), value=st['v'], step=k))
                    elif g.startswith('ratchet'):
                        r = int(g[-1])
                        for q in range(r):
                            steps.append(dict(t=t + q * length // r, dur=max(20, length // r - 15), value=st['v'],
                                              accent=q == 0, step=k))
                    t += length
        return finish(ctx, cfg, cls.ID, steps, priority, extra=dict(stages=stages))


# ------------------------------------------------------------------------------------------------ Marbles
class Marbles:
    ID, NAME = 'marbles', 'Seq Marbles'
    DEFAULTS = base(name=NAME, spread=0.5, value_space='scale', channel=S.CHANNELS[6], program=81)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        cfg['value_space'] = 'scale'
        spread = float(cfg['spread'])
        if not 0 <= spread <= 1:
            raise ValueError(f'{cls.NAME}: spread must be between 0 and 1.')
        reach = 1 + round(spread * 3)                                   # largest step between notes, in scale steps
        moves = [m for m in range(-reach, reach + 1)]
        rng = random.Random(f"marbles-{cfg['seed']}")
        priority = sorted(range(16), key=lambda k: (0 if k % 4 == 0 else 1 if k % 2 == 0 else 2, k))
        steps = []
        for a, b in sections(ctx):
            memory, last = [], 4
            for i, t in enumerate(range(a, b, S16)):
                chance = (0.75 if i % 4 == 0 else 0.35 if i % 2 == 0 else 0.2) * S.DENSITY[ctx.level_at(t)]
                if len(memory) >= 8 and rng.random() < 0.65:            # deja vu: replay the decision of 8 steps ago
                    on, v = memory[-8]
                else:
                    on = rng.random() < chance
                    v = max(0, min(9, last + rng.choice(moves)))
                memory.append((on, v))
                if on:
                    last = v
                    steps.append(dict(t=t, dur=int(S16 * 0.8), value=v, accent=i % 4 == 0, step=(i % 16)))
        return finish(ctx, cfg, cls.ID, steps, priority, own_density=True)


# ------------------------------------------------------------------------------------------------ René
class Rene:
    ID, NAME = 'rene', 'Seq René'
    PATHS = ('cartesian', 'snake', 'diagonal')
    DEFAULTS = base(name=NAME, path='cartesian', channel=S.CHANNELS[7], program=81)

    @staticmethod
    def cell(path, i):
        if path == 'cartesian':                          # X moves every step, Y every third step
            return i % 4, (i // 3) % 4
        if path == 'snake':                              # along a row, back along the next
            y, x = divmod(i % 16, 4)
            return (x if y % 2 == 0 else 3 - x), y
        return (i % 4), (i + i // 4) % 4                 # diagonal: Y moves with X, shifting each lap

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        if cfg['path'] not in cls.PATHS:
            raise ValueError(f"{cls.NAME}: path must be one of {', '.join(cls.PATHS)}.")
        rng = random.Random(f"rene-{cfg['seed']}")
        grid = [[rng.choice([0, 1, 2, 3, 4, 5]) for x in range(4)] for y in range(4)]
        gate = [[(x, y) == (0, 0) or rng.random() < 0.8 for x in range(4)] for y in range(4)]
        cells = [(x, y) for y in range(4) for x in range(4) if gate[y][x] and (x, y) != (0, 0)]
        rng.shuffle(cells)
        priority = [(0, 0)] + cells
        steps = []
        for a, b in sections(ctx):
            for i, t in enumerate(range(a, b, S16)):
                x, y = cls.cell(cfg['path'], i)
                if gate[y][x]:
                    steps.append(dict(t=t, dur=int(S16 * 0.7), value=grid[y][x], accent=x == 0, step=(x, y)))
        return finish(ctx, cfg, cls.ID, steps, priority, extra=dict(grid=grid))


# ------------------------------------------------------------------------------------------------ Nodal
class Nodal:
    ID, NAME = 'nodal', 'Seq Nodal'
    DEFAULTS = base(name=NAME, branching=0.5, channel=S.CHANNELS[8], program=81)

    @classmethod
    def generate(cls, ctx, settings=None):
        cfg = prepare(cls, settings)
        branching = float(cfg['branching'])
        if not 0 <= branching <= 1:
            raise ValueError(f'{cls.NAME}: branching must be between 0 and 1.')
        rng = random.Random(f"nodal-{cfg['seed']}")
        names = 'ABCDE'
        nodes = {}
        for n in names:
            size = rng.choice([2, 3, 3, 4])
            nodes[n] = [(0 if (n == 'A' and k == 0) else pick(rng, [(-1, 1), (0, 2), (1, 2), (2, 2), (3, 1), (4, 1)]),
                         pick(rng, [(1, 3), (2, 2), (3, 1)])) for k in range(size)]
        links = {}
        for n in names:
            a, b = rng.sample([m for m in names if m != n], 2)
            links[n] = [(a, 0.7), (b, 0.3)]
        priority = [(n, 0) for n in names] + [(n, k) for k in range(1, 4) for n in names if k < len(nodes[n])]
        steps = []
        for a, b in sections(ctx):
            node, t = 'A', a
            while t < b:
                for k, (v, q) in enumerate(nodes[node]):
                    if t >= b:
                        break
                    steps.append(dict(t=t, dur=min(q * S8 - 20, b - t), value=v, accent=k == 0, step=(node, k)))
                    t += q * S8
                options = links[node]
                weights = [w * (1 - branching) + 0.5 * branching for _, w in options]   # 0: strongest link mostly
                if branching == 0:
                    weights = [1, 0]
                node = rng.choices([m for m, _ in options], weights)[0]
        return finish(ctx, cfg, cls.ID, steps, priority, extra=dict(nodes=nodes, links=links))


ENGINES = [Euclidean, Polymetric, TB303, Turing, Metropolix, Marbles, Rene, Nodal]
