/* Calidad de los datos (QA-05): estado en vivo de cada fuente (última corrida, éxito,
 * resultado y mensaje de /api/status?history=20), cupos de FIRMS y Open-Meteo, errores de
 * la última ronda, barridos GOES-19, incidentes por estado, opinión agregada de los avisos
 * (/api/quality/feedback), los tiempos del servidor en la última hora, la concordancia del
 * índice con CONAF y la licencia de cada capa (docs/FUENTES.md). Sin datos de personas. */
import { api, request } from '../api.js';
import { advice, run as correrChequeo, summarize } from '../autochequeo.js';
import { errorConSalidaHtml } from '../errores.js';
import { show } from '../map.js';
import { store } from '../store.js';
import { phonesHtml } from '../ui.js';
import { $, ago, dual, fmtDateTime, fmtNum, html, keepPlace, parseUTC, raw, storage, toast } from '../util.js';
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

/* CAL-21: la portada puede decir «Actualizado hace 5 min» (satélites) mientras el peligro del
 * vecino tiene horas. Estas funciones separan ambas edades; sin marca, «sin dato». */
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

/* AUTO-03/AUTO-07: diagnóstico en una frase por fuente. `recovered` distingue «sigue
 * fallando» de «se recuperó sola»; `diagnostico` arma la lista con su arreglo. */

/** {episodes, lastFailedAt, failingNow, longestMin} de un historial ok/started_at, más nuevo primero.
 * Episodio = racha de fallos; si llega hasta el elemento más nuevo, «sigue fallando». */
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

/* Cupo de la clave FIRMS (DAT-01): /api/status publica el último consumo conocido en su
 * ventana de 10 min (consulta a FIRMS a lo sumo cada 45 min). Cerca del tope las corridas
 * VIIRS/MODIS fallan con 429; sin lectura, «sin dato» y por qué, nunca una cifra inventada. */
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

/* Cupo diario de Open-Meteo (RISK-14, CALIDAD-02): `locations` cuenta este proceso y
 * `scheduled.total` es el acumulado durable del día (sobrevive la suspensión del contenedor):
 * el gasto honesto es el mayor. Si el cupo aprieta se reparte con prioridad pronóstico > FWI >
 * normales > casos; si se agota, el mapa de peligro queda congelado. Sin lectura, «sin dato». */
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

/* Errores de la última ronda (OPS-14, CALIDAD-02): `errors.cycle_errors` trae las claves
 * `*_error` del último ciclo, solo el nombre de la tarea. Se traduce a la fuente y se dice
 * qué mirar; sin bloque o con `error`, «sin detalle». */
