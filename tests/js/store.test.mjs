/* Pruebas de web/js/store.js (QA-05, ROB-04): contrato del estado global del que dependen todas
 * las vistas. Un manejador roto no debe dejar sin aviso a los demás suscriptores ni salir por
 * quien hizo set. Sin DOM: console.error se silencia con node:test. */
import { describe, mock, test } from 'node:test';
import assert from 'node:assert/strict';

const { store } = await import('../../web/js/store.js');

const silenciar = (t) => {
  const error = mock.method(console, 'error', () => {});
  t.after(() => error.mock.restore());
  return error;
};

describe('store', () => {
  test('el default de arranque no cambia', () => {
    assert.equal(store.get('theme'), 'dark');
    assert.equal(store.get('obsHours'), 24);
    assert.deepEqual(store.get('places'), []);
  });

  test('set avisa solo a los suscriptores de esa clave, con el valor nuevo', (t) => {
    const deTheme = [];
    const deOtraClave = [];
    const quitarTheme = store.on('theme', (valor) => deTheme.push(valor));
    const quitarOtra = store.on('view', (valor) => deOtraClave.push(valor));
    t.after(() => {
      quitarTheme();
      quitarOtra();
      store.set('theme', 'dark');
    });

    store.set('theme', 'light');

    assert.deepEqual(deTheme, ['light']);
    assert.deepEqual(deOtraClave, []);
  });

  test('on no dispara al suscribirse', (t) => {
    let veces = 0;
    const quitar = store.on('obsHours', () => {
      veces += 1;
    });
    t.after(quitar);

    assert.equal(veces, 0);
  });

  test('dos suscriptores de la misma clave reciben ambos y quitar uno no afecta al otro', (t) => {
    const primero = [];
    const segundo = [];
    const quitarPrimero = store.on('obsHours', (valor) => primero.push(valor));
    const quitarSegundo = store.on('obsHours', (valor) => segundo.push(valor));
    t.after(() => {
      quitarPrimero();
      quitarSegundo();
      store.set('obsHours', 24);
    });

    store.set('obsHours', 48);
    quitarPrimero();
    store.set('obsHours', 72);

    assert.deepEqual(primero, [48]);
    assert.deepEqual(segundo, [48, 72]);
  });

  test('suscribir dos veces la misma función no la duplica en las notificaciones', (t) => {
    let veces = 0;
    const fn = () => {
      veces += 1;
    };
    const quitar = store.on('obsHours', fn);
    store.on('obsHours', fn);
    t.after(() => {
      quitar();
      store.set('obsHours', 24);
    });

    store.set('obsHours', 48);

    assert.equal(veces, 1);
  });

  test('get devuelve lo último puesto', () => {
    store.set('status', { version: '0.9.0' });
    assert.deepEqual(store.get('status'), { version: '0.9.0' });
    store.set('status', null);
  });

  test('un manejador que lanza no impide que el siguiente reciba el valor', (t) => {
    const error = silenciar(t);
    const recibidos = [];
    const quitarRoto = store.on('places', () => {
      throw new Error('manejador roto');
    });
    const quitarBueno = store.on('places', (valor) => recibidos.push(valor));
    t.after(() => {
      quitarRoto();
      quitarBueno();
      store.set('places', []);
    });

    store.set('places', ['un lugar']);

    assert.deepEqual(recibidos, [['un lugar']]);
    assert.equal(error.mock.callCount(), 1);
    assert.equal(error.mock.calls[0].arguments[0], 'store');
    assert.equal(error.mock.calls[0].arguments[1], 'places');
    assert.equal(error.mock.calls[0].arguments[2].message, 'manejador roto');
  });

  test('un suscriptor async que rechaza se registra y no afecta a los demás', async (t) => {
    const error = silenciar(t);
    const recibidos = [];
    const quitarRoto = store.on('places', async () => {
      await Promise.resolve();
      throw new Error('manejador async roto');
    });
    const quitarBueno = store.on('places', (valor) => recibidos.push(valor));
    t.after(() => {
      quitarRoto();
      quitarBueno();
      store.set('places', []);
    });

    store.set('places', ['otro lugar']);
    await new Promise((resuelve) => setImmediate(resuelve));

    assert.deepEqual(recibidos, [['otro lugar']]);
    assert.equal(error.mock.callCount(), 1);
    assert.equal(error.mock.calls[0].arguments[0], 'store');
    assert.equal(error.mock.calls[0].arguments[1], 'places');
    assert.equal(error.mock.calls[0].arguments[2].message, 'manejador async roto');
  });

  test('set no lanza aunque un manejador lance', (t) => {
    silenciar(t);
    const quitar = store.on('risk', () => {
      throw new Error('manejador roto');
    });
    t.after(() => {
      quitar();
      store.set('risk', null);
    });

    assert.doesNotThrow(() => store.set('risk', { nivel: 'alto' }));
    assert.deepEqual(store.get('risk'), { nivel: 'alto' });
  });

  test('la función que devuelve on deja de notificar', () => {
    let veces = 0;
    const quitar = store.on('online', () => {
      veces += 1;
    });
    store.set('online', false);
    quitar();
    store.set('online', true);

    assert.equal(veces, 1);
    assert.equal(store.get('online'), true);
  });
});
