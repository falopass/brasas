/* Pruebas de web/js/motion.js con node:test, sin navegador: matchMedia, MutationObserver,
 * document y setTimeout se simulan con objetos mínimos (mismo enfoque que zona.test.mjs).
 * Sin DOM real quedan fuera: el disparo auténtico de un MutationObserver y countUp, que
 * necesita requestAnimationFrame y un texto que evoluciona; el contenedor falso devuelve
 * una lista vacía de cifras para no llegar a él. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, reduced, scanPass, watchView } from '../../web/js/motion.js';

// matchMedia simulado: reduced() solo lee .matches de la consulta de movimiento reducido.
let mediaMatches = false;
globalThis.matchMedia = (query) => ({ matches: mediaMatches, media: query });

// MutationObserver simulado: watchView registra el callback y observa el contenedor; las
// pruebas invocan el callback a mano para ver qué haría ante un render de la vista.
const observers = [];
globalThis.MutationObserver = class {
  constructor(cb) { this.cb = cb; observers.push(this); }
  observe(target, options) { this.target = target; this.options = options; }
};

// document simulado: scanPass busca #scan.
let scanEl = null;
globalThis.document = { getElementById: (id) => (id === 'scan' ? scanEl : null) };

// Elemento falso: classList registra las llamadas y style guarda lo que setProperty escribe.
const fakeEl = (log = [], nodeType = 1) => ({
  nodeType,
  textContent: '',
  offsetWidth: 0,
  style: { setProperty(k, v) { this[k] = v; } },
  classList: {
    add: (c) => log.push(`add:${c}`),
    remove: (c) => log.push(`remove:${c}`),
  },
});

const fakeContainer = (children, viewTitle = undefined) => ({
  children,
  querySelector: () => viewTitle,
  querySelectorAll: () => [],
});

/* Invoca el callback del último observer con setTimeout simulado (la limpieza real sería a
 * 1600 ms) y devuelve los temporales pendientes, para que ninguna prueba deje un timer vivo. */
function fireCallback() {
  const realSetTimeout = globalThis.setTimeout;
  const pending = [];
  globalThis.setTimeout = (fn, ms) => { pending.push({ fn, ms }); return pending.length; };
  try { observers.at(-1).cb(); } finally { globalThis.setTimeout = realSetTimeout; }
  return pending;
}

describe('reduced', () => {
  test('true cuando matchMedia reporta la preferencia', () => {
    mediaMatches = true;
    assert.equal(reduced(), true);
  });
  test('false cuando no está activada', () => {
    mediaMatches = false;
    assert.equal(reduced(), false);
  });
});

describe('watchView', () => {
  test('observa childList del contenedor y deja el callback listo', () => {
    const container = fakeContainer([]);
    watchView(container);
    const obs = observers.at(-1);
    assert.equal(obs.target, container);
    assert.deepEqual(obs.options, { childList: true });
    assert.equal(typeof obs.cb, 'function');
  });

  test('sin ventana armada el callback no anima nada (enterUntil parte en 0)', () => {
    mediaMatches = false;
    const log = [];
    watchView(fakeContainer([fakeEl(log), fakeEl(log)]));
    assert.deepEqual(fireCallback(), []);
    assert.deepEqual(log, []);
  });

  test('con reducir movimiento el callback no anima nada', () => {
    mediaMatches = true;
    const log = [];
    watchView(fakeContainer([fakeEl(log), fakeEl(log)]));
    assert.deepEqual(fireCallback(), []);
    assert.deepEqual(log, []);
    mediaMatches = false;
  });

  test('mientras la vista carga («Cargando…») no anima, con la ventana ya armada', () => {
    mediaMatches = false;
    const log = [];
    watchView(fakeContainer([fakeEl(log)], { textContent: 'Cargando radar…' }));
    armEnter(1000); // ventana abierta: la única razón para no animar es la carga
    assert.deepEqual(fireCallback(), []);
    assert.deepEqual(log, []);
  });

  test('armEnter abre la ventana: el próximo render se anima en orden y una sola vez', () => {
    mediaMatches = false;
    const log = [];
    const children = [fakeEl(log), fakeEl(log, 3), fakeEl(log)]; // el del medio es un nodo de texto
    watchView(fakeContainer(children));
    armEnter(1000);
    const pending = fireCallback();
    assert.equal(pending.length, 1);
    assert.equal(pending[0].ms, 1600);
    assert.deepEqual(log, ['add:enter', 'add:enter']); // el nodo de texto se salta
    assert.equal(children[0].style['--i'], '0');
    assert.equal(children[2].style['--i'], '1');
    pending[0].fn(); // la limpieza posterior quita la clase: la entrada corre una sola vez
    assert.deepEqual(log, ['add:enter', 'add:enter', 'remove:enter', 'remove:enter']);
  });

  test('con muchas partes el índice de entrada se corta en 9', () => {
    mediaMatches = false;
    const log = [];
    const children = Array.from({ length: 12 }, () => fakeEl(log));
    watchView(fakeContainer(children));
    armEnter(1000);
    fireCallback();
    assert.equal(children[0].style['--i'], '0');
    assert.equal(children[9].style['--i'], '9');
    assert.equal(children[11].style['--i'], '9');
  });
});

describe('scanPass', () => {
  test('sin #scan en el documento no explota', () => {
    scanEl = null;
    assert.doesNotThrow(() => scanPass());
  });

  test('reinicia la pasada: quita run y vuelve a ponerla', () => {
    mediaMatches = false;
    const log = [];
    scanEl = fakeEl(log);
    scanPass();
    assert.deepEqual(log, ['remove:run', 'add:run']);
  });

  test('con reducir movimiento no toca #scan', () => {
    mediaMatches = true;
    const log = [];
    scanEl = fakeEl(log);
    scanPass();
    assert.deepEqual(log, []);
    mediaMatches = false;
  });
});
