/* Mi zona: ¿mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer? */
import { api, request } from '../api.js';
import { digest, snapshot } from '../cambios.js';
import { accionesHoy, resumenHoy } from '../prevencion.js';
import { cerrarPopup, popupFoco, popupOficial } from '../popup.js';
import { AGE_BINS, EMPTY_FC, fitBbox, fly, getMap, onReady, pointsGeoJSON, registrarToque, setData, show } from '../map.js';
import { store } from '../store.js';
import { alertChannels, closeModal, collapseSheet, openModal, phonesHtml, placeForm } from '../ui.js';
import { debeRefrescar } from '../pildora.js';
import { $, ago, botonRojoIcs, cardWord, download, haversineKm, minutesSince, dual, emberSvg, fmtDateTime, fmtDay, fmtTime, fmtNum, html, keepPlace, parseUTC, radarSvg, raw, RISK, storage, riskChip, toast, TZ, windFrom, windWords } from '../util.js';
import { INCIDENT } from './incendio.js';

// «Urgente» dice por qué lo es: calor satelital, un incendio de CONAF, una persona mayor o una mezcla.
export const URGENT_TEXT = {
  satelite: 'Un satélite vio calor dentro de tu zona de aviso: muy cerca o con el viento hacia ti',
  conaf: 'CONAF informa un incendio activo dentro de tu zona de aviso',
  persona_mayor: 'Un satélite vio calor dentro de tu zona de aviso y ahí vive alguien que necesita más tiempo para salir',
  ambos: 'CONAF informa un incendio y un satélite vio calor dentro de tu zona de aviso',
};

// Cada estado responde en palabras simples: qué pasa y qué tan grave es.
export const STATUS = {
  urgente: { label: 'Urgente', title: 'Puede haber fuego muy cerca de tu lugar', text: URGENT_TEXT.satelite },
  aviso: { label: 'Calor cerca', title: 'Un satélite vio calor cerca', text: 'Puede ser un incendio o una quema. Revisa y mantente atento' },
  riesgo: { label: 'Día peligroso', title: 'Hoy el clima es peligroso para incendios', text: 'No se ve fuego cerca, pero hace calor, el aire está seco o hay viento' },
  tranquilo: { label: 'Tranquilo', title: 'No se ve fuego cerca', text: 'Los satélites no vieron calor en tu zona en los últimos 2 días' },
};

export const GUIDANCE = {
  urgente: ['Si la autoridad ordena evacuar, sal de inmediato por la ruta que indiquen. No esperes a ver las llamas.',
    'Si ves fuego o humo, llama al 130 (CONAF) o al 132 (Bomberos) y entrega la ubicación exacta.',
    'Ten a mano la mochila de emergencia, documentos, medicamentos y a tus mascotas. Avisa a tus vecinos y a tus familiares.',
    'No te acerques al foco ni bloquees caminos: los brigadistas y Bomberos los necesitan.'],
  aviso: ['Revisa las noticias oficiales (SENAPRED, CONAF y tu municipio). El calor que ve un satélite puede ser un incendio, pero también una quema o una industria.',
    'Revisa hacia dónde sopla el viento y ten lista la mochila y una ruta de salida.',
    'Si ves humo o llamas, llama al 130 o al 132.'],
  riesgo: ['Hoy no hagas quemas ni uses maquinaria que produzca chispas (esmeriles, soldadura, cortadoras) cerca de pasto seco.',
    'Revisa tu mochila de emergencia y tu ruta de evacuación.',
    'Si ves humo, avisa temprano: los primeros minutos son decisivos.'],
  tranquilo: ['Aprovecha para preparar tu casa: limpia techos y canaletas, poda y retira material seco alrededor.',
    'Conversa con tu familia por dónde saldrían y dónde se encontrarían.'],
};

let mounted = false;
let summaries = new Map();
let histories = new Map();
let meData = null;
let inboxData = [];
let temporadaData = null;
let lluvias = new Map();
let stations = new Map();
let aires = new Map();
let oficiales = new Map();
let staleShown = false;
let emActive = false;
/* MZ-06/MZ-07: `summariesAt` guarda la hora de la última consulta de resumen que salió
 * bien por lugar; `lastSummaryAt` la de la última tanda (buena o fallida). `turno` es el
 * contador de turno: un render, refresco o reintento viejo no pisa al nuevo. */
let turno = 0;
const summariesAt = new Map();
let lastSummaryAt = null;
const RESUMEN_BUENO_MS = 30 * 60000;
// soltar() de cada registrarToque (MAPA-157): el resolutor único reparte cada toque
// — el punto VIIRS gana sobre el cuadro GOES que lo contiene y un incendio CONAF
// sobre un foco (PRIORIDAD_TOQUE en capas.js).
let soltarToques = [];
const FOCO_CAPAS = ['detections', 'goes-pixels'];

/** Dónde anclar la ficha: en un punto, su coordenada exacta; en otra figura, el toque. */
const puntoDe = (feature, lngLat) => (feature?.geometry?.type === 'Point' ? feature.geometry.coordinates : lngLat);

/** Tocar un punto de calor en «Mi zona»: la misma ficha que en el Mapa; una celda
 * agrupada acerca hasta separar los focos, igual que allá. */
function onFoco(feature, lngLat) {
  const map = getMap();
  const props = feature?.properties;
  if (props?.count > 1) { map.easeTo({ center: lngLat, zoom: Math.min(map.getZoom() + 1.8, 10.5), duration: 600 }); return; }
  const obs = (store.get('observations') || []).find((o) => o.id === props?.id);
  if (obs) popupFoco(obs, puntoDe(feature, lngLat));
}

/* MZ-08: el contexto que ven las tarjetas, también sobre el mapa de la portada. */
let conafCerca = new Map(); // incendios CONAF no extinguidos cerca de los lugares (id → incendio)
let incidentes = [];        // incidentes de /api/incidents (el borde la cachea)
const ANILLO_STATUS = new Set(['posible', 'reportado', 'confirmado', 'controlado']);

/* Los incendios de CONAF cercanos (`summary.official` de cada lugar) van a la capa
 * `official` y los incidentes abiertos dentro de 2× el radio de algún lugar a
 * `incident-rings`. Se recalcula en cada pintado: un resumen nuevo puede cambiar
 * qué hay cerca. La leyenda solo se reescribe si cambia la lista de incendios. */
function contextoMapa() {
  const antes = [...conafCerca.keys()].join();
  conafCerca = new Map();
  for (const s of summaries.values()) {
    for (const f of s?.official || []) if (f.status !== 'extinguido') conafCerca.set(f.id, f);
  }
  setData('official', pointsGeoJSON([...conafCerca.values()], (f) => ({ id: f.id, status: f.status })));
  const places = store.get('places') || [];
  setData('incident-rings', pointsGeoJSON(
    incidentes.filter((i) => ANILLO_STATUS.has(i.status)
      && places.some((p) => haversineKm(p.lat, p.lon, i.lat, i.lon) <= p.radius_km * 2)),
    (i) => ({ id: i.id, status: i.status, n: i.n_obs })));
  if ([...conafCerca.keys()].join() !== antes) legend();
}

/** La lista de incidentes abiertos para los anillos; un fallo conserva lo último conocido. */
async function loadIncidentes() {
  try {
    const { incidents } = await api.incidents();
    if (!mounted) return;
    incidentes = incidents || [];
    contextoMapa();
  } catch { /* sin datos nuevos: los anillos quedan como estaban */ }
}

function onOficial(feature, lngLat) {
  const fire = conafCerca.get(feature?.properties?.id);
  if (fire) popupOficial(fire, puntoDe(feature, lngLat));
}

function onAnillo(feature) {
  const id = feature?.properties?.id;
  if (id) location.hash = `#/incendio/${id}`;
}

/* Tocar tu lugar lleva el panel a su tarjeta: la hoja baja a «half» si estaba en
 * «peek», la tarjeta se desplaza a la vista y se resalta un momento. El desplazamiento
 * usa el scroll suave de .panel-body, que ya se desactiva con movimiento reducido. */
function onLugar(feature) {
  const id = feature?.properties?.id;
  const card = id ? document.querySelector(`#view [data-place="${CSS.escape(id)}"]`) : null;
  if (!card) return;
  if (store.get('sheet') === 'peek') document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'half' }));
  card.scrollIntoView({ block: 'start' });
  card.classList.add('flash');
  setTimeout(() => card.classList.remove('flash'), 1800);
}
const STALE_MIN = 30;

/* OFI-30: temporada 2025-26 por comuna, una sola lectura por sesión (mismo patrón perezoso
   que exposure.js): promesa cacheada que nunca lanza; sin el archivo no se pinta nada. */
