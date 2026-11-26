"""Drum family: three engines with fixed characters, on MIDI channel 10 (General MIDI drum map by default, which
Superior Drummer 3, Drum Machine Designer and Drum Kit Designer play without setup).

  Drum Machine  exact grid; a style bank (berlin, synthpop, motorik, four, halftime, pulse); accents only on accent
                steps; machine fills (snare rolls rising in velocity, ending on a tom).       signature: style
  Drummer       the same skeleton played: hats pushed slightly ahead, snare behind by `feel`; dynamics rise with the
                density level; ghost notes and the ride at full level; open hat at phrase ends; tom fills that grow
                before section arrivals.                                                   signature: feel (0-1)
  Percussion    three to five interlocking lanes (Euclidean, polymetric, chance with deja vu) from a lane set
                (shakers_rims, metals, toms_hands); slow velocity swells.                  signature: lanes

Shared: `conclusiveness` (0-100). High: kick on the downbeat, a backbeat, crashes at section starts, fills before
arrivals, a final hit. Low (ambient): no downbeat weight, the backbeat replaced by occasional sidesticks, no crashes or
fills, percussion cycles that do not divide the bar, and an ending that fades away.

Density: the Drum Machine and Drummer follow the shared density plan (level 1 hats only, 2 + kick, 3 + snare,
4 + extras, 5 + ghost notes or the ride). Percussion follows the plan by default (lanes join one per level) or evolves
independently (`evolution: independent`). Styles adapt to the meter: backbeats fall on the weak beats (2 and 4 in 4/4,
2 and 3 in 3/4, the second dotted crotchet in 6/8). All weights are DESIGN (agreed 26 November 2026).
"""
import copy, math, random
import harmonic_engine as H
import notation as N
import seqcore as S

VERSION = '0.1.0'
STEP = 120                                   # semiquaver steps (480 ppq)
CHANNEL = 9                                  # MIDI channel 10
GM_MAP = dict(kick=36, side=37, snare=38, clap=39, rim=40, tomlf=41, hatc=42, tomhf=43, hatp=44, toml=45, hato=46,
              tomlm=47, tomhm=48, crash=49, tomh=50, ride=51, bell=53, tamb=54, cow=56, crash2=57, conga_h=62,
              conga_l=64, shaker=70, clave=75, wood=76, tri=81, cabasa=69)
STYLES = ('berlin', 'synthpop', 'motorik', 'four', 'halftime', 'pulse')
LANE_SETS = ('shakers_rims', 'metals', 'toms_hands')
DEFAULTS = dict(
    map=dict(GM_MAP),
    machine=dict(enabled=False, name='Drum Machine', style='berlin', conclusiveness=70, velocity=96, seed=1),
    drummer=dict(enabled=False, name='Drummer', style='motorik', feel=0.4, conclusiveness=75, velocity=92, seed=1),
    percussion=dict(enabled=False, name='Percussion', lanes='shakers_rims', conclusiveness=30, evolution='plan',
                    velocity=80, seed=1))


def defaults():
    return copy.deepcopy(DEFAULTS)


def resolve(settings):
    cfg = defaults()
    for k, v in (settings or {}).items():
        if k not in cfg:
            raise ValueError(f"Drums: unknown setting '{k}' (map, machine, drummer, percussion).")
        cfg[k] = dict(cfg[k], **(v or {}))
    for name, note in cfg['map'].items():
        if not isinstance(note, int) or not 0 <= note <= 127:
            raise ValueError(f'Drums: map entry {name} must be a MIDI note 0-127.')
    for eng in ('machine', 'drummer', 'percussion'):
        c = cfg[eng]
        if not 0 <= float(c['conclusiveness']) <= 100:
            raise ValueError(f"{c['name']}: conclusiveness must be 0-100.")
        if not 1 <= int(c['velocity']) <= 127:
            raise ValueError(f"{c['name']}: velocity must be 1-127.")
    for eng in ('machine', 'drummer'):
        if cfg[eng]['style'] not in STYLES:
            raise ValueError(f"{cfg[eng]['name']}: style must be one of {', '.join(STYLES)}.")
    if not 0 <= float(cfg['drummer']['feel']) <= 1:
        raise ValueError('Drummer: feel must be 0-1.')
    if cfg['percussion']['lanes'] not in LANE_SETS:
        raise ValueError(f"Percussion: lanes must be one of {', '.join(LANE_SETS)}.")
    if cfg['percussion']['evolution'] not in ('plan', 'independent'):
        raise ValueError('Percussion: evolution must be plan or independent.')
    return cfg


