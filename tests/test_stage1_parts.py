"""Tests for orchestration, the 960 bass, lines, the density filter and the piece runner."""
import collections
import tempfile
from pathlib import Path

import pytest
import yaml

import composition_generator as C
import harmonic_engine as H
import parts as PT
import orchestration as O
import bass960 as B
import lines as LN
import thinning as T
import piece as P
import sequencers as SQ

SONGS = {}


def song(key='A minor', meter='4/4', seed='5', rates=(0.25, 0.5), length='64'):
    k = (key, meter, seed, rates, length)
    if k not in SONGS:
        SONGS[k] = C.compose(dict(key=key, meter=meter, seed=seed, tempo='112', length=length),
                             harmony={'rates': list(rates)})[1]
    return SONGS[k]


CASES = [('A minor', '4/4', '5', (0.25, 0.5)), ('D dorian', '3/4', '2', (0.5, 1)), ('F major', '6/8', '3', (0.5, 1)),
         ('E phrygian', '4/4', '4', (1, 2))]


def build(case, orch=None, bass=None, lines=None):
    r = song(*case)
    doc = O.arrange_pads(PT.generate_parts(r), r, orch or {})
    plan = doc['orchestration']['plan']
    b = B.generate(doc, r, plan, bass or {})
    ls = LN.generate(doc, r, plan, lines or {})
    return r, doc, plan, b, ls


def mono(notes):
    ns = sorted(notes, key=lambda n: n['start'])
    return all(a['start'] + a['duration'] <= b['start'] for a, b in zip(ns, ns[1:]))


# ---------------------------------------------------------------- orchestration
@pytest.mark.parametrize('case', CASES)
def test_plan_moves_one_step_and_stays_in_range(case):
    r, doc, plan, b, ls = build(case)
    levels = [st['level'] for st in plan]
    assert all(1 <= lv <= 5 for lv in levels)
    assert all(abs(a - b) <= 1 for a, b in zip(levels, levels[1:]))
    assert [st['bar'] for st in plan] == sorted(st['bar'] for st in plan)
    assert plan[0]['bar'] == 0


@pytest.mark.parametrize('case', CASES)
def test_constant_pad_is_unchanged_and_variable_pad_follows_levels(case):
    r = song(*case)
    full = PT.generate_parts(r)
    doc = O.arrange_pads(full, r, {})
    const_full = next(p for p in full['parts'] if p['id'] == 'pad2')
    const_arr = next(p for p in doc['parts'] if p['id'] == 'pad2')
    assert [(n['start'], n['duration'], n['pitch']) for n in const_full['notes']] == \
        [(n['start'], n['duration'], n['pitch']) for n in const_arr['notes']]
    var = next(p for p in doc['parts'] if p['id'] == 'pad3')
    for seg in var['segments']:
        mid = (seg['start'] + seg['end']) // 2
        sounding = [n for n in var['notes'] if n['start'] <= mid < n['start'] + n['duration']]
        assert len(sounding) <= min(seg['level'] - 1, 3)


def test_orchestration_is_reproducible_and_seed_sensitive():
    r = song(*CASES[0])
    a = O.arrange_pads(PT.generate_parts(r), r, dict(seed=3))
    b = O.arrange_pads(PT.generate_parts(r), r, dict(seed=3))
    c = O.arrange_pads(PT.generate_parts(r), r, dict(seed=4, randomness=1.0))
    assert a == b
    assert [s['level'] for s in a['orchestration']['plan']] != [s['level'] for s in c['orchestration']['plan']] \
        or a['parts'] != c['parts']


def test_randomness_zero_follows_target():
    r = song(*CASES[0])
    doc = O.arrange_pads(PT.generate_parts(r), r, dict(randomness=0.0, phrase_changes=1.0))
    for st in doc['orchestration']['plan']:
        assert abs(st['level'] - st['target']) <= 4      # moves only towards the target
    levels = [st['level'] for st in doc['orchestration']['plan']]
    targets = [st['target'] for st in doc['orchestration']['plan']]
    for i in range(1, len(levels)):
        if levels[i] != levels[i - 1]:
            assert (levels[i] - levels[i - 1]) * (targets[i] - levels[i - 1]) > 0


# ---------------------------------------------------------------- bass
@pytest.mark.parametrize('case', CASES)
def test_bass_is_monophonic_in_register_on_grid(case):
    r, doc, plan, b, ls = build(case)
    cfg = b['settings']
    assert mono(b['notes'])
    assert all(cfg['low'] <= n['pitch'] <= cfg['high'] for n in b['notes'])
    assert all(n['start'] % B.GRIDS[str(cfg['grid'])] == 0 for n in b['notes'])
    assert all(n['duration'] < B.GRIDS[str(cfg['grid'])] for n in b['notes'])     # a gap before every step


