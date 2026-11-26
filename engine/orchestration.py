"""Orchestration of pads (prototype): which pad voices sound where, driven by density.

The parts in step 4 are generated for the whole song. This layer decides how much of them is heard,
section by section and phrase by phrase, and returns an arranged copy. The full parts are kept.

Model
  * One pad is the constant: it plays throughout, unchanged.
  * The other pad (the variable pad) enters and leaves one voice at a time. Density levels:
        1  constant pad alone
        2  + one voice of the variable pad
        3  + two voices
        4  + all three voices (a 2-note variable pad stops at 3)
        top  the variable pad re-strikes every chord instead of holding shared notes
  * A density target per section comes from a contour: 'role' (verse lower, chorus higher, intro and
    outro lowest), 'rising', 'arch' or 'flat'.
  * At every phrase start the level may move one step: towards the target most of the time, away from
    it occasionally. `randomness` (0-1) sets how loosely the target is followed. Moves are more likely
    at section starts than at phrase starts inside a section (`phrase_changes` scales the latter; 0 means
    changes only at section starts).
  * Related repeats: a section that has occurred before aims at the level its previous occurrence started
    on, instead of the contour.
  * Which voice enters or leaves is chosen at random (seeded); the voices already sounding stay.
  * Velocity rises a few points per level (`velocity_step`), so a change is felt as much as heard.
All of this is DESIGN, not measured.
"""
import copy, math, random
import harmonic_engine as H

VERSION = '0.0.1'
DEFAULTS = dict(constant='pad2', contour='role', randomness=0.5, phrase_changes=0.5, low=1, high=None,
                velocity_step=3, seed=1)
ROLE_TARGET = {'intro': 0.1, 'verse': 0.35, 'prechorus': 0.6, 'pre-chorus': 0.6, 'chorus': 0.8, 'bridge': 0.55,
               'instrumental': 0.65, 'solo': 0.65, 'breakdown': 0.2, 'outro': 0.15, 'coda': 0.15}


def boundaries(result):
    """Phrase starts in bars, each marked as a section start or not."""
    out = []
    for i, sec in enumerate(result['sections']):
        b = sec['start']
        for j, ph in enumerate(sec['phrases']):
            out.append(dict(bar=b, section=i, first=j == 0))
            b += ph
    return out


def contour_value(kind, sec, i, n):
    x = i / max(1, n - 1)
    if kind == 'flat':
        return 0.5
    if kind == 'rising':
        return 0.1 + 0.8 * x
    if kind == 'arch':
        return 0.1 + 0.8 * math.sin(math.pi * x)
    if kind == 'role':
        return ROLE_TARGET.get(sec['identity'].lower(), 0.15 if i in (0, n - 1) else 0.45 + 0.2 * (i % 2))
    raise ValueError(f'Unknown contour {kind!r}.')


def plan_levels(result, top, cfg):
    """Density level at every phrase start."""
    rng = random.Random(f"orchestration-{cfg['seed']}")
    lo, hi = int(cfg['low']), int(cfg['high'] or top)
    if not 1 <= lo <= hi <= top:
        raise ValueError(f'Density range must lie within 1-{top}.')
    r = float(cfg['randomness'])
    secs = result['sections']
    plan, level, remembered = [], None, {}
    for bd in boundaries(result):
        sec = secs[bd['section']]
        key = sec['identity']
        if bd['first'] and key in remembered:
            target = remembered[key]                                    # related repeat
        else:
            target = lo + round(contour_value(cfg['contour'], sec, bd['section'], len(secs)) * (hi - lo))
        if level is None:
            level = target
        else:
            scale = 1.0 if bd['first'] else float(cfg['phrase_changes'])
            u = rng.random()
            if level != target:
                step = 1 if target > level else -1
                if u < (1 - 0.6 * r) * scale:
                    level += step                                       # towards the target
                elif u < (1 - 0.6 * r) * scale + 0.15 * r * scale:
                    level -= step                                       # occasionally away
            elif u < 0.5 * r * scale:
                level += rng.choice((-1, 1))                            # drift off target
        level = max(lo, min(hi, level))
        if bd['first']:
            remembered[key] = level
        plan.append(dict(bd, level=level, target=target))
    return plan