let panoramas = new Map();
let cambiosVisto = storage.get('zona:cambios:visto', null);
let temporadaPromise = null;
export function loadTemporada() {
  return (temporadaPromise ??= fetch('/web/data/temporada-2526.json')
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .catch(() => { temporadaPromise = null; return null; }));
}

// Primero en la lista cuando en el lugar vive alguien que necesita ayuda para salir.
export const OLDER_GUIDANCE = {
  urgente: 'Llama ahora a la persona mayor y confirma quién la ayuda a salir. Salgan temprano: no esperen a ver las llamas ni la orden de evacuar.',
  aviso: 'Llama a la persona mayor: que tenga a mano sus remedios, documentos y la mochila, y acuerden quién la ayuda a salir si hace falta.',
  riesgo: 'Hoy revisa con la persona mayor la mochila y sus remedios, y confirma quién la ayuda si hay que salir.',
  tranquilo: 'Acuerda con la persona mayor quién la ayuda a salir y anoten juntos el plan familiar.',
};
export const guidanceFor = (status, olderAdult) => (olderAdult ? [OLDER_GUIDANCE[status], ...GUIDANCE[status]] : GUIDANCE[status]);

/* Lectura en voz alta (UX-02, mismo patrón que web/js/lite.js): «Escuchar» solo se crea
   cuando hay speechSynthesis; un solo «leyendo» a la vez y la etiqueta pasa a «Detener». */
const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
let speakingBtn = null;

function setSpeaking(btn, on) {
  btn.classList.toggle('speaking', on);
  btn.textContent = on ? 'Detener' : 'Escuchar';
}

function stopSpeak() {
  if (speakingBtn) { setSpeaking(speakingBtn, false); speakingBtn = null; }
  synth?.cancel();
}

function speak(text, btn) {
  if (speakingBtn === btn) { stopSpeak(); return; }
  if (speakingBtn) setSpeaking(speakingBtn, false);
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'es-CL';
  const voices = synth.getVoices?.() || [];
  u.voice = voices.find((v) => v.lang === 'es-CL')
    || voices.find((v) => v.lang === 'es-419')
    || voices.find((v) => (v.lang || '').toLowerCase().startsWith('es'))
    || null;
  speakingBtn = btn;
  setSpeaking(btn, true);
  u.onend = u.onerror = () => {
    if (speakingBtn === btn) { speakingBtn = null; setSpeaking(btn, false); }
  };
  synth.speak(u);
}

// El texto de «urgente» según la causa del resumen; sin causa (resúmenes antiguos) queda el del satélite.
export function statusText(status, cause = {}) {
  if (status !== 'urgente') return STATUS[status].text;
  if (cause.conaf && cause.satelite) return URGENT_TEXT.ambos;
  if (cause.conaf) return URGENT_TEXT.conaf;
  if (cause.persona_mayor) return URGENT_TEXT.persona_mayor;
  return URGENT_TEXT.satelite;
}

/* Modo emergencia: con un lugar en «urgente», la pantalla deja el análisis y responde solo lo esencial.
 * ¿Qué tan cerca está?, ¿qué dijo la autoridad?, qué hacer ahora y a quién llamar. Se puede volver a la vista completa. */
const EM_KEY = 'em-dismissed';
const emKey = (urgent) => urgent.map(([p, s]) => `${p.id}:${s.nearby?.find((o) => o.inside_radius && o.reliable)?.id || ''}:${s.official?.[0]?.id || ''}`).join('|');
const emDismissed = (key) => { try { return sessionStorage.getItem(EM_KEY) === key; } catch { return false; } };

/** Lo que informa la autoridad (CONAF) sobre un incendio cercano; lo usan el modo emergencia y el modo vecino.
 *  OFI-04: el botón a SENAPRED nombra la comuna cuando se conoce; BRASA no afirma si hay o no alerta vigente. */
export function officialBlock(official, source, comuna) {
  return html`<div class="em-official"><b>¿Qué dijo la autoridad?</b>
    ${official ? html`<span><b>CONAF:</b> incendio «${official.name || 'sin nombre'}», ${(official.status_raw || 'informado').toLowerCase()}, desde las ${fmtTime(official.started_at)} (${ago(official.started_at)}).</span>` : ''}
    ${official && source ? html`<span class="tiny">Fuente: <a href="${source.url}" target="_blank" rel="noopener">${source.name}</a>.</span>` : ''}
    <span>Las órdenes de evacuación las da SENAPRED: llegan como mensaje de emergencia al celular, por radio y en su sitio. BRASA no las reemplaza.</span>
    <a class="btn btn-sm btn-block" href="https://senapred.cl/alertas/" target="_blank" rel="noopener">Consulta la alerta oficial vigente${comuna ? ` para ${comuna}` : ''} en SENAPRED ↗</a></div>`;
}

