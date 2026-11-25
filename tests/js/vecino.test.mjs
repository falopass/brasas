/* «Lo que hay alrededor» en la vista vecino (#/v/<token>): contexto breve de la comuna
 * del lugar compartido — población y viviendas del Censo 2024 (OFI-07) y la interfaz
 * urbano-forestal (OFI-08) en lenguaje llano, sin cuenta y sin datos de personas.
 * vecino.js arrastra ui.js y speak.js, que tocan `window` al cargarse: stub mínimo como
 * en riesgo.test.mjs (index.js junta todas las suites en un proceso). fetch se simula
 * dentro del describe, como en smoke.test.mjs, para no pisar a otras suites. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { default: vistaVecino, aroundBlock, trendBlock } = await import('../../web/js/views/vecino.js');
const { officialBlock } = await import('../../web/js/views/zona.js');
const { comunaExposure, comunaExposureOf } = await import('../../web/js/exposure.js');
const { marcarConfigFresca } = await import('../../web/js/config.js');
const { store } = await import('../../web/js/store.js');
const { storage } = await import('../../web/js/util.js');

// comuna.code = 7101 (Talca). Los archivos reales tienen esta forma:
// censo_2024.json → comunas: [{code, poblacion, viviendas, …}]; interfaz.json → comunas: {codigo: {…}}.
const CENSO = { comunas: [{ code: 7101, poblacion: 220000, viviendas: 80000 }] };
const CON_INTERFAZ = { comunas: { 7101: { ha_interfaz: 6054.7, pct_comuna: 17.31 } } };
const SIN_INTERFAZ = { comunas: {} };

describe('«Lo que hay alrededor»', () => {
  test('con censo e interfaz: dos cifras, la frase llana y la fuente', () => {
    const exposure = comunaExposureOf(CENSO, CON_INTERFAZ, 7101);
    assert.deepEqual(exposure, { poblacion: 220000, viviendas: 80000, interfaz: true });
    const section = String(aroundBlock(exposure));
    assert.ok(section.includes('Lo que hay alrededor'));
    assert.ok(section.includes('220.000'));
    assert.ok(section.includes('80.000'));
    assert.ok(section.includes('bosque toca las casas'));
    assert.ok(section.includes('Censo 2024'));
    assert.ok(section.includes('CONAF GEPRIF'));
  });

  test('sin zonas de interfaz la frase lo dice en claro', () => {
    const exposure = comunaExposureOf(CENSO, SIN_INTERFAZ, 7101);
    assert.equal(exposure.interfaz, false);
    const section = String(aroundBlock(exposure));
    assert.ok(section.includes('no registra interfaz urbano-forestal'));
    assert.ok(!section.includes('bosque toca'));
    assert.ok(section.includes('220.000'));
  });

  test('comuna fuera del censo → la sección no aparece', () => {
    assert.equal(comunaExposureOf(CENSO, CON_INTERFAZ, 9999), null);
    assert.equal(String(aroundBlock(null)), '');
    assert.equal(String(aroundBlock(undefined)), '');
  });
});

describe('pronóstico de esta semana contra el de la semana pasada (VECINO-01)', () => {
  const summary = (counts) => ({ sube: 0, baja: 0, igual: 0, sin_anterior: 0, sin_hoy: 0, ...counts });
  const row = (change, label, extra = {}) => ({
    target_date: '2026-10-24', current: 'alto', previous: 'moderado', change, change_label: label, missing: null, ...extra,
  });
  const bloque = (summaryCounts, rows) => String(trendBlock({ summary: summary(summaryCounts), rows }));

  test('cuando sube, lo dice y nombra el día', () => {
    const out = bloque({ sube: 1 }, [row('sube', 'Más alto que el pronóstico de la semana pasada')]);
    assert.ok(out.includes('Pronóstico de esta semana contra el de la semana pasada'));
    assert.ok(out.includes('Esta semana 1 día sube'));
    assert.ok(out.includes('24'), 'la fila debe nombrar el día del pronóstico');
    assert.ok(out.includes('Más alto que el pronóstico de la semana pasada'));
    assert.ok(out.includes('Son pronósticos, no lo que pasó.'));
  });

  test('cuando baja, muestra el paso entre los dos niveles', () => {
    const out = bloque({ baja: 1 }, [row('baja', 'Más bajo que el pronóstico de la semana pasada', { current: 'moderado', previous: 'alto' })]);
    assert.ok(out.includes('Esta semana 1 día baja'));
    assert.ok(out.includes('alto → moderado'));
  });

  test('cuando sigue igual, no inventa una comparación', () => {
    const out = bloque({ igual: 1 }, [row('igual', 'Igual que el pronóstico de la semana pasada', { current: 'alto', previous: 'alto' })]);
    assert.ok(out.includes('1 día sigue igual'));
    assert.ok(out.includes('alto · Igual que el pronóstico de la semana pasada'));
  });

  test('sin pronóstico de la semana pasada avisa sin alarmar', () => {
    const out = bloque({ sin_anterior: 1 }, [row('sin_anterior', 'No hay pronóstico de la semana pasada para ese día', { previous: null, missing: 'semana_pasada' })]);
    assert.ok(out.includes('Sin pronóstico de la semana pasada para comparar'));
    assert.ok(out.includes('No hay pronóstico de la semana pasada para ese día'));
    assert.ok(!out.includes('sube') && !out.includes('baja'));
  });

  test('sin datos o con null no se pinta nada', () => {
    assert.equal(String(trendBlock(null)), '');
    assert.equal(String(trendBlock(undefined)), '');
    assert.equal(String(trendBlock({})), '');
    assert.equal(String(trendBlock({ summary: summary({}), rows: [] })), '');
  });
});

/* OFI-04 opción 2: la vista compartida siempre muestra el bloque «¿Qué dijo la autoridad?»
   (sin incendio CONAF el enlace a SENAPRED es lo único que queda) y le pasa el nombre de la
   comuna del lugar como tercer argumento. Aquí se fija ese contrato del helper compartido. */
