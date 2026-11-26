"""API tests for the web server (FastAPI TestClient). Score engraving is checked only when LilyPond is installed."""
import base64
import importlib
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HC_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HC_PASSWORD', raising=False)
    import server
    importlib.reload(server)
    return TestClient(server.app)


def test_health_and_index(client):
    h = client.get('/health').json()
    assert h['status'] == 'ok' and h['engine']
    r = client.get('/')
    assert r.status_code == 200 and 'Harmonic Composition' in r.text
    assert client.get('/static/app.js').status_code == 200


def test_schema_fields_point_into_defaults(client):
    s = client.get('/api/schema').json()
    defaults = s['defaults']
    assert defaults['harmony']['rates'] == ['1/2', '1']
    optional = {'density.parts.pad3', 'density.parts.tenor', 'density.parts.alto', 'density.parts.descant'}
    for sec in s['sections']:
        for f in sec['fields']:
            if f['path'] in optional or (f['path'].startswith('density.parts.') and sec['id'].startswith('seq_')):
                continue
            node = defaults
            for k in f['path'].split('.'):
                assert k in node, f['path']
                node = node[k]
            if f['type'] == 'select':
                assert str(node) in [str(c[0]) for c in f['choices']], (f['path'], node)


def test_script_round_trip(client):
    ex = client.get('/api/examples').json()
    assert 'night_transit' in ex
    text = client.get('/api/examples/night_transit').json()['yaml']
    cfg = client.post('/api/script/parse', json={'yaml': text}).json()['config']
    assert cfg['piece']['key'] == 'A minor' and cfg['harmony']['rates'] == ['1/4', '1/2']
    again = client.post('/api/script/parse', json={'yaml': client.post('/api/script/dump', json={'config': cfg}).json()['yaml']}).json()['config']
    assert again == cfg


def test_parse_errors_are_400(client):
    r = client.post('/api/script/parse', json={'yaml': 'melody: {}\n'})
    assert r.status_code == 400 and 'Unknown' in r.json()['detail']
    assert client.post('/api/script/parse', json={'yaml': 'harmony: {}\n'}).status_code == 400


def test_generate_and_fetch_files(client):
    text = client.get('/api/examples/night_transit').json()['yaml']
    cfg = client.post('/api/script/parse', json={'yaml': text}).json()['config']
    cfg['density']['keep'] = 70
    r = client.post('/api/generate', json={'config': cfg, 'score': True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['bars'] >= 48 and body['plan'] and body['chart'].strip()
    ids = {p['id'] for p in body['parts']}
    assert ids == {'pad2', 'pad3', 'bass', 'tenor', 'alto', 'descant', 'm960', 'euclid', 'poly', 'tb303', 'turing', 'metro',
                       'marbles', 'rene', 'nodal'}
    z = client.get(f"/runs/{body['run']}/{body['files']['midi_zip']}")
    assert z.status_code == 200 and z.content[:2] == b'PK'
    res = client.get(f"/runs/{body['run']}/{body['files']['resolved']}")
    assert yaml.safe_load(res.text)['density']['keep'] == 70
    if shutil.which('lilypond'):
        assert body['files'].get('score_pdf')
        pdf = client.get(f"/runs/{body['run']}/{body['files']['score_pdf']}")
        assert pdf.content[:4] == b'%PDF'
        if shutil.which('pdftoppm'):
            assert body['pages'] and client.get(f"/runs/{body['run']}/{body['pages'][0]}").content[:4] == b'\x89PNG'


def test_generate_error_is_400(client):
    cfg = client.get('/api/schema').json()['defaults']
    cfg['piece']['length'] = '8'
    cfg['structure']['model'] = 'verse_chorus'
    r = client.post('/api/generate', json={'config': cfg, 'score': False})
    assert r.status_code == 400 and r.json()['detail']


def test_run_files_cannot_escape(client):
    assert client.get('/runs/../etc/passwd').status_code == 404
    assert client.get('/runs/20260101-000000-abcd/..%2F..%2Fx').status_code == 404
    assert client.get('/runs/nonsense/x').status_code == 404


def test_save_and_list_pieces(client):
    text = client.get('/api/examples/night_transit').json()['yaml']
    assert client.put('/api/pieces/My piece 1', json={'yaml': text}).status_code == 200
    names = [p['name'] for p in client.get('/api/pieces').json()]
    assert names == ['My piece 1']
    assert client.get('/api/pieces/My piece 1').json()['yaml'] == text
    assert client.put('/api/pieces/../bad', json={'yaml': text}).status_code in (400, 404)
    assert client.put('/api/pieces/bad', json={'yaml': 'melody: 1'}).status_code == 400


def test_basic_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('HC_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HC_USERNAME', 'allan')
    monkeypatch.setenv('HC_PASSWORD', 'secret')
    import server
    importlib.reload(server)
    c = TestClient(server.app)
    assert c.get('/health').status_code == 200
    assert c.get('/').status_code == 401
    good = base64.b64encode(b'allan:secret').decode()
    bad = base64.b64encode(b'allan:nope').decode()
    assert c.get('/', headers={'Authorization': f'Basic {good}'}).status_code == 200
    assert c.get('/', headers={'Authorization': f'Basic {bad}'}).status_code == 401
    monkeypatch.delenv('HC_PASSWORD')


def test_export_copy_and_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('HC_DATA_DIR', str(tmp_path / 'local'))
    monkeypatch.delenv('HC_PASSWORD', raising=False)
    import server
    for target, ok in ((tmp_path / 'vault' / 'Runs', True), (tmp_path / 'blocker', False)):
        if not ok:
            target.write_text('a file where a folder should be')
        monkeypatch.setenv('HC_EXPORT_DIR', str(target))
        importlib.reload(server)
        c = TestClient(server.app)
        cfg = c.get('/api/schema').json()['defaults']
        cfg['lines']['enabled'] = False
        r = c.post('/api/generate', json={'config': cfg, 'score': False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (tmp_path / 'local' / 'runs' / body['run'] / body['files']['midi_zip']).exists()
        if ok:
            assert body['exported'] and not body['export_error']
            copied = list((tmp_path / 'vault' / 'Runs').iterdir())[0]
            assert (copied / body['files']['midi_zip']).exists()
        else:
            assert body['export_error'] and not body['exported']
    monkeypatch.delenv('HC_EXPORT_DIR')


def test_pieces_folder_unavailable(tmp_path, monkeypatch):
    blocker = tmp_path / 'blocked'
    blocker.write_text('x')
    monkeypatch.setenv('HC_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HC_PIECES_DIR', str(blocker / 'Pieces'))
    monkeypatch.delenv('HC_PASSWORD', raising=False)
    import server
    importlib.reload(server)
    c = TestClient(server.app)
    assert c.get('/api/pieces').json() == []
    r = c.put('/api/pieces/x', json={'yaml': 'piece: {key: C major}\n'})
    assert r.status_code == 500 and 'Download script' in r.json()['detail']
    monkeypatch.delenv('HC_PIECES_DIR')
