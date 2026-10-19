/* Riesgo 30-30-30 por comuna para los próximos 7 días. */
import { api } from '../api.js';
import { timeChart } from '../charts.js';
import { fitBbox, getMap, RISK_COLORS, selectComuna, setRisk, show } from '../map.js';
import { store } from '../store.js';
import { phonesHtml, placeForm } from '../ui.js';
import { $, ago, dual, fmtDateTime, fmtDay, fmtNum, html, minutesSince, RISK, riskChip, TZ, todayChile } from '../util.js';

let mounted = false;
let day = null;
let selected = null;
let chart = null;
let clickHandler = null;
const LEVEL_ORDER = ['extremo', 'alto', 'moderado', 'bajo'];
const STALE_MIN = 30; // misma regla que el pill de la cabecera y que Mi zona: 30 minutos

/** Aviso de datos satelitales viejos. El pronóstico no depende de ellos, pero el mapa sí. */
function staleNote(dataAsOf) {
  if (!dataAsOf || minutesSince(dataAsOf) <= STALE_MIN) return '';
  return html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(dataAsOf)}.</b>
    Este pronóstico viene de Open-Meteo y sigue vigente, pero el mapa de focos de calor puede estar incompleto.</div>`;
}

/** Condiciones del día: 30-30-30 y FWI juntos, con la razón del nivel. */
function combinedCallout(combined, base, reasons) {
  if (!combined || !base) return '';
  // La ficha recibe `reasons` como texto JSON desde risk_daily; el mapa ya lo entrega como arreglo.
  let list = reasons;
  if (typeof list === 'string') { try { list = JSON.parse(list); } catch { list = []; } }
  const label = (RISK[combined] || {}).label || combined;
  const baseLabel = (RISK[base] || {}).label || base;
  const same = combined === base;
  return html`<div class="callout" style="margin-top:10px"><b>Condiciones del día · ${label.toLowerCase()}</b>
    ${dual(same
    ? 'El calor del día y la sequía acumulada coinciden: los dos índices marcan lo mismo.'
    : `La sequía acumulada sube el día a ${label.toLowerCase()}: el 30-30-30 solo marcaba ${baseLabel.toLowerCase()}, pero el combustible lleva semanas secándose.`,
    `Nivel combinado 30-30-30 + FWI: ${(list || []).join(' · ') || 'sin detalle'}`)}</div>`;
}

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Peligro de incendio · ${day ? fmtDay(day) : ''}</div>
    <div class="legend-row">${LEVEL_ORDER.slice().reverse().map((k) => html`<span class="legend-item"><span class="sw sw-sq" style="background:${RISK_COLORS[k]}"></span>${RISK[k].label}</span>`)}</div>
    <div class="legend-note">${dual('Qué tanto ayuda el clima a que un fuego crezca. No predice dónde habrá incendios.', 'Pronóstico en el centroide de cada comuna. No es probabilidad de ignición.')}</div>`);
}

