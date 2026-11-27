"""Tests for Seq Drift: slow-harmony gating, step-by-step arrival, bass pedal lag, registers and integration."""
import tempfile
from pathlib import Path

import pytest

import fixtures as F
import harmonic_engine as H
import parts as PT
import piece as P
import seqcore as S
import seqdrift as D
import sequencers as SQ
import thinning as T

BAR = H.bar_ticks('4/4')


def slow(bars=8, chords='Am F C G', level=3, repeats=1, **kw):
    r = F.progression(chords, key='A minor', bars_per_chord=bars, repeats=repeats)
    return r, PT.generate_parts(r), F.flat_plan(r, level)


def drift(r, doc, plan, **cfg):
    out = SQ.generate(doc, r, plan, {'drift': dict(dict(enabled=True, seed=3), **cfg)})
    return next(p for p in out if p['id'] == 'drift')


def tones(r, t):
    ev = S.Context(PT.generate_parts(r), r, F.flat_plan(r)).chord_at(t)
    return {(ev['root_pc'] + i) % 12 for i in ev['intervals']}


def test_registered_last_and_off_by_default():
    assert SQ.ENGINES[-1].ID == 'drift'
    assert SQ.defaults()['drift']['enabled'] is False
    r, doc, plan = slow()
    assert 'drift' not in [p['id'] for p in SQ.generate(doc, r, plan, {})]
    assert drift(r, doc, plan)['kind'] == 'seq'


def test_needs_the_chords():
    r, doc, plan = slow()
    for bad in (dict(follow='static'), dict(harmonic='transposed'), dict(harmonic='independent')):
        with pytest.raises(ValueError):
            drift(r, doc, plan, **bad)


@pytest.mark.parametrize('key,value', [('arrival', 0.0), ('lag', 1.5), ('density', 0.0), ('flip', 0.9), ('move', 0.9),
                                       ('min_chord_bars', -1)])
def test_settings_are_checked(key, value):
    r, doc, plan = slow()
    with pytest.raises(ValueError):
        drift(r, doc, plan, **{key: value})


def test_deterministic_and_seed_changes_it():
    r, doc, plan = slow()
    a, b, c = drift(r, doc, plan), drift(r, doc, plan), drift(r, doc, plan, seed=4)
    assert a['notes'] == b['notes'] and a['notes'] != c['notes']


def test_rests_over_fast_chords_and_sounds_over_slow_ones():
    r, doc, plan = slow(bars=1, chords='Am F C G', repeats=4)
    assert drift(r, doc, plan, min_chord_bars=2)['notes'] == []                  # one-bar chords are too fast
    assert drift(r, doc, plan, min_chord_bars=0)['notes']
    r, doc, plan = slow(bars=4)
    p = drift(r, doc, plan, min_chord_bars=4)
    assert p['notes'] and p['drift']['loops'] == 16


def test_sounds_only_inside_slow_chords_and_keeps_its_place():
    r = F.progression(['Am', 'F', 'C', 'G', 'Am', 'Dm'], key='A minor')
    t = 0
    for ev, bars in zip(r['events'], [4, 1, 1, 1, 1, 4]):
        ev['start_tick'], ev['duration_ticks'] = t, bars * BAR
        t += bars * BAR
    r['sections'][0].update(bars=12, phrases=[4, 4, 4])
    doc = PT.generate_parts(r)
    p = drift(r, doc, F.flat_plan(r), min_chord_bars=4)
    assert p['notes']
    for n in p['notes']:
        assert n['start'] < 4 * BAR or n['start'] >= 8 * BAR                     # nothing over the one-bar chords
    assert p['drift']['chords_drifted'] == 1                                     # the second slow chord drifts in from the first


def test_notes_stay_in_each_lanes_register():
    r, doc, plan = slow()
    p = drift(r, doc, plan)
    cfg = p['settings']
    assert all(cfg['low'] <= n['pitch'] <= cfg['high'] for n in p['notes'])
    assert all(isinstance(n['step'], tuple) and 0 <= n['step'][0] < 4 for n in p['notes'])
    for lane, (lo, hi, _) in zip(range(4), [L['reg'] for L in D.LANES]):
        pitches = [n['pitch'] for n in p['notes'] if n['step'][0] == lane]
        assert pitches and all(lo <= x <= hi for x in pitches)


def test_first_loop_is_settled_on_its_chord():
    r, doc, plan = slow()
    p = drift(r, doc, plan)
    first = [n for n in p['notes'] if n['start'] < BAR]
    assert first and {n['pitch'] % 12 for n in first} <= tones(r, 0)


