/* Pruebas de web/js/motion.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { armEnter, reduced, scanPass, watchView } from '../../web/js/motion.js';

function replaceGlobal(t, name, value) {
  const original = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, name, original);
    else delete globalThis[name];
  });
}

function installObserver(t) {
  const registrations = [];
  replaceGlobal(t, 'MutationObserver', class {
    constructor(callback) { this.callback = callback; }
    observe(target, options) { registrations.push({ callback: this.callback, target, options }); }
  });
  return registrations;
}

function fakeView(children = []) {
  return { children, querySelector: () => null, querySelectorAll: () => [] };
}

function fakeChild() {
  const styles = new Map();
  const classes = new Set();
  return {
    nodeType: 1,
    style: { setProperty: (name, value) => styles.set(name, value) },
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) },
    styles,
    classes,
  };
}

describe('reduced', () => {
  test('devuelve true cuando matchMedia indica que se reduzca el movimiento', (t) => {
    replaceGlobal(t, 'matchMedia', (query) => {
      assert.equal(query, '(prefers-reduced-motion: reduce)');
      return { matches: true };
    });
    assert.equal(reduced(), true);
  });

  test('devuelve false cuando matchMedia indica movimiento normal', (t) => {
    replaceGlobal(t, 'matchMedia', () => ({ matches: false }));
    assert.equal(reduced(), false);
  });
});

describe('entrada de vistas', () => {
  test('armEnter(ms) limita a esa ventana la animación de watchView', (t) => {
    let now = 100;
    replaceGlobal(t, 'matchMedia', () => ({ matches: false }));
    replaceGlobal(t, 'performance', { now: () => now });
    replaceGlobal(t, 'setTimeout', () => 0);
    const observers = installObserver(t);
    const activeChild = fakeChild();
    const activeView = fakeView([activeChild]);

    armEnter(25);
    watchView(activeView);
    now = 124;
    observers[0].callback();

    assert.equal(activeChild.styles.get('--i'), '0');
    assert.equal(activeChild.classes.has('enter'), true);

    const expiredChild = fakeChild();
    armEnter(25);
    watchView(fakeView([expiredChild]));
    now = 150;
    observers[1].callback();

    assert.equal(expiredChild.classes.has('enter'), false);
  });

  test('watchView observa un contenedor simple', (t) => {
    const observers = installObserver(t);
    const container = {};

    assert.doesNotThrow(() => watchView(container));
    assert.equal(observers.length, 1);
    assert.equal(observers[0].target, container);
    assert.deepEqual(observers[0].options, { childList: true });
  });
});

test('scanPass reinicia la clase de barrido cuando existe el elemento', (t) => {
  replaceGlobal(t, 'matchMedia', () => ({ matches: false }));
  const changes = [];
  const scan = {
    classList: {
      remove: (name) => changes.push(`remove:${name}`),
      add: (name) => changes.push(`add:${name}`),
    },
    offsetWidth: 1,
  };
  replaceGlobal(t, 'document', {
    getElementById: (id) => {
      assert.equal(id, 'scan');
      return scan;
    },
  });

  // Sin un navegador se valida la coordinación JS, no los estilos CSS finales de la animación.
  assert.doesNotThrow(scanPass);
  assert.deepEqual(changes, ['remove:run', 'add:run']);
});
