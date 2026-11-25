/* Pruebas de la reutilización de secundarios de «Mi zona» (REND-02 t3) con node:test:
 * pedirSecundario reutiliza lo vigente por clave y vigencia, comparte el vuelo en curso,
 * descarta respuestas de claves reemplazadas, no deja vigente un fallo (y retira lo
 * vencido), invalida al editar el lugar y comparte el panorama por comuna. zona.js toca
 * `window` al cargarse, así que se importa con un global mínimo (igual que zona.test.mjs). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { pedirSecundario, SECUNDARIOS } = await import('../../web/js/views/zona.js');

const MIN = 60000;
const TTL = (i) => SECUNDARIOS[i][0]; // fila: [vigencia, Map visible, cómo pedir]
const lugar = (extra = {}) => ({ id: 'p1', lat: -33.05, lon: -71.6, radius_km: 5, comuna: { code: '13101' }, ...extra });
const fila = (i, pedir, visible) => [TTL(i), visible || new Map(), pedir];
const turnoLibre = () => new Promise((r) => setImmediate(r)); // pedir() corre en un microturno
const vigentes = (registro) => [...registro.keys()].filter((k) => !k.startsWith('@')).length;

/* Reloj controlable para las vigencias. */
async function conReloj(fn) {
  const reloj = { t: 0 };
  const realNow = Date.now;
  Date.now = () => reloj.t;
  try { await fn(reloj); } finally { Date.now = realNow; }
}

describe('SECUNDARIOS · vigencias conservadoras por fuente', () => {
  test('historial, lluvia, estación y panorama 10 min; aire 30 min; oficiales 5 min', () => {
    assert.equal(TTL(0), 10 * MIN);
    assert.equal(TTL(1), 10 * MIN);
    assert.equal(TTL(2), 10 * MIN);
    assert.equal(TTL(3), 10 * MIN);
    assert.equal(TTL(4), 30 * MIN);
    assert.equal(TTL(5), 5 * MIN);
  });
});

