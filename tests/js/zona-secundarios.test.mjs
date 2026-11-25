/* Pruebas de la reutilización de secundarios de «Mi zona» (REND-02 t3) con node:test:
 * pedirSecundario reutiliza lo vigente por clave y vigencia, comparte el vuelo en curso
 * entre renders seguidos, no guarda los fallos, invalida al editar el lugar y comparte
 * el panorama por comuna. zona.js toca `window` al cargarse, así que se importa con un
 * global mínimo (igual que zona.test.mjs). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { pedirSecundario, SECUNDARIOS } = await import('../../web/js/views/zona.js');

const MIN = 60000;
const TTL = (i) => SECUNDARIOS[i][0]; // fila: [vigencia, Map visible, cómo pedir]
const lugar = (extra = {}) => ({ id: 'p1', lat: -33.05, lon: -71.6, comuna: { code: '13101' }, ...extra });
/* Fila de prueba con el Map visible y un `pedir` contable; el registro y el Map se
   reciben por parámetro, así el conteo de pedidos es explícito por clave. */
const fila = (i, pedir, visible) => [TTL(i), visible || new Map(), pedir];

describe('SECUNDARIOS · vigencias conservadoras por fuente', () => {
  test('historial, lluvia y estación 10 min; aire 30 min; panorama 3 h; oficiales 5 min', () => {
    assert.equal(TTL(0), 10 * MIN); // incidentes: cambian en cada ciclo de ingesta
    assert.equal(TTL(2), 10 * MIN); // lluvia: el backend sirve la celda 30 min
    assert.equal(TTL(3), 10 * MIN); // estación: red EMA de la DMC, ~10 min
    assert.equal(TTL(4), 30 * MIN); // aire: SINCA cachea el resumen 30 min
    assert.equal(TTL(1), 3 * 60 * MIN); // panorama: agregados de temporada (GEPRIF)
    assert.equal(TTL(5), 5 * MIN); // oficiales: mitad del ciclo de SENAPRED (10 min)
  });
});

