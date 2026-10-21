/* Estado global mínimo con suscripciones. Una sola fuente de verdad para vistas, mapa y línea temporal. */
import { pendientes } from './reportes.js';
import { storage } from './util.js';

const state = {
  config: null,
  theme: 'dark',
  view: 'mi-zona',
  places: [],
  observations: [],
  obsHours: 24,
  obsFilter: { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } },
  status: null,
  risk: null,
  online: typeof navigator !== 'undefined' ? navigator.onLine : true,
};
const listeners = new Map();

export const store = {
  get: (key) => state[key],
  set(key, value) {
    state[key] = value;
    (listeners.get(key) || []).forEach((fn) => {
      try {
        Promise.resolve(fn(value)).catch((err) => console.error('store', key, err));
      } catch (err) {
        console.error('store', key, err);
      }
    });
  },
  on(key, fn) {
    if (!listeners.has(key)) listeners.set(key, new Set());
    listeners.get(key).add(fn);
    return () => listeners.get(key).delete(fn);
  },
};

const PREFERENCIAS = ['theme', 'text', 'detail'];

/* Inventario de lo que BRASA guarda en este dispositivo (SEC-01): conteos y nombres de
 * preferencia, nunca el token, coordenadas ni el contenido de un reporte. Vive aquí y no
 * en util.js porque reúne tres fuentes —storage, la cola de reportes y la caché del
 * service worker— y util.js es la base que reportes.js importa: al revés habría un ciclo.
 * `pendientes()` es la dueña del plazo de la cola y de paso retira lo vencido. */
export async function inventarioLocal(now = Date.now()) {
  const crudas = storage.get('outbox', []);
  const enCola = pendientes(now);
  const vigentes = new Set(enCola.map((e) => e.id));
  const vencidos = (Array.isArray(crudas) ? crudas : []).filter((e) => !vigentes.has(e.id)).length;
  return {
    token: Boolean(storage.get('token')),
    preferencias: PREFERENCIAS.filter((key) => storage.get(key) !== null),
    reportes_en_cola: enCola.length,
    reportes_vencidos: vencidos,
    cache_api: await contarCacheApi(),
  };
}

async function contarCacheApi() {
  if (typeof caches === 'undefined') return 0;
  try {
    const nombres = (await caches.keys()).filter((name) => name.endsWith('-api'));
    const cuentas = await Promise.all(nombres.map(async (name) => (await (await caches.open(name)).keys()).length));
    return cuentas.reduce((total, n) => total + n, 0);
  } catch { return 0; }
}
