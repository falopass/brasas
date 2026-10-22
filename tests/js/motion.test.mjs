/* Pruebas de web/js/motion.js con node:test: matchMedia, requestAnimationFrame,
 * los temporizadores y el reloj se simulan; nada corre en tiempo real. Lo visual
 * (la transición CSS de .enter, el barrido norte→sur de #scan) necesita navegador. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, countUp, reduced, scanPass, watchView } from '../../web/js/motion.js';

let clock;
let rafQueue; // callbacks de requestAnimationFrame pendientes, en orden
let timers; // setTimeout capturados (nunca se ejecutan solos)
let observers; // MutationObserver registrados por watchView
let reduceMatches; // lo que responde matchMedia
let lastQuery; // la última media query consultada

const GLOBALES = ['matchMedia', 'requestAnimationFrame', 'setTimeout', 'MutationObserver', 'document'];
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
    lastQuery = '';
    for (const nombre of GLOBALES) previos[nombre] = globalThis[nombre];
    globalThis.matchMedia = (query) => {
      lastQuery = query;
      return { matches: query === '(prefers-reduced-motion: reduce)' && reduceMatches };
    };
    globalThis.requestAnimationFrame = (cb) => { rafQueue.push(cb); return rafQueue.length; };
    globalThis.setTimeout = (cb, ms) => { timers.push({ cb, ms }); return timers.length; };
    globalThis.MutationObserver = class {
      constructor(cb) { this.cb = cb; }
      observe(el, opts) { observers.push({ cb: this.cb, el, opts }); }
    };
    globalThis.document = { getElementById: () => null };
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
    const props = {};
    return {
      nodeType: 1,
      textContent: texto,
      isConnected: true,
      clases,
      props,
      style: { setProperty: (k, v) => { props[k] = v; } },
      classList: {
        add: (c) => clases.add(c),
        remove: (c) => clases.delete(c),
        contains: (c) => clases.has(c),
      },
    };
  }

  const contenedor = (hijos = [], { title = null, counted = [] } = {}) => ({
    title,
    children: hijos,
    querySelector(sel) { return sel === '.view-title' && this.title !== null ? { textContent: this.title } : null; },
    querySelectorAll: () => counted,
  });

  const mutarVista = () => observers.at(-1).cb(); // dispara la mutación más reciente
  const frame = (now) => rafQueue.shift()(now); // corre el próximo cuadro con hora controlada

  describe('reduced', () => {
    test('responde al medio prefers-reduced-motion', () => {
      reduceMatches = true;
      assert.equal(reduced(), true);
      assert.equal(lastQuery, '(prefers-reduced-motion: reduce)');
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

    test('ordena las partes en orden de lectura y corta el índice en 9', () => {
      const partes = Array.from({ length: 11 }, () => el());
      const texto = { nodeType: 3, textContent: 'hola' };
      const vista = contenedor([texto, ...partes]);
      watchView(vista);
      armEnter(1000);
      mutarVista();
      assert.equal(texto.style, undefined, 'un nodo de texto no se toca');
      assert.equal(partes[0].props['--i'], '0', 'el nodo de texto no ocupa un índice');
      assert.equal(partes[10].props['--i'], '9');
      assert.ok(partes.every((p) => p.clases.has('enter')));
    });

    test('la ventana se consume con la primera animación (armEnter sin argumentos)', () => {
      const primera = el();
      const vista = contenedor([primera]);
      watchView(vista);
      armEnter();
      mutarVista();
      assert.ok(primera.clases.has('enter'));

      clock = 5000; // la ventana ya venció: se gastó con la animación anterior
      const segunda = el();
      vista.children = [segunda];
      mutarVista();
      assert.ok(!segunda.clases.has('enter'), 'la ventana dura una sola animación');
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

  describe('watchView', () => {
    test('observa el contenedor y no explota con un contenedor mínimo', () => {
      const vista = contenedor();
      assert.doesNotThrow(() => watchView(vista));
      const observado = observers.at(-1);
      assert.equal(observado.el, vista);
      assert.deepEqual(observado.opts, { childList: true });
      armEnter(-1);
      assert.doesNotThrow(mutarVista);
    });

    test('con el título «Cargando» no anima ni gasta la ventana', () => {
      const parte = el();
      const vista = contenedor([parte], { title: 'Cargando incendios…' });
      watchView(vista);
      armEnter(4000);
      mutarVista();
      assert.ok(!parte.clases.has('enter'));
      vista.title = 'Incendios cerca';
      mutarVista();
      assert.ok(parte.clases.has('enter'), 'la ventana sigue abierta para el render real');
    });

    test('las cifras con número se animan al entrar y vuelven a su texto', () => {
      const kpi = el('12.345 ha');
      kpi.isConnected = false; // el tick se corta y restaura el texto
      const vista = contenedor([el()], { counted: [kpi] });
      watchView(vista);
      armEnter(4000);
      mutarVista();
      assert.equal(rafQueue.length, 1, 'la cifra arranca su conteo');
      frame(0);
      assert.equal(kpi.textContent, '12.345 ha');
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

  describe('scanPass', () => {
    test('sin #scan no explota', () => {
      globalThis.document = { getElementById: () => null };
      assert.doesNotThrow(() => scanPass());
    });

    test('reinicia el barrido: quita .run y lo vuelve a poner', () => {
      const llamadas = [];
      const clases = new Set();
      const scan = {
        offsetWidth: 320,
        classList: {
          add: (c) => { llamadas.push(`add:${c}`); clases.add(c); },
          remove: (c) => { llamadas.push(`remove:${c}`); clases.delete(c); },
          contains: (c) => clases.has(c),
        },
      };
      globalThis.document = { getElementById: (id) => (id === 'scan' ? scan : null) };
      scanPass();
      assert.deepEqual(llamadas, ['remove:run', 'add:run']);
      assert.ok(scan.classList.contains('run'));
    });

    test('con «reducir movimiento» no toca el elemento', () => {
      reduceMatches = true;
      const tocados = [];
      const scan = { offsetWidth: 320, classList: { add: (c) => tocados.push(c), remove: (c) => tocados.push(c) } };
      globalThis.document = { getElementById: () => scan };
      scanPass();
      assert.deepEqual(tocados, []);
    });
  });
});
