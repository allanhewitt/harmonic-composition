"""Tests for the drum family: Drum Machine, Drummer and Percussion."""
import pytest

import drums as D
import midi_export as MX
import notation as N
import piece as P

ENGINES = ('machine', 'drummer', 'percussion')


def build(meter='4/4', length=64):
    cfg = P.defaults()
    cfg['piece'].update(length=length, seed=3, meter=meter)
    return P.build(cfg)


@pytest.fixture(scope='module')
def b44():
    return build()


def gen(b, **engines):
    ctx, r, doc, plan = b
    return D.generate(doc, r, plan, {e: dict(dict(enabled=True), **kw) for e, kw in engines.items()})


def test_off_by_default(b44):
    ctx, r, doc, plan = b44
    assert D.generate(doc, r, plan, {}) == []


def test_parts_on_channel_10_with_gm_notes(b44):
    parts = gen(b44, machine={}, drummer={}, percussion={})
    assert [p['id'] for p in parts] == ['drums_machine', 'drums_drummer', 'drums_percussion']
    gm = set(D.GM_MAP.values())
    for p in parts:
        assert p['kind'] == 'drums' and p['channel'] == 9
        assert p['notes'] and all(n['pitch'] in gm for n in p['notes'])
        by = {}
        for n in p['notes']:
            assert by.get(n['pitch'], -1) <= n['start']
            by[n['pitch']] = n['start'] + n['duration']


def test_deterministic_and_seeded(b44):
    assert gen(b44, drummer={}) == gen(b44, drummer={})
    assert gen(b44, drummer=dict(seed=2))[0]['notes'] != gen(b44, drummer={})[0]['notes']


def test_density_plan_shapes_the_kit(b44):
    ctx, r, doc, plan = b44
    import seqcore as S
    c = S.Context(doc, r, plan)
    g = D.Grid(doc)
    p = gen(b44, machine=dict(conclusiveness=60))[0]
    last_bar = doc['end_tick'] - g.bar_ticks
    for n in p['notes']:
        lvl, pos = c.level_at(n['start']), n['step'] % g.steps
        if n['inst'] == 'kick' and n['start'] < last_bar:
            assert lvl >= 2                                             # kick from level 2
        if n['inst'] == 'snare' and lvl < 3:
            assert pos >= g.steps - 2 * g.spb                           # below level 3, snare only in fills
    assert not any(n['inst'] in ('clap', 'hato') and c.level_at(n['start']) < 4 for n in p['notes'])
    high = [dict(st, level=4) for st in plan]                           # extras arrive at level 4
    q = D.generate(doc, r, high, dict(machine=dict(enabled=True, conclusiveness=60)))[0]
    assert any(n['inst'] in ('clap', 'hato') for n in q['notes'])


def test_conclusiveness_controls_crashes_fills_and_downbeat(b44):
    hi = gen(b44, drummer=dict(conclusiveness=90))[0]
    lo = gen(b44, drummer=dict(conclusiveness=15))[0]
    assert hi['stats']['crashes'] > 0 and hi['stats']['fills'] > 0
    assert lo['stats']['crashes'] == 0 and lo['stats']['fills'] == 0
    g = D.Grid(b44[2])
    down = lambda p: sum(1 for n in p['notes'] if n['inst'] == 'kick' and n['step'] % g.steps == 0)
    assert down(lo) == 0 < down(hi)
    assert not any(n['inst'] == 'snare' for n in lo['notes'])          # backbeat only as sidesticks


def test_drummer_feel_moves_the_snare_behind(b44):
    tight = gen(b44, drummer=dict(feel=0.0, style='motorik'))[0]
    loose = gen(b44, drummer=dict(feel=1.0, style='motorik'))[0]
    lag = lambda p: sum(n['start'] - n['step'] * D.STEP for n in p['notes'] if n['inst'] == 'snare') / \
        max(1, sum(1 for n in p['notes'] if n['inst'] == 'snare'))
    assert lag(loose) > lag(tight) + 5


def test_machine_is_on_the_grid(b44):
    p = gen(b44, machine={})[0]
    assert all(n['start'] == n['step'] * D.STEP for n in p['notes'])


@pytest.mark.parametrize('style', D.STYLES)
def test_every_style(b44, style):
    p = gen(b44, machine=dict(style=style))[0]
    assert p['notes']


@pytest.mark.parametrize('lanes', D.LANE_SETS)
def test_percussion_lane_sets_and_evolution(b44, lanes):
    for evo in ('plan', 'independent'):
        p = gen(b44, percussion=dict(lanes=lanes, evolution=evo))[0]
        assert p['notes'] and set(p['stats']['lanes']) >= {n['inst'] for n in p['notes']}


def test_ambient_percussion_cycles_do_not_divide_the_bar(b44):
    g = D.Grid(b44[2])
    specs = D.lane_specs('shakers_rims', g, 0.2)
    assert all(g.steps % (a[1] if k == 'euclid' else a[0]) for _, k, a in specs if k in ('euclid', 'poly'))


@pytest.mark.parametrize('meter', ['3/4', '6/8', '12/8', '2/4'])
def test_other_meters(meter):
    b = build(meter, 64)
    parts = gen(b, machine={}, drummer={}, percussion={})
    g = D.Grid(b[2])
    assert all(p['notes'] for p in parts)
    if meter == '6/8':
        snares = {n['step'] % g.steps for n in parts[0]['notes'] if n['inst'] == 'snare' and n['velocity'] > 80}
        assert 6 in snares                                              # backbeat on the second dotted crotchet


def test_custom_map_and_bad_settings(b44):
    ctx, r, doc, plan = b44
    m = dict(D.GM_MAP, hatc=22)
    p = D.generate(doc, r, plan, dict(machine=dict(enabled=True), map=m))[0]
    assert 22 in {n['pitch'] for n in p['notes']} and 42 not in {n['pitch'] for n in p['notes']}
    for bad in (dict(machine=dict(enabled=True, style='x')), dict(drummer=dict(enabled=True, feel=2)),
                dict(percussion=dict(enabled=True, lanes='x')), dict(map=dict(kick=200)), dict(nope={})):
        with pytest.raises(ValueError):
            D.generate(doc, r, plan, bad)


def test_drum_staff_and_midi(b44, tmp_path):
    ctx, r, doc, plan = b44
    parts = gen(b44, drummer={})
    d = dict(doc, parts=parts)
    src = N.lily_source(r, d)
    assert '\\new DrumStaff' in src and '\\drummode' in src and 'Score reduction' not in src
    track = MX.part_track(parts[0], doc['end_tick'])
    assert bytes([0xC9]) not in track                                   # no program change on channel 10
    assert bytes([0x99]) in track


def test_example_piece_builds():
    cfg = P.load(__file__.replace('tests/test_drums.py', 'pieces/examples/motorik_drive.yaml'))
    cfg['piece']['length'] = 48
    ctx, r, doc, plan = P.build(cfg)
    assert {'drums_drummer', 'drums_percussion'} <= {p['id'] for p in doc['parts']}
