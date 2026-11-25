/* Pruebas de web/js/config.js (REND-02): esperarConfig, la espera compartida de /api/config.
 *
 * Contrato: resuelve en cuanto la configuración está en el store (o había copia guardada en
 * el dispositivo), con null si vence el plazo o si el consumidor aborta su signal. Un signal
 * ya abortada gana SIEMPRE, incluso con la configuración disponible: un consumidor cancelado
 * (vista cerrada, modal repintado) no ejecuta acciones muertas. Nunca rechaza, nunca cancela
 * la petición compartida (app.js la pide una sola vez) y cada espera limpia exactamente su
 * temporizador y su suscripción al store.
 *
 * Con {fresca: true} (los envíos la exigen: reportes y push): la copia guardada y las
 * siembras sin marca NO resuelven —una copia vieja pudo rotar la clave Turnstile o la push—;
 * solo resuelve la configuración que trajo pedirConfig en esta sesión (app.js marca con
 * marcarConfigFresca justo ANTES del store.set). La marca es de sesión: una vez puesta,
 * la fresca del store responde de inmediato y las actualizaciones posteriores también valen.
 *
 * Sin navegador: el store se maneja a mano, localStorage se simula por test y los plazos se
 * congelan con t.mock.timers (mismo patrón que globe.test.mjs). La limpieza de suscripciones
 * se cuenta con un envoltorio de store.on que lleva la cuenta de las bajas pendientes. */
import { afterEach, beforeEach, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { esperarConfig, marcarConfigFresca } from '../../web/js/config.js';
import { store } from '../../web/js/store.js';
import { storage } from '../../web/js/util.js';

let guardado;
beforeEach(() => {
  store.set('config', null); // estado de arranque: sin configuración en el store
  guardado = new Map();
  globalThis.localStorage = {
    getItem: (k) => (guardado.has(k) ? guardado.get(k) : null),
    setItem: (k, v) => guardado.set(k, String(v)),
    removeItem: (k) => guardado.delete(k),
  };
});

afterEach(() => {
  delete globalThis.localStorage;
  store.set('config', null);
});

/** Cuenta las suscripciones al store que siguen vivas: la limpieza debe ser exacta. */
function contarSuscripciones(t) {
  const original = store.on;
  let vivas = 0;
  store.on = (clave, fn) => {
    vivas += 1;
    const off = original(clave, fn);
    return () => {
      vivas -= 1;
      off();
    };
  };
  t.after(() => { store.on = original; });
  return () => vivas;
}

describe('esperarConfig: caminos inmediatos', () => {
  test('config ya en el store: resuelve de inmediato con el mismo objeto', async () => {
    const config = { zones: { norte: { bbox: [1, 2, 3, 4] } } };
    store.set('config', config);
    assert.equal(await esperarConfig(), config);
  });

  test('la configuración del store gana sobre la copia guardada del dispositivo', async () => {
    storage.set('config', { vieja: true });
    const actual = { nueva: true };
    store.set('config', actual);
    assert.equal(await esperarConfig(), actual);
  });

  test('sin config en el store pero con copia guardada: resuelve de inmediato con la copia', async () => {
    storage.set('config', { copia: true });
    // storage serializa: la copia llega con el contenido, no con la identidad
    assert.deepEqual(await esperarConfig(), { copia: true });
  });
});

describe('esperarConfig: espera, plazo y limpieza exacta', () => {
  test('arranque frío sin config ni copia: espera y vence a los 4000 ms por defecto', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let valor = 'pendiente';
    esperarConfig().then((v) => { valor = v; });
    t.mock.timers.tick(3999);
    await new Promise((resuelve) => setImmediate(resuelve));
    assert.equal(valor, 'pendiente'); // justo antes del plazo sigue esperando: no responde null al toque
    t.mock.timers.tick(1);
    await new Promise((resuelve) => setImmediate(resuelve));
    assert.equal(valor, null); // vencido: null, nunca un rechazo
  });

  test('config tardía: resuelve con el mismo objeto y retira exactamente su suscripción', async (t) => {
    const vivas = contarSuscripciones(t);
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const config = { push: { public_key: 'clave' } };
    const promesa = esperarConfig({ timeoutMs: 4000 });
    assert.equal(vivas(), 1); // mientras espera, una sola suscripción al store
    store.set('config', config);
    assert.equal(await promesa, config); // mismo objeto, sin copias
    assert.equal(vivas(), 0); // resuelta: la suscripción se retiró exactamente
    t.mock.timers.tick(60000); // el temporizador ya no está: nada vence tarde (y si lo hiciera, el guard no hace nada)
  });

  test('al vencer el plazo también se retira la suscripción', async (t) => {
    const vivas = contarSuscripciones(t);
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const vencida = esperarConfig({ timeoutMs: 100 });
    assert.equal(vivas(), 1);
    t.mock.timers.tick(100);
    assert.equal(await vencida, null);
    assert.equal(vivas(), 0);
  });

  test('store.set(config, null) termina la espera en null: contrato vigente, revisado', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const promesa = esperarConfig({ timeoutMs: 4000 });
    store.set('config', null);
    assert.equal(await promesa, null);
    // Revisión (REND-02): app.js nunca pone config en null (solo con una respuesta válida),
    // así que aceptar el null es solo protección: si algún día alguien reinicia la
    // configuración, ninguna espera queda colgada para siempre. Se pinea el contrato vigente.
  });
});