function explainer() {
  return html`<details class="fold"><summary>¿Cómo sabe BRASA si un día es peligroso?</summary><div>
    <p>Bomberos y CONAF usan una regla simple, la <b>regla 30-30-30</b>: el fuego se vuelve muy difícil de controlar cuando hay <b>más de 30 °C</b>, <b>menos de 30 % de humedad</b> en el aire y <b>viento de más de 30 km/h</b>.</p>
    <p>BRASA revisa el pronóstico hora a hora en cada comuna:</p>
    <ul><li><b>Extremo:</b> al menos una hora con las tres cosas a la vez.</li>
      <li><b>Alto:</b> varias horas con dos de las tres, o muy cerca de las tres.</li>
      <li><b>Moderado:</b> alguna hora con dos de las tres, o mucho calor y aire seco.</li>
      <li><b>Bajo:</b> el resto de los días.</li></ul>
    <p>Es un pronóstico para toda la comuna: no ve el viento de cada quebrada ni qué tan seco está el pasto de tu sector.</p>
    <p>Por eso BRASA agrega el <b>FWI</b>, el índice del sistema canadiense: no mira solo el día de hoy, mira <b>cuánto llevan secándose el pasto y la hojarasca</b> en las últimas semanas (hasta dos meses de lluvia y calor). Un día no tan caluroso después de un mes seco puede ser más peligroso que un día de 33 °C después de una semana de lluvia. Se muestran los dos, no uno en lugar del otro.</p>
    <p>Y hay una trampa del clima: en la zona central, <b>un invierno más lluvioso que lo normal no baja el riesgo del verano siguiente, lo sube</b>. Esa lluvia hace crecer más pasto y matorral; cuando se seca en enero, hay más combustible fino en las laderas. Por eso la ficha de cada comuna muestra cuánto se apartó la temporada de lluvias de su normal de los últimos 30 años.</p>
    <p class="x-tech tiny">Fuente: Open-Meteo (pronóstico horario, multi-modelo), evaluado en el centroide de cada comuna BCN. Criterios 30-30-30: T &gt; 30 °C, HR &lt; 30 %, viento sostenido &gt; 30 km/h. FWI: Van Wagner (1987), calculado por BRASA con 60 días de archivo y el pronóstico; en el hemisferio sur usa sus propias tablas de largo del día. Anomalía de lluvia: ERA5 (Open-Meteo), temporada 1 de junio → hoy contra la normal 1991-2020 de la misma ventana de días. Avisos de viento y calor extremo: DMC, CAP 1.2 (dominio público), por comuna según el polígono de cada zona. Pendiente: humedad del combustible por satélite (Sentinel-2) y capa de lluvia en el mapa. <a href="https://deigeprif.com" target="_blank" rel="noopener">Pronóstico de riesgo (CONAF · DEI GEPRIF) ↗</a> · <a href="https://meteograma.deigeprif.com" target="_blank" rel="noopener">Pyrocast (meteograma por punto, CONAF) ↗</a></p>
  </div></details>`;
}

const ENSO_LABELS = { nino: 'El Niño', nina: 'La Niña', neutral: 'neutral' };
const ENSO_SEASONS = {
  DJF: 'diciembre–febrero', JFM: 'enero–marzo', FMA: 'febrero–abril', MAM: 'marzo–mayo',
  AMJ: 'abril–junio', MJJ: 'mayo–julio', JJA: 'junio–agosto', JAS: 'julio–septiembre',
  ASO: 'agosto–octubre', SON: 'septiembre–noviembre', OND: 'octubre–diciembre', NDJ: 'noviembre–enero',
};
let ensoData; // undefined: aún no pedido · null: sin dato o error de red

/** Panel «El Pacífico y esta temporada»: estado ENSO de la NOAA, sin la regla «El Niño = más incendios». */
function ensoPanel(d) {
  const url = d?.source_url || 'https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml';
  const name = d?.source || 'NOAA · Climate Prediction Center (CPC)';
  if (!d || !d.phase) {
    return html`<details class="fold"><summary>El Pacífico y esta temporada</summary><div>
      <p class="small">Ahora no hay dato del Pacífico: BRASA no pudo leer el índice ONI y no hay una lectura anterior guardada.
        Fuente: <a href="${url}" target="_blank" rel="noopener">${name} ↗</a>.</p></div></details>`;
  }
  const label = ENSO_LABELS[d.phase] || d.phase;
  const season = `${ENSO_SEASONS[d.season] || d.season} de ${d.year}`;
  return html`<details class="fold"><summary>El Pacífico y esta temporada · ${label}</summary><div>
    <p class="small"><b>${d.phase === 'neutral' ? 'Pacífico en estado neutro' : label}</b> · índice ONI ${d.oni > 0 ? '+' : ''}${fmtNum(d.oni, 1)} °C (${season}).</p>
    <p class="small">${dual('La superficie del Pacífico se calienta (El Niño) o se enfría (La Niña) en ciclos de años, y eso inclina el clima de Chile: cambia cuánto y cuándo llueve. Inclina las probabilidades de la temporada, pero no dice cuántos incendios habrá: casi todos los incendios los inicia la gente, y día a día manda el pronóstico de calor, humedad y viento de arriba.',
      'El ONI inclina la distribución estacional de lluvia y temperatura; no es un predictor de igniciones ni una regla lineal «El Niño = más incendios».')}</p>
    <p class="tiny muted x-tech">ONI: anomalía de la temperatura del mar en la región Niño 3.4, media de 3 meses (ERSST.v5). Umbrales del CPC: ≥ +0,5 °C El Niño, ≤ −0,5 °C La Niña. Dato del trimestre ${season}${d.updated_at ? ` · consultado ${ago(d.updated_at)}` : ''}.</p>
    <p class="tiny muted">Fuente: <a href="${url}" target="_blank" rel="noopener">${name} ↗</a> (dominio público).</p>
  </div></details>`;
}