describe('pedirSecundario · reutilización entre renders', () => {
  test('el reingreso dentro de la vigencia no repite el pedido ni repinta', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    const f = fila(2, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); }, visible);
    assert.deepEqual(await pedirSecundario(registro, 2, lugar(), f), { ok: 1 });
    assert.deepEqual(visible.get('p1'), { ok: 1 });
    assert.equal(await pedirSecundario(registro, 2, lugar(), f), null);
    assert.equal(pedidos, 1);
  });

  test('una copia del service worker vence desde la fecha guardada, no desde su entrega', () => conReloj(async (reloj) => {
    const registro = new Map();
    const visible = new Map();
    const origen = Date.UTC(2026, 10, 25, 12);
    reloj.t = origen + 9 * MIN;
    let pedidos = 0;
    const f = fila(0, () => {
      pedidos += 1;
      return Promise.resolve({ body: { incidents: [] }, cachedAt: new Date(origen).toISOString() });
    }, visible);
    await pedirSecundario(registro, 0, lugar(), f);
    assert.deepEqual(visible.get('p1'), { incidents: [] });
    reloj.t = origen + 11 * MIN;
    await pedirSecundario(registro, 0, lugar(), f);
    assert.equal(pedidos, 2);
  }));

  test('vencida la vigencia se pide de nuevo solo el tipo vencido', () => conReloj(async (reloj) => {
    const registro = new Map();
    let pedidos = 0;
    const pedir = () => { pedidos += 1; return Promise.resolve({ ok: 1 }); };
    const pedirTipo = (i) => pedirSecundario(registro, i, lugar(), fila(i, pedir));
    await pedirTipo(0); await pedirTipo(4); await pedirTipo(1);
    reloj.t = 11 * MIN; // solo el historial venció
    await pedirTipo(0); await pedirTipo(4); await pedirTipo(1);
    assert.equal(pedidos, 4);
  }));

  test('las alertas oficiales se repiden al vencer su vigencia corta (5 min)', () => conReloj(async (reloj) => {
    const registro = new Map();
    let pedidos = 0;
    const f = fila(5, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); });
    await pedirSecundario(registro, 5, lugar(), f);
    reloj.t = 4 * MIN;
    await pedirSecundario(registro, 5, lugar(), f);
    assert.equal(pedidos, 1);
    reloj.t = 6 * MIN;
    await pedirSecundario(registro, 5, lugar(), f);
    assert.equal(pedidos, 2);
  }));

  test('el TTL oficial cuenta desde la descarga de SENAPRED, no desde que llega al navegador', () => conReloj(async (reloj) => {
    const registro = new Map();
    const origen = Date.UTC(2026, 10, 25, 12);
    reloj.t = origen + 4 * MIN; // SENAPRED puede seguir sirviendo la lista vacía hasta cinco minutos
    let pedidos = 0;
    const f = fila(5, () => {
      pedidos += 1;
      return Promise.resolve({ alerts: [], fetched_at: new Date(origen).toISOString() });
    });
    await pedirSecundario(registro, 5, lugar(), f);
    reloj.t = origen + 6 * MIN; // la copia local no debe ocultar una alerta nueva
    await pedirSecundario(registro, 5, lugar(), f);
    assert.equal(pedidos, 2);
  }));

  test('alerta oficial vencida cuya renovación falla deja de mostrarse', () => conReloj(async (reloj) => {
    const registro = new Map();
    const visible = new Map();
    let falla = false;
    const f = fila(5, () => (falla ? Promise.reject(new Error('sin señal')) : Promise.resolve({ alerta: 'roja' })), visible);
    await pedirSecundario(registro, 5, lugar(), f);
    assert.deepEqual(visible.get('p1'), { alerta: 'roja' });
    reloj.t = 6 * MIN; falla = true;
    assert.notEqual(await pedirSecundario(registro, 5, lugar(), f), null); // repinta sin la alerta
    assert.equal(visible.has('p1'), false);
    assert.equal(vigentes(registro), 0); // el fallo no queda vigente: el próximo render reintenta
    falla = false;
    assert.deepEqual(await pedirSecundario(registro, 5, lugar(), f), { alerta: 'roja' });
  }));

  test('dos renders seguidos comparten el vuelo: un solo pedido por clave', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    let resolver;
    const f = fila(2, () => new Promise((res) => { pedidos += 1; resolver = res; }), visible);
    const r1 = pedirSecundario(registro, 2, lugar(), f);
    const r2 = pedirSecundario(registro, 2, lugar(), f);
    await turnoLibre();
    resolver({ dato: 1 });
    assert.deepEqual(await r1, { dato: 1 });
    assert.equal(await r2, null); // el mismo valor ya quedó visible: un solo repintado
    assert.equal(pedidos, 1);
    assert.deepEqual(visible.get('p1'), { dato: 1 });
  });

  test('editar el lugar retira lo visible y una respuesta vieja no pisa la nueva', async () => {
    const registro = new Map();
    const visible = new Map();
    const pendientes = [];
    const f = fila(5, (p) => new Promise((res) => pendientes.push([p.lat, res])), visible);
    const viejo = pedirSecundario(registro, 5, lugar(), f);
    const nuevo = pedirSecundario(registro, 5, lugar({ lat: -39.8 }), f); // lugar editado
    await turnoLibre();
    assert.equal(pendientes.length, 2);
    pendientes[1][1]({ de: 'nueva' }); // la nueva llega primero
    assert.deepEqual(await nuevo, { de: 'nueva' });
    pendientes[0][1]({ de: 'vieja' }); // la vieja llega después
    assert.equal(await viejo, null);
    assert.deepEqual(visible.get('p1'), { de: 'nueva' });
  });

  test('editar el lugar retira el dato anterior antes de que llegue el nuevo', async () => {
    const registro = new Map();
    const visible = new Map();
    const f = fila(2, () => Promise.resolve({ ok: 1 }), visible);
    await pedirSecundario(registro, 2, lugar(), f);
    assert.equal(visible.has('p1'), true);
    const editado = pedirSecundario(registro, 2, lugar({ lon: -73.1 }), f);
    assert.equal(visible.has('p1'), false); // síncrono: el primer pintado ya no lo muestra
    await editado;
  });

  test('cambiar solo el radio vuelve a pedir el historial', async () => {
    const registro = new Map();
    let pedidos = 0;
    const f = fila(0, () => { pedidos += 1; return Promise.resolve({ incidentes: [] }); });
    await pedirSecundario(registro, 0, lugar(), f);
    await pedirSecundario(registro, 0, lugar(), f);
    assert.equal(pedidos, 1);
    await pedirSecundario(registro, 0, lugar({ radius_km: 2 }), f);
    assert.equal(pedidos, 2);
  });

  test('conteo: N lugares × 6 secundarios se piden una vez; el reingreso pide 0', async () => {
    const lugares = [lugar(), lugar({ id: 'p2', comuna: { code: '13102' } }), lugar({ id: 'p3', comuna: { code: '13103' } })];
    const registro = new Map();
    const visibles = SECUNDARIOS.map(() => new Map());
    let pedidos = 0;
    const pedir = () => { pedidos += 1; return Promise.resolve({ ok: 1 }); };
    const ronda = () => Promise.all(lugares.flatMap((p) => SECUNDARIOS.map((_, i) =>
      pedirSecundario(registro, i, p, [TTL(i), visibles[i], pedir]))));
    await ronda();
    assert.equal(pedidos, 6 * lugares.length); // antes: 6N en cada render
    await ronda();
    assert.equal(pedidos, 6 * lugares.length); // reingreso dentro de vigencia: 0 pedidos
  });
});