describe('esperarConfig: abortos sin cancelar la petición compartida', () => {
  test('signal ya abortada gana siempre, incluso con la configuración disponible', async () => {
    // Contrato final (REND-02): el aborto se revisa ANTES que el store y la copia guardada.
    // Un consumidor cancelado (vista cerrada, modal repintado) no ejecuta acciones muertas.
    const config = { zones: { sur: { bbox: [1, 2, 3, 4] } } };
    store.set('config', config);
    storage.set('config', config); // tampoco vale la copia guardada del dispositivo
    const control = new AbortController();
    control.abort();
    assert.equal(await esperarConfig({ signal: control.signal }), null);
  });

  test('signal ya abortada: null inmediato, sin suscribirse a nada', async (t) => {
    const vivas = contarSuscripciones(t);
    const control = new AbortController();
    control.abort();
    assert.equal(await esperarConfig({ signal: control.signal }), null);
    assert.equal(vivas(), 0); // no llegó a suscribirse: no hay nada que limpiar
  });

  test('dos consumidores: abortar uno no cancela al otro ni a la petición compartida', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const control = new AbortController();
    const queAbandona = esperarConfig({ timeoutMs: 4000, signal: control.signal });
    const queEspera = esperarConfig({ timeoutMs: 4000 });
    control.abort();
    assert.equal(await queAbandona, null); // quien aborta solo deja de esperar
    store.set('config', { version: 3 }); // la petición compartida sigue su curso
    assert.equal((await queEspera).version, 3); // el otro consumidor la recibe igual
  });

  test('abortar dos veces el mismo signal no rompe nada: el listener propio se quitó al abortar', async () => {
    const control = new AbortController();
    const promesa = esperarConfig({ timeoutMs: 4000, signal: control.signal });
    control.abort();
    assert.equal(await promesa, null);
    assert.doesNotThrow(() => control.abort());
  });
});

/* Con fresca: true los envíos (reportes, push) esperan SOLO la configuración de esta sesión.
 * La marca de marcarConfigFresca es de módulo y no se resetea entre tests: este describe va
 * al final del archivo y sus tests corren en orden —los que necesitan «sin marca» van antes
 * del primero que marca, como en un arranque real que aún no recibe respuesta de /api/config. */