/** Pide el estado ENSO una sola vez por sesión y lo vuelca en el slot del panel. */
async function fillEnso(container) {
  if (ensoData === undefined) ensoData = await api.enso().catch(() => null);
  if (!mounted) return;
  const slot = container.querySelector('#enso-slot');
  if (slot) slot.innerHTML = String(ensoPanel(ensoData));
}

const hourFlags = (h) => [(h.t ?? 0) > 30, (h.rh ?? 100) < 30, (h.wind ?? 0) > 30];

/** Rango de horas (hora de Chile) en que se cumplen dos o más criterios, en palabras. */
function dangerHours(hours, date) {
  const hits = hours.filter((h) => new Date(h.time).toLocaleDateString('en-CA', { timeZone: TZ }) === date)
    .filter((h) => hourFlags(h).filter(Boolean).length >= 2)
    .map((h) => Number(new Date(h.time).toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: TZ })) % 24);
  if (!hits.length) return null;
  return { from: Math.min(...hits), to: Math.max(...hits) + 1 };
}
const joinList = (parts) => (parts.length > 1 ? `${parts.slice(0, -1).join(', ')} y ${parts.at(-1)}` : parts.join(''));

/** Frase sencilla del «por qué» del nivel, con las cifras reales del día (y de la hora peak si hay horas). */
function whyPlain(day, hours) {
  const hits = (hours || [])
    .filter((h) => new Date(h.time).toLocaleDateString('en-CA', { timeZone: TZ }) === day.date)
    .map((h) => ({ h, n: hourFlags(h).filter(Boolean).length }))
    .filter((x) => x.n >= 2);
  const peak = (list) => list.reduce((a, x) => ((x.h.score ?? 0) > (a?.h.score ?? -1) ? x : a), null)?.h;
  const hourOf = (h) => Number(new Date(h.time).toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: TZ })) % 24;
  const met = (h) => joinList(hourFlags(h).map((ok, i) => ok && [
    `${fmtNum(h.t, 0)} °C`, `${fmtNum(h.rh)} % de humedad`, `${fmtNum(h.wind)} km/h de viento`][i]).filter(Boolean));
  const h3 = day.hours_3of3 ?? day.h3 ?? 0;
  const h2 = day.hours_2of3 ?? day.h2 ?? 0;
  const maxes = `máximos del día: ${fmtNum(day.tmax, 0)} °C, ${fmtNum(day.rhmin)} % de humedad y ${fmtNum(day.windmax)} km/h`;
  switch (day.level) {
    case 'extremo': {
      const p = peak(hits.filter((x) => x.n === 3));
      if (p) return `A las ${hourOf(p)} h se juntaron las tres: ${met(p)}.`;
      return h3 ? `${h3 === 1 ? 'Una hora' : `${h3} horas`} con las tres a la vez (${maxes}).`
        : `Se juntaron las tres condiciones a la vez (${maxes}).`;
    }
    case 'alto': {
      const p = peak(hits);
      const dh = dangerHours(hours || [], day.date);
      if (p) return `Dos de las tres condiciones (${met(p)})${dh ? ` entre las ${dh.from} y las ${dh.to} h` : ''}.`;
      return h2 ? `Dos de las tres condiciones durante ${h2} h (${maxes}).`
        : `Ninguna hora juntó dos condiciones, pero estuvo muy cerca (${maxes}).`;
    }
    case 'moderado': {
      const p = peak(hits);
      if (p) return `Alguna hora juntó dos condiciones (${met(p)}).`;
      if (h2) return `Alguna hora juntó dos condiciones (${maxes}).`;
      // «Calor y aire seco» solo cuando esa regla explica el nivel; si fue el puntaje (p. ej. puro
      // viento), la frase neutra no le atribuye el nivel a algo que no pasó.
      return (day.tmax ?? 0) >= 27 && (day.rhmin ?? 100) <= 40
        ? `Calor y aire seco, sin las tres a la vez (${maxes}).`
        : `Horas cerca de los límites, sin las tres a la vez (${maxes}).`;
    }
    default:
      return `Ninguna hora se acercó a las tres condiciones (máximo ${fmtNum(day.tmax, 0)} °C).`;
  }
}