@pytest.mark.parametrize('case', CASES)
def test_bass_step_count_follows_density(case):
    r, doc, plan, b, ls = build(case)
    bt = H.bar_ticks(doc['meter'])
    L = b['settings']['length']
    for k, st in enumerate(plan):
        a = st['bar'] * bt
        e = plan[k + 1]['bar'] * bt if k + 1 < len(plan) else doc['end_tick']
        steps = (e - a) // B.GRIDS['8']
        n = sum(1 for x in b['notes'] if a <= x['start'] < e)
        want = max(1, round(L * B.DENSITY[st['level']]))
        assert abs(n - steps * want / L) <= want, (st, n, steps)


def test_bass_fitted_notes_belong_to_chord_or_scale():
    r, doc, plan, b, ls = build(CASES[0])
    ev = sorted(r['events'], key=lambda e: e['start_tick'])
    for n in b['notes']:
        e = LN.chord_at(ev, n['start'])
        ok = set(H.scale_pcs(e['scale'])) | {(e['root_pc'] + i) % 12 for i in e['intervals']} | {e['bass_pc']}
        assert n['pitch'] % 12 in ok


def test_bass_first_step_of_each_section_is_the_bass_note():
    r, doc, plan, b, ls = build(CASES[0], bass=dict(reset='section'))
    ev = sorted(r['events'], key=lambda e: e['start_tick'])
    bt = H.bar_ticks(doc['meter'])
    for sec in r['sections']:
        t = sec['start'] * bt
        n = next(x for x in b['notes'] if x['start'] == t)
        assert n['pitch'] % 12 == LN.chord_at(ev, t)['bass_pc']


def test_bass_strict_and_odd_length_and_errors():
    r, doc, plan, b, ls = build(CASES[0], bass=dict(transpose='strict', length=7))
    assert b['settings']['length'] == 7 and mono(b['notes'])
    for bad in (dict(length=2), dict(transpose='loose'), dict(low=40, high=48)):
        with pytest.raises(ValueError):
            B.generate(doc, r, plan, bad)


def test_bass_related_repeats():
    r, doc, plan, b, ls = build(CASES[0], bass=dict(mutation=0.0))
    by_id = collections.defaultdict(set)
    for p in b['patterns']:
        st = next(s for s in plan if s['bar'] + 1 == p['bar'])
        if st['first']:
            by_id[r['sections'][st['section']]['identity']].add(tuple(p['intervals']))
    assert all(len(v) == 1 for v in by_id.values())


# ---------------------------------------------------------------- lines
@pytest.mark.parametrize('case', CASES)
def test_lines_monophonic_in_register(case):
    r, doc, plan, b, ls = build(case)
    for p in ls:
        cfg = p['settings']
        assert mono(p['notes']), p['id']
        assert all(cfg['low'] <= n['pitch'] <= cfg['high'] for n in p['notes']), p['id']


@pytest.mark.parametrize('case', CASES)
def test_inner_lines_use_chord_tones_and_avoid_each_other(case):
    r, doc, plan, b, ls = build(case)
    ev = sorted(r['events'], key=lambda e: e['start_tick'])
    tenor, alto = ls[0]['notes'], ls[1]['notes']
    for n in tenor + alto:
        e = LN.chord_at(ev, n['start'])
        assert n['pitch'] % 12 in set(LN.chord_tone_pcs(e))
    for n in alto:
        same = [t for t in tenor if t['start'] <= n['start'] < t['start'] + t['duration'] and t['pitch'] == n['pitch']]
        assert not same


def test_lines_enter_by_level():
    r, doc, plan, b, ls = build(CASES[0])
    bt = H.bar_ticks(doc['meter'])
    for k, st in enumerate(plan):
        a = st['bar'] * bt
        e = plan[k + 1]['bar'] * bt if k + 1 < len(plan) else doc['end_tick']
        for p in ls:
            on = LN.LINES[p['id']]['ladder'][st['level']][2]
            if not on:
                assert not [n for n in p['notes'] if a <= n['start'] < e], (p['id'], st)


def test_descant_lands_on_chord_tones_on_strong_beats():
    r, doc, plan, b, ls = build(CASES[0], orch=dict(contour='rising', randomness=0.0))
    ev = sorted(r['events'], key=lambda e: e['start_tick'])
    bt = H.bar_ticks(doc['meter'])
    desc = ls[2]['notes']
    assert desc, 'a rising plan should reach the descant'
    for n in desc:
        if n['start'] % bt == 0:
            e = LN.chord_at(ev, n['start'])
            assert n['pitch'] % 12 in {(e['root_pc'] + i) % 12 for i in sorted(e['intervals'])[:3]}


