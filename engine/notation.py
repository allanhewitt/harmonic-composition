"""Step 5 (score): engrave the parts document as notation with LilyPond.

Writes LilyPond source (.ly) and, when the `lilypond` program is installed, a PDF.
One staff per part, chord symbols above the top staff, a boxed mark and double bar at every section,
key signatures that follow the harmony's keys (all seven modes), and the song's meter and tempo.

Notes are spelled from the chord (root letter, then the 3rd and 5th on the letters above it), so
A major is A C# E and Bb minor is Bb Db F. Held notes in a "hold" pad are tied into the next chord;
every chord is split at barlines with ties.
"""
import shutil, subprocess
from pathlib import Path
import harmonic_engine as H

VERSION = '0.1.0'
LETTERS = 'cdefgab'
NATURAL = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}
LILY_MODE = {'major': 'major', 'minor': 'minor', 'dorian': 'dorian', 'phrygian': 'phrygian', 'lydian': 'lydian',
             'mixolydian': 'mixolydian', 'locrian': 'locrian'}
# durations in quarter-note units for LilyPond (largest first)
DURATIONS = [(6, '1.'), (4, '1'), (3, '2.'), (2, '2'), (1.5, '4.'), (1, '4'), (0.75, '8.'), (0.5, '8'), (0.25, '16')]


def letter_step(iv):
    """How many letters above the root a chord interval sits."""
    return {0: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4}[iv]


def name_root(symbol):
    """Root letter and alteration from a chord symbol such as 'Bb', 'F#m7', 'Ebmaj7'."""
    letter = symbol[0].lower()
    alter = 1 if symbol[1:2] == '#' else -1 if symbol[1:2] == 'b' else 0
    return letter, alter


def spell(pitch, root_letter, iv):
    """LilyPond absolute pitch for MIDI `pitch`, spelled on the letter `iv` implies above the root."""
    letter = LETTERS[(LETTERS.index(root_letter) + letter_step(iv)) % 7]
    nat_pc = NATURAL[letter]
    alter = ((pitch % 12) - nat_pc + 6) % 12 - 6
    if abs(alter) > 2:
        raise ValueError(f'Cannot spell MIDI {pitch} on {letter}.')
    natural = pitch - alter
    octave = natural // 12 - 4                      # c' (MIDI 60) is octave 1 above c (MIDI 48)
    acc = {-2: 'eses', -1: 'es', 0: '', 1: 'is', 2: 'isis'}[alter]
    marks = "'" * octave if octave >= 0 else ',' * (-octave)
    return letter + acc + marks


GENERAL_STEP = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}


def chord_spelling(span, voicing):
    """Spell each note from the span's chord: the chord's own 3rd and 5th on the 3rd and 5th letters
    above the root (so sus, diminished and augmented chords spell correctly); any other note by its
    interval above the root (b2/2 on the 2nd letter, 4/#4 on the 4th, b6/6 on the 6th, b7/7 on the 7th)."""
    root_letter, _ = name_root(span['symbol'])
    root_pc, third_pc, fifth_pc = span['triad']
    third_iv = (third_pc - root_pc) % 12
    out = []
    for p in voicing:
        pc = p % 12
        if pc == root_pc:
            step = 0
        elif pc == third_pc:
            step = {2: 1, 5: 3}.get(third_iv, 2)
        elif pc == fifth_pc:
            step = 4
        else:
            step = GENERAL_STEP[(pc - root_pc) % 12]
        letter = LETTERS[(LETTERS.index(root_letter) + step) % 7]
        out.append(spell_on(p, letter))
    return out


def spell_on(pitch, letter):
    nat_pc = NATURAL[letter]
    alter = ((pitch % 12) - nat_pc + 6) % 12 - 6
    if abs(alter) > 2:
        raise ValueError(f'Cannot spell MIDI {pitch} on {letter}.')
    natural = pitch - alter
    octave = natural // 12 - 4
    acc = {-2: 'eses', -1: 'es', 0: '', 1: 'is', 2: 'isis'}[alter]
    return letter + acc + ("'" * octave if octave >= 0 else ',' * (-octave))


def split_duration(ticks, ppq):
    q = ticks / ppq
    out = []
    for val, name in DURATIONS:
        while q >= val - 1e-9:
            out.append(name)
            q -= val
    if q > 1e-6:
        raise ValueError(f'Duration of {ticks} ticks cannot be notated with the available values.')
    return out


def key_command(key):
    pc, mode = H.parse_key(key)
    tonic = key.split()[0]
    letter, alter = tonic[0].lower(), (1 if tonic[1:2] == '#' else -1 if tonic[1:2] == 'b' else 0)
    acc = {1: 'is', -1: 'es', 0: ''}[alter]
    return '\\key ' + letter + acc + ' \\' + LILY_MODE[mode]


def section_starts(result):
    bt = H.bar_ticks(result['settings']['meter'])
    return {sec['start'] * bt: (sec, key) for sec, key in zip(result['sections'], result['keys'])}


