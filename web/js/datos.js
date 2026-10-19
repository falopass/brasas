/* BRASA · datos abiertos (web/datos.html): pinta en vivo el índice autodescriptivo de
 * GET /api/opendata — conjuntos con sus parámetros, geometría, propiedades, fuente,
 * límites y licencia. Página independiente de la app: si el índice no responde, el
 * aviso con «Reintentar» convive con los enlaces directos que ya trae el HTML. */

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

/* Tema: la preferencia guardada en la app (por defecto, oscuro como el resto de BRASA). */
try {
  const saved = JSON.parse(localStorage.getItem('brasa:theme'));
  document.documentElement.dataset.theme = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
} catch { document.documentElement.dataset.theme = 'dark'; }

function statusMsg(text, retry = false) {
  const box = $('#datos-status');
  box.classList.toggle('error', retry);
  box.replaceChildren();
  if (text) box.append(text);
  if (retry) {
    const btn = el('button', 'retry', 'Reintentar');
    btn.type = 'button';
    btn.addEventListener('click', load);
    box.append(el('br'), btn);
  }
}

function listCell(items) {
  const td = el('td');
  const values = items && (Array.isArray(items) ? items : Object.entries(items).map(([k, v]) => `${k}: ${v}`));
  if (!values || !values.length) { td.append(el('span', 'muted', '—')); return td; }
  const ul = el('ul', 'props');
  for (const v of values) ul.append(el('li', null, String(v)));
  td.append(ul);
  return td;
}

function datasetRow(ds) {
  const tr = el('tr');
  tr.append(el('td', null, ds.id || '—'));
  const file = el('td');
  file.append(el('div', 'mono', ds.url || '—'));
  if (ds.url) {
    const open = el('a', 'open-btn', 'Abrir');
    open.href = ds.url;
    open.target = '_blank';
    open.rel = 'noopener';
    file.append(open);
  }
  tr.append(file, listCell(ds.params), el('td', null, ds.geometry || '—'),
    listCell(ds.properties), el('td', null, ds.source || '—'));
  return tr;
}

function datasetsTable(datasets) {
  const table = el('table');
  const head = el('thead');
  const htr = el('tr');
  for (const h of ['Conjunto', 'Archivo', 'Parámetros', 'Geometría', 'Propiedades', 'Fuente']) {
    htr.append(el('th', null, h));
  }
  head.append(htr);
  const body = el('tbody');
  for (const ds of datasets) body.append(datasetRow(ds));
  table.append(head, body);
  return table;
}

function paintLimits(limits) {
  const dl = $('#datos-limites');
  dl.replaceChildren();
  for (const [key, value] of Object.entries(limits || {})) {
    const dt = el('dt');
    dt.append(el('code', null, key));
    dl.append(dt, el('dd', null, String(value)));
  }
  $('#datos-limites-sec').hidden = !dl.childElementCount;
}

function paintLicense(data) {
  $('#datos-licencia').textContent = data.license || '';
  $('#datos-acceso').textContent = data.access ? `Acceso: ${data.access}.` : '';
  $('#datos-nooficial').textContent = data.not_official || '';
  $('#datos-licencia-sec').hidden = !(data.license || data.access || data.not_official);
}

async function load() {
  statusMsg('Cargando el índice de datos abiertos…');
  let data;
  try {
    const r = await fetch('/api/opendata');
    if (!r.ok) throw new Error(`Error ${r.status}`);
    data = await r.json();
  } catch (err) {
    statusMsg(`No se pudo cargar el índice (${err.message}). Los enlaces directos siguen disponibles.`, true);
    $('#datos-tabla').replaceChildren();
    return;
  }
  statusMsg('');
  $('#datos-tabla').replaceChildren(datasetsTable(data.datasets || []));
  paintLimits(data.limits);
  paintLicense(data);
}

load();