# ------------------------------------------------------------------------------------------------ meter
class Grid:
    def __init__(self, doc):
        self.bar_ticks = H.bar_ticks(doc['meter'])
        self.steps = self.bar_ticks // STEP
        quarters = N.tempo_beat(doc['meter'])[1]
        self.spb = max(1, int(round(quarters * 4)))              # steps per counted beat
        self.nb = max(1, self.steps // self.spb)
        self.bars = doc['end_tick'] // self.bar_ticks

    def at(self, beat, frac=0.0):
        s = beat * self.spb + int(round(frac * self.spb))
        return s if 0 <= s < self.steps and beat < self.nb else None

    def strong(self):
        return [0] + ([self.nb // 2] if self.nb >= 4 and self.nb % 2 == 0 else [])

    def backbeats(self):
        if self.nb == 1:
            return []
        if self.nb == 3:
            return [1, 2]
        return [b for b in range(self.nb) if b % 2 == 1]

    def half(self):
        return max(1, self.spb // 2)


def style_lanes(style, g):
    """One bar of the style: {lane: [(step, accent)]}; lanes kick, snare, hatc are core, the rest are extras."""
    beats = [g.at(b) for b in range(g.nb)]
    every = [(s, s % g.spb == 0) for s in range(g.steps)]
    eighths = [(s, s % g.spb == 0) for s in range(0, g.steps, g.half())]
    offs = [(g.at(b, 0.5), False) for b in range(g.nb) if g.at(b, 0.5) is not None and g.spb > 1]
    strong = [(g.at(b), True) for b in g.strong()]
    back = [(g.at(b), True) for b in g.backbeats()]
    last_off = [(g.at(g.nb - 1, 0.5), False)] if g.at(g.nb - 1, 0.5) is not None else []
    push = [(g.at(1, 0.5), False)] if g.nb >= 4 else []
    lanes = {
        'berlin': dict(hatc=every, kick=strong, snare=back, clap=back[-1:], hato=last_off),
        'synthpop': dict(hatc=eighths, kick=strong + push, snare=back, clap=back,
                         tamb=[(s + max(1, g.half() // 2), False) for s, _ in eighths if s + max(1, g.half() // 2) < g.steps],
                         hato=last_off),
        'motorik': dict(hatc=eighths, kick=strong + push, snare=back, kick2=[(g.at(2, 0.5), False)] if g.nb >= 4 else [],
                        hato=last_off),
        'four': dict(hatc=offs, kick=[(b, True) for b in beats], snare=[], clap=back, hato=offs[-1:],
                     tamb=[(s, False) for s, _ in every if s % g.spb not in (0,)][::2]),
        'halftime': dict(hatc=eighths, kick=[(0, True)] + ([(g.at(g.nb - 1, 0.5), False)] if g.nb >= 3 else []),
                         snare=[(g.at(g.nb // 2), True)] if g.nb >= 2 else [], hato=last_off),
        'pulse': dict(hatc=every, kick=[], snare=[], side=[(g.at(g.nb - 1, 0.75 if g.spb >= 4 else 0.5), False)]
                      if g.at(g.nb - 1, 0.75 if g.spb >= 4 else 0.5) is not None else []),
    }[style]
    return {k: [(s, a) for s, a in v if s is not None] for k, v in lanes.items()}


# ------------------------------------------------------------------------------------------------ structure
def phrase_bars(ctx, g):
    """Per bar: (level, phrase index, is first bar of a section, is last bar of a phrase, next phrase rises/arrives)."""
    info = []
    for i, ph in enumerate(ctx.phrases):
        first_bar, last_bar = ph['start'] // g.bar_ticks, (ph['end'] - 1) // g.bar_ticks
        nxt = ctx.phrases[i + 1] if i + 1 < len(ctx.phrases) else None
        arrive = bool(nxt) and (nxt['first'] or nxt['level'] > ph['level'])
        for b in range(first_bar, last_bar + 1):
            info.append(dict(bar=b, level=ph['level'], section_start=ph['first'] and b == first_bar,
                             phrase_end=b == last_bar and nxt is not None, arrive=arrive))
    return info[:g.bars]


def add(notes, bar, step, inst, vel, g, off=0):
    notes.append(dict(t=bar * g.bar_ticks + step * STEP + off, inst=inst, vel=max(1, min(127, int(vel))),
                      step=bar * g.steps + step))


def kit(ctx, cfg, g, played):
    """Drum Machine (played=False) or Drummer (played=True)."""
    c = float(cfg['conclusiveness']) / 100
    rng = random.Random(f"drums-{'drummer' if played else 'machine'}-{cfg['seed']}")
    feel = float(cfg.get('feel', 0.4))
    base = int(cfg['velocity'])
    lanes = style_lanes(cfg['style'], g)
    notes, fills, crashes = [], 0, 0
    bars = phrase_bars(ctx, g)
    for info in bars:
        bar, lvl = info['bar'], info['level']
        final = bar == g.bars - 1
        fill = info['phrase_end'] and c > 0.3 and rng.random() < (0.5 + 0.5 * c if info['arrive'] else 0.35 * c)
        fill_from = g.steps - (2 * g.spb if info['arrive'] and g.nb >= 4 else g.spb) if fill else g.steps
        dyn = {1: -24, 2: -16, 3: -8, 4: 0, 5: 6}[lvl] if played else 0
        if final and c >= 0.5:                                     # a final hit
            add(notes, bar, 0, 'kick', base + 10, g)
            add(notes, bar, 0, 'crash', base + 14, g)
            crashes += 1
            continue
        fade = (1 - 0.35 * (bar - (g.bars - 2))) if c < 0.5 and bar >= g.bars - 2 else 1.0
        active = ['hatc'] + (['kick'] if lvl >= 2 else []) + (['snare'] if lvl >= 3 else []) + \
            ([k for k in lanes if k not in ('hatc', 'kick', 'snare')] if lvl >= 4 else [])
        for lane in active:
            for s, acc in lanes.get(lane, []):
                if s >= fill_from and lane not in ('kick', 'kick2'):
                    continue
                inst = 'kick' if lane == 'kick2' else lane
                if inst == 'kick' and s == 0 and c < 0.4:
                    continue                                       # ambient: no weight on the downbeat
                if inst == 'snare' and c < 0.3:
                    if rng.random() < 0.35:                        # the backbeat only as an occasional sidestick
                        add(notes, bar, s, 'side', (base - 20) * fade, g)
                    continue
                if played and inst == 'hatc' and lvl == 5:
                    inst = 'ride'
                if played and inst == 'hatc' and info['phrase_end'] and lane == 'hatc' and \
                        (s, False) in lanes.get('hato', []):
                    inst = 'hato'
                vel = base + (8 if acc else -14) + dyn
                if inst in ('tamb', 'hato', 'clap', 'side'):
                    vel -= 12
                if played:
                    vel += rng.randint(-7, 7)
                add(notes, bar, s, inst, vel * fade, g)
        if played and lvl == 5:                                    # ghost notes between the hits
            for s in range(g.steps):
                if s % g.half() and s < fill_from and rng.random() < 0.3:
                    add(notes, bar, s, 'snare', rng.randint(24, 38), g)
        if info['section_start'] and c > 0.5 and (bar > 0 or c > 0.7):
            add(notes, bar, 0, 'crash', base + 12, g)
            crashes += 1
        if fill:
            fills += 1
            n = g.steps - fill_from
            if played:
                toms = ['snare', 'tomh', 'tomhm', 'toml', 'tomlf']
                for k in range(n):
                    inst = toms[min(len(toms) - 1, k * len(toms) // n)] if n > 2 else ('snare', 'tomlf')[k % 2]
                    if k % max(1, g.half()) and rng.random() < 0.35:
                        continue                                   # a played fill breathes
                    add(notes, bar, fill_from + k, inst, base - 10 + 3 * k + rng.randint(-5, 5), g)
            else:
                for k in range(n):
                    add(notes, bar, fill_from + k, 'tomh' if k == n - 1 else 'snare', base - 30 + 4 * k, g)
    if played:                                                     # feel: hats ahead, snare behind
        for nt in notes:
            if nt['inst'] in ('hatc', 'hato', 'ride'):
                nt['t'] += int(round(rng.uniform(-6, 2) * (0.5 + feel)))
            elif nt['inst'] in ('snare', 'side'):
                nt['t'] += int(round(12 * feel + rng.uniform(-3, 3)))
            else:
                nt['t'] += rng.randint(-3, 3)
            nt['t'] = max(0, nt['t'])
    return notes, dict(fills=fills, crashes=crashes)


# ------------------------------------------------------------------------------------------------ percussion
def lane_specs(name, g, c):
    """(instrument, mechanism, argument). Cycles divide the bar when conclusive, and do not when ambient."""
    odd = c < 0.5
    n16 = g.steps - 3 if odd else g.steps
    short = lambda lo_, hi_: lo_ if odd else hi_
    return {
        'shakers_rims': [('shaker', 'euclid', (round(0.31 * n16), n16, 3)), ('side', 'poly', (short(5, 8), 1)),
                         ('clave', 'euclid', (2, short(7, 8), 2)), ('conga_l', 'chance', 0.12),
                         ('tri', 'poly', (short(11, g.steps), 1))],
        'metals': [('cabasa', 'euclid', (round(0.44 * n16), n16, 1)), ('tri', 'euclid', (round(0.19 * n16), n16, 5)),
                   ('cow', 'poly', (short(7, 8), 2)), ('tamb', 'chance', 0.18), ('bell', 'euclid', (2, short(9, 8), 4))],
        'toms_hands': [('conga_h', 'euclid', (round(0.31 * n16), n16, 2)), ('conga_l', 'poly', (short(5, 8), 2)),
                       ('wood', 'euclid', (3, short(7, 8), 1)), ('tomh', 'chance', 0.1), ('toml', 'poly', (short(11, g.steps), 1))],
    }[name]


def euclid(k, n, rot):
    return [((i + rot) * k) % n < k for i in range(n)]


def percussion(ctx, cfg, g):
    c = float(cfg['conclusiveness']) / 100
    rng = random.Random(f"drums-percussion-{cfg['seed']}")
    specs = lane_specs(cfg['lanes'], g, c)
    base = int(cfg['velocity'])
    levels = [b['level'] for b in phrase_bars(ctx, g)]
    if cfg['evolution'] == 'independent':                          # its own slow walk through the levels
        x, levels = rng.uniform(1, 5), []
        for b in range(g.bars):
            if b % 4 == 0:
                x = max(1, min(5, x + rng.uniform(-1.2, 1.2)))
            levels.append(int(round(x)))
    patterns = []
    for inst, kind, arg in specs:                                  # poly lanes: hits placed once, by seed
        if kind == 'poly':
            L, hits = arg
            patterns.append(set(rng.sample(range(L), min(hits, L))))
        else:
            patterns.append(None)
    notes = []
    total = g.bars * g.steps
    for li, (inst, kind, arg) in enumerate(specs):
        memory = []
        for i in range(total):
            bar = i // g.steps
            if bar >= len(levels) or li >= levels[bar]:
                memory.append(False)
                continue                                           # lanes join one per density level
            if kind == 'euclid':
                k, n, rot = arg
                hit = euclid(max(1, k), n, rot)[i % n]
            elif kind == 'poly':
                hit = (i % arg[0]) in patterns[li]
            else:
                if len(memory) >= g.steps and rng.random() < 0.7:
                    hit = memory[-g.steps]                         # deja vu
                else:
                    hit = rng.random() < arg * (1.5 if i % g.spb == g.half() else 1)
            memory.append(hit)
            if not hit:
                continue
            s = i % g.steps
            if c < 0.4 and s == 0 and li > 0:
                continue                                           # ambient: no weight on the downbeat
            swell = 0.5 + 0.5 * math.sin(2 * math.pi * i / (4 * g.steps) + li)
            vel = base - 35 + 45 * swell + (14 * c if s % g.spb == 0 else 0) + rng.randint(-5, 5)
            add(notes, bar, s, inst, vel, g)
    return notes, dict(lanes=[s[0] for s in specs])


# ------------------------------------------------------------------------------------------------ parts
def finish(notes, cmap, end):
    """Pitch from the map; one note per (time, pitch), the loudest; short notes that never overlap."""
    best = {}
    for nt in notes:
        key = (nt['t'], cmap[nt['inst']])
        if key not in best or nt['vel'] > best[key]['vel']:
            best[key] = nt
    out = []
    by_pitch = {}
    for (t, p), nt in sorted(best.items()):
        by_pitch.setdefault(p, []).append((t, nt))
    for p, items in by_pitch.items():
        for j, (t, nt) in enumerate(items):
            nxt = items[j + 1][0] if j + 1 < len(items) else end
            dur = min(60, nxt - t, end - t)
            if dur > 0:
                out.append(dict(start=t, duration=dur, pitch=p, velocity=nt['vel'], inst=nt['inst'], step=nt['step']))
    return sorted(out, key=lambda n: (n['start'], n['pitch']))


def generate(doc, result, plan, settings=None):
    cfg = resolve(settings)
    if not any(cfg[e]['enabled'] for e in ('machine', 'drummer', 'percussion')):
        return []
    ctx = S.Context(doc, result, plan)
    g = Grid(doc)
    parts = []
    for eid, short, fn in (('machine', 'DM', lambda c: kit(ctx, c, g, False)),
                           ('drummer', 'Dr', lambda c: kit(ctx, c, g, True)),
                           ('percussion', 'Perc', lambda c: percussion(ctx, c, g))):
        c = cfg[eid]
        if not c['enabled']:
            continue
        raw, stats = fn(c)
        missing = sorted({n['inst'] for n in raw} - set(cfg['map']))
        if missing:
            raise ValueError(f"Drums: the map has no note for {', '.join(missing)}.")
        notes = finish(raw, cfg['map'], doc['end_tick'])
        stats = dict(stats, notes=len(notes), per_bar=round(len(notes) / max(1, g.bars), 1))
        parts.append(dict(id=f'drums_{eid}', name=c['name'], short=short, kind='drums', channel=CHANNEL, program=0,
                          settings=dict(copy.deepcopy(c), map=dict(cfg['map'])), notes=notes, stats=stats))
    return parts
