/* Riesgo 30-30-30 por comuna para los próximos 7 días. */
import { api } from '../api.js';
import { timeChart } from '../charts.js';
import { fitBbox, getMap, RISK_COLORS, selectComuna, setRisk, show } from '../map.js';
import { store } from '../store.js';
import { placeForm } from '../ui.js';
import { $, fmtDateTime, fmtDay, fmtNum, html, RISK, riskChip, todayChile, toast } from '../util.js';

let mounted = false;
let day = null;
let selected = null;
let chart = null;
let clickHandler = null;
const LEVEL_ORDER = ['extremo', 'alto', 'moderado', 'bajo'];

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">Índice 30-30-30 · ${day ? fmtDay(day) : ''}</div>
    <div class="legend-row">${LEVEL_ORDER.slice().reverse().map((k) => html`<span class="legend-item"><span class="sw sw-sq" style="background:${RISK_COLORS[k]}"></span>${RISK[k].icon} ${RISK[k].label}</span>`)}</div>
    <div class="legend-note">Pronóstico meteorológico en el centro de cada comuna. No es la probabilidad de que ocurra un incendio.</div>`);
}

function explainer() {
  return html`<details class="fold"><summary>¿Cómo se calcula?</summary><div>
    <p>La <b>regla 30-30-30</b> que difunde CONAF describe condiciones muy favorables para la propagación: <b>temperatura sobre 30 °C</b>, <b>humedad relativa bajo 30 %</b> y <b>viento sobre 30 km/h</b>.</p>
    <p>BRASA la evalúa hora a hora con el pronóstico de Open-Meteo en el centro de cada comuna:</p>
    <ul><li><b>Extremo:</b> al menos una hora con los tres criterios.</li>
      <li><b>Alto:</b> tres o más horas con dos criterios, o valores muy cercanos a los tres umbrales.</li>
      <li><b>Moderado:</b> alguna hora con dos criterios, o calor y sequedad marcados.</li>
      <li><b>Bajo:</b> el resto.</li></ul>
    <p>Limitaciones: el modelo tiene una resolución de kilómetros y no ve el viento de quebradas ni la sequedad de la vegetación. Úsalo como alerta temprana, no como verdad local.</p>
    <div class="chips" style="margin-top:6px"><button class="chip" disabled>FWI (GWIS/Copernicus) · próximamente</button><button class="chip" disabled>Sequedad de vegetación (Sentinel-2) · próximamente</button></div>
  </div></details>`;
}

async function renderDetail(container, code) {
  const host = container.querySelector('#detail');
  chart?.destroy(); chart = null;
  if (!code) { host.innerHTML = ''; return; }
  host.innerHTML = '<p class="small muted">Cargando la comuna…</p>';
  try {
    const data = await api.riskComuna(code);
    if (!mounted || selected !== code) return;
    const today = data.days.find((d) => d.date === day) || data.days[0];
    host.innerHTML = String(html`<div class="card">
      <div class="card-head"><div><div class="card-title">${data.comuna.name}</div><div class="card-sub">${data.comuna.provincia} · ${data.comuna.region}</div></div>
        ${today ? riskChip(today.level) : ''}</div>
      ${today ? html`<div class="kpis" style="margin-top:12px">
        <div class="kpi"><small>Temp. máx.</small><strong>${fmtNum(today.tmax, 1)} °C</strong></div>
        <div class="kpi"><small>Humedad mín.</small><strong>${fmtNum(today.rhmin)} %</strong></div>
        <div class="kpi"><small>Viento máx.</small><strong>${fmtNum(today.windmax)} km/h</strong><span>ráfagas ${fmtNum(today.gustmax)}</span></div></div>
        <p class="small" style="margin-top:10px">${today.hours_3of3 ? `${today.hours_3of3} hora(s) cumplen los tres criterios 30-30-30.` : today.hours_2of3 ? `${today.hours_2of3} hora(s) cumplen dos de los tres criterios.` : 'Ninguna hora cumple dos o más criterios.'}</p>` : html`<p class="small muted">Sin pronóstico para esta fecha.</p>`}
      <div class="day-strip">${data.days.slice(0, 7).map((d) => html`<button class="day-cell" data-day="${d.date}" aria-pressed="${d.date === day}">
        <b>${fmtDay(d.date, { day: undefined, month: undefined })}</b>${fmtDay(d.date, { weekday: undefined, month: undefined })}<i class="${RISK[d.level].cls}"></i></button>`)}</div>
      <h2 class="section" style="margin-top:18px">Pronóstico hora a hora</h2>
      <div id="risk-chart"></div>
      <p class="tiny muted">Zona sombreada: hora que cruza el umbral de la regla. ${data.computed_at ? `Calculado ${fmtDateTime(data.computed_at)}.` : ''}</p>
      <div class="card-actions"><button class="btn btn-sm" id="watch">Vigilar un lugar en ${data.comuna.name}</button></div>
    </div>`);
    host.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => { day = b.dataset.day; load(container); }));
    host.querySelector('#watch').addEventListener('click', () => placeForm(null, { lat: data.comuna.center[1], lon: data.comuna.center[0] }));
    const hours = data.hours;
    if (hours.length) {
      chart = timeChart(host.querySelector('#risk-chart'), {
        times: hours.map((h) => h.time),
        panels: [
          { id: 't', title: 'Temperatura', unit: '°C', kind: 'line', digits: 1, series: [{ key: 't', label: 'Temperatura', color: 'var(--series-2)', values: hours.map((h) => h.t) }], threshold: { value: 30, label: '30 °C', direction: 'above' } },
          { id: 'rh', title: 'Humedad relativa', unit: '%', kind: 'line', yMax: 100, series: [{ key: 'rh', label: 'Humedad', color: 'var(--series-1)', values: hours.map((h) => h.rh) }], threshold: { value: 30, label: '30 %', direction: 'below' } },
          { id: 'w', title: 'Viento', unit: 'km/h', kind: 'line', series: [{ key: 'w', label: 'Viento', color: 'var(--series-2)', values: hours.map((h) => h.wind) }], threshold: { value: 30, label: '30 km/h', direction: 'above' } },
        ],
      });
    }
  } catch (err) { host.innerHTML = String(html`<p class="small muted">${err.message}</p>`); }
}

async function load(container) {
  let risk;
  try { risk = await api.risk(day || todayChile()); } catch (err) { toast(err.message, 'error'); return; }
  if (!mounted) return;
  store.set('risk', risk);
  day = risk.date;
  setRisk(risk.comunas);
  legend();
  const comunas = store.get('comunasIndex') || [];
  const byCode = new Map(comunas.map((c) => [String(c.code), c]));
  const ranked = Object.entries(risk.comunas).map(([code, r]) => ({ code: Number(code), ...r, comuna: byCode.get(code) }))
    .filter((r) => r.comuna).sort((a, b) => b.score - a.score || (b.tmax || 0) - (a.tmax || 0));
  const counts = Object.fromEntries(LEVEL_ORDER.map((k) => [k, ranked.filter((r) => r.level === k).length]));
  const summary = new Map((risk.summary || []).map((s) => [s.date, s]));
  const empty = !ranked.length;
  container.innerHTML = String(html`
    <p class="eyebrow">Riesgo meteorológico</p>
    <h1 class="view-title">Semáforo 30-30-30 por comuna</h1>
    <p class="lede">Días en que el calor, la sequedad y el viento favorecen la propagación del fuego. Toca una comuna en el mapa o en la lista.</p>
    ${risk.dates.length ? html`<div class="day-strip" role="group" aria-label="Día del pronóstico">${risk.dates.map((d) => {
      const s = summary.get(d) || {};
      const worst = s.extremo ? 'extremo' : s.alto ? 'alto' : s.moderado ? 'moderado' : 'bajo';
      return html`<button class="day-cell" data-day="${d}" aria-pressed="${d === day}" title="${s.extremo || 0} comunas en extremo, ${s.alto || 0} en alto">
        <b>${fmtDay(d, { day: undefined, month: undefined })}</b>${fmtDay(d, { weekday: undefined, month: undefined })}<i class="${RISK[worst].cls}"></i></button>`;
    })}</div>` : ''}
    ${empty ? html`<div class="empty" style="margin-top:16px"><div class="glyph">◌</div><b>Aún no hay pronóstico calculado.</b><p class="small">El servidor calcula el índice cada 3 horas con Open-Meteo. Si acabas de iniciarlo, espera unos minutos o revisa su conexión a internet.</p></div>`
      : html`<div class="kpis" style="margin-top:12px">
        <div class="kpi"><small>${RISK.extremo.icon} Extremo</small><strong>${fmtNum(counts.extremo)}</strong><span>comunas</span></div>
        <div class="kpi"><small>${RISK.alto.icon} Alto</small><strong>${fmtNum(counts.alto)}</strong><span>comunas</span></div>
        <div class="kpi"><small>${RISK.moderado.icon} Moderado</small><strong>${fmtNum(counts.moderado)}</strong><span>comunas</span></div></div>`}
    <div class="field" style="margin-top:14px"><label for="r-search">Buscar comuna</label>
      <input class="input" id="r-search" list="r-comunas" placeholder="Ej.: Quilpué" autocomplete="off" />
      <datalist id="r-comunas">${comunas.map((c) => html`<option value="${c.name}">${c.region}</option>`)}</datalist></div>
    <div id="detail"></div>
    ${empty ? '' : html`<h2 class="section">Comunas con mayor riesgo · ${fmtDay(day)}</h2>
      <ul class="list">${ranked.slice(0, 30).map((r) => html`<li><button class="row-btn" data-code="${r.code}">
        <span class="grow"><b class="small">${r.comuna.name}</b><span class="tiny muted"> · ${r.comuna.region}</span>
        <span class="tiny muted" style="display:block">${fmtNum(r.tmax)} °C · HR ${fmtNum(r.rhmin)} % · ${fmtNum(r.windmax)} km/h</span></span>${riskChip(r.level)}</button></li>`)}</ul>`}
    <hr class="rule" />
    ${explainer()}
    ${risk.computed_at ? html`<p class="tiny muted" style="margin-top:10px">Pronóstico calculado ${fmtDateTime(risk.computed_at)} · Open-Meteo.</p>` : ''}`);
  container.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => { day = b.dataset.day; load(container); }));
  container.querySelectorAll('[data-code]').forEach((b) => b.addEventListener('click', () => choose(container, Number(b.dataset.code))));
  container.querySelector('#r-search').addEventListener('change', (e) => {
    const c = comunas.find((x) => x.name.toLowerCase() === e.target.value.trim().toLowerCase());
    if (c) choose(container, c.code);
  });
  if (selected) renderDetail(container, selected);
}

function choose(container, code) {
  selected = code;
  selectComuna(code);
  const c = (store.get('comunasIndex') || []).find((x) => x.code === code);
  if (c) fitBbox(c.bbox, 60);
  renderDetail(container, code);
  container.querySelector('#detail')?.scrollIntoView({ block: 'start' });
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
    container.innerHTML = '<p class="eyebrow">Riesgo meteorológico</p><h1 class="view-title">Cargando el pronóstico…</h1>';
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
