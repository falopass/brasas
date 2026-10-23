/* FOCOS-01 · /focos.html: focos e incendios activos en texto, sin mapa.
 * Solo GET públicos: /api/incidents?hours=24 (señales satelitales agrupadas por
 * incidente) y /api/official-fires (incendios que informa CONAF). Todo lo que se
 * interpola entra por textContent: los nombres de comuna y de incendio vienen de
 * terceros y jamás se parsean como HTML («Talca <b>» se lee tal cual). */

import { fmtDateTime, fmtNum, utcDate } from './formato.js';

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

const TOPE_MS = 8_000; // en 2G la consulta no puede colgar la página: se aborta a los 8 s
const horaChile = new Intl.DateTimeFormat('es-CL', {
  hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/Santiago',
});

/* Estados en palabras, sin jerga. Un punto de calor no es un incendio y
 * «informado por CONAF» es la única confirmación que publica BRASA. */
const INCIDENTE = {
  anomalia: 'Señal de calor vista por satélite',
  posible: 'Posible incendio (el satélite lo vio más de una vez)',
  reportado: 'Posible incendio; un vecino también lo avisó',
  confirmado: 'Incendio informado por CONAF',
  controlado: 'Controlado según CONAF',
  extinguido: 'Extinguido según CONAF',
};
const OFICIAL = { confirmado: 'En curso', controlado: 'Controlado', extinguido: 'Extinguido' };

async function get(path) {
  const ctrl = new AbortController();
  const reloj = setTimeout(() => ctrl.abort(), TOPE_MS);
  try {
    const r = await fetch(path, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(reloj);
  }
}

/* Una fila por incidente; el incendio de CONAF se une por `official_ref` cuando
 * existe. Un incendio de CONAF sin incidente satelital también es activo y la
 * lista no puede esconderlo porque el satélite no lo haya visto todavía. */
function armaFilas(incidents, fires) {
  const porId = new Map((fires || []).map((f) => [f.id, f]));
  const filas = (incidents || []).map((inc) => ({
    inc,
    fire: inc.official_ref ? porId.get(inc.official_ref) || null : null,
    t: utcDate(inc.last_seen_at)?.getTime() ?? 0,
  }));
  const conIncidente = new Set((incidents || []).map((i) => i.official_ref).filter(Boolean));
  for (const fire of fires || []) {
    if (conIncidente.has(fire.id)) continue;
    filas.push({ inc: null, fire, t: utcDate(fire.fetched_at || fire.started_at)?.getTime() ?? 0 });
  }
  filas.sort((a, b) => b.t - a.t);
  return filas;
}

function fila({ inc, fire }) {
  const tr = el('tr');
  tr.append(el('td', null, fire
    ? `${OFICIAL[fire.status] || fire.status_raw || fire.status} según CONAF`
    : INCIDENTE[inc?.status] || INCIDENTE.anomalia));
  const donde = [inc?.comuna || fire?.comuna, inc?.region || fire?.region].filter(Boolean).join(', ') || 'sin comuna publicada';
  tr.append(el('td', null, fire?.name ? `«${fire.name}» · ${donde}` : donde));
  tr.append(el('td', null, fmtDateTime(inc ? inc.last_seen_at : fire.fetched_at || fire.started_at)));
  tr.append(el('td', 'num', inc ? fmtNum(inc.n_obs) : '—'));
  tr.append(el('td', 'num', fire?.area_ha ? `${fmtNum(fire.area_ha, fire.area_ha < 10 ? 1 : 0)} ha` : '—'));
  const ficha = el('td');
  if (inc) {
    const a = el('a', null, 'Ver la ficha');
    a.href = `/#/incendio/${encodeURIComponent(inc.id)}`;
    ficha.append(a);
  } else {
    ficha.textContent = '—';
  }
  tr.append(ficha);
  return tr;
}

function marcaConsulta() {
  const ahora = new Date();
  const t = $('#focos-consulta');
  t.dateTime = ahora.toISOString();
  const texto = horaChile.format(ahora);
  t.textContent = `a las ${texto}`;
  return texto;
}

/* Estados honestos: si una fuente falla se muestra la tabla de la otra con un
 * aviso (nunca «no hay fuego» cuando no se pudo consultar); si fallan las dos,
 * un solo bloque con los teléfonos de emergencia. */
async function load() {
  $('#focos-estado').textContent = 'Consultando…';
  const [inc, ofi] = await Promise.allSettled([
    get('/api/incidents?hours=24'),
    get('/api/official-fires'),
  ]);
  const intento = marcaConsulta();
  const incidents = inc.status === 'fulfilled' ? inc.value?.incidents || [] : null;
  const fires = ofi.status === 'fulfilled' ? ofi.value?.fires || [] : null;
  $('#focos-aviso').hidden = true;
  $('#focos-vacio').hidden = true;
  $('#focos-error').hidden = true;
  if (incidents === null && fires === null) {
    $('#focos-error-hora').textContent = intento;
    $('#focos-error').hidden = false;
    $('#focos-estado').textContent = '';
    return;
  }
  const falta = [];
  if (incidents === null) falta.push('las señales de los satélites');
  if (fires === null) falta.push('los incendios que informa CONAF');
  const filas = armaFilas(incidents, fires);
  $('#focos-tabla-wrap').hidden = !filas.length;
  if (filas.length) $('#focos-filas').replaceChildren(...filas.map(fila));
  if (!filas.length && !falta.length) $('#focos-vacio').hidden = false;
  if (falta.length) {
    const aviso = $('#focos-aviso');
    aviso.textContent = `No pudimos consultar ${falta.join(' ni ')} al intentarlo a las ${intento} (hora de Chile)`
      + (filas.length ? ': la tabla muestra solo lo que sí respondió.' : '.');
    aviso.hidden = false;
  }
  $('#focos-estado').textContent = `Consultado a las ${intento} (hora de Chile).`;
}

if (typeof document !== 'undefined') {
  document.getElementById('focos-reintentar')?.addEventListener('click', load);
  load();
}
