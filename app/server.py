"""Harmonic Composition web server: the engine behind a small JSON API, plus the static front end.

Routes
  GET  /health                      status, versions, whether LilyPond is available
  GET  /api/schema                  menu definitions and the full default script
  POST /api/script/parse            {yaml}    -> {config}   (YAML text to a merged script)
  POST /api/script/dump             {config}  -> {yaml}
  POST /api/generate                {config, score} -> chart, plan, parts, file links
  GET  /runs/{run}/{path}           files of a run (score PDF, page images, MIDI zip, resolved script)
  GET  /api/pieces, GET/PUT /api/pieces/{name}   scripts saved on the server
  GET  /api/examples, GET /api/examples/{name}   example scripts from the repository
Environment
  PORT (3000), HC_DATA_DIR (/data), HC_USERNAME and HC_PASSWORD (optional HTTP basic authentication;
  /health stays open for the container health check).
"""
import base64, copy, datetime as dt, json, os, re, secrets, shutil, subprocess, sys, zipfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'app'))

from fastapi import FastAPI, HTTPException, Request                       # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response         # noqa: E402
from fastapi.staticfiles import StaticFiles                                # noqa: E402

import composition_generator as C                                         # noqa: E402
import harmonic_engine as H                                               # noqa: E402
import parts as PT                                                        # noqa: E402
import piece as P                                                         # noqa: E402
import schema as S                                                        # noqa: E402

VERSION = '0.1.0'
DATA = Path(os.environ.get('HC_DATA_DIR', '/data'))
RUNS, PIECES = DATA / 'runs', DATA / 'pieces'
EXAMPLES = ROOT / 'pieces' / 'examples'
STATIC = ROOT / 'app' / 'static'
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$')
HARMONY_FROM_SONG = {'key', 'tempo', 'meter', 'seed'}

app = FastAPI(title='Harmonic Composition', version=VERSION, docs_url=None, redoc_url=None)


@app.middleware('http')
async def basic_auth(request: Request, call_next):
    user, pw = os.environ.get('HC_USERNAME'), os.environ.get('HC_PASSWORD')
    if pw and request.url.path != '/health':
        ok = False
        h = request.headers.get('authorization', '')
        if h.lower().startswith('basic '):
            try:
                u, _, p = base64.b64decode(h[6:]).decode().partition(':')
                ok = secrets.compare_digest(p, pw) and (not user or secrets.compare_digest(u, user))
            except Exception:
                ok = False
        if not ok:
            return Response('Authentication required', 401, {'WWW-Authenticate': 'Basic realm="Harmonic Composition"'})
    return await call_next(request)


def fraction_text(x):
    f = Fraction(str(x)).limit_denominator(4) if not isinstance(x, str) else Fraction(x)
    return str(f.numerator) if f.denominator == 1 else f'{f.numerator}/{f.denominator}'


def normalise(cfg):
    """Fill harmony defaults (so the menus show them) and write chord rates as fractions."""
    cfg = copy.deepcopy(cfg)
    base = {k: v for k, v in H.DEFAULT_SETTINGS.items() if k not in HARMONY_FROM_SONG}
    cfg['harmony'] = P.merge(base, cfg.get('harmony') or {})
    cfg['harmony']['rates'] = [fraction_text(r) for r in cfg['harmony'].get('rates') or []]
    return cfg


def safe_name(name):
    if not NAME.match(name or ''):
        raise HTTPException(400, 'Use letters, digits, spaces, dots, dashes or underscores (up to 80 characters).')
    return name


def error(e):
    return HTTPException(400, str(e))


@app.get('/health')
def health():
    return dict(status='ok', version=VERSION, engine=H.ENGINE_VERSION, generator=C.VERSION, parts=PT.VERSION,
                lilypond=bool(shutil.which('lilypond')), images=bool(shutil.which('pdftoppm')))


@app.get('/api/schema')
def api_schema():
    return dict(sections=S.schema(), defaults=normalise(P.defaults()))


@app.post('/api/script/parse')
def api_parse(body: dict):
    try:
        return dict(config=normalise(P.parse(body.get('yaml', ''))))
    except Exception as e:
        raise error(e)


@app.post('/api/script/dump')
def api_dump(body: dict):
    return dict(yaml=P.dump(body.get('config') or {}))


