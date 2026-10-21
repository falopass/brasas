/* Estado global mínimo con suscripciones. Una sola fuente de verdad para vistas, mapa y línea temporal. */

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
        fn(value);
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