const CYCLE_ERRORS = {
  risk_error: ['peligro por comuna', 'el mapa de peligro puede quedar con datos atrasados'],
  fwi_error: ['índice FWI', 'la sequía del índice FWI puede quedar atrasada'],
  snapshot_error: ['foto del pronóstico', 'la foto diaria del peligro puede quedar atrasada'],
  rain_error: ['lluvia de la temporada', 'la lluvia acumulada por comuna puede quedar atrasada'],
  dmc_error: ['avisos de la DMC', 'pueden faltar avisos de viento, calor, lluvia o tormenta de la Dirección Meteorológica'],
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

/* Radar de respuesta oficial (QA-21): medianas detección → aviso → despacho sobre las marcas
 * del CSV de CONAF (/api/opendata/response.json). Si no responde o viene vacío, la sección
 * lo dice sin romper el resto de la vista. */
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

/* Licencias y atribución (PERF-07): las filas viven en web/data/licencias.json, copia fiel de
 * docs/FUENTES.md (revisado en octubre de 2026). Si el archivo no llega, la sección muestra el
 * aviso con «Reintentar» y los teléfonos en vez de quedar vacía, y el resto de la vista sigue. */
function licenses(lic, licErr) {
  const nota = (note) => String(note).split(/(https:\/\/[^\s),;]+)/g).map((part) => (
    part.startsWith('https://') ? html`<a href="${part}" target="_blank" rel="noopener" style="overflow-wrap:anywhere">${part}</a>` : part
  ));
  const block = (items) => html`<ul class="list">${items.map(([name, note]) => html`<li><div class="grow"><b class="small">${name}</b><div class="tiny muted">${nota(note)}</div></div></li>`)}</ul>`;
  return html`<h2 class="section">Licencia y atribución de cada capa</h2>
    <p class="small">Todo lo que BRASA muestra indica su fuente y su hora. Esto es lo que viene de terceros y bajo qué condiciones se usa; más abajo, lo que BRASA calcula por su cuenta. El detalle completo está en <a href="https://github.com/falopass/brasas/blob/main/docs/FUENTES.md" target="_blank" rel="noopener">docs/FUENTES.md</a>.</p>
    ${licErr ? raw(errorConSalidaHtml(licErr)) : lic ? html`
    <h3 class="small" style="margin:12px 0 2px">Datos de terceros</h3>
    ${block(lic.terceros)}
    <h3 class="small" style="margin:12px 0 2px">Cálculo propio de BRASA</h3>
    ${block(lic.propios)}` : html`<p class="small muted">Cargando…</p>`}
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

export function partialNotice(failed = [], sinActualizar = false) {
  if (!failed.length) return '';
  const labels = failed.map((key) => EXTRA_SECTIONS[key]).filter(Boolean);
  // Con el estado venido de una copia vieja no se puede afirmar «al día».
  return html`<div class="callout callout-warn" role="status">
    <b>No pudimos cargar: ${labels.join(', ')}.</b> ${sinActualizar ? 'Lo demás es del último estado conocido.' : 'Lo demás sigue al día.'}</div>
    <div class="btn-row" style="margin-top:8px"><button class="btn btn-sm" type="button" data-retry-partial>Reintentar</button></div>`;
}

/* AUTO-03: el veredicto primero — qué falla ahora, qué significa y qué se está haciendo,
 * arriba de las tablas; con «Copiar diagnóstico» para reportarlo sin transcribir.
 * Con `sinActualizar` el estado viene de una copia vieja: no se afirma «ahora» ni
 * «al día», solo lo último conocido con su hora. */
export function bloqueDiagnostico(status, sinActualizar = false) {
  const problemas = diagnostico(status);
  if (!problemas.length) {
    if (sinActualizar) {
      return html`<p class="small" style="margin-top:12px"><span class="status-badge st-aviso">Sin actualizar</span> ${dual(`Último estado conocido (${ago(status.time_utc)}): sin problemas reportados.`, `Estado de ${fmtDateTime(status.time_utc)}: ninguna fuente, el respaldo ni la ingesta reportaban problemas.`)}</p>`;
    }
    return html`<p class="small" style="margin-top:12px"><span class="status-badge st-tranquilo">Todo al día</span> Ninguna fuente, el respaldo ni la ingesta reportan problemas ahora.</p>`;
  }
  const titulo = sinActualizar
    ? dual(`Último estado conocido (${ago(status.time_utc)}): había algo que revisar`, `${fmtNum(problemas.length)} problema(s) en el estado de ${fmtDateTime(status.time_utc)}`)
    : dual('Ahora mismo hay algo que revisar', `${fmtNum(problemas.length)} problema(s) en el estado`);
  return html`<div class="callout callout-warn" role="status" style="margin-top:12px"><b>${titulo}.</b>
    <ul class="list list-diag" style="margin-top:6px">${problemas.map((p) => html`<li><b class="small">${p.titulo}:</b> <span class="small">${p.detalle}.</span> <span class="tiny muted">${p.arreglo}</span></li>`)}</ul>
    <div class="btn-row" style="margin-top:8px"><button class="btn btn-sm" id="copy-diag">Copiar diagnóstico</button></div></div>`;
}

/* CALIDAD-OBS: p50/p95 de GET /api/observability/routes. Sin ventana, no se inventa un milisegundo. */
const ms = (n) => (Number.isFinite(Number(n)) ? `${fmtNum(Number(n))} ms` : 'sin dato');
export function latenciasRutas(obs = null) {
  const head = html`<h2 class="section">Tiempos de respuesta del servidor (última hora)</h2>`;
  if (!obs || !Array.isArray(obs.routes)) {
    return html`${head}<p class="small muted">Este resumen no está disponible ahora. El resto de la página no se ve afectado.</p>`;
  }
  const routes = obs.routes;
  const total = Number.isFinite(Number(obs.n))
    ? Number(obs.n)
    : routes.reduce((sum, row) => sum + (Number(row.n) || 0), 0);
  const mostradas = routes.slice(0, 8);
  const sencillo = total
    ? `En la última hora el servidor atendió ${fmtNum(total)} ${total === 1 ? 'consulta' : 'consultas'}. Lo típico tardó ${ms(obs.p50_ms)} y el 95 % más rápido tardó ${ms(obs.p95_ms)} o menos.`
    : 'En la última hora el servidor no registró consultas, así que no hay un tiempo típico que mostrar.';
  const detallado = total
    ? `${fmtNum(total)} peticiones en la ventana · p50 ${ms(obs.p50_ms)} · p95 ${ms(obs.p95_ms)} · ${fmtNum(mostradas.length)} de ${fmtNum(routes.length)} rutas, las de p95 más alto.`
    : 'Ventana de 60 minutos sin muestras en este proceso.';
  const filas = mostradas.map((row) => html`<li><div class="grow"><b class="small">${row.path}</b>
    <div class="tiny muted">${fmtNum(row.n)} peticiones · p50 ${fmtNum(row.p50_ms)} ms · p95 ${fmtNum(row.p95_ms)} ms · 4xx ${fmtNum(row.errors_4xx || 0)} · 5xx ${fmtNum(row.errors_5xx || 0)}</div></div></li>`);
  return html`${head}
    <p class="small">${dual(sencillo, detallado)}</p>
    ${filas.length ? html`<ul class="list x-tech">${filas}</ul>` : ''}
    ${obs.aviso ? html`<p class="tiny muted x-tech">${obs.aviso}</p>` : ''}`;
}

/* RISK-09: concordancia del índice con CONAF. null no es 0: Number(null) === 0 y se vería como «0 %». */
const esNumero = (value) => typeof value === 'number' && Number.isFinite(value);
const tasaTxt = (rate) => (esNumero(rate) ? `${fmtNum(rate * 100, 1)} %` : 'sin dato');
const liftTxt = (value) => (esNumero(value) ? fmtNum(value, 2) : 'sin dato');
export function concordanciaRiesgo(conc = null) {
  const head = html`<h2 class="section">Concordancia del índice de peligro con CONAF</h2>`;
  if (!conc || conc.error) {
    return html`${head}<p class="small muted">Este resumen no está disponible ahora. El resto de la página no se ve afectado.</p>`;
  }
  if (conc.dias_riesgo === 0) {
    return html`${head}<p class="small">Todavía no hay suficientes días acumulados en este servidor para medir la concordancia.</p>${fuentesConcordancia(conc)}`;
  }
  const ae = conc.alto_extremo?.level_combined || {};
  const diasAlto = Number(ae.dias) || 0;
  const conBr = Number(ae.dias_con_boton_rojo) || 0;
  const incendios = Number(ae.con_incendio) || 0;
  const conDato = Number(ae.eventos_con_dato) || 0;
  const fraseBr = diasAlto
    ? `De ${fmtNum(diasAlto)} ${diasAlto === 1 ? 'día comuna' : 'días comuna'} con peligro alto o extremo, ${fmtNum(conBr)} coincidieron con el Botón Rojo de CONAF (${tasaTxt(ae.coincidencia_boton_rojo)}).`
    : 'En los días acumulados todavía no hay peligro alto o extremo, así que no hay una tasa de coincidencia con el Botón Rojo.';
  const fraseFuego = conDato
    ? `De ${fmtNum(conDato)} ${conDato === 1 ? 'incendio comuna-día' : 'incendios comuna-día'} del reporte de CONAF en un día con pronóstico, ${fmtNum(incendios)} ${incendios === 1 ? 'empezó' : 'empezaron'} en un día alto o extremo (${tasaTxt(ae.proporcion_incendios)}).`
    : 'Todavía no hay incendios del reporte de CONAF en un día con pronóstico, así que no hay una proporción que mostrar.';
  const niveles = ['bajo', 'moderado', 'alto', 'extremo'];
  const combinado = conc.clases?.level_combined || {};
  const filas = niveles.map((nivel) => {
    const celda = combinado[nivel] || {};
    return html`<li><div class="grow"><b class="small">${nivel}</b>
      <div class="tiny muted">${fmtNum(celda.dias || 0)} días · ${fmtNum(celda.con_incendio || 0)} con incendio · tasa ${tasaTxt(celda.tasa)} · lift ${liftTxt(celda.lift)}</div></div></li>`;
  });
  const clases = [
    ['30-30-30', conc.alto_extremo?.level],
    ['combinado', conc.alto_extremo?.level_combined],
    ['FWI', conc.alto_extremo?.fwi_level],
  ].map(([nombre, bloque]) => {
    const b = bloque || {};
    return `${nombre}: ${fmtNum(b.dias || 0)} días alto o extremo, tasa ${tasaTxt(b.tasa)}, lift ${liftTxt(b.lift)}`;
  }).join(' · ');
  const brDias = Number(conc.dias_boton_rojo) || 0;
  const brAlto = Number(conc.boton_rojo_en_alto_extremo) || 0;
  const detallado = brDias
    ? `${clases}. De ${fmtNum(brDias)} días con Botón Rojo, ${fmtNum(brAlto)} tuvieron el nivel combinado en alto o extremo (${tasaTxt(conc.coincidencia_br_alto_extremo)}). ${conc.method || ''}`
    : `${clases}. En estos días no hay Botón Rojo con el que comparar. ${conc.method || ''}`;
  return html`${head}
    <p class="small">${dual(`${fraseBr} ${fraseFuego}`, detallado)}</p>
    <ul class="list x-tech">${filas}</ul>
    ${conc.note ? html`<p class="tiny muted">${conc.note}</p>` : ''}
    ${fuentesConcordancia(conc)}`;
}

function fuentesConcordancia(conc) {
  const conafIncendiosUrl = 'https://www.conaf.cl/incendios-forestales/incendios-forestales-en-chile/estadisticas-historicas/';
  const conafBotonRojoUrl = 'https://deigeprif.com';
  const incendiosUrl = typeof conc.source_url === 'string' && conc.source_url.startsWith('https://')
    ? conc.source_url
    : conafIncendiosUrl;
  return html`<p class="tiny muted">Fuente: <a href="${incendiosUrl}" target="_blank" rel="noopener">reporte de incendios de CONAF</a> · <a href="${conafBotonRojoUrl}" target="_blank" rel="noopener">CONAF GEPRIF · Botón Rojo</a>.</p>`;
}

/* QA-3.2: detecciones descartadas por fuente (GET /api/observability/descartes, ventana de
 * 24 h). Un conteo en null es «sin medir»: la corrida no guardó el recuento del parser y
 * mostrarlo como 0 afirmaría que no hubo descartes. */
const celdaNum = (n) => (esNumero(n) ? fmtNum(n) : 'sin medir');
const CELDA = 'padding:3px 10px 3px 0;text-align:right;white-space:nowrap';
function fraseDescartes(f) {
  const nombre = PRODUCT_NAMES[f.source] || f.source;
  const partes = [];
  if (esNumero(f.recibidas)) {
    partes.push(`${fmtNum(f.recibidas)} puntos recibidos`);
    if (f.fuera_de_chile > 0) partes.push(`${fmtNum(f.fuera_de_chile)} cayeron fuera de Chile`);
    if (f.fila_invalida > 0) partes.push(`${fmtNum(f.fila_invalida)} ${f.fila_invalida === 1 ? 'fila inválida' : 'filas inválidas'}`);
  } else {
    partes.push('recuento de llegada sin medir');
  }
  if (f.fuente_fija > 0) partes.push(`${fmtNum(f.fuente_fija)} en una fuente de calor fija`);
  if (f.fuera_del_pais > 0) partes.push(`${fmtNum(f.fuera_del_pais)} quedaron fuera del país al agruparse`);
  if (f.confianza_baja > 0) partes.push(`${fmtNum(f.confianza_baja)} de confianza baja`);
  if (esNumero(f.repetidas) && f.repetidas > 0) partes.push(`${fmtNum(f.repetidas)} ya estaban guardadas`);
  return `${nombre}: ${partes.join('; ')}.`;
}
export function descartesPorFuente(desc = null) {
  const head = html`<h2 class="section">${dual('Lo que se descartó por fuente', 'Detecciones descartadas por fuente')}</h2>`;
  if (!desc || desc.error || !Array.isArray(desc.fuentes)) {
    return html`${head}<p class="small muted">Este resumen no está disponible ahora. El resto de la página no se ve afectado.</p>`;
  }
  if (!desc.fuentes.length) {
    return html`${head}<p class="small muted">No hay corridas de las fuentes satelitales en las últimas ${fmtNum(desc.horas || 24)} horas.</p>`;
  }
  const columnas = ['fuente', 'recibidas', 'nuevas', 'repetidas', 'fuera de Chile', 'fila inválida', 'fuente fija', 'fuera del país', 'confianza baja', 'corridas', 'sin medir'];
  const filas = desc.fuentes.map((f) => html`<tr>
    <td style="${CELDA}text-align:left">${PRODUCT_NAMES[f.source] || f.source}</td>
    <td style="${CELDA}">${celdaNum(f.recibidas)}</td><td style="${CELDA}">${celdaNum(f.nuevas)}</td>
    <td style="${CELDA}">${celdaNum(f.repetidas)}</td><td style="${CELDA}">${celdaNum(f.fuera_de_chile)}</td>
    <td style="${CELDA}">${celdaNum(f.fila_invalida)}</td><td style="${CELDA}">${celdaNum(f.fuente_fija)}</td>
    <td style="${CELDA}">${celdaNum(f.fuera_del_pais)}</td><td style="${CELDA}">${celdaNum(f.confianza_baja)}</td>
    <td style="${CELDA}">${celdaNum(f.corridas)}</td><td style="${CELDA}">${celdaNum(f.corridas_sin_medir)}</td></tr>`);
  return html`${head}
    <p class="small x-plain">${desc.fuentes.map((f) => `${fraseDescartes(f)} `)}</p>
    <div class="x-tech" style="overflow-x:auto">
      <table class="tiny" style="border-collapse:collapse;white-space:nowrap">
        <thead><tr>${columnas.map((t, i) => html`<th style="padding:3px 10px 3px 0;text-align:${i === 0 ? 'left' : 'right'}">${t}</th>`)}</tr></thead>
        <tbody>${filas}</tbody>
      </table>
    </div>
    <p class="tiny muted">Ventana de ${fmtNum(desc.horas)} h, generado ${fmtDateTime(desc.generated_at)}. ${desc.note || ''}</p>`;
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

/* `status` puede llegar null el primer instante (la vista pinta antes de que responda
 * /api/status): las secciones que dependen de él muestran su carga y las demás —extras,
 * latencias, concordancia, licencias, chequeo— completan lo suyo apenas cada consulta llega. */
function render(status, resp, cal, fb, failed = [], lic = null, licErr = null, obs = null, conc = null, sinActualizar = false, desc = null) {
  const cargando = html`<p class="small muted">Consultando el estado de las fuentes…</p>`;
  return html`<h1 class="view-title">Calidad de los datos</h1>
    <p class="lede">${dual('De dónde salen los datos, si llegan a tiempo, si los avisos sirvieron y bajo qué licencia se usan: la transparencia hecha vista.', 'Estado de /api/status por fuente: última corrida, último éxito, historial reciente, barridos GOES, incidentes abiertos, opinión agregada de los avisos y atribución de cada capa.')}</p>
    ${status && sinActualizar ? html`<div class="callout callout-warn" role="status">${dual(`No pudimos actualizar el estado ahora: lo que ves es de ${ago(status.time_utc)}.`, `Falló la consulta a /api/status: se muestra el estado de ${ago(status.time_utc)}, sin el historial reciente.`)}</div>` : ''}
    ${status ? html`${bloqueDiagnostico(status, sinActualizar)}${summary(status)}${peligroDeHoy(status)}` : cargando}
    ${partialNotice(failed, sinActualizar)}
    <h2 class="section">${dual('Cada fuente, con su estado', 'Fuentes y corridas de ingesta')}</h2>
    ${status ? html`${sourcesTable(status)}${firmsQuota(status)}${openMeteoQuota(status)}${ultimosErrores(status)}` : cargando}
    ${conafResponse(resp)}
    ${adelanto(cal)}
    ${status ? html`${sweeps(status)}${openIncidents(status)}` : ''}
    ${descartesPorFuente(desc)}
    ${sirvieron(fb)}
    ${latenciasRutas(obs)}
    ${concordanciaRiesgo(conc)}
    ${licenses(lic, licErr)}
    ${autochequeoBloque()}
    <p class="tiny muted" style="margin-top:14px">Esta página solo muestra el estado de las fuentes y conteos: no hay ubicaciones de personas ni datos de suscriptores.</p>
    <p class="tiny muted"><a href="/web/preguntas.html">¿Cómo leer estos datos? Preguntas frecuentes</a></p>`;
}

let unsubs = [];
let vistaViva = null; // la vista montada: una consulta que llega tras salir no pinta sobre otra vista
export default {
  id: 'calidad',
  nav: false, // sin lugar en la barra de 320 px: se entra por la píldora de estado y por URL
  sheet: 'full',
  async mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    // Todo lo que muestra la vista, en un solo objeto: cada consulta actualiza su parte
    // y repinta; ningún fallo parcial tapa lo que ya se ve (FIX-76 conserva su aviso).
    const vista = {
      status: store.get('status'), history: {},
      resp: null, cal: null, fb: null, lic: null, licErr: null, obs: null, conc: null, desc: null,
      failed: new Set(), sinSalida: false, sinActualizar: false,
    };
    let rutasToken = 0;
    const pedirRutas = async () => {
      const token = ++rutasToken;
      try {
        const data = await request('/api/observability/routes');
        if (token !== rutasToken) return;
        vista.obs = data;
      } catch {
        if (token !== rutasToken) return;
        vista.obs = null;
      }
      repintar();
    };
    const pedirLicencias = async () => {
      try {
        vista.lic = await request('/web/data/licencias.json');
        vista.licErr = null;
      } catch (err) {
        vista.licErr = err;
      }
      repintar();
    };
    const pedirConcordancia = async () => {
      try { vista.conc = await request('/api/observability/concordancia'); }
      catch { vista.conc = { error: true }; }
      repintar();
    };
    const pedirDescartes = async () => {
      try { vista.desc = await request('/api/observability/descartes'); }
      catch { vista.desc = { error: true }; }
      repintar();
    };
    const fetchSection = (key) => ({
      resp: () => request('/api/opendata/response.json'),
      cal: () => request('/web/data/calibracion.json'),
      fb: () => request('/api/quality/feedback'),
    })[key]();
    const applyExtras = (extras) => {
      for (const [key, value] of Object.entries(extras)) {
        if (value.error) { vista.failed.add(key); continue; }
        vista.failed.delete(key);
        if (key === 'resp') vista.resp = value.data;
        if (key === 'cal') vista.cal = value.data;
        if (key === 'fb') vista.fb = value.data;
      }
    };
    const pintar = () => {
      const status = vista.status ? { ...vista.status, history: vista.history } : null;
      container.innerHTML = String(render(status, vista.resp, vista.cal, vista.fb, [...vista.failed], vista.lic, vista.licErr, vista.obs, vista.conc, vista.sinActualizar, vista.desc));
      // «Reintentar» del bloque de licencias: vuelve a pedir solo el JSON, como el aviso parcial.
      container.querySelector('[data-retry]')?.addEventListener('click', async (event) => {
        const btn = event.currentTarget;
        btn.disabled = true;
        btn.textContent = 'Reintentando…';
        await pedirLicencias();
      });
      container.querySelector('#copy-diag')?.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(diagnosticoTexto({ ...vista.status, history: vista.history }));
          toast('Diagnóstico copiado: pégalo donde quieras reportarlo.');
        } catch { toast('No se pudo copiar: anota los problemas de arriba.', 'error'); }
      });
      container.querySelector('#autochk')?.addEventListener('click', async () => {
        autoResult = 'corriendo';
        repintar();
        try { autoResult = { results: await correrChequeo(), resumen: null }; autoResult.resumen = summarize(autoResult.results); }
        catch { autoResult = null; toast('No se pudo hacer el chequeo ahora.', 'error'); }
        repintar();
      });
    };
    vistaViva = vista;
    const repintar = () => { if (vistaViva === vista && !vista.sinSalida) keepPlace(container, pintar); };
    // Error con salida (FIX-57): los teléfonos y «Reintentar» solo cuando no hay ningún
    // estado que mostrar — con un estado vigente (aunque no trajo historial) la vista se
    // queda pintada y los extras fallidos pasan al aviso parcial.
    const pintarError = (err) => {
      if (vistaViva !== vista) return;
      vista.sinSalida = true;
      container.innerHTML = String(html`<h1 class="view-title">Calidad de los datos</h1>
        <div class="empty"><div class="glyph">◎</div>No se pudo consultar el estado de las fuentes. Revisa tu conexión y vuelve a intentarlo.</div>
        <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-retry>Reintentar</button></div>
        <p class="small" style="margin:12px 0 8px">Si ves fuego o humo cerca, llama de inmediato. No esperes a que lo vea un satélite.</p>
        ${phonesHtml()}`);
      const btn = container.querySelector('[data-retry]');
      btn.addEventListener('click', () => { btn.disabled = true; btn.textContent = 'Reintentando…'; vista.sinSalida = false; cargarTodo(); });
      toast(err.message, 'error');
    };
    const pedirEstado = async () => {
      try {
        const data = await api.status(20);
        vista.status = data;
        vista.history = data.history || {};
        // Si el SW sirvió la copia guardada (sin conexión), la respuesta llega con 200 y el
        // encabezado X-Brasa-Cached-At: sin ese dato fresco tampoco se puede decir «al día».
        vista.sinActualizar = storage.get('cached-at') != null;
      } catch (err) {
        if (!vista.status) { pintarError(err); return; }
        // Con el estado de la portada la vista sigue pintada, pero avisa que no se pudo refrescar:
        // no puede decir «al día» sobre un dato que no alcanzó a comprobar.
        vista.sinActualizar = true;
      }
      repintar();
    };
    // Cada extra por separado: uno lento no retiene a los otros dos.
    const pedirExtras = (only = null) => Promise.all((only ?? Object.keys(EXTRA_SECTIONS)).map(async (key) => {
      applyExtras(await loadExtras(fetchSection, [key]));
      repintar();
    }));
    // Cada consulta sale apenas se monta: la que llega primero pinta primero, sin esperar a las demás.
    const cargarTodo = () => {
      pedirEstado();
      pedirExtras();
      pedirLicencias();
      pedirRutas();
      pedirConcordancia();
      pedirDescartes();
    };
    // Pintado inmediato: con el estado que ya tiene la portada o con cada sección en carga.
    pintar();
    cargarTodo();
    // Un solo listener sobre el contenedor: el aviso de fallo parcial se repinta y su botón
    // debe seguir funcionando sin volver a enganchar nada.
    container.addEventListener('click', (event) => {
      const btn = event.target.closest?.('[data-retry-partial]');
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      btn.textContent = 'Reintentando…';
      pedirExtras([...vista.failed]);
    });
    // La píldora refresca /api/status cada minuto: se repinta con ese dato y se vuelven a pedir las latencias.
    unsubs = [store.on('status', (status) => {
      if (!status) return;
      vista.status = status;
      vista.sinSalida = false;
      vista.sinActualizar = storage.get('cached-at') != null;
      repintar();
      pedirRutas();
    })];
  },
  unmount() { vistaViva = null; unsubs.forEach((u) => u()); unsubs = []; },
};
