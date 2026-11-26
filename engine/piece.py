"""Run a piece script: one YAML file describes the whole piece, from song parameters to parts.

    python3 piece.py my_piece.yaml            # score (PDF, if LilyPond is installed) and MIDI
    python3 piece.py my_piece.yaml --no-score

Anything left out of the script takes its default. Next to the outputs the runner writes
<stem>_resolved.yaml: the script with every default filled in, so a result can always be rebuilt exactly.

Sections of the script (all optional except piece):
  piece          title, key, tempo, meter, length, seed            (step 1)
  structure      form model and its settings                       (step 2)
  harmony        harmonic engine settings                          (step 3)
  pads           pad2 / pad3 settings                              (step 4)
  orchestration  constant pad, density contour, randomness, seed   (shared density plan)
  bass           Moog 960 bass settings; enabled: false to leave it out
  lines          tenor / alto / descant settings and seed; enabled: false to leave them out
  sequencers     one entry per sequencer engine (m960, ...), each on by default; enabled: false to leave it out
  density        keep (0-100), mode (even/flatten/contrast), per-part keep, randomness, seed
  output         folder, stem, score, midi
"""
import copy, json, sys
from pathlib import Path
import yaml
import composition_generator as C
import harmonic_engine as H
import parts as PT
import orchestration as O
import bass960 as B
import lines as LN
import thinning as T
import sequencers as SQ
import counterpoint as CP
import notation as N
import midi_export as MX

VERSION = '0.0.1'
SECTIONS = ('piece', 'structure', 'harmony', 'pads', 'orchestration', 'bass', 'lines', 'sequencers', 'rhythm', 'density',
            'output')


def defaults():
    return dict(
        piece=dict(title='Untitled piece', key='C major', tempo=100, meter='4/4', length=64, seed=42),
        structure=copy.deepcopy(C.STRUCTURE_DEFAULTS),
        harmony={},
        pads=PT.default_settings(),
        orchestration=copy.deepcopy(O.DEFAULTS),
        bass=dict(copy.deepcopy(B.DEFAULTS), enabled=True),
        lines=dict({k: {kk: vv for kk, vv in v.items() if kk != 'ladder'} for k, v in LN.LINES.items()}, seed=1, enabled=True),
        sequencers=SQ.defaults(),
        rhythm=CP.defaults(),
        density=copy.deepcopy(T.DEFAULTS),
        output=dict(folder='piece_output', stem=None, score=True, midi=True))


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path):
    return parse(Path(path).read_text())


def build(cfg):
    pc = cfg['piece']
    song = dict(composition=str(pc['title']), key=str(pc['key']), tempo=str(pc['tempo']), meter=str(pc['meter']),
                length=str(pc['length']), seed=str(pc['seed']))
    ctx, result = C.compose(song, cfg['structure'], cfg['harmony'])
    doc = PT.generate_parts(result, cfg['pads'])
    plan = None
    if len([p for p in doc['parts'] if p['kind'] == 'pad']) == 2:
        doc = O.arrange_pads(doc, result, cfg['orchestration'])
        plan = doc['orchestration']['plan']
    else:
        top = 5
        plan = O.plan_levels(result, top, dict(O.DEFAULTS, **cfg['orchestration']))
    extra = []
    if cfg['lines'].get('enabled', True):
        lset = {k: v for k, v in cfg['lines'].items() if k in LN.LINES}
        extra += LN.generate(doc, result, plan, dict(lset, seed=cfg['lines'].get('seed', 1)))
    if cfg['bass'].get('enabled', True):
        extra.append(B.generate(doc, result, plan, {k: v for k, v in cfg['bass'].items() if k != 'enabled'}))
    seqs = SQ.generate(doc, result, plan, cfg.get('sequencers') or {})
    voices = CP.generate(doc, result, plan, cfg.get('rhythm') or {})
    lines_first = [p for p in extra if p['kind'] == 'line'][::-1]
    doc = dict(doc, parts=voices + seqs + lines_first + doc['parts'] + [p for p in extra if p['kind'] == 'bass'])
    doc = T.apply(doc, result, cfg['density'], constant=cfg['orchestration'].get('constant', 'pad2'))
    return ctx, result, doc, plan