function emergencyView(urgent) {
  const [place, summary] = urgent[0];
  const near = summary.nearby.filter((o) => o.inside_radius && o.reliable);
  const n = near[0];
  const latest = near.map((o) => o.observed_at).sort().pop();
  const ww = windWords(summary.wind?.direction);
  const upwind = near.some((o) => o.upwind);
  const official = (summary.official || []).find((f) => f.inside_radius && f.status !== 'extinguido');
  return html`<section class="emergency" aria-labelledby="em-title">
    <div class="em-head"><span class="status-badge st-urgente">Urgente</span><span class="small">${latest ? `último calor ${ago(latest)}` : ''}</span></div>
    <h1 class="em-title" id="em-title">${official ? `CONAF informa un incendio a ${fmtNum(official.distance_km, official.distance_km < 3 ? 1 : 0)} km de «${place.name}»`
      : n ? `Posible fuego a ${fmtNum(n.distance_km, n.distance_km < 3 ? 1 : 0)} km de «${place.name}»` : `Calor cerca de «${place.name}»`}</h1>
    <p class="em-sub">${official ? `Hacia el ${cardWord(official.direction)}.` : n ? `Hacia el ${cardWord(n.direction)}.` : ''} ${upwind && ww ? `El viento va hacia tu lugar (${fmtNum(summary.wind.speed)} km/h).` : ''}
      ${urgent.length > 1 ? `También hay calor cerca de ${urgent.length - 1 === 1 ? 'otro de tus lugares' : `otros ${urgent.length - 1} de tus lugares`}.` : ''}</p>
    <div class="em-calls"><a class="btn btn-call btn-lg" href="tel:132">Bomberos · 132</a><a class="btn btn-lg" href="tel:130">CONAF · 130</a></div>
    ${officialBlock(official, summary.official_source, place.comuna?.name)}
    <ol class="steps em-steps">
      ${place.older_adult ? html`<li><b>Llama ahora a la persona mayor</b> y confirma quién la ayuda a salir. Salgan temprano, sin esperar a ver las llamas.</li>` : ''}
      <li><b>Si ordenan evacuar, sal ya</b> por la ruta que indiquen. Si la instrucción es salir a pie, sal a pie. No esperes a ver las llamas.</li>
      <li><b>Prepárate para salir ahora:</b> mochila, remedios, documentos y tus mascotas. No las dejes amarradas ni encerradas.</li>
      <li><b>Avisa por mensaje de texto o WhatsApp</b>, no con llamadas largas: las líneas se saturan. Si ves fuego o humo, llama al 132.</li>
      <li><b>No regreses</b> aunque ya no veas llamas: espera a que la autoridad lo permita.</li>
    </ol>
    <div class="btn-row">${n?.incident_id ? html`<a class="btn" href="#/incendio/${n.incident_id}">Qué han visto los satélites</a>` : ''}
      ${synth ? html`<button class="btn btn-speak" id="em-listen" type="button" aria-label="Escuchar qué pasa y qué hacer">Escuchar</button>` : ''}
      <button class="btn btn-ghost" id="em-full">Ver todo (mapa, clima y detalles)</button></div>
    <p class="tiny muted">BRASA es un proyecto ciudadano y no es una alerta oficial. Un satélite vio calor dentro de tu zona de aviso; puede ser un incendio, una quema o una industria.</p>
  </section>`;
}

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Puntos de calor vistos por satélite</div>
    <div class="legend-row"><span class="legend-item"><span class="sw" style="background:#3987e5"></span>Tu lugar y zona de aviso</span>
    ${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}
    ${conafCerca.size ? html`<span class="legend-item"><span class="sw sw-ring"></span>${dual('Incendio que informa CONAF', 'Incendio CONAF (oficial)')}</span>` : ''}</div>
    <div class="legend-note">${dual('Más rojo = más reciente. Los cuadros marcan una zona de unos 2 km donde hay calor. Tócalos para ver su detalle.', 'Cuadros: píxeles GOES ABI (~2–3 km). Puntos: VIIRS (375 m) y MODIS (1 km). Toque abre la ficha del punto.')}</div>
    <div class="legend-note esencial">Calor no siempre es incendio. Toca un punto para ver su detalle.</div>`);
}

export function dayStrip(days) {
  if (!days?.length) return html`<p class="tiny muted" style="margin-top:8px">El pronóstico de los próximos días aparecerá pronto.</p>`;
  return html`<div class="day-strip" aria-label="Peligro de incendio por el clima, próximos 7 días">${days.slice(0, 7).map((d) => html`
    <button type="button" class="day-cell" data-daytip="${fmtDay(d.date)}: peligro ${(RISK[d.level]?.label || 'sin dato').toLowerCase()}. ${RISK[d.level]?.plain || ''} Hasta ${fmtNum(d.tmax)} °C, humedad ${fmtNum(d.rhmin)} %, viento ${fmtNum(d.windmax)} km/h.${d.boton_rojo_hours ? ' CONAF pronostica Botón Rojo: condiciones favorables para incendios (no significa que haya fuego).' : ''}">
      <b>${fmtDay(d.date, { weekday: 'short', day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, day: 'numeric', month: undefined })}
      <i class="${RISK[d.level]?.cls || ''}"></i>${d.boton_rojo_hours ? html`<em class="br-mark" aria-hidden="true">${dual(html`<span class="br-dot"></span>CONAF`, 'BR')}</em>` : ''}<span class="sr-only">Peligro ${(RISK[d.level]?.label || 'sin dato').toLowerCase()}${d.boton_rojo_hours ? '. CONAF pronostica Botón Rojo: condiciones favorables para incendios, no significa que haya fuego' : ''}</span></button>`)}</div>`;
}

/** Radar y datos clave de un lugar (los usa la tarjeta propia y la vista compartida con la familia). */
export function placeBody(place, summary) {
  const near = summary?.nearby?.filter((o) => o.inside_radius && o.reliable) || [];
  const nearest = near[0] || summary?.nearby?.[0];
  const today = summary?.risk_days?.[0];
  const wind = summary?.wind;
  const dmc = summary?.dmc_alerts || [];
  const ww = windWords(wind?.direction);
  return html`<div class="place-body">
      <figure class="radar-wrap">${radarSvg({ radiusKm: place.radius_km, nearby: summary?.nearby || [], wind })}
        <figcaption class="tiny">${dual(`Anillo: ${fmtNum(place.radius_km)} km`, `Anillos ${fmtNum(place.radius_km)} y ${fmtNum(place.radius_km * 2)} km`)}</figcaption></figure>
      <ul class="place-facts">
        <li>${nearest
          ? html`<b>${near.length ? `${near.length === 1 ? 'Un punto' : `${near.length} puntos`} de calor` : 'Calor'}</b> ${dual(`a ${fmtNum(nearest.distance_km, nearest.distance_km < 3 ? 1 : 0)} km, hacia el ${cardWord(nearest.direction)}`, `más cercano a ${fmtNum(nearest.distance_km, 1)} km, rumbo ${nearest.bearing_deg}° (${nearest.direction}) · ${nearest.satellite || nearest.sensor}`)}<span class="muted"> · ${ago(nearest.observed_at)}</span>`
          : summary?.data_as_of
          ? html`<b>Sin calor</b> a menos de ${fmtNum(place.radius_km * 2)} km <span class="muted">en 2 días</span>`
          : html`<b>Sin hora de actualización</b> <span class="muted">· no se sabe si hubo calor cerca en 2 días</span>`}</li>
        ${wind?.speed != null ? html`<li><b>Viento ${fmtNum(wind.speed)} km/h</b> ${ww ? dual(`viene del ${ww.from} y va hacia el ${ww.to} (flecha azul)`, `${windFrom(wind.direction)} (${Math.round(wind.direction)}°)${wind.gust ? ` · ráfagas ${fmtNum(wind.gust)} km/h` : ''}`) : ''}</li>` : ''}
        ${today ? html`<li>Clima de hoy: ${riskChip(today.level)}</li>` : ''}
        ${dmc.length ? html`<li><b>${[...new Set(dmc.map((a) => a.label))].join(' y ')}</b> de la DMC ${dual(`hasta ${fmtDateTime(dmc[0].expires)}`, `${dmc[0].event} · severidad ${dmc[0].severity} · vence ${fmtDateTime(dmc[0].expires)}`)}</li>` : ''}
      </ul>
    </div>`;
}

/** «Qué pasó cerca estos días» (UX-17): contexto, no alarma. Se pliega y, sin incidentes, ni aparece. */
function historyBlock(history) {
  const items = history?.incidents || [];
  if (!items.length) return '';
  return html`<details class="fold"><summary>${dual(`Los últimos ${history.days} días cerca de este lugar`,
    `Incidentes a menos de 2× el radio, últimos ${history.days} días (sin fuentes de calor fijas)`)}</summary>
    <ul class="list">${items.map((h) => {
      const info = INCIDENT[h.status] || INCIDENT.anomalia;
      return html`<li><a class="row-btn" href="#/incendio/${h.id}"><span class="status-badge st-${info.tone}">${info.short}</span>
        <span class="grow small">${dual(`a ${fmtNum(h.distance_km, h.distance_km < 3 ? 1 : 0)} km${h.comuna ? `, ${h.comuna}` : ''} · ${ago(h.last_seen_at)}`,
          `${fmtNum(h.distance_km, 1)} km · ${h.n_obs === 1 ? '1 detección' : `${h.n_obs} detecciones`} · ${fmtDateTime(h.last_seen_at)}`)}</span></a></li>`;
    })}</ul></details>`;
}

/* RISK-05: el 30-30-30 calculado en el punto exacto del lugar (no el del centro de la comuna).
   Solo en la tarjeta de Mi zona: el modo vecino usa placeBody directamente, no esta tarjeta. */
function riskPointLine(point) {
  if (!point?.level) return '';
  return html`<p class="tiny muted" style="margin-top:8px">En tu punto exacto: ${riskChip(point.level)} — ${point.reasons?.[0] || ''}</p>`;
}

/* OFI-30/VEC-02: lo que informó CONAF de la temporada pasada en la comuna del lugar.
 * Contexto, no pronóstico: sin fila ni `source` no se pinta nada (nunca un cero inventado). */
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const mesPalabras = (ym) => MESES[Number((ym || '').split('-')[1]) - 1] || null;
function seasonBlock(place, temporada) {
  const row = temporada?.comunas?.find((c) => Number(c.code) === Number(place.comuna?.code));
  if (!row || !temporada.source) return '';
  const mes = mesPalabras(row.mes_peak);
  const simple = row.incendios === 0
    ? 'CONAF no informó incendios en tu comuna esa temporada.'
    : `Entre septiembre de 2025 y mayo de 2026 CONAF informó ${fmtNum(row.incendios)} ${row.incendios === 1 ? 'incendio' : 'incendios'} en tu comuna; quemaron ${fmtNum(row.hectareas, 1)} ha.${mes ? ` El mes con más superficie fue ${mes}` : ''}${row.max_ha ? ` y el mayor incendio llegó a ${fmtNum(row.max_ha, 1)} ha` : ''}.`;
  return html`<details class="fold"><summary>La temporada pasada en tu comuna</summary><div>
    <p class="small">${dual(simple, `temporada ${temporada.temporada || '—'} · ${row.name} (${row.code}) · ${fmtNum(row.incendios)} incendios · ${fmtNum(row.hectareas, 1)} ha`)}</p>
    <p class="tiny muted">Fuente: <a href="${temporada.source}" target="_blank" rel="noopener">CONAF, reporte público de incendios (GEPRIF)</a>${temporada.fetched_at ? ` · datos al ${fmtDateTime(temporada.fetched_at)}` : ''}. Dato histórico; no es el pronóstico de hoy.</p></div></details>`;
}

/* «La semana»: los últimos siete días del lugar, en una frase y una barra por día.
   Con datos viejos no se puede decir «no hubo calor»: la frase lo advierte en vez de afirmar calma. */
function weekBlock(week) {
  if (!week?.days?.length) return '';
  const days = week.days;
  const max = Math.max(1, ...days.map((d) => d.n));
  const chileYmd = (iso) => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(parseUTC(iso));
  const withHeat = days.filter((d) => d.n > 0).length;
  const emptyLabel = week.enough_data ? 'sin calor confiable' : 'sin datos';
  const nearest = week.nearest_km == null ? ''
    : `el más cercano a ${fmtNum(week.nearest_km, week.nearest_km < 3 ? 1 : 0)} km${week.nearest_at ? `, el ${fmtDay(chileYmd(week.nearest_at), { weekday: 'long', day: undefined, month: undefined })}` : ''}`;
  const sentence = !week.enough_data ? 'sin datos suficientes para la semana'
    : !withHeat ? 'ningún día con calor confiable cerca'
    : `${withHeat === 1 ? 'un día' : `${withHeat} días`} con calor cerca${nearest ? `; ${nearest}` : ''}`;
  return html`<div style="margin-top:12px">
    <p class="tiny"><b>La semana</b> · ${sentence}.</p>
    <div class="day-strip" style="margin-top:6px">${days.map((d) => html`<span class="day-cell" role="img"
      aria-label="${fmtDay(d.date, { weekday: 'long', day: 'numeric', month: 'long' })}: ${d.n === 0 ? emptyLabel : d.n === 1 ? '1 detección de calor' : `${d.n} detecciones de calor`}">
      <i aria-hidden="true" style="--h:${d.n ? Math.max(12, Math.round((d.n / max) * 100)) : 0}%;--rc:var(--accent)"></i>
      <b aria-hidden="true">${fmtDay(d.date, { weekday: 'short', day: undefined, month: undefined })}</b>
      <span aria-hidden="true">${fmtDay(d.date, { weekday: undefined, day: 'numeric', month: undefined })}</span></span>`)}</div>
  </div>`;
}

/* MZ-03: «¿Por qué hoy es peligroso?» en una frase, sin tocar el data-daytip.
 * No inventa valores faltantes; sin day o sin level devuelve ''. */
export function whyDangerous(day) {
  if (!day?.level) return '';
  const partes = [];
  if (day.tmax != null) partes.push(`hasta ${fmtNum(day.tmax)} °C`);
  if (day.rhmin != null) partes.push(`humedad ${fmtNum(day.rhmin)} %`);
  if (day.windmax != null) partes.push(`viento de ${fmtNum(day.windmax)} km/h`);
  let txt = partes.length
    ? `Hoy: ${partes.slice(0, -1).join(', ')}${partes.length > 1 ? ' y ' : ''}${partes[partes.length - 1]}. El aire seco y el viento hacen que un fuego crezca rápido.`
    : '';
  if (day.boton_rojo_hours > 0) {
    txt += `${txt ? ' ' : ''}CONAF pronostica Botón Rojo: condiciones favorables para incendios, no significa que haya fuego.`;
  }
  return txt;
}

function whyLine(day) {
  const txt = whyDangerous(day);
  const at = store.get('status')?.risk_computed_at;
  if (!txt && !at) return '';
  return html`<p class="small" style="margin-top:8px">${txt}${at ? html` <span class="tiny muted">Pronóstico calculado ${ago(at)}.</span>` : ''}</p>`;
}

/* RISK-22: «¿Y la semana pasada?» en una frase de pronóstico (nunca «hubo» ni «habrá»).
 * '' sin filas o con todas en sin_anterior: no se inventa comparación. */
export function weekLine(trend) {
  const rows = trend?.rows || [];
  if (!rows.length || rows.every((r) => r.change === 'sin_anterior')) return '';
  const s = trend.summary || {};
  const partes = [];
  if (s.sube) partes.push(`subió en ${fmtNum(s.sube)} ${s.sube === 1 ? 'día' : 'días'}`);
  if (s.baja) partes.push(`bajó en ${fmtNum(s.baja)} ${s.baja === 1 ? 'día' : 'días'}`);
  if (!partes.length) return 'El pronóstico de tu comuna se mantiene igual que hace una semana.';
  return `El pronóstico de tu comuna para los próximos días ${partes.join(' y ')} respecto de hace una semana.`;
}

function trendFold(trend, place) {
  if (!place.comuna) return '';
  const line = weekLine(trend);
  if (!line) return '';
  return html`<details class="fold"><summary>¿Y la semana pasada?</summary><div>
    <p class="small">${line}</p>${trend?.method ? html`<p class="tiny muted">${trend.method}</p>` : ''}</div></details>`;
}

/* TEMP-03: «Tu comuna esta temporada» lee `comuna_detail` de /api/panorama?comuna=<code>,
 * que responde aunque la comuna no entre al top 12 del panorama general. */
function panoramaLine(place, panorama) {
  const d = panorama?.comuna_detail;
  if (!d) return '';
  const c = d.current || {};
  const line = c.n
    ? `CONAF informó ${fmtNum(c.n)} ${c.n === 1 ? 'incendio' : 'incendios'} en tu comuna esta temporada (${fmtNum(c.ha, 1)} ha)`
    : 'CONAF todavía no informa incendios en tu comuna esta temporada';
  const prev = d.previous;
  return html`<p class="tiny muted" style="margin-top:8px">${line}${d.boton_rojo_days ? ` · ${fmtNum(d.boton_rojo_days)} ${d.boton_rojo_days === 1 ? 'día' : 'días'} de Botón Rojo` : ''}${prev ? ` · la temporada anterior: ${fmtNum(prev.n)} (${fmtNum(prev.ha, 1)} ha)` : ''}. (cifras de CONAF). <a href="#/temporada">Ver el panorama completo →</a></p>`;
}

/* UX-62: «Qué hacer hoy» según el nivel del día, cada acción con su fuente. */
function prevencionLine(today, calor) {
  const resumen = resumenHoy(today?.level, { calor });
  if (!resumen) return '';
  const resto = accionesHoy(today.level, { calor }).slice(1);
  return html`<p class="small" style="margin-top:8px"><b>${resumen}</b></p>
    ${resto.length ? html`<details class="fold"><summary>Qué más puedes hacer hoy</summary><ul class="list">
      ${resto.map((a) => html`<li><span class="grow small">${a.text} <a class="tiny muted" href="${a.url}" target="_blank" rel="noopener">${a.source} ↗</a></span></li>`)}</ul></details>` : ''}`;
}

/* AGUA-09: la lluvia prevista y la isoterma 0 °C del lugar, como dato del pronóstico.
 * Es la señal ya calculada en el servidor: se muestra con su fuente, nunca como
 * aviso de aluvión, y solo cuando hay lluvia prevista que contar. */
export function lluviaLine(data) {
  const s = data?.senal;
  if (!s || !Number.isFinite(s.mm_3h) || s.mm_3h <= 0) return '';
  const cuando = s.ventana ? ` el ${fmtDateTime(s.ventana)}` : '';
  const iso = s.isoterma_m != null ? ` La isoterma 0 °C está a ${fmtNum(s.isoterma_m)} m.` : '';
  return html`<p class="tiny muted" style="margin-top:8px">${s.intensa
    ? html`<b>Lluvia intensa prevista:</b>` : html`Lluvia prevista:`}
    hasta ${fmtNum(s.mm_3h, 1)} mm en 3 horas${cuando}.${iso}
    Es un dato del pronóstico, no un aviso de aluvión: BRASA no emite avisos de aluvión.
    Fuente: ${data.source || 'Open-Meteo'}.</p>`;
}

/* OFI-33: lo que midió de verdad la estación automática de la DMC más cercana (≤25 km y
 * de las últimas 3 horas; el servidor filtra lo demás). Es una medición, no un pronóstico:
 * sin dato no se pinta nada. */
export function stationLine(data) {
  const s = data?.station;
  if (!s || !s.observed_at) return '';
  const partes = [];
  if (s.temperature_c != null) partes.push(`${fmtNum(s.temperature_c, 1)} °C`);
  if (s.humidity != null) partes.push(`humedad ${fmtNum(s.humidity)} %`);
  if (s.wind_kmh != null) partes.push(`viento ${fmtNum(s.wind_kmh)} km/h${s.wind_deg != null ? ` ${windFrom(s.wind_deg)}` : ''}`);
  if (!partes.length) return '';
  return html`<p class="tiny muted" style="margin-top:8px"><b>Medido en la estación ${s.name}</b> (a ${fmtNum(s.distance_km, 1)} km): ${partes.join(', ')} a las ${fmtTime(s.observed_at)} (${ago(s.observed_at)}). Fuente: ${data.source || 'DMC'} — medición real, no un pronóstico.</p>`;
}

/* OFI-10: el MP2,5 medido por la estación SINCA más cercana (≤60 km y de las últimas 6 h;
 * el servidor filtra lo demás). Es una medición preliminar del MMA junto al pronóstico
 * de humo: sin dato no se pinta nada. */
export function airLine(data) {
  const a = data?.air;
  if (!a || a.pm25 == null || !a.observed_at) return '';
  const icap = typeof a.icap === 'number' ? ` — ICAP ${fmtNum(a.icap)}${a.status ? ` (${a.status})` : ''}` : (a.status ? ` — ${a.status}` : '');
  return html`<p class="tiny muted" style="margin-top:8px"><b>Aire medido en la estación ${a.name}</b> (${a.comuna || 'SINCA'}, a ${fmtNum(a.distance_km, 1)} km): MP2,5 ${fmtNum(a.pm25, 1)} µg/m³${icap}, medido a las ${fmtTime(a.observed_at)} (${ago(a.observed_at)}). Fuente: <a class="tiny muted" href="https://sinca.mma.gob.cl/" target="_blank" rel="noopener">SINCA ↗</a> — medición preliminar del MMA, no un pronóstico.</p>`;
}

/* OFI-04: «La autoridad informa» — las alertas vigentes de SENAPRED que nombran a la
 * comuna o a la región del lugar, con su texto oficial, su fecha y su enlace. BRASA no
 * emite alertas: vacío no significa «todo tranquilo», solo que SENAPRED no te nombró. */
export function autoridadBlock(data) {
  const lista = data?.alerts;
  if (!lista?.length) return '';
  return html`<div class="place-body" style="margin-top:8px"><b class="small">La autoridad informa:</b>
    <ul class="list">${lista.map((a) => html`<li><a href="${a.url}" target="_blank" rel="noopener">${a.title} ↗</a> <span class="tiny muted">${a.scope === 'comuna' ? 'tu comuna' : 'tu región'}${a.issued_at ? ` · ${ago(a.issued_at)}` : ''}</span></li>`)}</ul>
    <p class="tiny muted">Texto oficial de SENAPRED — BRASA no emite alertas.</p></div>`;
}

export function placeCard(place, summary, history, temporada, trend, panorama, lluvia, station, air, oficial, revisado) {
  const failed = !summary || summary.error;
  const status = failed ? 'sindatos' : summary.status;
  const botonRojo = place.comuna && summary?.risk_days?.some((d) => d.boton_rojo_hours);
  /* MZ-09: lo esencial («¿hay fuego cerca y qué hago?») queda a la vista; el contexto
   * va cerrado bajo «Más sobre este lugar» y las acciones secundarias bajo «Más
   * acciones». Ningún dato ni botón se pierde: solo cambia el orden y lo que se ve
   * sin desplegar. En «urgente» «La autoridad informa» y «Qué hago» quedan arriba. */
  // MZ-09: el contexto va al pliegue, pero historial, calendario y temporada
  // siguen existiendo aunque la consulta falle (venian de otros endpoints).
  const detalle = [
    ...(failed ? [] : [
      riskPointLine(summary.risk_point),
      whyLine(summary.risk_days?.[0]),
      weekBlock(summary.week),
      prevencionLine(summary.risk_days?.[0], (summary.dmc_alerts || []).some((a) => /calor/i.test(a.event || a.label || ''))),
      trendFold(summary.trend, place),
      panoramaLine(place, panorama),
      lluviaLine(lluvia),
      stationLine(station),
      airLine(air),
    ]),
    historyBlock(history),
    summary?.risk_days?.some((d) => d.boton_rojo_hours)
      ? html`<div class="btn-row"><button class="btn btn-sm" data-act="ics">Añadir los días de Botón Rojo al calendario</button></div>` : '',
    seasonBlock(place, temporada),
  ].map(String).join('');
  return html`<article class="card place-card st-border-${status}" data-place="${place.id}">
    <div class="card-head">
      <div class="place-title"><i class="px" aria-hidden="true"></i><div style="min-width:0"><div class="card-title">${place.name}</div>
        <div class="card-sub">${place.comuna ? place.comuna.name : 'Fuera de una comuna conocida'} · aviso a ${fmtNum(place.radius_km)} km</div>
        ${revisado ? html`<div class="tiny muted" style="margin-top:2px">Revisado ${ago(revisado)}</div>` : ''}
        ${place.older_adult || place.shared ? html`<div class="badges" style="margin-top:6px">${place.older_adult ? html`<span class="tag tag-older">Persona mayor · aviso anticipado</span>` : ''}${place.shared ? html`<span class="tag tag-live">Compartido con la familia</span>` : ''}</div>` : ''}</div></div>
      <span class="status-badge st-${status}">${failed ? 'Sin datos' : STATUS[status].label}</span>
    </div>
    ${failed
      ? html`<div class="place-body" role="status">
        <p><b>No pudimos consultar este lugar ahora.</b> Que falle la consulta no significa que no haya fuego cerca: si ves humo o llamas, llama al 130 o al 132.</p>
        <div class="btn-row"><button class="btn btn-sm btn-primary" data-act="reintentar">Reintentar</button></div>
        ${phonesHtml()}</div>`
      : html`${placeBody(place, summary)}${dayStrip(summary.risk_days)}${autoridadBlock(oficial)}`}
    <div class="card-actions">
      <button class="btn btn-sm ${status === 'tranquilo' ? '' : 'btn-primary'}" data-act="que-hacer">Qué hago</button>
      <button class="btn btn-sm" data-act="ver">Ver en el mapa</button>
      <button class="btn btn-sm" data-act="compartir">${place.shared ? 'Enlace para la familia' : 'Compartir con la familia'}</button>
    </div>
    ${detalle ? html`<details class="fold"><summary>Más sobre este lugar</summary><div>${raw(detalle)}</div></details>` : ''}
    <details class="fold"><summary>Más acciones</summary><div>
      <div class="card-actions">
        <button class="btn btn-sm" data-act="servicios">Dónde reunirse</button>
        <button class="btn btn-sm btn-ghost" data-act="editar">Editar</button>
        <button class="btn btn-sm btn-danger" data-act="borrar" aria-label="Eliminar ${place.name}">Eliminar</button>
        ${botonRojo ? html`<a class="btn btn-sm btn-ghost" href="/api/calendar/boton-rojo/${place.comuna.code}.ics"
          title="Agregar los días de Botón Rojo de ${place.comuna.name} a tu calendario"
          aria-label="Agregar los días de Botón Rojo de ${place.comuna.name} a tu calendario">Calendario</a>` : ''}
      </div>
      ${botonRojo ? html`<p class="tiny muted" style="margin-top:6px">Archivo de calendario: se actualiza solo si lo suscribes.</p>` : ''}
    </div></details>
  </article>`;
}

function guidanceModal(status, place, failed = false) {
  const steps = guidanceFor(status, place.older_adult);
  // Con la consulta fallida la guía general sigue sirviendo, pero el título no puede afirmar calma.
  const title = failed ? 'No pudimos consultar este lugar' : STATUS[status].title;
  const dlg = openModal(html`<h2 id="modal-title">${title}</h2>
    <p class="muted small">${place.name}${place.comuna ? ` · ${place.comuna.name}` : ''}</p>
    ${failed ? html`<p class="small"><b>La consulta falló:</b> no sabemos si hay calor cerca ni cómo viene el clima. Reintenta desde la tarjeta; ante humo o llamas, llama al 132.</p>` : ''}
    <ol class="steps">${steps.map((g) => html`<li>${g}</li>`)}</ol>
    ${phonesHtml()}
    ${synth ? html`<div class="btn-row" style="margin-top:10px"><button class="btn btn-speak" id="gm-listen" type="button" aria-label="Escuchar los pasos de qué hacer">Escuchar</button></div>` : ''}
    <p class="tiny muted" style="margin-top:12px">Recomendaciones generales. Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen.</p>`, (body) => {
    body.querySelector('#gm-listen')?.addEventListener('click', () => speak(
      `${title}. ${steps.join(' ')} Recomendaciones generales: las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen.`,
      body.querySelector('#gm-listen')));
  });
  dlg.addEventListener('close', stopSpeak, { once: true }); // si el modal se cierra leyendo, la voz no queda huérfana
}

/** Modo vecino: un enlace de solo lectura para que la familia vea este lugar (y active sus propios avisos). */
async function shareModal(place) {
  let token;
  try { ({ token } = await api.sharePlace(place.id)); } catch (err) { toast(err.message, 'error'); return; }
  const url = `${location.origin}/#/v/${token}`;
  const text = `Mira cómo está «${place.name}» frente a incendios, en BRASA: ${url}`;
  openModal(html`<h2 id="modal-title">Compartir «${place.name}» con la familia</h2>
    <p class="small">Quien tenga este enlace verá el estado de este lugar: si hay calor cerca, el viento y el peligro de los próximos días. <b>No necesita cuenta</b> y puede activar sus propios avisos para este lugar.</p>
    <div class="share-url"><input class="input" id="share-url" readonly value="${url}" aria-label="Enlace para compartir" /></div>
    <div class="btn-row" style="margin-top:10px">
      <a class="btn btn-primary" href="https://wa.me/?text=${encodeURIComponent(text)}" target="_blank" rel="noopener">Enviar por WhatsApp</a>
      <button class="btn" id="share-copy">Copiar enlace</button>
      ${navigator.share ? html`<button class="btn" id="share-native">Más opciones</button>` : ''}
    </div>
    <p class="tiny muted" style="margin-top:12px">Compártelo solo con personas de confianza: muestra dónde está el lugar${place.older_adult ? ' <b>y que ahí vive alguien que necesita ayuda para salir</b>' : ''}.</p>
    <div class="btn-row"><button class="btn btn-sm btn-danger" id="share-stop">Dejar de compartir</button></div>`, (body) => {
    body.querySelector('#share-copy').addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(url); toast('Enlace copiado.'); } catch { body.querySelector('#share-url').select(); toast('Selecciona el enlace y cópialo.'); }
    });
    body.querySelector('#share-native')?.addEventListener('click', () => navigator.share({ title: `BRASA · ${place.name}`, text, url }).catch(() => {}));
    body.querySelector('#share-stop').addEventListener('click', async () => {
      try {
        await api.unsharePlace(place.id);
        closeModal(); toast('Listo: el enlace ya no funciona.');
        document.dispatchEvent(new CustomEvent('brasa:places-changed'));
      } catch (err) { toast(err.message, 'error'); }
    });
  });
  if (!place.shared) document.dispatchEvent(new CustomEvent('brasa:places-changed'));
}

