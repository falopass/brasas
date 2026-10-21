/* ESTADO-01: summarizeStatus traduce /api/status a palabras, sin inventar datos.
 * Se prueba la función pura (sin navegador): la página la usa para pintar los tres
 * bloques y node:test la importa tal cual. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const { summarizeStatus } = await import('../../web/js/estado.js');

const sano = () => ({
  freshness: { age_seconds: 180, stale: false },
  runs: [
    { product: 'GOES19_FDCF', ok: true, finished_at: new Date().toISOString() },
    { product: 'VIIRS_NOAA20_NRT', ok: true, finished_at: new Date().toISOString() },
  ],
  errors: { by_product: { GOES19_FDCF: { runs: 10, failed: 0 }, VIIRS_NOAA20_NRT: { runs: 10, failed: 0 } } },
  last_cycle: { backup: true, finished_at: new Date().toISOString() },
});

describe('summarizeStatus', () => {
  test('con todo sano dice la edad, que no hubo fallos y que el respaldo subió', () => {
    const r = summarizeStatus(sano());
    assert.match(r.text, /Datos de los satélites: hace 3 minutos/);
    assert.match(r.text, /GOES no falló en las últimas 24 horas/);
    assert.match(r.text, /El respaldo se subió bien/);
    assert.doesNotMatch(r.text, /undefined|null/);
  });

  test('con stale: true dice «atrasados» y los minutos', () => {
    const r = summarizeStatus({ freshness: { age_seconds: 2820, stale: true } });
    assert.match(r.text, /Atrasados: la última lectura es de hace 47 minutos/);
    assert.doesNotMatch(r.text, /undefined|null/);
  });

  test('con backup: false y backup_error dice que el respaldo falló y qué pasó', () => {
    const r = summarizeStatus({ last_cycle: { backup: false, backup_error: "work: Server error '500'" } });
    assert.match(r.text, /El respaldo falló: work: Server error '500'/);
    assert.match(r.text, /copia de seguridad fuera del servidor/);
    assert.doesNotMatch(r.text, /undefined|null/);
  });

  test('con una fuente fallida la nombra y cuenta sus fallos', () => {
    const r = summarizeStatus({
      freshness: { age_seconds: 2820, stale: true },
      last_cycle: { backup: false, backup_error: "work: Server error '500'" },
      errors: { by_product: { GOES19_FDCF: { runs: 142, failed: 3 } } },
    });
    assert.match(r.text, /Atrasados/);
    assert.match(r.text, /47 minutos/);
    assert.match(r.text, /El respaldo falló/);
    assert.match(r.text, /GOES falló 3 veces/);
    assert.doesNotMatch(r.text, /undefined|null/);
  });

  test('sin payload no inventa: dice que no hay dato y nunca escribe undefined', () => {
    const r = summarizeStatus({});
    assert.match(r.text, /No hay dato de la última lectura de los satélites/);
    assert.match(r.text, /No hay dato del respaldo/);
    assert.match(r.text, /No hay dato del último ciclo/);
    assert.equal(r.sources.length, 0);
    assert.doesNotMatch(r.text, /undefined|null/);
  });

  test('el error del respaldo se recorta para que no desborde la página', () => {
    const largo = 'x'.repeat(400);
    const r = summarizeStatus({ last_cycle: { backup: false, backup_error: largo } });
    assert.ok(r.text.length < 600);
    assert.match(r.text, /…/);
  });
});