def test_lines_reproducible():
    a = build(CASES[1], lines=dict(seed=9))[4]
    b = build(CASES[1], lines=dict(seed=9))[4]
    assert a == b


# ---------------------------------------------------------------- density filter
@pytest.mark.parametrize('mode', ['even', 'flatten', 'contrast'])
def test_thinning_reduces_and_exempts_constant(mode):
    r, doc, plan, b, ls = build(CASES[0])
    full = dict(doc, parts=ls + doc['parts'] + [b])
    out = T.apply(full, r, dict(keep=50, mode=mode))
    before = {p['id']: p for p in full['parts']}
    for p in out['parts']:
        if p['id'] in ('pad2', 'bass'):
            assert p['notes'] == before[p['id']]['notes']
            continue
        assert len(p['notes']) <= len(before[p['id']]['notes'])
        assert {(n['start'], n['pitch']) for n in p['notes']} <= {(n['start'], n['pitch']) for n in before[p['id']]['notes']}
        rep = out['thinning']['report'][p['id']]
        assert rep['kept'] >= 0.45 and rep['kept'] <= 1.0


def test_thinning_protects_phrase_edges_and_keep_100_is_identity():
    r, doc, plan, b, ls = build(CASES[0])
    full = dict(doc, parts=ls + doc['parts'])
    same = T.apply(full, r, dict(keep=100))
    assert [p['notes'] for p in same['parts']] == [p['notes'] for p in full['parts']]
    out = T.apply(full, r, dict(keep=10))
    bt = H.bar_ticks(doc['meter'])
    phrases = T.phrase_bounds(r, bt, doc['end_tick'])
    for p, q in zip(full['parts'], out['parts']):
        if p['kind'] != 'line':
            continue
        kept = {(n['start'], n['pitch']) for n in q['notes']}
        for ph in phrases:
            ns = [n for n in p['notes'] if ph['start'] <= n['start'] < ph['end']]
            if ns:
                first = min(ns, key=lambda n: n['start'])
                assert (first['start'], first['pitch']) in kept


def test_thinning_per_part_and_bad_settings():
    r, doc, plan, b, ls = build(CASES[0])
    full = dict(doc, parts=ls + doc['parts'])
    out = T.apply(full, r, dict(keep=100, parts={'descant': 40}))
    assert set(out['thinning']['report']) >= {'descant'}
    assert out['thinning']['report']['alto']['kept'] == 1.0
    with pytest.raises(ValueError):
        T.apply(full, r, dict(mode='random'))
    with pytest.raises(ValueError):
        T.apply(full, r, dict(keep=120))


def test_thinning_reproducible_across_runs():
    r, doc, plan, b, ls = build(CASES[0])
    full = dict(doc, parts=ls + doc['parts'])
    a = T.apply(full, r, dict(keep=60, mode='flatten', seed=2))
    b2 = T.apply(full, r, dict(keep=60, mode='flatten', seed=2))
    assert [p['notes'] for p in a['parts']] == [p['notes'] for p in b2['parts']]


# ---------------------------------------------------------------- piece runner
EXAMPLE = Path(__file__).resolve().parents[1] / 'pieces' / 'examples' / 'night_transit.yaml'


def test_piece_runner_writes_everything_and_resolved_rebuilds():
    with tempfile.TemporaryDirectory() as d:
        script = yaml.safe_load(EXAMPLE.read_text())
        script['output'] = dict(folder=d, stem='t', score=False, midi=True)
        script['density'] = dict(keep=60, mode='flatten')
        sp = Path(d) / 't.yaml'
        sp.write_text(yaml.safe_dump(script))
        r1 = P.run(sp)
        names = {f.name for f in r1['files']}
        assert 't_all_parts.mid' in names and 't_resolved.yaml' in names
        resolved = Path(d) / 't_resolved.yaml'
        r2 = P.run(resolved)
        assert [p['notes'] for p in r1['doc']['parts']] == [p['notes'] for p in r2['doc']['parts']]


def test_piece_runner_rejects_unknown_sections_and_missing_piece():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / 'bad.yaml'
        bad.write_text('piece: {key: C major}\nmelody: {x: 1}\n')
        with pytest.raises(ValueError):
            P.load(bad)
        bad.write_text('harmony: {}\n')
        with pytest.raises(ValueError):
            P.load(bad)


def test_piece_runner_can_leave_out_bass_and_lines():
    cfg = P.merge(P.defaults(), dict(piece=dict(key='G mixolydian', length=64, seed=7),
                                     bass=dict(enabled=False), lines=dict(enabled=False)))
    ctx, r, doc, plan = P.build(cfg)
    assert {p['id'] for p in doc['parts']} == {'pad2', 'pad3'} | {e.ID for e in SQ.ENGINES}
