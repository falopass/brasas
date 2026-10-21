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
if (typeof document !== 'undefined') {
  try {
    const saved = JSON.parse(localStorage.getItem('brasa:theme'));
    document.documentElement.dataset.theme = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  } catch { document.documentElement.dataset.theme = 'dark'; }
}

class ApiFail extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function get(path, timeoutMs = 0) {
  const controller = timeoutMs ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response;
  try {
    response = await fetch(path, controller ? { signal: controller.signal } : undefined);
  } catch (err) {
    throw new ApiFail(err?.name === 'AbortError' ? 'El estado no respondió a tiempo.' : 'Sin conexión con el servidor de BRASA.', 0);
  } finally {
    if (timer) clearTimeout(timer);
  }
  if (!response.ok) throw new ApiFail(`Error ${response.status}`, response.status);
  return response.json();
}

function statusMsg(text, retry = false, box = $('#status')) {
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

/* DATOS-01: la edad del dato en palabras, sin prometer que un conjunto está «oficialmente» al día. */
export function edadEnPalabras(segundos) {
  const s = Number(segundos);
  if (segundos == null || !Number.isFinite(s)) return 'sin dato';
  if (s < 60) return 'recién';
  const min = Math.round(s / 60);
  if (min < 60) return `hace ${min} ${min === 1 ? 'minuto' : 'minutos'}`;
  const horas = Math.round(min / 60);
  if (horas < 24) return `hace ${horas} ${horas === 1 ? 'hora' : 'horas'}`;
  const dias = Math.round(horas / 24);
  return `hace ${dias} ${dias === 1 ? 'día' : 'días'}`;
}

const NOMBRE_FUENTE = {
  GOES19_FDCF: 'GOES-19', GOES16_FDCF: 'GOES-16', VIIRS_NOAA20_NRT: 'VIIRS NOAA-20',
  VIIRS_NOAA21_NRT: 'VIIRS NOAA-21', VIIRS_SNPP_NRT: 'VIIRS Suomi NPP', MODIS_NRT: 'MODIS Terra/Aqua',
};

/** Una fila por fuente con detecciones: nombre legible y edad de la observación más nueva. */
export function filasDeFrescura(status = {}, now = Date.now()) {
  const newest = status?.newest_observation || {};
  return Object.entries(newest)
    .filter(([, iso]) => typeof iso === 'string' && iso)
    .map(([key, iso]) => ({
      key,
      label: NOMBRE_FUENTE[key] || key,
      cuando: iso,
      edad: edadEnPalabras((now - Date.parse(iso)) / 1000),
    }));
}

/** Cada cuánto se renueva cada conjunto, según el ciclo real de ingesta (no se inventan minutos). */
export const CADENCIA = {
  incidents: 'según el ciclo',
  observations: 'GOES cada 10 min; VIIRS/MODIS según pasada (~1 h o menos)',
  risk: 'cada 3 h',
  lightning: 'según el ciclo',
  smoke: 'según el ciclo',
  scars: 'se calcula al pedirlo',
  response: 'según el ciclo',
  'boton-rojo': 'cada 3 h',
};

function pintarFrescura(status) {
  const estado = $('#frescura-estado');
  estado.classList.remove('error');
  estado.replaceChildren(`Última ingesta: ${edadEnPalabras(status?.freshness?.age_seconds)}.`);
  const filas = filasDeFrescura(status);
  $('#frescura-lista').replaceChildren(...filas.map((f) => {
    const li = el('li');
    li.append(`${f.label}: ${f.edad}`);
    return li;
  }));
  const fallos = Array.isArray(status?.last_cycle?.failed_sources) ? status.last_cycle.failed_sources : [];
  $('#frescura-fallos').textContent = fallos.length ? `Hoy falló: ${fallos.join(', ')}.` : '';
}

async function loadFrescura() {
  try {
    pintarFrescura(await get('/api/status', 5000));
  } catch {
    $('#frescura-lista').replaceChildren();
    $('#frescura-fallos').textContent = '';
    statusMsg('No pudimos leer el estado ahora. Los conjuntos se pueden descargar igual.', true, $('#frescura-estado'));
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
  tr.append(nombre, params, el('td', null, d.geometry || 'no aplica'), props, el('td', null, d.source || ''),
    el('td', null, CADENCIA[d.id] || 'según el ciclo'));
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
  loadFrescura(); // sin await: la tabla de conjuntos no espera al estado
  try {
    paint(await get('/api/opendata'));
    statusMsg('');
  } catch (err) {
    statusMsg(`No se pudo cargar el índice de datos abiertos. ${err.message} Los enlaces directos de abajo siguen funcionando.`, true);
  }
}

if (typeof document !== 'undefined') load();
