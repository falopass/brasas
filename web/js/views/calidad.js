/* Calidad de los datos (QA-05): la transparencia como una vista. El estado en vivo de cada
 * fuente (última corrida, último éxito, resultado y mensaje, con el historial reciente de
 * /api/status?history=20), el cupo de FIRMS y el de Open-Meteo, los errores de la última ronda,
 * los barridos de GOES-19, los incidentes abiertos por estado, la opinión agregada sobre los
 * avisos (/api/quality/feedback) y la licencia de cada capa (docs/FUENTES.md). Solo estado de
 * fuentes y conteos: aquí no hay datos de personas. */
import { api, request } from '../api.js';
import { advice, run as correrChequeo, summarize } from '../autochequeo.js';
import { show } from '../map.js';
import { store } from '../store.js';
import { phonesHtml } from '../ui.js';
import { $, ago, dual, fmtDateTime, fmtNum, html, keepPlace, parseUTC, raw, toast } from '../util.js';
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

/** Mediana de minutos legible: «45 min», «2,5 h», «3 días». Sin dato → «—». */
const fmtSpan = (m) => (!Number.isFinite(m) ? '—'
  : m < 90 ? `${fmtNum(Math.round(m))} min`
  : m < 2880 ? `${fmtNum(m / 60, 1)} h`
  : `${fmtNum(m / 1440, 1)} días`);

const dot = (ok) => html`<span class="dot" style="background:${ok ? 'var(--risk-bajo)' : 'var(--risk-extremo)'}"></span>`;
/** Tirita de corridas recientes: la más nueva a la izquierda. `history` solo trae ok/started_at, ya escapada. */
const histDots = (hist) => raw(hist.slice(0, 20)
  .map((h) => `<span class="dot" style="width:6px;height:6px;background:${h.ok ? 'var(--risk-bajo)' : 'var(--risk-extremo)'}"></span>`)
  .join('<span style="display:inline-block;width:3px"></span>'));

/** Marca de tiempo en ms; NaN si falta o no se puede leer (así nunca llega un NaN a pantalla). */
const ts = (s) => {
  if (typeof s !== 'string' || !s) return NaN;
  try { return parseUTC(s).getTime(); } catch { return NaN; }
};
/** Duración breve: «38 s» bajo 2 minutos; desde ahí reutiliza fmtSpan («3 min», «1,2 h»). */
const fmtDur = (s) => (s < 120 ? `${fmtNum(Math.round(s))} s` : fmtSpan(s / 60));

/* CAL-21: la portada puede decir «Actualizado hace 5 min» hablando de los satélites mientras el
 * peligro que ve el vecino tiene horas. Estas dos funciones puras separan la edad del riesgo de
 * la del respaldo; sin marca dicen «sin dato», nunca «al día», y no muestran la excepción cruda. */
export function edadDelRiesgo(status = {}) {
  const fallo = status.last_cycle?.risk_error === true;
  const when = status.risk_computed_at;
  if (!when) return { valor: 'sin dato', detalle: 'todavía no hay una marca del cálculo', fallo };
  return {
    valor: ago(when),
    detalle: fallo ? 'falló el último cálculo' : `calculado ${fmtDateTime(when)}`,
    fallo,
  };
}

/* AUTO-03/AUTO-07: el diagnóstico en una frase por fuente. `recovered` lee el historial
 * de /api/status?history=N (el más nuevo primero) y distingue «sigue fallando» de
 * «falló y se recuperó sola»; `diagnostico` arma la lista de problemas con su arreglo. */

/** {episodes, lastFailedAt, failingNow, longestMin} de un historial ok/started_at, más nuevo primero.
 * Episodio = racha de fallos seguida en el tiempo de una corrida correcta; una racha que
 * llega hasta el elemento más nuevo cuenta como «sigue fallando», no como recuperada. */
export function recovered(hist = []) {
  const ceros = { episodes: 0, lastFailedAt: null, failingNow: false, longestMin: null };
  if (!Array.isArray(hist) || !hist.length) return ceros;
  const rachas = [];
  let i = 0;
  while (i < hist.length) {
    if (hist[i].ok === false) {
      let j = i;
      while (j + 1 < hist.length && hist[j + 1].ok === false) j += 1;
      rachas.push([i, j]);
      i = j + 1;
    } else {
      i += 1;
    }
  }
  let episodes = 0;
  let longestMin = null;
  for (const [a, b] of rachas) {
    if (a === 0 || hist[a - 1].ok === false) continue; // no hay un éxito posterior que la cierre
    episodes += 1;
    const t1 = ts(hist[a - 1].started_at);
    const t0 = ts(hist[b].started_at);
    if (Number.isFinite(t0) && Number.isFinite(t1)) {
      longestMin = Math.max(longestMin ?? 0, Math.abs(t1 - t0) / 60000);
    }
  }
  return {
    episodes,
    lastFailedAt: hist.find((h) => h.ok === false)?.started_at ?? null,
    failingNow: hist[0].ok === false,
    longestMin,
  };
}

