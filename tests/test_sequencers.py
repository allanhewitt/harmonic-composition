"""Tests for the sequencer framework (seqcore) and the Moog 960 engine."""
import pytest

import composition_generator as C
import fixtures as F
import harmonic_engine as H
import orchestration as O
import parts as PT
import piece as P
import seq960
import seqcore as S
import sequencers as SQ


def fixture(chords='C Am F G', key='C major', level=5, repeats=2, **kw):
    r = F.progression(chords, key=key, repeats=repeats, **kw)
    doc = PT.generate_parts(r)
    return r, doc, F.flat_plan(r, level)


def run(r, doc, plan, **cfg):
    return SQ.generate(doc, r, plan, {'m960': dict(seed=3, **cfg)})[0]


def chord_at(r, t):
    return S.Context(PT.generate_parts(r), r, F.flat_plan(r)).chord_at(t)


def mono(notes, slides=()):
    ns = sorted(notes, key=lambda n: n['start'])
    for i, (a, b) in enumerate(zip(ns, ns[1:])):
        if a['start'] + a['duration'] > b['start'] and i not in slides:
            return False
    return True


# ------------------------------------------------------------------ harmonic modes
def test_adapted_chord_space_uses_chord_tones():
    r, doc, plan = fixture()
    p = run(r, doc, plan, harmonic='adapted', value_space='chord')
    for n in p['notes']:
        ev = chord_at(r, n['start'])
        assert n['pitch'] % 12 in {(ev['root_pc'] + i) % 12 for i in ev['intervals']}


def test_adapted_scale_space_stays_in_scale_and_lands_on_chord_tones():
    r, doc, plan = fixture()
    p = run(r, doc, plan, harmonic='adapted', value_space='scale')
    for n in p['notes']:
        ev = chord_at(r, n['start'])
        assert n['pitch'] % 12 in set(H.scale_pcs(ev['scale']))
        if n['start'] == ev['start_tick']:
            assert n['pitch'] % 12 in {(ev['root_pc'] + i) % 12 for i in ev['intervals']}


def test_transposed_keeps_shape_over_minor_chords():
    r, doc, plan = fixture('C Am')
    p = run(r, doc, plan, harmonic='transposed', value_space='chord')
    bt = H.bar_ticks('4/4')
    for n in p['notes']:
        ev = chord_at(r, n['start'])
        assert (n['pitch'] - ev['root_pc']) % 12 in {0, 4, 7}        # major-triad shape, even on A minor
    assert any((n['pitch'] - 9) % 12 == 4 for n in p['notes'] if bt <= n['start'] < 2 * bt)   # C# over Am


def test_independent_ignores_chords():
    r, doc, plan = fixture('C Am F G', repeats=1, level=5)
    p = run(r, doc, plan, harmonic='independent', value_space='scale', mutation=0.0, reset='never')
    for n in p['notes']:
        assert n['pitch'] % 12 in set(H.scale_pcs('C major'))
    r2, doc2, plan2 = fixture('F Bb Eb Ab', repeats=1, level=5)
    q = run(r2, doc2, plan2, harmonic='independent', value_space='scale', mutation=0.0, reset='never')
    assert [n['pitch'] for n in p['notes']] == [n['pitch'] for n in q['notes']]


@pytest.mark.parametrize('mode', S.MODES)
@pytest.mark.parametrize('space', S.SPACES)
def test_register_and_monophony(mode, space):
    r, doc, plan = fixture()
    p = run(r, doc, plan, harmonic=mode, value_space=space, low=62, high=80)
    assert all(62 <= n['pitch'] <= 80 for n in p['notes'])
    assert mono(p['notes'], set(p['slides']))


# ------------------------------------------------------------------ 960 mechanism
def test_density_adds_steps():
    counts = []
    for level in range(1, 6):
        r, doc, plan = fixture(level=level)
        counts.append(len(run(r, doc, plan, skip_rate=0)['notes']))
    assert counts == sorted(counts) and counts[0] < counts[-1]


def test_lower_density_is_a_subset_of_higher():
    r, doc, plan = fixture(level=2)
    low = {(n['start'], n['pitch']) for n in run(r, doc, plan)['notes']}
    r, doc, plan = fixture(level=5)
    high = {(n['start'], n['pitch']) for n in run(r, doc, plan)['notes']}
    assert low <= high


