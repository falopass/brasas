/* QA-120 — territorio de los focos en pantalla: con coordenadas reales de Mendoza,
 * Tarija y Tacna se comprueba de punta a punta que nada fuera de Chile se dibuja en el
 * mapa ni engorda el «N focos de calor» que anuncia el lector de pantalla. La guarda es
 * `inChile` (web/js/data.js) y aquí se prueba el camino real de la app:
 * store → visibleObservations → detectionsGeoJSON → resumenMapa. Sin red ni DOM. */
import { describe, test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { visibleObservations } from '../../web/js/data.js';
import { detectionsGeoJSON, resumenMapa } from '../../web/js/map.js';
import { store } from '../../web/js/store.js';

const OBSERVADO = '2026-10-21T08:30:00Z';
const AHORA = Date.parse('2026-10-21T09:00:00Z');

const foco = (id, lat, lon, comuna_code, sensor = 'VIIRS') => ({
  id, lat, lon, comuna_code, sensor, confidence: 'alta', frp_mw: 50, observed_at: OBSERVADO,
});

const CHILENOS = [
  foco('aysen', -45.40, -72.50, 11201),           // fiordos de la comuna de Aysén
  foco('visviri', -17.59, -69.48, 15202, 'ABI'),  // trifinio Chile-Perú-Bolivia: el límite mismo
];
const EXTRANJEROS = [
  foco('mendoza', -32.89, -68.84, null, 'ABI'),   // Argentina; ABI para probar también «squares»
  foco('tarija', -21.53, -64.73, null, 'MODIS'),  // Bolivia
  foco('tacna', -18.01, -70.25, null),            // Perú
  foco('pisiga', -17.60, -69.42, null),           // a metros del límite, del lado boliviano
];

const cargar = (puntos) => {
  store.set('obsFilter', { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } });
  store.set('observations', puntos);
};
const ids = (lista) => lista.map((o) => o.id);

afterEach(() => cargar([]));

describe('visibleObservations con el store real', () => {
  test('de una mezcla Chile + vecinos solo quedan los focos chilenos', () => {
    cargar([...EXTRANJEROS, ...CHILENOS]);
    assert.deepEqual(ids(visibleObservations()), ['aysen', 'visviri']);
  });

  test('aunque el punto extranjero esté a metros del límite, sin comuna no pasa', () => {
    cargar([CHILENOS[1], EXTRANJEROS[3]]);
    assert.deepEqual(ids(visibleObservations()), ['visviri']);
  });
});

describe('detectionsGeoJSON: lo que el mapa dibuja', () => {
  test('cada punto pintado tiene coordenadas chilenas; ninguna extranjera', () => {
    cargar([...EXTRANJEROS, ...CHILENOS]);
    const { dots } = detectionsGeoJSON(visibleObservations(), AHORA);
    assert.deepEqual(dots.features.map((f) => f.properties.id), ['aysen', 'visviri']);
    const pintadas = new Set(dots.features.map((f) => f.geometry.coordinates.join(',')));
    assert.deepEqual([...pintadas], ['-72.5,-45.4', '-69.48,-17.59']);
    for (const p of EXTRANJEROS) {
      assert.ok(!pintadas.has(`${p.lon},${p.lat}`), `${p.id} no debe pintarse`);
    }
  });

  test('los cuadrados de píxel ABI tampoco escapan: un ABI de Mendoza no deja marca', () => {
    cargar([...EXTRANJEROS, ...CHILENOS]);
    const { squares } = detectionsGeoJSON(visibleObservations(), AHORA);
    assert.deepEqual(squares.features.map((f) => f.properties.id), ['visviri']);
  });
});

describe('resumenMapa: el conteo que lee el lector de pantalla', () => {
  test('anuncia solo los focos chilenos aunque el store tenga extranjeros', () => {
    cargar([...EXTRANJEROS, ...CHILENOS]);
    const { dots } = detectionsGeoJSON(visibleObservations(), AHORA);
    const s = resumenMapa({ focos: dots.features });
    assert.match(s, /Mapa: 2 focos de calor/);
    assert.doesNotMatch(s, /[3-9]\d* focos de calor/);
  });

  test('con puros extranjeros dice en claro que no hay focos', () => {
    cargar(EXTRANJEROS);
    const { dots } = detectionsGeoJSON(visibleObservations(), AHORA);
    assert.match(resumenMapa({ focos: dots.features }), /sin focos de calor a la vista/);
  });
});

describe('qué cuenta como comuna chilena para la guarda', () => {
  test('comuna_code null o ausente no cuenta como Chile', () => {
    const { comuna_code, ...sinCode } = EXTRANJEROS[0];
    cargar([EXTRANJEROS[2], { ...sinCode, id: 'sin-code' }]);
    assert.deepEqual(visibleObservations(), []);
  });

  /* Fuga encontrada al escribir esta prueba (QA-120): `o.comuna_code != null` solo
   * rechaza null/undefined, así que un 0 o un «13101» en texto pasan y el foco
   * extranjero se dibujaría y contaría. La corrección de data.js quedó para otro
   * encargo; cuando la guarda sea estricta esta prueba debe afirmar la lista vacía. */
  test('fuga documentada: un comuna_code 0 o en texto hoy sí deja pasar puntos de fuera', () => {
    cargar([
      { ...EXTRANJEROS[0], comuna_code: 0 },        // Mendoza con un cero heredado
      { ...EXTRANJEROS[2], comuna_code: '13101' },  // Tacna con código de Valparaíso en texto
    ]);
    assert.deepEqual(ids(visibleObservations()), ['mendoza', 'tacna']);
  });
});
