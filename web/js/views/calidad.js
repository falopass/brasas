/* Calidad de los datos (QA-05): la transparencia como una vista. El estado en vivo de cada
 * fuente (última corrida, último éxito, resultado y mensaje, con el historial reciente de
 * /api/status?history=20), los barridos de GOES-19, los incidentes abiertos por estado y la
 * licencia de cada capa (docs/FUENTES.md). Solo estado de fuentes y conteos: aquí no hay
 * datos de personas. */
import { api } from '../api.js';
import { show } from '../map.js';
import { store } from '../store.js';
import { $, ago, dual, fmtDateTime, fmtNum, html, keepPlace, raw, toast } from '../util.js';
import { incidentInfo } from './incendio.js';

const PRODUCT_NAMES = {
  GOES19_FDCF: 'GOES-19', GOES16_FDCF: 'GOES-16', 'ABI-L2-FDCF': 'barridos de GOES',
  VIIRS_NOAA20_NRT: 'VIIRS NOAA-20', VIIRS_NOAA21_NRT: 'VIIRS NOAA-21',
  VIIRS_SNPP_NRT: 'VIIRS Suomi NPP', MODIS_NRT: 'MODIS Terra/Aqua',
  DMC_CAP: 'avisos CAP', BOTON_ROJO: 'Botón Rojo', CONAF_INCENDIOS: 'incendios de la temporada',
};
const OPEN_ORDER = ['confirmado', 'controlado', 'reportado', 'posible', 'anomalia'];
const INGEST_MODE = {
  interna: 'en este mismo servidor',
  cron: 'por un programador externo',
  apagada: 'apagada',
};

// Licencias y atribución: copia fiel de docs/FUENTES.md (revisado en octubre de 2026).
const THIRD_PARTY = [
  ['Puntos de calor · NOAA GOES-19 y GOES-16', 'Producto ABI-L2-FDC en AWS Open Data: público, sin clave. Llega cada 10 minutos, con ~10–20 min de retraso.'],
  ['Puntos de calor · NASA FIRMS (VIIRS y MODIS)', 'API pública con clave gratuita. Informa detecciones térmicas, no incendios confirmados; cada satélite pasa unas 2 veces al día, con ~1–3 h de retraso.'],
  ['CONAF · Botón Rojo', 'Capa pública de la Gerencia de Protección contra Incendios Forestales, la del tablero oficial. La información es propiedad de CONAF; sin licencia declarada, se muestra siempre con su nombre y enlace.'],
  ['CONAF · incendios de la temporada', 'Reporte público en CSV de la cuenta GEPRIF (deigeprif). El repositorio no declara licencia: se cita con enlace. Es la única vía a «confirmado», «controlado» y «extinguido según CONAF».'],
  ['DMC · avisos de viento y calor', 'Avisos oficiales de la Dirección Meteorológica de Chile en formato CAP 1.2; el RSS se declara «public domain».'],
  ['Clima · Open-Meteo y ERA5', 'Pronóstico horario de Open-Meteo y reanálisis ERA5 de Copernicus vía Open-Meteo Archive. Uso gratuito no comercial.'],
  ['Comunas y regiones', 'Mapas vectoriales de la Biblioteca del Congreso Nacional (BCN), vía el repositorio chile-geojson, simplificadas conservando los bordes compartidos.'],
  ['Mapas base', 'Vectorial: OpenFreeMap, esquema OpenMapTiles y datos © OpenStreetMap. Satélite: Sentinel-2 cloudless 2023 de EOX, CC BY-NC-SA 4.0 (no comercial). Relieve: OpenTopoMap, CC-BY-SA. 3D: CesiumJS.'],
  ['Puntos de encuentro y servicios', 'OpenStreetMap vía Overpass, en caché 24 h. Los puntos de encuentro oficiales los define cada municipio y SENAPRED.'],
];
const OWN_WORK = [
  ['Peligro de incendio por comuna', 'La regla 30-30-30 aplicada hora a hora sobre el pronóstico, junto al índice FWI que BRASA calcula. Los niveles «alto» y «moderado» son criterios propios, documentados en el código.'],
  ['Incidentes', 'Agrupación propia de las detecciones satelitales; «confirmado» solo cuando CONAF lo informa. Un incidente es evidencia agrupada, no un perímetro.'],
  ['Huella de los casos históricos', 'La unión de los píxeles calientes observados: no es un perímetro oficial y con GOES sobreestima la superficie.'],
  ['Fuentes fijas probables', 'Volcanes activos conocidos y celdas con calor repetido (industria, antorchas): se muestran pero no generan avisos.'],
];