async function showServices(place) {
  try {
    const data = await api.nearbyServices(place.lat, place.lon);
    setData('services', pointsGeoJSON(data.items, (i) => ({ kind: i.kind, name: i.name })));
    show('services', true);
    fly(place.lon, place.lat, 12);
    const groups = data.items.slice(0, 12);
    openModal(html`<h2 id="modal-title">Dónde reunirse cerca de ${place.name}</h2>
      <p class="muted small">${data.note}</p>
      ${groups.length ? html`<ul class="list">${groups.map((i) => html`<li><span class="dot" style="background:${i.kind === 'assembly_point' ? '#0ca30c' : i.kind === 'hospital' ? '#e34948' : i.kind === 'fire_station' ? '#eb6834' : '#3987e5'}"></span>
        <div class="grow"><b>${i.name}</b><div class="tiny muted">${i.kind_label}</div></div><span class="small nowrap">${fmtNum(i.distance_km, 1)} km ${i.direction}</span></li>`)}</ul>`
        : html`<div class="empty"><div class="glyph">⌖</div>No hay puntos registrados en OpenStreetMap cerca de aquí. Consulta a tu municipio.</div>`}
      <p class="tiny muted">Fuente: ${data.source}. Antes de una emergencia, confirma con tu municipio cuál es tu punto de encuentro oficial.</p>`);
  } catch (err) { toast(err.message, 'error'); }
}