/** «¿Por qué este nivel?»: frase por reglas, sin modelos de lenguaje. Detallada agrega puntaje y horas. */
function whyLevel(day, hours) {
  const h3 = day.hours_3of3 ?? day.h3 ?? 0;
  const h2 = day.hours_2of3 ?? day.h2 ?? 0;
  const plain = whyPlain(day, hours);
  return dual(plain, `${plain} Puntaje ${day.score} · ${h3} h con 3/3 · ${h2} h con 2/3.`);
}

/** Pronóstico oficial CONAF Botón Rojo: siempre con su fuente, y nunca como «incendio detectado». */
function brCallout(b, source) {
  return html`<div class="callout br-callout" style="margin-top:10px"><b>CONAF: Botón Rojo${b.hours ? ` · ${b.hours} h` : ''}.</b>
    ${dual('CONAF pronostica para este día condiciones favorables para que un incendio empiece y se propague. No significa que haya fuego.',
      `Pronóstico oficial de condiciones de Botón Rojo: hasta ${b.hours} h, ${fmtNum(b.area_ha)} ha (${fmtNum(b.proportion * 100)} % de la comuna).`)}
    <a href="${source?.url}" target="_blank" rel="noopener">Ver en CONAF ↗</a></div>`;
}

/** FWI propio de BRASA: qué tan seco está el combustible después de semanas sin lluvia. */
function fwiCallout(f, source) {
  return html`<div class="callout" style="margin-top:10px"><b>${dual('Sequía acumulada', 'FWI')} · ${fmtNum(f.fwi, 0)} (${RISK[f.level] ? RISK[f.level].label.toLowerCase() : f.level})</b>
    ${dual('El pasto y la hojarasca llevan semanas secándose. Cuanto más alto, más rápido crece un fuego que ya empezó.',
      `Índice canadiense calculado por BRASA: FFMC ${fmtNum(f.ffmc, 0)} · DMC ${fmtNum(f.dmc, 0)} · DC ${fmtNum(f.dc, 0)} · ISI ${fmtNum(f.isi)} · BUI ${fmtNum(f.bui, 0)}.`)
    }${source?.url ? html` <a href="${source.url}" target="_blank" rel="noopener">Método ↗</a>` : ''}</div>`;
}

/** Anomalía de lluvia de la temporada: qué implica para el pasto del verano. */
function rainCallout(r, source) {
  if (!r || !r.level) return '';
  const pct = Math.abs(Math.round(r.percent ?? 0));
  const side = (r.percent ?? 0) >= 0 ? 'por encima' : 'por debajo';
  return html`<div class="callout" style="margin-top:10px"><b>Lluvia de la temporada · ${pct} % ${side} de lo normal</b>
    ${dual(r.plain, `${fmtNum(r.current_mm, 0)} mm caídos frente a ${fmtNum(r.normal_mm, 0)} mm de la normal 1991-2020 en la misma ventana de días (ERA5).`)}
    ${source?.url ? html` <a href="${source.url}" target="_blank" rel="noopener">Fuente ↗</a>` : ''}</div>`;
}

/** Texto listo para compartir el riesgo del día de una comuna: nivel en palabras, qué hacer,
 *  el Botón Rojo de CONAF si está vigente ese día y el enlace, con el recordatorio de que no es oficial. */
const shareText = (name, today, br, code) => {
  const level = RISK[today.level] || {};
  const url = `${location.origin}/#/riesgo?comuna=${code}`;
  const parts = [`${name}: ${fmtDay(today.date)} el peligro es ${(level.label || today.level).toLowerCase()}.`,
    level.plain,
    br?.hours ? `CONAF marcó Botón Rojo: hasta ${br.hours} h.` : '',
    `Más detalle en BRASA: ${url}`,
    'No es una alerta oficial: sigue a SENAPRED (senapred.cl).'];
  return { title: `BRASA · ${name}`, text: parts.filter(Boolean).join(' ') };
};

