/* Modo vecino: la familia ve, sin cuenta y en solo lectura, cómo está un lugar que alguien compartió.
 * Pensado para hijos que vigilan la casa de sus padres: letra grande, el estado en una frase, qué hacer y a quién llamar. */
import { api, request } from '../api.js';
import { fly, placesGeoJSON, setData, show } from '../map.js';
import { enablePush } from '../push.js';
import { adopt, speak, stopSpeak, synth } from '../speak.js';
import { store } from '../store.js';
import { phonesHtml } from '../ui.js';
import { $, ago, cardWord, dual, emberSvg, fmtDateTime, fmtNum, fmtTime, html, keepPlace, minutesSince, toast } from '../util.js';
import { dayStrip, guidanceFor, officialBlock, placeBody, STATUS, statusText } from './zona.js';

let mounted = false;
let timer = null;
let onVisible = null;
let fingerprint = null; // huella del último pintado: si nada relevante cambió, no se repinta (UX-47)

/* Avisos oficiales de viento y calor de la DMC que tocan la comuna del lugar compartido:
   la misma redacción en lenguaje claro de «Mi zona», con el enlace y la nota de que no es de BRASA. */
function dmcBlock(list, source) {
  if (!list?.length) return '';
  const first = list[0];
  return html`<h2 class="section">Avisos oficiales</h2>
    <div class="callout"><b>${[...new Set(list.map((a) => a.label))].join(' y ')}</b> de la DMC ${dual(`hasta ${fmtDateTime(first.expires)}`, `${first.event} · severidad ${first.severity} · vence ${fmtDateTime(first.expires)}`)}.
    <a href="${first.web || source?.url}" target="_blank" rel="noopener">Ver en la DMC ↗</a>
    <div class="tiny muted" style="margin-top:4px">Es un aviso oficial de la Dirección Meteorológica de Chile, no de BRASA: BRASA solo lo muestra.</div></div>`;
}

/* UX-47: «¿le llegó el aviso a este lugar?». Una línea en la tarjeta: qué fue, hace cuánto y si se entregó.
   Sin aviso en las últimas 48 h no se muestra nada (null del servidor). */
const ALERT_KIND = { foco: 'foco de calor', oficial: 'incendio informado por CONAF', reporte: 'reporte de un vecino',
                     dmc: 'aviso de la DMC', diario: 'revisión preventiva de la mañana' };

function lastAlertLine(alert) {
  if (!alert) return '';
  const label = ALERT_KIND[alert.kind] || 'aviso';
  const how = alert.delivered_at ? `entregado ${fmtTime(alert.delivered_at)}` : 'aún sin entregar';
  return html`<p class="tiny muted" style="margin-top:8px">Último aviso${alert.level === 'urgente' ? ' urgente' : ''}: ${label}, ${ago(alert.created_at)} · ${how}.</p>`;
}

/* Lo que dice «Escuchar», en una sola frase. Se calcula aparte para compararla entre refrescos:
   si no cambió, la lectura en voz alta sigue aunque la tarjeta se repinte (UX-47). */