/* MZ-06: aplica el resultado de una consulta de resumen. Un resultado bueno se guarda con
 * su hora; un fallo conserva el último resumen bueno de menos de 30 min (un fallo
 * transitorio no borra lo que ya se sabía ni pinta «sin datos») — pasado ese plazo se
 * muestra el estado de falla de siempre (FIX-51): nunca como «tranquilo». */
function applySummary(place, result, ahora = Date.now()) {
  if (result && !result.error) {
    summaries.set(place.id, result);
    summariesAt.set(place.id, new Date(ahora).toISOString());
    return;
  }
  const bueno = summariesAt.get(place.id);
  if (bueno && ahora - Date.parse(bueno) < RESUMEN_BUENO_MS && summaries.get(place.id)) return;
  summaries.set(place.id, { error: true });
  summariesAt.delete(place.id);
}

/* MZ-06: vuelve a pedir SOLO el resumen de cada lugar (nunca historial, panorama, lluvia,
 * estación, aire ni alertas oficiales) y repinta sin perder la posición del panel. El modo
 * emergencia se reevalúa solo: paint() ya decide. `mine` congela el turno para que un
 * render nuevo gane sobre un refresco viejo. */
async function refreshSummaries(container) {
  const places = store.get('places') || [];
  if (!places.length) return;
  const mine = turno;
  lastSummaryAt = new Date().toISOString();
  const results = await Promise.all(places.map((p) => api.placeSummary(p.id).catch(() => ({ error: true }))));
  if (!mounted || mine !== turno) return;
  const ahora = Date.now();
  places.forEach((p, i) => applySummary(p, results[i], ahora));
  keepPlace(container, () => paint(container));
  loadIncidentes(); // los anillos de MZ-08 siguen el mismo turno de refresco
}

