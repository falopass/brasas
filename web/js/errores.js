/* Bloque de error compartido de las vistas (UX-16): qué pasó, «Reintentar» sobre el mismo loader
 * y los teléfonos de emergencia. Un solo módulo para que el texto no se desdoble entre vistas. */
import { phonesHtml } from './ui.js';
import { dual, html } from './util.js';

/** HTML del «error con salida»: mismo marcado en todas las vistas. */
export const errorConSalidaHtml = (err) => String(html`<div class="callout callout-warn" role="alert">
    <b>${dual('No pudimos cargar esto ahora.', `Error al cargar: ${err.message}`)}</b>
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-retry>Reintentar</button></div>
    <p class="small" style="margin:12px 0 8px">Si ves fuego o humo cerca, llama de inmediato. No esperes a que lo vea un satélite.</p>
    ${phonesHtml()}</div>`);

/** Pinta el bloque en `host` y enlaza el botón «Reintentar» a `retry`. */
export function errorConSalida(host, err, retry) {
  host.innerHTML = errorConSalidaHtml(err);
  host.querySelector('[data-retry]').addEventListener('click', retry);
}
