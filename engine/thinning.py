"""Density filter (prototype): keep only a share of the notes in pads and lines.

Settings
  keep        0-100, the share of each part kept (100 = everything).
  parts       optional per-part values, e.g. {'descant': 50}, overriding `keep` for that part.
  mode        'even'     the same share removed in every phrase
              'flatten'  more removed where a part is busiest, so clutter goes first
              'contrast' more removed where a part is already sparse, so the busy passages stand out
  randomness  0-1: how far chance, rather than importance, decides which notes go (seeded).
  exempt      parts never thinned (the constant pad by default).
What counts: lines count notes; pads count sounding time (a held pad note can last several bars).
Which notes go: weak-beat, short and inner notes first. Protected: the first and last note of every
phrase, and in the inner lines the notes that arrive with a chord change. A removed note leaves a rest.
Repeated sections with the same notes lose the same notes, so related repeats stay related.
DESIGN, not measured.
"""
import copy, random
import harmonic_engine as H

VERSION = '0.0.1'
DEFAULTS = dict(keep=100, parts={}, mode='even', randomness=0.3, exempt=['pad2'], seed=1)
MODES = {'even': 0, 'flatten': 1, 'contrast': -1}


def phrase_bounds(result, bt, end):
    out = []
    for si, sec in enumerate(result['sections']):
        b = sec['start'] * bt
        for j, ph in enumerate(sec['phrases']):
            out.append(dict(start=b, end=b + ph * bt, section=si, index=j, identity=sec['identity']))
            b += ph * bt
    out[-1]['end'] = max(out[-1]['end'], end)
    return out


def importance(n, ph, bt, beat, chord_starts, inner, rng, randomness):
    t = n['start']
    pos = t % bt
    metric = 1.0 if pos == 0 else 0.7 if pos % (2 * beat) == 0 else 0.5 if pos % beat == 0 else 0.25
    length = min(1.0, n['duration'] / bt)
    score = 0.6 * metric + 0.4 * length + (0.4 if inner and t in chord_starts else 0)
    return (1 - randomness) * score + randomness * rng.random()


def thin_part(part, result, doc, keep, cfg):
    if keep >= 100 or not part['notes']:
        return part, dict(kept=1.0)
    bt = H.bar_ticks(doc['meter'])
    beat = doc['ppq'] * 4 // int(doc['meter'].split('/')[1])
    end = doc['end_tick']
    chord_starts = {e['start_tick'] for e in result['events']}
    phrases = phrase_bounds(result, bt, end)
    is_pad = part['kind'] == 'pad'
    inner = part['id'] in ('tenor', 'alto')
    weight = (lambda n: n['duration']) if is_pad else (lambda n: 1)
    # notes per phrase, with protection and importance
    groups = []
    for ph in phrases:
        ns = [n for n in part['notes'] if ph['start'] <= n['start'] < ph['end']]
        if not ns:
            continue
        occ_key = (ph['identity'], ph['index'], tuple((n['start'] - ph['start'], n['pitch']) for n in ns))
        rng = random.Random(f"thin-{cfg['seed']}-{part['id']}-{occ_key}")    # same notes, same choices
        first, last = min(n['start'] for n in ns), max(n['start'] for n in ns)
        rows = []
        for n in ns:
            protected = n['start'] in (first, last) or (inner and n['start'] in chord_starts)
            rows.append(dict(note=n, w=weight(n), protected=protected and not is_pad,
                             score=importance(n, ph, bt, beat, chord_starts, inner, rng, cfg['randomness'])))
        total = sum(r['w'] for r in rows)
        groups.append(dict(rows=rows, total=total, density=total / (ph['end'] - ph['start'])))
    grand = sum(g['total'] for g in groups)
    target = grand * (1 - keep / 100)
    k = MODES[cfg['mode']]
    mean = sum(g['density'] for g in groups) / len(groups)
    shares = [g['total'] * ((g['density'] / mean) ** k if mean > 0 else 1) for g in groups]
    # allocate removal across phrases, capped by what each phrase can lose; redistribute the rest
    alloc = [0.0] * len(groups)
    cap = [sum(r['w'] for r in g['rows'] if not r['protected']) for g in groups]
    left, open_ = target, set(range(len(groups)))
    for _ in range(10):
        if left <= 1e-6 or not open_:
            break
        tot = sum(shares[i] for i in open_)
        if tot <= 0:
            break
        spill = 0.0
        for i in list(open_):
            want = left * shares[i] / tot
            room = cap[i] - alloc[i]
            take = min(want, room)
            alloc[i] += take
            spill += want - take
            if cap[i] - alloc[i] <= 1e-6:
                open_.discard(i)
        left = spill
    removed = set()
    for g, a in zip(groups, alloc):
        got = 0.0
        for r in sorted((r for r in g['rows'] if not r['protected']), key=lambda r: r['score']):
            if got + r['w'] / 2 > a:
                break
            removed.add(id(r['note']))
            got += r['w']
    out = copy.deepcopy(part)
    out['notes'] = [copy.deepcopy(n) for n in part['notes'] if id(n) not in removed]
    kept_w = sum(weight(n) for n in out['notes'])
    return out, dict(kept=round(kept_w / grand, 3) if grand else 1.0, target=keep / 100)


def apply(doc, result, settings=None):
    cfg = dict(DEFAULTS, **(settings or {}))
    if cfg['mode'] not in MODES:
        raise ValueError(f"Thinning mode must be one of {', '.join(MODES)}.")
    report, parts = {}, []
    for p in doc['parts']:
        if p['kind'] not in ('pad', 'line') or p['id'] in cfg['exempt']:
            parts.append(p)
            continue
        keep = float(cfg['parts'].get(p['id'], cfg['keep']))
        if not 0 <= keep <= 100:
            raise ValueError(f"Keep for {p['id']} must be 0-100.")
        q, rep = thin_part(p, result, doc, keep, cfg)
        parts.append(q)
        report[p['id']] = rep
    return dict(doc, parts=parts, thinning=dict(version=VERSION, settings=cfg, report=report))