def test_steps_on_grid_and_skip_takes_no_time():
    r, doc, plan = fixture(level=5)
    p = run(r, doc, plan, skip_rate=0.0, time_rate=0.0, rows=dict(a='pitch', b='gate', c='velocity'))
    grid = S.GRIDS['16']
    starts = [n['start'] for n in p['notes']]
    assert all(s % grid == 0 for s in starts)
    assert starts == list(range(0, doc['end_tick'], grid))          # every sixteenth plays at full density
    q = run(r, doc, plan, skip_rate=0.5, time_rate=0.0, rows=dict(a='pitch', b='gate', c='velocity'))
    assert [n['start'] for n in q['notes']] == starts                # skipped steps take no time
    pat = q['patterns'][0]
    assert 'skip' in pat['modes']


def test_rest_and_time_rows():
    r, doc, plan = fixture(level=5)
    p = run(r, doc, plan, skip_rate=0.0, time_rate=0.6)
    pat = p['patterns'][0]
    assert 2 in pat['values']['time']
    gaps = {b['start'] - a['start'] for a, b in zip(p['notes'], p['notes'][1:])}
    assert S.GRIDS['16'] * 2 in gaps


def test_stop_halts_until_section_restart():
    r, doc, plan = fixture('C F G C', repeats=4, level=5, phrase=4)
    p = run(r, doc, plan, stop_rate=1.0, skip_rate=0.0, time_rate=0.0, reset='section')
    L = 8
    stop_at = p['patterns'][0]['modes'].index('stop')
    assert len(p['notes']) == stop_at                                # one section: plays up to the Stop, then halts
    q = run(r, doc, plan, stop_rate=1.0, skip_rate=0.0, time_rate=0.0, reset='phrase')
    assert len(q['notes']) == stop_at * len(r['sections'][0]['phrases'])
    assert stop_at < L


def test_reset_section_restarts_pattern_and_related_repeats():
    r = C.compose(dict(key='A minor', seed='5', tempo='112', length='64'), harmony={'rates': ['1/4', '1/2']})[1]
    doc = O.arrange_pads(PT.generate_parts(r), r, {})
    plan = doc['orchestration']['plan']
    p = SQ.generate(doc, r, plan, {'m960': dict(mutation=0.0, skip_rate=0.0, seed=4)})[0]
    bt = H.bar_ticks(doc['meter'])
    firsts = {}
    for sec in r['sections']:
        t = sec['start'] * bt
        first = next((n for n in p['notes'] if n['start'] == t), None)
        if first:
            ev = chord_at(r, t)
            assert first['pitch'] % 12 == ev['root_pc']             # step 1 is the root after every restart
        ph = next(x for x in p['patterns'] if x['start_bar'] == sec['start'] + 1)
        firsts.setdefault(sec['identity'], ph['values']['pitch'])
        assert firsts[sec['identity']] == ph['values']['pitch']


def test_errors_and_reproducibility():
    r, doc, plan = fixture()
    assert run(r, doc, plan) == run(r, doc, plan)
    for bad in (dict(harmonic='free'), dict(value_space='modal'), dict(grid='12'), dict(length=1),
                dict(rows=dict(a='gate', b='gate', c='time')), dict(low=60, high=66), dict(profile='organ')):
        with pytest.raises(ValueError):
            run(r, doc, plan, **bad)
    with pytest.raises(ValueError):
        SQ.generate(doc, r, plan, {'tr808': {}})


def test_poly_profile_avoids_same_pitch_overlap():
    r, doc, plan = fixture()
    p = run(r, doc, plan, profile='poly_synth', rows=dict(a='pitch', b='time', c='velocity'))
    by_pitch = {}
    for n in sorted(p['notes'], key=lambda n: n['start']):
        assert by_pitch.get(n['pitch'], -1) <= n['start']
        by_pitch[n['pitch']] = n['start'] + n['duration']


# ------------------------------------------------------------------ in a piece
def test_piece_includes_sequencer_by_default_and_can_switch_off():
    cfg = P.merge(P.defaults(), dict(piece=dict(key='D dorian', length=64, seed=3)))
    ctx, r, doc, plan = P.build(cfg)
    ids = [p['id'] for p in doc['parts']]
    assert ids[0] == 'm960'
    seq = doc['parts'][0]
    assert seq['channel'] not in (9,) and seq['notes']
    cfg = P.merge(cfg, dict(sequencers=dict(m960=dict(enabled=False))))
    ctx, r, doc, plan = P.build(cfg)
    assert 'm960' not in [p['id'] for p in doc['parts']]


def test_channels_skip_drums():
    assert 9 not in S.CHANNELS and len(set(S.CHANNELS)) == 9
