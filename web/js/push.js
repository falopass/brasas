/* Service worker y Web Push (VAPID). */
import { api } from './api.js';

/** Registra el service worker. Si una versión nueva toma el control, `onUpdate` permite ofrecer recargar. */
export async function registerServiceWorker(onUpdate) {
  if (!('serviceWorker' in navigator)) return null;
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (hadController) onUpdate?.(); });
  try {
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' });
    setInterval(() => registration.update().catch(() => {}), 30 * 60000);
    return registration;
  } catch {
    return null;
  }
}

export async function pushState() {
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  return { supported, permission: supported ? Notification.permission : 'unsupported' };
}

function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function enablePush(publicKey) {
  const { supported } = await pushState();
  if (!supported) throw new Error('Este navegador no admite notificaciones web.');
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Debes permitir las notificaciones en el navegador.');
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  }
  const json = subscription.toJSON();
  await api.pushSubscribe({ endpoint: json.endpoint, keys: json.keys });
}

/** Desactiva los avisos: borra la suscripción del servidor y la del navegador.

 * Las dos cosas, en ese orden: si primero se borrara la del navegador y fallara la llamada, el
 * servidor seguiría guardando un endpoint que ya no entrega nada.
 */
export async function disablePush() {
  await api.pushUnsubscribe();
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) await subscription.unsubscribe();
}
