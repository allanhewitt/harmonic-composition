"""Menu definitions for the front end, generated alongside the engine's own defaults.

Each field names its place in the piece script (`path`), how to show it, and its allowed values. Settings that
are not listed here can still be set in the script view; they are kept when the menus change other values.
"""
import composition_generator as C
import gcl_structure as G
import harmonic_engine as H
import parts as PT
import orchestration as O
import bass960 as B
import thinning as T
import seqcore as SC

KEYS = [f'{t} {m}' for m in C.MODES for t in C.TONICS]
RATES = [('1/4', '4 bars'), ('1/3', '3 bars'), ('1/2', '2 bars'), ('2/3', '1½ bars'), ('1', '1 bar'),
         ('2', '½ bar'), ('4', '¼ bar')]


def sel(path, label, choices, help=''):
    return dict(path=path, label=label, type='select', choices=[c if isinstance(c, (list, tuple)) else (c, c) for c in choices],
                help=help)


def num(path, label, lo, hi, step=1, help=''):
    return dict(path=path, label=label, type='number', min=lo, max=hi, step=step, help=help)


def rng(path, label, lo=0.0, hi=1.0, step=0.05, help=''):
    return dict(path=path, label=label, type='range', min=lo, max=hi, step=step, help=help)


def txt(path, label, help=''):
    return dict(path=path, label=label, type='text', help=help)


def flag(path, label, help=''):
    return dict(path=path, label=label, type='bool', help=help)


def pad_fields(pid, two):
    f = [flag(f'pads.{pid}.enabled', 'Include')]
    if two:
        f.append(sel(f'pads.{pid}.tones', 'Chord tones', [('1-3', '1st + 3rd'), ('1-5', '1st + 5th'), ('3-5', '3rd + 5th')]))
    f += [sel(f'pads.{pid}.voicing', 'Voicing', [('smooth', 'Smooth (inversions)'), ('root', 'Root position')]),
          sel(f'pads.{pid}.articulation', 'On chord change', [('hold', 'Hold shared notes'), ('clean', 'Re-strike all')]),
          num(f'pads.{pid}.low', 'Lowest note (MIDI)', 24, 108), num(f'pads.{pid}.high', 'Highest note (MIDI)', 24, 108),
          num(f'pads.{pid}.velocity', 'Velocity', 1, 127)]
    return f


def line_fields(lid, label):
    return [num(f'lines.{lid}.low', f'{label}: lowest (MIDI)', 24, 108), num(f'lines.{lid}.high', f'{label}: highest (MIDI)', 24, 108)]


ROW_CHOICES = [('pitch', 'Pitch'), ('gate', 'Gate length'), ('velocity', 'Accent'), ('time', 'Step length')]


def seq_fields(eid, label, specific):
    p = f'sequencers.{eid}'
    return ([dict(path=f'{p}.enabled', label=f'{label}: include', type='bool'),
             sel(f'{p}.harmonic', 'Harmonic mode', [('adapted', 'Adapted (fit each chord)'), ('transposed', 'Transposed (keep shape)'),
                                                   ('independent', 'Independent (ignore chords)')]),
             sel(f'{p}.value_space', 'Values move through', [('chord', 'Chord tones'), ('scale', 'Scale steps')]),
             sel(f'{p}.grid', 'Step', [('4', 'Crotchets'), ('8', 'Quavers'), ('16', 'Semiquavers'), ('32', 'Demisemiquavers')])]
            + specific
            + [sel(f'{p}.reset', 'Pattern restarts', [('section', 'At each section'), ('phrase', 'At each phrase'), ('never', 'Never')]),
               rng(f'{p}.mutation', 'Gradual change'),
               num(f'{p}.low', 'Lowest note (MIDI)', 12, 115), num(f'{p}.high', 'Highest note (MIDI)', 12, 120),
               num(f'{p}.anchor', 'Root placed near (MIDI)', 12, 115),
               sel(f'{p}.profile', 'Instrument', [('mono_synth', 'Mono synth (Diva, Repro-1…)'), ('poly_synth', 'Poly synth (Repro-5…)'),
                                                  ('mono_hw_novel', 'Mono synth, no velocity')]),
               num(f'{p}.velocity', 'Velocity', 1, 127), num(f'{p}.accent', 'Accent (+ velocity)', 0, 60),
               num(f'{p}.channel', 'MIDI channel (0-15; 9 is drums)', 0, 15),
               txt(f'{p}.seed', 'Seed')])


