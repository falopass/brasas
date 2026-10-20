/* Pruebas de web/js/globe.js (PERF-01/UX-15) con node:test, sin navegador ni dependencias:
 * dobles de window.Cesium y de document para comprobar que el bucle de render se pausa
 * cuando la pestaña queda oculta. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { openGlobe, renderLoopFor } from '../../web/js/globe.js';

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
