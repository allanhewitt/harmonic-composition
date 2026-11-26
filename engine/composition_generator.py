"""Harmonic Composition generator: three steps, no widgets.

  1. Song parameters   gcl_structure.resolve_global     title, tempo, meter, key, length, seed
  2. Structure         gcl_structure.generate_structure sections, bar counts, phrase lengths
  3. Harmony           harmonic_engine.generate         every chord, chosen by the engine

Each step is accepted before the next can use it. Accepting new song parameters marks the
structure outdated; accepting a new structure marks the harmony outdated. Generation is
deterministic for a given seed and variant number.
"""
from __future__ import annotations

import copy
import json

import gcl_structure as G
import harmonic_engine as H
import parts as PT
import midi_export as MX
import notation as NT

VERSION = '0.3.0'
TONICS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
MODES = ['major', 'minor', 'dorian', 'phrygian', 'lydian', 'mixolydian', 'locrian']
SONG_DEFAULTS = dict(G.GLOBAL_DEFAULTS, composition='Untitled sketch', length='64..96')
STRUCTURE_DEFAULTS = dict(G.STRUCT_DEFAULTS, repeats_keep_shape=True)


def song_config(composition='Untitled sketch', tempo='100', meter='4/4', tonic='C', mode='major',
                length='64..96', seed='42'):
    """Song settings as the structure stage expects them. Tonic or mode may be 'auto'."""
    return dict(composition=composition, tempo=str(tempo), meter=meter, key=f'{tonic} {mode}',
                length=str(length), seed=str(seed))


def resolve_song(cfg, variant=0):
    """Step 1. A partly automatic key ('auto dorian', 'D auto') is resolved here; a fully automatic key is
    left to the structure stage, which chooses a tonic and major or minor."""
    cfg = dict(cfg)
    tonic, _, mode = str(cfg['key']).strip().partition(' ')
    if tonic == 'auto' and mode == 'auto':
        cfg['key'] = 'auto'
    g = G.resolve_global(dict(cfg, key='C major' if 'auto' in (tonic, mode) and cfg['key'] != 'auto' else cfg['key']),
                         variant)
    if cfg['key'] != 'auto' and 'auto' in (tonic, mode):
        r = G.rng_for(g['seed'], 'key', variant)
        g['key'] = f"{r.choice(TONICS) if tonic == 'auto' else tonic} {r.choice(['major', 'minor']) if mode == 'auto' else mode}"
    # A drawn length (range or auto) is rounded to whole 4-bar groups inside the range, so that sections built
    # from 4- and 8-bar phrases can fill it. A single number is kept as given.
    if not str(cfg['length']).strip().isdigit():
        lo, hi = G.span(cfg['length'], 1, 1024, (64, 128))
        fours = [n for n in range(lo, hi + 1) if n % 4 == 0]
        if fours:
            g['length'] = min(fours, key=lambda n: (abs(n - g['length']), n))
    return g


FIELDS = dict(sections=('Sections', 1, 64), section_length=('Section length', 1, 1024), phrase_length=('Phrase length', 1, 128))


def check_structure_inputs(cfg):
    """Readable messages for inputs the structure stage cannot parse."""
    if cfg.get('model') == 'explicit':
        return
    for key, (label, lo, hi) in FIELDS.items():
        try:
            G.allowed_ints(cfg[key], lo, hi)
        except ValueError:
            raise ValueError(f"{label}: '{cfg[key]}' isn't readable. Use a number (16), a range with two dots "
                             f"(8..16) or choices separated by commas (8,12,16).") from None


LENGTH_TOLERANCE = 16      # bars either side of the target that the structure stage may use


def nearest_feasible_length(g, cfg, variant, tolerance=LENGTH_TOLERANCE):
    """The song length is a target: the closest total the form can fill, within the tolerance (shorter on a tie)."""
    for d in range(0, tolerance + 1):
        for n in sorted({g['length'] - d, g['length'] + d}):
            if n > 0:
                try:
                    generate_structure(dict(g, length=n), cfg, variant)
                    return n
                except ValueError:
                    pass
    return None


