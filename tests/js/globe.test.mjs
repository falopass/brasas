/* Pruebas de web/js/globe.js (PERF-01/UX-15/UX-04) con node:test, sin navegador ni dependencias:
 * dobles de window.Cesium y de document para comprobar que el bucle de render se pausa
 * cuando la pestaña queda oculta, y de Element para la leyenda y el texto accesible. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { CESIUM_DEADLINE_MESSAGE, describeGlobe, openGlobe, renderLoopFor, withDeadline } from '../../web/js/globe.js';

function fakeEl() {
  return {
    attrs: {},
    children: [],
    style: {},
    className: '',
    innerHTML: '',
    textContent: '',
    setAttribute(k, v) { this.attrs[k] = String(v); },
    append(...nodes) { this.children.push(...nodes); },
  };
}

function fakeCesium() {
  const c = {};
  const scene = {
    globe: {},
    primitives: { add: (p) => { c.points = p; return p; } },
    renders: 0,
    requestRender() { scene.renders += 1; },
  };
  const viewer = {
    scene,
    dataSources: { add: (d) => { c.footprintSrc = d; return d; } },
    camera: { flyTo() {} },
    useDefaultRenderLoop: true,
  };
  Object.assign(c, {
    Ion: { defaultAccessToken: null },
    UrlTemplateImageryProvider: function () {},
    ImageryLayer: function () {},
    Viewer: function () { return viewer; },
    PointPrimitiveCollection: function () {
      return { added: [], removeAll() { this.added = []; }, add(p) { this.added.push(p); } };
    },
    CustomDataSource: function () {
      return { entities: { removed: 0, added: [], removeAll() { this.removed += 1; this.added = []; }, add(e) { this.added.push(e); } } };
    },
    Terrain: { fromWorldTerrain: () => ({}) },
    Cartesian3: { fromDegrees() { return {}; }, fromDegreesArray() { return []; } },
    PolygonHierarchy: function () {},
    Color: {
      fromCssColorString() { return { withAlpha() { return {}; } }; },
      BLACK: { withAlpha() { return {}; } },
    },
    ClassificationType: { TERRAIN: 'terrain' },
    HeightReference: { CLAMP_TO_GROUND: 'ground' },
    viewer,
  });
  return c;
}

function fakeDocument() {
  const listeners = [];
  return {
    hidden: false,
    listeners,
    addEventListener(type, fn) { if (type === 'visibilitychange') listeners.push(fn); },
    createElement() { return fakeEl(); },
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
    await openGlobe(fakeEl(), {});
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
    await openGlobe(fakeEl(), {});
    await openGlobe(fakeEl(), {});
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

describe('describeGlobe: la frase que lee el lienzo 3D', () => {
  test('sin focos lo dice en claro', () => {
    assert.match(describeGlobe([]), /^Vista 3D: sin focos de calor a la vista/);
  });

  test('cuenta los focos y los de menos de 1 hora', () => {
    const s = describeGlobe([
      { lat: -33.4, lon: -70.6, age_h: 0.5 },
      { lat: -34.1, lon: -71.2, age_h: 2 },
      { lat: -35.0, lon: -72.0, age_h: 5 },
    ]);
    assert.match(s, /3 focos de calor/);
    assert.match(s, /1 de menos de 1 hora/);
  });

  test('un foco va en singular', () => {
    assert.match(describeGlobe([{ lat: -33, lon: -70, age_h: 4 }]), /1 foco de calor/);
  });

  test('ignora los puntos sin lat/lon finitos', () => {
    const s = describeGlobe([
      { lat: NaN, lon: -70, age_h: 0.4 },
      { lat: -34, lon: 'x', age_h: 0.4 },
      null,
      { lat: -34, lon: -71, age_h: 0.4 },
    ]);
    assert.match(s, /1 foco de calor, 1 de menos de 1 hora/);
  });

  test('dice si la zona con calor está marcada', () => {
    assert.match(describeGlobe([], { type: 'Polygon', coordinates: [] }), /La zona con calor está marcada/);
    assert.match(describeGlobe([], null), /Sin zona con calor marcada/);
  });

  test('dice si el terreno tiene relieve', () => {
    assert.match(describeGlobe([], null, true), /Con relieve/);
    assert.match(describeGlobe([], null, false), /Terreno plano/);
  });
});

// Cada prueba abre su propio globo con un import con query: el módulo guarda el viewer
// en estado interno y solo una instancia nueva corre el montaje del contenedor.
async function globoListo(tag) {
  const mod = await import(`../../web/js/globe.js?${tag}`);
  const prevWindow = globalThis.window;
  const prevDocument = globalThis.document;
  const c = fakeCesium();
  const container = fakeEl();
  globalThis.window = { ...globalThis.window, addEventListener() {}, Cesium: c };
  globalThis.document = fakeDocument();
  await mod.openGlobe(container, {});
  return {
    mod, c, container,
    restore() { globalThis.window = prevWindow; globalThis.document = prevDocument; },
  };
}

describe('updateGlobe: entrada blindada y vista que habla', () => {
  test('el contenedor queda con role, nombre, leyenda y texto para lector de pantalla', async () => {
    const { container, restore } = await globoListo('a11y-dom');
    try {
      assert.equal(container.attrs.role, 'region');
      assert.match(container.attrs['aria-label'], /^Vista 3D:/);
      const legend = container.children.find((n) => n.className === 'map-legend');
      assert.ok(legend, 'falta la leyenda de la vista 3D');
      assert.match(legend.innerHTML, /menos de 1 h/);
      assert.match(legend.innerHTML, /entre 1 y 3 h/);
      assert.match(legend.innerHTML, /más de 3 h/);
      const live = container.children.find((n) => n.className === 'sr-only');
      assert.ok(live, 'falta el resumen para lector de pantalla');
      assert.equal(live.attrs.role, 'status');
      assert.match(live.textContent, /^Vista 3D:/);
    } finally { restore(); }
  });

  test('llamado sin dots no lanza ni toca el visor', async () => {
    const { mod, c, container, restore } = await globoListo('a11y-sin-dots');
    try {
      const renders = c.viewer.scene.renders;
      assert.doesNotThrow(() => mod.updateGlobe(null));
      assert.doesNotThrow(() => mod.updateGlobe(null, undefined));
      assert.equal(c.viewer.scene.renders, renders);
      assert.equal(c.footprintSrc.entities.removed, 0);
      assert.match(container.attrs['aria-label'], /sin focos de calor a la vista/);
    } finally { restore(); }
  });

  test('pinta solo los puntos con coordenadas válidas', async () => {
    const { mod, c, container, restore } = await globoListo('a11y-invalidos');
    try {
      mod.updateGlobe(null, [
        { lat: NaN, lon: -70, age_h: 0.4 },
        { lat: -34, lon: null, age_h: 1 },
        { lat: -33.5, lon: -70.7, age_h: 0.4 },
        { lat: -35, lon: -71.5, age_h: 4 },
      ]);
      assert.equal(c.points.added.length, 2);
      assert.match(container.attrs['aria-label'], /2 focos de calor, 1 de menos de 1 hora/);
    } finally { restore(); }
  });

  test('con huella dibuja el polígono y lo anuncia', async () => {
    const { mod, c, container, restore } = await globoListo('a11y-huella');
    try {
      const footprint = { type: 'Polygon', coordinates: [[[-70, -33], [-69, -33], [-69, -34], [-70, -34], [-70, -33]]] };
      mod.updateGlobe(footprint, []);
      assert.equal(c.footprintSrc.entities.added.length, 1);
      assert.match(container.attrs['aria-label'], /La zona con calor está marcada/);
    } finally { restore(); }
  });
});