/** Avisos oficiales de viento y calor de la DMC que tocan esta comuna. */
function dmcCallout(list, source) {
  if (!list || !list.length) return '';
  const first = list[0];
  const labels = [...new Set(list.map((a) => a.label))].join(' y ');
  return html`<div class="callout" style="margin-top:10px"><b>DMC: ${labels}</b>
    ${dual(`La Dirección Meteorológica de Chile tiene un aviso oficial vigente para esta comuna hasta el ${fmtDateTime(first.expires)}.`,
      `${first.event} · severidad ${first.severity} · vence ${fmtDateTime(first.expires)}`)}
    <a href="${first.web || source?.url}" target="_blank" rel="noopener">Ver en la DMC ↗</a></div>`;
}

/** Error con salida (UX-16): qué pasó, «Reintentar» sobre el mismo loader y los teléfonos de emergencia. */
function loadError(host, err, retry) {
  host.innerHTML = String(html`<div class="callout callout-warn" role="alert">
    <b>${dual('No pudimos cargar esto ahora.', `Error al cargar: ${err.message}`)}</b>
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-retry>Reintentar</button></div>
    <p class="small" style="margin:12px 0 8px">Si ves fuego o humo cerca, llama de inmediato. No esperes a que lo vea un satélite.</p>
    ${phonesHtml()}</div>`);
  host.querySelector('[data-retry]').addEventListener('click', retry);
}