function maybeRefresh(container, motivo) {
  if (!debeRefrescar({ ultimo: lastSummaryAt, ahora: Date.now(), visible: document.visibilityState === 'visible', motivo })) return;
  refreshSummaries(container);
}

/* Reintenta solo el resumen del lugar que falló (FIX-51): no vuelve a pedir me, avisos,
   historiales ni los demás lugares; repinta con lo que ya está en memoria. */
async function retrySummary(container, place, btn) {
  btn.disabled = true;
  btn.textContent = 'Consultando…';
  const mine = turno;
  const summary = await api.placeSummary(place.id).catch(() => ({ error: true }));
  if (!mounted || mine !== turno) return;
  lastSummaryAt = new Date().toISOString();
  applySummary(place, summary);
  if (summary.error) toast('Sigue sin poder consultar este lugar.', 'error');
  keepPlace(container, () => paint(container));
}

/* MZ-07: la vista se pinta por etapas. Primera: resúmenes + me + avisos → héroe, estado
 * de cada tarjeta y, si corresponde, modo emergencia. Segunda: historial, temporada,
 * panorama, lluvia, estación, aire y alertas oficiales completan cada tarjeta al llegar,
 * sin esperar a las demás y sin perder la posición (keepPlace). Mientras falta un dato
 * secundario su bloque no aparece. `turno` descarta resultados de un render viejo. */
async function render(container) {
  const mine = ++turno;
  const places = store.get('places') || [];
  const [me, avisos, ...sums] = await Promise.all([
    api.me().catch(() => null),
    api.alerts().then((r) => r.alerts).catch(() => []),
    ...places.map((p) => api.placeSummary(p.id).catch(() => ({ error: true }))),
  ]);
  if (mine !== turno || !mounted) return;
  meData = me; inboxData = avisos;
  [histories, panoramas, lluvias, stations, aires, oficiales].forEach((m) => m.clear());
  lastSummaryAt = new Date().toISOString();
  const ahora = Date.now();
  const ids = new Set(places.map((p) => p.id));
  for (const id of [...summaries.keys()]) if (!ids.has(id)) { summaries.delete(id); summariesAt.delete(id); }
  places.forEach((p, i) => applySummary(p, sums[i], ahora));
  paint(container);
  // Segunda etapa: cada dato secundario completa su tarjeta apenas llega.
  const completar = (prom, apply) => prom.then((v) => {
    if (mine !== turno || !mounted || v == null) return;
    apply(v);
    keepPlace(container, () => paint(container));
  });
  completar(loadTemporada(), (v) => { temporadaData = v; });
  for (const p of places) {
    completar(api.placeHistory(p.id).catch(() => null), (v) => histories.set(p.id, v));
    completar(p.comuna ? api.panorama(p.comuna.code).catch(() => null) : Promise.resolve(null), (v) => panoramas.set(p.id, v));
    completar(request(`/api/climate/lluvia?lat=${p.lat}&lon=${p.lon}`).catch(() => null), (v) => lluvias.set(p.id, v));
    completar(request(`/api/climate/station?lat=${p.lat}&lon=${p.lon}`).catch(() => null), (v) => stations.set(p.id, v));
    completar(request(`/api/climate/air?lat=${p.lat}&lon=${p.lon}`).catch(() => null), (v) => aires.set(p.id, v));
    completar(request(`/api/alerts/official?lat=${p.lat}&lon=${p.lon}`).catch(() => null), (v) => oficiales.set(p.id, v));
  }
}

