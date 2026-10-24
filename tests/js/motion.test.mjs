/* Pruebas de web/js/motion.js con node:test, sin navegador. matchMedia, MutationObserver,
 * document, requestAnimationFrame, setTimeout y performance.now son falsos y se restauran
 * tras cada prueba; el reloj es manual, así que las ventanas de armEnter no esperan.
 * No cubre lo que depende de un DOM real: que MutationObserver dispare al cambiar hijos y
 * que las clases .enter y .run se animen en CSS. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, reduced, scanPass, watchView } from '../../web/js/motion.js';

const REDUCE = '(prefers-reduced-motion: reduce)';
const patches = [];
let clock = 1000;
let env;

function patch(obj, key, value) {
  patches.push([obj, key, Object.getOwnPropertyDescriptor(obj, key)]);
  Object.defineProperty(obj, key, { value, configurable: true, writable: true });
}

class FakeObserver {
  constructor(cb) { this.cb = cb; this.observed = []; FakeObserver.last = this; }
  observe(target, init) { this.observed.push({ target, init }); }
}

function fakeEl(textContent = '') {
  const cls = new Set();
  const vars = {};
  return {
    nodeType: 1, textContent, isConnected: true, cls, vars,
    classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c) },
    style: { setProperty: (k, v) => { vars[k] = v; } },
  };
}

function fakeView({ title = 'Mapa', children = [], counters = [] } = {}) {
  const heading = fakeEl(title);
  return { children: [heading, ...children], querySelector: () => heading, querySelectorAll: () => counters };
}

const fakeScan = (log) => ({
  classList: { add: (c) => log.push(`add ${c}`), remove: (c) => log.push(`remove ${c}`) },
  get offsetWidth() { log.push('reflow'); return 0; },
});

const render = () => FakeObserver.last.cb([]);
const runFrame = (t) => env.frames.splice(0).forEach((cb) => cb(t));

beforeEach(() => {
  clock += 10_000; // cierra la ventana que pudo dejar abierta la prueba anterior
  env = { reduce: false, queries: [], scanEl: null, frames: [], timers: [] };
  patch(performance, 'now', () => clock);
  patch(globalThis, 'matchMedia', (q) => { env.queries.push(q); return { matches: env.reduce }; });
  patch(globalThis, 'MutationObserver', FakeObserver);
  patch(globalThis, 'document', { getElementById: (id) => (id === 'scan' ? env.scanEl : null) });
  patch(globalThis, 'requestAnimationFrame', (cb) => env.frames.push(cb));
  patch(globalThis, 'setTimeout', (fn, ms) => env.timers.push({ fn, ms }));
});

afterEach(() => {
  for (const [obj, key, desc] of patches.splice(0).reverse()) {
    if (desc) Object.defineProperty(obj, key, desc); else delete obj[key];
  }
});

describe('reduced', () => {
  test('true si el sistema pide reducir movimiento, y consulta esa media query', () => {
    env.reduce = true;
    assert.equal(reduced(), true);
    assert.deepEqual(env.queries, [REDUCE]);
  });
  test('false si no lo pide', () => {
    assert.equal(reduced(), false);
  });
});

describe('armEnter y watchView', () => {
  test('sin ventana abierta, un render no anima partes ni cifras', () => {
    const counter = fakeEl('1.234');
    const view = fakeView({ children: [fakeEl('a')], counters: [counter] });
    watchView(view);
    render();
    assert.ok(view.children.every((c) => !c.cls.has('enter')));
    assert.equal(counter.textContent, '1.234');
    assert.equal(env.frames.length, 0);
  });
  test('acepta un contenedor simple sin lanzar, con la ventana abierta o cerrada', () => {
    const container = { children: [], querySelector: () => null, querySelectorAll: () => [] };
    assert.doesNotThrow(() => watchView(container));
    assert.doesNotThrow(render);
    armEnter();
    assert.doesNotThrow(render);
    assert.deepEqual(FakeObserver.last.observed, [{ target: container, init: { childList: true } }]);
  });
  test('con la ventana abierta, anima las partes en orden y limita --i a 9', () => {
    const view = fakeView({ children: Array.from({ length: 11 }, (_, i) => fakeEl(`p${i}`)) });
    watchView(view);
    armEnter();
    render();
    assert.deepEqual(view.children.map((c) => c.vars['--i']), [...Array(10).keys(), 9, 9].map(String));
    assert.ok(view.children.every((c) => c.cls.has('enter')));
  });
  test('la ventana se consume: el render siguiente ya no anima', () => {
    const view = fakeView();
    watchView(view);
    armEnter();
    render();
    view.children.push(fakeEl('nuevo'));
    render();
    assert.equal(view.children.at(-1).cls.has('enter'), false);
  });
  test('una ventana vencida no anima', () => {
    const view = fakeView({ children: [fakeEl('a')] });
    watchView(view);
    armEnter(1000);
    clock += 1001;
    render();
    assert.ok(view.children.every((c) => !c.cls.has('enter')));
  });
  test('un «Cargando…» no consume la ventana: anima el primer render con contenido', () => {
    const view = fakeView({ title: 'Cargando mapa…', children: [fakeEl('a')] });
    watchView(view);
    armEnter();
    render();
    assert.ok(view.children.every((c) => !c.cls.has('enter')));
    view.querySelector('.view-title').textContent = 'Mapa';
    render();
    assert.ok(view.children.every((c) => c.cls.has('enter')));
  });
  test('las cifras cuentan desde 0 hasta su valor original', () => {
    const counter = fakeEl('1.234');
    const view = fakeView({ counters: [counter] });
    watchView(view);
    armEnter();
    render();
    const t0 = clock;
    assert.equal(counter.textContent, '1.234');
    runFrame(t0);
    assert.equal(counter.textContent, '0');
    runFrame(t0 + 550);
    assert.equal(counter.textContent, '1.157');
    runFrame(t0 + 1100);
    assert.equal(counter.textContent, '1.234');
    assert.equal(env.frames.length, 0);
  });
  test('la clase enter se quita al cabo de 1,6 s', () => {
    const view = fakeView({ children: [fakeEl('a')] });
    watchView(view);
    armEnter();
    render();
    assert.deepEqual(env.timers.map((t) => t.ms), [1600]);
    env.timers[0].fn();
    assert.ok(view.children.every((c) => !c.cls.has('enter')));
  });
});

describe('reducir movimiento', () => {
  test('con la ventana abierta no anima nada y el contenido queda tal cual', () => {
    env.reduce = true;
    const counter = fakeEl('1.234');
    const view = fakeView({ children: [fakeEl('a')], counters: [counter] });
    watchView(view);
    armEnter();
    render();
    assert.ok(view.children.every((c) => !c.cls.has('enter') && Object.keys(c.vars).length === 0));
    assert.equal(counter.textContent, '1.234');
    assert.equal(env.frames.length + env.timers.length, 0);
  });
});

describe('scanPass', () => {
  test('sin #scan no hace nada', () => {
    assert.doesNotThrow(scanPass);
  });
  test('reinicia la pasada: quita run, fuerza reflow y la vuelve a poner', () => {
    const log = [];
    env.scanEl = fakeScan(log);
    scanPass();
    assert.deepEqual(log, ['remove run', 'reflow', 'add run']);
  });
  test('con reducir movimiento no toca el elemento', () => {
    env.reduce = true;
    const log = [];
    env.scanEl = fakeScan(log);
    scanPass();
    assert.deepEqual(log, []);
  });
});
