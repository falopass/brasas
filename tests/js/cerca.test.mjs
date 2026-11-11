/* Pruebas de la función pura `cercaDe` de web/js/cerca.js con node:test (MZ-10):
 * distancia y rumbo, ventana de 24 h, radio, CONAF extinguido, dudosos aparte y
 * lista vacía. cerca.js importa en cadena ui.js, que registra un listener «online»
 * a nivel de módulo, así que se importa con un global mínimo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { cercaDe } = await import('../../web/js/cerca.js');

const AHORA = Date.parse('2026-10-25T15:00:00Z');
const hace = (h) => new Date(AHORA - h * 3600000).toISOString();
const YO = { lat: -33.0, lon: -71.0 };

const obs = (extra = {}) => ({ id: 'o1', lat: -33.05, lon: -71.05, observed_at: hace(2), confidence: 'alta', sensor: 'VIIRS', ...extra });
const conaf = (extra = {}) => ({ id: 'f1', name: '(DEMO) Quilpué', status: 'confirmado', status_raw: 'Activo', lat: -33.05, lon: -71.05, started_at: hace(5), ...extra });
const incidente = (extra = {}) => ({ id: 'i1', status: 'posible', lat: -33.05, lon: -71.05, last_seen_at: hace(1), n_obs: 3, ...extra });
const OPC = { ahora: AHORA };

describe('cercaDe', () => {
  test('un incidente solo de señales débiles no entra: cuenta como dudosa', () => {
    // anomalia con n_reliable 0: sus focos son dudosos, no un resultado.
    const debil = incidente({ id: 'iD', status: 'anomalia', n_obs: 2, n_reliable: 0 });
    const miembro = obs({ id: 'oD', incident_id: 'iD', confidence: 'baja' });
    const { items, dudosos } = cercaDe(YO, { incidentes: [debil], observaciones: [miembro] }, OPC);
    assert.equal(items.length, 0);
    assert.equal(dudosos, 1); // el miembro presente cuenta una vez; n_obs no infla
  });

  test('mide distancia y rumbo con el orden lat/lon correcto', () => {
    // Al norte (~111 km) el cardinal debe ser «norte»; al este, «este». Un orden
    // invertido de lat/lon cambiaría ambos resultados.
    const norte = cercaDe(YO, { observaciones: [obs({ lat: -32.0, lon: -71.0 })] }, { ...OPC, radioKm: 200 }).items[0];
    assert.equal(norte.cardinal, 'norte');
    assert.ok(Math.abs(norte.km - 111.2) < 2, `km norte: ${norte.km}`);
    const este = cercaDe(YO, { observaciones: [obs({ lat: -33.0, lon: -70.0 })] }, { ...OPC, radioKm: 200 }).items[0];
    assert.equal(este.cardinal, 'este');
    assert.ok(este.bearing_deg > 60 && este.bearing_deg < 120, `rumbo este: ${este.bearing_deg}`);
  });

  test('solo focos de las últimas 24 horas, aunque la ventana del mapa sea mayor', () => {
    const { items, dudosos } = cercaDe(YO, {
      observaciones: [obs({ observed_at: hace(25) }), obs({ id: 'o2', observed_at: hace(23) })],
    }, OPC);
    assert.equal(items.length, 1);
    assert.equal(items[0].id, 'o2');
    assert.equal(dudosos, 0);
  });

  test('respeta el radio', () => {
    const lejos = obs({ lat: -33.5, lon: -71.0 }); // ~55 km
    assert.equal(cercaDe(YO, { observaciones: [lejos] }, OPC).items.length, 0);
    assert.equal(cercaDe(YO, { observaciones: [lejos] }, { ...OPC, radioKm: 60 }).items.length, 1);
  });

  test('CONAF extinguido queda fuera; uno activo entra', () => {
    const { items } = cercaDe(YO, {
      oficiales: [conaf({ status: 'extinguido' }), conaf({ id: 'f2', status: 'controlado' })],
    }, OPC);
    assert.equal(items.length, 1);
    assert.equal(items[0].tipo, 'conaf');
    assert.equal(items[0].id, 'f2');
  });

  test('incidentes abiertos entran; extinguido y fuente fija no', () => {
    const { items } = cercaDe(YO, {
      incidentes: [incidente(), incidente({ id: 'i2', status: 'extinguido' }), incidente({ id: 'i3', status: 'posible', fixed_source: true })],
    }, OPC);
    assert.equal(items.length, 1);
    assert.equal(items[0].tipo, 'incidente');
  });

  test('un foco dentro de un incidente listado no se repite', () => {
    const { items } = cercaDe(YO, {
      incidentes: [incidente()],
      observaciones: [obs({ incident_id: 'i1' }), obs({ id: 'o9', lat: -33.1, lon: -71.1 })],
    }, OPC);
    assert.equal(items.length, 2);
    assert.deepEqual(items.map((i) => i.id).sort(), ['i1', 'o9']);
  });

  test('focos dudosos dentro del radio se cuentan aparte, no en la lista', () => {
    const { items, dudosos } = cercaDe(YO, {
      observaciones: [obs({ confidence: 'baja' }), obs({ id: 'o2', confidence: 'baja' }), obs({ id: 'o3' })],
    }, OPC);
    assert.equal(items.length, 1);
    assert.equal(items[0].id, 'o3');
    assert.equal(dudosos, 2);
  });

  test('ordena por distancia y vacío devuelve lista vacía sin dudosos', () => {
    assert.deepEqual(cercaDe(YO, {}, OPC), { items: [], dudosos: 0 });
    const { items } = cercaDe(YO, {
      observaciones: [obs({ lat: -33.2, lon: -71.0 }), obs({ id: 'o2', lat: -33.05, lon: -71.0 })],
    }, OPC);
    assert.deepEqual(items.map((i) => i.id), ['o2', 'o1']);
  });

  test('el borde de las 24 h es exclusivo: exactamente 24 h ya quedó fuera', () => {
    const { items } = cercaDe(YO, {
      observaciones: [
        obs({ id: 'justo', observed_at: hace(24) }),          // 24 h clavadas: fuera
        obs({ id: 'dentro', observed_at: new Date(AHORA - 24 * 3600000 + 999).toISOString() }), // casi 24 h: dentro
      ],
    }, OPC);
    assert.deepEqual(items.map((i) => i.id), ['dentro']);
  });

  test('la hora de referencia acepta Date e ISO y se ignora lo ilegible', () => {
    const una = obs({ id: 'o1' });
    assert.equal(cercaDe(YO, { observaciones: [una] }, { ahora: new Date(AHORA) }).items.length, 1);
    assert.equal(cercaDe(YO, { observaciones: [una] }, { ahora: '2026-10-25T15:00:00Z' }).items.length, 1);
    // Sin referencia legible no se arma una lista que mienta «reciente».
    assert.deepEqual(cercaDe(YO, { observaciones: [una] }, { ahora: 'no-es-fecha' }), { items: [], dudosos: 0 });
  });

  test('un punto o una referencia sin coordenadas finitas no entran a la lista', () => {
    assert.deepEqual(cercaDe(null, { observaciones: [obs()] }, OPC), { items: [], dudosos: 0 });
    assert.deepEqual(cercaDe({ lat: NaN, lon: -71 }, { observaciones: [obs()] }, OPC), { items: [], dudosos: 0 });
    const { items } = cercaDe(YO, {
      observaciones: [obs({ id: 'bueno' }), obs({ id: 'roto', lat: 'norte' })],
      oficiales: [conaf({ id: 'f-roto', lat: Infinity })],
    }, OPC);
    assert.deepEqual(items.map((i) => i.id), ['bueno']);
  });

  test('un foco de incidente fuera del radio o no listado sí cuenta solo', () => {
    // El incidente quedó fuera del radio: sus miembros no se tapan (la deduplicación
    // solo esconde focos cuyo incidente sí se muestra).
    const lejano = incidente({ id: 'iL', lat: -33.8, lon: -71.8 });
    const { items } = cercaDe(YO, {
      incidentes: [lejano],
      observaciones: [obs({ id: 'oL', incident_id: 'iL' }), obs({ id: 'oX', incident_id: 'otro' })],
    }, OPC);
    assert.deepEqual(items.map((i) => i.id).sort(), ['oL', 'oX']);
  });

  test('un foco de fuente fija no entra ni cuenta como dudoso', () => {
    const { items, dudosos } = cercaDe(YO, {
      observaciones: [obs({ id: 'fijo', incident_fixed: true })],
    }, OPC);
    assert.deepEqual({ items: items.map((i) => i.id), dudosos }, { items: [], dudosos: 0 });
  });

  test('un confirmado o controlado nunca se degrada aunque sus focos sean débiles', () => {
    // El respaldo de CONAF pesa más que la confianza de las detecciones: el incidente
    // oficial entra aunque n_reliable sea 0 (la regla «anomalia débil» no lo toca).
    const { items } = cercaDe(YO, {
      incidentes: [
        incidente({ id: 'ic', status: 'confirmado', n_reliable: 0 }),
        incidente({ id: 'ico', status: 'controlado', n_reliable: 0 }),
      ],
    }, OPC);
    assert.deepEqual(items.map((i) => i.id).sort(), ['ic', 'ico']);
  });
});
