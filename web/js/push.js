/* Service worker y Web Push (VAPID). */
import { api } from './api.js';

export async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    return await navigator.serviceWorker.register('/sw.js', { scope: '/' });
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
