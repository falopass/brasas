/* Service worker de BRASA: interfaz disponible sin conexión, últimos datos en caché y notificaciones push. */
// El despliegue reemplaza esta versión por el hash del commit (deploy-cloudflare.yml): cada publicación renueva la caché.
const VERSION = 'brasa-dev';
const SHELL = [
  '/', '/manifest.webmanifest', '/web/css/app.css',
  '/web/lite.html', '/web/js/lite.js', '/web/lista.html', '/web/css/lista.css',
  '/web/js/app.js', '/web/js/api.js', '/web/js/store.js', '/web/js/util.js', '/web/js/map.js', '/web/js/charts.js',
  '/web/js/ui.js', '/web/js/push.js', '/web/js/globe.js', '/web/js/motion.js', '/web/js/data.js',
  '/web/js/views/zona.js', '/web/js/views/mapa.js', '/web/js/views/riesgo.js', '/web/js/views/casos.js', '/web/js/views/preparate.js', '/web/js/views/vecino.js', '/web/js/views/incendio.js', '/web/js/views/calidad.js',
  '/web/vendor/maplibre/maplibre-gl.js', '/web/vendor/maplibre/maplibre-gl.css',
  '/web/data/comunas.geojson', '/web/data/comunas-index.json', '/web/data/regiones.geojson', '/web/data/cases.json',
  '/web/icons/icon.svg', '/web/icons/icon-192.png',
  '/web/vendor/fonts/anybody-latin-standard-normal.woff2', '/web/vendor/fonts/public-sans-latin-wght-normal.woff2',
];
const API_CACHE = `${VERSION}-api`;
// Suscripción push renovada por el navegador mientras no había ventana abierta: la app la reenvía al servidor al volver.
const PUSH_PENDING = 'brasa-push-pending';
// Datos públicos y, a propósito, tus lugares y avisos: en una emergencia sin señal siguen visibles en tu propio teléfono.
const CACHEABLE_API = ['/api/config', '/api/observations', '/api/risk', '/api/status', '/api/cases', '/api/places', '/api/alerts', '/api/reports', '/api/shared', '/api/incidents', '/api/official-fires'];

self.addEventListener('install', (event) => {
  // Archivo por archivo: si uno falla (red inestable), el resto igual queda disponible sin conexión.
  event.waitUntil(caches.open(VERSION)
    .then((cache) => Promise.allSettled(SHELL.map((path) => cache.add(new Request(path, { cache: 'reload' })))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION) && k !== PUSH_PENDING).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET') {
    // Al editar o borrar un lugar, se olvida lo guardado de tus lugares (nombres incluidos) hasta la próxima consulta.
    if (url.origin === self.location.origin && url.pathname.startsWith('/api/places')) {
      event.respondWith(fetch(request).then(async (response) => {
        const cache = await caches.open(API_CACHE);
        const keys = await cache.keys();
        await Promise.all(keys.filter((k) => new URL(k.url).pathname.startsWith('/api/places')).map((k) => cache.delete(k)));
        return response;
      }));
    }
    return;
  }
  if (url.origin !== self.location.origin) return; // teselas y CDN: el navegador decide
  if (url.pathname.startsWith('/api/')) {
    if (!CACHEABLE_API.some((p) => url.pathname.startsWith(p))) return;
    // Red primero; si no hay conexión, la última respuesta guardada (la app muestra su antigüedad).
    event.respondWith(fetch(request).then((response) => {
      if (response.ok) { const copy = response.clone(); caches.open(API_CACHE).then((c) => c.put(request, copy)); }
      return response;
    }).catch(() => caches.match(request).then((hit) => {
      if (!hit) return new Response(JSON.stringify({ detail: 'Sin conexión' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
      // Marca cuándo se generó el dato guardado: la interfaz la muestra como «datos de hace N min».
      const saved = new Date(hit.headers.get('date') || '');
      const headers = new Headers(hit.headers);
      headers.set('X-Brasa-Cached-At', (Number.isNaN(saved.getTime()) ? new Date() : saved).toISOString());
      return new Response(hit.body, { status: hit.status, statusText: hit.statusText, headers });
    })));
    return;
  }
  // Interfaz: caché primero y actualización en segundo plano.
  event.respondWith(caches.match(request).then((hit) => {
    const network = fetch(request).then((response) => {
      if (response.ok && (url.pathname.startsWith('/web/') || url.pathname === '/')) {
        const copy = response.clone(); caches.open(VERSION).then((c) => c.put(request, copy));
      }
      return response;
    }).catch(() => hit);
    return hit || network;
  }));
});

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: 'BRASA Chile', body: event.data?.text() }; }
  const urgent = data.level === 'urgente';
  event.waitUntil(self.registration.showNotification(data.title || 'BRASA Chile', {
    body: `${data.body || ''}\n${data.footer || ''}`.trim(),
    icon: '/web/icons/icon-192.png', badge: '/web/icons/icon-192.png',
    tag: data.place?.id ? `place-${data.place.id}` : undefined,
    renotify: urgent, requireInteraction: urgent,
    vibrate: urgent ? [300, 120, 300, 120, 600] : [200],
    data: { url: data.url || '/#/mi-zona' },
  }));
});

function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

self.addEventListener('pushsubscriptionchange', (event) => {
  // El navegador rotó la suscripción (rotación de claves del servicio push, limpieza de almacenamiento).
  // El service worker no puede reenviarla al servidor (el alta exige el token del dispositivo, que
  // vive en la página), así que guarda la suscripción nueva en la caché y la app la reenvía al abrirse.
  event.waitUntil((async () => {
    let subscription = event.newSubscription;
    if (!subscription) {
      const config = await fetch('/api/config').then((r) => r.json());
      subscription = await self.registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(config.push.public_key),
      });
    }
    const cache = await caches.open(PUSH_PENDING);
    await cache.put('/__push-pending', new Response(JSON.stringify(subscription.toJSON()),
      { headers: { 'Content-Type': 'application/json' } }));
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    clients.forEach((client) => client.postMessage({ type: 'brasa:push-resubscribed' }));
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
    const existing = clients.find((c) => c.url.startsWith(self.location.origin));
    if (existing) { existing.navigate(target); return existing.focus(); }
    return self.clients.openWindow(target);
  }));
});