/** Frase corta del estado de una fuente a partir de su historial; null si no hay datos. */
export function lineaRecuperacion(hist, longestGapMin = null) {
  const r = recovered(hist);
  if (!hist?.length) return null;
  if (r.failingNow) return 'Sigue fallando ahora: se reintenta en la próxima corrida.';
  if (r.episodes > 0) {
    const ultima = r.longestMin != null ? `; la falla más larga duró ${fmtSpan(r.longestMin)}` : '';
    return `Se recuperó sola ${r.episodes} ${r.episodes === 1 ? 'vez' : 'veces'}${ultima}.`;
  }
  return `Sin fallas en las últimas ${hist.length} corridas.`;
}

/** Lista de problemas actuales {clave, gravedad, titulo, detalle, arreglo}; [] si no hay nada. */
export function diagnostico(status = {}) {
  const problemas = [];
  const edadMs = status.last_ingest_at ? Date.now() - ts(status.last_ingest_at) : NaN;
  if (status.freshness?.stale === true || (Number.isFinite(edadMs) && edadMs > 30 * 60 * 1000)) {
    problemas.push({ clave: 'datos_viejos', gravedad: 'alta', titulo: 'Los datos están atrasados',
      detalle: 'la última lectura de las fuentes tiene más de 30 minutos',
      arreglo: 'Los datos de los satélites están atrasados: que no veamos calor no significa que no haya fuego. La ingesta reintenta sola.' });
  }
  for (const [producto, hist] of Object.entries(status.history || {})) {
    if (Array.isArray(hist) && hist.slice(0, 3).length === 3 && hist.slice(0, 3).every((h) => h.ok === false)) {
      const nombre = PRODUCT_NAMES[producto] || producto;
      problemas.push({ clave: `fuente_caida:${producto}`, gravedad: 'alta', titulo: `${nombre} está fallando`,
        detalle: 'las últimas 3 corridas de esa fuente terminaron en error',
        arreglo: `Estamos reintentando la consulta a ${nombre}; pueden faltar datos de las últimas horas.` });
    }
  }
  if (status.last_cycle?.backup === false) {
    problemas.push({ clave: 'respaldo', gravedad: 'media', titulo: 'El respaldo de la base falló',
      detalle: 'la copia de seguridad de la última ronda no se completó',
      arreglo: 'El respaldo se reintenta en la próxima ronda; no cambia lo que ves, pero conviene revisarlo.' });
  }
  if (status.ingest_mode === 'apagada') {
    problemas.push({ clave: 'ingesta_apagada', gravedad: 'alta', titulo: 'La actualización automática está apagada',
      detalle: 'este servidor no renueva las fuentes por sí solo',
      arreglo: 'La actualización automática de las fuentes está apagada en este servidor: los datos solo cambian cuando alguien la enciende.' });
  }
  return problemas;
}

/** Texto plano para «Copiar diagnóstico»: fecha, versión, problemas y conteos por producto.
 * Nunca lleva tokens ni claves; tope 4000 caracteres. */
export function diagnosticoTexto(status = {}) {
  const problemas = diagnostico(status);
  const lineas = [`Diagnóstico de BRASA Chile — ${new Date().toISOString().slice(0, 16)}Z`];
  if (status.version) lineas.push(`Versión: ${status.version}`);
  lineas.push(problemas.length ? 'Problemas:' : 'Sin problemas: todo al día.');
  for (const p of problemas) lineas.push(`- [${p.gravedad}] ${p.titulo} — ${p.detalle}. Arreglo: ${p.arreglo}`);
  for (const [producto, hist] of Object.entries(status.history || {})) {
    if (Array.isArray(hist) && hist.length) {
      lineas.push(`${PRODUCT_NAMES[producto] || producto}: ${hist.filter((h) => h.ok).length} de ${hist.length} corridas correctas`);
    }
  }
  return lineas.join('\n').slice(0, 4000);
}

export function respaldoTexto(status = {}) {
  const b = status.backup || {};
  const fallo = status.last_cycle?.backup === false;
  if (fallo) return { valor: 'falló', detalle: 'el respaldo de anoche falló', fallo: true };
  if (b.bytes == null || !b.updated_at) {
    return { valor: 'sin dato', detalle: 'el servidor no publica el tamaño ni la fecha del respaldo', fallo: true };
  }
  return { valor: ago(b.updated_at), detalle: `${fmtNum(b.bytes)} bytes en el respaldo`, fallo: false };
}

