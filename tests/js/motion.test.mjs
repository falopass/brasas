/* Pruebas de web/js/motion.js con node:test, sin DOM real: matchMedia, MutationObserver
 * y document se simulan con objetos mínimos. Lo visual no se prueba aquí (la transición
 * CSS de .enter, el barrido norte→sur de #scan o el reflujo que fuerza offsetWidth):
 * para eso hace falta un navegador. Se prueba la lógica: cuándo se anima y cuándo no. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

let matches = false;
let lastQuery = '';
globalThis.matchMedia = (q) => { lastQuery = q; return { matches, media: q }; };

const observers = [];
globalThis.MutationObserver = class {
  constructor(cb) { this.cb = cb; observers.push(this); }
  observe(target, opts) { this.target = target; this.opts = opts; }
};
const fire = () => observers.at(-1).cb();

globalThis.document = { getElementById: () => null };

const { armEnter, reduced, scanPass, watchView } = await import('../../web/js/motion.js');

function fakeEl(text = '') {
  const classes = new Set();
  return {
    nodeType: 1,
    textContent: text,
    children: [],
    style: { setProperty(k, v) { this[k] = v; } },
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
  };
}

function fakeContainer({ parts = [], title = null, counted = [] } = {}) {
  return {
    title,
    children: parts,
    querySelector(sel) { return sel === '.view-title' && this.title !== null ? { textContent: this.title } : null; },
    querySelectorAll() { return counted; },
  };
}

describe('reduced', () => {
  test('true cuando el sistema pide menos movimiento', () => {
    matches = true;
    assert.equal(reduced(), true);
    assert.equal(lastQuery, '(prefers-reduced-motion: reduce)');
  });

  test('false cuando no lo pide', () => {
    matches = false;
    assert.equal(reduced(), false);
  });
});

describe('armEnter', () => {
  test('abre la ventana: el próximo render anima las partes en orden de lectura', () => {
    matches = false;
    const parts = [fakeEl(), fakeEl(), fakeEl()];
    watchView(fakeContainer({ parts }));
    armEnter(1000);
    fire();
    parts.forEach((p, i) => {
      assert.ok(p.classList.contains('enter'), `parte ${i}`);
      assert.equal(p.style['--i'], String(i));
    });
  });

  test('ignora los nodos que no son elementos y corta el índice en 9', () => {
    matches = false;
    const text = { nodeType: 3, textContent: 'hola' };
    const els = Array.from({ length: 11 }, () => fakeEl());
    watchView(fakeContainer({ parts: [text, ...els] }));
    armEnter(1000);
    fire();
    assert.equal(text.style, undefined, 'un nodo de texto no se toca');
    assert.equal(els[0].style['--i'], '0', 'el nodo de texto no ocupa un índice');
    assert.equal(els[10].style['--i'], '9');
  });

  test('sin ventana abierta no anima', () => {
    matches = false;
    const a = fakeEl();
    watchView(fakeContainer({ parts: [a] }));
    armEnter(-1);
    fire();
    assert.ok(!a.classList.contains('enter'));
  });

  test('la ventana se consume con la primera animación (armEnter sin argumentos)', () => {
    matches = false;
    const first = fakeEl();
    const c = fakeContainer({ parts: [first] });
    watchView(c);
    armEnter();
    fire();
    assert.ok(first.classList.contains('enter'));
    const second = fakeEl();
    c.children = [second];
    fire();
    assert.ok(!second.classList.contains('enter'), 'la ventana dura una sola animación');
  });
});

describe('watchView', () => {
  test('observa el contenedor y no explota con un contenedor mínimo', () => {
    const c = fakeContainer();
    assert.doesNotThrow(() => watchView(c));
    const obs = observers.at(-1);
    assert.equal(obs.target, c);
    assert.deepEqual(obs.opts, { childList: true });
    armEnter(-1);
    assert.doesNotThrow(fire);
  });

  test('con «reducir movimiento» no anima aunque la ventana esté abierta', () => {
    matches = true;
    const a = fakeEl();
    watchView(fakeContainer({ parts: [a] }));
    armEnter(4000);
    fire();
    assert.ok(!a.classList.contains('enter'));
    matches = false;
  });

  test('con el título «Cargando» no anima ni gasta la ventana', () => {
    matches = false;
    const a = fakeEl();
    const c = fakeContainer({ parts: [a], title: 'Cargando incendios…' });
    watchView(c);
    armEnter(4000);
    fire();
    assert.ok(!a.classList.contains('enter'));
    c.title = 'Incendios cerca';
    fire();
    assert.ok(a.classList.contains('enter'), 'la ventana sigue abierta para el render real');
  });

  test('las cifras con número se animan y vuelven a su texto', () => {
    matches = false;
    const kpi = fakeEl('12.345 ha');
    kpi.isConnected = false; // el tick se corta y restaura el texto
    const raf = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = (cb) => cb(performance.now());
    try {
      watchView(fakeContainer({ counted: [kpi] }));
      armEnter(4000);
      fire();
      assert.equal(kpi.textContent, '12.345 ha');
    } finally {
      globalThis.requestAnimationFrame = raf;
    }
  });
});

describe('scanPass', () => {
  test('sin #scan no explota', () => {
    globalThis.document = { getElementById: () => null };
    assert.doesNotThrow(() => scanPass());
  });

  test('reinicia el barrido: quita .run y lo vuelve a poner', () => {
    matches = false;
    const calls = [];
    const classes = new Set();
    const scan = {
      offsetWidth: 320,
      classList: {
        add: (c) => { calls.push(`add:${c}`); classes.add(c); },
        remove: (c) => { calls.push(`remove:${c}`); classes.delete(c); },
        contains: (c) => classes.has(c),
      },
    };
    globalThis.document = { getElementById: (id) => (id === 'scan' ? scan : null) };
    scanPass();
    assert.deepEqual(calls, ['remove:run', 'add:run']);
    assert.ok(scan.classList.contains('run'));
  });

  test('con «reducir movimiento» no toca el elemento', () => {
    matches = true;
    const touched = [];
    const scan = { offsetWidth: 320, classList: { add: (c) => touched.push(c), remove: (c) => touched.push(c) } };
    globalThis.document = { getElementById: () => scan };
    scanPass();
    assert.deepEqual(touched, []);
    matches = false;
  });
});
