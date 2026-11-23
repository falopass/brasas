/* Pruebas de web/js/globe.js (PERF-01/UX-15/UX-04) con node:test, sin navegador ni dependencias:
 * dobles de window.Cesium y de document para comprobar que el bucle de render se pausa
 * cuando la pestaña queda oculta, y de Element para la leyenda y el texto accesible. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { CESIUM_DEADLINE_MESSAGE, describeGlobe, openGlobe, setGlobeRendering, withDeadline } from '../../web/js/globe.js';

function fakeEl() {
  return {
    attrs: {},
    children: [],
    style: {},
    className: '',
    innerHTML: '',
    textContent: '',
    addEventListener() {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    append(...nodes) { this.children.push(...nodes); },
  };
}

function fakeCesium() {
  const c = {};
  const scene = {
    globe: { tilesLoaded: true },
    primitives: { add: (p) => { c.points = p; return p; } },
    renders: 0,
    requestRender() { scene.renders += 1; },
  };
  const viewer = {
    scene,
    dataSources: { add: (d) => { c.footprintSrc = d; return d; } },
    camera: { flyTo() {} },
    useDefaultRenderLoop: false,
    render() { scene.renders += 1; },
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

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

// La suite completa (tests/js/index.js) corre con un requestAnimationFrame de prueba
// que no dispara callbacks (motion.test.mjs); aquí se usa uno que sí, como en el navegador.
function conRafVivo() {
  const prev = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(performance.now()), 16);
  return () => { globalThis.requestAnimationFrame = prev; };
}

async function esperarRender(leer, base, ms = 1500) {
  const t0 = Date.now();
  while (leer() <= base && Date.now() - t0 < ms) await dormir(25);
}

describe('openGlobe con la pestaña oculta', () => {
  test('oculta no pinta; al volver pide un cuadro', async () => {
    const restaurar = conRafVivo();
    try {
      globalThis.window = { ...globalThis.window, addEventListener() {}, Cesium: cesium };
      globalThis.document = doc;
      await openGlobe(fakeEl(), {});
      cesium.viewer.scene.renders = 0;
      doc.hidden = true;
      doc.fire();
      await dormir(60);
      assert.equal(cesium.viewer.scene.renders, 0);
      doc.hidden = false;
      doc.fire();
      await esperarRender(() => cesium.viewer.scene.renders, 0);
      assert.equal(cesium.viewer.scene.renders, 1);
    } finally { restaurar(); }
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
  await mod.openGlobe(container, { camera: null });
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

  test('colapsa barridos repetidos del mismo sensor dejando el más reciente arriba y conserva sensores distintos', async () => {
    const { mod, c, container, restore } = await globoListo('dedup-3d');
    try {
      mod.updateGlobe(null, [
        { lat: -35.8388, lon: -71.5985, age_h: 5, sensor: 'ABI' },
        { lat: -35.8388, lon: -71.5985, age_h: 0.4, sensor: 'ABI' },
        { lat: -35.8388, lon: -71.5985, age_h: 2, sensor: 'ABI' },
        { lat: -35.8388, lon: -71.5985, age_h: 4, sensor: 'POLAR' },
      ]);
      assert.equal(c.points.added.length, 2);
      // El punto polar antiguo (4 h -> pixelSize 7) se añade antes que el ABI reciente (0.4 h -> pixelSize 9).
      assert.equal(c.points.added[0].pixelSize, 7);
      assert.equal(c.points.added[1].pixelSize, 9);
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

describe('setGlobeRendering: el globo no pinta con el lienzo oculto (MAPA-196)', () => {
  test('pausado no agenda cuadros; al reanudar pinta lo pedido', async () => {
    const restaurar = conRafVivo();
    try {
      const { mod, c, restore } = await globoListo('render-pausa');
      try {
        mod.setGlobeRendering(false);
        const renders = c.viewer.scene.renders;
        mod.updateGlobe(null, [{ lat: -33, lon: -70, age_h: 1 }]);
        await dormir(80);
        assert.equal(c.viewer.scene.renders, renders);
        mod.setGlobeRendering(true);
        await esperarRender(() => c.viewer.scene.renders, renders);
        assert.ok(c.viewer.scene.renders > renders);
      } finally { restore(); }
    } finally { restaurar(); }
  });

  test('pausado, el manejador de visibilidad de pestaña no reenciende los cuadros', async () => {
    const { mod, c, restore } = await globoListo('render-pausa-vis');
    try {
      mod.setGlobeRendering(false);
      const renders = c.viewer.scene.renders;
      globalThis.document.hidden = true;
      globalThis.document.fire();
      globalThis.document.hidden = false;
      globalThis.document.fire();
      await dormir(40);
      assert.equal(c.viewer.scene.renders, renders);
    } finally { restore(); }
  });

  test('sin visor todavía no hace nada', async () => {
    const mod = await import('../../web/js/globe.js?sin-visor');
    assert.doesNotThrow(() => mod.setGlobeRendering(false));
    assert.doesNotThrow(() => mod.setGlobeRendering(true));
  });
});
