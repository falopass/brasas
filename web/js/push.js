/* Service worker y Web Push (VAPID). */
import { api } from './api.js';
import { esperarConfig } from './config.js';

const PUSH_PENDING = 'brasa-push-pending';
const PUSH_PENDING_KEY = '/__push-pending';
const PUSH_UNSUB_KEY = '/__push-unsubscribe-pending';
// UX-75: el contador del ícono de la app, en la misma caché que escribe el service worker.
const BADGE_CACHE = 'brasa-badge';
const BADGE_KEY = '/__badge-count';

// Interruptor de la sesión: con los avisos apagados, ninguna resincronización en vuelo
// puede volver a darlos de alta. `enablePush` lo levanta al completar el alta.
let disabled = false;

const pushEnabled = () => 'Notification' in window && Notification.permission === 'granted';

/** Reenvía al servidor lo que quedó pendiente: primero una baja anotada sin señal (manda la
 * intención de apagar) y después la suscripción que el service worker renovó sin ventana
 * abierta (FIX: rotación push). Con `disabled` no se registra nada nuevo.
 */
export async function flushPendingSubscription() {
  if (!pushEnabled()) return;
  const cache = await caches.open(PUSH_PENDING);
  if (await cache.match(PUSH_UNSUB_KEY)) {
    await api.pushUnsubscribe();
    await cache.delete(PUSH_UNSUB_KEY);
  }
  if (disabled) return;
  const hit = await cache.match(PUSH_PENDING_KEY);
  if (!hit) return;
  const sub = await hit.json();
  // La baja pudo ocurrir mientras se leía la caché: se mira otra vez antes del alta.
  if (disabled) return;
  await api.pushSubscribe({ endpoint: sub.endpoint, keys: sub.keys });
  await cache.delete(PUSH_PENDING_KEY);
}

let resyncDiferido = null; // una sola comprobación de clave diferida por sesión, compartida

/** Garantiza una suscripción con la clave fresca: devuelve la vigente si coincide (o no hay
 *  clave); si difiere o no existe, da de baja la vieja y crea otra. */
async function suscripcionConClave(registration, key) {
  const sub = await registration.pushManager.getSubscription();
  if (!key || (sub && mismaClave(sub, key))) return sub;
  if (sub) await sub.unsubscribe().catch(() => {});
  return registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
}

const enviarAlta = async (subscription) => {
  if (!subscription || disabled) return;
  const json = subscription.toJSON();
  await api.pushSubscribe({ endpoint: json.endpoint, keys: json.keys });
};

/** Reenvía la suscripción vigente: el alta es un UPDATE idempotente por dispositivo. */
async function resyncSubscription() {
  if (!pushEnabled() || disabled) return;
  const registration = await navigator.serviceWorker.ready;
  const key = (await esperarConfig({ fresca: true }))?.push?.public_key;
  if (key) return enviarAlta(await suscripcionConClave(registration, key));
  // Sin clave fresca aún no se puede comparar (REND-02/seg): se difiere UNA comprobación
  // compartida al llegar la config fresca (sin bucles ni envíos duplicados) y la vigente
  // se reenvía igual que siempre.
  resyncDiferido ??= esperarConfig({ fresca: true, timeoutMs: 120000 })
    .then((cfg) => { resyncDiferido = null; comprobarClaveDiferida(registration, cfg?.push?.public_key); })
    .catch(() => { resyncDiferido = null; });
  return enviarAlta(await registration.pushManager.getSubscription());
}

/** Comprobación diferida: si la clave fresca difiere de la de la suscripción vigente, se
 *  re-crea y se reenvía; si coincide o no hay clave, no se envía nada. */
async function comprobarClaveDiferida(registration, key) {
  if (!key || !pushEnabled() || disabled) return;
  const sub = await registration.pushManager.getSubscription();
  if (sub && !mismaClave(sub, key)) await enviarAlta(await suscripcionConClave(registration, key));
}

