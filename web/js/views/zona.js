/* Mi zona: ¿mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer? */
import { api } from '../api.js';
import { AGE_BINS, fitBbox, fly, pointsGeoJSON, setData, show } from '../map.js';
import { store } from '../store.js';
import { alertChannels, closeModal, openModal, phonesHtml, placeForm } from '../ui.js';
import { $, ago, cardWord, dual, emberSvg, fmtDateTime, fmtDay, fmtNum, html, radarSvg, RISK, riskChip, toast, windFrom, windWords } from '../util.js';

// Cada estado responde en palabras simples: qué pasa y qué tan grave es.
const STATUS = {
  urgente: { label: 'Urgente', title: 'Hay fuego cerca y el viento va hacia tu lugar', text: 'Un satélite vio calor dentro de tu zona de aviso y el viento lo empuja hacia ti' },
  aviso: { label: 'Calor cerca', title: 'Un satélite vio calor cerca', text: 'Puede ser un incendio o una quema. Revisa y mantente atento' },
  riesgo: { label: 'Día peligroso', title: 'Hoy el clima es peligroso para incendios', text: 'No se ve fuego cerca, pero hace calor, el aire está seco o hay viento' },
  tranquilo: { label: 'Tranquilo', title: 'No se ve fuego cerca', text: 'Los satélites no vieron calor en tu zona en los últimos 2 días' },
};

