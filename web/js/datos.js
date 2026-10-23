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

/* DAT-04/DAT-05: cada conjunto en palabras simples — qué es, cada cuánto cambia y
 * qué NO se puede concluir de él. La cadencia sigue lo que declara CADENCIA (el
 * ciclo real); un id del índice que no esté aquí cae al `description` del índice. */
export const PLANO = {
  incidents: {
    que: 'Los incendios e incidentes abiertos que BRASA agrupa desde las detecciones.',
    cadencia: CADENCIA.incidents,
    ojo: '«Posible» es evidencia agrupada, no un incendio confirmado: «confirmado» solo lo fija CONAF.',
  },
  observations: {
    que: 'Los puntos de calor que vieron los satélites (GOES-19, VIIRS y MODIS).',
    cadencia: CADENCIA.observations,
    ojo: 'Un punto de calor no es un incendio: puede ser una quema, una industria o un falso positivo.',
  },
  risk: {
    que: 'El peligro de incendio de hoy por comuna, estimado con el clima (30-30-30 y FWI).',
    cadencia: CADENCIA.risk,
    ojo: 'Es una aproximación de BRASA en el centro de la comuna, no el Botón Rojo ni una alerta oficial.',
  },
  lightning: {
    que: 'Los rayos detectados por el satélite GOES (GLM) en las últimas horas.',
    cadencia: CADENCIA.lightning,
    ojo: 'Un rayo cerca no prueba que ese sea el origen de un incendio.',
  },
  smoke: {
    que: 'Las manchas de humo (aerosol) que distingue GOES-19 en la última hora.',
    cadencia: CADENCIA.smoke,
    ojo: 'Es aerosol visto desde el espacio: no es un incendio ni una trayectoria del humo.',
  },
  scars: {
    que: 'La huella de calor de la temporada por comuna, calculada desde las detecciones.',
    cadencia: CADENCIA.scars,
    ojo: 'No es el área quemada oficial ni el perímetro del incendio: es la suma de detecciones.',
  },
  response: {
    que: 'Los tiempos de respuesta a incendios que informa CONAF por temporada.',
    cadencia: CADENCIA.response,
    ojo: 'Son cifras oficiales de temporadas cerradas: no miden la respuesta de hoy.',
  },
  'boton-rojo': {
    que: 'Los días en que CONAF pronostica condiciones favorables para incendios por comuna.',
    cadencia: CADENCIA['boton-rojo'],
    ojo: 'Es un pronóstico de condiciones, no un aviso de incendio en curso.',
  },
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
  const simple = el('td');
  const plano = PLANO[d.id];
  if (plano) simple.append(`${plano.que} Ojo: ${plano.ojo}`);
  else simple.append(d.description || '');
  const params = el('td');
  params.append(cellParams(d.params));
  const props = el('td');
  props.append(d.fields?.length
    ? cellList(d.fields.map((f) => `${f.name} — ${f.description}${f.unit ? ` (${f.unit})` : ''}`))
    : cellList(d.properties));
  const tr = el('tr');
  tr.append(nombre, simple, params, el('td', null, d.geometry || 'no aplica'), props, el('td', null, d.source || ''),
    el('td', null, CADENCIA[d.id] || 'según el ciclo'));
  return tr;
}

/** Primer parámetro numérico declarado en el índice («(48 por defecto)»), para el ejemplo. */
function ejemploUrl(d) {
  for (const [k, v] of Object.entries(d.params || {})) {
    const m = String(v).match(/\((\d+) por defecto\)/);
    if (m) return `${d.url}?${k}=${m[1]}`;
  }
  return d.url;
}

/* «Un camino por conjunto»: un <li> por dataset del índice, en su orden, con su URL
 * y un ejemplo de llamada armado con los parámetros que el propio índice declara. */
function paintDirecto(datasets) {
  $('#directo-lista').replaceChildren(...(datasets || []).map((d) => {
    const li = el('li');
    const a = el('a', null, d.url);
    a.href = d.url;
    li.append(a, document.createTextNode(' · '), el('code', null, `curl -s "${ejemploUrl(d)}"`));
    return li;
  }));
}

/* DAT-03: recetas listas para copiar. Cada una se arma con la URL y los parámetros
 * que el índice declara; si falta el conjunto o el parámetro, la receta no se pinta. */
const RECETAS = [
  { texto: 'Focos de calor de las últimas 24 horas', partes: [{ id: 'observations', params: { hours: 24 } }] },
  { texto: 'Incidentes de la semana', partes: [{ id: 'incidents', params: { hours: 168 } }] },
  { texto: 'Riesgo de hoy por comuna', partes: [{ id: 'risk' }] },
  { texto: 'Humo y rayos de ahora', partes: [{ id: 'smoke' }, { id: 'lightning', params: { hours: 1 } }] },
];

function recetaUrls(partes, datasets) {
  const urls = [];
  for (const p of partes) {
    const d = (datasets || []).find((x) => x.id === p.id);
    if (!d) return null;
    const qs = Object.entries(p.params || {}).map(([k, v]) => {
      if (!(k in (d.params || {}))) return null;
      return `${k}=${v}`;
    });
    if (qs.includes(null)) return null;
    urls.push(d.url + (qs.length ? `?${qs.join('&')}` : ''));
  }
  return urls;
}

function copiar(texto, estado) {
  const ok = () => { estado.textContent = 'Copiado al portapapeles.'; };
  const mal = () => { estado.textContent = 'No se pudo copiar: selecciona el texto y cópialo a mano.'; };
  try {
    const p = navigator.clipboard?.writeText(texto);
    if (p?.then) p.then(ok, mal); else ok();
  } catch { mal(); }
}

function paintRecetas(datasets) {
  const estado = $('#copia-estado');
  $('#recetas').replaceChildren(...RECETAS.map((r) => {
    const urls = recetaUrls(r.partes, datasets);
    if (!urls) return null;
    const bloque = el('div');
    const pre = el('pre');
    const code = el('code', null, urls.join('\n'));
    pre.append(code);
    const btn = el('button', 'btn', 'Copiar');
    btn.type = 'button';
    btn.addEventListener('click', () => copiar(urls.join('\n'), estado));
    bloque.append(el('p', 'note', r.texto), pre, btn);
    return bloque;
  }).filter(Boolean));
}

function paint(idx) {
  $('#filas').replaceChildren(...(idx.datasets || []).map(fila));
  $('#tabla-wrap').hidden = false;
  paintDirecto(idx.datasets);
  paintRecetas(idx.datasets);
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
