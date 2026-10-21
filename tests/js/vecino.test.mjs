/* «Lo que hay alrededor» en la vista vecino (#/v/<token>): contexto breve de la comuna
 * del lugar compartido — población y viviendas del Censo 2024 (OFI-07) y la interfaz
 * urbano-forestal (OFI-08) en lenguaje llano, sin cuenta y sin datos de personas.
 * vecino.js arrastra ui.js y speak.js, que tocan `window` al cargarse: stub mínimo como
 * en riesgo.test.mjs (index.js junta todas las suites en un proceso). fetch se simula
 * dentro del describe, como en smoke.test.mjs, para no pisar a otras suites. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { aroundBlock } = await import('../../web/js/views/vecino.js');
const { comunaExposure, comunaExposureOf } = await import('../../web/js/exposure.js');

// comuna.code = 7101 (Talca). Los archivos reales tienen esta forma:
// censo_2024.json → comunas: [{code, poblacion, viviendas, …}]; interfaz.json → comunas: {codigo: {…}}.
const CENSO = { comunas: [{ code: 7101, poblacion: 220000, viviendas: 80000 }] };
const CON_INTERFAZ = { comunas: { 7101: { ha_interfaz: 6054.7, pct_comuna: 17.31 } } };
const SIN_INTERFAZ = { comunas: {} };

describe('«Lo que hay alrededor»', () => {
  test('con censo e interfaz: dos cifras, la frase llana y la fuente', () => {
    const exposure = comunaExposureOf(CENSO, CON_INTERFAZ, 7101);
    assert.deepEqual(exposure, { poblacion: 220000, viviendas: 80000, interfaz: true });
    const section = String(aroundBlock(exposure));
    assert.ok(section.includes('Lo que hay alrededor'));
    assert.ok(section.includes('220.000'));
    assert.ok(section.includes('80.000'));
    assert.ok(section.includes('bosque toca las casas'));
    assert.ok(section.includes('Censo 2024'));
    assert.ok(section.includes('CONAF GEPRIF'));
  });

  test('sin zonas de interfaz la frase lo dice en claro', () => {
    const exposure = comunaExposureOf(CENSO, SIN_INTERFAZ, 7101);
    assert.equal(exposure.interfaz, false);
    const section = String(aroundBlock(exposure));
    assert.ok(section.includes('no registra interfaz urbano-forestal'));
    assert.ok(!section.includes('bosque toca'));
    assert.ok(section.includes('220.000'));
  });

  test('comuna fuera del censo → la sección no aparece', () => {
    assert.equal(comunaExposureOf(CENSO, CON_INTERFAZ, 9999), null);
    assert.equal(String(aroundBlock(null)), '');
    assert.equal(String(aroundBlock(undefined)), '');
  });
});

describe('archivo de datos ausente o sin conexión', () => {
  beforeEach(() => {
    globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
  });
  afterEach(() => {
    delete globalThis.fetch;
  });

  test('la sección no aparece y nada más cambia', async () => {
    const exposure = await comunaExposure(7101);
    assert.equal(exposure, null);
    assert.equal(String(aroundBlock(exposure)), '');
  });
});
