/* Pruebas de web/js/globe.js (PERF-01/UX-15) con node:test, sin navegador ni dependencias:
 * dobles de window.Cesium y de document para comprobar que el bucle de render se pausa
 * cuando la pestaña queda oculta. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { CESIUM_DEADLINE_MESSAGE, openGlobe, renderLoopFor, withDeadline } from '../../web/js/globe.js';

function fakeCesium() {
  const scene = {
    globe: {},
    primitives: { add: (p) => p },
    renders: 0,
    requestRender() { scene.renders += 1; },
  };
  const viewer = {
    scene,
    dataSources: { add: (d) => d },
    camera: { flyTo() {} },
    useDefaultRenderLoop: true,
  };
  return {
    Ion: { defaultAccessToken: null },
    UrlTemplateImageryProvider: function () {},
    ImageryLayer: function () {},
    Viewer: function () { return viewer; },
    PointPrimitiveCollection: function () {},
    CustomDataSource: function () {},
    Terrain: { fromWorldTerrain: () => ({}) },
    viewer,
  };
}

function fakeDocument() {
  const listeners = [];
  return {
    hidden: false,
    listeners,
    addEventListener(type, fn) { if (type === 'visibilitychange') listeners.push(fn); },
    fire() { for (const fn of listeners) fn(); },
  };
}

// Los dobles se instalan dentro de las pruebas, no al importar: tests/js/index.js junta
// todas las suites en un proceso y otras dependen de su propio window.
const cesium = fakeCesium();
const doc = fakeDocument();

describe('renderLoopFor', () => {
  test('con la pestaña oculta apaga el bucle aunque estuviera encendido', () => {
    assert.equal(renderLoopFor(true, true), false);
    assert.equal(renderLoopFor(true, false), false);
  });
  test('con la pestaña visible conserva el estado actual', () => {
    assert.equal(renderLoopFor(false, true), true);
    assert.equal(renderLoopFor(false, false), false);
  });
});

describe('openGlobe con la pestaña oculta', () => {
  test('apaga el bucle al ocultar y lo enciende con un cuadro al volver', async () => {
    globalThis.window = { ...globalThis.window, addEventListener() {}, Cesium: cesium };
    globalThis.document = doc;
    await openGlobe({}, {});
    doc.hidden = true;
    doc.fire();
    assert.equal(cesium.viewer.useDefaultRenderLoop, false);
    const renders = cesium.viewer.scene.renders;
    doc.hidden = false;
    doc.fire();
    assert.equal(cesium.viewer.useDefaultRenderLoop, true);
    assert.equal(cesium.viewer.scene.renders, renders + 1);
  });
  test('dos openGlobe no registran dos manejadores', async () => {
    globalThis.window = { ...globalThis.window, addEventListener() {}, Cesium: cesium };
    globalThis.document = doc;
    await openGlobe({}, {});
    await openGlobe({}, {});
    assert.equal(doc.listeners.length, 1);
  });
});

describe('withDeadline', () => {
  test('deja pasar la promesa que resuelve antes del plazo', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    assert.equal(await withDeadline(Promise.resolve('Cesium'), 20000, 'no debería vencer'), 'Cesium');
  });

  test('rechaza con el mensaje del plazo si la promesa nunca resuelve', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const pendiente = withDeadline(new Promise(() => {}), 20000, 'La vista 3D pesa unos 6 MB y no cargó en 20 s.');
    const rechazo = assert.rejects(pendiente, /no cargó en 20 s/);
    t.mock.timers.tick(20000);
    await rechazo;
  });

  test('conserva el motivo original cuando la promesa rechaza', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    await assert.rejects(withDeadline(Promise.reject(new Error('sin CDN')), 20000, 'tarde'), /sin CDN/);
  });

  test('el mensaje del plazo dice qué pasó y sugiere el mapa 2D', () => {
    assert.match(CESIUM_DEADLINE_MESSAGE, /6 MB/);
    assert.match(CESIUM_DEADLINE_MESSAGE, /no cargó en 20 s/);
    assert.match(CESIUM_DEADLINE_MESSAGE, /mapa 2D/);
  });
});

describe('loadCesium cuando la descarga falla', () => {
  test('limpia el script y el link, y el segundo intento avisa al instante', async () => {
    const mod = await import('../../web/js/globe.js?fallo');
    const prevWindow = globalThis.window;
    const prevDocument = globalThis.document;
    const head = { nodes: [], append(n) { head.nodes.push(n); } };
    globalThis.window = {};
    globalThis.document = {
      head,
      createElement(tag) { return { tag, removed: false, remove() { this.removed = true; } }; },
    };
    try {
      const primero = mod.openGlobe({}, {});
      const script = head.nodes.find((n) => n.tag === 'script');
      const css = head.nodes.find((n) => n.tag === 'link');
      script.onerror();
      await assert.rejects(primero, /No se pudo descargar/);
      assert.equal(script.removed, true);
      assert.equal(css.removed, true);
      await assert.rejects(mod.openGlobe({}, {}), /no está disponible en esta conexión/);
    } finally {
      globalThis.window = prevWindow;
      globalThis.document = prevDocument;
    }
  });
});
