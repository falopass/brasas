/* MZ-10: «¿Hay fuego cerca de mí?» sin guardar un lugar. Detecciones de las últimas 24 h,
 * incendios CONAF e incidentes abiertos alrededor del punto. La ubicación jamás sale del
 * teléfono: todo se calcula aquí. Se carga con import(): no suma al arranque y al
 * importarse no toca el DOM, así las pruebas lo importan en Node. */
import { api } from './api.js';
import { isReliable } from './data.js';
import { fly } from './map.js';
import { OFFICIAL_LABEL, OFFICIAL_TONE, popupFoco, popupIncidente, popupOficial } from './popup.js';
import { store } from './store.js';
import { closeModal, collapseSheet, openModal, PHONES, pickOnMap, placeForm } from './ui.js';
import { incidentInfo } from './views/incendio.js';
import { $, ago, bearingDeg, cardinal, fmtNum, haversineKm, html, minutesSince, parseUTC, toast } from './util.js';

const RADIO_KM = 30;
const HORAS = 24;
const DATOS_ATRASADOS_MIN = 30;
const TOPE_RESULTADOS = 5;
// Incidentes abiertos: el mismo conjunto que usa el backend (incidents.OPEN_STATES);
// las fuentes fijas (volcán, industria) no son fuego y se excluyen aparte.
const ABIERTOS = new Set(['anomalia', 'posible', 'reportado', 'confirmado', 'controlado']);

/** Lista lo que hay alrededor de `punto`, ordenado por distancia. Solo focos confiables
 *  de las últimas `horas`, CONAF no extinguidos e incidentes abiertos; un foco ya
 *  cubierto por un incidente de la lista no se repite. Los focos dudosos dentro del
 *  radio se cuentan aparte, en `dudosos` (pueden no ser fuego). */
export function cercaDe(punto, { observaciones = [], oficiales = [], incidentes = [] } = {}, { radioKm = RADIO_KM, horas = HORAS, ahora = Date.now() } = {}) {
  const vacio = { items: [], dudosos: 0 };
  const { lat, lon } = punto || {};
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return vacio;
  const ms = ahora instanceof Date ? ahora.getTime() : Number.isFinite(ahora) ? ahora : Date.parse(ahora);
  if (!Number.isFinite(ms)) return vacio;
  const items = [];
  const entrada = (tipo, ref, at) => {
    if (!Number.isFinite(ref?.lat) || !Number.isFinite(ref?.lon)) return null;
    const b = bearingDeg(lat, lon, ref.lat, ref.lon);
    const km = haversineKm(lat, lon, ref.lat, ref.lon);
    if (km > radioKm) return null;
    return { tipo, ref, id: ref.id, lat: ref.lat, lon: ref.lon, at, km, bearing_deg: Math.round(b), cardinal: cardinal(b) };
  };
  // Los incidentes primero: un foco que ya está dentro de uno no se repite como ítem.
  const enIncidente = new Set();
  for (const i of incidentes) {
    if (!i || !ABIERTOS.has(i.status) || i.fixed_source) continue;
    const it = entrada('incidente', i, i.last_seen_at);
    // Una `anomalia` armada solo con señales débiles no es un resultado: sus
    // miembros cuentan solos como dudosos en el loop de abajo (ventana y radio
    // exactos), así que aquí solo se omite la fila — sin bloquearlos ni sumar
    // n_obs a ciegas. Un `confirmado`/`controlado` nunca se degrada: el respaldo
    // de la autoridad pesa más que la confianza de sus detecciones.
    if (i.status === 'anomalia' && i.n_reliable === 0) continue;
    if (it) { items.push(it); enIncidente.add(i.id); }
  }
  for (const f of oficiales) {
    if (!f || f.status === 'extinguido') continue;
    const it = entrada('conaf', f, f.started_at);
    if (it) items.push(it);
  }
  let dudosos = 0;
  for (const o of observaciones) {
    if (!o || o.incident_fixed) continue;
    const t = parseUTC(o.observed_at);
    if (!t || (ms - t.getTime()) / 3600000 >= horas) continue;
    const it = entrada('foco', o, o.observed_at);
    if (!it) continue;
    if (o.incident_id && enIncidente.has(o.incident_id)) continue;
    if (!isReliable(o)) { dudosos += 1; continue; }
    items.push(it);
  }
  items.sort((a, b) => a.km - b.km);
  return { items, dudosos };
}

