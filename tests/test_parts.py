"""Tests for step 4 pads (parts.py) and step 5 MIDI writing (midi_export.py). Run: python3 test_parts.py"""
import itertools, tempfile
from pathlib import Path
import composition_generator as C
import parts as PT
import midi_export as MX

SONGS = []
def songs():
    if not SONGS:
        for tonic, mode, meter, seed in [('C', 'major', '4/4', 1), ('D', 'minor', '3/4', 2), ('F', 'dorian', '4/4', 3),
                                         ('E', 'phrygian', '6/8', 4), ('G', 'mixolydian', '4/4', 5), ('A', 'lydian', '4/4', 6),
                                         ('B', 'locrian', '4/4', 7), ('Bb', 'major', '12/8', 8)]:
            for style in ({}, {'corpus_mix': {'billboard': 0, 'beatles': 0, 'jazz': 1}, 'colour': 0.9},
                          {'rates': [0.25, 0.5, 1, 2], 'mixture': 0.9}):
                SONGS.append(C.compose(dict(key=f'{tonic} {mode}', meter=meter, seed=str(seed)), harmony=style)[1])
    return SONGS

ALL = [dict(voices=v, tones=t, voicing=vo, articulation=a)
       for v, t in [(2, '1-3'), (2, '1-5'), (2, '3-5'), (3, '1-3-5')] for vo in PT.VOICINGS for a in PT.ARTICULATIONS]

def pad(r, **kw):
    cfg = dict(PT.PAD_DEFAULTS['pad3' if kw.get('voices') == 3 else 'pad2'], **kw)
    return PT.make_pad(PT.chord_timeline(r), cfg, 'p')

def sounding_at(notes, tick):
    return sorted(n['pitch'] for n in notes if n['start'] <= tick < n['start'] + n['duration'])

def test_triads():
    mk = lambda root, ivs: dict(root_pc=root, intervals=ivs, chord_symbol='x')
    assert PT.chord_triad(mk(0, [0, 4, 7, 11])) == (0, 4, 7)            # maj7: 7th ignored
    assert PT.chord_triad(mk(9, [0, 5, 7])) == (9, 2, 4)                # sus4: the 4th stands in for the 3rd
    assert PT.chord_triad(mk(2, [0, 2, 7])) == (2, 4, 9)                # sus2
    assert PT.chord_triad(mk(11, [0, 3, 6])) == (11, 2, 5)              # diminished fifth kept
    assert PT.chord_triad(mk(0, [0, 4, 8])) == (0, 4, 8)                # augmented
    assert PT.chord_triad(mk(0, [0, 4, 7, 14])) == (0, 4, 7)            # add9

def test_changes_only_on_chord_changes():
    for r in songs():
        spans = PT.chord_timeline(r)
        starts = {s['start'] for s in spans}
        assert all(a['triad'] != b['triad'] for a, b in zip(spans, spans[1:]))
        for cfg in ALL:
            p = pad(r, **cfg)
            assert {n['start'] for n in p['notes']} <= starts, cfg

def test_voicings_sound_exactly_the_chord():
    for r in songs():
        spans = PT.chord_timeline(r)
        for cfg in ALL:
            p = pad(r, **cfg)
            for sp, v in zip(spans, p['voicings']):
                want = PT.pad_pcs(sp['triad'], dict(PT.PAD_DEFAULTS['pad2'], **cfg))
                assert sorted(x % 12 for x in v) == sorted(want) and len(v) == cfg['voices']
                assert p['settings']['low'] <= min(v) and max(v) <= p['settings']['high']
                assert max(v) - min(v) < 12                           # close position
                mid = sp['start'] + (sp['end'] - sp['start']) // 2
                assert sounding_at(p['notes'], mid) == sorted(v), (cfg, sp)