/** Bloque «El peligro de hoy»: edad del riesgo, si el último cálculo falló y cómo va el respaldo. */
function peligroDeHoy(status) {
  const riesgo = edadDelRiesgo(status);
  const respaldo = respaldoTexto(status);
  return html`<h2 class="section">${dual('El peligro de hoy', 'Cálculo del riesgo y respaldo de la base')}</h2>
    <p class="small x-plain">El nivel de peligro que ves en el mapa se calcula aparte de los satélites: si esa cuenta falla, el dato se queda con la hora del último cálculo bueno.</p>
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>${dual('última vez que se calculó', 'risk_computed_at')}</small><strong class="kpi-text">${riesgo.valor}</strong><span>${riesgo.detalle}</span></div>
      <div class="kpi"><small>${dual('el último cálculo', 'last_cycle.risk_error')}</small><strong class="kpi-text">${riesgo.fallo ? 'falló' : (status.risk_computed_at ? 'terminó' : 'sin dato')}</strong><span>${riesgo.fallo ? 'falló el último cálculo' : (status.risk_computed_at ? 'sin errores en el último ciclo' : 'no hay marca del cálculo')}</span></div>
      <div class="kpi"><small>${dual('respaldo de la base', 'backup a R2')}</small><strong class="kpi-text">${respaldo.valor}</strong><span>${respaldo.detalle}</span></div>
    </div>
    ${riesgo.fallo ? html`<p class="small" style="margin-top:8px"><b>Qué hacer:</b> el peligro se recalcula cada 3 h; si sigue fallando, revisa en la página del proyecto el <a href="https://github.com/falopass/brasas/issues?q=is%3Aissue+is%3Aopen+label%3Amonitoreo" target="_blank" rel="noopener">issue de monitoreo ↗</a>.</p>` : ''}
    ${respaldo.fallo ? html`<p class="small" style="margin-top:8px"><b>Qué hacer:</b> el respaldo protege la base; no cambia lo que ves.</p>` : ''}`;
}

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
  if (!runs.length) return html`<div class="empty"><div class="glyph">◎</div>Aún no hay ingestas registradas. ${{ interna: 'La primera ocurre al iniciar el servidor.', cron: 'La ingesta corre cada 10 minutos: la primera ocurre en unos minutos.' }[status.ingest_mode] || 'La ingesta automática está apagada.'}</div>`;
  return html`<ul class="list">${runs.map((r) => {
    const products = r.product.split(',');
    const newest = products.map((p) => status.newest_observation?.[p]).filter(Boolean).sort().pop();
    const hist = (status.history || {})[r.product] || [];
    const okN = hist.filter((h) => h.ok).length;
    const times = hist.map((h) => ts(h.started_at)).filter(Number.isFinite);
    const gaps = times.slice(1).map((t, i) => Math.abs(t - times[i]) / 60000);
    const gapMin = gaps.length ? Math.max(...gaps) : NaN;
    const durS = (ts(r.finished_at) - ts(r.started_at)) / 1000;
    const durTxt = Number.isFinite(durS) && durS >= 0 ? fmtDur(durS) : null;
    return html`<li>${dot(r.ok)}<div class="grow">
      <b class="small">${r.provider} · ${products.map((p) => PRODUCT_NAMES[p] || p).join(' + ')}</b>
      <div class="tiny muted">${r.ok ? `Corrida correcta ${ago(r.finished_at)}` : `Falló ${ago(r.finished_at || r.started_at)}`} · último éxito ${r.last_ok_at ? ago(r.last_ok_at) : 'sin datos'}</div>
      <div class="tiny muted">${r.ok ? `${fmtNum(r.n_records)} registros, ${fmtNum(r.n_new)} nuevos` : (r.message || 'sin detalle')}${newest ? ` · dato más nuevo ${ago(newest)}` : ''}${r.ok && r.message ? ` · ${r.message}` : ''}</div>
      ${hist.length ? html`<div class="tiny muted" title="Las 20 corridas más recientes, la última a la izquierda">${okN} de ${hist.length} corridas correctas${Number.isFinite(gapMin) ? html` · ${dual('hueco más largo', 'hueco máx. entre corridas')}: ${fmtSpan(gapMin)}` : ''}${durTxt ? html` · ${dual('la última tardó', 'duración última corrida')}: ${durTxt}` : ''}</div><div style="display:flex;gap:0;align-items:center;margin-top:4px">${histDots(hist)}</div>
      <div class="tiny muted">${dual(lineaRecuperacion(hist), lineaRecuperacion(hist))}</div>` : ''}</div>
      <span class="status-badge st-${r.ok ? 'tranquilo' : 'aviso'}">${r.ok ? 'correcta' : 'falló'}</span></li>`;
  })}</ul>
  <p class="tiny muted">GOES llega con ~10–20 min de retraso; VIIRS (NOAA-20/21) pasa sobre Chile unas 2 veces al día por satélite y llega con ~1–3 h de retraso.${status.firms_configured ? '' : ' Sin clave NASA FIRMS, VIIRS/MODIS no se ingieren.'}</p>`;
}

/* Cupo de la clave FIRMS (DAT-01): /api/status ya publica el último consumo conocido de la
 * clave en su ventana de 10 minutos (el servidor lo consulta a FIRMS a lo sumo cada 45 min).
 * Cerca del tope las corridas de VIIRS/MODIS empiezan a fallar con 429; sin clave o sin
 * lectura se dice «sin dato» y por qué, nunca una cifra inventada. */