// Lo que las tres fuentes piden al abrir la pantalla (observaciones ya están en el store).
// Una fuente que no responde no vale una lista vacía: `fail` se avisa arriba.
// Los focos se piden a 24 h — la ventana que la pantalla anuncia, no la del
// mapa — y si esa consulta cae se usa lo que haya en el store como respaldo.
const pedirDatos = () => Promise.all([
  api.observations(HORAS).then((d) => ({ d })).catch(() => ({ fail: 'los puntos de calor del satélite' })),
  api.officialFires().then((d) => ({ d })).catch(() => ({ fail: 'lo que informa CONAF' })),
  api.incidents(HORAS).then((d) => ({ d })).catch(() => ({ fail: 'los posibles incendios' })),
]);
const contar = (punto, [obs, oficiales, incidentes]) => {
  const respaldo = obs.d ? [] : (store.get('observations') || []);
  // El respaldo del mapa solo cubre la ventana que tenga puesta (puede ser 6 h):
  // si no alcanza las 24 h que la pantalla promete, la fuente se declara caída.
  const faltaObs = !obs.d && (!respaldo.length || (store.get('obsHours') || 0) < HORAS);
  return {
    ...cercaDe(punto, {
      observaciones: obs.d?.points || respaldo,
      oficiales: oficiales.d?.fires || [],
      incidentes: incidentes.d?.incidents || [],
    }),
    faltan: [oficiales.fail, incidentes.fail, faltaObs ? 'los puntos de calor del satélite' : null].filter(Boolean),
    fuenteConaf: oficiales.d?.source || null,
  };
};

/** Chip, detalle y verbo temporal de cada ítem de la lista. */
const fichaDe = (it) => {
  if (it.tipo === 'foco') {
    const o = it.ref;
    return { chip: 'Punto de calor', tono: 'aviso', verbo: 'visto',
      detalle: `${o.comuna || 'en Chile'}${o.satellite || o.sensor ? ` · ${o.satellite || o.sensor}` : ''}` };
  }
  if (it.tipo === 'conaf') {
    const f = it.ref;
    return { chip: 'CONAF', tono: OFFICIAL_TONE[f.status] || 'aviso', verbo: 'empezó',
      detalle: `«${f.name || 'Sin nombre'}» · ${f.status_raw || OFFICIAL_LABEL[f.status] || 'Informado'}${f.comuna ? ` · ${f.comuna}` : ''}` };
  }
  const info = incidentInfo(it.ref);
  const n = it.ref.n_obs;
  return { chip: info.short, tono: info.tone, verbo: 'último calor',
    detalle: `${it.ref.comuna || 'en Chile'}${Number.isFinite(n) ? ` · calor visto ${n === 1 ? '1 vez' : `${n} veces`}` : ''}` };
};

const fila = (it, i, fuenteConaf) => {
  const f = fichaDe(it);
  return html`<li><span class="status-badge st-${f.tono}">${f.chip}</span>
    <div class="grow"><b class="small">a ${fmtNum(it.km, it.km < 10 ? 1 : 0)} km, al ${it.cardinal}</b>
      <div class="tiny muted">${f.detalle} · ${f.verbo} ${ago(it.at)}${it.tipo === 'conaf' && fuenteConaf?.url ? html` · <a href="${fuenteConaf.url}" target="_blank" rel="noopener">${fuenteConaf.name || 'CONAF'}</a>` : ''}</div></div>
    <button class="btn btn-sm" data-act="ver" data-ver="${i}">Ver en el mapa</button></li>`;
};

function verEnElMapa(it) {
  closeModal();
  collapseSheet();
  fly(it.lon, it.lat, it.tipo === 'incidente' ? 10 : 12);
  if (it.tipo === 'foco') popupFoco(it.ref, [it.lon, it.lat]);
  else if (it.tipo === 'conaf') popupOficial(it.ref, [it.lon, it.lat]);
  else popupIncidente(it.ref, [it.lon, it.lat]);
}

function abrirLista(punto, items, dudosos, faltan, fuenteConaf) {
  const lastIngest = store.get('status')?.last_ingest_at;
  const atrasado = lastIngest && minutesSince(lastIngest) > DATOS_ATRASADOS_MIN;
  openModal(html`<h2 id="modal-title">¿Hay fuego cerca de ti?</h2>
    <p class="small muted">Los puntos de calor y los posibles incendios de las últimas ${fmtNum(HORAS)} horas, más los incendios que CONAF sigue informando, a menos de ${fmtNum(RADIO_KM)} km de ti. <b>Para responderte, tu ubicación no sale de tu teléfono:</b> solo ordena la lista aquí mismo. Si eliges «Avisarme», ahí sí la usamos para crear el lugar que te avisará.</p>
    ${atrasado ? html`<div class="callout callout-warn" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(lastIngest)}.</b> Que BRASA no muestre fuego no significa que no lo haya.</div>` : ''}
    ${faltan.length ? html`<div class="callout callout-warn" role="alert"><b>No pudimos consultar ${faltan.join(' ni ')}.</b> La lista puede estar incompleta: no asegures que no hay fuego por lo que falta.</div>` : ''}
    ${items.length ? html`<ul class="list" id="cerca-lista">${items.slice(0, TOPE_RESULTADOS).map((it, i) => fila(it, i, fuenteConaf))}</ul>
        ${items.length > TOPE_RESULTADOS ? html`<p class="tiny muted">Y ${items.length - TOPE_RESULTADOS} más: búscalos en el Mapa.</p>` : ''}`
      : faltan.length ? html`<p class="small" id="cerca-vacia"><b>En los datos que sí llegaron no hay calor a menos de ${fmtNum(RADIO_KM)} km,</b> pero faltan fuentes por consultar: puede que haya un incendio que no vemos.</p>`
      : html`<p class="small" id="cerca-vacia"><b>No vemos calor en las últimas ${fmtNum(HORAS)} horas ni incendios informados por CONAF a menos de ${fmtNum(RADIO_KM)} km.</b> Que no aparezca no garantiza que no haya fuego.</p>`}
    ${dudosos ? html`<p class="tiny muted">Además hay ${dudosos === 1 ? 'una señal dudosa' : `${dudosos} señales dudosas`} dentro de ese radio: pueden no ser fuego.</p>` : ''}
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-primary" id="cerca-watch">Avisarme si hay calor cerca de aquí</button></div>
    <div class="phones">${PHONES.filter((p) => p.primary).map((p) => html`<a class="phone primary" href="tel:${p.tel || p.n}"><strong>${p.n}</strong><span>${p.label}</span></a>`)}</div>
    <p class="tiny muted">Un punto de calor puede ser un incendio, una quema o una industria. Si ves fuego o humo, llama: no esperes a BRASA. BRASA no es una alerta oficial.</p>`,
  (body) => {
    body.querySelectorAll('[data-ver]').forEach((b) => b.addEventListener('click', () => verEnElMapa(items[Number(b.dataset.ver)])));
    body.querySelector('#cerca-watch').addEventListener('click', () => placeForm(null, { lat: punto.lat, lon: punto.lon }));
  });
}

