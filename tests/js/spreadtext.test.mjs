/* Pruebas de web/js/spreadtext.js (FUEGO-14): el escenario estimado explicado en
 * palabras de vecino — la etiqueta siempre visible y nunca un hueco «undefined». */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { spreadWords } from '../../web/js/spreadtext.js';

const SPREAD = {
  kind: 'escenario_estimado',
  ffmc: 92.4,
  wind_kmh: 25,
  wind_deg: 315,
  slope_deg: null,
  direction_deg: 135,
  speed_kmh: 1.8,
  speed_m_min: 30,
  isi: 4.1,
  fuel: 'pasto en pie seco (tipo O-1b del FBP canadiense)',
  reference: 'FCFDG (1992) ST-X-3',
  assumptions: ['Terreno plano: BRASA aún no tiene modelo de elevaciones.'],
  note: 'Escenario estimado con las condiciones de ahora: no es una predicción ni el perímetro del incendio.',
};

const todo = (r) => [r.resumen, r.porque, r.tecnico, r.etiqueta].join(' ');

const CASOS = [
  ['con rumbo y viento', SPREAD],
  ['sin dirección de viento', { ...SPREAD, wind_deg: null, direction_deg: null }],
  ['FFMC alto', { ...SPREAD, ffmc: 95 }],
  ['FFMC bajo', { ...SPREAD, ffmc: 72 }],
  ['escenario mínimo', { kind: 'escenario_estimado' }],
];

describe('escenario estimado en palabras de vecino', () => {
  for (const [nombre, spread] of CASOS) {
    test(`la etiqueta es siempre visible y no hay huecos (${nombre})`, () => {
      const r = spreadWords(spread);
      assert.match(r.etiqueta, /escenario estimado/i);
      assert.ok(r.etiqueta.includes('no es una predicción'));
      assert.ok(!/undefined|\bnull\b/.test(todo(r)), todo(r));
      assert.ok(r.porque.trim().length > 0, 'porque nunca viene vacío');
    });
  }

  test('con rumbo y viento dice velocidad, hacia dónde y de dónde sopla', () => {
    const r = spreadWords(SPREAD);
    assert.ok(r.resumen.includes('1,8 km/h'), r.resumen);
    assert.ok(r.resumen.includes('sureste'), 'direction_deg 135 → hacia el sureste');
    assert.ok(r.resumen.includes('desde el noroeste'), 'wind_deg 315 es DE DÓNDE viene el viento');
    assert.ok(r.resumen.includes('25 km/h'));
  });

  test('sin dirección de viento lo dice explícitamente y no inventa rumbos', () => {
    const r = spreadWords({ ...SPREAD, wind_deg: null, direction_deg: null });
    assert.ok(/no se (sabe|conoce)/.test(todo(r)), todo(r));
    assert.ok(!/hacia el (norte|noreste|este|sureste|sur|suroeste|oeste|noroeste)/.test(r.resumen));
    assert.ok(!/desde el (norte|noreste|este|sureste|sur|suroeste|oeste|noroeste)/.test(r.resumen));
  });

  test('la sequedad del pasto fino cambia con el FFMC', () => {
    assert.ok(spreadWords({ ...SPREAD, ffmc: 95 }).porque.includes('muy secos'));
    assert.ok(spreadWords({ ...SPREAD, ffmc: 72 }).porque.includes('humedad'));
  });

  test('sin modelo de elevación declara el terreno plano', () => {
    const r = spreadWords(SPREAD);
    assert.ok(r.porque.includes('modelo de elevación'));
    assert.ok(r.porque.includes('terreno plano'));
  });

  test('la jerga queda solo en la línea técnica', () => {
    const r = spreadWords(SPREAD);
    assert.ok(r.tecnico.includes('ISI'));
    assert.ok(!r.porque.includes('ISI'));
    assert.ok(!r.resumen.includes('ISI'));
  });

  test('sin escenario de BRASA no hay bloque', () => {
    assert.equal(spreadWords(null), null);
    assert.equal(spreadWords({ kind: 'otro_tipo' }), null);
  });
});