async function renderDetail(container, code) {
  const host = container.querySelector('#detail');
  if (!host) return; // la vista quedó en estado de error
  chart?.destroy(); chart = null;
  if (!code) { host.innerHTML = ''; return; }
  host.innerHTML = '<p class="small muted">Cargando la comuna…</p>';
  try {
    const data = await api.riskComuna(code);
    if (!mounted || selected !== code) return;
    if (!(store.get('comunasIndex') || []).some((x) => x.code === code) && data.comuna.bbox) fitBbox(data.comuna.bbox, 60);
    const today = data.days.find((d) => d.date === day) || data.days[0];
    const br = new Map((data.boton_rojo || []).map((b) => [b.date, b]));
    const brToday = today && br.get(today.date);
    const fwiDays = data.fwi_days || [];
    // Sin dato del día exacto no se muestra el de otro día: sería informar de una fecha distinta.
    const fwiToday = today ? fwiDays.find((f) => f.date === today.date) : null;
    host.innerHTML = String(html`<div class="card">
      <div class="card-head"><div><div class="card-title">${data.comuna.name}</div><div class="card-sub">${data.comuna.provincia} · ${data.comuna.region}</div></div>
        ${today ? riskChip(today.level) : ''}</div>
      <p class="tiny muted" style="margin-top:4px"><a href="https://deigeprif.com" target="_blank" rel="noopener">Ver las herramientas oficiales de CONAF ↗</a></p>
      ${staleNote(data.data_as_of)}
      ${today ? html`<p class="small" style="margin:10px 0 0">${RISK[today.level].plain}</p>
        <div class="kpis" style="margin-top:8px">
        <div class="kpi"><small>${dual('calor máximo', 'T máx.')}</small><strong>${fmtNum(today.tmax, 0)}°</strong></div>
        <div class="kpi"><small>${dual('humedad del aire', 'HR mín.')}</small><strong>${fmtNum(today.rhmin)} %</strong></div>
        <div class="kpi"><small>${dual('viento', 'viento máx.')}</small><strong>${fmtNum(today.windmax)}</strong><span>km/h · ráfagas ${fmtNum(today.gustmax)}</span></div></div>
        <p class="small" style="margin:6px 0 0">${whyLevel(today, data.hours)}</p>
        ${brToday ? brCallout(brToday, data.boton_rojo_source) : ''}
        ${fwiToday ? fwiCallout(fwiToday, data.fwi_source) : ''}
        ${combinedCallout(today.level_combined, today.level, today.reasons)}
        ${dmcCallout(data.dmc_alerts, data.dmc_source)}
        ${(() => { const dh = dangerHours(data.hours, today.date); return dh ? html`<p class="small danger-hours"><b>Horas más peligrosas: de ${dh.from} a ${dh.to} h.</b> Evita cualquier chispa en ese horario.</p>` : ''; })()}
        <p class="tiny muted x-tech" style="margin-top:6px">${today.hours_3of3 ? `${today.hours_3of3} h con 3/3 criterios.` : ''} ${today.hours_2of3 ? `${today.hours_2of3} h con 2/3.` : 'Ninguna hora con 2 o más criterios.'} Puntaje ${today.score}.</p>` : html`<p class="small muted">Sin pronóstico para esta fecha.</p>`}
      ${rainCallout(data.rain, data.rain_source)}
      <div class="day-strip">${data.days.slice(0, 7).map((d) => html`<button class="day-cell" data-day="${d.date}" aria-pressed="${d.date === day}">
        <b>${fmtDay(d.date, { day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, month: undefined })}<i class="${RISK[d.level].cls}"></i>${br.has(d.date) ? html`<em class="br-mark" aria-hidden="true">BR</em>` : ''}<span class="sr-only">Peligro ${RISK[d.level].label.toLowerCase()}${br.has(d.date) ? '. CONAF: Botón Rojo' : ''}</span></button>`)}</div>
      ${br.size ? html`<p class="tiny muted" style="margin-top:4px"><b class="br-inline">BR</b> = ${dual('CONAF avisa condiciones favorables para incendios ese día.', 'Botón Rojo pronosticado por CONAF.')}</p>` : ''}
      <h2 class="section" style="margin-top:18px">Hora a hora</h2>
      <div id="risk-chart"></div>
      <p class="tiny muted">La línea roja punteada marca el límite peligroso (30). ${data.computed_at ? `Pronóstico de ${fmtDateTime(data.computed_at)}.` : ''}</p>
      <div class="card-actions"><button class="btn btn-sm" id="watch">Guardar un lugar en ${data.comuna.name}</button>
        ${today ? html`<button class="btn btn-sm btn-ghost" id="share">Compartir</button>` : ''}</div>
    </div>`);
    host.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => { day = b.dataset.day; load(container); }));
    host.querySelector('#watch').addEventListener('click', () => placeForm(null, { lat: data.comuna.center[1], lon: data.comuna.center[0] }));
    host.querySelector('#share')?.addEventListener('click', async () => {
      const { title, text } = shareText(data.comuna.name, today, brToday, code);
      // La URL ya va dentro del texto: pasarla también como `url` la duplicaría en Android/Chromium.
      if (navigator.share) {
        try { await navigator.share({ title, text }); return; } catch (err) { if (err?.name === 'AbortError') return; }
      }
      try { await navigator.clipboard.writeText(text); toast('Enlace copiado.'); }
      catch { toast('No se pudo copiar el enlace.', 'error'); }
    });
    const hours = data.hours;
    if (hours.length) {
      chart = timeChart(host.querySelector('#risk-chart'), {
        times: hours.map((h) => h.time),
        panels: [
          { id: 't', title: 'Calor', unit: '°C', kind: 'line', digits: 1, series: [{ key: 't', label: 'Temperatura', color: 'var(--series-2)', values: hours.map((h) => h.t) }], threshold: { value: 30, label: '30 °C', direction: 'above' } },
          { id: 'rh', title: 'Humedad del aire (más baja = más seco)', unit: '%', kind: 'line', yMax: 100, series: [{ key: 'rh', label: 'Humedad', color: 'var(--series-1)', values: hours.map((h) => h.rh) }], threshold: { value: 30, label: '30 %', direction: 'below' } },
          { id: 'w', title: 'Viento', unit: 'km/h', kind: 'line', series: [{ key: 'w', label: 'Viento', color: 'var(--series-2)', values: hours.map((h) => h.wind) }], threshold: { value: 30, label: '30 km/h', direction: 'above' } },
        ],
      });
    }
  } catch (err) { loadError(host, err, () => renderDetail(container, code)); }
}