export function firmsQuota(status) {
  const q = status.firms_quota || {};
  const head = html`<h3 class="small" style="margin:12px 0 2px">${dual('Cupo de la clave de NASA FIRMS', 'Cupo de la clave FIRMS · ventana de 10 min')}</h3>`;
  const limit = Number(q.limit);
  const used = Number(q.used);
  if (!status.firms_configured || q.error || !Number.isFinite(limit) || !Number.isFinite(used) || limit <= 0) {
    const why = !status.firms_configured
      ? 'este servidor no tiene clave de NASA FIRMS configurada, así que VIIRS y MODIS no se ingieren'
      : q.error
        ? `la última consulta a FIRMS falló o quedó atrasada${q.checked_at ? ` (lectura de ${ago(q.checked_at)})` : ''}; se reintenta cada 45 minutos`
        : 'FIRMS aún no ha entregado una lectura de esta ventana';
    return html`${head}<p class="small muted">Sin dato del cupo: ${why}.</p>`;
  }
  const pct = Math.round((100 * used) / limit);
  return html`${head}
    <p class="small">${fmtNum(used)} de ${fmtNum(limit)} transacciones en la ventana de 10 minutos (${fmtNum(pct)} %), consultado ${ago(q.checked_at)}.</p>
    ${used >= 0.8 * limit ? html`<div class="callout callout-warn" role="alert"><b>La clave de FIRMS está cerca de su tope: ${fmtNum(pct)} % usado.</b>
      Si se agota, las corridas de VIIRS y MODIS fallan con error 429 y deja de verse el calor de los satélites polares hasta la ventana siguiente.<span class="x-tech"> El cupo se renueva solo cada 10 minutos y BRASA reintenta la ingesta en el próximo ciclo.</span></div>` : ''}`;
}

/* Cupo diario de Open-Meteo (RISK-14, CALIDAD-02): /api/status publica en `open_meteo` las
 * ubicaciones pedidas hoy contra el tope diario. `locations` cuenta este proceso y
 * `scheduled.total` es el acumulado durable del día (sobrevive a la suspensión del contenedor
 * en Cloudflare): el gasto honesto es el mayor de los dos. Cuando el cupo aprieta se reparte
 * con la prioridad fija pronóstico > FWI > normales > casos, y si se agota el mapa de peligro
 * queda congelado con datos viejos. Sin lectura se dice «sin dato» y por qué, nunca un cero. */
export function openMeteoQuota(status) {
  const om = status.open_meteo || {};
  const head = html`<h3 class="small" style="margin:12px 0 2px">${dual('Cupo diario de Open-Meteo', 'Cupo Open-Meteo · ubicaciones por día')}</h3>`;
  const cap = Number(om.daily_cap);
  const local = Number(om.locations);
  const scheduled = Number(typeof om.scheduled === 'object' && om.scheduled !== null ? om.scheduled.total : om.scheduled);
  if (om.error || !Number.isFinite(cap) || cap <= 0 || !Number.isFinite(local)) {
    return html`${head}<p class="small muted">Sin dato del cupo: el servidor aún no publica el consumo de Open-Meteo de hoy.</p>`;
  }
  const used = Math.max(local, Number.isFinite(scheduled) ? scheduled : 0);
  const pct = Math.round((100 * used) / cap);
  return html`${head}
    <p class="small">${fmtNum(used)} de ${fmtNum(cap)} ubicaciones hoy (${fmtNum(pct)} %).
      ${dual('Si el cupo aprieta se reparte así: primero el pronóstico del peligro, después el índice FWI, la lluvia normal y al final los casos históricos.', 'Prioridad fija del cupo: pronóstico > FWI > normales > casos.')}${om.rate_limited ? ` Open-Meteo ya pidió esperar ${fmtNum(om.rate_limited)} ${om.rate_limited === 1 ? 'vez' : 'veces'} hoy (error 429).` : ''}</p>
    ${used >= 0.8 * cap ? html`<div class="callout callout-warn" role="alert"><b>El cupo diario de Open-Meteo está cerca de su tope: ${fmtNum(pct)} % usado.</b>
      Si se agota, lo primero que queda fuera son los casos históricos y las normales de lluvia, después el FWI, y lo último que se sostiene es el pronóstico: con el cupo vacío el mapa de peligro se congela con datos del día anterior.<span class="x-tech"> El cupo cuenta ubicaciones pedidas por día de Chile y se renueva a medianoche.</span></div>` : ''}`;
}

/* Errores de la última ronda de ingesta (OPS-14, CALIDAD-02): `errors.cycle_errors` trae las
 * claves `*_error` del último ciclo, solo el nombre de la tarea (sin hora ni mensaje: no se
 * inventan). Se traduce a la fuente y se dice qué mirar; sin bloque o con `error`, «sin detalle». */
