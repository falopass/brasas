/* Modo vecino: la familia ve, sin cuenta y en solo lectura, cómo está un lugar que alguien compartió.
 * Pensado para hijos que vigilan la casa de sus padres: letra grande, el estado en una frase, qué hacer y a quién llamar. */
import { api } from '../api.js';
import { fly, placesGeoJSON, setData, show } from '../map.js';
import { store } from '../store.js';
import { phonesHtml, placeForm } from '../ui.js';
import { $, ago, emberSvg, html, minutesSince } from '../util.js';
import { dayStrip, guidanceFor, officialBlock, placeBody, STATUS, statusText } from './zona.js';

let mounted = false;
let timer = null;

async function render(container, token) {
  let data;
  try { data = await api.shared(token); } catch (err) {
    if (!mounted) return;
    container.innerHTML = String(html`<div class="ember-hero" role="status">${emberSvg({ tone: 'tranquilo' })}
      <div><div class="hero-label">Este enlace ya no funciona</div><small>${err.status === 404 ? 'Quien lo compartió dejó de compartirlo, o el enlace está incompleto.' : err.message}</small></div></div>
      <p class="small">Pídele un enlace nuevo a quien te lo envió, o guarda tú mismo el lugar para recibir avisos.</p>
      <a class="btn btn-primary btn-lg btn-block" href="#/mi-zona">Ir a BRASA</a>`);
    return null;
  }
  if (!mounted) return null;
  const { place, status } = data;
  const stale = data.data_as_of && minutesSince(data.data_as_of) > 30;
  const official = (data.official || []).find((f) => f.inside_radius && f.status !== 'extinguido');
  const { points, radius } = placesGeoJSON([{ ...place, id: 'compartido' }]);
  setData('places', points); setData('place-radius', radius);
  container.innerHTML = String(html`
    <div class="ember-hero st-${status}" role="status">${emberSvg({ tone: status })}
      <div><div class="hero-label">${STATUS[status].title}</div>
        <small>En «${place.name}»${data.comuna ? `, ${data.comuna.name}` : ''}. ${statusText(status, data.cause)}.</small>
        ${status === 'urgente' ? html`<div class="btn-row hero-cta"><a class="btn btn-sm btn-call" href="tel:132">Llamar a Bomberos · 132</a></div>` : ''}</div></div>
    ${stale ? html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(data.data_as_of)}.</b> Que no veamos fuego no significa que no lo haya.</div>` : ''}
    <h1 class="view-title">${place.name}</h1>
    <p class="lede">Lo compartieron contigo para que puedas estar atento. Se actualiza solo.</p>
    ${place.older_adult ? html`<div class="callout"><b>Aquí vive una persona mayor o alguien que necesita ayuda para salir.</b> Por eso cualquier calor cerca se trata como urgente: hay que avisar con tiempo.</div>` : ''}
    <article class="card place-card st-border-${status}">${placeBody({ ...place, comuna: data.comuna }, data)}${dayStrip(data.risk_days)}</article>
    ${official ? html`<h2 class="section">Lo que dice la autoridad</h2>${officialBlock(official, data.official_source)}` : ''}
    <h2 class="section">Qué hacer ahora</h2>
    <ol class="steps">${guidanceFor(status, place.older_adult).map((g) => html`<li>${g}</li>`)}</ol>
    <button class="btn btn-primary btn-lg btn-block" id="follow">Recibir avisos de este lugar en mi teléfono</button>
    <p class="tiny muted" style="margin-top:6px">Se guarda como un lugar tuyo: te avisaremos aunque no tengas BRASA abierta.</p>
    <h2 class="section">Emergencias</h2>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:14px">Vista de solo lectura. Quien la compartió puede cortar el enlace cuando quiera. BRASA es una ayuda ciudadana: no reemplaza las alertas de SENAPRED.</p>`);
  container.querySelector('#follow').addEventListener('click', () => placeForm(null, { ...place }));
  return data;
}

export default {
  id: 'v',
  sheet: 'half',
  nav: false,
  async mount(container, { rest }) {
    mounted = true;
    document.documentElement.classList.add('vecino-on');
    show(['places', 'place-radius-fill', 'place-radius-line', 'detections', 'goes-pixels', 'goes-pixels-line'], true);
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore', 'reports'], false);
    $('#map-legend').innerHTML = '';
    const token = rest?.[0] || '';
    container.innerHTML = '<h1 class="view-title">Cargando el lugar compartido…</h1>';
    const data = await render(container, token);
    if (data && mounted) fly(data.place.lon, data.place.lat, data.place.radius_km > 15 ? 9.5 : 10.5);
    timer = setInterval(() => mounted && render(container, token), 120000);
  },
  unmount() {
    mounted = false;
    clearInterval(timer);
    document.documentElement.classList.remove('vecino-on');
    store.set('places', store.get('places')); // vuelve a pintar tus propios lugares
  },
};