def test_root_position():
    for r in songs()[:9]:
        spans = PT.chord_timeline(r)
        for cfg in [c for c in ALL if c['voicing'] == 'root']:
            p = pad(r, **cfg)
            for sp, v in zip(spans, p['voicings']):
                assert v[0] % 12 == PT.pad_pcs(sp['triad'], dict(PT.PAD_DEFAULTS['pad2'], **cfg))[0]
            assert p['stats']['inversions'] == 0

def test_smooth_moves_less_than_root():
    for r in songs():
        for v, t in [(2, '1-3'), (2, '1-5'), (3, '1-3-5')]:
            root = pad(r, voices=v, tones=t, voicing='root')['stats']['mean_movement']
            smooth = pad(r, voices=v, tones=t, voicing='smooth')['stats']['mean_movement']
            assert smooth <= root + 1e-9, (v, t, smooth, root)

def test_clean_restrikes_hold_ties():
    for r in songs():
        n = len(PT.chord_timeline(r))
        for cfg in ALL:
            p = pad(r, **cfg)
            if cfg['articulation'] == 'clean':
                assert len(p['notes']) == n * cfg['voices']
            else:
                assert len(p['notes']) <= n * cfg['voices']
                by_pitch = {}
                for x in sorted(p['notes'], key=lambda x: x['start']):   # a held pitch is never re-struck at a join
                    assert by_pitch.get(x['pitch'], -1) < x['start'], cfg
                    by_pitch[x['pitch']] = x['start'] + x['duration']

def test_hold_strikes_only_changed_notes():
    for r in songs()[:6]:
        spans = PT.chord_timeline(r)
        p = pad(r, voices=3, articulation='hold')
        for i in range(1, len(spans)):
            struck = sorted(n['pitch'] for n in p['notes'] if n['start'] == spans[i]['start'])
            assert struck == sorted(set(p['voicings'][i]) - set(p['voicings'][i - 1]))

def test_merge_and_determinism():
    r = songs()[0]
    a, b = PT.generate_parts(r), PT.generate_parts(r)
    assert a == b
    e = r['events']
    fake = dict(r, events=[dict(e[0], intervals=[0, 4, 7, 11]), dict(e[0], start_tick=e[0]['start_tick'] + e[0]['duration_ticks'])])
    assert len(PT.chord_timeline(fake)) == 1

def test_bad_settings():
    r = songs()[0]
    for bad in [dict(tones='1-7'), dict(voicing='open'), dict(articulation='legato'), dict(low=60, high=66), dict(low=80, high=70)]:
        try:
            PT.generate_parts(r, {'pad2': bad})
        except ValueError:
            continue
        raise AssertionError(bad)

def read_midi(path):
    data = Path(path).read_bytes()
    assert data[:4] == b'MThd'
    fmt, ntr, ppq = int.from_bytes(data[8:10], 'big'), int.from_bytes(data[10:12], 'big'), int.from_bytes(data[12:14], 'big')
    pos, tracks = 14, []
    for _ in range(ntr):
        assert data[pos:pos + 4] == b'MTrk'
        ln = int.from_bytes(data[pos + 4:pos + 8], 'big')
        tracks.append(data[pos + 8:pos + 8 + ln])
        pos += 8 + ln
    assert pos == len(data)
    return fmt, ppq, tracks

def parse_track(t):
    i, tick, out, status = 0, 0, [], None
    while i < len(t):
        d = 0
        while True:
            b = t[i]; i += 1; d = (d << 7) | (b & 127)
            if b < 128: break
        tick += d
        if t[i] == 0xFF:
            typ = t[i + 1]; i += 2; ln = 0
            while True:
                b = t[i]; i += 1; ln = (ln << 7) | (b & 127)
                if b < 128: break
            out.append((tick, 'meta', typ, t[i:i + ln])); i += ln
        else:
            st = t[i]; i += 1
            n = 1 if st >> 4 in (0xC, 0xD) else 2
            out.append((tick, st >> 4, st & 15, t[i:i + n])); i += n
    return out