const CYCLE_ERRORS = {
  risk_error: ['peligro por comuna', 'el mapa de peligro puede quedar con datos atrasados'],
  fwi_error: ['índice FWI', 'la sequía del índice FWI puede quedar atrasada'],
  snapshot_error: ['foto del pronóstico', 'la foto diaria del peligro puede quedar atrasada'],
  rain_error: ['lluvia de la temporada', 'la lluvia acumulada por comuna puede quedar atrasada'],
  dmc_error: ['avisos de la DMC', 'pueden faltar avisos de viento y calor de la Dirección Meteorológica'],
  official_error: ['incendios de CONAF', 'los estados «confirmado» y «controlado» pueden quedar atrasados'],
  boton_rojo_error: ['Botón Rojo de CONAF', 'pueden faltar focos declarados por CONAF'],
  conaf_cond_error: ['condiciones de CONAF', 'las condiciones operativas por región pueden quedar atrasadas'],
  daily_brief_error: ['revisión preventiva', 'los avisos preventivos del día pueden no haber salido'],
  firms_error: ['FIRMS', 'el calor de VIIRS y MODIS puede faltar; sus corridas están más arriba'],
  backfill_error: ['relleno de GOES', 'pueden faltar barridos antiguos del satélite'],
  restore_error: ['restauración', 'el servidor partió sin recuperar sus datos de respaldo'],
  backup_error: ['respaldo', 'la copia de seguridad de la base no salió'],
};
export function ultimosErrores(status) {
  const head = html`<h3 class="small" style="margin:12px 0 2px">Errores de la última ronda de ingesta</h3>`;
  const errors = status.errors;
  if (!errors || errors.error) return html`${head}<p class="small muted">Sin detalle: el servidor no pudo resumir los errores de la última ronda.</p>`;
  const list = Array.isArray(errors.cycle_errors) ? errors.cycle_errors : [];
  if (!list.length) return html`${head}<p class="small muted">La última ronda de ingesta terminó sin errores.</p>`;
  return html`${head}<ul class="list">${list.map((key) => {
    const [name, hint] = CYCLE_ERRORS[key] || [key.replace(/_error$/, '').replace(/_/g, ' '), 'revisa las corridas de más arriba'];
    return html`<li><div class="grow"><b class="small">${name}</b><div class="tiny muted">qué mirar: ${hint}.</div></div></li>`;
  })}</ul>`;
}

function sweeps(status) {
  const list = status.goes_sweeps || [];
  return html`<h2 class="section">${dual('Barridos del satélite GOES-19', 'Barridos GOES · últimas corridas')} <span class="tag">${dual('se esperan 6 por hora', '1 cada 10 min')}</span></h2>
    <p class="small x-plain">GOES-19 mira el disco completo cada 10 minutos: en una hora deberían llegar 6 barridos. ${status.goes_missing ? `En la última hora faltan ${status.goes_missing}.` : 'En la última hora no falta ninguno.'}</p>
    ${list.length ? html`<ul class="list">${list.map((s) => html`<li>${dot(s.ok)}<div class="grow"><b class="small">${s.ok ? 'Barrido recibido' : 'Barrido falló'}</b>
      <div class="tiny muted">${ago(s.started_at)} · ${fmtDateTime(s.started_at)}</div><div class="tiny muted x-tech">${s.source_ref}</div></div></li>`)}</ul>` : html`<p class="small muted">Aún no hay barridos registrados.</p>`}`;
}

/* Radar de respuesta oficial (QA-21): medianas de detección → aviso → despacho calculadas sobre
 * las marcas que publica CONAF en su CSV (GET /api/opendata/response.json). Si el conjunto no
 * responde o viene vacío la sección lo dice, pero nunca rompe el resto de la vista. */