def staff_music(part, doc, result, chord_symbols):
    """LilyPond music for one part, from its notes: chords, ties and rests, split at barlines,
    chord changes and section starts. Note edges are snapped to a semiquaver grid for notation."""
    bt = H.bar_ticks(doc['meter'])
    ppq = doc['ppq']
    grid = ppq // 4
    snap = lambda t: int(round(t / grid)) * grid
    starts = section_starts(result)
    spans = doc['chords']
    end = doc['end_tick']
    step = {'8': ppq // 2, '16': ppq // 4}.get(str(part.get('settings', {}).get('grid', '8')), ppq // 2)
    if part.get('staccato'):                       # short sequencer notes: written as staccato steps
        notes = [(snap(n['start']), snap(n['start']) + step, n['pitch']) for n in part['notes']]
    else:
        notes = [(snap(n['start']), snap(n['start'] + n['duration']), n['pitch']) for n in part['notes']]
    attacks = {s for s, e, p in notes}
    notes = [n for n in notes if n[1] > n[0]]
    edges = {0, end} | {a for a, b, p in notes} | {b for a, b, p in notes} | set(range(0, end, bt)) \
        | {sp['start'] for sp in spans} | set(starts)
    edges = sorted(e for e in edges if 0 <= e <= end)
    out, last_key, span_i = [], None, 0
    for a, b in zip(edges, edges[1:]):
        while spans[span_i]['end'] <= a:
            span_i += 1
        sp = spans[span_i]
        if a in starts:
            sec, key = starts[a]
            if a > 0:
                out.append('\\bar "||"')
            if key != last_key:
                out.append(key_command(key))
                last_key = key
            if chord_symbols:
                out.append(f'\\mark \\markup \\box "{sec["identity"]} {sec["occurrence"]}"')
        sounding = sorted(p for s, e, p in notes if s <= a < e)
        cont = {p for s, e, p in notes if s <= a < e and e > b}
        vals = split_duration(b - a, ppq)
        for k, d in enumerate(vals):
            last = k == len(vals) - 1
            text = f'^\\markup \\bold "{sp["symbol"]}"' if chord_symbols and a == sp['start'] and k == 0 else ''
            if k == 0 and a in part.get('annotations', {}):
                text += f'_\\markup \\italic "{part["annotations"][a]}"'
            if sounding:
                names = chord_spelling(sp, sounding)
                body = ' '.join(n + ('~' if (not last or p in cont) else '') for n, p in zip(names, sounding))
                art = '-.' if part.get('staccato') and k == 0 and a in attacks else ''
                out.append(f'<{body}>{d}{art}{text}')
            else:
                out.append(f'r{d}{text}')
    return '\n  '.join(out)


def clef_for(part):
    """Treble unless the part mostly sits below the G under middle C."""
    pitches = [n['pitch'] for n in part['notes']] or [60]
    return 'treble' if sum(pitches) / len(pitches) >= 55 else 'bass'


def lily_source(result, doc, title='Harmonic composition', subtitle=''):
    if not doc['parts']:
        raise ValueError('No parts to engrave: switch on at least one part in step 4.')
    num, den = doc['meter'].split('/')
    beat = {'4': '4', '2': '2', '8': '4.' if int(num) % 3 == 0 and int(num) > 3 else '8'}[den]
    staves = []
    for k, p in enumerate(doc['parts']):
        music = staff_music(p, doc, result, chord_symbols=(k == 0))
        tempo = f'\\tempo {beat} = {round(float(doc["tempo"]))}' if k == 0 else ''
        staves.append(f'''  \\new Staff \\with {{ instrumentName = "{p['name']}" shortInstrumentName = "{p.get('short') or p['name'].split(' (')[0].replace(' line', '')}" }} {{
    \\clef "{clef_for(p)}" \\time {doc['meter']} {tempo}
  {music}
    \\bar "|."
  }}''')
    return f'''\\version "2.24.0"
\\header {{
  title = "{title}"
  subtitle = "{subtitle}"
  tagline = ##f
}}
\\paper {{ #(set-paper-size "a4") indent = 32\\mm short-indent = 18\\mm }}
#(set-global-staff-size 17)
\\layout {{
  \\context {{ \\Score \\override BarNumber.break-visibility = ##(#f #t #t) }}
}}
\\score {{
  <<
{chr(10).join(staves)}
  >>
  \\layout {{ }}
}}
'''


def write_score(result, doc, folder, stem, title='Harmonic composition', subtitle='', pdf=True):
    """Write <stem>_score.ly and, if LilyPond is installed, <stem>_score.pdf. Returns the paths written.

    LilyPond runs in a private temporary folder (short path, no spaces, not synced by Dropbox) with relative
    file names, and the finished files are copied into `folder`. Some LilyPond builds cannot change into
    folders inside cloud-storage locations such as ~/Dropbox on macOS."""
    import tempfile
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source = lily_source(result, doc, title, subtitle)
    ly = folder / f'{stem}_score.ly'
    ly.write_text(source)
    paths = [ly]
    exe = shutil.which('lilypond')
    if pdf and exe:
        with tempfile.TemporaryDirectory(prefix='hc-lily-') as tmp:
            (Path(tmp) / 'score.ly').write_text(source)
            run = subprocess.run([exe, '-s', '-o', 'score', 'score.ly'], cwd=tmp, capture_output=True, text=True)
            made = Path(tmp) / 'score.pdf'
            if run.returncode != 0 or not made.exists():
                detail = (run.stderr or run.stdout or '').strip().splitlines()
                raise RuntimeError('LilyPond failed: ' + ' | '.join(detail[-4:])[:800])
            out = folder / f'{stem}_score.pdf'
            shutil.copyfile(made, out)
        paths.append(out)
    return paths
