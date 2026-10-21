/* Pruebas de web/js/motion.js con node:test: matchMedia, requestAnimationFrame,
 * los temporizadores y el reloj se simulan; nada corre en tiempo real. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, countUp, reduced, watchView } from '../../web/js/motion.js';

let clock;
let rafQueue; // callbacks de requestAnimationFrame pendientes, en orden
let timers; // setTimeout capturados (nunca se ejecutan solos)
let observers; // MutationObserver registrados por watchView
let reduceMatches; // lo que responde matchMedia

const GLOBALES = ['matchMedia', 'requestAnimationFrame', 'setTimeout', 'MutationObserver'];
const previos = {};

/* Los hooks viven dentro de este describe: index.js importa todas las suites en un
 * solo proceso y un hook de nivel raíz alcanzaría también a las pruebas ajenas. */
describe('motion (entorno simulado)', () => {
  beforeEach(() => {
    clock = 0;
    rafQueue = [];
    timers = [];
    observers = [];
    reduceMatches = false;
    for (const nombre of GLOBALES) previos[nombre] = globalThis[nombre];
    globalThis.matchMedia = (query) => ({ matches: query === '(prefers-reduced-motion: reduce)' && reduceMatches });
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

  describe('reduced', () => {
    test('responde al medio prefers-reduced-motion', () => {
      reduceMatches = true;
      assert.equal(reduced(), true);
      reduceMatches = false;
      assert.equal(reduced(), false);
    });
  });

  describe('ventana de entrada (armEnter + watchView)', () => {
    test('abierta anima el próximo render; vencida ya no', () => {
      armEnter(100); // ventana hasta clock = 100
      const abierta = contenedor([el(), el()]);
      watchView(abierta);
      mutarVista();
      assert.ok(abierta.children.every((ch) => ch.clases.has('enter')));

      clock = 50;
      armEnter(100); // nueva ventana hasta 150
      clock = 200;
      const cerrada = contenedor([el()]);
      watchView(cerrada);
      mutarVista();
      assert.ok(!cerrada.children[0].clases.has('enter'));
    });

    test('con reducir movimiento no agrega la clase enter aunque la ventana esté abierta', () => {
      reduceMatches = true;
      armEnter(10000);
      const vista = contenedor([el(), el()]);
      watchView(vista);
      mutarVista();
      assert.ok(vista.children.every((ch) => !ch.clases.has('enter')));
      assert.equal(timers.length, 0);
    });
  });

  describe('countUp', () => {
    test('texto no numérico o menor que 2 queda intacto y no agenda nada', () => {
      for (const texto of ['hola', '—', '1 km', '0 ha', '1,5 °C']) {
        const nodo = el(texto);
        countUp(nodo);
        assert.equal(nodo.textContent, texto);
      }
      assert.equal(rafQueue.length, 0);
    });

    test('con «1.234 ha» el valor intermedio usa punto de miles y al terminar vuelve al original', () => {
      const nodo = el('1.234 ha'); // duración: min(1100, 500 + 1234*4) = 1100
      countUp(nodo); // t0 = 0
      assert.equal(rafQueue.length, 1);
      frame(550); // mitad de la animación
      assert.match(nodo.textContent, /^1\.\d{3} ha$/, `intermedio: ${nodo.textContent}`);
      assert.notEqual(nodo.textContent, '1.234 ha');
      frame(1100); // p = 1: termina
      assert.equal(nodo.textContent, '1.234 ha');
      assert.equal(rafQueue.length, 0);
    });

    test('los decimales se muestran con coma (es-CL) y el texto vuelve al final', () => {
      const nodo = el('12,5 km'); // duración: min(1100, 500 + 12,5*4) = 550
      countUp(nodo);
      frame(275);
      assert.match(nodo.textContent, /^\d{1,2},\d km$/, `intermedio: ${nodo.textContent}`);
      frame(550);
      assert.equal(nodo.textContent, '12,5 km');
    });
  });
});
