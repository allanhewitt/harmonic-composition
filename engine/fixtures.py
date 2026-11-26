"""Small hand-made harmonies for testing and auditioning engines, in the same shape as the engine's results.

    canonical()                    the handoff's four-bar test: C - F - G - C in C major, one chord per bar
    progression('Am F C G', ...)   any list of triads (major, m, dim, aug, 7, maj7, m7, sus2, sus4), one per bar
"""
import harmonic_engine as H

QUALITIES = {'': [0, 4, 7], 'm': [0, 3, 7], 'dim': [0, 3, 6], 'aug': [0, 4, 8], '7': [0, 4, 7, 10],
             'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10], 'sus2': [0, 2, 7], 'sus4': [0, 5, 7]}
NAMES = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
         'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}


def parse_chord(sym):
    root = sym[:2] if sym[1:2] in ('#', 'b') else sym[:1]
    qual = sym[len(root):]
    if root not in NAMES or qual not in QUALITIES:
        raise ValueError(f'Cannot read chord {sym!r}.')
    return NAMES[root], QUALITIES[qual]


def progression(chords, key='C major', meter='4/4', tempo=100, bars_per_chord=1, repeats=1, phrase=None):
    syms = chords.split() if isinstance(chords, str) else list(chords)
    syms = syms * repeats
    bt = H.bar_ticks(meter)
    span = bt * bars_per_chord
    events = []
    for i, sym in enumerate(syms):
        root, ivs = parse_chord(sym)
        events.append(dict(start_tick=i * span, duration_ticks=span, root_pc=root, intervals=ivs, bass_pc=root,
                           scale=key, chord_symbol=sym, core_symbol=sym, roman='', section_index=0, identity='A',
                           occurrence=1, phrase_index=0, token='', local_key=key))
    bars = len(syms) * bars_per_chord
    phrase = phrase or min(bars, 4)
    phrases = [phrase] * (bars // phrase) + ([bars % phrase] if bars % phrase else [])
    return dict(events=events, sections=[dict(index=0, identity='A', occurrence=1, start=0, bars=bars, phrases=phrases)],
                keys=[key], settings=dict(H.DEFAULT_SETTINGS, key=key, meter=meter, tempo=tempo))


def canonical(**kw):
    return progression('C F G C', key='C major', **kw)


def flat_plan(result, level=5):
    """A density plan with one level everywhere (every phrase start listed)."""
    out, bar = [], 0
    for si, sec in enumerate(result['sections']):
        for j, ph in enumerate(sec['phrases']):
            out.append(dict(bar=bar, section=si, first=j == 0, level=level, target=level))
            bar += ph
    return out
