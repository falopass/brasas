/* Pruebas de web/sw.js (MOV-03): con la red caída, ninguna navegación del mismo
 * origen debe terminar en la página de error del navegador — se devuelve la copia
 * guardada de esa URL, su gemela bajo /web/, la versión liviana o la portada.
 * El script se ejecuta tal cual con `self`, `caches`, `fetch` y `Request` simulados;
 * index.js junta todas las suites en un proceso, así que los globales se vuelven
 * a montar antes de cada prueba por si otra los pisa. */
import { describe, test, before, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

const ORIGEN = 'https://brasa.test';
const listeners = {};

// Caché de mentira con el contrato mínimo que usa sw.js: put/match con ignoreSearch.
class CacheFalso {
  constructor() { this.mapa = new Map(); }
  async add(request) {
    const res = await fetch(request);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await this.put(request, res);
  }
  async put(request, response) {
    this.mapa.set(typeof request === 'string' ? request : request.url, response);
  }
  async match(request, { ignoreSearch = false } = {}) {
    let url = new URL(typeof request === 'string' ? request : request.url, ORIGEN).href;
    if (ignoreSearch) url = url.split('?')[0];
    const hit = this.mapa.get(url)
      || (ignoreSearch && [...this.mapa.entries()].find(([k]) => k.split('?')[0] === url)?.[1]);
    return hit ? hit.clone() : undefined;
  }
  async keys() { return [...this.mapa.keys()]; }
  async delete(request) { return this.mapa.delete(typeof request === 'string' ? request : request.url); }
}

const almacenes = new Map();
// La red: `redCaida` la tira; en línea responde un cuerpo que nombra la ruta pedida.
let redCaida = false;
const RequestReal = globalThis.Request;

function montar() {
  globalThis.caches = {
    open: async (nombre) => {
      if (!almacenes.has(nombre)) almacenes.set(nombre, new CacheFalso());
      return almacenes.get(nombre);
    },
    keys: async () => [...almacenes.keys()],
    delete: async (nombre) => almacenes.delete(nombre),
    match: async (request, opciones) => {
      for (const cache of almacenes.values()) {
        const hit = await cache.match(request, opciones);
        if (hit) return hit;
      }
      return undefined;
    },
  };
  globalThis.fetch = async (request) => {
    if (redCaida) throw new TypeError('fetch failed');
    const { pathname } = new URL(typeof request === 'string' ? request : request.url);
    return new Response(`pagina:${pathname}`, { status: 200, headers: { 'Content-Type': 'text/html' } });
  };
  // sw.js construye Request con rutas relativas (el ámbito del SW como base).
  globalThis.Request = class extends RequestReal {
    constructor(url, init) { super(new URL(url, ORIGEN).href, init); }
  };
  globalThis.self = {
    location: { origin: ORIGEN },
    addEventListener: (tipo, fn) => { listeners[tipo] = fn; },
    skipWaiting: () => Promise.resolve(),
    clients: { claim: () => Promise.resolve() },
    navigator: {},
    registration: {},
  };
}

montar();
await import('../../web/sw.js');

async function instalar() {
  let espera;
  listeners.install({ waitUntil: (p) => { espera = p; } });
  await espera;
}

function navegar(pathname, { mode = 'navigate', method = 'GET' } = {}) {
  const request = { url: new URL(pathname, ORIGEN).href, method, mode };
  let respuesta;
  listeners.fetch({ request, respondWith: (p) => { respuesta = p; }, waitUntil: () => {} });
  return respuesta;
}

describe('respaldo de navegación sin conexión (MOV-03)', () => {
  // Los globales los pisan otras suites (index.js junta todo en un proceso):
  // se vuelven a montar antes del precache y antes de cada prueba.
  before(() => { montar(); return instalar(); });
  beforeEach(montar);

  test('el precache guarda /focos.html, la URL limpia que enlaza el noscript', async () => {
    const copia = await caches.match(new Request(`${ORIGEN}/focos.html`));
    assert.ok(copia, 'falta /focos.html en el precache');
    assert.equal(await copia.text(), 'pagina:/focos.html');
  });

  test('sin conexión, /focos.html devuelve su copia y no el error del navegador', async () => {
    redCaida = true;
    const res = await navegar('/focos.html');
    assert.equal(res.status, 200);
    assert.equal(await res.text(), 'pagina:/focos.html');
    redCaida = false;
  });

  test('sin conexión, /lista.html cae en su gemela /web/lista.html', async () => {
    redCaida = true;
    const res = await navegar('/lista.html?imprimir=1');
    assert.equal(res.status, 200);
    assert.equal(await res.text(), 'pagina:/web/lista.html');
    redCaida = false;
  });

  test('una navegación cualquiera sin copia cae en la versión liviana', async () => {
    redCaida = true;
    const res = await navegar('/una-pagina-que-no-existe');
    assert.equal(res.status, 200);
    assert.equal(await res.text(), 'pagina:/web/lite.html');
    redCaida = false;
  });

  test('con red, la navegación responde del servidor y deja su copia guardada', async () => {
    const res = await navegar('/admin');
    assert.equal(await res.text(), 'pagina:/admin');
    redCaida = true;
    const resOffline = await navegar('/admin');
    assert.equal(await resOffline.text(), 'pagina:/admin');
    redCaida = false;
  });
});
