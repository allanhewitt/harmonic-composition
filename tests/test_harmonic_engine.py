"""Regression tests for harmonic_engine. Run with: python -m pytest -q"""
import collections
import io

import pytest

import harmonic_engine as H

SONG = 'intro 8\nverse 8\nchorus 8\nverse 12\nchorus 8\nbridge 8\nchorus 8\noutro 4'
FORMS = {
    'song': SONG,
    'aaba': 'A 8\nA 8\nB 8\nA 8',
    'arch': 'A 8\nB 8\nC 8\nB 8\nA 8',
    'through': 'S1 8\nS2 8\nS3 8\nS4 8',
    'evolving': 'A 8\nA_v1 8\nA_v2 8',
    'loop': 'A 16',
}


def cores(result, i=None):
    return [(e['token'], e['duration_ticks']) for e in result['events'] if i is None or e['section_index'] == i]


def test_deterministic():
    a = H.generate(SONG, dict(seed=7))
    b = H.generate(SONG, dict(seed=7))
    assert a['events'] == b['events']
    assert H.generate(SONG, dict(seed=7), variant=1)['events'] != a['events']


@pytest.mark.parametrize('form', FORMS)
def test_functions_are_form_derived(form):
    r = H.generate(FORMS[form], dict(seed=3))
    rec = [f['recurrence'] for f in r['functions']]
    if form == 'through':
        assert rec == ['statement'] * 4
    if form == 'evolving':
        assert rec == ['statement', 'variant', 'variant']
    if form == 'arch':
        assert rec == ['statement', 'statement', 'statement', 'return', 'return']


@pytest.mark.parametrize('form', FORMS)
def test_final_tonic_and_home(form):
    for seed in range(25):
        r = H.generate(FORMS[form], dict(seed=seed, tonal_departure=0.8))
        if form == 'loop':
            continue
        assert r['diagnostics']['ends_on_home_tonic'], (form, seed, r['diagnostics']['final_chord'])
        assert r['keys'][0] == r['keys'][-1] == 'C major'


def test_returns_repeat_exactly_apart_from_reaimed_endings():
    for seed in range(40):
        d = H.generate(SONG, dict(seed=seed))['diagnostics']
        assert d['returns_identical_except_ending'] == d['exact_returns']


def test_colour_never_changes_core_chords():
    for seed in range(20):
        plain = H.generate(SONG, dict(seed=seed, colour=0.0, dominant_sevenths=0.0))
        rich = H.generate(SONG, dict(seed=seed, colour=1.0, dominant_sevenths=1.0))
        assert cores(plain) == cores(rich)
        # at colour 0 the only additions are measured identities (generated dominants and suspensions), never optional colour
        assert all(e['chord_symbol'] == e['core_symbol'] or (e.get('colour') or {}).get('kind') == 'function'
                   for e in plain['events'])
        assert not any((e.get('colour') or {}).get('kind') == 'optional' for e in plain['events'])


def colour_stats(dial, seeds=60):
    pairs = collections.Counter()
    share = []
    for seed in range(seeds):
        d = H.generate(SONG, dict(seed=seed, colour=dial, dominant_sevenths=0.0))['diagnostics']
        share.append(d['colour_share'])
    return sum(share) / len(share)