function paint(container) {
  const places = store.get('places') || [];
  const config = store.get('config');
  const me = meData; const inbox = inboxData;
  stopSpeak(); // un repintado deja el botón «Detener» huérfano (igual que en lite.js)
  contextoMapa(); // MZ-08: CONAF y anillos siguen al resumen vigente (también en modo emergencia)
  const worst = ['urgente', 'aviso', 'riesgo', 'tranquilo'].find((s) => [...summaries.values()].some((x) => x?.status === s));
  const worstSummary = [...summaries.values()].find((x) => x?.status === worst);
  const urgent = places.map((p) => [p, summaries.get(p.id)]).filter(([, x]) => x?.status === 'urgente')
    .sort((a, b) => (a[1].nearby?.[0]?.distance_km ?? 99) - (b[1].nearby?.[0]?.distance_km ?? 99));
  if (urgent.length && !emDismissed(emKey(urgent))) {
    if (!emActive) { emActive = true; document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'full' })); }
    container.innerHTML = String(emergencyView(urgent));
    document.documentElement.classList.add('emergency-on');
    const emListen = container.querySelector('#em-listen');
    emListen?.addEventListener('click', () => speak(
      `${['.em-head', '.em-title', '.em-sub', '.em-official', '.em-steps'].map((s) => container.querySelector(s)?.innerText.trim()).filter(Boolean).join(' ')} BRASA no es una alerta oficial: sigue a SENAPRED.`,
      emListen));
    container.querySelector('#em-full').addEventListener('click', () => {
      try { sessionStorage.setItem(EM_KEY, emKey(urgent)); } catch { /* sin almacenamiento: se muestra igual la vista completa */ }
      render(container);
    });
    const [place] = urgent[0];
    fly(place.lon, place.lat, place.radius_km > 15 ? 9.5 : 10.5);
    return;
  }
  document.documentElement.classList.remove('emergency-on');
  if (emActive) { emActive = false; document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'half' })); }
  const channels = me && (me.push || me.telegram);
  const chileHot = (store.get('observations') || []).filter((o) => o.region && ['alta', 'nominal', 'media'].includes(o.confidence)
    && Date.now() - Date.parse(o.observed_at) < 24 * 3600000).length;
  // Lugares cuya consulta falló: el héroe no puede declarar la zona «tranquila» mientras falten datos.
  const nFailed = places.filter((p) => !summaries.get(p.id) || summaries.get(p.id).error).length;
  const hero = places.length
    ? worst && (worst !== 'tranquilo' || !nFailed)
    ? html`<div class="ember-hero st-${worst}" role="status">${emberSvg({ tone: worst })}
        <div><div class="hero-label">${STATUS[worst].title}</div>
        <small>${places.length === 1 ? 'En tu lugar' : `En tus ${places.length} lugares`}. ${statusText(worst, worstSummary?.cause)}.</small>
        ${worst !== 'tranquilo' ? html`<div class="btn-row hero-cta">${worst === 'urgente' ? html`<a class="btn btn-sm btn-call" href="tel:132">Llamar a Bomberos · 132</a>` : ''}
          <button class="btn btn-sm ${worst === 'urgente' ? 'btn-blue' : 'btn-primary'}" id="hero-what">Qué hago ahora</button>
          ${synth ? html`<button class="btn btn-sm btn-speak" id="hero-listen" type="button" aria-label="Escuchar el estado y qué hacer ahora">Escuchar</button>` : ''}</div>` : ''}</div></div>`
    : html`<div class="ember-hero" role="status">${emberSvg({ tone: 'tranquilo' })}
        <div><div class="hero-label">No pudimos consultar ${nFailed === places.length ? 'tus lugares' : `${nFailed === 1 ? 'uno' : nFailed} de tus lugares`} ahora</div>
        <small>Puede ser tu conexión o el servidor; no significa que no haya fuego cerca. Si ves humo o llamas, llama al 130 o al 132.</small></div></div>`
    : !store.get('status')?.last_ingest_at
    ? html`<div class="ember-hero" role="status">${emberSvg({ tone: 'tranquilo' })}
        <div><div class="hero-label">Aún no llegan datos de los satélites</div>
        <small>BRASA los revisa cada 10 minutos. Mientras tanto, si ves fuego o humo, llama al 130 o al 132.</small></div></div>`
    : html`<div class="ember-hero" role="status">${emberSvg({ tone: chileHot ? 'brasa' : 'tranquilo' })}
        <div><div class="hero-figure tabular">${fmtNum(chileHot)}</div>
        <small>${dual(chileHot === 1 ? 'punto de calor visto hoy por satélites en Chile' : 'puntos de calor vistos hoy por satélites en Chile',
          `${chileHot === 1 ? 'píxel caliente' : 'píxeles calientes'} de confianza media o alta en Chile, últimas 24 h (GOES + VIIRS/MODIS)`)}</small></div></div>`;
  // Datos atrasados: «no vemos fuego» deja de significar «no hay fuego».
  const lastIngest = store.get('status')?.last_ingest_at;
  const staleMin = lastIngest ? minutesSince(lastIngest) : 0;
  staleShown = staleMin > STALE_MIN;
  const staleNote = staleShown ? html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(lastIngest)}.</b>
      Que BRASA no muestre fuego no significa que no lo haya. Si ves humo o llamas, llama al <a href="tel:132"><b>132</b></a> o al <a href="tel:130"><b>130</b></a>.</div>` : '';
  // MZ-05: «Desde tu última visita» — compara el snapshot guardado con el de ahora.
  const nAvisos = [...summaries.values()].reduce((n, s) => n + (s?.dmc_alerts?.length || 0), 0);
  const cambiosPrev = storage.get('zona:snapshot', null);
  const cambiosAhora = snapshot({ places, summaries, avisos: nAvisos, now: new Date().toISOString() });
  const cambiosDig = places.length ? digest(cambiosPrev, cambiosAhora) : { dias: 0, frases: [] };
  const cambiosBloque = cambiosDig.frases.length && cambiosPrev?.at && cambiosVisto !== cambiosPrev.at
    ? html`<div class="callout small" role="status"><b>Desde tu última visita</b>
        <ul class="list" style="margin-top:4px">${cambiosDig.frases.map((f) => html`<li><span class="grow small">${f}</span></li>`)}</ul>
        <div class="btn-row" style="margin-top:6px"><button class="btn btn-sm btn-ghost" id="cambios-cerrar" aria-label="Ocultar el resumen">Ocultar</button></div></div>`
    : '';
  container.innerHTML = String(html`
    ${hero}${staleNote}
    <h1 class="view-title">${places.length ? 'Tus lugares, hoy' : '¿Hay fuego cerca de tu casa?'}</h1>
    <p class="lede">${places.length ? dual('Lo que vieron los satélites cerca de cada lugar, el viento y cómo viene el clima.', 'Detecciones satelitales de las últimas 48 h dentro de 2× el radio, viento actual (Open-Meteo) e índice 30-30-30 diario por comuna.') : 'Guarda tu casa, tu parcela o la casa de tu familia. Te avisamos cuando un satélite vea calor cerca.'}</p>
    ${worst === 'urgente' ? html`<div class="callout callout-urgent"><b>Si la autoridad ordena evacuar, hazlo de inmediato.</b> Ante fuego o humo visible llama al <a href="tel:130"><b>130</b></a> o al <a href="tel:132"><b>132</b></a>. BRASA no reemplaza las alertas oficiales.</div>` : ''}
    ${cambiosBloque}
    ${places.length ? html`<div id="places">${places.map((p) => placeCard(p, summaries.get(p.id), histories.get(p.id), temporadaData, null, panoramas.get(p.id), lluvias.get(p.id), stations.get(p.id), aires.get(p.id), oficiales.get(p.id), summariesAt.get(p.id) ?? lastSummaryAt))}</div>
      <div class="btn-row" style="margin-top:12px"><button class="btn btn-primary" id="add-place">Agregar lugar</button></div>`
      : html`<button class="btn btn-primary btn-block btn-lg" id="add-place">Agregar mi casa</button>
        <div class="card onboard" style="margin-top:10px"><ol class="steps">
          <li><b>Guarda un lugar.</b> Tu casa, tu parcela, el colegio o la casa de tus padres.</li>
          <li><b>Activa los avisos.</b> En este teléfono o por Telegram.</li>
          <li><b>Prepárate.</b> Mochila, ruta de salida y tu casa lista para el verano.</li></ol></div>
        <details class="fold" style="margin-top:8px"><summary>¿Qué es un «punto de calor»?</summary><div>
          <p>Los satélites miran Chile desde el espacio y detectan lugares mucho más calientes que su entorno. Casi siempre es fuego: un incendio, una quema agrícola o una fogata. A veces es una industria o un techo muy caliente.</p>
          <p>Por eso BRASA dice «punto de calor» y no «incendio»: es una señal para estar atento y revisar fuentes oficiales.</p></div></details>`}
    <h2 class="section">Avisos ${channels ? html`<span class="tag tag-live">${[me.push && 'Push', me.telegram && 'Telegram'].filter(Boolean).join(' · ')}</span>` : ''}</h2>
    ${channels ? '' : html`<div class="callout callout-warn"><b>Aún no recibes avisos.</b> Actívalos y te avisaremos aunque no tengas BRASA abierta.</div>`}
    <div class="btn-row" style="margin-top:10px"><button class="btn ${channels ? '' : 'btn-blue'}" id="channels">${channels ? 'Cambiar cómo me avisan' : 'Activar avisos'}</button></div>
    ${inbox.length ? html`<ul class="list" style="margin-top:10px">${inbox.slice(0, 8).map((a) => html`<li>
        <span class="status-badge st-${a.level === 'urgente' ? 'urgente' : 'aviso'}">${a.level === 'urgente' ? 'Urgente' : 'Aviso'}</span>
        <div class="grow"><b class="small">${a.title}</b><div class="tiny muted">${fmtDateTime(a.created_at)} · ${a.observation?.satellite || ''}</div></div>
        ${a.observation?.lat != null ? html`<button class="btn btn-sm btn-ghost" data-alert-id="${a.observation.id}" data-alert-lat="${a.observation.lat}" data-alert-lon="${a.observation.lon}" aria-label="Ver en el mapa: ${a.title}">Ver</button>` : ''}</li>`)}</ul>`
      : html`<p class="small muted" style="margin-top:10px">No hay avisos recientes.</p>`}
    <h2 class="section">Emergencias</h2>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:14px">BRASA es un proyecto ciudadano. ${dual('Los satélites pueden tardar unos minutos u horas en ver un fuego, y a veces no lo ven (por nubes o humo). Si ves fuego, llama: no esperes a BRASA.', `Usa detecciones de NASA y NOAA, con latencia de minutos a horas, omisiones y falsos positivos. ${config?.firms_configured ? '' : 'Sin clave NASA FIRMS en este servidor: solo GOES.'}`)}</p>`);

  container.querySelector('#cambios-cerrar')?.addEventListener('click', () => {
    cambiosVisto = cambiosPrev?.at || true;
    storage.set('zona:cambios:visto', cambiosVisto);
    paint(container);
  });
  container.querySelector('#add-place').addEventListener('click', () => placeForm());
  container.querySelector('#hero-what')?.addEventListener('click', () => {
    const p = places.find((x) => summaries.get(x.id)?.status === worst) || places[0];
    guidanceModal(worst, p);
  });
  const heroListen = container.querySelector('#hero-listen');
  heroListen?.addEventListener('click', () => {
    const p = places.find((x) => summaries.get(x.id)?.status === worst) || places[0];
    speak(`${STATUS[worst].title}. ${statusText(worst, worstSummary?.cause)}. ${guidanceFor(worst, p.older_adult)[0]} No es una alerta oficial: sigue a SENAPRED.`, heroListen);
  });
  container.querySelector('#channels').addEventListener('click', alertChannels);
  // Tocar un día lo explica en palabras (en el teléfono no hay «pasar el puntero» para ver un title).
  container.querySelectorAll('[data-daytip]').forEach((b) => b.addEventListener('click', () => toast(b.dataset.daytip, 'info', 7000)));
  if (!cambiosPrev?.at || Date.now() - Date.parse(cambiosPrev.at) > 30 * 60000) storage.set('zona:snapshot', cambiosAhora);
  // MAPA-162: bajar la hoja a peek antes de volar, si no el punto queda tapado bajo el panel.
  // MZ-08: si el punto sigue entre los focos cargados, «Ver» abre su ficha; si no, solo vuela.
  container.querySelectorAll('[data-alert-lat]').forEach((b) => b.addEventListener('click', () => {
    collapseSheet();
    const lat = Number(b.dataset.alertLat); const lon = Number(b.dataset.alertLon);
    const obs = (store.get('observations') || []).find((o) => o.id === b.dataset.alertId);
    fly(lon, lat, 12);
    if (obs) popupFoco(obs, [lon, lat]);
  }));
  container.querySelectorAll('[data-place]').forEach((card) => {
    const place = places.find((p) => p.id === card.dataset.place);
    const summary = summaries.get(place.id);
    const failed = !summary || summary.error;
    card.querySelector('[data-act="ver"]').addEventListener('click', () => { collapseSheet(); fly(place.lon, place.lat, place.radius_km > 15 ? 9.5 : 10.5); });
    card.querySelector('[data-act="que-hacer"]').addEventListener('click', () => guidanceModal(summary?.status || 'tranquilo', place, failed));
    card.querySelector('[data-act="reintentar"]')?.addEventListener('click', (ev) => retrySummary(container, place, ev.currentTarget));
    card.querySelector('[data-act="servicios"]').addEventListener('click', () => showServices(place));
    card.querySelector('[data-act="compartir"]').addEventListener('click', () => shareModal(place));
    card.querySelector('[data-act="ics"]')?.addEventListener('click', () => {
      const comuna = summary?.comuna?.name || place.comuna?.name || 'tu comuna';
      download(`boton-rojo-${comuna.toLowerCase().replace(/\s+/g, '-')}.ics`,
        botonRojoIcs({ comuna, days: summary?.risk_days || [], url: location.origin }), 'text/calendar');
      toast('Listo: abre el archivo descargado para agregarlo a tu calendario.');
    });
    card.querySelector('[data-act="editar"]').addEventListener('click', () => placeForm(place));
    card.querySelector('[data-act="borrar"]').addEventListener('click', () => openModal(html`<h2 id="modal-title">¿Eliminar «${place.name}»?</h2>
      <p class="muted">Dejarás de recibir alertas para este lugar.</p><div class="btn-row"><button class="btn btn-danger" id="confirm-del">Eliminar</button><button class="btn btn-ghost" id="cancel-del">Cancelar</button></div>`, (body) => {
      body.querySelector('#cancel-del').addEventListener('click', closeModal);
      body.querySelector('#confirm-del').addEventListener('click', async () => {
        try { await api.deletePlace(place.id); closeModal(); document.dispatchEvent(new CustomEvent('brasa:places-changed')); } catch (err) { toast(err.message, 'error'); }
      });
    }));
  });
}

