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


def test_default_is_one_fixed_pattern_fitted_to_each_chord():
    r = C.compose(dict(key='A minor', seed='5', tempo='112', length='64'), harmony={'rates': ['1/4', '1/2']})[1]
    doc = PT.generate_parts(r)
    plan = [dict(st, level=5) for st in O.plan_levels(r, 5, dict(O.DEFAULTS))]
    p = SQ.generate(doc, r, plan, {})[0]
    pats = {tuple(x['values']['pitch']) for x in p['patterns']}
    assert len(pats) == 1                                           # the same pattern throughout
    bt = H.bar_ticks(doc['meter'])
    grid = S.GRIDS[str(seq960.DEFAULTS['grid'])]
    L = seq960.DEFAULTS['length']
    assert bt % (grid * L) == 0                                     # the loop lines up with the bar
    for n in p['notes']:                                            # every note is a tone of the chord it sounds over
        ev = chord_at(r, n['start'])
        assert n['pitch'] % 12 in {(ev['root_pc'] + i) % 12 for i in ev['intervals']}


def test_c_pattern_over_a_minor_uses_c_natural():
    r, doc, plan = fixture('C Am', repeats=1)
    p = run(r, doc, plan)
    bt = H.bar_ticks('4/4')
    bar2 = {n['pitch'] % 12 for n in p['notes'] if bt <= n['start'] < 2 * bt}
    assert 1 not in bar2 and bar2 <= {9, 0, 4}


# ------------------------------------------------------------------ the eight further engines and sequencer thinning
import seqengines as E
import thinning as T

NEW = [e.ID for e in E.ENGINES]
ALL = [e.ID for e in SQ.ENGINES]
SIGNATURE = dict(euclid=('cycle', [8, 12, 16]), poly=('loops', ['3-5-7', '7-9-11']), tb303=('slide', [0.0, 1.0]),
                 turing=('change', [0.0, 1.0]), metro=('ratchet', [0.0, 1.0]), marbles=('spread', [0.0, 1.0]),
                 rene=('path', ['cartesian', 'snake', 'diagonal']), nodal=('branching', [0.0, 1.0]))


def part_of(eid, level=5, **cfg):
    r, doc, plan = fixture(level=level)
    return next(p for p in SQ.generate(doc, r, plan, {eid: dict(seed=3, **cfg)}) if p['id'] == eid), r


def test_registry_order_and_distinct_channels():
    assert ALL == ['m960', 'euclid', 'poly', 'tb303', 'turing', 'metro', 'marbles', 'rene', 'nodal']
    chans = [e.DEFAULTS['channel'] for e in SQ.ENGINES]
    assert len(set(chans)) == len(chans) and 9 not in chans


@pytest.mark.parametrize('eid', NEW)
def test_engine_register_kind_and_steps(eid):
    p, _ = part_of(eid)
    cfg = p['settings']
    assert p['kind'] == 'seq' and p['notes'] and p['step_priority']
    assert all(cfg['low'] <= n['pitch'] <= cfg['high'] for n in p['notes'])
    assert all('step' in n for n in p['notes'])


@pytest.mark.parametrize('eid', NEW)
def test_engine_is_deterministic(eid):
    a, _ = part_of(eid)
    b, _ = part_of(eid)
    assert a['notes'] == b['notes']


@pytest.mark.parametrize('eid', NEW)
def test_mono_profile_never_overlaps(eid):
    p, _ = part_of(eid, profile='mono_synth')
    assert mono(p['notes'], p['slides'])


@pytest.mark.parametrize('eid', NEW)
def test_poly_profile_never_repeats_a_sounding_pitch(eid):
    p, _ = part_of(eid, profile='poly_synth')
    by = {}
    for n in sorted(p['notes'], key=lambda n: n['start']):
        prev = by.get(n['pitch'])
        assert prev is None or prev['start'] + prev['duration'] <= n['start']
        by[n['pitch']] = n


