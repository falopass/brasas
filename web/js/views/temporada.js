/* Panorama de la temporada (TEMP-01/02): incendios CONAF, superficie por región y comuna,
 * estado oficial y días con Botón Rojo; con selector para mirar otra temporada. Solo
 * agregados de los reportes que BRASA ya recibe, con la fuente a la vista. Sin datos de personas. */
import { request } from '../api.js';
import { show } from '../map.js';
import { store } from '../store.js';
import { $, ago, dual, fmtDateTime, fmtNum, html, toast } from '../util.js';

const kpi = (label, value, sub) => html`<div class="kpi"><small>${label}</small><strong class="kpi-text">${value}</strong><span>${sub}</span></div>`;

const phones = html`<div class="tiny muted" style="margin-top:10px">Si ves fuego o humo, llama al <a href="tel:130"><b>130</b> (CONAF)</a> o al <a href="tel:132"><b>132</b> (Bomberos)</a> y entrega la ubicación exacta.</div>`;

function emptyState(data) {
  return html`<div class="empty"><div class="glyph">◎</div>${data.season
    ? `CONAF no ha informado incendios en la temporada ${data.season} todavía.`
    : 'Todavía no hay incendios oficiales guardados.'}
    ${phones}</div>`;
}

/* TEMP-31: la diferencia de la semana en palabras, sin porcentajes que sugieran precisión. */
export function weekDiff(actual, previous) {
  const diff = (actual || 0) - (previous || 0);
  if (diff === 0) return 'igual que la semana pasada';
  return `${fmtNum(Math.abs(diff))} ${diff > 0 ? 'más' : 'menos'} que la semana pasada`;
}

function weekCard(data) {
  const w = data.semana;
  if (!w) return '';
  return html`<div class="callout" style="margin-top:12px">
    <b>Esta semana</b>
    <p class="small">${fmtNum(w.incendios)} ${w.incendios === 1 ? 'incendio informado' : 'incendios informados'} por CONAF, ${weekDiff(w.incendios, w.anterior?.incendios)}.</p>
    <p class="tiny muted">Cuenta los incendios que CONAF ya informó; no es un pronóstico.</p>
  </div>`;
}

/* TEMPORADA-02: la región del primer lugar guardado que tenga comuna; '' si no hay ninguno.
 * Un lugar sin `comuna` (o con `comuna: null`) no rompe la vista: se salta y sigue. */
export function regionPropia(places) {
  return (places || []).find((p) => p?.comuna?.region)?.comuna.region || '';
}

function regionRow(r, totals, propia) {
  const mine = !!propia && r.region === propia;
  const pct = mine && totals?.ha > 0 && r.ha > 0 ? Math.round((r.ha / totals.ha) * 100) : null;
  // Una región con hectáreas pero menos del 0,5 % redondea a 0: decir «el 0 %» sería falso.
  const parte = pct === null ? 'sin superficie informada'
    : pct === 0 ? 'menos del 1 % de la superficie del país' : `el ${pct} % de la superficie del país`;
  const aria = mine ? `${r.region}, tu región: ${fmtNum(r.n)} ${r.n === 1 ? 'incendio' : 'incendios'}, ${fmtNum(r.ha, 1)} ha, ${parte}` : '';
  return html`<li${mine ? html` aria-label="${aria}"` : ''}><div class="grow">
      <b class="small">${r.region || 'Sin región informada'}${mine ? html` <span class="tag">Tu región</span>` : ''}</b>
      <div class="tiny muted">${fmtNum(r.n)} ${r.n === 1 ? 'incendio' : 'incendios'}${r.en_combate ? ` · ${fmtNum(r.en_combate)} en combate` : ''}${mine ? ` · ${parte}` : ''}</div></div>
      <span class="small tabular">${fmtNum(r.ha, 1)} ha</span></li>`;
}

function regions(data, places) {
  if (!data.by_region.length) return '';
  const propia = regionPropia(places);
  const rows = [...data.by_region];
  const at = propia ? rows.findIndex((r) => r.region === propia) : -1;
  if (at > 0) rows.unshift(...rows.splice(at, 1));
  return html`<h2 class="section">${dual('Por región', 'Agregados por región')}</h2>
    <ul class="list">${rows.map((r) => regionRow(r, data.totals, propia))}</ul>`;
}

function seasonPicker(data) {
  if ((data.seasons || []).length < 2) return '';
  return html`<p><label class="small muted" for="season-pick">Temporada</label>
    <select class="input" id="season-pick">${data.seasons.map((s) => html`<option value="${s}"${s === data.season ? ' selected' : ''}>${s}</option>`)}</select></p>`;
}

