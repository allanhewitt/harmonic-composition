"""End-to-end tests for the three-step generator. Run with: python -m pytest -q test_composition_generator.py"""
import json

import pytest

import composition_generator as C
import gcl_structure as G
import harmonic_engine as H


def test_compose_every_form_model_and_mode():
    done = 0
    for i, model in enumerate(m for m in G.MODELS if m != 'explicit'):
        for j, mode in enumerate(C.MODES):
            try:
                ctx, r = C.compose(song=dict(key=f'{C.TONICS[(i + j) % 12]} {mode}', seed=str(i * 7 + j)),
                                   structure=dict(model=model))
            except ValueError as e:              # the structure stage may find no form for a random length
                assert 'feasible' in str(e).lower()
                continue
            g = ctx['global_parameters']
            assert r['settings']['key'] == g['key'] and r['settings']['tempo'] == g['tempo']
            assert sum(s['bars'] for s in r['sections']) == g['length']
            assert [s['phrases'] for s in r['sections']] == [s['phrases'] for s in ctx['sections']]
            bt = H.bar_ticks(g['meter'])
            assert sum(e['duration_ticks'] for e in r['events']) == g['length'] * bt
            done += 1
    assert done >= 45


def test_partly_automatic_keys():
    for v in range(6):
        assert C.resolve_song(C.song_config(tonic='auto', mode='dorian'), v)['key'].endswith(' dorian')
        assert C.resolve_song(C.song_config(tonic='Eb', mode='auto'), v)['key'] in ('Eb major', 'Eb minor')
    assert C.resolve_song(C.song_config(tonic='auto', mode='auto', seed='5'), 1) == \
        C.resolve_song(C.song_config(tonic='auto', mode='auto', seed='5'), 1)


def test_project_flow_staleness_and_restore():
    p = C.Project()
    with pytest.raises(ValueError):
        p.generate_harmony()
    p.generate_song(C.song_config(mode='mixolydian', seed='9')); p.accept_song()
    p.generate_structure(dict(C.STRUCTURE_DEFAULTS, model='arch')); p.accept_structure()
    r = p.generate_harmony(dict(colour=0.7)); p.accept_harmony()
    assert p.harmony_current() and p.manifest()['harmony']['events']
    q = C.Project.restore(json.loads(json.dumps(p.snapshot())))
    assert q.context() == p.context() and q.harmony_current()
    # a new structure makes the harmony outdated; a new song makes the structure outdated
    p.generate_structure(dict(C.STRUCTURE_DEFAULTS, model='arch')); p.accept_structure()
    assert not p.harmony_current()
    p.generate_song(C.song_config(tempo='120')); p.accept_song()
    assert p.context() is None


def test_harmony_variants_and_locks():
    p = C.Project()
    p.generate_song(C.song_config(seed='3')); p.accept_song()
    p.generate_structure(dict(C.STRUCTURE_DEFAULTS)); p.accept_structure()
    a = p.generate_harmony()
    b = p.generate_harmony(new_variant=True, locks={1: 'all'})
    first = lambda r, i: [(e['token'], e['duration_ticks']) for e in r['events'] if e['section_index'] == i]
    assert first(a, 1) == first(b, 1)
    assert [e['token'] for e in a['events']] != [e['token'] for e in b['events']]


def test_deterministic():
    assert C.compose(song=dict(seed='11'))[1]['events'] == C.compose(song=dict(seed='11'))[1]['events']


def test_song_length_is_a_target():
    p = C.Project()
    p.generate_song(C.song_config(length='76')); p.accept_song()
    rows = p.generate_structure(dict(C.STRUCTURE_DEFAULTS, section_length='8,16', phrase_length='4,8'))
    g = p.ws.global_accepted
    assert g['length_target'] == 76 and g['length'] in (72, 80) and sum(s['bars'] for s in rows) == g['length']
    p.accept_structure()
    assert p.generate_harmony()['sections'][-1]['start'] + rows[-1]['bars'] == g['length']
    ctx, r = C.compose(song=dict(length='77'), structure=dict(section_length='8,16', phrase_length='4,8'))
    assert ctx['global_parameters']['length_target'] == 77 and ctx['global_parameters']['length'] % 8 == 0


def test_repeated_sections_keep_shape_and_harmony():
    for model in ('verse_chorus', 'aaba', 'arch', 'cyclic'):
        for seed in range(6):
            ctx, r = C.compose(song=dict(seed=str(seed)), structure=dict(model=model))
            first = {}
            for s in ctx['sections']:
                f = first.setdefault(s['identity'], s)
                if f is s:
                    continue
                assert (f['bars'], f['phrases']) == (s['bars'], s['phrases'])
                a = [e['token'] for e in r['events'] if e['section_index'] == f['index']]
                b = [e['token'] for e in r['events'] if e['section_index'] == s['index']]
                assert len(a) == len(b) and sum(x == y for x, y in zip(a, b)) >= len(a) - 3