function conafResponse(resp) {
  const head = html`<h2 class="section">Respuesta oficial de CONAF${resp?.season ? html` <span class="tag">temporada ${resp.season}</span>` : ''}</h2>`;
  if (!resp) return html`${head}<p class="small muted">Este resumen no está disponible ahora. El resto de la página no se ve afectado.</p>`;
  const intro = html`<p class="small">${dual('CONAF publica tres marcas por incendio: detección, aviso a los equipos y despacho de recursos. Estas medianas salen de esas marcas declaradas; el reporte no trae la hora en que llegaron al incendio.', resp.method)} ${resp.season ? `Temporada ${resp.season}: ${fmtNum(resp.count)} incendios en el reporte.` : ''}</p>`;
  if (!resp.count) return html`${head}${intro}<div class="empty"><div class="glyph">◎</div>${resp.note || 'Todavía no hay incendios con horas publicadas.'}</div>`;
  const kpi = (plain, tech, key) => {
    const s = resp.overall?.[key] || {};
    return html`<div class="kpi"><small>${dual(plain, tech)}</small>
      <strong class="kpi-text">${fmtSpan(s.median_min)}</strong>
      <span>${fmtNum(s.n)} incendios con ambas marcas</span></div>`;
  };
  const mediana = (s) => (Number.isFinite(s?.median_min) ? `mediana ${fmtSpan(s.median_min)}` : 'sin mediana');
  return html`${head}${intro}
    <div class="kpis" style="margin-top:12px">
      ${kpi('de la detección al aviso', 'detección → aviso', 'detection_to_alert')}
      ${kpi('del aviso al despacho', 'aviso → despacho', 'alert_to_dispatch')}
      ${kpi('de la detección al despacho', 'detección → despacho', 'detection_to_dispatch')}
    </div>
    ${resp.buckets?.length ? html`<h3 class="small" style="margin:12px 0 2px">Según la superficie</h3>
    <ul class="list">${resp.buckets.map((b) => html`<li><div class="grow"><b class="small">Incendios de ${b.bucket.includes('ha') ? b.bucket : `${b.bucket} ha`}</b>
      <div class="tiny muted">${fmtNum(b.n_fires)} en total · detección → aviso: ${mediana(b.detection_to_alert)}</div></div></li>`)}</ul>` : ''}
    ${resp.comunas?.length ? html`<h3 class="small" style="margin:12px 0 2px">Comunas (con 3 o más incendios con marcas)</h3>
    <ul class="list">${resp.comunas.slice(0, 5).map((c) => html`<li><div class="grow"><b class="small">${c.comuna}</b>
      <div class="tiny muted">${fmtNum(c.n)} incendios · detección → aviso: ${mediana(c.detection_to_alert)}</div></div></li>`)}</ul>` : ''}
    <p class="tiny muted" style="margin-top:8px">${resp.excluded ? `Sin marcas calculables: ${fmtNum(resp.excluded)} de ${fmtNum(resp.count)} incendios del reporte. ` : ''}Fuente: <a href="${resp.source_url}" target="_blank" rel="noopener">reporte de incendios de CONAF</a>.</p>`;
}

/* Qué tan rápido llega BRASA (QA-03): minutos de la primera detección a «posible», medidos
 * reproduciendo el caso Viña del Mar 2024 con la regla de agrupación vigente
 * (web/data/calibracion.json, lo genera scripts/local/medir_adelanto.py). Es la medición de
 * un incendio pasado, no una promesa de tiempo de aviso. Si el JSON no carga, la sección no
 * aparece y el resto de la vista sigue igual. */