def render(cfg, folder, stem, score=True, midi=True):
    """Build the piece described by a merged script `cfg` and write its outputs into `folder`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ctx, result, doc, plan = build(cfg)
    written = []
    pc = cfg['piece']
    sub = f"{pc['key']} · {pc['tempo']} BPM · {pc['meter']} · {doc['end_tick'] // H.bar_ticks(doc['meter'])} bars"
    if cfg['density']['keep'] < 100 or cfg['density']['parts']:
        sub += f" · density {cfg['density']['keep']}% ({cfg['density']['mode']})"
    if score:
        written += N.write_score(result, doc, folder, stem, title=str(pc['title']), subtitle=sub)
    if midi:
        written += MX.write(result, doc, folder / f'{stem}_midi', stem, title=str(pc['title']))
    resolved = folder / f'{stem}_resolved.yaml'
    resolved.write_text(dump(resolve(cfg, ctx, result), header=provenance(result)))
    written.append(resolved)
    return dict(context=ctx, result=result, doc=doc, plan=plan, files=written)


def resolve(cfg, ctx, result):
    """The script as actually used: drawn values (an automatic seed, key, tempo or length range) replaced by the
    values chosen, and the harmony section filled with every effective setting, so reloading it rebuilds the same
    piece even if defaults change later."""
    out = copy.deepcopy(cfg)
    g = (ctx or {}).get('global_parameters', {})
    for k in ('key', 'tempo', 'meter', 'length', 'seed'):
        if k in g:
            out['piece'][k] = g[k]
    out['harmony'] = {k: v for k, v in result['settings'].items() if k not in ('key', 'tempo', 'meter', 'seed')}
    return out


def provenance(result):
    import counterpoint as CP_, seqcore as SC_
    return (f"Resolved script: every setting used for this result. Reloading it rebuilds the same piece with these "
            f"versions: piece runner {VERSION}, generator {C.VERSION}, harmonic engine {result.get('engine')}, "
            f"parts {PT.VERSION}, sequencers {SC_.VERSION}, rhythm family {CP_.VERSION}, density filter {T.VERSION}.")


def dump(cfg, header=None):
    text = yaml.safe_dump(json.loads(json.dumps(cfg)), sort_keys=False, allow_unicode=True)
    return (f'# {header}\n' if header else '') + text


def parse(text):
    """Merge a script given as YAML text with the defaults (same checks as load)."""
    script = yaml.safe_load(text) or {}
    if not isinstance(script, dict):
        raise ValueError('A piece script is a set of sections such as piece:, harmony:, bass:.')
    unknown = set(script) - set(SECTIONS)
    if unknown:
        raise ValueError(f"Unknown script sections: {', '.join(sorted(unknown))}. Allowed: {', '.join(SECTIONS)}.")
    if 'piece' not in script:
        raise ValueError('The script needs a piece: section (title, key, tempo, meter, length, seed).')
    return merge(defaults(), script)


def run(path, score=None, midi=None):
    cfg = load(path)
    out = cfg['output']
    stem = out['stem'] or Path(path).stem
    return render(cfg, out['folder'], stem, out['score'] if score is None else score,
                  out['midi'] if midi is None else midi)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    r = run(args[0], score=False if '--no-score' in sys.argv else None)
    print(H.chart_text(r['result']))
    for p in r['doc']['parts']:
        kept = r['doc']['thinning']['report'].get(p['id'], {}).get('kept')
        print(f"{p['name']:<28} {len(p['notes']):>5} notes" + (f'  kept {kept:.0%}' if kept is not None else ''))
    print('\n'.join(str(f) for f in r['files']))
