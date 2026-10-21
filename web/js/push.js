/* Service worker y Web Push (VAPID). */
import { api } from './api.js';

const PUSH_PENDING = 'brasa-push-pending';
const PUSH_PENDING_KEY = '/__push-pending';
const PUSH_UNSUB_KEY = '/__push-unsubscribe-pending';

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

/** Reenvía la suscripción vigente: el alta es un UPDATE idempotente por dispositivo, así que es barato. */
async function resyncSubscription() {
  if (!pushEnabled() || disabled) return;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription && !disabled) {
    const json = subscription.toJSON();
    await api.pushSubscribe({ endpoint: json.endpoint, keys: json.keys });
  }
}

/** Registra el service worker. Si una versión nueva toma el control, `onUpdate` permite ofrecer recargar. */
export async function registerServiceWorker(onUpdate) {
  if (!('serviceWorker' in navigator)) return null;
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (hadController) onUpdate?.(); });
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

/** iPhone/iPad: iPadOS se declara como Mac con pantalla táctil. */
export const detectIos = (nav = navigator) => /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1);

/** Estado de los avisos. `env` permite probar la decisión sin navegador; cada pieza ausente se lee del navegador. */
export async function pushState(env = {}) {
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

export async function enablePush(publicKey) {
  const state = await pushState();
  const problem = pushProblem(state);
  // Si ya está bloqueado (o falta instalar en iOS), pedir permiso otra vez no sirve: se explica cómo arreglarlo.
  if (problem) throw new Error(`${problem.title}: ${problem.help}`);
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Debes permitir las notificaciones en el navegador.');
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  }
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
