/* Pruebas de web/js/escenario.js: el escenario de propagación en palabras para un vecino.
 * El módulo no pinta ni inventa: solo traduce el `spread` que ya devuelve el API. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { FFMC_TRAMOS, direccion, esEscenario, humedad, limites, resumen, viento } from '../../web/js/escenario.js';

const SPREAD = {
  kind: 'escenario_estimado',
  ffmc: 92.4,
  wind_kmh: 24,
  wind_deg: 315,
  slope_deg: null,
  direction_deg: 180,
  speed_kmh: 1.4,
  speed_m_min: 23.3,
  isi: 4.2,
  fuel: 'pastizal y matorral de referencia',
  reference: 'FBP canadiense',
  assumptions: [
    'Viento y combustible fino (FFMC) del centro de la comuna, no del punto exacto del fuego; viento del pronóstico de las 12:00 UTC.',
    'Terreno plano: BRASA aún no tiene modelo de elevaciones; la pendiente puede acelerar el avance.',
  ],
  note: 'Escenario estimado con las condiciones de ahora: no es una predicción ni el perímetro del incendio.',
};

const texto = (r) => [r.titular, r.detalle, ...r.limites].join(' ');

describe('escenario de propagación en palabras', () => {
  test('con viento del noroeste explica el avance, la humedad y la pendiente', () => {
    const r = resumen(SPREAD);
    assert.ok(r.titular.includes('sur'), 'el titular debe decir hacia dónde avanza');
    assert.ok(r.titular.includes('24 km/h'), 'el titular debe decir cuánto sopla el viento');
    assert.ok(r.titular.includes(humedad(SPREAD)), 'el titular debe traer la frase de humedad');
    assert.ok(r.titular.includes('muy secos'), 'FFMC 92,4 es el tramo más seco');
    assert.ok(r.limites.some((l) => l.includes('pendiente')), 'la lista debe declarar la pendiente no considerada');
  });

  test('sin dirección de avance no inventa un rumbo ni deja huecos', () => {
    const r = resumen({ ...SPREAD, direction_deg: null });
    assert.ok(!/hacia el (norte|noreste|este|sureste|sur|suroeste|oeste|noroeste)/.test(texto(r)));
    assert.ok(!/undefined|null/.test(texto(r)));
  });

  test('con FFMC bajo la humedad se explica como del tramo húmedo', () => {
    const frase = humedad({ ...SPREAD, ffmc: 78 });
    assert.ok(frase.includes('humedad'), 'el tramo bajo debe hablar de humedad');
    assert.ok(!frase.includes('muy secos'));
    assert.ok(!resumen({ ...SPREAD, ffmc: 78 }).titular.includes('muy secos'));
  });

  test('los cortes de FFMC están declarados y se respetan', () => {
    assert.equal(FFMC_TRAMOS.muySeco, 90);
    assert.equal(FFMC_TRAMOS.seco, 80);
    assert.ok(humedad({ ffmc: 90 }).includes('muy secos'));
    assert.ok(!humedad({ ffmc: 80 }).includes('muy secos'));
    assert.ok(!humedad({ ffmc: FFMC_TRAMOS.seco - 1 }).includes('secos'));
  });

  test('solo el escenario estimado pinta el bloque', () => {
    assert.equal(esEscenario(SPREAD), true);
    assert.equal(esEscenario({ ...SPREAD, kind: 'algo_que_no_es_escenario' }), false);
    assert.equal(esEscenario(null), false);
    assert.equal(resumen({ ...SPREAD, kind: 'algo_que_no_es_escenario' }), null);
    assert.equal(resumen(null), null);
  });

  test('no escribe promesas ni órdenes: el rótulo va en el note del API', () => {
    const casos = [SPREAD, { ...SPREAD, direction_deg: null }, { ...SPREAD, ffmc: 78 },
      { ...SPREAD, wind_kmh: null, wind_deg: null, speed_kmh: null }, { kind: 'escenario_estimado' }];
    for (const caso of casos) {
      const r = resumen(caso);
      const todo = [texto(r), direccion(caso), viento(caso), humedad(caso)].join(' ');
      for (const palabra of ['predicción', 'va a llegar', 'evacuar']) {
        assert.ok(!todo.includes(palabra), `«${palabra}» no puede salir del módulo`);
      }
    }
  });

  test('los rumbos y el viento usan el mismo criterio cardinal que la ficha', () => {
    assert.equal(direccion({ direction_deg: 180 }), 'hacia el sur');
    assert.equal(direccion({ direction_deg: 135 }), 'hacia el sureste');
    assert.equal(direccion({ direction_deg: null }), '');
    assert.equal(viento({ wind_kmh: 24, wind_deg: 315 }), 'viento de 24 km/h desde el noroeste');
    assert.equal(viento({ wind_kmh: 24 }), '');
    assert.ok(limites(SPREAD).some((l) => l.includes('combate')));
  });
});