/** Registra el service worker. Si una versión nueva toma el control, `onUpdate` permite ofrecer recargar. */
export async function registerServiceWorker(onUpdate) {
  if (!('serviceWorker' in navigator)) return null;
  // Avisa desde la segunda toma de control: la primera es la instalación inicial.
  let teniaController = Boolean(navigator.serviceWorker.controller);
  const pedirPrecacheDiferido = () => {
    try { navigator.serviceWorker.controller?.postMessage({ type: 'PRECACHE_DATA' }); } catch { /* sin soporte */ }
  };
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    const era = teniaController;
    teniaController = true;
    pedirPrecacheDiferido();
    if (era) onUpdate?.();
  });
  if (teniaController) {
    const lanzar = () => pedirPrecacheDiferido();
    if (typeof requestIdleCallback === 'function') requestIdleCallback(lanzar, { timeout: 5000 });
    else setTimeout(lanzar, 4000);
  }
  try {
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' });
    setInterval(() => registration.update().catch(() => {}), 30 * 60000);
    // Si el navegador rota la suscripción push, el service worker la deja en la caché y avisa:
    // aquí se reenvía al servidor. Fallos silenciosos: la próxima apertura lo reintenta.
    const resync = () => { flushPendingSubscription().catch(() => {}); resyncSubscription().catch(() => {}); };
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data?.type === 'brasa:push-resubscribed') resync();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') flushPendingSubscription().catch(() => {});
    });
    resync();
    return registration;
  } catch {
    return null;
  }
}

/** Qué hacer cuando una versión nueva del service worker toma el control: recarga una sola
 * vez por pestaña (`yaRecargo`), salvo que haya un formulario abierto o «Marcarlo en el mapa»
 * esté eligiendo el punto —el borrador vive solo en memoria—; ahí difiere hasta el cierre del
 * diálogo. El navegador encola el `close` como tarea y pickOnMap marca `picking` en el mismo
 * bloque síncrono que cierra el diálogo, así que al reevaluar la elección ya está en curso.
 * Si ya recargó en esta pestaña, avisa con `avisar` para recargar a mano.
 * Las piezas se inyectan para probar el flujo sin navegador. */
export function crearManejadorRecargaSw({ modal, body, yaRecargo, recargar, avisar }) {
  const alActualizar = () => {
    if (modal?.open || body.classList.contains('picking')) {
      if (modal && !modal.dataset.swUpdate) {
        modal.dataset.swUpdate = '1';
        modal.addEventListener('close', () => { delete modal.dataset.swUpdate; alActualizar(); }, { once: true });
      }
      return;
    }
    if (!yaRecargo()) { recargar(); return; }
    avisar();
  };
  return alActualizar;
}

/** iPhone/iPad: iPadOS se declara como Mac con pantalla táctil. */
export const detectIos = (nav = navigator) => /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1);

/** Estado de los avisos, calculado sin esperar nada: lo usa pushState (envuelto en promesa
 *  para probar sin navegador) y pedirPermisoPush, que necesita el gesto del clic vivo. */
function pushStateSync(env = {}) {
  const hasServiceWorker = env.hasServiceWorker ?? ('serviceWorker' in navigator);
  const hasPushManager = env.hasPushManager ?? ('PushManager' in window);
  const hasNotification = env.hasNotification ?? ('Notification' in window);
  const supported = hasServiceWorker && hasPushManager && hasNotification;
  return {
    supported,
    permission: supported ? (env.permission ?? Notification.permission) : 'unsupported',
    standalone: env.standalone ?? (matchMedia('(display-mode: standalone)').matches || navigator.standalone === true),
    isIos: env.isIos ?? detectIos(),
  };
}

/** Estado de los avisos. `env` permite probar la decisión sin navegador; cada pieza ausente se lee del navegador. */
export async function pushState(env = {}) {
  return pushStateSync(env);
}

/** Pide el permiso de notificaciones con el gesto del clic aún vivo: Safari solo muestra el
 *  diálogo si se pide en el mismo turno del clic, sin awaits antes. Valida soporte y estado
 *  sin pedir; con permiso ya resuelto no se re-pregunta. Devuelve { problema, permiso }:
 *  `problema` es null cuando el diálogo va en camino y `permiso` una promesa con el estado.
 *  `env` permite probarlo sin navegador, como pushState. */
export function pedirPermisoPush(env = {}) {
  const state = pushStateSync(env);
  const problema = pushProblem(state);
  if (problema || state.permission !== 'default') return { problema, permiso: Promise.resolve(state.permission) };
  const resultado = Notification.requestPermission(); // llamada síncrona, con el gesto vivo
  return { problema: null, permiso: Promise.resolve(resultado) };
}

