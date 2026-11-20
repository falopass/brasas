/* Pruebas de la recarga única por módulos mezclados (el fix del service worker en Safari):
 * la pestaña recarga una sola vez y solo ante errores de exports/binding de módulos —
 * nunca por un corte de red sin conexión, y sin gastar la marca en ese caso.
 * index.js junta todas las suites en un proceso, así que los globales se guardan y
 * se restauran para no pisar a las demás. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { debeRecargarVista, esErrorDeVersiones, yaRecargoSw, yaRecargoVista } from '../../web/js/util.js';

const errorVersiones = new TypeError("Importing binding name 'setGibs' is not found");
const errorOffline = new TypeError('fetch failed');

const sessionOriginal = globalThis.sessionStorage;
const windowOriginal = globalThis.window;
afterEach(() => {
  if (sessionOriginal === undefined) delete globalThis.sessionStorage; else globalThis.sessionStorage = sessionOriginal;
  if (windowOriginal === undefined) delete globalThis.window; else globalThis.window = windowOriginal;
});

describe('esErrorDeVersiones', () => {
  test('reconoce los errores de módulos mezclados de cada navegador', () => {
    assert.equal(esErrorDeVersiones(new Error("Mapa doesn't provide an export named 'setGibs'")), true); // Firefox
    assert.equal(esErrorDeVersiones(new Error("Importing binding name 'setGibs' is not found")), true); // Safari/Chrome
    assert.equal(esErrorDeVersiones(new Error('setGibs is not an exported member of map.js')), true);
    assert.equal(esErrorDeVersiones(new Error('failed to resolve module specifier ./mapa.js')), true);
  });

  test('un corte de red u otro error no es de versiones', () => {
    assert.equal(esErrorDeVersiones(errorOffline), false);
    assert.equal(esErrorDeVersiones(new Error('Load failed')), false);
    assert.equal(esErrorDeVersiones(null), false);
    assert.equal(esErrorDeVersiones(undefined), false);
  });
});

describe('yaRecargoVista', () => {
  beforeEach(() => {
    const datos = new Map();
    globalThis.sessionStorage = {
      getItem: (k) => (datos.has(k) ? datos.get(k) : null),
      setItem: (k, v) => datos.set(k, String(v)),
      removeItem: (k) => datos.delete(k),
    };
    globalThis.window = { name: '' };
  });

  test('la primera vez deja recargar y la segunda no', () => {
    assert.equal(yaRecargoVista(), false);
    assert.equal(yaRecargoVista(), true);
  });

  test('sin sessionStorage usa window.name con la misma regla', () => {
    globalThis.sessionStorage = {
      getItem() { throw new Error('bloqueado'); },
      setItem() { throw new Error('bloqueado'); },
    };
    assert.equal(yaRecargoVista(), false);
    assert.equal(window.name.includes('brasa:recarga-vista'), true);
    assert.equal(yaRecargoVista(), true);
  });

  test('si todo el almacenamiento falla, no recarga (evita el bucle)', () => {
    globalThis.sessionStorage = {
      getItem() { throw new Error('bloqueado'); },
      setItem() { throw new Error('bloqueado'); },
    };
    globalThis.window = {
      get name() { throw new Error('bloqueado'); },
      set name(_v) { throw new Error('bloqueado'); },
    };
    assert.equal(yaRecargoVista(), true);
  });
});

describe('debeRecargarVista', () => {
  test('recarga una sola vez ante un error de versiones', () => {
    let ya = false;
    const yaRecargo = () => { if (ya) return true; ya = true; return false; };
    assert.equal(debeRecargarVista(errorVersiones, yaRecargo), true);
    assert.equal(debeRecargarVista(errorVersiones, yaRecargo), false);
  });

  test('nunca recarga por un corte de red y no gasta la marca', () => {
    let consultada = 0;
    let ya = false;
    const yaRecargo = () => { consultada += 1; if (ya) return true; ya = true; return false; };
    assert.equal(debeRecargarVista(errorOffline, yaRecargo), false);
    assert.equal(consultada, 0); // el error offline ni siquiera mira la marca
    assert.equal(debeRecargarVista(errorVersiones, yaRecargo), true);
    assert.equal(debeRecargarVista(errorVersiones, yaRecargo), false);
  });
});

describe('yaRecargoSw', () => {
  beforeEach(() => {
    const datos = new Map();
    globalThis.sessionStorage = {
      getItem: (k) => (datos.has(k) ? datos.get(k) : null),
      setItem: (k, v) => datos.set(k, String(v)),
      removeItem: (k) => datos.delete(k),
    };
    globalThis.window = { name: '' };
  });

  test('recarga una sola vez por pestaña cuando cambia el service worker', () => {
    assert.equal(yaRecargoSw(), false);
    assert.equal(yaRecargoSw(), true);
  });

  test('si todo el almacenamiento falla, no recarga (evita el bucle)', () => {
    globalThis.sessionStorage = {
      getItem() { throw new Error('bloqueado'); },
      setItem() { throw new Error('bloqueado'); },
    };
    globalThis.window = {
      get name() { throw new Error('bloqueado'); },
      set name(_v) { throw new Error('bloqueado'); },
    };
    assert.equal(yaRecargoSw(), true);
  });
});