const dot = (ok) => html`<span class="dot" style="background:${ok ? 'var(--risk-bajo)' : 'var(--risk-extremo)'}"></span>`;
/** Tirita de corridas recientes: la más nueva a la izquierda. `history` solo trae ok/started_at, ya escapada. */
const histDots = (hist) => raw(hist.slice(0, 20)
  .map((h) => `<span class="dot" style="width:6px;height:6px;background:${h.ok ? 'var(--risk-bajo)' : 'var(--risk-extremo)'}"></span>`)
  .join('<span style="display:inline-block;width:3px"></span>'));

function summary(status) {
  const fresh = status.freshness || {};
  const newest = Object.values(status.newest_observation || {}).filter(Boolean).sort().pop();
  const stale = status.last_ingest_at ? Boolean(fresh.stale) : true;
  const mode = status.ingest_mode === 'apagada'
    ? 'La actualización automática de las fuentes está apagada en este servidor.'
    : `BRASA revisa sus fuentes automáticamente (${INGEST_MODE[status.ingest_mode] || 'sin dato'}).`;
  return html`
    <p class="small x-plain">${mode} Si un dato se atrasa más de 30 minutos, se marca como atrasado. Aquí puedes comprobarlo.</p>
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>${dual('última revisión', 'última ingesta')}</small><strong class="kpi-text">${status.last_ingest_at ? ago(status.last_ingest_at) : '—'}</strong><span>${status.last_ingest_at ? fmtDateTime(status.last_ingest_at) : 'sin datos'}</span></div>
      <div class="kpi"><small>${dual('¿al día?', 'frescura')}</small><strong class="kpi-text">${status.last_ingest_at ? (stale ? 'Atrasada' : 'Al día') : 'Sin datos'}</strong><span>${stale ? 'puede faltar un foco reciente' : 'dentro de los 30 min'}</span></div>
      <div class="kpi"><small>${dual('último calor visto', 'detección más nueva')}</small><strong class="kpi-text">${newest ? ago(newest) : '—'}</strong><span>${newest ? fmtDateTime(newest) : 'sin datos'}</span></div>
    </div>
    ${status.goes_gap ? html`<div class="callout callout-warn" role="alert"><b>Puede que BRASA no esté viendo todo: faltan barridos del satélite GOES en la última hora.</b>
      Que no aparezca calor no garantiza que no haya fuego.<span class="x-tech"> Faltan ${status.goes_missing} de 6 barridos esperados.</span></div>` : ''}`;
}

function sourcesTable(status) {
  const runs = status.runs || [];
  if (!runs.length) return html`<div class="empty"><div class="glyph">◎</div>Aún no hay ingestas registradas. ${{ interna: 'La primera ocurre al iniciar el servidor.', cron: 'La ingesta corre cada 10 minutos: la primera llegará en unos minutos.' }[status.ingest_mode] || 'La ingesta automática está apagada.'}</div>`;
  return html`<ul class="list">${runs.map((r) => {
    const products = r.product.split(',');
    const newest = products.map((p) => status.newest_observation?.[p]).filter(Boolean).sort().pop();
    const hist = (status.history || {})[r.product] || [];
    const okN = hist.filter((h) => h.ok).length;
    return html`<li>${dot(r.ok)}<div class="grow">
      <b class="small">${r.provider} · ${products.map((p) => PRODUCT_NAMES[p] || p).join(' + ')}</b>
      <div class="tiny muted">${r.ok ? `Corrida correcta ${ago(r.finished_at)}` : `Falló ${ago(r.finished_at || r.started_at)}`} · último éxito ${r.last_ok_at ? ago(r.last_ok_at) : 'sin datos'}</div>
      <div class="tiny muted">${r.ok ? `${fmtNum(r.n_records)} registros, ${fmtNum(r.n_new)} nuevos` : (r.message || 'sin detalle')}${newest ? ` · dato más nuevo ${ago(newest)}` : ''}${r.ok && r.message ? ` · ${r.message}` : ''}</div>
      ${hist.length ? html`<div class="tiny muted" title="Las 20 corridas más recientes, la última a la izquierda">${okN} de ${hist.length} corridas correctas</div><div style="display:flex;gap:0;align-items:center;margin-top:4px">${histDots(hist)}</div>` : ''}</div>
      <span class="status-badge st-${r.ok ? 'tranquilo' : 'aviso'}">${r.ok ? 'correcta' : 'falló'}</span></li>`;
  })}</ul>
  <p class="tiny muted">GOES llega con ~10–20 min de retraso; VIIRS (NOAA-20/21) pasa sobre Chile unas 2 veces al día por satélite y llega con ~1–3 h de retraso.${status.firms_configured ? '' : ' Sin clave NASA FIRMS, VIIRS/MODIS no se ingieren.'}</p>`;
}