def generate_structure(g, cfg, variant=0, locked=None, previous=None):
    """Structure stage with consistent repeats: every occurrence of a section (each chorus, each A) keeps the
    length and phrase layout of its first occurrence, so the harmony engine can reuse its harmony exactly.
    Section order comes from the GCL form models; set repeats_keep_shape=False (or use the explicit model)
    for GCL's own behaviour, where each occurrence is sized separately."""
    locked = locked or {}
    if cfg.get('repeats_keep_shape', True) is False or cfg['model'] == 'explicit':
        return G.generate_structure(g, cfg, variant, locked, previous)
    r = G.rng_for(g['seed'], 'structure', variant)
    sl = G.allowed_ints(cfg['section_length'], 1, 1024)
    pc = G.allowed_ints(cfg['phrase_length'], 1, 128)
    contiguous = pc == list(range(min(pc), max(pc) + 1))
    allowed = [n for n in sl if (G.phrase_options(n, min(pc), max(pc)) if contiguous else G.discrete_phrase_counts(n, tuple(pc)))]
    if not allowed:
        raise ValueError('No section lengths can satisfy the phrase range.')
    total = g['length']
    forms = G.model_forms(cfg, r, total, allowed)
    if locked:
        forms = [f for f in forms if len(f) == len(previous) and all(f[i] == x['identity'] for i, x in locked.items())]
        if cfg['model'] in ('auto', 'modular') and not forms:
            forms = [[x['identity'] for x in previous]]
    for names in forms:
        order = list(dict.fromkeys(names))
        count = {n: names.count(n) for n in order}
        fixed = {}
        for i, x in locked.items():
            if fixed.get(x['identity'], x['bars']) != x['bars']:
                fixed = None
                break
            fixed[x['identity']] = x['bars']
        if fixed is None:
            continue
        choices = {n: [fixed[n]] if n in fixed else allowed for n in order}

        def reachable(k, remaining, _memo={}):
            key = (k, remaining)
            if key not in _memo:
                if k == len(order):
                    _memo[key] = remaining == 0
                else:
                    n = order[k]
                    _memo[key] = any(reachable(k + 1, remaining - count[n] * x) for x in choices[n]
                                     if remaining - count[n] * x >= 0)
            return _memo[key]
        if not reachable(0, total):
            continue
        lengths, remaining = {}, total
        for k, n in enumerate(order):
            ok = [x for x in choices[n] if remaining - count[n] * x >= 0 and reachable(k + 1, remaining - count[n] * x)]
            share = remaining / sum(count[m] for m in order[k:])
            target = min(share, 8) if n in ('intro', 'outro') else share
            w = [1 / (1 + abs(x - target)) ** (int(cfg['symmetry']) / 35) for x in ok]
            lengths[n] = r.choices(ok, weights=w, k=1)[0]
            remaining -= count[n] * lengths[n]
        rows = G.assemble(names, [lengths[n] for n in names], cfg, r, locked)
        first = {}
        for x in rows:                       # repeats take the first occurrence's phrase layout
            if x['identity'] in first and x['index'] not in locked:
                x['phrases'] = list(first[x['identity']])
            first.setdefault(x['identity'], x['phrases'])
        try:
            G.validate_structure(rows, g, cfg, locked)
            return rows
        except ValueError:
            continue
    raise ValueError('No feasible form for this model, length, phrase/section constraints and locks. '
                     'Adjust constraints or unlock sections.')


def structure_with_target(g, cfg, variant, locked=None, previous=None):
    """Generate a structure treating g['length'] as approximate. Returns (rows, length used)."""
    try:
        return generate_structure(g, cfg, variant, locked or {}, previous), g['length']
    except ValueError as e:
        if 'No feasible form' not in str(e) or locked:
            raise
    n = nearest_feasible_length(g, cfg, variant)
    if n is None:
        raise ValueError(f"No {cfg['model'].replace('_', '-')} form comes within {LENGTH_TOLERANCE} bars of "
                         f"{g['length']} with section lengths {cfg['section_length']} and phrase lengths "
                         f"{cfg['phrase_length']}. Widen the section or phrase lengths, or change the model.")
    return generate_structure(dict(g, length=n), cfg, variant), n