def schema():
    return [
        dict(id='piece', label='Piece', help='Step 1: the song parameters.', fields=[
            txt('piece.title', 'Title'),
            sel('piece.key', 'Key', KEYS),
            num('piece.tempo', 'Tempo (BPM)', 30, 240),
            sel('piece.meter', 'Meter', ['4/4', '3/4', '6/8', '12/8', '2/4']),
            txt('piece.length', 'Length (bars)', 'A target such as 64, or a range such as 64..96.'),
            txt('piece.seed', 'Seed', 'Any number or word. The same seed gives the same piece.')]),
        dict(id='structure', label='Structure', help='Step 2: sections and phrases.', fields=[
            sel('structure.model', 'Form model', G.MODELS),
            txt('structure.sections', 'Sections', 'Number or range, e.g. 5..9.'),
            txt('structure.section_length', 'Section length (bars)', 'e.g. 8..24'),
            txt('structure.phrase_length', 'Phrase length (bars)', 'e.g. 4..8'),
            flag('structure.intro', 'Intro'), flag('structure.bridge', 'Bridge'), flag('structure.outro', 'Outro'),
            num('structure.recurrence', 'Recurrence', 0, 100), num('structure.contrast', 'Contrast', 0, 100),
            num('structure.symmetry', 'Symmetry', 0, 100),
            flag('structure.repeats_keep_shape', 'Repeats keep their length and phrases'),
            dict(path='structure.explicit', label='Explicit form (model: explicit)', type='textarea',
                 help='One section per line: name and bars.')]),
        dict(id='harmony', label='Harmony', help='Step 3: the engine chooses every chord. 0.5 reproduces the measured corpus behaviour.', fields=[
            dict(path='harmony.rates', label='Chord lengths', type='multi', choices=RATES,
                 help='Which chord lengths the engine may use.'),
            rng('harmony.interest', 'Predictable … interesting'),
            sel('harmony.interest_contour', 'Interest across the piece', H.INTEREST_CONTOURS),
            rng('harmony.development', 'Development across repeats'),
            rng('harmony.harmonic_activity', 'Harmonic activity'),
            rng('harmony.stability', 'Stability'),
            rng('harmony.cadence_strength', 'Cadence strength'),
            rng('harmony.tonal_departure', 'Key changes'),
            rng('harmony.prepare_returns', 'Prepared returns'),
            rng('harmony.colour', 'Chord colour (sevenths, extensions)'),
            rng('harmony.mixture', 'Borrowed chords'),
            rng('harmony.modal_emphasis', 'Modal emphasis'),
            num('harmony.corpus_mix.billboard', 'Style mix: Billboard', 0, 100),
            num('harmony.corpus_mix.beatles', 'Style mix: Beatles', 0, 100),
            num('harmony.corpus_mix.jazz', 'Style mix: jazz', 0, 100)]),
        dict(id='pads', label='Pads', help='Two pads from the chord\'s 1st, 3rd and 5th, changing only when the chord changes.',
             fields=pad_fields('pad2', True) + pad_fields('pad3', False)),
        dict(id='orchestration', label='Density plan', help='One shared plan (levels 1-5) for pads, bass and lines.', fields=[
            sel('orchestration.constant', 'Constant pad', [('pad2', '2-note pad'), ('pad3', '3-note pad')]),
            sel('orchestration.contour', 'Shape', [('role', 'Follow section roles'), ('rising', 'Rising'), ('arch', 'Arch'), ('flat', 'Flat')]),
            rng('orchestration.randomness', 'Randomness'),
            rng('orchestration.phrase_changes', 'Changes at phrase starts', help='0 = only at section starts.'),
            num('orchestration.low', 'Lowest level', 1, 5),
            num('orchestration.velocity_step', 'Velocity change per level', 0, 12),
            txt('orchestration.seed', 'Seed')]),
        dict(id='bass', label='Bass (960)', help='Moog 960-style sequencer bass for the Model D.', fields=[
            flag('bass.enabled', 'Include'),
            num('bass.length', 'Pattern length (steps)', 3, 16, help='Odd lengths drift against the bar.'),
            sel('bass.grid', 'Step', [('8', 'Quavers'), ('16', 'Semiquavers')]),
            rng('bass.gate', 'Gate length', 0.1, 0.9),
            sel('bass.transpose', 'Transposition', [('fitted', 'Fitted to chord and scale'), ('strict', 'Strict (keep intervals)')]),
            sel('bass.reset', 'Pattern restarts', [('section', 'At each section'), ('phrase', 'At each phrase'), ('never', 'Never')]),
            rng('bass.mutation', 'Gradual change'),
            num('bass.low', 'Lowest note (MIDI)', 12, 72), num('bass.high', 'Highest note (MIDI)', 12, 84),
            txt('bass.seed', 'Seed')]),
        dict(id='lines', label='Lines', help='Tenor and alto guide-tone lines and a descant, written phrase by phrase.', fields=[
            flag('lines.enabled', 'Include'), txt('lines.seed', 'Seed')]
            + line_fields('tenor', 'Tenor') + line_fields('alto', 'Alto') + line_fields('descant', 'Descant')),
        dict(id='sequencers', label='Sequencers', help='One instance of each sequencer, each on by default. Values follow the chords '
             '(adapted), keep their shape and move with each chord root (transposed), or ignore the chords (independent).',
             fields=seq_fields('m960', 'Seq 960', [
                 num('sequencers.m960.length', 'Steps', 2, 16),
                 sel('sequencers.m960.rows.a', 'Row A controls', ROW_CHOICES),
                 sel('sequencers.m960.rows.b', 'Row B controls', ROW_CHOICES),
                 sel('sequencers.m960.rows.c', 'Row C controls', ROW_CHOICES),
                 rng('sequencers.m960.skip_rate', 'Skip steps', 0, 0.5, help='Skipped steps take no time.'),
                 rng('sequencers.m960.stop_rate', 'Stop step', 0, 0.5, help='Chance of a Stop step: the pattern halts until its next restart.'),
                 rng('sequencers.m960.time_rate', 'Double-length steps', 0, 0.6)])),
        dict(id='density', label='Density filter', help='Keep only a share of the notes in pads and lines (the constant pad is exempt).', fields=[
            num('density.keep', 'Keep (%)', 0, 100),
            sel('density.mode', 'Mode', [('even', 'Even'), ('flatten', 'Flatten (busiest thinned most)'),
                                         ('contrast', 'Contrast (sparse thinned most)')]),
            num('density.parts.pad3', 'Keep: variable pad (%)', 0, 100),
            num('density.parts.tenor', 'Keep: tenor (%)', 0, 100),
            num('density.parts.alto', 'Keep: alto (%)', 0, 100),
            num('density.parts.descant', 'Keep: descant (%)', 0, 100),
            rng('density.randomness', 'Randomness'),
            txt('density.seed', 'Seed')]),
    ]
