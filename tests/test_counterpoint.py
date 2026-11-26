"""Tests for the rhythmic counterpoint family (rhythm first, then pitch)."""
import pytest

import counterpoint as CP
import harmonic_engine as H
import piece as P
import seqcore as S

V = CP.VOICE_KEYS


@pytest.fixture(scope='module')
def built():
    cfg = P.defaults()
    cfg['piece'].update(length=128, seed=3, key='A minor')
    return P.build(cfg)


def gen(built, **kw):
    ctx, r, doc, plan = built
    return CP.generate(doc, r, plan, dict(dict(enabled=True), **kw))


def sounding_above(parts, v, t):
    return [q for u in range(v) for q in parts[u]['notes'] if q['start'] <= t < q['start'] + q['duration']]


def test_off_by_default(built):
    ctx, r, doc, plan = built
    assert CP.generate(doc, r, plan, {}) == []


def test_four_monophonic_voices_in_register(built):
    parts = gen(built)
    assert [p['id'] for p in parts] == ['rv1', 'rv2', 'rv3', 'rv4'] and all(p['kind'] == 'voice' for p in parts)
    for p in parts:
        s = p['settings']
        ns = sorted(p['notes'], key=lambda n: n['start'])
        assert ns and all(s['low'] <= n['pitch'] <= s['high'] for n in ns)
        assert all(a['start'] + a['duration'] <= b['start'] for a, b in zip(ns, ns[1:]))
        assert all(n['start'] % CP.GRIDS['8'] == 0 for n in ns)


def test_deterministic(built):
    assert gen(built) == gen(built)
    assert gen(built, seed=2) != gen(built)


def test_density_and_participation_near_targets(built):
    for p in gen(built, evolution='steady'):
        s = p['settings']
        assert abs(p['stats']['density'] - s['density']) <= 12
        assert abs(p['stats']['participation'] - s['participation']) <= 15


def test_coordinated_voices_rise_and_fall_out_of_step(built):
    parts = gen(built, interdependence=100)
    curves = [[d for _, d, _ in p['targets']] for p in parts]
    assert all(max(c) - min(c) >= 10 for c in curves)
    lo_points = [c.index(min(c)) for c in curves]
    assert len(set(lo_points)) >= 3                       # the voices are quietest at different times


def test_steady_keeps_targets(built):
    parts = gen(built, evolution='steady')
    assert all(len({d for _, d, _ in p['targets']}) == 1 for p in parts)


def test_returning_sections_reuse_rhythm(built):
    ctx, r, doc, plan = built
    parts = gen(built, evolution='steady', repetition=100)
    bar = H.bar_ticks(doc['meter'])
    by = {}
    for sec in r['sections']:
        a, b = sec['start'] * bar, (sec['start'] + sec['bars']) * bar
        rel = tuple(n['start'] - a for n in parts[0]['notes'] if a <= n['start'] < b)
        by.setdefault(sec['identity'], []).append(rel)
    repeats = [v for v in by.values() if len(v) > 1]
    assert repeats and all(len(set(v)) == 1 for v in repeats)


def test_no_crossing_below_the_voice_above(built):
    for eng in ('markov', 'step'):
        parts = gen(built, **{k: dict(engine=eng) for k in V})
        for v in range(1, 4):
            for n in parts[v]['notes']:
                assert all(n['pitch'] < q['pitch'] for q in sounding_above(parts, v, n['start']))


def test_adherence_raises_chord_tones(built):
    ctx, r, doc, plan = built
    c = S.Context(doc, r, plan)

    def share(parts):
        hits = total = 0
        for p in parts:
            for n in p['notes']:
                ev = c.chord_at(n['start'])
                hits += (n['pitch'] - ev['root_pc']) % 12 in {i % 12 for i in S.chord_ladder(ev)}
                total += 1
        return hits / total
    assert share(gen(built, **{k: dict(adherence=1.0) for k in V})) > share(gen(built, **{k: dict(adherence=0.0) for k in V})) + 0.1


def test_markov_lines_mostly_move_by_step(built):
    for p in gen(built):
        ns = p['notes']
        steps = sum(1 for a, b in zip(ns, ns[1:]) if 1 <= abs(a['pitch'] - b['pitch']) <= 2)
        assert steps / (len(ns) - 1) > 0.4


def test_piece_ends_on_the_tonic(built):
    ctx, r, doc, plan = built
    tonic = H.parse_key(r['keys'][-1])[0] % 12
    ends = [p['notes'][-1]['pitch'] % 12 for p in gen(built)]
    assert sum(e == tonic for e in ends) >= 2


def test_static_stays_in_the_home_key(built):
    ctx, r, doc, plan = built
    home = set(H.scale_pcs(r['keys'][0]))
    for eng in ('markov', 'step'):
        for p in gen(built, follow='static', **{k: dict(engine=eng) for k in V}):
            assert {n['pitch'] % 12 for n in p['notes']} <= home


def test_step_engine_advances_only_on_notes(built):
    parts = gen(built, follow='static', **{k: dict(engine='step', pattern=[0, 1, 2]) for k in V})
    ctx, r, doc, plan = built
    tonic = H.parse_key(r['keys'][0])[0] % 12
    first = parts[0]['notes'][0]['pitch']
    assert first % 12 == tonic                             # pattern value 0 on the first note, whatever the rests


def test_custom_table_and_presets(built):
    flat = [[1] * 9 for _ in range(9)]
    assert gen(built, v1=dict(table=flat))[0]['notes']
    for t in CP.TABLES:
        assert all(abs(sum(row) - 1) < 1e-3 for row in CP.TABLES[t])
        assert gen(built, v1=dict(table=t))[0]['notes']


@pytest.mark.parametrize('bad', [dict(follow='x'), dict(grid='3'), dict(grid='16', shortest='8'), dict(evolution='x'),
                                 dict(conventionality=120), dict(v1=dict(density=0)), dict(v2=dict(engine='x')),
                                 dict(v3=dict(table='nope')), dict(v3=dict(table=[[1, 2]])), dict(v4=dict(adherence=2)),
                                 dict(v1=dict(low=60, high=65)), dict(v2=dict(channel=16))])
def test_bad_settings_rejected(built, bad):
    with pytest.raises(ValueError):
        gen(built, **bad)


def test_infeasible_targets_are_reported_not_hidden(built):
    parts = gen(built, v3=dict(density=60, density_change=0, participation=10, participation_change=0), shortest='8')
    assert parts[2]['warnings'] and parts[2]['stats']['infeasible_phrases'] == len(parts[2]['warnings'])


def test_piece_with_only_voices_and_bass_renders(tmp_path):
    cfg = P.load(__file__.replace('tests/test_counterpoint.py', 'pieces/examples/four_voices_and_bass.yaml'))
    cfg['piece']['length'] = 48
    ctx, r, doc, plan = P.build(cfg)
    assert [p['id'] for p in doc['parts']] == ['rv1', 'rv2', 'rv3', 'rv4', 'bass']
    out = P.render(cfg, tmp_path, 'fv', score=False, midi=True)
    assert any(str(f).endswith('_all_parts.mid') for f in out['files'])


def test_density_filter_leaves_the_voices_alone(built):
    import thinning as T
    ctx, r, doc, plan = built
    parts = gen(built)
    out = T.apply(dict(doc, parts=parts), r, dict(keep=30))
    assert out['parts'] == parts