describe('enlace a la alerta oficial de SENAPRED (OFI-04)', () => {
  test('con la comuna del lugar compartido el enlace la nombra y abre en otra pestaña', () => {
    const out = String(officialBlock(null, null, 'Talca'));
    assert.ok(out.includes('href="https://senapred.cl/alertas/"'));
    assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener"'));
    assert.ok(out.includes('alerta oficial vigente para Talca'));
  });
  test('sin incendio de CONAF el bloque sigue existiendo: no afirma nada por BRASA', () => {
    const out = String(officialBlock(null, null, 'Curicó'));
    assert.ok(out.includes('¿Qué dijo la autoridad?'));
    assert.ok(!out.includes('CONAF:'));
    assert.ok(!/no hay alerta|sin alerta/i.test(out));
  });
});

describe('archivo de datos ausente o sin conexión', () => {
  beforeEach(() => {
    globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
  });
  afterEach(() => {
    delete globalThis.fetch;
  });

  test('la sección no aparece y nada más cambia', async () => {
    const exposure = await comunaExposure(7101);
    assert.equal(exposure, null);
    assert.equal(String(aroundBlock(exposure)), '');
  });
});

/* seg/UX: «Que me avisen a mí también» guarda el lugar (POST follow) y activa los avisos.
 * Si los AVISOS fallan, el lugar ya quedó guardado en el servidor: el reintento del botón
 * repite solo la activación de los avisos, nunca el POST follow. Se monta la vista de verdad
 * con el contenedor y el document de mentira; fetch y localStorage se simulan dentro del
 * describe y se restauran, para no pisar a otras suites del proceso (index.js las une). */
