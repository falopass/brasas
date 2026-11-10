/* CARGA-UI: «Calidad» pinta al instante con el estado que ya está en el store (el que
 * trajo la portada), sin esperar a que respondan /api/status ni los extras; y un extra
 * que falla no bloquea el resto ni tira la pantalla de error (FIX-76/FIX-57 se conservan).
 * Se monta la vista sobre un contenedor falso: el HTML pintado es lo que se verifica.
 * index.js junta todas las suites en un proceso: window va con ??= para no pisar el stub
 * de otra suite (ui.js lo pide al importar) y document/matchMedia/fetch se instalan dentro
 * de cada prueba y se restauran en after(). */
import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} };

const { api } = await import('../../web/js/api.js');
const { store } = await import('../../web/js/store.js');
const { default: calidad } = await import('../../web/js/views/calidad.js');

const apiStatusOriginal = api.status;
const guardados = {};
const instalar = (nombre, valor) => {
  if (!(nombre in guardados)) guardados[nombre] = globalThis[nombre];
  globalThis[nombre] = valor;
};

after(() => {
  api.status = apiStatusOriginal;
  store.set('status', null);
  for (const nombre of Object.keys(guardados)) globalThis[nombre] = guardados[nombre];
});

const estado = () => ({
  version: '0.0.0-prueba',
  ingest_mode: 'cron',
  last_ingest_at: new Date().toISOString(),
  freshness: { stale: false },
  newest_observation: {},
  runs: [], history: {}, goes_sweeps: [], incidents_open: {},
  firms_configured: false, firms_quota: {}, open_meteo: {},
  errors: { cycle_errors: [] },
  risk_computed_at: new Date().toISOString(),
  backup: { bytes: 1, updated_at: new Date().toISOString() },
  last_cycle: {},
});

/* DOM mínimo para el camino de mount: #map-legend se limpia, #map-summary y #toasts no
 * existen (updateSummary y toast salen al instante) y [data-retry] siempre está tras
 * pintar — el botón se acaba de escribir en innerHTML. */
const prepararDom = () => {
  instalar('document', {
    hidden: false,
    activeElement: null,
    addEventListener() {},
    dispatchEvent() {},
    getElementById: () => null,
    querySelector: (sel) => (sel === '#map-legend' ? { innerHTML: '' } : null),
  });
  instalar('matchMedia', () => ({ matches: true })); // movimiento reducido: el latido no agenda frames
  instalar('requestAnimationFrame', () => 0);
};

const contenedor = () => ({
  innerHTML: '',
  scrollTop: 0,
  querySelector: (sel) => (sel === '[data-retry]' ? { addEventListener() {}, disabled: false } : null),
  addEventListener: () => {},
  contains: () => false,
});

const json = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('CARGA-UI · Calidad pinta sin esperar', () => {
  test('con el estado del store pinta al instante, sin esperar a /api/status ni a los extras', async () => {
    prepararDom();
    const pendiente = () => new Promise(() => {}); // nunca responde
    api.status = pendiente;
    instalar('fetch', pendiente);
    store.set('status', estado());
    const c = contenedor();
    try {
      await calidad.mount(c); // resuelve tras el pintado síncrono: no espera la red
      assert.match(c.innerHTML, /Calidad de los datos/);
      assert.match(c.innerHTML, /Al día/); // el resumen ya se ve con el estado del store
      assert.match(c.innerHTML, /Licencia y atribución/); // las secciones externas también pintaron su base
      assert.doesNotMatch(c.innerHTML, /No se pudo consultar el estado/);
    } finally {
      calidad.unmount();
      store.set('status', null);
    }
  });

  test('un extra que falla avisa en el aviso parcial y el resto completa igual', async () => {
    prepararDom();
    api.status = async () => ({ ...estado(), history: { FAKE: [{ ok: true, started_at: new Date().toISOString() }] } });
    instalar('fetch', async (path) => {
      const url = String(path);
      if (url.includes('/api/opendata/response.json')) return new Response('caído', { status: 503 });
      if (url.includes('/web/data/calibracion.json')) return json({ summary: { median_min: 42, n_incidents: 5, max_min: 80 }, generated_at: '2026-10-20T00:00:00Z' });
      if (url.includes('/api/quality/feedback')) return json({ total: 3, counts: { sirvio: 2 }, since: '2026-10-01T00:00:00Z' });
      if (url.includes('/web/data/licencias.json')) return json({ terceros: [['GOES-19', 'NOAA — https://noaa.gov']], propios: [['Peligro', 'Cálculo propio']] });
      if (url.includes('/api/observability/routes')) return json({ n: 10, p50_ms: 100, p95_ms: 900, routes: [] });
      if (url.includes('/api/observability/concordancia')) return json({ dias_riesgo: 0 });
      return new Response('no encontrado', { status: 404 });
    });
    store.set('status', null); // ni siquiera hace falta el estado del store para completar lo demás
    const c = contenedor();
    try {
      await calidad.mount(c);
      await tick(); // que las consultas en paralelo terminen de repintar
      await tick();
      assert.match(c.innerHTML, /No pudimos cargar: tiempos de respuesta de CONAF/); // aviso parcial FIX-76
      assert.match(c.innerHTML, /Sirvieron los avisos/); // el extra que sí respondió pintó
      assert.match(c.innerHTML, /Licencia y atribución/); // licencias llegaron por su cuenta
      assert.match(c.innerHTML, /Al día/); // el estado con historial también completó
      assert.doesNotMatch(c.innerHTML, /No se pudo consultar el estado/); // un fallo parcial no tira la vista
    } finally {
      calidad.unmount();
    }
  });

  test('si falla la consulta del estado, la vista avisa que muestra el de la portada', async () => {
    prepararDom();
    api.status = async () => { const err = new Error('caído'); err.status = 503; throw err; };
    instalar('fetch', () => new Promise(() => {}));
    store.set('status', { ...estado(), time_utc: new Date(Date.now() - 5 * 60000).toISOString() });
    const c = contenedor();
    try {
      await calidad.mount(c);
      await tick();
      assert.match(c.innerHTML, /No pudimos actualizar el estado ahora/);
      assert.doesNotMatch(c.innerHTML, /No se pudo consultar el estado de las fuentes/);
    } finally {
      calidad.unmount();
      store.set('status', null);
    }
  });

  test('sin estado ni respuesta del servidor sí sale la pantalla de error con salida', async () => {
    prepararDom();
    api.status = async () => { const err = new Error('sin conexión'); err.status = 503; throw err; };
    instalar('fetch', () => new Promise(() => {}));
    store.set('status', null);
    const c = contenedor();
    try {
      await calidad.mount(c);
      await tick();
      assert.match(c.innerHTML, /No se pudo consultar el estado de las fuentes/); // FIX-57 intacto
      assert.match(c.innerHTML, /data-retry/);
    } finally {
      calidad.unmount();
    }
  });
});