/** Permiso denegado o ubicación sin respuesta: cómo activarla y «Elegir en el mapa». */
function permisoDenegado(codigo) {
  openModal(html`<h2 id="modal-title">No pudimos saber dónde estás</h2>
    <p class="small">${codigo === 0 ? 'Tu navegador no permite usar la ubicación.'
      : codigo === 1 ? 'La ubicación está bloqueada para BRASA. Para activarla: toca el candado o el ícono junto a la dirección de esta página, entra a los permisos del sitio y permite la ubicación. Después vuelve a intentarlo.'
      : 'La ubicación no llegó a tiempo o no está disponible. Revisa que el GPS de tu teléfono esté encendido e inténtalo de nuevo.'}</p>
    <p class="tiny muted">Tu ubicación nunca sale de tu teléfono: solo ordena aquí mismo la lista de puntos cercanos.</p>
    <div class="btn-row"><button class="btn btn-primary" id="cerca-pick" data-act="ver">Elegir en el mapa</button>
      <button class="btn btn-ghost" data-cancel>Cancelar</button></div>`, (body) => {
    // data-act="ver" no es decoración: sin mapa cargado, app.js lo descarga antes de este clic.
    body.querySelector('#cerca-pick').addEventListener('click', async () => {
      const picked = await pickOnMap('Mueve el mapa hasta dejar el pin sobre donde estás');
      if (picked) abrirCerca({ punto: picked });
      else permisoDenegado(codigo); // canceló el pin: vuelve a las opciones
    });
    body.querySelector('[data-cancel]').addEventListener('click', closeModal);
  });
}

const modalAbierto = () => $('#modal')?.open === true;

function pedirUbicacion() {
  if (!navigator.geolocation) {
    permisoDenegado(0);
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => {
        if (modalAbierto()) permisoDenegado(err?.code || 0);
        resolve(null);
      },
      { enableHighAccuracy: true, timeout: 12000 });
  });
}

/** Abre la pantalla «cerca de mí». Con `punto` se salta la geolocalización
 *  («Elegir en el mapa» y el aviso «Ver» del Mapa ya la traen). */
export async function abrirCerca({ punto = null } = {}) {
  const datos = pedirDatos();
  openModal(html`<h2 id="modal-title">¿Hay fuego cerca de ti?</h2>
    <p class="small muted" role="status">${punto ? 'Buscando los puntos de calor cercanos…' : 'Buscando tu ubicación y los puntos de calor cercanos…'}</p>`);
  const p = punto || await pedirUbicacion();
  if (!p) return;
  const { items, dudosos, faltan, fuenteConaf } = contar(p, await datos);
  abrirLista(p, items, dudosos, faltan, fuenteConaf);
}

/* Tras «Mi ubicación» en el Mapa (map.js): aviso «N puntos de calor a menos de 30 km ·
 * Ver», sin abrir nada solo. Se amortigua: la posición puede reportarse varias veces
 * seguidas y el aviso no debe repetirse. */
let ultimoAviso = 0;
export async function avisoTrasGeolocate(punto) {
  const ahora = Date.now();
  if (ahora - ultimoAviso < 2 * 60_000) return;
  ultimoAviso = ahora;
  const { items } = contar(punto, await pedirDatos());
  if (!items.length) return;
  toast(`${items.length === 1 ? '1 punto' : `${items.length} puntos`} de calor a menos de ${fmtNum(RADIO_KM)} km`, 'info', 9000,
    { label: 'Ver', onClick: () => abrirCerca({ punto }) });
}