@pytest.mark.parametrize('eid', NEW)
def test_static_stays_in_the_home_key(eid):
    r, doc, plan = fixture(chords='C Ab Bb Eb', key='C major')
    p = next(x for x in SQ.generate(doc, r, plan, {eid: dict(seed=3, follow='static')}) if x['id'] == eid)
    assert {n['pitch'] % 12 for n in p['notes']} <= {0, 2, 4, 5, 7, 9, 11}


@pytest.mark.parametrize('eid', NEW)
def test_follow_uses_the_chord_or_scale(eid):
    p, r = part_of(eid)
    for n in p['notes']:
        ev = chord_at(r, n['start'])
        if n['start'] == ev['start_tick'] and p['settings']['value_space'] == 'chord':
            assert (n['pitch'] - ev['root_pc']) % 12 in {i % 12 for i in S.chord_ladder(ev)}


@pytest.mark.parametrize('eid', NEW)
def test_density_levels_reduce_notes(eid):
    counts = [len(part_of(eid, level=lvl)[0]['notes']) for lvl in (1, 3, 5)]
    assert counts[0] < counts[2] and counts[0] <= counts[1] <= counts[2]


@pytest.mark.parametrize('eid', NEW)
def test_signature_controls_accepted_and_bad_values_rejected(eid):
    key, values = SIGNATURE[eid]
    for v in values:
        assert part_of(eid, **{key: v})[0]['notes']
    with pytest.raises(ValueError):
        part_of(eid, **{key: 'nonsense' if isinstance(values[0], str) else 5})


def test_euclidean_pulses_are_even():
    hits = E.Euclidean.pattern(5, 16, 0)
    gaps = [j - i for i, j in zip([k for k, h in enumerate(hits) if h], [k for k, h in enumerate(hits) if h][1:])]
    assert sum(hits) == 5 and set(gaps) <= {3, 4}


def test_turing_keeps_changing_only_with_change():
    still, _ = part_of('turing', change=0.0)
    assert still['changes'] == 0
    moving, _ = part_of('turing', change=1.0)
    assert moving['changes'] > 0


def test_tb303_slides_follow_slide_amount():
    assert part_of('tb303', slide=0.0)[0]['stats']['slides'] == 0
    assert part_of('tb303', slide=1.0)[0]['stats']['slides'] > 0


def test_metropolix_ratchets_follow_amount():
    none, _ = part_of('metro', ratchet=0.0)
    assert not any(s['gate'].startswith('ratchet') for s in none['stages'])


def test_disabled_engines_are_left_out():
    r, doc, plan = fixture()
    parts = SQ.generate(doc, r, plan, {e: dict(enabled=False) for e in ALL})
    assert parts == []


def test_sequencer_thinning_silences_the_same_steps_throughout():
    r, doc, plan = fixture(repeats=4)
    parts = SQ.generate(doc, r, plan, {})
    out = T.apply(dict(doc, parts=parts), r, dict(keep=50))
    for full, thin in zip(parts, out['parts']):
        keys_full = {repr(n['step']) for n in full['notes']}
        keys_thin = {repr(n['step']) for n in thin['notes']}
        assert keys_thin < keys_full or len(keys_full) == 1
        assert all(repr(n['step']) in keys_thin for n in full['notes'] if n in thin['notes'])
        # a kept step sounds every time its pattern comes round
        assert all(n in thin['notes'] for n in full['notes'] if repr(n['step']) in keys_thin)


def test_sequencer_thinning_per_part_override_and_full_keep():
    r, doc, plan = fixture()
    parts = SQ.generate(doc, r, plan, {})
    out = T.apply(dict(doc, parts=parts), r, dict(keep=100, parts={'tb303': 25}))
    rep = out['thinning']['report']
    assert rep['m960']['kept'] == 1.0 and rep['tb303']['kept'] < 0.5