describe('pedirSecundario · reutilización entre renders', () => {
  test('el reingreso dentro de la vigencia no repite el pedido ni vuelve a guardar', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    const f = fila(2, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); }, visible);
    assert.deepEqual(await pedirSecundario(registro, 2, lugar(), f), { ok: 1 });
    assert.deepEqual(visible.get('p1'), { ok: 1 });
    assert.equal(await pedirSecundario(registro, 2, lugar(), f), null);
    assert.equal(pedidos, 1); // el reingreso dentro de vigencia pidió 0
  });

  test('vencida la vigencia se pide de nuevo solo el tipo vencido', async () => {
    const registro = new Map();
    const reloj = { t: 0 };
    const realNow = Date.now;
    Date.now = () => reloj.t;
    try {
      let pedidos = 0;
      const pedir = () => { pedidos += 1; return Promise.resolve({ ok: 1 }); };
      const pedirTipo = (i) => pedirSecundario(registro, i, lugar(), fila(i, pedir));
      await pedirTipo(0); // historial: 10 min
      await pedirTipo(4); // aire: 30 min
      await pedirTipo(1); // panorama: 3 h
      reloj.t = 11 * MIN; // solo el historial venció
      await pedirTipo(0);
      await pedirTipo(4);
      await pedirTipo(1);
      assert.equal(pedidos, 4); // 3 iniciales + solo el historial vencido
    } finally {
      Date.now = realNow;
    }
  });

  test('las alertas oficiales se repiden al vencer su vigencia corta (5 min)', async () => {
    const registro = new Map();
    const reloj = { t: 0 };
    const realNow = Date.now;
    Date.now = () => reloj.t;
    try {
      let pedidos = 0;
      const f = fila(5, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); });
      await pedirSecundario(registro, 5, lugar(), f);
      reloj.t = 4 * MIN;
      await pedirSecundario(registro, 5, lugar(), f);
      assert.equal(pedidos, 1); // a los 4 min sigue vigente
      reloj.t = 6 * MIN;
      await pedirSecundario(registro, 5, lugar(), f);
      assert.equal(pedidos, 2); // a los 6 min venció y se vuelve a pedir
    } finally {
      Date.now = realNow;
    }
  });

  test('dos renders seguidos comparten el vuelo: un solo pedido por clave', async () => {
    const registro = new Map();
    let pedidos = 0;
    let resolver;
    const f = fila(2, () => new Promise((res) => { pedidos += 1; resolver = res; }));
    const r1 = pedirSecundario(registro, 2, lugar(), f);
    const r2 = pedirSecundario(registro, 2, lugar(), f);
    await new Promise((r) => setImmediate(r)); // pedir() corre en un microturno
    resolver({ dato: 1 }); // la respuesta del render viejo alimenta al nuevo
    assert.deepEqual(await r1, { dato: 1 });
    assert.deepEqual(await r2, { dato: 1 });
    assert.equal(pedidos, 1);
  });

  test('un fallo no queda vigente: se reintenta y se conserva el último valor bueno visible', async () => {
    const registro = new Map();
    const visible = new Map([['p1', { bueno: 1 }]]);
    let falla = true;
    const f = fila(2, () => (falla ? Promise.reject(new Error('sin señal')) : Promise.resolve({ nuevo: 2 })), visible);
    assert.equal(await pedirSecundario(registro, 2, lugar(), f), null);
    assert.equal(registro.size, 0); // el fallo no se guardó como vigente
    assert.deepEqual(visible.get('p1'), { bueno: 1 }); // lo bueno de antes sigue visible
    assert.equal(await pedirSecundario(registro, 2, lugar(), f), null); // reintenta
    assert.equal(registro.size, 0);
    falla = false;
    assert.deepEqual(await pedirSecundario(registro, 2, lugar(), f), { nuevo: 2 });
    assert.deepEqual(visible.get('p1'), { nuevo: 2 });
  });

  test('editar el lugar (lat o lon) invalida la clave y obliga a pedir de nuevo', async () => {
    const registro = new Map();
    let pedidos = 0;
    const f = fila(2, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); });
    await pedirSecundario(registro, 2, lugar(), f);
    assert.equal(pedidos, 1);
    await pedirSecundario(registro, 2, lugar(), f); // sin cambios: reutiliza
    assert.equal(pedidos, 1);
    await pedirSecundario(registro, 2, lugar({ lat: -39.8 }), f); // editado: pide
    assert.equal(pedidos, 2);
    await pedirSecundario(registro, 2, lugar({ lon: -73.1 }), f); // editado: pide
    assert.equal(pedidos, 3);
  });

  test('conteo: N lugares × 6 secundarios se piden una vez; el reingreso pide 0', async () => {
    const lugares = [lugar(), lugar({ id: 'p2', comuna: { code: '13102' } }), lugar({ id: 'p3', comuna: { code: '13103' } })];
    const registro = new Map();
    let pedidos = 0;
    const pedir = () => { pedidos += 1; return Promise.resolve({ ok: 1 }); };
    const ronda = () => Promise.all(lugares.flatMap((p) => SECUNDARIOS.map((_, i) =>
      pedirSecundario(registro, i, p, [TTL(i), new Map(), pedir]))));
    await ronda();
    assert.equal(pedidos, 6 * lugares.length); // antes: 6N en cada render
    await ronda();
    assert.equal(pedidos, 6 * lugares.length); // reingreso dentro de vigencia: 0 pedidos
  });

  test('panorama: la misma comuna comparte clave, vuelo y valor entre dos lugares', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    let resolver;
    const f = fila(1, () => new Promise((res) => { pedidos += 1; resolver = res; }), visible);
    const a = lugar();
    const b = lugar({ id: 'p2' }); // otro lugar, misma comuna
    const r1 = pedirSecundario(registro, 1, a, f);
    const r2 = pedirSecundario(registro, 1, b, f);
    await new Promise((r) => setImmediate(r)); // pedir() corre en un microturno
    resolver({ ok: 1 });
    assert.deepEqual(await r1, { ok: 1 });
    assert.deepEqual(await r2, { ok: 1 });
    assert.equal(pedidos, 1); // un solo pedido de panorama para toda la comuna
    assert.deepEqual(visible.get('p1'), { ok: 1 });
    assert.deepEqual(visible.get('p2'), { ok: 1 }); // ambos lugares guardaron el valor
    const c = lugar({ id: 'p3', comuna: { code: '13579' } }); // otra comuna: otra clave
    const r3 = pedirSecundario(registro, 1, c, f);
    await new Promise((r) => setImmediate(r)); // pedir() corre en un microturno
    assert.equal(pedidos, 2); // otra comuna es otra clave: se vuelve a pedir
    resolver({ ok: 2 });
    assert.deepEqual(await r3, { ok: 2 });
  });

  test('panorama vigente: un lugar nuevo de la misma comuna recibe el valor sin pedir', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    const f = fila(1, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); }, visible);
    await pedirSecundario(registro, 1, lugar(), f);
    assert.deepEqual(await pedirSecundario(registro, 1, lugar({ id: 'p2' }), f), { ok: 1 }); // repinta
    assert.equal(pedidos, 1);
    assert.deepEqual(visible.get('p2'), { ok: 1 });
    assert.equal(await pedirSecundario(registro, 1, lugar({ id: 'p2' }), f), null); // ya lo tiene
  });
});