def test_chords_arrive_step_by_step_then_settle():
    """Over a new chord the first loop still plays old-chord notes; by the last loop almost everything has crossed."""
    r, doc, plan = slow(bars=8)
    p = drift(r, doc, plan, arrival=0.5)
    tl = p['drift']['timeline']
    assert p['drift']['chords_drifted'] == 3
    for k in (1, 2, 3):                                                          # each later chord
        a, b = k * 8 * BAR, (k + 1) * 8 * BAR
        new = tones(r, a)
        first = [n['pitch'] % 12 for n in p['notes'] if a <= n['start'] < a + BAR]
        last = [n['pitch'] % 12 for n in p['notes'] if b - BAR <= n['start'] < b]
        assert any(pc not in new for pc in first), 'the old chord is still heard at the start'
        assert sum(pc in new for pc in last) / len(last) >= 0.9, 'the new chord has arrived by the end'
        arrived = [x['arrived'] for x in tl if x['bar'] // 8 == k]
        assert arrived[-1] >= 0.95 and arrived[0] < 1.0


def test_arrival_rate_scales_with_chord_length():
    """The same arrival setting spreads over more loops for a longer chord, and always finishes inside the chord."""
    def bars_to_settle(bars):
        r, doc, plan = slow(bars=bars, chords='Am F C')
        tl = drift(r, doc, plan, arrival=0.6, drift=False, flip=0, move=0)['drift']['timeline']
        return next((x['bar'] - bars for x in tl if bars <= x['bar'] < 2 * bars and x['arrived'] >= 0.95), None)
    short, long_ = bars_to_settle(4), bars_to_settle(12)
    assert short is not None and long_ is not None
    assert short < long_ and long_ <= 12 * 0.9


def test_bass_holds_the_old_root_until_the_upper_steps_have_arrived():
    r, doc, plan = slow(bars=8)
    p = drift(r, doc, plan, lag=0.9)
    tl = p['drift']['timeline']
    assert any(not x['bass_released'] and x['progress'] < 0.9 for x in tl)
    bass = [n for n in p['notes'] if n['step'][0] == 0]
    for k in (1, 2, 3):
        a = k * 8 * BAR
        release = next(x['bar'] for x in tl if x['bar'] >= k * 8 and x['bass_released'])
        old_root, new_root = tones(r, a - 1), tones(r, a)
        early = [n['pitch'] % 12 for n in bass if a <= n['start'] < release * BAR]
        assert all(pc in old_root for pc in early), 'before release the bass is still on the old chord'
        assert release > k * 8                                                   # and release does come after the change


def test_zero_lag_releases_the_bass_at_once():
    r, doc, plan = slow(bars=8)
    tl = drift(r, doc, plan, lag=0.0)['drift']['timeline']
    assert all(x['bass_released'] for x in tl)


def test_density_level_raises_note_count():
    counts = []
    for level in (1, 3, 5):
        r, doc, plan = slow(level=level)
        counts.append(len(drift(r, doc, plan)['notes']))
    assert counts[0] < counts[1] < counts[2]


def test_density_filter_thins_whole_steps():
    r, doc, plan = slow()
    p = drift(r, doc, plan)
    thinned, rep = T.thin_seq(p, 50)
    assert 0 < len(thinned['notes']) < len(p['notes']) and rep['steps_kept'] < rep['steps']
    kept = {repr(n['step']) for n in thinned['notes']}
    assert all(repr(n['step']) in kept for n in p['notes'] if repr(n['step']) in kept)


def test_pace_drift_makes_stillness_and_movement():
    r, doc, plan = slow(bars=8, repeats=2)
    paces = [x['pace'] for x in drift(r, doc, plan)['drift']['timeline']]
    assert max(paces) - min(paces) > 0.3
    still = [x['pace'] for x in drift(r, doc, plan, drift=False)['drift']['timeline']]
    assert set(still) == {1.0}


def test_other_meters_loop_one_bar():
    for meter, bars in (('3/4', 6), ('6/8', 6), ('2/4', 8)):
        r = F.progression('Am F C G', key='A minor', meter=meter, bars_per_chord=bars)
        doc = PT.generate_parts(r)
        p = drift(r, doc, F.flat_plan(r), min_chord_bars=0)
        steps_per_bar = H.bar_ticks(meter) // S.GRIDS['16']
        assert p['notes'] and max(n['step'][1] for n in p['notes']) < steps_per_bar


def test_piece_runner_writes_drift_midi():
    """A whole piece with slow chords and Drift switched on writes its part, files and resolved script."""
    cfg = P.merge(P.defaults(), dict(piece=dict(title='Drift test', key='A minor', length=64, seed=11),
                                     harmony=dict(rates=[0.25]), sequencers=dict(drift=dict(enabled=True)),
                                     output=dict(score=False)))
    with tempfile.TemporaryDirectory() as d:
        out = P.render(cfg, d, 'drift_test', score=False, midi=True)
        ids = [p['id'] for p in out['doc']['parts']]
        assert 'drift' in ids
        part = next(p for p in out['doc']['parts'] if p['id'] == 'drift')
        assert part['notes'] and part['drift']['chords_drifted'] >= 1
        names = [f.name for f in out['files']]
        assert any('Seq_Drift' in n and n.endswith('.mid') for n in names)
        assert 'drift:' in (Path(d) / 'drift_test_resolved.yaml').read_text()