const GUIDANCE = {
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

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Puntos de calor vistos por satélite</div>
    <div class="legend-row"><span class="legend-item"><span class="sw" style="background:#3987e5"></span>Tu lugar y zona de aviso</span>
    ${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>
    <div class="legend-note">${dual('Más rojo = más reciente. Los cuadros marcan una zona de unos 2 km donde hay calor.', 'Cuadros: píxeles GOES ABI (~2–3 km). Puntos: VIIRS (375 m) y MODIS (1 km).')}</div>`);
}

function dayStrip(days) {
  if (!days?.length) return html`<p class="tiny muted" style="margin-top:8px">El pronóstico de los próximos días aparecerá pronto.</p>`;
  return html`<div class="day-strip" aria-label="Peligro de incendio por el clima, próximos 7 días">${days.slice(0, 7).map((d) => html`
    <div class="day-cell" title="${RISK[d.level]?.label || ''}: ${RISK[d.level]?.plain || ''} Máx ${fmtNum(d.tmax)} °C, humedad ${fmtNum(d.rhmin)} %, viento ${fmtNum(d.windmax)} km/h">
      <b>${fmtDay(d.date, { weekday: 'short', day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, day: 'numeric', month: undefined })}
      <i class="${RISK[d.level]?.cls || ''}"></i></div>`)}</div>`;
}

function placeCard(place, summary) {
  const status = summary?.status || 'tranquilo';
  const near = summary?.nearby?.filter((o) => o.inside_radius && o.reliable) || [];
  const nearest = near[0] || summary?.nearby?.[0];
  const today = summary?.risk_days?.[0];
  const wind = summary?.wind;
  const ww = windWords(wind?.direction);
  return html`<article class="card place-card st-border-${status}" data-place="${place.id}">
    <div class="card-head">
      <div class="place-title"><i class="px" aria-hidden="true"></i><div style="min-width:0"><div class="card-title">${place.name}</div>
        <div class="card-sub">${place.comuna ? place.comuna.name : 'Fuera de una comuna conocida'} · aviso a ${fmtNum(place.radius_km)} km</div></div></div>
      <span class="status-badge st-${status}">${STATUS[status].label}</span>
    </div>
    <div class="place-body">
      <figure class="radar-wrap">${radarSvg({ radiusKm: place.radius_km, nearby: summary?.nearby || [], wind })}
        <figcaption class="tiny">${dual(`Anillo: ${fmtNum(place.radius_km)} km`, `Anillos ${fmtNum(place.radius_km)} y ${fmtNum(place.radius_km * 2)} km`)}</figcaption></figure>
      <ul class="place-facts">
        <li>${nearest
          ? html`<b>${near.length ? `${near.length === 1 ? 'Un punto' : `${near.length} puntos`} de calor` : 'Calor'}</b> ${dual(`a ${fmtNum(nearest.distance_km, 0)} km, hacia el ${cardWord(nearest.direction)}`, `más cercano a ${fmtNum(nearest.distance_km, 1)} km, rumbo ${nearest.bearing_deg}° (${nearest.direction}) · ${nearest.satellite || nearest.sensor}`)}<span class="muted"> · ${ago(nearest.observed_at)}</span>`
          : html`<b>Sin calor</b> a menos de ${fmtNum(place.radius_km * 2)} km <span class="muted">en 2 días</span>`}</li>
        ${wind?.speed != null ? html`<li><b>Viento ${fmtNum(wind.speed)} km/h</b> ${ww ? dual(`viene del ${ww.from} y va hacia el ${ww.to} (flecha azul)`, `${windFrom(wind.direction)} (${Math.round(wind.direction)}°)${wind.gust ? ` · ráfagas ${fmtNum(wind.gust)} km/h` : ''}`) : ''}</li>` : ''}
        ${today ? html`<li>Clima de hoy: ${riskChip(today.level)}</li>` : ''}
      </ul>
    </div>
    ${dayStrip(summary?.risk_days)}
    <div class="card-actions">
      <button class="btn btn-sm ${status === 'tranquilo' ? '' : 'btn-primary'}" data-act="que-hacer">Qué hago</button>
      <button class="btn btn-sm" data-act="ver">Ver en el mapa</button>
      <button class="btn btn-sm" data-act="servicios">Dónde reunirse</button>
      <button class="btn btn-sm btn-ghost" data-act="editar">Editar</button>
      <button class="btn btn-sm btn-danger" data-act="borrar" aria-label="Eliminar ${place.name}">Eliminar</button>
    </div>
  </article>`;
}

function guidanceModal(status, place) {
  openModal(html`<h2 id="modal-title">${STATUS[status].title}</h2>
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
    openModal(html`<h2 id="modal-title">Dónde reunirse cerca de ${place.name}</h2>
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
    ? html`<div class="ember-hero st-${worst}" role="status">${emberSvg({ tone: worst })}
        <div><div class="hero-label">${STATUS[worst].title}</div>
        <small>${places.length === 1 ? 'En tu lugar' : `En tus ${places.length} lugares`}. ${STATUS[worst].text}.</small>
        ${worst !== 'tranquilo' ? html`<button class="btn btn-sm ${worst === 'urgente' ? 'btn-blue' : 'btn-primary'} hero-cta" id="hero-what">Qué hago ahora</button>` : ''}</div></div>`
    : !store.get('status')?.last_ingest_at
    ? html`<div class="ember-hero" role="status">${emberSvg({ tone: 'tranquilo' })}
        <div><div class="hero-label">Aún no llegan datos de los satélites</div>
        <small>BRASA los revisa cada 10 minutos. Mientras tanto, si ves fuego o humo, llama al 130 o al 132.</small></div></div>`
    : html`<div class="ember-hero" role="status">${emberSvg({ tone: chileHot ? 'brasa' : 'tranquilo' })}
        <div><div class="hero-figure tabular">${fmtNum(chileHot)}</div>
        <small>${dual(chileHot === 1 ? 'punto de calor visto hoy por satélites en Chile' : 'puntos de calor vistos hoy por satélites en Chile',
          `${chileHot === 1 ? 'píxel caliente' : 'píxeles calientes'} de confianza media o alta en Chile, últimas 24 h (GOES + VIIRS/MODIS)`)}</small></div></div>`;
  container.innerHTML = String(html`
    ${hero}
    <h1 class="view-title">${places.length ? 'Tus lugares, hoy' : '¿Hay fuego cerca de tu casa?'}</h1>
    <p class="lede">${places.length ? dual('Lo que vieron los satélites cerca de cada lugar, el viento y cómo viene el clima.', 'Detecciones satelitales de las últimas 48 h dentro de 2× el radio, viento actual (Open-Meteo) e índice 30-30-30 diario por comuna.') : 'Guarda tu casa, tu parcela o la casa de tu familia. Te avisamos cuando un satélite vea calor cerca.'}</p>
    ${worst === 'urgente' ? html`<div class="callout callout-urgent"><b>Si la autoridad ordena evacuar, hazlo de inmediato.</b> Ante fuego o humo visible llama al <a href="tel:130"><b>130</b></a> o al <a href="tel:132"><b>132</b></a>. BRASA no reemplaza las alertas oficiales.</div>` : ''}
    ${places.length ? html`<div id="places">${places.map((p) => placeCard(p, summaries.get(p.id)))}</div>
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
        <button class="btn btn-sm btn-ghost" data-alert-lat="${a.observation?.lat}" data-alert-lon="${a.observation?.lon}">Ver</button></li>`)}</ul>`
      : html`<p class="small muted" style="margin-top:10px">No hay avisos recientes.</p>`}
    <h2 class="section">Emergencias</h2>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:14px">BRASA es un proyecto ciudadano. ${dual('Los satélites pueden tardar unos minutos u horas en ver un fuego, y a veces no lo ven (por nubes o humo). Si ves fuego, llama: no esperes a BRASA.', `Usa detecciones de NASA y NOAA, con latencia de minutos a horas, omisiones y falsos positivos. ${config?.firms_configured ? '' : 'Sin clave NASA FIRMS en este servidor: solo GOES.'}`)}</p>`);

  container.querySelector('#add-place').addEventListener('click', () => placeForm());
  container.querySelector('#hero-what')?.addEventListener('click', () => {
    const p = places.find((x) => summaries.get(x.id)?.status === worst) || places[0];
    guidanceModal(worst, p);
  });
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