function sweeps(status) {
  const list = status.goes_sweeps || [];
  return html`<h2 class="section">${dual('Barridos del satélite GOES-19', 'Barridos GOES · últimas corridas')} <span class="tag">${dual('se esperan 6 por hora', '1 cada 10 min')}</span></h2>
    <p class="small x-plain">GOES-19 mira el disco completo cada 10 minutos: en una hora deberían llegar 6 barridos. ${status.goes_missing ? `En la última hora faltan ${status.goes_missing}.` : 'En la última hora no falta ninguno.'}</p>
    ${list.length ? html`<ul class="list">${list.map((s) => html`<li>${dot(s.ok)}<div class="grow"><b class="small">${s.ok ? 'Barrido recibido' : 'Barrido falló'}</b>
      <div class="tiny muted">${ago(s.started_at)} · ${fmtDateTime(s.started_at)}</div><div class="tiny muted x-tech">${s.source_ref}</div></div></li>`)}</ul>` : html`<p class="small muted">Aún no hay barridos registrados.</p>`}`;
}

function openIncidents(status) {
  const open = status.incidents_open || {};
  const rows = OPEN_ORDER.filter((s) => open[s]).map((s) => {
    const info = incidentInfo({ status: s });
    return html`<li><span class="status-badge st-${info.tone}">${info.short}</span><div class="grow"><b class="small">${info.title}</b><div class="tiny muted">${info.text}</div></div><span class="small tabular">${fmtNum(open[s])}</span></li>`;
  });
  return html`<h2 class="section">Incidentes abiertos</h2>
    <p class="small x-plain">Lo que BRASA está siguiendo ahora mismo, por estado. Las cifras salen de la misma base que el mapa.</p>
    ${rows.length ? html`<ul class="list">${rows}</ul>` : html`<div class="empty"><div class="glyph">◎</div>No hay incidentes abiertos.</div>`}`;
}

function licenses() {
  const block = (items) => html`<ul class="list">${items.map(([name, note]) => html`<li><div class="grow"><b class="small">${name}</b><div class="tiny muted">${note}</div></div></li>`)}</ul>`;
  return html`<h2 class="section">Licencia y atribución de cada capa</h2>
    <p class="small">Todo lo que BRASA muestra indica su fuente y su hora. Esto es lo que viene de terceros y bajo qué condiciones se usa; más abajo, lo que BRASA calcula por su cuenta. El detalle completo está en <a href="https://github.com/falopass/brasas/blob/main/docs/FUENTES.md" target="_blank" rel="noopener">docs/FUENTES.md</a>.</p>
    <h3 class="small" style="margin:12px 0 2px">Datos de terceros</h3>
    ${block(THIRD_PARTY)}
    <h3 class="small" style="margin:12px 0 2px">Cálculo propio de BRASA</h3>
    ${block(OWN_WORK)}
    <p class="tiny muted" style="margin-top:12px">Pendiente: autorización formal de CONAF para redistribuir el Botón Rojo y el reporte de incendios; mientras tanto se citan con nombre y enlace. Una detección térmica no confirma un incendio y su ausencia no garantiza que no haya fuego.</p>`;
}

function render(status) {
  return html`<h1 class="view-title">Calidad de los datos</h1>
    <p class="lede">${dual('De dónde salen los datos, si llegan a tiempo y bajo qué licencia se usan: la transparencia hecha vista.', 'Estado de /api/status por fuente: última corrida, último éxito, historial reciente, barridos GOES, incidentes abiertos y atribución de cada capa.')}</p>
    ${summary(status)}
    <h2 class="section">${dual('Cada fuente, con su estado', 'Fuentes y corridas de ingesta')}</h2>
    ${sourcesTable(status)}
    ${sweeps(status)}
    ${openIncidents(status)}
    ${licenses()}
    <p class="tiny muted" style="margin-top:14px">Esta página solo muestra el estado de las fuentes y conteos: no hay ubicaciones de personas ni datos de suscriptores.</p>`;
}

let unsubs = [];
export default {
  id: 'calidad',
  nav: false, // sin lugar en la barra de 320 px: se entra por la píldora de estado y por URL
  sheet: 'full',
  async mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    let history = {};
    const paint = (status) => { container.innerHTML = String(render({ ...status, history })); };
    try {
      const status = await api.status(20);
      history = status.history || {};
      paint(status);
    } catch (err) {
      container.innerHTML = String(html`<h1 class="view-title">Calidad de los datos</h1>
        <div class="empty"><div class="glyph">◎</div>No se pudo consultar el estado de las fuentes. Revisa tu conexión y vuelve a intentarlo.</div>`);
      toast(err.message, 'error');
    }
    // La píldora refresca /api/status cada minuto: esta vista aprovecha ese dato y conserva el historial ya pedido.
    unsubs = [store.on('status', (status) => { if (status) keepPlace(container, () => paint(status)); })];
  },
  unmount() { unsubs.forEach((u) => u()); unsubs = []; },
};
