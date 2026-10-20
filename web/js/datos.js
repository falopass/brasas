/* BRASA · datos abiertos (web/datos.html): página pública que explica qué publica la API
 * leyendo el índice autodescriptivo (GET /api/opendata). Pinta la tabla de conjuntos,
 * la licencia y los límites tal como los declara el índice; sin app.js, sin mapa, sin
 * token y sin datos personales. Si el índice no responde, los enlaces directos de la
 * página siguen sirviendo. */

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

class ApiFail extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function get(path) {
  let response;
  try {
    response = await fetch(path);
  } catch {
    throw new ApiFail('Sin conexión con el servidor de BRASA.', 0);
  }
  if (!response.ok) throw new ApiFail(`Error ${response.status}`, response.status);
  return response.json();
}

function statusMsg(text, retry = false) {
  const box = $('#status');
  box.replaceChildren();
  box.classList.toggle('error', retry);
  if (text) box.append(text);
  if (retry) {
    const btn = el('button', 'retry', 'Reintentar');
    btn.type = 'button';
    btn.addEventListener('click', load);
    box.append(el('br'), btn);
  }
}

const cellList = (items) => {
  const ul = el('ul');
  for (const item of items || []) ul.append(el('li', null, item));
  return ul;
};

const cellParams = (params) => {
  const entries = Object.entries(params || {});
  if (!entries.length) return document.createTextNode('sin parámetros');
  return cellList(entries.map(([k, v]) => `${k}: ${v}`));
};

function fila(d) {
  const nombre = el('td');
  nombre.append(el('b', null, d.id));
  const url = el('a', null, d.url);
  url.href = d.url;
  nombre.append(el('br'), url);
  const btn = el('a', 'btn', 'Abrir el archivo');
  btn.href = d.url;
  btn.target = '_blank';
  btn.rel = 'noopener';
  nombre.append(el('br'), btn);
  const params = el('td');
  params.append(cellParams(d.params));
  const props = el('td');
  props.append(cellList(d.properties));
  const tr = el('tr');
  tr.append(nombre, params, el('td', null, d.geometry || 'no aplica'), props, el('td', null, d.source || ''));
  return tr;
}

function paint(idx) {
  $('#filas').replaceChildren(...(idx.datasets || []).map(fila));
  $('#tabla-wrap').hidden = false;
  if (idx.license) {
    $('#licencia').textContent = idx.license;
    $('#licencia-sec').hidden = false;
  }
  const limites = Object.entries(idx.limits || {});
  if (limites.length) {
    $('#limites').replaceChildren(...limites.flatMap(([k, v]) => [el('dt', null, k), el('dd', null, v)]));
    $('#limites-sec').hidden = false;
  }
}

async function load() {
  try {
    paint(await get('/api/opendata'));
    statusMsg('');
  } catch (err) {
    statusMsg(`No se pudo cargar el índice de datos abiertos. ${err.message} Los enlaces directos de abajo siguen funcionando.`, true);
  }
}

load();