class Project:
    """Candidates and accepted results for the three steps, with staleness tracking."""

    def __init__(self):
        self.ws = G.Worksheet()
        self.harmony_candidate = self.harmony_accepted = None
        self.harmony_settings = None
        self.harmony_parent = self.harmony_accepted_parent = None
        self.harmony_variant = 0
        self.harmony_revision = 0          # increases on every accepted harmony; parts follow it
        self.parts_candidate = self.parts_settings = None
        self.parts_parent = None

    # ---- step 1
    def generate_song(self, cfg):
        if not str(cfg.get('length', '')).strip():
            raise ValueError('Length: give a number of bars (96), a range (64..96) or auto.')
        v = self.ws.global_variant + 1
        self.ws.global_candidate = resolve_song(cfg, v)
        self.ws.global_variant = v
        return self.ws.global_candidate

    def accept_song(self):
        if self.ws.global_candidate is None:
            raise ValueError('Nothing to accept yet: press Generate first.')
        self.ws.accept_global()

    # ---- step 2
    def generate_structure(self, cfg):
        if self.ws.global_accepted is None:
            raise ValueError('Accept the song parameters in step 1 first.')
        check_structure_inputs(cfg)
        ws = self.ws
        g = ws.global_accepted
        g.setdefault('length_target', g['length'])
        v = ws.structure_variant + 1
        rows, used = structure_with_target(dict(g, length=g['length'] if ws.locks else g['length_target']), cfg, v, ws.locks,
                                           ws.structure_candidate)
        # The accepted song length follows the structure actually built; the requested length is kept as the target.
        g['length'] = used
        ws.structure_candidate, ws.structure_config = rows, copy.deepcopy(cfg)
        ws.candidate_parent, ws.structure_variant = ws.global_revision, v
        return rows

    def edit_structure(self, rows_text):
        ws = self.ws
        if ws.structure_candidate is None or ws.candidate_parent != ws.global_revision:
            raise ValueError('Generate a structure from the accepted song parameters first.')
        rows = G.edit_structure(rows_text, ws.global_accepted, ws.structure_config,
                                ws.structure_variant, ws.structure_candidate, ws.locks)
        if ws.structure_config.get('repeats_keep_shape', True):
            first = {}
            for x in rows:               # a repeat with the same length as its first occurrence takes its phrases
                f = first.setdefault(x['identity'], x)
                if f is not x and f['bars'] == x['bars'] and x['index'] not in ws.locks:
                    x['phrases'] = list(f['phrases'])
        ws.structure_candidate = rows
        return rows

    def lock_structure(self, indices):
        self.ws.locks = {i: copy.deepcopy(self.ws.structure_candidate[i]) for i in indices}

    def accept_structure(self):
        if self.ws.structure_candidate is None or self.ws.candidate_parent != self.ws.global_revision:
            raise ValueError('Nothing to accept yet: press Generate first.')
        self.ws.accept_form()

    def context(self):
        """The accepted song parameters and structure (schema gcl-context-0.1), or None if outdated."""
        return self.ws.context()

    # ---- step 3
    def generate_harmony(self, settings=None, new_variant=False, locks=None):
        ctx = self.context()
        if ctx is None:
            raise ValueError('Accept the song parameters and a structure first.')
        if new_variant:
            self.harmony_variant += 1
        previous = self.harmony_candidate if locks and self.harmony_parent == self.ws.structure_revision else None
        if locks and previous is None:
            raise ValueError('Generate harmony for this structure before locking sections.')
        result = H.generate(ctx, settings or {}, variant=self.harmony_variant, previous=previous, locks=locks)
        self.harmony_candidate, self.harmony_settings = result, copy.deepcopy(settings or {})
        self.harmony_parent = self.ws.structure_revision
        return result

    def accept_harmony(self):
        if self.harmony_candidate is None or self.harmony_parent != self.ws.structure_revision:
            raise ValueError('Generate harmony for the accepted structure first.')
        self.harmony_accepted = copy.deepcopy(self.harmony_candidate)
        self.harmony_accepted_parent = self.harmony_parent
        self.harmony_revision = (self.harmony_revision or 0) + 1

    def harmony_current(self):
        return self.harmony_candidate is not None and self.harmony_parent == self.ws.structure_revision \
            and self.context() is not None

    def harmony_accepted_current(self):
        return self.harmony_accepted is not None and self.harmony_accepted_parent == self.ws.structure_revision \
            and self.context() is not None

    # ---- step 4
    def generate_parts(self, settings=None):
        """Parts for the accepted harmony. A current, unaccepted harmony candidate is accepted first."""
        if not self.harmony_accepted_current() or (self.harmony_current() and self.harmony_candidate != self.harmony_accepted):
            if not self.harmony_current():
                raise ValueError('Generate and accept harmony in step 3 first.')
            self.accept_harmony()
        doc = PT.generate_parts(self.harmony_accepted, settings)
        self.parts_candidate, self.parts_settings = doc, copy.deepcopy(settings or {})
        self.parts_parent = self.harmony_revision
        return doc

    def parts_current(self):
        return self.parts_candidate is not None and self.parts_parent == self.harmony_revision \
            and self.harmony_accepted_current()

    # ---- step 5
    def write_midi(self, folder, stem):
        if not self.parts_current():
            raise ValueError('Generate parts in step 4 for the accepted harmony first.')
        title = (self.context() or {}).get('global_parameters', {}).get('composition', 'Harmonic composition')
        return MX.write(self.harmony_accepted, self.parts_candidate, folder, stem, title=str(title))

    def write_score(self, folder, stem, pdf=True):
        if not self.parts_current():
            raise ValueError('Generate parts in step 4 for the accepted harmony first.')
        g = (self.context() or {}).get('global_parameters', {})
        sub = f"{g.get('key', '')} · {g.get('tempo', '')} BPM · {g.get('meter', '')} · {g.get('length', '')} bars"
        return NT.write_score(self.harmony_accepted, self.parts_candidate, folder, stem,
                              title=str(g.get('composition', 'Harmonic composition')), subtitle=sub, pdf=pdf)

    # ---- records
    def manifest(self):
        """Everything needed to reproduce the piece: song, structure, harmony settings and result."""
        ctx = self.context()
        h = self.harmony_accepted if self.harmony_accepted_parent == self.ws.structure_revision else None
        return dict(schema='harmonic-composition-0.1', generator_version=VERSION, engine_version=H.ENGINE_VERSION,
                    context=ctx, structure_config=self.ws.accepted_structure_config,
                    harmony=H.manifest(h) if h else None,
                    parts=dict(schema=PT.SCHEMA, version=PT.VERSION, settings=self.parts_candidate['settings'])
                    if self.parts_current() else None)

    def snapshot(self):
        return json.loads(json.dumps(dict(worksheet=self.ws.snapshot(), harmony_candidate=self.harmony_candidate,
                                          harmony_accepted=self.harmony_accepted, harmony_settings=self.harmony_settings,
                                          harmony_parent=self.harmony_parent,
                                          harmony_accepted_parent=self.harmony_accepted_parent,
                                          harmony_variant=self.harmony_variant, harmony_revision=self.harmony_revision,
                                          parts_settings=self.parts_settings,
                                          parts_current=self.parts_current()), default=str))

    @classmethod
    def restore(cls, data):
        p = cls()
        p.ws = G.Worksheet.restore(data['worksheet'])
        for k in ('harmony_candidate', 'harmony_accepted', 'harmony_settings', 'harmony_parent',
                  'harmony_accepted_parent', 'harmony_variant'):
            setattr(p, k, data.get(k))
        p.harmony_revision = data.get('harmony_revision') or (1 if p.harmony_accepted else 0)
        p.parts_settings = data.get('parts_settings')
        if data.get('parts_current') and p.harmony_accepted_current():      # parts are deterministic: rebuild them
            p.parts_candidate = PT.generate_parts(p.harmony_accepted, p.parts_settings)
            p.parts_parent = p.harmony_revision
        return p


def compose(song=None, structure=None, harmony=None, song_variant=0, structure_variant=0, harmony_variant=0):
    """All three steps in one call, for scripts and the larger generator. Returns (context, harmony result)."""
    g = resolve_song(dict(SONG_DEFAULTS, **(song or {})), song_variant)
    cfg = dict(STRUCTURE_DEFAULTS, **(structure or {}))
    rows, used = structure_with_target(g, cfg, structure_variant)
    g = dict(g, length=used, length_target=g['length'])
    ctx = dict(schema='gcl-context-0.1', global_parameters=g, sections=rows, structure_revision=1)
    return ctx, H.generate(ctx, harmony or {}, variant=harmony_variant)