async function load(container) {
  let risk;
  try { risk = await api.risk(day || todayChile()); } catch (err) { if (mounted) loadError(container, err, () => load(container)); return; }
  if (!mounted) return;
  store.set('risk', risk);
  day = risk.date;
  setRisk(risk.comunas);
  legend();
  const comunas = store.get('comunasIndex') || [];
  const byCode = new Map(comunas.map((c) => [String(c.code), c]));
  const ranked = Object.entries(risk.comunas).map(([code, r]) => ({ code: Number(code), ...r, comuna: byCode.get(code) }))
    .filter((r) => r.comuna).sort((a, b) => b.score - a.score || (b.tmax || 0) - (a.tmax || 0));
  const brMap = risk.boton_rojo || {};
  const brList = Object.entries(brMap).map(([code, b]) => ({ code: Number(code), ...b, comuna: byCode.get(code) }))
    .filter((b) => b.comuna).sort((a, b) => b.hours - a.hours || b.proportion - a.proportion);
  const counts = Object.fromEntries(LEVEL_ORDER.map((k) => [k, ranked.filter((r) => r.level === k).length]));
  const summary = new Map((risk.summary || []).map((s) => [s.date, s]));
  const empty = !ranked.length;
  const worstToday = LEVEL_ORDER.find((k) => counts[k]);
  container.innerHTML = String(html`
    <h1 class="view-title">¿Qué tan peligroso está el clima?</h1>
    <p class="lede">${dual('Hay días en que el calor, el aire seco y el viento hacen que un fuego crezca muy rápido. Busca tu comuna.', 'Índice 30-30-30 por comuna para los próximos 7 días. Toca una comuna en el mapa o búscala.')}</p>
    <div class="field" style="margin-bottom:6px"><label for="r-search">Tu comuna</label>
      <input class="input input-lg" id="r-search" list="r-comunas" placeholder="Escribe, por ejemplo: Quilpué" autocomplete="off" />
      <datalist id="r-comunas">${comunas.map((c) => html`<option value="${c.name}">${c.region}</option>`)}</datalist></div>
    <div id="detail"></div>
    ${staleNote(risk.data_as_of)}
    ${risk.dates.length ? html`<h2 class="section">Todo Chile, día por día</h2>
      <div class="day-strip" role="group" aria-label="Día del pronóstico">${risk.dates.map((d) => {
      const s = summary.get(d) || {};
      const worst = s.extremo ? 'extremo' : s.alto ? 'alto' : s.moderado ? 'moderado' : 'bajo';
      return html`<button class="day-cell" data-day="${d}" aria-pressed="${d === day}" title="${s.extremo || 0} comunas en extremo, ${s.alto || 0} en alto">
        <b>${fmtDay(d, { day: undefined, month: undefined })}</b>${fmtDay(d, { weekday: undefined, month: undefined })}<i class="${RISK[worst].cls}"></i></button>`;
    })}</div><p class="tiny muted" style="margin-top:6px">La barra más alta es el peor nivel de ese día en alguna comuna. Toca un día para verlo en el mapa.</p>` : ''}
    ${empty ? html`<div class="empty" style="margin-top:16px"><div class="glyph">◌</div><b>El pronóstico aún no está listo.</b><p class="small">BRASA lo calcula cada 3 horas. Vuelve en unos minutos.</p></div>`
      : html`<div class="kpis" style="margin-top:12px">
        <div class="kpi"><small>en extremo</small><strong>${fmtNum(counts.extremo)}</strong><span>comunas</span></div>
        <div class="kpi"><small>en alto</small><strong>${fmtNum(counts.alto)}</strong><span>comunas</span></div>
        <div class="kpi"><small>en moderado</small><strong>${fmtNum(counts.moderado)}</strong><span>comunas</span></div></div>
        ${worstToday ? html`<p class="small" style="margin-top:6px">${riskChip(worstToday)} ${RISK[worstToday].plain}</p>` : ''}`}
    ${empty ? '' : html`<h2 class="section">Las comunas más peligrosas · ${fmtDay(day)}</h2>
      <ul class="list">${ranked.slice(0, 30).map((r) => html`<li><button class="row-btn" data-code="${r.code}">
        <span class="grow"><b class="small">${r.comuna.name}</b><span class="tiny muted"> · ${r.comuna.region}</span>
        <span class="tiny muted" style="display:block">hasta ${fmtNum(r.tmax)} °C · humedad ${fmtNum(r.rhmin)} % · viento ${fmtNum(r.windmax)} km/h</span>
        <span class="tiny muted" style="display:block">${whyPlain(r)}</span></span>${brMap[r.code] ? html`<em class="br-mark" title="CONAF: Botón Rojo">BR</em>` : ''}${riskChip(r.level)}</button></li>`)}</ul>`}
    ${brList.length ? html`<h2 class="section">${dual('Aviso de CONAF', 'CONAF · Botón Rojo')} · ${fmtDay(day)} <span class="tag">${brList.length} ${brList.length === 1 ? 'comuna' : 'comunas'}</span></h2>
      <p class="small">${dual('CONAF, el organismo a cargo de los incendios forestales, pronostica condiciones favorables para incendios («Botón Rojo») en estas comunas. No significa que haya fuego: es un día para no hacer quemas ni usar herramientas que hagan chispas.', 'Pronóstico oficial de CONAF de condiciones de Botón Rojo, resumido por comuna (máximo de horas y superficie). Se muestra junto al 30-30-30 de BRASA, no en su reemplazo.')}</p>
      <ul class="list">${brList.slice(0, 15).map((b) => html`<li><button class="row-btn" data-code="${b.code}"><span class="grow"><b class="small">${b.comuna.name}</b><span class="tiny muted"> · ${b.comuna.region}</span></span>
        <span class="small tabular">${b.hours} h</span></button></li>`)}</ul>
      <p class="tiny muted" style="margin-top:6px">${risk.boton_rojo_source.note} ${risk.boton_rojo_source.fetched_at ? `Consultado ${ago(risk.boton_rojo_source.fetched_at)}.` : ''} <a href="${risk.boton_rojo_source.url}" target="_blank" rel="noopener">Tablero de CONAF ↗</a></p>` : ''}
    <div id="enso-slot"></div>
    ${explainer()}
    ${risk.computed_at ? html`<p class="tiny muted" style="margin-top:10px">Pronóstico de ${fmtDateTime(risk.computed_at)} · ${dual('servicio Open-Meteo', 'Open-Meteo')}.</p>` : ''}`);
  container.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => { day = b.dataset.day; load(container); }));
  container.querySelectorAll('[data-code]').forEach((b) => b.addEventListener('click', () => choose(container, Number(b.dataset.code))));
  container.querySelector('#r-search').addEventListener('change', (e) => {
    const c = comunas.find((x) => x.name.toLowerCase() === e.target.value.trim().toLowerCase());
    if (c) choose(container, c.code);
  });
  fillEnso(container);
  if (selected) renderDetail(container, selected);
}