def test_midi_export():
    try:
        import mido
    except ImportError:
        mido = None
    for r in songs()[::4]:
        doc = PT.generate_parts(r, {'pad2': dict(articulation='clean')})
        with tempfile.TemporaryDirectory() as d:
            paths = MX.write(r, doc, d, 'x')
            assert len(paths) == len(doc['parts']) + 2
            fmt, ppq, tracks = read_midi(paths[-2])
            assert fmt == 1 and ppq == 480 and len(tracks) == 1 + len(doc['parts'])
            ends = []
            for k, t in enumerate(tracks):
                ev = parse_track(t)
                ends.append(ev[-1][0])
                assert ev[-1][1:3] == ('meta', 0x2F)
                if k == 0:
                    assert any(e[1:3] == ('meta', 0x51) for e in ev) and any(e[1:3] == ('meta', 0x06) for e in ev)
                    continue
                p = doc['parts'][k - 1]
                assert (0, 0xB, p['channel'], bytes([11, 127])) in ev
                assert (doc['end_tick'], 0xE, p['channel'], bytes([0, 0x40])) in ev
                ons = [e for e in ev if e[1] == 0x9]
                assert len(ons) == len(p['notes']) == len([e for e in ev if e[1] == 0x8])
                for a, b in zip(ev, ev[1:]):                        # note-off before note-on at the same tick
                    if a[0] == b[0] and a[1] == 0x9 and b[1] == 0x8:
                        raise AssertionError('note-on before note-off')
            assert set(ends) == {doc['end_tick']}
            if mido:
                m = mido.MidiFile(paths[-2])
                assert len(m.tracks) == len(tracks) and m.ticks_per_beat == 480

def test_overlap_refused():
    r = songs()[0]
    doc = PT.generate_parts(r)
    p = doc['parts'][0]
    n = p['notes'][0]
    p['notes'].append(dict(n, start=n['start'] + 1))
    try:
        MX.part_track(p, doc['end_tick'])
    except ValueError:
        return
    raise AssertionError('overlap accepted')

def test_spelling():
    import notation as N
    sp = lambda sym, triad: dict(symbol=sym, triad=triad)
    assert N.chord_spelling(sp('A', (9, 1, 4)), [57, 61, 64]) == ["a", "cis'", "e'"]
    assert N.chord_spelling(sp('Bbm', (10, 1, 5)), [58, 61, 65]) == ["bes", "des'", "f'"]
    assert N.chord_spelling(sp('Bdim', (11, 2, 5)), [59, 62, 65]) == ["b", "d'", "f'"]
    assert N.chord_spelling(sp('Dsus4', (2, 7, 9)), [62, 67, 69]) == ["d'", "g'", "a'"]
    assert N.chord_spelling(sp('C', (0, 4, 7)), [60]) == ["c'"]
    assert N.key_command('F# dorian') == '\\key fis \\dorian' and N.key_command('Bb major') == '\\key bes \\major'
    assert N.split_duration(1920, 480) == ['1'] and N.split_duration(2880, 480) == ['1.'] and N.split_duration(720, 480) == ['4.']

def test_score_engraves():
    import shutil, notation as N
    for r in songs()[::3]:
        for cfg in ({}, {'pad2': dict(voicing='root', articulation='clean', tones='3-5')}):
            doc = PT.generate_parts(r, cfg)
            src = N.lily_source(r, doc, 'Test')
            assert src.count('\\new Staff') == len(doc['parts']) and src.count('\\mark \\markup \\box') == len(r['sections'])
            if shutil.which('lilypond'):
                with tempfile.TemporaryDirectory() as d:
                    paths = N.write_score(r, doc, d, 't')
                    assert paths[-1].suffix == '.pdf' and paths[-1].stat().st_size > 1000

if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print('ok', t.__name__)
    print(f'{len(tests)} tests passed over {len(songs())} songs')