def check(cfg):
    unknown = set(cfg) - set(P.SECTIONS)
    if unknown:
        raise ValueError(f"Unknown script sections: {', '.join(sorted(unknown))}.")
    if 'piece' not in cfg:
        raise ValueError('The script needs a piece section.')
    return P.merge(P.defaults(), cfg)


@app.post('/api/generate')
def api_generate(body: dict):
    try:
        cfg = check(body.get('config') or {})
    except Exception as e:
        raise error(e)
    title = str(cfg['piece'].get('title') or 'piece')
    stem = re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_')[:40] or 'piece'
    run_id = dt.datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(2)
    folder = RUNS / run_id
    want_score = bool(body.get('score', True)) and bool(shutil.which('lilypond'))
    try:
        out = P.render(cfg, folder, stem, score=want_score, midi=True)
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise error(e)
    result, doc, plan = out['result'], out['doc'], out['plan']
    files = {'resolved': f'{stem}_resolved.yaml'}
    midi_dir = folder / f'{stem}_midi'
    zpath = folder / f'{stem}_midi.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(midi_dir.iterdir()):
            z.write(f, f.name)
    files['midi_zip'] = zpath.name
    pages = []
    pdf = folder / f'{stem}_score.pdf'
    if pdf.exists():
        files['score_pdf'] = pdf.name
        if shutil.which('pdftoppm'):
            subprocess.run(['pdftoppm', '-r', '110', '-png', str(pdf), str(folder / 'page')], check=True,
                           capture_output=True)
            pages = sorted(p.name for p in folder.glob('page-*.png'))
    bt = H.bar_ticks(doc['meter'])
    secs = result['sections']
    plan_rows = [dict(bar=st['bar'] + 1, section=f"{secs[st['section']]['identity']} {secs[st['section']]['occurrence']}",
                      section_start=st['first'], level=st['level'], target=st['target']) for st in plan]
    parts = []
    report = doc.get('thinning', {}).get('report', {})
    for p in doc['parts']:
        ns = p['notes']
        parts.append(dict(id=p['id'], name=p['name'], kind=p['kind'], channel=p['channel'] + 1, notes=len(ns),
                          lowest=min((n['pitch'] for n in ns), default=None), highest=max((n['pitch'] for n in ns), default=None),
                          kept=report.get(p['id'], {}).get('kept')))
    meta = dict(run=run_id, title=title, created=dt.datetime.now().isoformat(timespec='seconds'), files=files, pages=pages)
    (folder / 'run.json').write_text(json.dumps(meta, indent=2))
    return dict(meta, chart=H.chart_text(result), plan=plan_rows, parts=parts, bars=doc['end_tick'] // bt,
                tempo=doc['tempo'], meter=doc['meter'], score_skipped=not want_score,
                resolved=(folder / files['resolved']).read_text())


@app.get('/runs/{run_id}/{name}')
def run_file(run_id: str, name: str):
    if not re.match(r'^[0-9-]+[0-9a-f]{4}$', run_id) or '/' in name or name.startswith('.'):
        raise HTTPException(404)
    path = (RUNS / run_id / name).resolve()
    if not str(path).startswith(str(RUNS.resolve())) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=name if not name.endswith('.png') else None)


@app.get('/api/pieces')
def list_pieces():
    PIECES.mkdir(parents=True, exist_ok=True)
    return [dict(name=p.stem, modified=dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'))
            for p in sorted(PIECES.glob('*.yaml'), key=lambda p: -p.stat().st_mtime)]


@app.get('/api/pieces/{name}')
def get_piece(name: str):
    path = PIECES / f'{safe_name(name)}.yaml'
    if not path.exists():
        raise HTTPException(404, 'No saved piece by that name.')
    return dict(name=name, yaml=path.read_text())


@app.put('/api/pieces/{name}')
def put_piece(name: str, body: dict):
    safe_name(name)
    text = body.get('yaml', '')
    try:
        P.parse(text)
    except Exception as e:
        raise error(e)
    PIECES.mkdir(parents=True, exist_ok=True)
    (PIECES / f'{name}.yaml').write_text(text)
    return dict(saved=name)


@app.get('/api/examples')
def list_examples():
    return [p.stem for p in sorted(EXAMPLES.glob('*.yaml'))]


@app.get('/api/examples/{name}')
def get_example(name: str):
    path = EXAMPLES / f'{safe_name(name)}.yaml'
    if not path.exists():
        raise HTTPException(404)
    return dict(name=name, yaml=path.read_text())


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


app.mount('/static', StaticFiles(directory=STATIC), name='static')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
