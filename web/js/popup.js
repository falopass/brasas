/* Un solo popup a la vez sobre el mapa, en cualquier vista: el estado vive aquí para
 * que la ficha del punto de calor en «Mi zona» y los popups del Mapa no queden
 * abiertos a la vez ni se borren entre sí. */
import { getMap } from './map.js';
import { placeForm, reportForm } from './ui.js';
import { incidentInfo } from './views/incendio.js';
import { ago, dual, fmtDateTime, fmtNum, fmtUTC, html, SENSOR_LABEL } from './util.js';

let popup = null;

/** Abre el único popup del mapa (cierra el anterior) y devuelve su elemento para atar botones. */
export function abrirPopup(lngLat, contenido, maxWidth = '280px') {
  popup?.remove();
  popup = new maplibregl.Popup({ maxWidth, offset: 10 }).setLngLat(lngLat).setHTML(String(contenido)).addTo(getMap());
  return popup.getElement();
}

export function cerrarPopup() { popup?.remove(); popup = null; }

/** Ficha corta de un punto de calor: la misma que abre el Mapa; «Mi zona» la comparte. */
export function popupFoco(obs, lngLat) {
  const age = ago(obs.observed_at);
  const reliable = ['alta', 'nominal', 'media'].includes(obs.confidence);
  const el = abrirPopup(lngLat, html`<div style="max-width:250px">
    <b>Punto de calor</b> · <span class="muted">visto ${age}</span>
    <div class="small" style="margin-top:4px">${obs.comuna ? `${obs.comuna}, ${obs.region}` : 'Fuera del territorio chileno'}</div>
    <p class="small x-plain" style="margin:8px 0 0">${obs.sensor === 'ABI' ? 'Lo vio un satélite que mira Chile cada 10 minutos. Marca una zona de unos 2 km: el calor está en algún punto dentro del cuadro.' : 'Lo vio un satélite que pasa sobre Chile unas veces al día. Su ubicación es bastante precisa.'}
      ${reliable ? 'Puede ser un incendio, una quema o una industria.' : 'Es una señal dudosa: puede no ser fuego.'}</p>
    <div class="x-tech small" style="margin-top:6px">
      <div>${SENSOR_LABEL[obs.sensor] || obs.sensor} · <b>${obs.satellite || obs.source}</b></div>
      <div>${fmtDateTime(obs.observed_at)} Chile · ${fmtUTC(obs.observed_at)}</div>
      <div>FRP ${obs.frp_mw != null ? `${fmtNum(obs.frp_mw, 1)} MW` : 'n/d'} · confianza ${obs.confidence || 'n/d'} · ${obs.sensor === 'ABI' ? 'píxel ~2–3 km' : `píxel ${obs.resolution_m || 375} m`}</div>
      <div class="tabular">${obs.lat.toFixed(4)}, ${obs.lon.toFixed(4)}</div></div>
    ${obs.incident_id && obs.incident_n > 1 ? html`<p class="small" style="margin:8px 0 0"><b>${incidentInfo({ status: obs.incident_status, fixed_source: obs.incident_fixed }).title}</b> · ${dual(`se vio calor ${obs.incident_n} veces aquí`, `${obs.incident_n} detecciones agrupadas`)}</p>
      <a class="btn btn-sm btn-primary" style="margin-top:6px" href="#/incendio/${obs.incident_id}">Ver qué ha pasado aquí</a>` : ''}
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" id="pp-watch">Avisarme si hay más aquí</button><button class="btn btn-sm btn-ghost" id="pp-report">Contar lo que veo</button></div></div>`);
  el.querySelector('#pp-watch').addEventListener('click', () => { cerrarPopup(); placeForm(null, { lat: obs.lat, lon: obs.lon }); });
  el.querySelector('#pp-report').addEventListener('click', () => { cerrarPopup(); reportForm({ lat: obs.lat, lon: obs.lon }); });
}