describe('esperarConfig({fresca:true}): solo la configuración de esta sesión vale para enviar', () => {
  test('signal ya abortada gana igual: null sin importar copias, siembras ni marcas', async (t) => {
    const vivas = contarSuscripciones(t);
    storage.set('config', { copia: true });
    store.set('config', { copia: true }); // sembrada, como al arrancar
    const control = new AbortController();
    control.abort();
    assert.equal(await esperarConfig({ fresca: true, signal: control.signal }), null);
    assert.equal(vivas(), 0); // ni siquiera se suscribe: nada que limpiar
  });

  test('sin marca ni red: vence a su plazo y limpia la suscripción, aunque haya copia sembrada', async (t) => {
    const vivas = contarSuscripciones(t);
    t.mock.timers.enable({ apis: ['setTimeout'] });
    storage.set('config', { copia: true });
    store.set('config', { copia: true }); // la copia guardada no resuelve envíos
    const vencida = esperarConfig({ fresca: true, timeoutMs: 100 });
    assert.equal(vivas(), 1);
    t.mock.timers.tick(100);
    assert.equal(await vencida, null); // sin la fresca no se envía nada: la cola queda intacta
    assert.equal(vivas(), 0);
  });

  test('la copia guardada y las siembras sin marca no resuelven; solo la configuración marcada', async (t) => {
    const vivas = contarSuscripciones(t);
    t.mock.timers.enable({ apis: ['setTimeout'] });
    // Como app.js al arrancar: siembra la copia guardada en el store, SIN marca.
    storage.set('config', { copia: true });
    store.set('config', { copia: true });
    // Sin fresca, la copia alcanza para pintar: contraste con el que espera la fresca.
    assert.deepEqual(await esperarConfig(), { copia: true });
    let valor = 'pendiente';
    const promesa = esperarConfig({ fresca: true, timeoutMs: 4000 });
    promesa.then((v) => { valor = v; });
    await new Promise((resuelve) => setImmediate(resuelve));
    assert.equal(valor, 'pendiente'); // la copia sembrada NO resuelve a los envíos
    assert.equal(vivas(), 1);
    store.set('config', { remontaje: true }); // un repintado que siembra otra vez: tampoco
    await new Promise((resuelve) => setImmediate(resuelve));
    assert.equal(valor, 'pendiente');
    assert.equal(vivas(), 1); // la suscripción sigue viva: la fresca no llegó todavía
    t.mock.timers.tick(3999); // casi al plazo: sigue esperando
    await new Promise((resuelve) => setImmediate(resuelve));
    assert.equal(valor, 'pendiente');
    // Como pedirConfig: la marca va ANTES del store.set, en ese mismo evento resuelve.
    marcarConfigFresca();
    const fresca = { turnstile_site_key: 'clave-rotada' };
    store.set('config', fresca);
    assert.equal(await promesa, fresca); // con claves vigentes, sin copias
    assert.equal(valor, fresca);
    assert.equal(vivas(), 0); // limpieza exacta: la suscripción que sobrevivió se retira al resolver
  });

  test('dos consumidores esperando la fresca: la marca los resuelve a ambos y deja cero suscripciones', async (t) => {
    const vivas = contarSuscripciones(t);
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const uno = esperarConfig({ fresca: true, timeoutMs: 4000 });
    const dos = esperarConfig({ fresca: true, timeoutMs: 4000 });
    assert.equal(vivas(), 2); // dos suscripciones vivas mientras la fresca no llega
    marcarConfigFresca();
    const cfg = { push: { public_key: 'k' } };
    store.set('config', cfg);
    assert.equal(await uno, cfg);
    assert.equal(await dos, cfg);
    assert.equal(vivas(), 0); // cero al terminar: aperturas repetidas no acumulan nada
  });

  test('con la marca ya puesta (configuración recibida en esta sesión): la del store responde de inmediato', async () => {
    // Corre después de los que marcan: la marca es de sesión, como en la app real.
    const actual = { turnstile_site_key: 'clave-2', push: { public_key: 'k2' } };
    store.set('config', actual);
    assert.equal(await esperarConfig({ fresca: true }), actual);
    // Y una actualización posterior también resuelve al que espera fresca desde cero:
    // sin nada en el store arranca a esperar, y la marca de sesión ya vale para el evento.
    store.set('config', null);
    const promesa = esperarConfig({ fresca: true, timeoutMs: 4000 });
    store.set('config', { actualizada: true });
    assert.deepEqual(await promesa, { actualizada: true });
  });
});