function frame() {
  const places = store.get('places') || [];
  if (!places.length) return fitBbox([-75.5, -45, -66.5, -18], 30);
  const lats = places.map((p) => p.lat); const lons = places.map((p) => p.lon);
  const pad = 0.18;
  fitBbox([Math.min(...lons) - pad, Math.min(...lats) - pad, Math.max(...lons) + pad, Math.max(...lats) + pad], 60);
}

let offPlaces = null;
let offStatus = null;
let offObs = null;
let onVis = null;
export default {
  id: 'mi-zona',
  sheet: 'half',
  async mount(container) {
    mounted = true;
    emActive = false;
    container.innerHTML = '<h1 class="view-title">Cargando tus lugares…</h1>';
    // El mapa de la portada llega diferido: capas, leyenda y encuadre se aplican cuando
    // está listo. Si ya se cambió de vista, no se pisan las capas de la otra vista.
    const aplicar = () => {
      if (!mounted) return;
      // MZ-08: `official` lleva los incendios CONAF cercanos a los lugares; se apaga en unmount.
      show(['places', 'place-radius-fill', 'place-radius-line', 'detections', 'goes-pixels', 'goes-pixels-line', 'official'], true);
      show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore', 'reports'], false);
      if (!soltarToques.length) soltarToques = [
        ...FOCO_CAPAS.map((capa) => [capa, onFoco]),
        ['official', onOficial], ['incident-rings', onAnillo], ['places', onLugar],
      ].map(([capa, fn]) => registrarToque(capa, fn));
      legend();
      // MAPA-160: la portada también explica su mapa en el celular (chip «Leyenda»).
      $('#map-legend').classList.add('mobile-show');
      loadIncidentes();
      frame();
    };
    // onReady también espera a las teselas; con el estilo ya cargado (la fuente existe) se
    // aplica de inmediato y no queda encolado sin otro style.load que lo despierte.
    if (getMap()?.getSource('detections')) aplicar();
    else onReady(aplicar);
    await render(container);
    offPlaces = store.on('places', async () => { if (mounted) { await render(container); frame(); } });
    // Solo se redibuja si cambia el aviso de datos atrasados (no en cada actualización del estado).
    offStatus = store.on('status', (st) => {
      const stale = st?.last_ingest_at ? minutesSince(st.last_ingest_at) > STALE_MIN : false;
      if (mounted && stale !== staleShown) render(container);
    });
    // MZ-06: el resumen se vuelve a pedir con cada lote nuevo de focos (data.js deduplica:
    // 'observations' solo cambia con un corte nuevo) y al volver a la app.
    offObs = store.on('observations', () => { if (mounted) maybeRefresh(container, 'focos'); });
    onVis = () => { if (mounted) maybeRefresh(container, 'volver'); };
    document.addEventListener('visibilitychange', onVis);
  },
  unmount() {
    mounted = false;
    emActive = false;
    turno += 1;
    stopSpeak();
    document.documentElement.classList.remove('emergency-on');
    offPlaces?.();
    offStatus?.();
    offObs?.();
    offObs = null;
    if (onVis) { document.removeEventListener('visibilitychange', onVis); onVis = null; }
    soltarToques.forEach((s) => s());
    soltarToques = [];
    cerrarPopup();
    show(['services', 'official'], false);
    // Lo que pintó esta vista no se hereda: otra vista con las mismas capas no ve datos ajenos.
    setData('official', EMPTY_FC);
    setData('incident-rings', EMPTY_FC);
    conafCerca = new Map();
    incidentes = [];
    $('#map-legend').classList.remove('mobile-show');
  },
};