def test_colour_dial_is_monotonic():
    shares = [colour_stats(x, 30) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert shares[0] == 0
    assert all(b >= a for a, b in zip(shares, shares[1:]))


def test_colour_persists_at_beatles_setting():
    after_colour, after_plain = [], []
    for seed in range(120):
        d = H.generate('A 64', dict(seed=seed, colour=0.5, dominant_sevenths=0.0, rates=[1]))['diagnostics']
        if d['p_colour_after_colour'] is not None:
            after_colour.append(d['p_colour_after_colour'])
        after_plain.append(d['p_colour_after_plain'])
    assert sum(after_colour) / len(after_colour) > 2 * sum(after_plain) / len(after_plain)


def test_valid_colours_only():
    for seed in range(20):
        r = H.generate(SONG, dict(seed=seed, colour=1.0))
        for e in r['events']:
            if e.get('colour') and e['colour']['kind'] == 'optional':
                assert H.valid_colour(e['token'], e['colour']['suffix'], e['local_key'])


def test_locks():
    a = H.generate(SONG, dict(seed=5))
    b = H.generate(SONG, dict(seed=5), variant=3, previous=a, locks={2: 'all', 5: 'core'})
    assert [e for e in a['events'] if e['section_index'] == 2] == [e for e in b['events'] if e['section_index'] == 2]
    assert cores(a, 5) == cores(b, 5)
    with pytest.raises(ValueError):
        H.generate(SONG.replace('chorus 8', 'chorus 4', 1), dict(seed=5), previous=a, locks={2: 'all'})


def test_loop_leads_back():
    for seed in range(15):
        r = H.generate('A 8', dict(seed=seed, final_destination='loop'))
        first, last = r['events'][0], r['events'][-1]
        assert (last['root_pc'] - first['root_pc']) % 12 == 7


@pytest.mark.parametrize('key', ['A minor', 'D dorian', 'G mixolydian', 'F# major'])
def test_modes(key):
    r = H.generate(SONG, dict(seed=1, key=key, mixture=1.0, colour=0.7))
    assert r['diagnostics']['ends_on_home_tonic']


def test_midi_and_csv():
    mido = pytest.importorskip('mido')
    r = H.generate(SONG, dict(seed=2, tempo=100))
    mid = mido.MidiFile(file=io.BytesIO(H.to_midi(r)))
    assert mid.type == 1 and len(mid.tracks) == 3
    assert abs(mid.length - 64 * 4 * 60 / 100) < 0.01
    names = [m.text for m in mid.tracks[0] if m.type == 'marker']
    assert names[0].startswith('intro 1') and names[4].startswith('chorus 2')
    rows = H.to_csv(r).splitlines()
    assert rows[0].startswith('section,occurrence,bar')


def test_meter_and_rates_validation():
    H.generate('A 6 3+3\nB 6 3+3', dict(seed=1, meter='3/4', rates=[1]))
    with pytest.raises(ValueError):
        H.generate('A 6 3+3', dict(seed=1, rates=[0.3]))
    r = H.generate('A 6 3+3', dict(seed=1, rates=[0.5]))       # odd bars fall back to 1-bar chords, with a note
    assert sum(e['duration_ticks'] for e in r['events']) == 6 * H.bar_ticks('4/4') and r['table_notes']
    with pytest.raises(ValueError):
        H.generate('A 8', dict(colour=2))


# ---- v0.2: measured tables and shaping dials

def opening_tonic_share(stability, seeds=150):
    hits = n = 0
    for seed in range(seeds):
        r = H.generate('A 8\nB 8\nA 8', dict(seed=seed, stability=stability, tonal_departure=0))
        first = [e for e in r['events'] if e['section_index'] == 1][0]
        hits += first['token'] == '1'
        n += 1
    return hits / n


def test_contrast_class_is_form_derived():
    f = H.derive_functions(H.parse_structure('A 8\nB 8\nA 8\nC 8\nA 8'))
    assert [x['cls'] for x in f] == ['opening_statement', 'statement', 'return', 'contrast_statement', 'return']


def test_stability_dial_is_monotonic_and_centred():
    low, mid, high = (opening_tonic_share(x) for x in (0.0, 0.5, 1.0))
    assert low < mid < high
    measured = H.mixed(H.DEFAULT_TABLES, 'opening', 'statement', H.resolve_settings({}))['1']
    assert abs(mid - measured) < 0.12


def test_cadence_strength_dial():
    def firm(dial):
        hits = 0
        for seed in range(150):
            r = H.generate('A 8\nB 8\nA 8', dict(seed=seed, cadence_strength=dial))
            hits += r['destinations'][1]['kind'] in ('authentic', 'plagal', 'tonic', 'mixture')
        return hits
    assert firm(0.0) < firm(0.5) < firm(1.0)


def test_activity_dial():
    def chords(dial):
        return sum(len(H.generate('A 16', dict(seed=s, harmonic_activity=dial, rates=[0.25, 0.5, 1, 2]))['events'])
                   for s in range(60))
    assert chords(0.0) < chords(0.5) < chords(1.0)


def test_tonal_departure_dial():
    song = 'A 8\nB 8\nA 8\nC 8\nA 8'
    def departures(dial):
        return sum(r != 'C major' for s in range(80) for r in H.generate(song, dict(seed=s, tonal_departure=dial))['keys'])
    assert departures(0.0) == 0
    assert departures(0.0) <= departures(0.5) < departures(1.0)


def test_no_chord_overrides_in_settings():
    for k in ('keys', 'openings', 'destinations'):
        assert k not in H.DEFAULT_SETTINGS
        with pytest.raises(ValueError):
            H.generate('A 8', {k: {}})


# ---- v0.3: corpus profiles

def test_profiles_blend_by_corpus_mix():
    t = H.DEFAULT_TABLES
    bb = H.mixed(t, 'opening', 'contrast_statement', H.resolve_settings({'corpus_mix': {'billboard': 1}}))
    be = H.mixed(t, 'opening', 'contrast_statement', H.resolve_settings({'corpus_mix': {'beatles': 1}}))
    half = H.mixed(t, 'opening', 'contrast_statement', H.resolve_settings({'corpus_mix': {'billboard': 1, 'beatles': 1}}))
    assert abs(half['1'] - (bb['1'] + be['1']) / 2) < 1e-9
    assert abs(sum(bb.values()) - 1) < 0.01


def test_missing_class_falls_back_and_is_recorded():
    r = H.generate('A 8\nB 8\nA 8', dict(seed=1, corpus_mix={'jazz': 1}))
    assert any('statement' in n for n in r['table_notes'])
    assert any('CC BY-NC-SA' in n for n in r['provenance']['licence_notes'])


def test_billboard_attribution_recorded():
    r = H.generate('A 8', dict(seed=1))
    assert any('Billboard' in n for n in r['provenance']['licence_notes'])


# ---- v0.4: chord-change models

def test_models_generate_and_score():
    r = H.generate('A 8\nA 8\nB 8\nA 8', dict(seed=4, corpus_mix={'jazz': 1}, model_generation=1.0, rates=[1, 2]))
    gen = sum(v.get('generated_slots', 0) or 0 for v in r['section_info'].values())
    assert gen > 0
    none = H.generate('A 8\nA 8\nB 8\nA 8', dict(seed=4, model_generation=0.0))
    assert all((v.get('generated_slots') or 0) == 0 for v in none['section_info'].values())


def test_jazz_mix_is_more_jazz_like():
    """Output under a jazz mix should be more probable under the jazz model than output under a pop mix."""
    parsed = H.transition_models(H.DEFAULT_TABLES)
    jazz_only = H.resolve_settings({'corpus_mix': {'jazz': 1}})
    def mean_logp(mix):
        total, n = 0.0, 0
        for seed in range(25):
            r = H.generate('A 8\nA 8\nB 8\nA 8', dict(seed=seed, corpus_mix=mix, rates=[1, 2]))
            for i in range(4):
                ev = [e for e in r['events'] if e['section_index'] == i]
                _, seq = H.model_sequence([e['token'] for e in ev], [e.get('model_quality') for e in ev], ev[0]['local_key'])
                hist = []
                for tok in seq:
                    if hist:
                        total += H.math.log(H.mixed_model_prob(jazz_only, parsed, hist, H.MODEL_INDEX[tok]))
                        n += 1
                    hist.append(tok)
        return total / n
    assert mean_logp({'jazz': 1}) > mean_logp({'billboard': 1}) + 0.2


def test_model_quality_survives_returns():
    r = H.generate('A 8\nB 8\nA 8', dict(seed=2, corpus_mix={'jazz': 1}, model_generation=1.0))
    a1 = [(e['token'], e['chord_symbol']) for e in r['events'] if e['section_index'] == 0]
    a2 = [(e['token'], e['chord_symbol']) for e in r['events'] if e['section_index'] == 2]
    assert a1[:-2] == a2[:-2]


# ---- v0.5: phrase harmonic rhythm (Experiment 37)

def test_rhythm_uses_only_allowed_lengths():
    for rates, allowed in (([0.5, 1], {1, 2}), ([1, 2], {0.5, 1}), ([0.25, 0.5, 1, 2], {0.5, 1, 2, 4})):
        for seed in range(15):
            r = H.generate(SONG, dict(seed=seed, rates=rates))
            bt = H.bar_ticks('4/4')
            assert {e['duration_ticks'] / bt for e in r['events']} <= allowed


def test_rhythm_is_mixed_within_sections():
    # the default lengths (1 and 2 bars) must produce uneven phrases, not one rate per section
    mixed = 0
    for seed in range(30):
        r = H.generate(SONG, dict(seed=seed))
        for sec in r['sections']:
            lens = {e['duration_ticks'] for e in r['events'] if e['section_index'] == sec['index']}
            mixed += len(lens) > 1
    assert mixed > 30


def test_rhythm_diagnostic_and_slots_fill_phrases():
    r = H.generate('A 6 4+2\nB 5 3+2', dict(seed=2, rates=[0.5, 1, 2]))
    bt = H.bar_ticks('4/4')
    for sec in r['sections']:
        evs = [e for e in r['events'] if e['section_index'] == sec['index']]
        assert sum(e['duration_ticks'] for e in evs) == sec['bars'] * bt


def test_no_silent_merges_in_new_material():
    # a slot repeating its neighbour would erase the rhythm; holds are only chosen when hold > 0
    bad = total = 0
    for seed in range(30):
        r = H.generate(SONG, dict(seed=seed, hold=0.0))
        evs = [e for e in r['events'] if e['occurrence'] == 1]
        for a, b in zip(evs, evs[1:]):
            if a['section_index'] == b['section_index']:
                total += 1
                bad += a['token'] == b['token']
    assert bad / total < 0.02


def test_short_slow_section_has_two_chords():
    for seed in range(20):
        r = H.generate('intro 4\nverse 8', dict(seed=seed, rates=[0.5]))
        intro = {e['token'] for e in r['events'] if e['section_index'] == 0}
        assert len(intro) >= 2


# ---- v0.6: modes by degree conversion

MODES7 = ['major', 'minor', 'lydian', 'mixolydian', 'dorian', 'phrygian', 'locrian']


def test_all_seven_modes_generate_and_report_their_key():
    for mode in MODES7:
        for seed in range(4):
            r = H.generate(SONG, dict(seed=seed, key=f'D {mode}'))
            assert r['settings']['key'] == f'D {mode}'
            assert r['keys'][0] == f'D {mode}'


def test_modal_conversion_avoids_diminished_except_locrian_tonic():
    for mode in MODES7:
        for seed in range(10):
            r = H.generate(SONG, dict(seed=seed, key=f'C {mode}', tonal_departure=0))
            dims = [e for e in r['events'] if e['core_family'] == 'diminished']
            if mode == 'locrian':
                assert all(e['root_pc'] == 0 for e in dims)
            elif mode not in ('major', 'minor'):   # major and minor keep their measured behaviour
                assert not dims, (mode, seed)


def test_modes_use_their_signature_chords():
    sig = {'lydian': (2, 'major'), 'dorian': (5, 'major'), 'phrygian': (1, 'major'), 'mixolydian': (7, 'minor')}
    for mode, (pc, fam) in sig.items():
        hits = sum(any(e['root_pc'] == pc and e['core_family'] == fam for e in
                       H.generate(SONG, dict(seed=s, key=f'C {mode}', tonal_departure=0))['events']) for s in range(10))
        assert hits >= 8, mode


def test_no_raised_dominant_in_modal_keys():
    for mode in ('dorian', 'phrygian'):
        for seed in range(10):
            r = H.generate(SONG, dict(seed=seed, key=f'C {mode}', tonal_departure=0, raised_dominant=1.0))
            assert not any(e['root_pc'] == 7 and e['core_family'] == 'major' for e in r['events'])


def test_major_and_minor_unaffected_by_modal_emphasis():
    for key in ('C major', 'A minor'):
        a = H.generate(SONG, dict(seed=3, key=key, modal_emphasis=0.0))
        b = H.generate(SONG, dict(seed=3, key=key, modal_emphasis=1.0))
        assert cores(a) == cores(b)


def test_modal_returns_stay_identical():
    r = H.generate('A 8\nB 8\nA 8', dict(seed=4, key='E lydian', tonal_departure=0, adapt_return_endings=False))
    a = [e['token'] for e in r['events'] if e['section_index'] == 0]
    c = [e['token'] for e in r['events'] if e['section_index'] == 2]
    assert a[:-2] == c[:-2]


def test_gcl_context_document():
    ctx = dict(schema='gcl-context-0.1', global_parameters=dict(key='G mixolydian', tempo=96, meter='4/4', seed=7),
               sections=[dict(identity='A', bars=8, phrases=[4, 4]), dict(identity='B', bars=8, phrases=[4, 4]),
                         dict(identity='A', bars=8, phrases=[4, 4])])
    r = H.generate(ctx)
    assert r['settings']['key'] == 'G mixolydian' and r['settings']['tempo'] == 96 and r['settings']['seed'] == 7
    assert H.generate(ctx, dict(key='G major'))['settings']['key'] == 'G major'


def test_exports_in_every_mode():
    for mode in MODES7:
        r = H.generate('A 8\nB 8', dict(seed=1, key=f'F# {mode}'))
        assert H.to_midi(r)[:4] == b'MThd'
        assert H.to_csv(r).count('\n') > 4 and H.chart_text(r)


def test_length_range_helper_and_dotted_lengths():
    assert H.lengths_to_rates(1, 2) == ['1/2', '2/3', '1']
    bt = H.bar_ticks('4/4')
    seen = set()
    for seed in range(20):
        r = H.generate(SONG, dict(seed=seed, rates=H.lengths_to_rates(0.5, 4)))
        seen |= {e['duration_ticks'] / bt for e in r['events']}
    assert seen <= {0.5, 1, 1.5, 2, 3, 4} and {0.5, 1, 2} <= seen


# ---- v0.7: readable keys, interest, development, prepared returns

def test_scale_map_covers_piece_and_agrees_with_events():
    for seed in range(8):
        r = H.generate(SONG, dict(seed=seed, mixture=0.8, tonal_departure=0.7))
        total = sum(s['bars'] for s in r['sections'])
        covered = sorted((m['start_bar'], m['end_bar']) for m in r['scale_map'])
        assert covered[0][0] == 1 and covered[-1][1] == total
        assert all(a[1] + 1 == b[0] for a, b in zip(covered, covered[1:]))
        assert all('scale' in e for e in r['events'])
        for m in r['scale_map']:
            pcs = set(H.scale_pcs(m['key']))
            for e in r['events']:
                if m['start_bar'] <= e['start_tick'] // H.bar_ticks('4/4') + 1 <= m['end_bar'] and e['core_symbol'] not in m['borrowed']:
                    assert H.chord_pcs(e) <= pcs


def test_key_opening_sections_state_their_tonic():
    for seed in range(12):
        r = H.generate('A 8\nB 8\nA 8\nC 12 4+4+4\nA 8\ncoda 4', dict(seed=seed, mixture=0.9, tonal_departure=0.9))
        for sec in r['sections']:
            i = sec['index']
            f = r['functions'][i]
            if f['recurrence'] == 'statement' and (i == 0 or r['keys'][i] != r['keys'][i - 1]):
                first = [e for e in r['events'] if e['section_index'] == i and e['phrase_index'] == 0]
                if i > 0:   # a key change starts inside the new key; the first section may use a measured chromatic opening
                    assert H.token_chord(first[0]['token'], r['keys'][i])[2] == 'diatonic'
                assert any(e['token'] == '1' for e in first), (seed, i)


def test_borrowed_runs_are_capped():
    for seed in range(12):
        r = H.generate(SONG, dict(seed=seed, mixture=0.7, interest=0.8))
        for sec in r['sections']:
            if r['section_info'][sec['index']].get('policy') == 'new':
                toks = [e['token'] for e in r['events'] if e['section_index'] == sec['index']]
                assert H.borrowed_run(toks, r['keys'][sec['index']]) <= 3


def test_interest_raises_surprise_and_vocabulary():
    def summary(v):
        sur, dist = [], 0
        for seed in range(8):
            r = H.generate(SONG, dict(seed=seed, interest=v))
            sur += [x['surprise'] for x in r['section_info'].values() if x.get('policy') == 'new' and x.get('surprise')]
            dist += len({e['core_symbol'] for e in r['events']})
        return sum(sur) / len(sur), dist
    lo, mid, hi = summary(0.0), summary(0.5), summary(1.0)
    assert lo[0] < mid[0] < hi[0] and hi[1] > lo[1]


def test_interest_half_changes_nothing():
    a = H.generate(SONG, dict(seed=3))
    b = H.generate(SONG, dict(seed=3, interest=0.5, interest_contour='flat'))
    assert cores(a) == cores(b)


def test_contrast_contour_raises_contrasting_sections():
    up = 0
    for seed in range(10):
        r = H.generate(SONG, dict(seed=seed, interest_contour='contrast'))
        cls = {i: f['cls'] for i, f in enumerate(r['functions'])}
        ints = {i: x.get('interest') for i, x in r['section_info'].items() if x.get('policy') == 'new'}
        up += all(v > 0.5 for i, v in ints.items() if cls[i] == 'contrast_statement')
    assert up == 10


def test_development_changes_later_repeats_more():
    form = 'A 8\nB 8\nA 8\nB 8\nA 8\nB 8\nA 8'
    def changed(dev):
        tot = [0, 0, 0]
        for seed in range(10):
            r = H.generate(form, dict(seed=seed, development=dev, adapt_return_endings=False, final_tonic=False))
            a = [[e['token'] for e in r['events'] if e['section_index'] == i] for i in (0, 2, 4, 6)]
            for k in range(3):
                tot[k] += sum(x != y for x, y in zip(a[0], a[k + 1]))
        return tot
    assert sum(changed(0.0)[:2]) == 0
    c = changed(1.0)
    assert c[0] > 0 and c[2] > c[0]


def test_prepare_returns_dial():
    def share(v):
        n = setup = 0
        for seed in range(30):
            r = H.generate(SONG, dict(seed=seed, prepare_returns=v))
            for i, d in enumerate(r['destinations'][:-1]):
                f = r['functions']
                if f[i]['recurrence'] == 'statement' and f[i + 1]['recurrence'] != 'statement':
                    n += 1
                    setup += d['kind'] in H.SETUP_ENDINGS
        return setup / n
    assert share(0.0) < 0.15 < share(0.5) < 0.8 < share(1.0)
