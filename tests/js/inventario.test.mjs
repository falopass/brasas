/* Inventario local de #/privacidad (SEC-01): la página muestra conteos de lo que hay en
 * este teléfono, nunca el token, coordenadas ni el texto de un reporte. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { inventarioLocal } from '../../web/js/store.js';

// ui.js, que privacidad.js importa en cadena, se suscribe a «online» al cargarse.
globalThis.window = { addEventListener() {} };
const { lineasInventario } = await import('../../web/js/views/privacidad.js');

const T0 = new Date('2026-10-21T12:00:00Z').getTime();
const VACIO = { token: false, preferencias: [], reportes_en_cola: 0, reportes_vencidos: 0, cache_api: 0 };

/* localStorage y Cache API de mentira, instalados por prueba y restaurados al salir
 * (otras suites del mismo proceso instalan los suyos; ver reportes.test.mjs). */
async function conNavegador(fn, { cache } = {}) {
  const mem = new Map();
  const prevLocal = globalThis.localStorage;
  const prevCaches = globalThis.caches;
  globalThis.localStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
  if (cache === undefined) delete globalThis.caches; else globalThis.caches = cache;
  try {
    return await fn(mem);
  } finally {
    if (prevLocal === undefined) delete globalThis.localStorage; else globalThis.localStorage = prevLocal;
    if (prevCaches === undefined) delete globalThis.caches; else globalThis.caches = prevCaches;
  }
}

const cacheFake = (entradas) => ({
  keys: async () => Object.keys(entradas),
  open: async (nombre) => ({ keys: async () => (entradas[nombre] || []).map((url) => ({ url })) }),
});

const entrada = (id, horas) => ({
  id, kind: 'humo', lat: -35.427, lon: -71.655, description: `secreto-${id}`,
  created_at: new Date(T0 - horas * 3600000).toISOString(),
});

describe('inventarioLocal', () => {
  test('sin nada guardado devuelve ceros y listas vacías', async () => {
    await conNavegador(async () => {
      assert.deepEqual(await inventarioLocal(T0), VACIO);
    });
  });

  test('informa presencia de token y preferencias, nunca sus valores', async () => {
    await conNavegador(async (mem) => {
      mem.set('brasa:token', JSON.stringify('tok-secreto-123'));
      mem.set('brasa:theme', JSON.stringify('light'));
      mem.set('brasa:text', JSON.stringify('grande'));
      mem.set('brasa:detail', JSON.stringify('experto'));
      mem.set('brasa:cached-at', JSON.stringify('2026-10-21T10:00:00Z'));
      const inv = await inventarioLocal(T0);
      assert.equal(inv.token, true);
      assert.deepEqual(inv.preferencias, ['theme', 'text', 'detail']);
      const texto = JSON.stringify(inv);
      assert.ok(!texto.includes('tok-secreto-123'), 'el token no puede salir del inventario');
      assert.ok(!texto.includes('2026-10-21T10:00:00Z'), 'la marca de caché no es una preferencia');
    });
  });

  test('la cola cuenta los vigentes y los vencidos, y quita los vencidos', async () => {
    await conNavegador(async (mem) => {
      mem.set('brasa:outbox', JSON.stringify([entrada('a', 1), entrada('b', 2), entrada('viejo', 25)]));
      const inv = await inventarioLocal(T0);
      assert.equal(inv.reportes_en_cola, 2);
      assert.equal(inv.reportes_vencidos, 1);
      assert.ok(!JSON.stringify(inv).includes('secreto'), 'el inventario no lleva el texto de los reportes');
      assert.deepEqual(JSON.parse(mem.get('brasa:outbox')).map((e) => e.id), ['a', 'b']);
    });
  });

  test('la caché cuenta solo las copias de la API, no la interfaz', async () => {
    const cache = cacheFake({
      'brasa-dev': ['/', '/web/css/app.css'],
      'brasa-dev-api': ['/api/places', '/api/alerts'],
    });
    await conNavegador(async () => {
      assert.equal((await inventarioLocal(T0)).cache_api, 2);
    }, { cache });
  });

  test('sin Cache API (navegador antiguo o modo privado) devuelve 0', async () => {
    await conNavegador(async () => {
      assert.equal((await inventarioLocal(T0)).cache_api, 0);
    });
  });

  test('sin localStorage no lanza: devuelve el inventario vacío', async () => {
    await conNavegador(async () => {
      delete globalThis.localStorage;
      assert.deepEqual(await inventarioLocal(T0), VACIO);
    });
  });
});

describe('lineasInventario', () => {
  const texto = (inv) => lineasInventario(inv).map(String).join('');

  test('dos reportes en cola: los cuenta y avisa que salen solos', () => {
    const t = texto({ ...VACIO, reportes_en_cola: 2 });
    assert.ok(t.includes('2 reportes esperando señal'));
    assert.ok(t.includes('Se enviarán solos al volver la conexión'));
  });

  test('un solo reporte usa singular', () => {
    assert.ok(texto({ ...VACIO, reportes_en_cola: 1 }).includes('1 reporte esperando señal'));
  });

  test('cola vacía lo dice con todas sus letras', () => {
    assert.ok(texto(VACIO).includes('No hay reportes esperando señal'));
  });

  test('vencidos: los cuenta y explica que se quitaron de la cola', () => {
    const t = texto({ ...VACIO, reportes_vencidos: 1 });
    assert.ok(t.includes('1 venció sin enviarse'));
    assert.ok(t.includes('Pasado un día ya no sirven para una emergencia'));
  });

  test('preferencias con nombre legible', () => {
    const t = texto({ ...VACIO, preferencias: ['theme', 'text', 'detail'] });
    assert.ok(t.includes('colores, tamaño de letra y nivel de detalle'));
  });

  test('token y caché se cuentan en palabras, sin valores', () => {
    const t = texto({ ...VACIO, token: true, cache_api: 2 });
    assert.ok(t.includes('1 identificador de este dispositivo'));
    assert.ok(t.includes('2 copias de datos para ver sin señal'));
  });

  test('sin nada guardado, cada línea lo declara', () => {
    const t = texto(VACIO);
    assert.ok(t.includes('Sin identificador guardado'));
    assert.ok(t.includes('Sin preferencias guardadas'));
    assert.ok(t.includes('Sin copias para ver sin señal'));
  });
});
