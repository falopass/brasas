/* Mi zona: ¿mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer? */
import { api } from '../api.js';
import { AGE_BINS, fitBbox, fly, pointsGeoJSON, setData, show } from '../map.js';
import { store } from '../store.js';
import { alertChannels, closeModal, openModal, phonesHtml, placeForm } from '../ui.js';
import { $, ago, fmtDateTime, fmtDay, fmtNum, html, RISK, riskChip, toast, windFrom } from '../util.js';

const STATUS = {
  urgente: { label: 'Urgente', text: 'Foco de calor cerca y viento hacia tu lugar' },
  aviso: { label: 'Foco cercano', text: 'Hay detecciones satelitales dentro de tu radio' },
  riesgo: { label: 'Riesgo alto hoy', text: 'Sin focos cercanos, pero el clima favorece la propagación' },
  tranquilo: { label: 'Sin focos cercanos', text: 'No hay detecciones satelitales dentro de tu radio en 48 h' },
};

const GUIDANCE = {
  urgente: ['Si la autoridad ordena evacuar, sal de inmediato por la ruta que indiquen. No esperes a ver las llamas.',
    'Si ves fuego o humo, llama al 130 (CONAF) o al 132 (Bomberos) y entrega la ubicación exacta.',
    'Ten a mano la mochila de emergencia, documentos, medicamentos y a tus mascotas. Avisa a tus vecinos y a tus familiares.',
    'No te acerques al foco ni bloquees caminos: los brigadistas y Bomberos los necesitan.'],
  aviso: ['Verifica con fuentes oficiales (SENAPRED, CONAF y municipio). Una detección satelital puede ser una quema u otra fuente de calor.',
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

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Tus lugares y focos de calor</div>
    <div class="legend-row"><span class="legend-item"><span class="sw" style="background:#3987e5"></span>Lugar y radio</span>
    ${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>
    <div class="legend-note">Los cuadros son píxeles GOES (~2–3 km); los puntos, VIIRS/MODIS (375 m–1 km).</div>`);
}

function dayStrip(days) {
  if (!days?.length) return html`<p class="tiny muted" style="margin-top:8px">El pronóstico 30-30-30 aparecerá cuando el servidor lo calcule.</p>`;
  return html`<div class="day-strip" aria-label="Riesgo de los próximos días">${days.slice(0, 7).map((d) => html`
    <div class="day-cell" title="${RISK[d.level]?.label || ''}: máx ${fmtNum(d.tmax)} °C, HR mín ${fmtNum(d.rhmin)} %, viento ${fmtNum(d.windmax)} km/h">
      <b>${fmtDay(d.date, { weekday: 'short', day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, day: 'numeric', month: undefined })}
      <i class="${RISK[d.level]?.cls || ''}"></i></div>`)}</div>`;
}

function placeCard(place, summary) {
  const status = summary?.status || 'tranquilo';
  const near = summary?.nearby?.filter((o) => o.inside_radius && o.reliable) || [];
  const nearest = near[0] || summary?.nearby?.[0];
  const today = summary?.risk_days?.[0];
  const wind = summary?.wind;
  return html`<article class="card place-card st-border-${status}" data-place="${place.id}">
    <div class="card-head">
      <div style="min-width:0"><div class="card-title">${place.name}</div>
        <div class="card-sub">${place.comuna ? `${place.comuna.name}, ${place.comuna.region}` : 'Fuera de una comuna conocida'} · radio ${fmtNum(place.radius_km)} km</div></div>
      <span class="status-badge st-${status}">${STATUS[status].label}</span>
    </div>
    <p class="small" style="margin:8px 0 0">${STATUS[status].text}.</p>
    <div class="place-meta">
      ${nearest ? html`<span><i class="px px-brasa"></i>${near.length ? `${near.length} foco(s) en tu radio · ` : ''}más cercano a <b>${fmtNum(nearest.distance_km, 1)} km</b> al ${nearest.direction}, ${ago(nearest.observed_at)}</span>` : html`<span><i class="px px-off"></i>Sin detecciones en ${fmtNum(place.radius_km * 2)} km (48 h)</span>`}
      ${wind?.speed != null ? html`<span><i class="px px-off"></i>Viento ${fmtNum(wind.speed)} km/h ${windFrom(wind.direction)}${wind.gust ? ` · ráfagas ${fmtNum(wind.gust)}` : ''}</span>` : ''}
      ${today ? html`<span>Hoy ${riskChip(today.level)}</span>` : ''}
    </div>
    ${dayStrip(summary?.risk_days)}
    <div class="card-actions">
      <button class="btn btn-sm" data-act="ver">Ver en el mapa</button>
      <button class="btn btn-sm" data-act="que-hacer">Qué hacer</button>
      <button class="btn btn-sm" data-act="servicios">Puntos de encuentro</button>
      <button class="btn btn-sm btn-ghost" data-act="editar">Editar</button>
      <button class="btn btn-sm btn-danger" data-act="borrar" aria-label="Eliminar ${place.name}">Eliminar</button>
    </div>
  </article>`;
}

function guidanceModal(status, place) {
  openModal(html`<h2 id="modal-title">Qué hacer: ${STATUS[status].label.toLowerCase()}</h2>
    <p class="muted small">${place.name}${place.comuna ? ` · ${place.comuna.name}` : ''}</p>
    <ol class="steps">${GUIDANCE[status].map((g) => html`<li>${g}</li>`)}</ol>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:12px">Recomendaciones generales. Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen.</p>`);
}

async function showServices(place) {
  try {
    const data = await api.nearbyServices(place.lat, place.lon);
    setData('services', pointsGeoJSON(data.items, (i) => ({ kind: i.kind, name: i.name })));
    show('services', true);
    fly(place.lon, place.lat, 12);
    const groups = data.items.slice(0, 12);
    openModal(html`<h2 id="modal-title">Cerca de ${place.name}</h2>
      <p class="muted small">${data.note}</p>
      ${groups.length ? html`<ul class="list">${groups.map((i) => html`<li><span class="dot" style="background:${i.kind === 'assembly_point' ? '#0ca30c' : i.kind === 'hospital' ? '#e34948' : i.kind === 'fire_station' ? '#eb6834' : '#3987e5'}"></span>
        <div class="grow"><b>${i.name}</b><div class="tiny muted">${i.kind_label}</div></div><span class="small nowrap">${fmtNum(i.distance_km, 1)} km ${i.direction}</span></li>`)}</ul>`
        : html`<div class="empty"><div class="glyph">⌖</div>No hay puntos registrados en OpenStreetMap cerca de aquí. Consulta a tu municipio.</div>`}
      <p class="tiny muted">Fuente: ${data.source}. Antes de una emergencia, confirma con tu municipio cuál es tu punto de encuentro oficial.</p>`);
  } catch (err) { toast(err.message, 'error'); }
}

async function render(container) {
  const places = store.get('places') || [];
  const config = store.get('config');
  let me = null; let inbox = [];
  [me, inbox] = await Promise.all([api.me().catch(() => null), api.alerts().then((r) => r.alerts).catch(() => [])]);
  const results = await Promise.all(places.map((p) => api.placeSummary(p.id).catch(() => null)));
  summaries = new Map(places.map((p, i) => [p.id, results[i]]));
  if (!mounted) return;
  const worst = ['urgente', 'aviso', 'riesgo', 'tranquilo'].find((s) => [...summaries.values()].some((x) => x?.status === s));
  const channels = me && (me.push || me.telegram);
  const chileHot = (store.get('observations') || []).filter((o) => o.region && ['alta', 'nominal', 'media'].includes(o.confidence)
    && Date.now() - Date.parse(o.observed_at) < 24 * 3600000).length;
  const hero = places.length
    ? html`<div class="hero-px st-${worst}" role="status"><span class="figure">${STATUS[worst].label}</span>
        <small>${places.length === 1 ? 'Tu lugar' : `Tus ${places.length} lugares`} · ${STATUS[worst].text.toLowerCase()}</small></div>`
    : html`<div class="hero-px" role="status"><span class="figure tabular">${fmtNum(chileHot)}</span>
        <small>${chileHot === 1 ? 'píxel caliente confiable' : 'píxeles calientes confiables'} en Chile en las últimas 24 h</small></div>`;
  container.innerHTML = String(html`
    ${hero}
    <h1 class="view-title">${places.length ? (worst === 'urgente' ? 'Atención: foco cerca de uno de tus lugares' : worst === 'aviso' ? 'Hay focos de calor cerca' : worst === 'riesgo' ? 'Día de riesgo alto en tu zona' : 'Tus lugares, hoy') : '¿Tu casa está en riesgo hoy?'}</h1>
    <p class="lede">${places.length ? 'Detecciones satelitales de las últimas 48 horas y el índice 30-30-30 de cada comuna.' : 'Guarda tu casa, tu parcela o la casa de tu familia y te avisaremos cuando un satélite detecte calor cerca, con el viento a favor o en contra.'}</p>
    ${worst === 'urgente' ? html`<div class="callout callout-urgent"><b>Si la autoridad ordena evacuar, hazlo de inmediato.</b> Ante fuego o humo visible llama al <a href="tel:130"><b>130</b></a> o al <a href="tel:132"><b>132</b></a>. BRASA no reemplaza las alertas oficiales.</div>` : ''}
    ${places.length ? html`<div id="places">${places.map((p) => placeCard(p, summaries.get(p.id)))}</div>
      <div class="btn-row" style="margin-top:12px"><button class="btn btn-primary" id="add-place">Agregar lugar</button></div>`
      : html`<div class="card onboard"><ol class="steps">
          <li><b>Guarda un lugar.</b> Tu casa, tu parcela, el colegio o la casa de tus padres.</li>
          <li><b>Activa las alertas.</b> Notificaciones en este teléfono o Telegram.</li>
          <li><b>Prepárate.</b> Mochila, ruta de salida y tu casa lista para el verano.</li></ol>
          <button class="btn btn-primary btn-block" id="add-place">Agregar mi primer lugar</button></div>`}
    <h2 class="section">Alertas ${channels ? html`<span class="tag tag-live">${[me.push && 'Push', me.telegram && 'Telegram'].filter(Boolean).join(' · ')}</span>` : ''}</h2>
    ${channels ? '' : html`<div class="callout callout-warn"><b>Aún no recibes alertas.</b> Activa las notificaciones o vincula Telegram para que te avisemos aunque no tengas BRASA abierta.</div>`}
    <div class="btn-row" style="margin-top:10px"><button class="btn ${channels ? '' : 'btn-blue'}" id="channels">${channels ? 'Gestionar canales' : 'Activar alertas'}</button></div>
    ${inbox.length ? html`<ul class="list" style="margin-top:10px">${inbox.slice(0, 8).map((a) => html`<li>
        <span class="status-badge st-${a.level === 'urgente' ? 'urgente' : 'aviso'}">${a.level}</span>
        <div class="grow"><b class="small">${a.title}</b><div class="tiny muted">${fmtDateTime(a.created_at)} · ${a.observation?.satellite || ''}</div></div>
        <button class="btn btn-sm btn-ghost" data-alert-lat="${a.observation?.lat}" data-alert-lon="${a.observation?.lon}">Ver</button></li>`)}</ul>`
      : html`<p class="small muted" style="margin-top:10px">Sin alertas recientes.</p>`}
    <h2 class="section">Emergencias</h2>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:14px">BRASA es un proyecto ciudadano independiente. Usa detecciones satelitales de NASA y NOAA, que pueden tener minutos u horas de retraso, omisiones y falsos positivos. ${config?.firms_configured ? '' : 'Este servidor aún no tiene clave NASA FIRMS: solo se usan detecciones GOES.'}</p>`);

  container.querySelector('#add-place').addEventListener('click', () => placeForm());
  container.querySelector('#channels').addEventListener('click', alertChannels);
  container.querySelectorAll('[data-alert-lat]').forEach((b) => b.addEventListener('click', () => fly(Number(b.dataset.alertLon), Number(b.dataset.alertLat), 12)));
  container.querySelectorAll('[data-place]').forEach((card) => {
    const place = places.find((p) => p.id === card.dataset.place);
    const summary = summaries.get(place.id);
    card.querySelector('[data-act="ver"]').addEventListener('click', () => fly(place.lon, place.lat, place.radius_km > 15 ? 9.5 : 10.5));
    card.querySelector('[data-act="que-hacer"]').addEventListener('click', () => guidanceModal(summary?.status || 'tranquilo', place));
    card.querySelector('[data-act="servicios"]').addEventListener('click', () => showServices(place));
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
export default {
  id: 'mi-zona',
  sheet: 'half',
  async mount(container) {
    mounted = true;
    container.innerHTML = '<h1 class="view-title">Cargando tus lugares…</h1>';
    show(['places', 'place-radius-fill', 'place-radius-line', 'detections', 'goes-pixels', 'goes-pixels-line'], true);
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore', 'reports'], false);
    legend();
    await render(container);
    frame();
    offPlaces = store.on('places', async () => { if (mounted) { await render(container); frame(); } });
  },
  unmount() {
    mounted = false;
    offPlaces?.();
    show('services', false);
  },
};
