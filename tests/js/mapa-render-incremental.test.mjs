/* PERF-10: render() en web/js/views/mapa.js actualiza solo los bloques dinámicos sin
 * destruir el cascarón (#map-search, #map-search-results, form#explore), de modo que el
 * buscador conserva su instancia DOM, foco, texto escrito y listeners entre repintados. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} };
globalThis.document ??= {
  activeElement: null,
  querySelector: () => null,
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener() {},
  dispatchEvent: () => true,
};

const { store } = await import('../../web/js/store.js');
const { render } = await import('../../web/js/views/mapa.js');

const STORE_KEYS = [
  'observations', 'obsHours', 'obsFilter', 'status', 'config',
  'official', 'places', 'obsError', 'statusError', 'dataAsOf',
];

function crearNodo(id = '', extra = {}) {
  const attrs = {};
  const listeners = {};
  return {
    id,
    innerHTML: '',
    textContent: '',
    value: '',
    checked: false,
    dataset: {},
    style: { setProperty() {} },
    listeners,
    attrs,
    addEventListener(ev, fn) { (listeners[ev] ??= []).push(fn); },
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return attrs[k] ?? null; },
    toggleAttribute(k, force) { if (force) attrs[k] = ''; else delete attrs[k]; },
    querySelector: () => null,
    querySelectorAll: () => [],
    scrollIntoView() {},
    ...extra,
  };
}

function crearContenedor() {
  let htmlStr = '';
  let nodos = {};
  let hoursBtns = [];
  let distBtns = [];
  let sensorBtns = [];
  const c = {
    dataset: {},
    innerHtmlWrites: 0,
    get innerHTML() { return htmlStr; },
    set innerHTML(v) {
      c.innerHtmlWrites += 1;
      htmlStr = String(v);
      nodos = {
        '#map-lectura': crearNodo('map-lectura'),
        '#map-search': crearNodo('map-search'),
        '#map-search-results': crearNodo('map-search-results'),
        '#goes-gap': crearNodo('goes-gap'),
        '#goes-next': crearNodo('goes-next'),
        '#trunc-note': crearNodo('trunc-note'),
        '#map-carga-err': crearNodo('map-carga-err'),
        '#f-reliable': crearNodo('f-reliable'),
        '#report': crearNodo('report'),
        '#map-listas': crearNodo('map-listas'),
        '#fuentes': crearNodo('fuentes'),
        '#sources-block': crearNodo('sources-block'),
        '#explore': crearNodo('explore'),
        '#ex-zone': crearNodo('ex-zone'),
        '#ex-date': crearNodo('ex-date', { value: '2024-02-02' }),
        '#ex-days': crearNodo('ex-days', { value: '3' }),
        '#ex-note': crearNodo('ex-note'),
      };
      hoursBtns = [6, 24, 48, 168].map((h) => crearNodo('', { dataset: { hours: String(h) } }));
      distBtns = [0, 10, 25, 50, 100].map((d) => crearNodo('', { dataset: { dist: String(d) } }));
      sensorBtns = ['ABI', 'VIIRS', 'MODIS', 'LANDSAT'].map((s) => crearNodo('', { dataset: { sensor: s } }));
    },
    querySelector(sel) { return nodos[sel] || null; },
    querySelectorAll(sel) {
      if (sel === '[data-hours]') return hoursBtns;
      if (sel === '[data-dist]') return distBtns;
      if (sel === '[data-sensor]') return sensorBtns;
      return [];
    },
  };
  return c;
}

const foco = (id, region = 'Maule') => ({
  id,
  comuna_code: 7101,
  region,
  lat: -35.42,
  lon: -71.65,
  sensor: 'VIIRS',
  confidence: 'alta',
  observed_at: new Date().toISOString(),
});

describe('render incremental de web/js/views/mapa.js (PERF-10)', () => {
  let prevDoc;
  let prevMatchMedia;
  let prevStore;

  beforeEach(() => {
    prevDoc = globalThis.document;
    prevMatchMedia = globalThis.matchMedia;
    prevStore = Object.fromEntries(STORE_KEYS.map((k) => [k, store.get(k)]));
    globalThis.document = {
      activeElement: null,
      querySelector: () => null,
      querySelectorAll: () => [],
      getElementById: () => null,
      addEventListener() {},
      dispatchEvent: () => true,
    };
    globalThis.matchMedia = () => ({ matches: false });
    store.set('places', []);
    store.set('obsHours', 24);
    store.set('obsFilter', { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true, LANDSAT: true } });
    store.set('config', { zones: {} });
    store.set('official', null);
    store.set('status', { last_ingest_at: new Date().toISOString(), runs: [], goes_sweeps: [] });
    store.set('obsError', null);
    store.set('statusError', null);
    store.set('dataAsOf', new Date().toISOString());
    store.set('observations', [foco('f1', 'Maule')]);
  });

  afterEach(() => {
    for (const k of STORE_KEYS) store.set(k, prevStore[k]);
    globalThis.document = prevDoc;
    if (prevMatchMedia === undefined) delete globalThis.matchMedia;
    else globalThis.matchMedia = prevMatchMedia;
  });

  test('conserva la instancia DOM, el foco y el valor de #map-search entre dos renders con datos distintos', async () => {
    const container = crearContenedor();
    await render(container, {});

    assert.equal(container.innerHtmlWrites, 1, 'el primer render monta el cascarón una vez');
    assert.equal(container.dataset.mapaMontado, '1');
    const searchAntes = container.querySelector('#map-search');
    const resultsAntes = container.querySelector('#map-search-results');
    const exploreAntes = container.querySelector('#explore');
    const lecturaAntes = container.querySelector('#map-lectura').innerHTML;
    assert.match(lecturaAntes, />1</);
    assert.match(container.querySelector('#map-listas').innerHTML, /Maule/);

    // El usuario enfoca el buscador y escribe mientras llegan datos nuevos.
    searchAntes.value = 'Talca';
    globalThis.document.activeElement = searchAntes;
    const listenersAntes = searchAntes.listeners.input.length;

    store.set('observations', [foco('f1', 'Biobío'), foco('f2', 'Biobío'), foco('f3', 'Ñuble')]);
    await render(container, {});

    assert.equal(container.innerHtmlWrites, 1, 'el segundo render no debe sobrescribir container.innerHTML');
    assert.equal(container.querySelector('#map-search'), searchAntes, '#map-search debe conservar la misma instancia DOM');
    assert.equal(container.querySelector('#map-search-results'), resultsAntes, '#map-search-results debe conservar la misma instancia DOM');
    assert.equal(container.querySelector('#explore'), exploreAntes, 'form#explore debe conservar la misma instancia DOM');
    assert.equal(searchAntes.value, 'Talca', 'el texto escrito en #map-search no se pierde');
    assert.equal(globalThis.document.activeElement, searchAntes, 'el foco en #map-search no se pierde');
    assert.equal(searchAntes.listeners.input.length, listenersAntes, 'los listeners del buscador se registran una sola vez');
    assert.match(container.querySelector('#map-lectura').innerHTML, />3</, 'el contador principal se actualiza');
    assert.match(container.querySelector('#map-listas').innerHTML, /Biobío/, 'las listas dinámicas se actualizan');
  });

  test('sincroniza #ex-zone cuando llegan las zonas, también con el foco activo (REND-02)', async () => {
    const container = crearContenedor();
    await render(container, {});

    const exZone = container.querySelector('#ex-zone');
    assert.equal(exZone.innerHTML, '');

    // La configuración puede llegar con el selector enfocado: las opciones se reconcilian en
    // el mismo nodo (no se reemplaza el select, así el foco no se pierde).
    globalThis.document.activeElement = exZone;
    store.set('config', { zones: { maule: { label: 'Maule', bbox: [-72, -36, -70, -34] } } });
    await render(container, {});
    assert.equal(container.querySelector('#ex-zone'), exZone);
    assert.match(exZone.innerHTML, /value="maule"/);
    assert.equal(exZone.dataset.zonesKey, 'maule');
  });

  test('si el contenedor pierde la marca de cascarón montado, lo vuelve a montar limpio', async () => {
    const container = crearContenedor();
    await render(container, {});
    assert.equal(container.innerHtmlWrites, 1);

    delete container.dataset.mapaMontado;
    await render(container, {});
    assert.equal(container.innerHtmlWrites, 2, 'sin marca mapaMontado el cascarón se monta de nuevo');
  });
});