/** Diagnóstico de por qué no se pueden activar los avisos, con la acción que lo resuelve. */
export function pushProblem({ supported, permission, standalone, isIos }) {
  if (!supported) {
    if (isIos && !standalone) {
      return { title: 'Los avisos necesitan BRASA instalada', help: 'En iPhone o iPad: Compartir → Añadir a pantalla de inicio. Después abre BRASA desde ese ícono y activa los avisos.' };
    }
    return { title: 'Este navegador no admite avisos', help: 'Prueba con Chrome, Edge o Firefox en su versión actual.' };
  }
  if (permission === 'denied') {
    return { title: 'Avisos bloqueados', help: 'Los avisos están bloqueados para este sitio. Ábrelos así: candado en la barra de direcciones → Notificaciones → Permitir.' };
  }
  return null;
}

export function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

/** Compara, byte a byte, la clave de servidor de la suscripción con la clave pública actual:
 *  si rotó (VAPID), el servidor ya no podría avisar con la suscripción vieja. Ante cualquier
 *  duda (sin clave registrada, error), no coincide. */
function mismaClave(subscription, publicKey) {
  try {
    const actual = subscription?.options?.applicationServerKey;
    if (!actual) return false;
    const esperada = urlBase64ToUint8Array(publicKey);
    const bytes = actual instanceof ArrayBuffer ? new Uint8Array(actual) : actual;
    return bytes?.length === esperada.length && esperada.every((b, i) => b === bytes[i]);
  } catch { return false; }
}

export async function enablePush(publicKey, { permiso } = {}) {
  const state = await pushState();
  const problem = pushProblem(state);
  // Si ya está bloqueado (o falta instalar en iOS), pedir permiso otra vez no sirve: se explica cómo arreglarlo.
  if (problem) throw new Error(`${problem.title}: ${problem.help}`);
  // Si el clic ya pidió el permiso con el gesto vivo (pedirPermisoPush), no se re-pregunta:
  // Safari exige el gesto y el resultado ya está en camino. Sin `permiso` se pide aquí.
  const permission = await (permiso ?? Notification.requestPermission());
  if (permission !== 'granted') throw new Error('Debes permitir las notificaciones en el navegador.');
  const registration = await navigator.serviceWorker.ready;
  // Una suscripción nacida con otra clave (rotación de VAPID) no sirve: se re-crea con la
  // actual, sin pedir permiso de nuevo.
  const subscription = await suscripcionConClave(registration, publicKey);
  const json = subscription.toJSON();
  await api.pushSubscribe({ endpoint: json.endpoint, keys: json.keys });
  disabled = false;
  // Un alta que sí salió vuelve obsoleta cualquier baja anotada sin señal.
  if ('caches' in window) await caches.open(PUSH_PENDING).then((c) => c.delete(PUSH_UNSUB_KEY)).catch(() => {});
}

/** Desactiva los avisos: primero lo local (la suscripción del navegador y lo pendiente en
 * caché) y después el servidor. Sin señal el dispositivo igual queda en silencio: la baja se
 * anota en la misma caché y el próximo resync la reenvía. Un fallo de red nunca revienta la baja.
 */
export async function disablePush() {
  disabled = true;
  const cache = 'caches' in window ? await caches.open(PUSH_PENDING).catch(() => null) : null;
  if (cache) await cache.delete(PUSH_PENDING_KEY).catch(() => {});
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) await subscription.unsubscribe();
  try {
    await api.pushUnsubscribe();
    if (cache) await cache.delete(PUSH_UNSUB_KEY).catch(() => {});
  } catch {
    if (cache) await cache.put(PUSH_UNSUB_KEY, new Response('{}')).catch(() => {});
  }
}

/** UX-75: al abrir Avisos, el número sobre el ícono vuelve a cero (el service worker hace
 *  lo mismo al tocar la notificación). Donde no hay Badging API no pasa nada. */
export async function clearBadge() {
  try {
    if ('caches' in window) {
      const cache = await caches.open(BADGE_CACHE);
      await cache.put(BADGE_KEY, new Response('0', { headers: { 'Content-Type': 'application/json' } }));
    }
    if ('clearAppBadge' in navigator) await navigator.clearAppBadge();
  } catch { /* sin badge que limpiar */ }
}