def arrange_pads(doc, result, settings=None):
    """Arranged copy of the parts document, plus the level plan."""
    cfg = dict(DEFAULTS, **(settings or {}))
    pads = {p['id']: p for p in doc['parts'] if p['kind'] == 'pad'}
    if cfg['constant'] not in pads or len(pads) != 2:
        raise ValueError('Orchestration needs both pads, with one of them as the constant.')
    const = pads[cfg['constant']]
    var = next(p for pid, p in pads.items() if pid != cfg['constant'])
    nv = len(var['voicings'][0])
    top = 1 + nv + 1                                                    # constant, +each voice, re-strike
    plan = plan_levels(result, top, cfg)
    rng = random.Random(f"orchestration-voices-{cfg['seed']}")
    bt = H.bar_ticks(doc['meter'])
    end = doc['end_tick']
    # active voice positions (0 = lowest) for each plan segment
    active, segs = [], []
    for k, p in enumerate(plan):
        want = min(p['level'] - 1, nv)
        while len(active) < want:
            free = [v for v in range(nv) if v not in active]
            active.append(rng.choice(free))
        while len(active) > want:
            active.remove(rng.choice(active))
        a = p['bar'] * bt
        b = plan[k + 1]['bar'] * bt if k + 1 < len(plan) else end
        segs.append(dict(start=a, end=b, voices=sorted(active), restrike=p['level'] == top, level=p['level']))
    # rebuild the variable pad's notes from its voicings, per chord span split at segment starts
    spans = doc['chords']
    pieces = []
    for sp, v in zip(spans, var['voicings']):
        cuts = sorted({sp['start'], sp['end']} | {s['start'] for s in segs if sp['start'] < s['start'] < sp['end']})
        for a, b in zip(cuts, cuts[1:]):
            seg = next(s for s in segs if s['start'] <= a < s['end'])
            pieces.append(dict(start=a, end=b, chord_start=a == sp['start'], pitches=[v[i] for i in seg['voices']],
                               restrike=seg['restrike'], level=seg['level']))
    base_v = var['settings']['velocity']
    notes, sounding = [], {}
    for pc in pieces:
        vel = max(1, min(127, base_v + cfg['velocity_step'] * (pc['level'] - 3)))
        keep = {} if (pc['restrike'] and pc['chord_start']) else {p: s for p, s in sounding.items() if p in pc['pitches']}
        for p, (s, vv) in sounding.items():
            if p not in keep:
                notes.append(dict(start=s, duration=pc['start'] - s, pitch=p, velocity=vv))
        sounding = {p: keep[p] for p in keep}
        for p in pc['pitches']:
            sounding.setdefault(p, (pc['start'], vel))
    notes += [dict(start=s, duration=end - s, pitch=p, velocity=vv) for p, (s, vv) in sounding.items()]
    notes.sort(key=lambda n: (n['start'], n['pitch']))
    arranged_var = dict(copy.deepcopy(var), notes=notes, segments=segs)
    # constant pad: unchanged notes, velocity following the level
    cnotes = []
    for n in const['notes']:
        lev = next(s['level'] for s in segs if s['start'] <= n['start'] < s['end'])
        cnotes.append(dict(n, velocity=max(1, min(127, n['velocity'] + cfg['velocity_step'] * (lev - 3)))))
    arranged_const = dict(copy.deepcopy(const), notes=cnotes, segments=segs)
    parts = [arranged_const if p['id'] == const['id'] else arranged_var if p['id'] == var['id'] else p
             for p in doc['parts']]
    return dict(copy.deepcopy(doc), parts=parts, orchestration=dict(version=VERSION, settings=cfg, plan=plan, top=top))
