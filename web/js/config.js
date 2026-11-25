/* Espera de la configuración del servidor (/api/config) sin bloquear el arranque (REND-02).
 *
 * La configuración la pide una sola vez app.js al arrancar, en segundo plano (con sus
 * reintentos) y la deja en el store bajo «config». Este módulo es el modo compartido de
 * esperarla:
 *
 * - esperarConfig({ timeoutMs, signal, fresca }) resuelve con la configuración y con null
 *   si vence el plazo o si el llamador aborta su `signal`. Nunca rechaza. Un `signal` ya
 *   abortado gana siempre, incluso con la configuración disponible: un consumidor
 *   cancelado (vista cerrada, modal repintado) no ejecuta acciones muertas.
 * - `fresca: true` espera la configuración que trajo pedirConfig en ESTA sesión (app.js la
 *   marca con marcarConfigFresca). Sin ella se devuelve la que haya —incluida la copia
 *   guardada en este dispositivo—, que solo sirve para pintar: los envíos (reportes y
 *   push) usan la fresca, porque una copia vieja pudo rotar o perder la clave Turnstile o
 *   la clave push, y con claves viejas el servidor rechazaría cada intento.
 * - La espera de un consumidor jamás cancela la petición compartida: no toca su señal.
 *   Quien aborta solo deja de esperar; el arranque y los demás consumidores siguen.
 * - Cada espera limpia su temporizador y su suscripción al store al resolver, vencer o
 *   abortarse: los remontajes y aperturas repetidas no acumulan nada.
 */
import { store } from './store.js';
import { storage } from './util.js';

const DEFAULT_TIMEOUT_MS = 4000;

let fresca = false; // ¿ya llegó el store.set de pedirConfig en esta sesión?

/** Marca que la configuración fresca de esta sesión está a punto de entrar al store.
 *  La llama app.js justo ANTES del store.set, para que quien espera la fresca la vea al
 *  llegar el evento y no confunda la copia guardada con la vigente. */
export function marcarConfigFresca() { fresca = true; }

export function esperarConfig({ timeoutMs = DEFAULT_TIMEOUT_MS, signal, fresca: quiereFresca = false } = {}) {
  if (signal?.aborted) return Promise.resolve(null); // el aborto gana: nada de acciones muertas
  const inmediata = quiereFresca
    ? (fresca ? store.get('config') : null) // la copia guardada no vale para envíos
    : (store.get('config') || storage.get('config'));
  if (inmediata) return Promise.resolve(inmediata);
  return new Promise((resolve) => {
    let off = null;
    let timer = 0;
    let lista = false;
    const terminar = (valor) => {
      if (lista) return;
      lista = true;
      clearTimeout(timer);
      off?.();
      signal?.removeEventListener?.('abort', alAbortar);
      resolve(valor);
    };
    const alAbortar = () => terminar(null);
    off = store.on('config', (cfg) => {
      // fresca: la copia que siembra el arranque no resuelve envíos; solo la configuración
      // que trajo pedirConfig en esta sesión (app.js marcó la llegada antes del evento).
      if (quiereFresca && !fresca) return;
      terminar(cfg || null);
    });
    if (signal) signal.addEventListener('abort', alAbortar, { once: true });
    timer = setTimeout(() => terminar(null), timeoutMs);
  });
}
