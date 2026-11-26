"""Regression tests for the review of 26 November 2026: escaping, reproduction, tempo, exemption, score timing."""
import shutil, struct, tempfile
from pathlib import Path

import pytest

import midi_export as MX
import notation as N
import piece as P
import thinning as T


@pytest.fixture(scope='module')
def small():
    cfg = P.defaults()
    cfg['piece'].update(length=64, seed=3)
    return cfg


def test_text_is_escaped_in_lilypond_source(small):
    cfg = P.merge(small, dict(piece=dict(title='Evil "title" \\ #(system "x")'), pads=dict(pad2=dict(name='Pad "2"\nx'))))
    ctx, r, doc, plan = P.build(cfg)
    src = N.lily_source(r, doc, title=cfg['piece']['title'], subtitle='a "b"')
    assert 'title = "Evil \\"title\\" \\\\ #(system \\"x\\")"' in src
    assert 'instrumentName = "Pad \\"2\\" x"' in src and 'subtitle = "a \\"b\\""' in src


@pytest.mark.skipif(not shutil.which('lilypond'), reason='LilyPond not installed')
def test_quoted_title_engraves(small, tmp_path):
    cfg = P.merge(small, dict(piece=dict(title='A "quoted" \\ title')))
    ctx, r, doc, plan = P.build(cfg)
    paths = N.write_score(r, doc, tmp_path, 'q', title=cfg['piece']['title'])
    assert any(str(p).endswith('.pdf') for p in paths)


def test_resolved_script_rebuilds_an_automatic_piece(tmp_path):
    cfg = P.parse('piece: {title: T, key: auto, tempo: 80..130, meter: 4/4, length: 64..96, seed: auto}\n')
    out = P.render(cfg, tmp_path, 'a', score=False, midi=False)
    text = (tmp_path / 'a_resolved.yaml').read_text()
    again = P.parse(text)
    assert str(again['piece']['seed']) != 'auto' and str(again['piece']['key']) != 'auto'
    assert again['harmony'] and 'rates' in again['harmony']
    ctx, r, doc, plan = P.build(again)
    assert [p['notes'] for p in doc['parts']] == [p['notes'] for p in out['doc']['parts']]
    assert 'harmonic engine' in text.splitlines()[0]


@pytest.mark.parametrize('meter,beat,factor', [('4/4', '4', 1.0), ('6/8', '4.', 1.5), ('12/8', '4.', 1.5),
                                               ('3/8', '8', 0.5), ('2/2', '2', 2.0)])
def test_score_and_midi_tempo_agree(meter, beat, factor):
    assert N.tempo_beat(meter) == (beat, factor)
    result = dict(settings=dict(meter=meter, tempo=120), sections=[], keys=[])
    data = MX.conductor(result, 1920, 'x')
    i = data.index(b'\xff\x51\x03')
    usec = int.from_bytes(data[i + 3:i + 6], 'big')
    assert round(60_000_000 / usec, 3) == 120 * factor               # MIDI crotchets per minute


def test_constant_pad_follows_orchestration(small):
    for constant, variable in (('pad2', 'pad3'), ('pad3', 'pad2')):
        cfg = P.merge(small, dict(orchestration=dict(constant=constant), density=dict(keep=40)))
        ctx, r, doc, plan = P.build(cfg)
        rep = doc['thinning']['report']
        assert constant not in rep and variable in rep


def test_explicit_exempt_list_still_works(small):
    cfg = P.merge(small, dict(density=dict(keep=40, exempt=['pad2', 'pad3'])))
    ctx, r, doc, plan = P.build(cfg)
    assert 'pad2' not in doc['thinning']['report'] and 'pad3' not in doc['thinning']['report']


def test_score_keeps_32nd_note_attacks(small):
    cfg = P.merge(small, dict(sequencers=dict(m960=dict(grid='32'))))
    ctx, r, doc, plan = P.build(cfg)
    m = next(p for p in doc['parts'] if p['id'] == 'm960')
    assert N.notation_grid(m, doc['ppq']) == (60, True)
    music = N.staff_music(m, doc, r, chord_symbols=False)
    assert '32' in music


def test_score_reports_rounded_parts(small):
    ctx, r, doc, plan = P.build(small)
    metro = next(p for p in doc['parts'] if p['id'] == 'metro')
    exact = N.notation_grid(metro, doc['ppq'])[1]
    src = N.lily_source(r, doc)
    assert ('Score reduction' in src) == (not all(N.notation_grid(p, doc['ppq'])[1] for p in doc['parts']))
    if not exact:
        assert 'Seq Metropolix' in src.splitlines()[-1]
