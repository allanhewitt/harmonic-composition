// Harmonic Composition front end: menus built from /api/schema, a piece script behind them, and the results.
'use strict';
const $ = (s, el = document) => el.querySelector(s);
let SCHEMA = [];
let config = {};
let last = null;

const status = (text, kind = '') => { const el = $('#status'); el.textContent = text; el.className = 'status ' + kind; };

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error(body?.detail || body || res.statusText);
  return body;
}

// ---- config paths
function getPath(obj, path) { return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj); }
function setPath(obj, path, value) {
  const keys = path.split('.'); let o = obj;
  keys.slice(0, -1).forEach(k => { if (o[k] == null || typeof o[k] !== 'object') o[k] = {}; o = o[k]; });
  if (value === undefined) delete o[keys.at(-1)]; else o[keys.at(-1)] = value;
}

// ---- menus
function fieldControl(f) {
  const wrap = document.createElement('label'); wrap.className = 'field';
  const name = document.createElement('span'); name.textContent = f.label; wrap.append(name);
  let input;
  const value = getPath(config, f.path);
  if (f.type === 'select') {
    input = document.createElement('select');
    f.choices.forEach(([v, l]) => { const o = new Option(l, v); input.add(o); });
    if (value != null && ![...input.options].some(o => o.value === String(value))) input.add(new Option(String(value), String(value)));
    input.value = value == null ? '' : String(value);
    input.onchange = () => setPath(config, f.path, input.value);
  } else if (f.type === 'number') {
    input = document.createElement('input'); input.type = 'number'; input.min = f.min; input.max = f.max; input.step = f.step;
    input.value = value ?? '';
    input.onchange = () => setPath(config, f.path, input.value === '' ? undefined : Number(input.value));
  } else if (f.type === 'range') {
    input = document.createElement('div'); input.className = 'range';
    const r = document.createElement('input'); r.type = 'range'; r.min = f.min; r.max = f.max; r.step = f.step;
    r.value = value ?? f.min; r.setAttribute('aria-label', f.label);
    const out = document.createElement('output'); out.textContent = Number(r.value).toFixed(2);
    r.oninput = () => { out.textContent = Number(r.value).toFixed(2); setPath(config, f.path, Number(r.value)); };
    input.append(r, out);
  } else if (f.type === 'bool') {
    input = document.createElement('input'); input.type = 'checkbox'; input.checked = value !== false;
    input.onchange = () => setPath(config, f.path, input.checked);
  } else if (f.type === 'multi') {
    input = document.createElement('div'); input.className = 'multi';
    const chosen = new Set((value || []).map(String));
    f.choices.forEach(([v, l]) => {
      const lab = document.createElement('label'); const c = document.createElement('input'); c.type = 'checkbox';
      c.checked = chosen.has(v);
      c.onchange = () => { c.checked ? chosen.add(v) : chosen.delete(v);
        setPath(config, f.path, f.choices.map(x => x[0]).filter(x => chosen.has(x))); };
      lab.append(c, ' ' + l); input.append(lab);
    });
  } else if (f.type === 'textarea') {
    input = document.createElement('textarea'); input.value = value ?? '';
    input.onchange = () => setPath(config, f.path, input.value);
  } else {
    input = document.createElement('input'); input.type = 'text'; input.value = value ?? '';
    input.onchange = () => setPath(config, f.path, input.value);
  }
  wrap.append(input);
  if (f.help) { const h = document.createElement('small'); h.textContent = f.help; wrap.append(h); }
  return wrap;
}

function renderSettings() {
  const box = $('#settings');
  const open = new Set([...box.querySelectorAll('details[open]')].map(d => d.dataset.id));
  box.innerHTML = '';
  SCHEMA.forEach((sec, i) => {
    const d = document.createElement('details'); d.dataset.id = sec.id;
    d.open = open.size ? open.has(sec.id) : i === 0;
    const s = document.createElement('summary'); s.textContent = sec.label; d.append(s);
    if (sec.help) { const p = document.createElement('p'); p.className = 'help'; p.textContent = sec.help; d.append(p); }
    sec.fields.forEach(f => d.append(fieldControl(f)));
    box.append(d);
  });
}

// ---- script
async function showScript() {
  const box = $('#script'); box.disabled = true;           // no typing until the current script has arrived
  try { box.value = (await api('/api/script/dump', { method: 'POST', body: JSON.stringify({ config }) })).yaml; }
  finally { box.disabled = false; }
}
async function applyScript(text) {
  const r = await api('/api/script/parse', { method: 'POST', body: JSON.stringify({ yaml: text }) });
  config = r.config; renderSettings(); await showScript();
}

// ---- results
function renderResults(r) {
  last = r;
  const base = `/runs/${r.run}/`;
  const links = [];
  if (r.files.score_pdf) links.push(`<a href="${base}${r.files.score_pdf}" target="_blank" rel="noopener">Score (PDF)</a>`);
  links.push(`<a href="${base}${r.files.midi_zip}">MIDI files (zip)</a>`);
  links.push(`<a href="${base}${r.files.resolved}">Resolved script</a>`);
  $('#files').innerHTML = links.join(' · ');
  $('#score').innerHTML = r.pages.length
    ? r.pages.map((p, i) => `<img src="${base}${p}" alt="Score page ${i + 1}" loading="lazy">`).join('')
    : `<p class="muted">${r.score_skipped ? 'LilyPond is not installed on this server, so no score was engraved.' : 'No score pages.'}</p>`;
  $('#chart').textContent = r.chart;
  $('#parts').innerHTML = '<table><thead><tr><th>Part</th><th>Channel</th><th>Notes</th><th>Range (MIDI)</th><th>Kept</th></tr></thead><tbody>'
    + r.parts.map(p => `<tr><td>${esc(p.name)}</td><td>${p.channel}</td><td>${p.notes}</td><td>${p.lowest ?? '–'}–${p.highest ?? '–'}</td>`
      + `<td>${p.kept == null ? '–' : Math.round(p.kept * 100) + '%'}</td></tr>`).join('') + '</tbody></table>';
  renderPlan(r);
}

