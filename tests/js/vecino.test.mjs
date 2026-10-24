/* «Lo que hay alrededor» en la vista vecino (#/v/<token>): contexto breve de la comuna
 * del lugar compartido — población y viviendas del Censo 2024 (OFI-07) y la interfaz
 * urbano-forestal (OFI-08) en lenguaje llano, sin cuenta y sin datos de personas.
 * vecino.js arrastra ui.js y speak.js, que tocan `window` al cargarse: stub mínimo como
 * en riesgo.test.mjs (index.js junta todas las suites en un proceso). fetch se simula
 * dentro del describe, como en smoke.test.mjs, para no pisar a otras suites. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { aroundBlock, trendBlock } = await import('../../web/js/views/vecino.js');
const { officialBlock } = await import('../../web/js/views/zona.js');
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

describe('pronóstico de esta semana contra el de la semana pasada (VECINO-01)', () => {
  const summary = (counts) => ({ sube: 0, baja: 0, igual: 0, sin_anterior: 0, sin_hoy: 0, ...counts });
  const row = (change, label, extra = {}) => ({
    target_date: '2026-10-24', current: 'alto', previous: 'moderado', change, change_label: label, missing: null, ...extra,
  });
  const bloque = (summaryCounts, rows) => String(trendBlock({ summary: summary(summaryCounts), rows }));

  test('cuando sube, lo dice y nombra el día', () => {
    const out = bloque({ sube: 1 }, [row('sube', 'Más alto que el pronóstico de la semana pasada')]);
    assert.ok(out.includes('Pronóstico de esta semana contra el de la semana pasada'));
    assert.ok(out.includes('Esta semana 1 día sube'));
    assert.ok(out.includes('24'), 'la fila debe nombrar el día del pronóstico');
    assert.ok(out.includes('Más alto que el pronóstico de la semana pasada'));
    assert.ok(out.includes('Son pronósticos, no lo que pasó.'));
  });

  test('cuando baja, muestra el paso entre los dos niveles', () => {
    const out = bloque({ baja: 1 }, [row('baja', 'Más bajo que el pronóstico de la semana pasada', { current: 'moderado', previous: 'alto' })]);
    assert.ok(out.includes('Esta semana 1 día baja'));
    assert.ok(out.includes('alto → moderado'));
  });

  test('cuando sigue igual, no inventa una comparación', () => {
    const out = bloque({ igual: 1 }, [row('igual', 'Igual que el pronóstico de la semana pasada', { current: 'alto', previous: 'alto' })]);
    assert.ok(out.includes('1 día sigue igual'));
    assert.ok(out.includes('alto · Igual que el pronóstico de la semana pasada'));
  });

  test('sin pronóstico de la semana pasada avisa sin alarmar', () => {
    const out = bloque({ sin_anterior: 1 }, [row('sin_anterior', 'No hay pronóstico de la semana pasada para ese día', { previous: null, missing: 'semana_pasada' })]);
    assert.ok(out.includes('Sin pronóstico de la semana pasada para comparar'));
    assert.ok(out.includes('No hay pronóstico de la semana pasada para ese día'));
    assert.ok(!out.includes('sube') && !out.includes('baja'));
  });

  test('sin datos o con null no se pinta nada', () => {
    assert.equal(String(trendBlock(null)), '');
    assert.equal(String(trendBlock(undefined)), '');
    assert.equal(String(trendBlock({})), '');
    assert.equal(String(trendBlock({ summary: summary({}), rows: [] })), '');
  });
});

/* OFI-04 opción 2: la vista compartida siempre muestra el bloque «¿Qué dijo la autoridad?»
   (sin incendio CONAF el enlace a SENAPRED es lo único que queda) y le pasa el nombre de la
   comuna del lugar como tercer argumento. Aquí se fija ese contrato del helper compartido. */
describe('enlace a la alerta oficial de SENAPRED (OFI-04)', () => {
  test('con la comuna del lugar compartido el enlace la nombra y abre en otra pestaña', () => {
    const out = String(officialBlock(null, null, 'Talca'));
    assert.ok(out.includes('href="https://senapred.cl/alertas/"'));
    assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener"'));
    assert.ok(out.includes('alerta oficial vigente para Talca'));
  });
  test('sin incendio de CONAF el bloque sigue existiendo: no afirma nada por BRASA', () => {
    const out = String(officialBlock(null, null, 'Curicó'));
    assert.ok(out.includes('¿Qué dijo la autoridad?'));
    assert.ok(!out.includes('CONAF:'));
    assert.ok(!/no hay alerta|sin alerta/i.test(out));
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