function adelanto(cal) {
  const s = cal?.summary;
  if (!s || !Number.isFinite(s.median_min)) return '';
  const when = ts(cal.generated_at);
  return html`<h2 class="section">${dual('Qué tan rápido llega BRASA', 'Adelanto medido sobre un caso real')}</h2>
    <p class="small">Al repetir el incendio de Viña del Mar 2024 con la regla de agrupación vigente, así demoró BRASA en declarar cada incidente «posible» desde la primera detección del satélite. Es la medición de un caso histórico, ${dual('no una promesa de cuánto tardará el aviso del próximo incendio', 'no una tasa ni una promesa de tiempo de aviso')}.</p>
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>${dual('lo típico', 'mediana detección → «posible»')}</small><strong class="kpi-text">${fmtSpan(s.median_min)}</strong><span>${fmtNum(s.n_incidents)} incidentes del caso</span></div>
      <div class="kpi"><small>${dual('lo más lento', 'peor caso')}</small><strong class="kpi-text">${fmtSpan(s.max_min)}</strong><span>${dual('el incidente que más tardó', 'incidente más tardío')}</span></div>
      <div class="kpi"><small>${dual('medido el', 'fecha de la medición')}</small><strong class="kpi-text">${Number.isFinite(when) ? fmtDateTime(cal.generated_at) : '—'}</strong><span>${cal.source || ''}</span></div>
    </div>
    <p class="tiny muted" style="margin-top:8px">${dual('«Posible» es el criterio de BRASA, no de CONAF; en vivo se suma el retraso con que llega el dato del satélite.', cal.method || '')} Método y límites en <a href="https://github.com/falopass/brasas/blob/main/docs/CALIBRACION.md" target="_blank" rel="noopener">docs/CALIBRACION.md</a>.</p>`;
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

/* ¿Sirvieron los avisos? (ALR-05): el agregado de /api/quality/feedback, conteos globales sin
 * personas ni avisos identificables. Si el conjunto no responde, la sección lo dice y el resto
 * de la vista sigue igual. */
function sirvieron(fb) {
  const head = html`<h2 class="section">¿Sirvieron los avisos?</h2>
    <p class="small x-plain">Quien recibe un aviso puede opinar una vez desde su historial: «me sirvió», «no me sirvió» o «era una quema». Es la lectura de las personas, ${dual('no cambia los umbrales de BRASA por sí sola', 'un agregado: no ajusta umbrales por sí solo')}.</p>`;
  if (!fb) return html`${head}<p class="small muted">Este resumen no está disponible ahora. El resto de la página no se ve afectado.</p>`;
  if (!fb.total) return html`${head}<div class="empty"><div class="glyph">◎</div>Todavía nadie ha respondido. La opinión aparece en el historial de avisos.</div>`;
  const counts = fb.counts || {};
  const pct = Math.round((100 * (counts.sirvio || 0)) / fb.total);
  const row = (label, n) => html`<li><div class="grow"><b class="small">${label}</b></div><span class="small tabular">${fmtNum(n)}</span></li>`;
  return html`${head}
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>${dual('opiniones recibidas', 'total')}</small><strong class="kpi-text">${fmtNum(fb.total)}</strong><span>${fb.since ? `desde ${fmtDateTime(fb.since)}` : ''}</span></div>
      <div class="kpi"><small>${dual('dijeron «me sirvió»', 'sirvio')}</small><strong class="kpi-text">${fmtNum(pct)} %</strong><span>${fmtNum(counts.sirvio || 0)} de ${fmtNum(fb.total)}</span></div>
    </div>
    <ul class="list" style="margin-top:8px">
      ${row('me sirvió', counts.sirvio || 0)}
      ${row('no me sirvió', counts.no_sirvio || 0)}
      ${row('era una quema', counts.quema || 0)}
    </ul>`;
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

/* FIX-76: las tres consultas que antes morían en `.catch(() => null)` ahora registran su
 * fallo. Un fallo parcial no borra la sección en silencio: se nombra en un aviso y el
 * botón «Reintentar» vuelve a pedir solo lo que falló. */
const EXTRA_SECTIONS = {
  resp: 'tiempos de respuesta de CONAF',
  cal: 'curva de calibración',
  fb: 'opiniones de los avisos',
};

export async function loadExtras(fetchSection, only = null) {
  const keys = only ?? Object.keys(EXTRA_SECTIONS);
  const out = {};
  await Promise.all(keys.map(async (key) => {
    try {
      out[key] = { data: await fetchSection(key) };
    } catch {
      out[key] = { error: true };
    }
  }));
  return out;
}

export function partialNotice(failed = []) {
  if (!failed.length) return '';
  const labels = failed.map((key) => EXTRA_SECTIONS[key]).filter(Boolean);
  return html`<div class="callout callout-warn" role="status">
    <b>No pudimos cargar: ${labels.join(', ')}.</b> Lo demás sigue al día.</div>
    <div class="btn-row" style="margin-top:8px"><button class="btn btn-sm" type="button" data-retry-partial>Reintentar</button></div>`;
}

/* AUTO-03: el veredicto primero — qué falla ahora, qué significa y qué se está haciendo,
 * arriba de las tablas; con «Copiar diagnóstico» para reportarlo sin transcribir. */
function bloqueDiagnostico(status) {
  const problemas = diagnostico(status);
  if (!problemas.length) {
    return html`<p class="small" style="margin-top:12px"><span class="status-badge st-tranquilo">Todo al día</span> Ninguna fuente, el respaldo ni la ingesta reportan problemas ahora.</p>`;
  }
  return html`<div class="callout callout-warn" role="status" style="margin-top:12px"><b>${dual('Ahora mismo hay algo que revisar', `${fmtNum(problemas.length)} problema(s) en el estado`)}.</b>
    <ul class="list" style="margin-top:6px">${problemas.map((p) => html`<li><b class="small">${p.titulo}:</b> <span class="small">${p.detalle}.</span> <span class="tiny muted">${p.arreglo}</span></li>`)}</ul>
    <div class="btn-row" style="margin-top:8px"><button class="btn btn-sm" id="copy-diag">Copiar diagnóstico</button></div></div>`;
}

let autoResult = null; // último «Revisar ahora»: sobrevive al repintado del minuto

/* AUTO-11: el vecino también prueba el producto desde su navegador. */
function autochequeoBloque() {
  return html`<h2 class="section">${dual('Chequeo del producto', 'Sonda a páginas y endpoints desde este navegador')}</h2>
    <p class="small x-plain">Comprueba ahora las páginas y los datos que el vecino usa: cuánto tardan y si responden.</p>
    <div class="btn-row"><button class="btn btn-sm" id="autochk" ${autoResult === 'corriendo' ? 'disabled' : ''}>${autoResult === 'corriendo' ? 'Revisando…' : 'Revisar ahora'}</button></div>
    ${autoResult && autoResult !== 'corriendo' ? html`
    <p class="small" role="status">${autoResult.resumen.ok} de ${autoResult.resumen.total} responden bien${autoResult.resumen.lentos ? ` · ${fmtNum(autoResult.resumen.lentos)} lento(s)` : ''}${autoResult.resumen.fallidos ? ` · ${fmtNum(autoResult.resumen.fallidos)} con error` : ''}${autoResult.resumen.peor ? ` · lo peor: ${autoResult.resumen.peor.target} (${fmtNum(autoResult.resumen.peor.ms)} ms)` : ''}</p>
    <ul class="list">${autoResult.results.map((r) => html`<li><div class="grow"><b class="small">${r.target}</b>
      <div class="tiny muted">${r.ok ? `${r.status} · ${fmtNum(r.ms)} ms` : advice(r)}</div></div>
      <span class="status-badge st-${r.ok && r.ms <= 2500 ? 'tranquilo' : 'aviso'}">${r.ok ? (r.ms > 2500 ? 'lento' : 'ok') : 'falla'}</span></li>`)}</ul>` : ''}`;
}

function render(status, resp, cal, fb, failed = []) {
  return html`<h1 class="view-title">Calidad de los datos</h1>
    <p class="lede">${dual('De dónde salen los datos, si llegan a tiempo, si los avisos sirvieron y bajo qué licencia se usan: la transparencia hecha vista.', 'Estado de /api/status por fuente: última corrida, último éxito, historial reciente, barridos GOES, incidentes abiertos, opinión agregada de los avisos y atribución de cada capa.')}</p>
    ${bloqueDiagnostico(status)}
    ${summary(status)}
    ${peligroDeHoy(status)}
    ${partialNotice(failed)}
    <h2 class="section">${dual('Cada fuente, con su estado', 'Fuentes y corridas de ingesta')}</h2>
    ${sourcesTable(status)}
    ${firmsQuota(status)}
    ${openMeteoQuota(status)}
    ${ultimosErrores(status)}
    ${conafResponse(resp)}
    ${adelanto(cal)}
    ${sweeps(status)}
    ${openIncidents(status)}
    ${sirvieron(fb)}
    ${licenses()}
    ${autochequeoBloque()}
    <p class="tiny muted" style="margin-top:14px">Esta página solo muestra el estado de las fuentes y conteos: no hay ubicaciones de personas ni datos de suscriptores.</p>
    <p class="tiny muted"><a href="/web/preguntas.html">¿Cómo leer estos datos? Preguntas frecuentes</a></p>`;
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
    let lastStatus = null;
    let resp = null;
    let cal = null;
    let fb = null;
    const failed = new Set();
    const paint = (status) => {
      container.innerHTML = String(render({ ...status, history }, resp, cal, fb, [...failed]));
      container.querySelector('#copy-diag')?.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(diagnosticoTexto({ ...status, history }));
          toast('Diagnóstico copiado: pégalo donde quieras reportarlo.');
        } catch { toast('No se pudo copiar: anota los problemas de arriba.', 'error'); }
      });
      container.querySelector('#autochk')?.addEventListener('click', async () => {
        autoResult = 'corriendo';
        paint(status);
        try { autoResult = { results: await correrChequeo(), resumen: null }; autoResult.resumen = summarize(autoResult.results); }
        catch { autoResult = null; toast('No se pudo hacer el chequeo ahora.', 'error'); }
        paint(status);
      });
    };
    const fetchSection = (key) => ({
      resp: () => request('/api/opendata/response.json'),
      cal: () => request('/web/data/calibracion.json'),
      fb: () => request('/api/quality/feedback'),
    })[key]();
    const applyExtras = (extras) => {
      for (const [key, value] of Object.entries(extras)) {
        if (value.error) { failed.add(key); continue; }
        failed.delete(key);
        if (key === 'resp') resp = value.data;
        if (key === 'cal') cal = value.data;
        if (key === 'fb') fb = value.data;
      }
    };
    const load = async (only = null) => {
      try {
        if (!only) {
          lastStatus = await api.status(20);
          history = lastStatus.history || {};
        }
        applyExtras(await loadExtras(fetchSection, only));
        paint(lastStatus);
      } catch (err) {
        // Error con salida (FIX-57): el mismo mensaje, los teléfonos de emergencia y «Reintentar» sobre load().
        container.innerHTML = String(html`<h1 class="view-title">Calidad de los datos</h1>
          <div class="empty"><div class="glyph">◎</div>No se pudo consultar el estado de las fuentes. Revisa tu conexión y vuelve a intentarlo.</div>
          <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-retry>Reintentar</button></div>
          <p class="small" style="margin:12px 0 8px">Si ves fuego o humo cerca, llama de inmediato. No esperes a que lo vea un satélite.</p>
          ${phonesHtml()}`);
        const btn = container.querySelector('[data-retry]');
        btn.addEventListener('click', () => { btn.disabled = true; btn.textContent = 'Reintentando…'; load(); });
        toast(err.message, 'error');
      }
    };
    // Un solo listener sobre el contenedor: el aviso de fallo parcial se repinta y su botón
    // debe seguir funcionando sin volver a enganchar nada.
    container.addEventListener('click', (event) => {
      const btn = event.target.closest?.('[data-retry-partial]');
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      btn.textContent = 'Reintentando…';
      load([...failed]);
    });
    await load();
    // La píldora refresca /api/status cada minuto: esta vista aprovecha ese dato y conserva el historial ya pedido.
    unsubs = [store.on('status', (status) => { if (status) keepPlace(container, () => paint(status)); })];
  },
  unmount() { unsubs.forEach((u) => u()); unsubs = []; },
};
