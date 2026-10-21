/* A11Y-MOTION-01: con «reducir movimiento» motion.js no anima nada — ni la ventana
 * de entrada (armEnter) ni el conteo de cifras (countUp) — y un cambio de la
 * preferencia a mitad de la animación no deja clases `enter` colgadas.
 * Mismo estilo que motion.test.mjs: matchMedia, rAF y temporizadores simulados. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, countUp, watchView } from '../../web/js/motion.js';

let clock;
let rafQueue; // callbacks de requestAnimationFrame pendientes, en orden
let timers; // setTimeout capturados (nunca se ejecutan solos)
let observers; // MutationObserver registrados por watchView
let mediaListeners; // listeners 'change' de matchMedia registrados por choreograph
let reduceMatches; // lo que responde matchMedia

const GLOBALES = ['matchMedia', 'requestAnimationFrame', 'setTimeout', 'MutationObserver'];
const previos = {};

/* Los hooks viven dentro de este describe: index.js importa todas las suites en un
 * solo proceso y un hook de nivel raíz alcanzaría también a las pruebas ajenas. */
describe('motion con «reducir movimiento» (A11Y-MOTION-01)', () => {
  beforeEach(() => {
    clock = 0;
    rafQueue = [];
    timers = [];
    observers = [];
    mediaListeners = [];
    reduceMatches = false;
    for (const nombre of GLOBALES) previos[nombre] = globalThis[nombre];
    globalThis.matchMedia = (query) => ({
      matches: query === '(prefers-reduced-motion: reduce)' && reduceMatches,
      addEventListener: (tipo, cb) => { if (tipo === 'change') mediaListeners.push(cb); },
    });
    globalThis.requestAnimationFrame = (cb) => { rafQueue.push(cb); return rafQueue.length; };
    globalThis.setTimeout = (cb, ms) => { timers.push({ cb, ms }); return timers.length; };
    globalThis.MutationObserver = class {
      constructor(cb) { this.cb = cb; }
      observe(el) { observers.push({ cb: this.cb, el }); }
    };
    performance.now = () => clock;
  });

  afterEach(() => {
    for (const nombre of GLOBALES) {
      if (previos[nombre] === undefined) delete globalThis[nombre];
      else globalThis[nombre] = previos[nombre];
    }
    delete performance.now; // vuelve al método del prototipo
  });

  // Elemento del DOM de mentira: lo único que motion.js toca.
  function el(texto = '') {
    const clases = new Set();
    return {
      nodeType: 1,
      textContent: texto,
      isConnected: true,
      clases,
      style: { setProperty: () => {} },
      classList: {
        add: (c) => clases.add(c),
        remove: (c) => clases.delete(c),
        contains: (c) => clases.has(c),
      },
    };
  }

  const contenedor = (hijos = []) => ({
    children: hijos,
    querySelector: () => null,
    querySelectorAll: () => [],
  });

  const mutarVista = () => observers.at(-1).cb(); // dispara la mutación más reciente
  const frame = (now) => rafQueue.shift()(now); // corre el próximo cuadro con hora controlada
  const cambiarPreferencia = () => mediaListeners.forEach((cb) => cb());

  describe('countUp', () => {
    test('con reducción deja el texto intacto y no agenda requestAnimationFrame', () => {
      reduceMatches = true;
      const nodo = el('1.234 ha');
      countUp(nodo);
      assert.equal(nodo.textContent, '1.234 ha');
      assert.equal(rafQueue.length, 0);
      assert.equal(timers.length, 0);
    });

    test('sin reducción anima y al terminar vuelve al texto original', () => {
      const nodo = el('1.234 ha'); // duración: min(1100, 500 + 1234*4) = 1100
      countUp(nodo);
      assert.equal(rafQueue.length, 1);
      frame(550); // mitad de la animación
      assert.notEqual(nodo.textContent, '1.234 ha');
      frame(1100); // p = 1: termina
      assert.equal(nodo.textContent, '1.234 ha');
      assert.equal(rafQueue.length, 0);
    });
  });

  describe('armEnter', () => {
    test('con reducción no habilita la animación del siguiente render', () => {
      reduceMatches = true;
      armEnter(10000); // la ventana no se abre: enterUntil queda en 0
      reduceMatches = false; // aunque la preferencia vuelva, la ventana nunca quedó armada
      clock = 50; // con la ventana armada (hasta t=10000) esta mutación sí animaría
      const vista = contenedor([el(), el()]);
      watchView(vista);
      mutarVista();
      assert.ok(vista.children.every((ch) => !ch.clases.has('enter')));
      assert.equal(timers.length, 0);
    });
  });

  describe('cambio de preferencia a mitad de la animación', () => {
    test('las clases enter se limpian al momento, sin esperar al temporizador', () => {
      armEnter(100);
      const vista = contenedor([el('1'), el('2')]);
      watchView(vista);
      mutarVista();
      assert.ok(vista.children.every((ch) => ch.clases.has('enter')));

      reduceMatches = true;
      cambiarPreferencia();
      assert.ok(vista.children.every((ch) => !ch.clases.has('enter')));
    });
  });
});