function renderPlan(r) {
  const W = 900, H = 170, top = 18, bottom = 34, left = 28, bars = r.bars;
  const x = b => left + (b - 1) / bars * (W - left - 8), y = lv => top + (5 - lv) / 5 * (H - top - bottom);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Density level per phrase">`;
  for (let lv = 1; lv <= 5; lv++) svg += `<text x="4" y="${y(lv) + 4}">${lv}</text>`;
  r.plan.forEach((p, i) => {
    const end = i + 1 < r.plan.length ? r.plan[i + 1].bar : bars + 1;
    svg += `<rect class="bar" x="${x(p.bar) + 1}" y="${y(p.level)}" width="${Math.max(1, x(end) - x(p.bar) - 2)}" height="${y(0) - y(p.level)}" opacity="0.8"><title>Bars ${p.bar}–${end - 1}: level ${p.level} (target ${p.target})</title></rect>`;
    svg += `<line class="target" x1="${x(p.bar)}" x2="${x(end)}" y1="${y(p.target)}" y2="${y(p.target)}"/>`;
    if (p.section_start) svg += `<text x="${x(p.bar) + 2}" y="${H - 8}">${esc(p.section)}</text>`;
  });
  svg += '</svg>';
  $('#plan').innerHTML = `<div class="plan">${svg}</div><p class="muted">Bars are the level used in each phrase; dashed lines are the target from the chosen shape.</p>`;
}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ---- actions
async function generate() {
  const b = $('#generate'); b.disabled = true; status('Generating…');
  try {
    const t0 = performance.now();
    const r = await api('/api/generate', { method: 'POST', body: JSON.stringify({ config, score: true }) });
    renderResults(r);
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    if (r.export_error) status(`Generated ${r.bars} bars in ${secs} s. ${r.export_error}`, 'error');
    else status(`Generated ${r.bars} bars in ${secs} s.` + (r.exported ? ` Copied to ${r.exported}.` : ''), 'ok');
  } catch (e) { status(e.message, 'error'); } finally { b.disabled = false; }
}

async function loadList() {
  const ex = await api('/api/examples'); const sel = $('#examples');
  ex.forEach(n => sel.add(new Option(n, n)));
  const saved = await api('/api/pieces'); const s2 = $('#saved');
  [...s2.options].slice(1).forEach(o => o.remove());
  saved.forEach(p => s2.add(new Option(`${p.name} (${p.modified.slice(0, 16).replace('T', ' ')})`, p.name)));
}

function selectTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  document.querySelectorAll('.tab').forEach(p => { p.hidden = p.dataset.panel !== name; });
  if (name === 'script') showScript().catch(e => status(e.message, 'error'));
}

async function init() {
  const h = await api('/health');
  $('#version').textContent = `app ${h.version} · engine ${h.engine}` + (h.lilypond ? '' : ' · no LilyPond');
  const s = await api('/api/schema');
  SCHEMA = s.sections; config = s.defaults; renderSettings();
  await loadList();
  document.querySelectorAll('.tabs button').forEach(b => { b.onclick = () => selectTab(b.dataset.tab); });
  $('#generate').onclick = generate;
  $('#apply-script').onclick = () => applyScript($('#script').value).then(() => status('Script applied.', 'ok')).catch(e => status(e.message, 'error'));
  $('#refresh-script').onclick = () => showScript();
  $('#examples').onchange = async e => {
    if (!e.target.value) return;
    try { await applyScript((await api('/api/examples/' + encodeURIComponent(e.target.value))).yaml); status(`Loaded example ${e.target.value}.`, 'ok'); }
    catch (err) { status(err.message, 'error'); } e.target.value = '';
  };
  $('#saved').onchange = async e => {
    if (!e.target.value) return;
    try { await applyScript((await api('/api/pieces/' + encodeURIComponent(e.target.value))).yaml);
      $('#save-name').value = e.target.value; status(`Opened ${e.target.value}.`, 'ok'); }
    catch (err) { status(err.message, 'error'); } e.target.value = '';
  };
  $('#save').onclick = async () => {
    const name = $('#save-name').value.trim() || String(config.piece?.title || '').trim();
    if (!name) { status('Give the script a name first.', 'error'); return; }
    try { const y = (await api('/api/script/dump', { method: 'POST', body: JSON.stringify({ config }) })).yaml;
      await api('/api/pieces/' + encodeURIComponent(name), { method: 'PUT', body: JSON.stringify({ yaml: y }) });
      await loadList(); status(`Saved ${name}.`, 'ok'); }
    catch (e) { status(e.message, 'error'); }
  };
  $('#upload').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    try { await applyScript(await f.text()); status(`Loaded ${f.name}.`, 'ok'); } catch (err) { status(err.message, 'error'); }
    e.target.value = '';
  };
  $('#download-script').onclick = async () => {
    const y = (await api('/api/script/dump', { method: 'POST', body: JSON.stringify({ config }) })).yaml;
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([y], { type: 'text/yaml' }));
    a.download = (String(config.piece?.title || 'piece').replace(/[^A-Za-z0-9]+/g, '_') || 'piece') + '.yaml'; a.click();
    URL.revokeObjectURL(a.href);
  };
  status('Ready. Choose settings or load an example, then Generate.');
}

init().catch(e => status('Could not start: ' + e.message, 'error'));
