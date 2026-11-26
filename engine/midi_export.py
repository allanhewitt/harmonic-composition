"""Step 5 of the Harmonic Composition Generator: write the parts document to MIDI.

Conventions carried over from Experiments 30-32 (checked against their source):
  * Type 1 files at 480 ticks per quarter note, with a conductor track first: tempo (the piece's tempo counts
    the notated beat, e.g. the dotted crotchet in 6/8, converted to crotchets for MIDI), meter, key
    signatures and a marker at every section ("verse 1 | C major").
  * One channel per part, with a track name and program change.
  * CC11 = 127 at tick 0 and a centred pitch wheel at the final tick of every part, so a part that
    starts late or ends early still lines up with bar 1 and the song's end when imported into Logic.
  * Note-offs come before note-ons on the same tick; same-pitch overlaps on a channel are refused.

Outputs: one whole-song file per part, one combined multitrack file, and a JSON manifest.
"""
import json, math, struct, zipfile
from pathlib import Path
import harmonic_engine as H
import notation as N

VERSION = '0.1.0'


def vlq(n):
    if not 0 <= n <= 0x0FFFFFFF:
        raise ValueError('MIDI delta time out of range.')
    b = [n & 127]
    n >>= 7
    while n:
        b.insert(0, 128 | (n & 127))
        n >>= 7
    return bytes(b)


def meta_text(kind, text):
    data = text.encode('utf-8')
    return b'\xff' + bytes([kind]) + vlq(len(data)) + data


def encode(events, end_tick):
    """events: (tick, priority, bytes). Lower priority sorts first at the same tick."""
    events = sorted(events, key=lambda x: (x[0], x[1]))
    data, prev = bytearray(), 0
    for tick, _, msg in events:
        if tick < prev or tick > end_tick:
            raise ValueError(f'Event at tick {tick} is outside the song.')
        data += vlq(tick - prev) + msg
        prev = tick
    data += vlq(end_tick - prev) + b'\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(data)) + bytes(data)


MODE_OFFSET = {'major': 0, 'dorian': 2, 'phrygian': 4, 'lydian': 5, 'mixolydian': 7, 'minor': 9, 'locrian': 11}
SHARPS_FLATS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: -6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}


def conductor(result, end_tick, title):
    s = result['settings']
    num, den = map(int, s['meter'].split('/'))
    quarter_bpm = float(s['tempo']) * N.tempo_beat(s['meter'])[1]      # the piece's tempo counts the notated beat
    tempo = round(60_000_000 / quarter_bpm)
    ev = [(0, 0, meta_text(0x03, title)), (0, 1, b'\xff\x51\x03' + tempo.to_bytes(3, 'big')),
          (0, 1, b'\xff\x58\x04' + bytes([num, int(math.log2(den)), 24, 8]))]
    bt = H.bar_ticks(s['meter'])
    last = None
    for sec, key in zip(result['sections'], result['keys']):
        tick = sec['start'] * bt
        ev.append((tick, 3, meta_text(0x06, f"{sec['identity']} {sec['occurrence']} | {key}")))
        if key != last:
            pc, mode = H.parse_key(key)
            sf = SHARPS_FLATS[(pc - MODE_OFFSET[mode]) % 12]
            ev.append((tick, 2, b'\xff\x59\x02' + bytes([sf % 256, int(H.REFERENCE_MODE[mode] == 'minor')])))
            last = key
    return encode(ev, end_tick)


def part_track(part, end_tick):
    ch = part['channel']
    if not 0 <= ch <= 15:
        raise ValueError(f"{part['name']}: channel must be 0-15.")
    ev = [(0, 0, meta_text(0x03, part['name'])), (0, 1, bytes([0xC0 | ch, part['program'] & 127])),
          (0, 2, bytes([0xB0 | ch, 11, 127]))]
    active = {}
    for n in sorted(part['notes'], key=lambda n: (n['start'], n['pitch'])):
        on, off, p = n['start'], n['start'] + n['duration'], n['pitch']
        if not (0 <= on < off <= end_tick and 0 <= p <= 127 and 1 <= n['velocity'] <= 127):
            raise ValueError(f"{part['name']}: invalid note {n}.")
        if active.get(p, -1) > on:
            raise ValueError(f"{part['name']}: overlapping notes on pitch {p} at tick {on}.")
        active[p] = off
        ev += [(on, 4, bytes([0x90 | ch, p, n['velocity']])), (off, 3, bytes([0x80 | ch, p, 0]))]
    ev.append((end_tick, 5, bytes([0xE0 | ch, 0x00, 0x40])))      # centred pitch wheel: end anchor
    return encode(ev, end_tick)


def midi_file(tracks):
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), H.PPQ) + b''.join(tracks)


def safe(name):
    return ''.join(c if c.isalnum() else '_' for c in name).strip('_') or 'part'


def write(result, doc, folder, stem, title='Harmonic composition'):
    """Write per-part MIDI, combined MIDI and a manifest into `folder`. Returns the list of paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    end = doc['end_tick']
    if not doc['parts']:
        raise ValueError('No parts to write: switch on at least one part in step 4.')
    head = conductor(result, end, title)
    tracks = {p['id']: part_track(p, end) for p in doc['parts']}
    paths = []
    for i, p in enumerate(doc['parts'], 1):
        path = folder / f"{stem}_{i:02d}_{safe(p['name'])}.mid"
        path.write_bytes(midi_file([head, tracks[p['id']]]))
        paths.append(path)
    combined = folder / f'{stem}_all_parts.mid'
    combined.write_bytes(midi_file([head] + list(tracks.values())))
    paths.append(combined)
    man = folder / f'{stem}_parts_manifest.json'
    man.write_text(json.dumps(dict(
        schema='gcl-midi-export-0.1', writer_version=VERSION, parts_schema=doc['schema'], parts_version=doc['version'],
        tempo=doc['tempo'], meter=doc['meter'], ppq=H.PPQ, end_tick=end,
        bars=end // H.bar_ticks(doc['meter']), files=[p.name for p in paths],
        parts=[dict(id=p['id'], name=p['name'], channel=p['channel'] + 1, program=p['program'], settings=p['settings'],
                    stats=p['stats']) for p in doc['parts']]), indent=2))
    paths.append(man)
    return paths


def bundle(paths, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, Path(p).name)
    return zip_path