describe('«Que me avisen a mí también»: el reintento tras un fallo de avisos no repite el POST follow', () => {
  // Resumen compartido mínimo y válido: tranquilo, sin calor cerca, sin comuna (nada extra se pide).
  const SHARED = {
    place: { name: 'Casa de mamá', lat: -35.5, lon: -71.5, radius_km: 10, older_adult: true },
    status: 'tranquilo', cause: null, data_as_of: null, last_alert: null, trend: null,
    estoy_bien: null, protected_area: null, nearby: [], official: [], dmc_alerts: [],
    dmc_source: null, comuna: null, risk_days: null,
  };
  let previos;
  let follow;
  let container;
  let peticiones;
  let follows;

  beforeEach(() => {
    previos = {
      window: globalThis.window,
      document: globalThis.document,
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      matchMedia: globalThis.matchMedia,
      setInterval: globalThis.setInterval,
      localStorage: globalThis.localStorage,
    };
    peticiones = [];
    follows = 0;
    const guardado = new Map();
    globalThis.localStorage = {
      getItem: (k) => (guardado.has(k) ? guardado.get(k) : null),
      setItem: (k, v) => guardado.set(k, String(v)),
      removeItem: (k) => guardado.delete(k),
    };
    // El POST follow lleva auth: con el token ya guardado no hay alta de dispositivo.
    storage.set('token', 'tok-dispositivo');
    globalThis.window = globalThis;
    // El latido del mapa no arranca (movimiento reducido) y matchMedia responde por consulta.
    globalThis.matchMedia = (q) => ({ matches: q.includes('prefers-reduced-motion') });
    // Navegador sin serviceWorker: los avisos no pueden activarse aquí, que es justo el fallo
    // que deja el botón como reintento. Con la clave fresca presente, el fallo es solo push.
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: { userAgent: 'Mozilla/5.0 (X11; Linux x86_64) rv:1.0 Node', platform: 'Linux x86_64', maxTouchPoints: 0 },
    });
    globalThis.document = {
      documentElement: { classList: { add() {}, remove() {} } },
      addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
      hidden: true, visibilityState: 'hidden', activeElement: null,
      getElementById: () => null,
      querySelector: (sel) => (sel === '#map-legend' ? { innerHTML: '' } : null), // mount escribe ahí
    };
    globalThis.setInterval = () => 0; // sin el ciclo de refresco de 2 min
    globalThis.fetch = async (url, init) => {
      const camino = String(url);
      peticiones.push(camino);
      const json = (body) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
      if (camino === '/api/shared/tok/follow') { follows += 1; return json({ created: true }); }
      if (camino === '/api/shared/tok') return json(SHARED);
      throw new Error('inesperado: ' + camino);
    };
    // La clave de push viaja en la configuración FRESCA de esta sesión (REND-02): con ella el
    // segundo clic llega a reintentar la activación y se comprueba que no envía nada nuevo.
    marcarConfigFresca();
    store.set('config', { push: { public_key: 'BCk-clave-de-prueba-no-real' } });
    follow = {
      disabled: false,
      textContent: 'Que me avisen a mí también',
      alClic: null,
      addEventListener(tipo, fn) { if (tipo === 'click') this.alClic = fn; },
    };
    container = {
      scrollTop: 0,
      innerHTML: '',
      contains: () => false,
      querySelector: (sel) => (sel === '#follow' ? follow : (sel === '#reshare' ? { addEventListener() {} } : null)),
    };
  });

  afterEach(() => {
    delete globalThis.fetch;
    if (previos.localStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previos.localStorage;
    if (previos.window === undefined) delete globalThis.window;
    else globalThis.window = previos.window;
    if (previos.document === undefined) delete globalThis.document;
    else globalThis.document = previos.document;
    if (previos.matchMedia === undefined) delete globalThis.matchMedia;
    else globalThis.matchMedia = previos.matchMedia;
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
    globalThis.setInterval = previos.setInterval;
    store.set('config', null);
  });

  test('primer clic guarda el lugar y falla los avisos; el segundo reintenta solo los avisos', async () => {
    await vistaVecino.mount(container, { rest: ['tok'] });
    assert.ok(follow.alClic, 'el botón «Que me avisen a mí también» quedó con su manejador');
    assert.deepEqual(peticiones, ['/api/shared/tok']); // hasta aquí, solo el resumen compartido
    await follow.alClic(); // primer clic: guarda el lugar, los avisos no se activan
    assert.equal(follows, 1);
    assert.equal(follow.disabled, false); // queda habilitado como reintento de los avisos
    assert.equal(follow.textContent, 'Lugar guardado; avisos no activados');
    assert.deepEqual(peticiones, ['/api/shared/tok', '/api/shared/tok/follow']);
    await follow.alClic(); // segundo clic: reintento de SOLO los avisos
    assert.equal(follows, 1, 'el POST follow no se repite: el lugar ya quedó guardado en el servidor');
    assert.deepEqual(peticiones, ['/api/shared/tok', '/api/shared/tok/follow'],
      'la activación falla antes de enviar nada: no hay más peticiones');
    assert.equal(follow.disabled, false);
    assert.equal(follow.textContent, 'Lugar guardado; avisos no activados'); // sigue siendo reintento
  });

  test('el texto feliz queda reservado para el alta completa, aunque el lugar sea nuevo', async () => {
    await vistaVecino.mount(container, { rest: ['tok'] });
    await follow.alClic();
    assert.equal(follow.textContent, 'Lugar guardado; avisos no activados');
    assert.notEqual(follow.textContent, 'Listo: te avisaremos de este lugar');
  });
});