function comunas(data) {
  if (!data.by_comuna?.length) return '';
  return html`<h2 class="section">${dual('Comunas con más superficie', 'Comunas con más hectáreas afectadas (12 primeras)')}</h2>
    <ul class="list">${data.by_comuna.map((c) => html`<li><div class="grow">
      ${c.comuna_code
        ? html`<a href="#/riesgo?comuna=${c.comuna_code}"><b class="small">${c.comuna}</b></a>`
        : html`<b class="small">${c.comuna || 'Sin comuna informada'}</b>`}
      <div class="tiny muted">${c.region || 'Sin región informada'} · ${fmtNum(c.n)} ${c.n === 1 ? 'incendio' : 'incendios'}${c.en_combate ? ` · ${fmtNum(c.en_combate)} en combate` : ''}</div></div>
      <span class="small tabular">${fmtNum(c.ha, 1)} ha</span></li>`)}</ul>`;
}

export function render(data, places = []) {
  const t = data.totals;
  return html`<h1 class="view-title">Panorama de la temporada${data.season ? html` <span class="tag">${data.season}</span>` : ''}</h1>
    <p class="lede">${dual('Cómo va la temporada de incendios en Chile según el reporte oficial de CONAF: cuántos van, cuánta superficie han afectado y en qué estado están.',
      'Agregados de work.official_fires (reporte público GEPRIF de CONAF) y work.boton_rojo, agrupados por la temporada que declara el CSV.')}</p>
    ${seasonPicker(data)}
    ${weekCard(data)}
    ${t.n === 0 ? emptyState(data) : html`
    <div class="kpis">
      ${kpi(dual('incendios informados', 'incendios en el reporte'), fmtNum(t.n), data.season ? `temporada ${data.season}` : 'sin temporada declarada')}
      ${kpi(dual('hectáreas afectadas', 'superficie total'), `${fmtNum(t.ha, 1)} ha`, 'suma de la superficie declarada por CONAF')}
      ${kpi(dual('días con Botón Rojo', 'días con Botón Rojo'), fmtNum(data.boton_rojo_days), dual('condiciones extremas en las últimas dos semanas', 'pronóstico CONAF; BRASA conserva solo los últimos 14 días'))}
      ${kpi(dual('en combate ahora', 'activos según CONAF'), fmtNum(t.en_combate), 'en combate o bajo observación en el último reporte')}
      ${kpi(dual('controlados', 'controlados'), fmtNum(t.controlados), 'ya no avanzan, pero no están apagados del todo')}
      ${kpi(dual('extinguidos', 'extinguidos'), fmtNum(t.extinguidos), 'apagados según CONAF')}
    </div>
    ${regions(data, places)}
    ${comunas(data)}
    <p class="tiny muted" style="margin-top:10px">${data.boton_rojo_source.note} Fuente: <a href="${data.boton_rojo_source.url}" target="_blank" rel="noopener">${data.boton_rojo_source.name}</a>.</p>`}
    <p class="tiny muted" style="margin-top:14px">Fuente: <a href="${data.source.url}" target="_blank" rel="noopener">CONAF (incendios informados)</a>${data.updated_at ? html` · datos de ${ago(data.updated_at)} (${fmtDateTime(data.updated_at)})` : ''}. ${data.not_official}</p>
    ${data.unknown_status?.n > 0 ? html`<p class="tiny muted" style="margin-top:10px">${fmtNum(data.unknown_status.n)} ${data.unknown_status.n === 1 ? 'incendio del reporte trae' : 'incendios del reporte traen'} un estado que BRASA no reconoce.</p>` : ''}`;
}

export default {
  id: 'temporada',
  sheet: 'full',
  async mount(container, { params } = {}) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    // Región viva persistente (mismo nodo en cada repintado): anuncia el cambio de temporada
    // solo cuando quien usa el teclado la cambia; vacía al entrar, para no hablar de más.
    const live = document.createElement('p');
    live.className = 'sr-only';
    live.setAttribute('role', 'status');
    live.setAttribute('aria-live', 'polite');
    const places = store.get('places') || [];
    const load = async (season, announce = false) => {
      try {
        const data = await request(`/api/panorama${season ? `?season=${encodeURIComponent(season)}` : ''}`);
        container.innerHTML = String(render(data, places));
        container.append(live);
        const pick = container.querySelector('#season-pick');
        pick?.addEventListener('change', (e) => load(e.target.value, true));
        if (announce) {
          pick?.focus({ preventScroll: true });
          live.textContent = `Temporada ${data.season || season} cargada`;
        }
      } catch (err) {
        container.innerHTML = String(html`<h1 class="view-title">Panorama de la temporada</h1>
          <div class="callout callout-warn" role="alert">
            <b>${dual('No se pudo consultar el panorama. Revisa tu conexión y vuelve a intentarlo.', `Error al consultar el panorama: ${err.message}`)}</b>
            <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-retry>Reintentar</button></div>
            ${phones}</div>`);
        container.append(live);
        container.querySelector('[data-retry]').addEventListener('click', () => load(season, announce));
        toast(err.message, 'error');
      }
    };
    await load(params?.season);
  },
};