function choose(container, code) {
  selected = code;
  selectComuna(code);
  const c = (store.get('comunasIndex') || []).find((x) => x.code === code);
  if (c) fitBbox(c.bbox, 60);
  renderDetail(container, code);
  container.querySelector('#detail')?.scrollIntoView({ block: 'nearest' });
}

export default {
  id: 'riesgo',
  sheet: 'half',
  async mount(container, { params }) {
    mounted = true;
    show('risk-fill', true);
    show(['detections', 'goes-pixels', 'goes-pixels-line', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore', 'reports', 'place-radius-fill', 'place-radius-line'], false);
    show('places', true);
    $('#map-legend').classList.add('mobile-show');
    if (params?.comuna) selected = Number(params.comuna);
    container.innerHTML = '<h1 class="view-title">Cargando el pronóstico…</h1>';
    await load(container);
    if (selected) choose(container, selected); else fitBbox([-75.5, -45, -66.5, -18], 30);
    clickHandler = (e) => { const code = e.features?.[0]?.id; if (code) choose(container, Number(code)); };
    getMap().on('click', 'risk-fill', clickHandler);
  },
  unmount() {
    mounted = false;
    chart?.destroy(); chart = null;
    getMap().off('click', 'risk-fill', clickHandler);
    selectComuna(null);
    show('risk-fill', false);
    $('#map-legend').classList.remove('mobile-show');
  },
};