function speechFor(place, data, dmc) {
  return `${STATUS[data.status].title}. En «${place.name}»${data.comuna ? `, ${data.comuna.name}` : ''}. ${statusText(data.status, data.cause)}.${
    dmc.length ? ` La Dirección Meteorológica de Chile tiene un aviso vigente para la comuna: ${[...new Set(dmc.map((a) => a.label))].join(' y ')}, hasta ${fmtDateTime(dmc[0].expires)}.` : ''
  } BRASA no es una alerta oficial: sigue a SENAPRED.`;
}

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
  // UX-47: si no cambió lo que se ve (estado, fecha de los datos, último aviso), repintar solo
  // movería la pantalla y cortaría la lectura en voz alta. El enlace sigue siendo el mismo.
  const fp = JSON.stringify([data.status, data.data_as_of, data.last_alert]);
  if (fp === fingerprint) return data;
  fingerprint = fp;
  const { place, status } = data;
  const stale = data.data_as_of && minutesSince(data.data_as_of) > 30;
  const seen = new Set();
  const fichas = (data.nearby || []).filter((o) => o.incident_id && !seen.has(o.incident_id) && seen.add(o.incident_id))
    .sort((a, b) => a.distance_km - b.distance_km).slice(0, 3);
  const official = (data.official || []).find((f) => f.inside_radius && f.status !== 'extinguido');
  const dmc = data.dmc_alerts || [];
  const { points, radius } = placesGeoJSON([{ ...place, id: 'compartido' }]);
  setData('places', points); setData('place-radius', radius);
  // La tarjeta omite la línea DMC de placeBody: abajo va el bloque «Avisos oficiales» con el enlace.
  const cardSummary = { ...data, dmc_alerts: [] };
  const speech = speechFor(place, data, dmc);
  keepPlace(container, () => {
    container.innerHTML = String(html`
    <div class="ember-hero st-${status}" role="status">${emberSvg({ tone: status })}
      <div><div class="hero-label">${STATUS[status].title}</div>
        <small>En «${place.name}»${data.comuna ? `, ${data.comuna.name}` : ''}. ${statusText(status, data.cause)}.</small>
        ${status === 'urgente' || synth ? html`<div class="btn-row hero-cta">${status === 'urgente' ? html`<a class="btn btn-sm btn-call" href="tel:132">Llamar a Bomberos · 132</a>` : ''}
          ${synth ? html`<button class="btn btn-sm btn-speak" id="v-listen" type="button" aria-label="Escuchar el estado en voz alta">Escuchar</button>` : ''}</div>` : ''}</div></div>
    ${stale ? html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(data.data_as_of)}.</b> Que no veamos fuego no significa que no lo haya.</div>` : ''}
    <h1 class="view-title">${place.name}</h1>
    <p class="lede">Lo compartieron contigo para que puedas estar atento. Se actualiza solo.</p>
    ${data.data_as_of ? html`<p class="tiny muted">Actualizado ${ago(data.data_as_of)}.</p>` : ''}
    ${place.older_adult ? html`<div class="callout"><b>Aquí vive una persona mayor o alguien que necesita ayuda para salir.</b> Por eso cualquier calor cerca se trata como urgente: hay que avisar con tiempo.</div>` : ''}
    <article class="card place-card st-border-${status}">${placeBody({ ...place, comuna: data.comuna }, cardSummary)}${lastAlertLine(data.last_alert)}${dayStrip(data.risk_days)}</article>
    <button class="btn btn-primary btn-lg btn-block" id="follow">Que me avisen a mí también</button>
    <p class="tiny muted" style="margin-top:6px">Se guarda una copia en este navegador: si quien lo compartió corta el enlace, tu lugar y tus avisos siguen funcionando.</p>
    ${dmcBlock(dmc, data.dmc_source)}
    ${official ? html`<h2 class="section">Lo que dice la autoridad</h2>${officialBlock(official, data.official_source)}` : ''}
    ${fichas.length ? html`<h2 class="section">Focos con ficha</h2>
      <ul class="list">${fichas.map((o) => html`<li><a class="row-btn" href="#/incendio/${o.incident_id}"><span class="grow small">a ${fmtNum(o.distance_km, o.distance_km < 3 ? 1 : 0)} km, hacia el ${cardWord(o.direction)} · <span class="tiny muted">visto ${ago(o.observed_at)}</span></span></a></li>`)}</ul>` : ''}
    <h2 class="section">Qué hacer ahora</h2>
    <ol class="steps">${guidanceFor(status, place.older_adult).map((g) => html`<li>${g}</li>`)}</ol>
    <button class="btn btn-lg btn-block" id="reshare" style="margin-top:10px">Compartir el enlace</button>
    <p class="tiny muted" style="margin-top:6px">Reenvíaselo a otra persona de la familia para que también vea este lugar.</p>
    <h2 class="section">Emergencias</h2>
    ${phonesHtml()}
    <p class="tiny muted" style="margin-top:14px">Vista de solo lectura. Quien la compartió puede cortar el enlace cuando quiera. BRASA es una ayuda ciudadana: no reemplaza las alertas de SENAPRED.</p>`);
    const follow = container.querySelector('#follow');
    follow.addEventListener('click', async () => {
      follow.disabled = true;
      follow.textContent = 'Guardando…';
      try {
        const { created } = await request(`/api/shared/${encodeURIComponent(token)}/follow`, { method: 'POST', auth: true });
        const key = store.get('config')?.push?.public_key;
        if (key) {
          try { await enablePush(key); } catch (err) { toast(err.message, 'error'); }
        }
        document.dispatchEvent(new CustomEvent('brasa:places-changed'));
        if (!mounted) return;
        follow.textContent = created ? 'Listo: te avisaremos de este lugar' : 'Ya lo tenías guardado: tus avisos siguen igual';
      } catch (err) {
        if (!mounted) return;
        follow.disabled = false;
        follow.textContent = 'Reintentar';
        toast(err.message, 'error');
      }
    });
    const listen = container.querySelector('#v-listen');
    listen?.addEventListener('click', () => speak(speech, listen));
    if (!adopt(speech, listen)) stopSpeak(); // misma frase: sigue sonando; otra: se corta
    container.querySelector('#reshare').addEventListener('click', async () => {
      const url = `${location.origin}/#/v/${token}`;
      // La URL ya va dentro del texto: pasarla también como `url` la duplicaría en Android/Chromium.
      const text = `Mira cómo está «${place.name}» frente a incendios, en BRASA: ${url}`;
      if (navigator.share) {
        try { await navigator.share({ title: `BRASA · ${place.name}`, text }); return; } catch (err) { if (err?.name === 'AbortError') return; }
      }
      try { await navigator.clipboard.writeText(text); toast('Enlace copiado.'); }
      catch { toast('No se pudo copiar el enlace.', 'error'); }
    });
  });
  return data;
}

export default {
  id: 'v',
  sheet: 'half',
  nav: false,
  async mount(container, { rest }) {
    mounted = true;
    fingerprint = null;
    document.documentElement.classList.add('vecino-on');
    show(['places', 'place-radius-fill', 'place-radius-line', 'detections', 'goes-pixels', 'goes-pixels-line'], true);
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore', 'reports'], false);
    $('#map-legend').innerHTML = '';
    const token = rest?.[0] || '';
    container.innerHTML = '<h1 class="view-title">Cargando el lugar compartido…</h1>';
    const data = await render(container, token);
    if (data && mounted) fly(data.place.lon, data.place.lat, data.place.radius_km > 15 ? 9.5 : 10.5);
    const restart = () => { clearInterval(timer); timer = setInterval(() => { if (mounted && !document.hidden) render(container, token); }, 120000); };
    restart();
    onVisible = () => { if (mounted && document.visibilityState === 'visible') { render(container, token); restart(); } };
    document.addEventListener('visibilitychange', onVisible);
  },
  unmount() {
    mounted = false;
    clearInterval(timer);
    stopSpeak();
    document.removeEventListener('visibilitychange', onVisible);
    document.documentElement.classList.remove('vecino-on');
    store.set('places', store.get('places')); // vuelve a pintar tus propios lugares
  },
};