describe('pedirSecundario · panorama por comuna', () => {
  test('la misma comuna comparte clave, vuelo y valor entre dos lugares', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    let resolver;
    const f = fila(1, () => new Promise((res) => { pedidos += 1; resolver = res; }), visible);
    const r1 = pedirSecundario(registro, 1, lugar(), f);
    const r2 = pedirSecundario(registro, 1, lugar({ id: 'p2' }), f);
    await turnoLibre();
    resolver({ ok: 1 });
    assert.deepEqual(await r1, { ok: 1 });
    assert.deepEqual(await r2, { ok: 1 });
    assert.equal(pedidos, 1);
    assert.deepEqual(visible.get('p2'), { ok: 1 });
    const r3 = pedirSecundario(registro, 1, lugar({ id: 'p3', comuna: { code: '13579' } }), f);
    await turnoLibre();
    assert.equal(pedidos, 2); // otra comuna es otra clave
    resolver({ ok: 2 });
    assert.deepEqual(await r3, { ok: 2 });
  });

  test('panorama vigente: un lugar nuevo de la misma comuna recibe el valor sin pedir', async () => {
    const registro = new Map();
    const visible = new Map();
    let pedidos = 0;
    const f = fila(1, () => { pedidos += 1; return Promise.resolve({ ok: 1 }); }, visible);
    await pedirSecundario(registro, 1, lugar(), f);
    assert.deepEqual(await pedirSecundario(registro, 1, lugar({ id: 'p2' }), f), { ok: 1 });
    assert.equal(pedidos, 1);
    assert.deepEqual(visible.get('p2'), { ok: 1 });
    assert.equal(await pedirSecundario(registro, 1, lugar({ id: 'p2' }), f), null);
  });

  test('mover el lugar a un punto sin comuna retira el panorama anterior', async () => {
    const registro = new Map();
    const visible = new Map();
    const f = [TTL(1), visible, SECUNDARIOS[1][2]];
    const conComuna = [TTL(1), visible, () => Promise.resolve({ incendios: 12 })];
    await pedirSecundario(registro, 1, lugar(), conComuna);
    assert.deepEqual(visible.get('p1'), { incendios: 12 });
    const sinComuna = pedirSecundario(registro, 1, lugar({ comuna: null }), f);
    assert.equal(visible.has('p1'), false); // se retira antes del primer pintado
    await sinComuna;
    assert.equal(visible.has('p1'), false); // «no aplica» no repone el panorama anterior
  });
});
