/* Pruebas de web/js/capas.js con node:test (MAPA-01): el estado de las capas del mapa,
 * su lectura desde la URL (#/mapa?capas=focos,riesgo) y su escritura de vuelta al hash. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { LAYERS, capasParam, defaultCapas, hashWithCapas, parseCapas, setCapa } from '../../web/js/capas.js';

const KEYS = LAYERS.map((l) => l.key);
const on = (state) => KEYS.filter((k) => state[k]);

describe('defaultCapas', () => {
  test('enciende focos, incendios, avisos y lugares; el resto apagado', () => {
    assert.deepEqual(on(defaultCapas()), ['focos', 'incendios', 'avisos', 'lugares']);
  });
});

describe('parseCapas', () => {
  test('sin parámetro devuelve null: la vista usa sus valores por defecto', () => {
    assert.equal(parseCapas(null), null);
    assert.equal(parseCapas(undefined), null);
  });
  test('la lista enciende solo las capas nombradas', () => {
    assert.deepEqual(on(parseCapas('focos,riesgo')), ['focos', 'riesgo']);
  });
  test('un parámetro vacío apaga todo (estado compartible)', () => {
    assert.deepEqual(on(parseCapas('')), []);
  });
  test('ignora claves desconocidas y espacios', () => {
    assert.deepEqual(on(parseCapas(' focos , inventada ,rayos')), ['focos', 'rayos']);
  });
  test('riesgo y lluvia son excluyentes: gana la última de la lista', () => {
    assert.deepEqual(on(parseCapas('riesgo,lluvia,focos')), ['focos', 'lluvia']);
    assert.deepEqual(on(parseCapas('lluvia,riesgo,focos')), ['focos', 'riesgo']);
  });
});

describe('setCapa', () => {
  test('enciende y apaga una capa sin tocar las demás', () => {
    const state = setCapa(defaultCapas(), 'focos', false);
    assert.deepEqual(on(state), ['incendios', 'avisos', 'lugares']);
    assert.deepEqual(on(setCapa(state, 'rayos', true)), ['incendios', 'avisos', 'lugares', 'rayos']);
  });
  test('encender una excluyente apaga a la otra', () => {
    const conLluvia = setCapa(defaultCapas(), 'lluvia', true);
    const conRiesgo = setCapa(conLluvia, 'riesgo', true);
    assert.equal(conRiesgo.riesgo, true);
    assert.equal(conRiesgo.lluvia, false);
  });
  test('apagar una excluyente no enciende a la otra', () => {
    const state = setCapa(setCapa(defaultCapas(), 'riesgo', true), 'riesgo', false);
    assert.equal(state.riesgo, false);
    assert.equal(state.lluvia, false);
  });
  test('clave desconocida devuelve el mismo estado', () => {
    const state = defaultCapas();
    assert.equal(setCapa(state, 'inventada', true), state);
  });
});

describe('capasParam', () => {
  test('serializa solo las encendidas, en el orden del control', () => {
    assert.equal(capasParam(defaultCapas()), 'focos,incendios,avisos,lugares');
  });
  test('refleja las capas activas tras un toggle', () => {
    const state = setCapa(defaultCapas(), 'riesgo', true);
    assert.equal(capasParam(state), 'focos,incendios,riesgo,avisos,lugares');
    assert.equal(capasParam(parseCapas('focos,riesgo')), 'focos,riesgo');
  });
  test('ida y vuelta conserva el estado', () => {
    const state = setCapa(setCapa(defaultCapas(), 'lluvia', true), 'avisos', false);
    assert.deepEqual(parseCapas(capasParam(state)), state);
  });
});

describe('hashWithCapas', () => {
  test('agrega el parámetro capas conservando la vista', () => {
    assert.equal(hashWithCapas('#/mapa', parseCapas('focos,riesgo')), '#/mapa?capas=focos,riesgo');
  });
  test('conserva los demás parámetros de la URL', () => {
    const out = hashWithCapas('#/mapa?lat=-33.4&lon=-70.6', defaultCapas());
    assert.equal(out, '#/mapa?lat=-33.4&lon=-70.6&capas=focos,incendios,avisos,lugares');
  });
  test('reemplaza un parámetro capas anterior', () => {
    const out = hashWithCapas('#/mapa?capas=focos&z=11', parseCapas('riesgo'));
    assert.equal(out, '#/mapa?z=11&capas=riesgo');
  });
  test('un hash que no es ruta vuelve a la vista del mapa', () => {
    assert.equal(hashWithCapas('#panel', defaultCapas()), '#/mapa?capas=focos,incendios,avisos,lugares');
  });
});
