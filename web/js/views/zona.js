/* Mi zona: ¿mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer? */
import { api } from '../api.js';
import { AGE_BINS, fitBbox, fly, pointsGeoJSON, setData, show } from '../map.js';
import { store } from '../store.js';
import { alertChannels, closeModal, openModal, phonesHtml, placeForm } from '../ui.js';
import { $, ago, cardWord, minutesSince, dual, emberSvg, fmtDateTime, fmtDay, fmtNum, html, radarSvg, RISK, riskChip, toast, windFrom, windWords } from '../util.js';

// Cada estado responde en palabras simples: qué pasa y qué tan grave es.
export const STATUS = {
  urgente: { label: 'Urgente', title: 'Puede haber fuego muy cerca de tu lugar', text: 'Un satélite vio calor dentro de tu zona de aviso: muy cerca, con el viento hacia ti o donde alguien necesita más tiempo para salir' },
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
let staleShown = false;
const STALE_MIN = 30;

// Primero en la lista cuando en el lugar vive alguien que necesita ayuda para salir.
export const OLDER_GUIDANCE = {
  urgente: 'Llama ahora a la persona mayor y confirma quién la ayuda a salir. Salgan temprano: no esperen a ver las llamas ni la orden de evacuar.',
  aviso: 'Llama a la persona mayor: que tenga a mano sus remedios, documentos y la mochila, y acuerden quién la ayuda a salir si hace falta.',
  riesgo: 'Hoy revisa con la persona mayor la mochila y sus remedios, y confirma quién la ayuda si hay que salir.',
  tranquilo: 'Acuerda con la persona mayor quién la ayuda a salir y anoten juntos el plan familiar.',
};
export const guidanceFor = (status, olderAdult) => (olderAdult ? [OLDER_GUIDANCE[status], ...GUIDANCE[status]] : GUIDANCE[status]);

/* Modo emergencia: con un lugar en «urgente», la pantalla deja el análisis y responde solo lo esencial.
 * ¿Qué tan cerca está?, ¿qué dijo la autoridad?, qué hacer ahora y a quién llamar. Se puede volver a la vista completa. */
const EM_KEY = 'em-dismissed';
const emKey = (urgent) => urgent.map(([p, s]) => `${p.id}:${s.nearby?.find((o) => o.inside_radius && o.reliable)?.id || ''}`).join('|');
const emDismissed = (key) => { try { return sessionStorage.getItem(EM_KEY) === key; } catch { return false; } };

function emergencyView(urgent) {
  const [place, summary] = urgent[0];
  const near = summary.nearby.filter((o) => o.inside_radius && o.reliable);
  const n = near[0];
  const latest = near.map((o) => o.observed_at).sort().pop();
  const ww = windWords(summary.wind?.direction);
  const upwind = near.some((o) => o.upwind);
  return html`<section class="emergency" aria-labelledby="em-title">
    <div class="em-head"><span class="status-badge st-urgente">Urgente</span><span class="small">${latest ? `último calor ${ago(latest)}` : ''}</span></div>
    <h1 class="em-title" id="em-title">${n ? `Posible fuego a ${fmtNum(n.distance_km, n.distance_km < 3 ? 1 : 0)} km de «${place.name}»` : `Calor cerca de «${place.name}»`}</h1>
    <p class="em-sub">${n ? `Hacia el ${cardWord(n.direction)}.` : ''} ${upwind && ww ? `El viento va hacia tu lugar (${fmtNum(summary.wind.speed)} km/h).` : ''}
      ${urgent.length > 1 ? `También hay calor cerca de ${urgent.length - 1 === 1 ? 'otro de tus lugares' : `otros ${urgent.length - 1} de tus lugares`}.` : ''}</p>
    <div class="em-calls"><a class="btn btn-call btn-lg" href="tel:132">Bomberos · 132</a><a class="btn btn-lg" href="tel:130">CONAF · 130</a></div>
    <div class="em-official"><b>¿Qué dijo la autoridad?</b> Las órdenes de evacuación las da SENAPRED: llegan como mensaje de emergencia al celular, por radio y en su sitio. BRASA no las reemplaza.
      <a class="btn btn-sm btn-block" href="https://senapred.cl/alertas/" target="_blank" rel="noopener">Ver alertas de SENAPRED ↗</a></div>
    <ol class="steps em-steps">
      ${place.older_adult ? html`<li><b>Llama ahora a la persona mayor</b> y confirma quién la ayuda a salir. Salgan temprano, sin esperar a ver las llamas.</li>` : ''}
      <li><b>Si ordenan evacuar, sal ya</b> por la ruta que indiquen. Si la instrucción es salir a pie, sal a pie. No esperes a ver las llamas.</li>
      <li><b>Prepárate para salir ahora:</b> mochila, remedios, documentos y tus mascotas. No las dejes amarradas ni encerradas.</li>
      <li><b>Avisa por mensaje de texto o WhatsApp</b>, no con llamadas largas: las líneas se saturan. Si ves fuego o humo, llama al 132.</li>
      <li><b>No regreses</b> aunque ya no veas llamas: espera a que la autoridad lo permita.</li>
    </ol>
    <div class="btn-row">${n?.incident_id ? html`<a class="btn" href="#/incendio/${n.incident_id}">Qué han visto los satélites</a>` : ''}
      <button class="btn btn-ghost" id="em-full">Ver todo (mapa, clima y detalles)</button></div>
    <p class="tiny muted">BRASA es un proyecto ciudadano y no es una alerta oficial. Un satélite vio calor dentro de tu zona de aviso; puede ser un incendio, una quema o una industria.</p>
  </section>`;
}

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Puntos de calor vistos por satélite</div>
    <div class="legend-row"><span class="legend-item"><span class="sw" style="background:#3987e5"></span>Tu lugar y zona de aviso</span>
    ${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>
    <div class="legend-note">${dual('Más rojo = más reciente. Los cuadros marcan una zona de unos 2 km donde hay calor.', 'Cuadros: píxeles GOES ABI (~2–3 km). Puntos: VIIRS (375 m) y MODIS (1 km).')}</div>`);
}

export function dayStrip(days) {
  if (!days?.length) return html`<p class="tiny muted" style="margin-top:8px">El pronóstico de los próximos días aparecerá pronto.</p>`;
  return html`<div class="day-strip" aria-label="Peligro de incendio por el clima, próximos 7 días">${days.slice(0, 7).map((d) => html`
    <button type="button" class="day-cell" data-daytip="${fmtDay(d.date)}: peligro ${(RISK[d.level]?.label || 'sin dato').toLowerCase()}. ${RISK[d.level]?.plain || ''} Hasta ${fmtNum(d.tmax)} °C, humedad ${fmtNum(d.rhmin)} %, viento ${fmtNum(d.windmax)} km/h.${d.boton_rojo_hours ? ' CONAF pronostica Botón Rojo: condiciones favorables para incendios (no significa que haya fuego).' : ''}">
      <b>${fmtDay(d.date, { weekday: 'short', day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, day: 'numeric', month: undefined })}
      <i class="${RISK[d.level]?.cls || ''}"></i>${d.boton_rojo_hours ? html`<em class="br-mark" aria-hidden="true">BR</em>` : ''}<span class="sr-only">Peligro ${(RISK[d.level]?.label || 'sin dato').toLowerCase()}${d.boton_rojo_hours ? '. CONAF: Botón Rojo' : ''}</span></button>`)}</div>`;
}

/** Radar y datos clave de un lugar (los usa la tarjeta propia y la vista compartida con la familia). */
export function placeBody(place, summary) {
  const near = summary?.nearby?.filter((o) => o.inside_radius && o.reliable) || [];
  const nearest = near[0] || summary?.nearby?.[0];
  const today = summary?.risk_days?.[0];
  const wind = summary?.wind;
  const ww = windWords(wind?.direction);
  return html`<div class="place-body">
      <figure class="radar-wrap">${radarSvg({ radiusKm: place.radius_km, nearby: summary?.nearby || [], wind })}
        <figcaption class="tiny">${dual(`Anillo: ${fmtNum(place.radius_km)} km`, `Anillos ${fmtNum(place.radius_km)} y ${fmtNum(place.radius_km * 2)} km`)}</figcaption></figure>
      <ul class="place-facts">
        <li>${nearest
          ? html`<b>${near.length ? `${near.length === 1 ? 'Un punto' : `${near.length} puntos`} de calor` : 'Calor'}</b> ${dual(`a ${fmtNum(nearest.distance_km, nearest.distance_km < 3 ? 1 : 0)} km, hacia el ${cardWord(nearest.direction)}`, `más cercano a ${fmtNum(nearest.distance_km, 1)} km, rumbo ${nearest.bearing_deg}° (${nearest.direction}) · ${nearest.satellite || nearest.sensor}`)}<span class="muted"> · ${ago(nearest.observed_at)}</span>`
          : html`<b>Sin calor</b> a menos de ${fmtNum(place.radius_km * 2)} km <span class="muted">en 2 días</span>`}</li>
        ${wind?.speed != null ? html`<li><b>Viento ${fmtNum(wind.speed)} km/h</b> ${ww ? dual(`viene del ${ww.from} y va hacia el ${ww.to} (flecha azul)`, `${windFrom(wind.direction)} (${Math.round(wind.direction)}°)${wind.gust ? ` · ráfagas ${fmtNum(wind.gust)} km/h` : ''}`) : ''}</li>` : ''}
        ${today ? html`<li>Clima de hoy: ${riskChip(today.level)}</li>` : ''}
      </ul>
    </div>`;
}

function placeCard(place, summary) {
  const status = summary?.status || 'tranquilo';
  return html`<article class="card place-card st-border-${status}" data-place="${place.id}">
    <div class="card-head">
      <div class="place-title"><i class="px" aria-hidden="true"></i><div style="min-width:0"><div class="card-title">${place.name}</div>
        <div class="card-sub">${place.comuna ? place.comuna.name : 'Fuera de una comuna conocida'} · aviso a ${fmtNum(place.radius_km)} km</div>
        ${place.older_adult || place.shared ? html`<div class="badges" style="margin-top:6px">${place.older_adult ? html`<span class="tag tag-older">Persona mayor · aviso anticipado</span>` : ''}${place.shared ? html`<span class="tag tag-live">Compartido con la familia</span>` : ''}</div>` : ''}</div></div>
      <span class="status-badge st-${status}">${STATUS[status].label}</span>
    </div>
    ${placeBody(place, summary)}
    ${dayStrip(summary?.risk_days)}
    <div class="card-actions">
      <button class="btn btn-sm ${status === 'tranquilo' ? '' : 'btn-primary'}" data-act="que-hacer">Qué hago</button>
      <button class="btn btn-sm" data-act="ver">Ver en el mapa</button>
      <button class="btn btn-sm" data-act="servicios">Dónde reunirse</button>
      <button class="btn btn-sm" data-act="compartir">${place.shared ? 'Enlace para la familia' : 'Compartir con la familia'}</button>
      <button class="btn btn-sm btn-ghost" data-act="editar">Editar</button>
      <button class="btn btn-sm btn-danger" data-act="borrar" aria-label="Eliminar ${place.name}">Eliminar</button>
    </div>
  </article>`;
}

function guidanceModal(status, place) {
  openModal(html`<h2 id="modal-title">${STATUS[status].title}</h2>
    <p class="muted small">${place.name}${place.comuna ? ` · ${place.comuna.name}` : ''}</p>
    <ol class="steps">${guidanceFor(status, place.older_adult).map((g) => html`<li>${g}</li>`)}</ol>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:12px">Recomendaciones generales. Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen.</p>`);
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
    <p class="tiny muted" style="margin-top:12px">Compártelo solo con personas de confianza: muestra dónde está el lugar.</p>
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

async function render(container) {
  const places = store.get('places') || [];
  const config = store.get('config');
  let me = null; let inbox = [];
  [me, inbox] = await Promise.all([api.me().catch(() => null), api.alerts().then((r) => r.alerts).catch(() => [])]);
  const results = await Promise.all(places.map((p) => api.placeSummary(p.id).catch(() => null)));
  summaries = new Map(places.map((p, i) => [p.id, results[i]]));
  if (!mounted) return;
  const worst = ['urgente', 'aviso', 'riesgo', 'tranquilo'].find((s) => [...summaries.values()].some((x) => x?.status === s));
  const urgent = places.map((p) => [p, summaries.get(p.id)]).filter(([, x]) => x?.status === 'urgente')
    .sort((a, b) => (a[1].nearby?.[0]?.distance_km ?? 99) - (b[1].nearby?.[0]?.distance_km ?? 99));
  if (urgent.length && !emDismissed(emKey(urgent))) {
    container.innerHTML = String(emergencyView(urgent));
    document.documentElement.classList.add('emergency-on');
    container.querySelector('#em-full').addEventListener('click', () => {
      try { sessionStorage.setItem(EM_KEY, emKey(urgent)); } catch { /* sin almacenamiento: se muestra igual la vista completa */ }
      render(container);
    });
    const [place] = urgent[0];
    fly(place.lon, place.lat, place.radius_km > 15 ? 9.5 : 10.5);
    return;
  }
  document.documentElement.classList.remove('emergency-on');
  const channels = me && (me.push || me.telegram);
  const chileHot = (store.get('observations') || []).filter((o) => o.region && ['alta', 'nominal', 'media'].includes(o.confidence)
    && Date.now() - Date.parse(o.observed_at) < 24 * 3600000).length;
  const hero = places.length
    ? html`<div class="ember-hero st-${worst}" role="status">${emberSvg({ tone: worst })}
        <div><div class="hero-label">${STATUS[worst].title}</div>
        <small>${places.length === 1 ? 'En tu lugar' : `En tus ${places.length} lugares`}. ${STATUS[worst].text}.</small>
        ${worst !== 'tranquilo' ? html`<div class="btn-row hero-cta">${worst === 'urgente' ? html`<a class="btn btn-sm btn-call" href="tel:132">Llamar a Bomberos · 132</a>` : ''}
          <button class="btn btn-sm ${worst === 'urgente' ? 'btn-blue' : 'btn-primary'}" id="hero-what">Qué hago ahora</button></div>` : ''}</div></div>`
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
  container.innerHTML = String(html`
    ${hero}${staleNote}
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
        ${a.observation?.lat != null ? html`<button class="btn btn-sm btn-ghost" data-alert-lat="${a.observation.lat}" data-alert-lon="${a.observation.lon}" aria-label="Ver en el mapa: ${a.title}">Ver</button>` : ''}</li>`)}</ul>`
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
  // Tocar un día lo explica en palabras (en el teléfono no hay «pasar el puntero» para ver un title).
  container.querySelectorAll('[data-daytip]').forEach((b) => b.addEventListener('click', () => toast(b.dataset.daytip, 'info', 7000)));
  container.querySelectorAll('[data-alert-lat]').forEach((b) => b.addEventListener('click', () => fly(Number(b.dataset.alertLon), Number(b.dataset.alertLat), 12)));
  container.querySelectorAll('[data-place]').forEach((card) => {
    const place = places.find((p) => p.id === card.dataset.place);
    const summary = summaries.get(place.id);
    card.querySelector('[data-act="ver"]').addEventListener('click', () => fly(place.lon, place.lat, place.radius_km > 15 ? 9.5 : 10.5));
    card.querySelector('[data-act="que-hacer"]').addEventListener('click', () => guidanceModal(summary?.status || 'tranquilo', place));
    card.querySelector('[data-act="servicios"]').addEventListener('click', () => showServices(place));
    card.querySelector('[data-act="compartir"]').addEventListener('click', () => shareModal(place));
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
    // Solo se redibuja si cambia el aviso de datos atrasados (no en cada actualización del estado).
    offStatus = store.on('status', (st) => {
      const stale = st?.last_ingest_at ? minutesSince(st.last_ingest_at) > STALE_MIN : false;
      if (mounted && stale !== staleShown) render(container);
    });
  },
  unmount() {
    mounted = false;
    document.documentElement.classList.remove('emergency-on');
    offPlaces?.();
    offStatus?.();
    show('services', false);
  },
};
