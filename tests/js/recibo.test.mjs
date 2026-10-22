/* Recibo de datos del dispositivo (PRIV-03): la página de privacidad muestra cuánto va a
 * descargar o borrar antes de que la persona toque los botones. Los reportes ciudadanos
 * no se cuentan: se guardan sin identificador y no cuelgan del dispositivo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { fechaLarga, reciboDe } from '../../web/js/recibo.js';

const dispositivo = { registrado_at: '2026-10-01T12:00:00Z', suscripcion_push: null, telegram_chat_id: null };

describe('recibo de /api/me/export', () => {
  test('un dispositivo sin datos dice 0 y no inventa reportes', () => {
    const r = reciboDe({ dispositivo, lugares: [], avisos: [] }, '2026-10-21');
    assert.equal(r.lugares, 0);
    assert.equal(r.avisos, 0);
    assert.equal(r.canales, 0);
    assert.equal(r.frase, '0 lugares guardados · 0 avisos, al 21 de octubre de 2026');
    assert.ok(!/reporte/i.test(r.frase), 'los reportes son anónimos: no se cuentan');
  });

  test('con un lugar, un aviso y push usa singular', () => {
    const r = reciboDe({
      dispositivo: { ...dispositivo, suscripcion_push: { endpoint: 'https://push.example/abc' } },
      lugares: [{ id: 'p1' }],
      avisos: [{ id: 'a1' }],
    }, '2026-10-21');
    assert.equal(r.frase, '1 lugar guardado · 1 aviso · 1 suscripción a avisos, al 21 de octubre de 2026');
  });

  test('con varios cuenta cada lista y cada canal de aviso', () => {
    const r = reciboDe({
      dispositivo: { ...dispositivo, suscripcion_push: { endpoint: 'https://push.example/abc' }, telegram_chat_id: '123' },
      lugares: [{}, {}, {}],
      avisos: Array.from({ length: 12 }, () => ({})),
      reportes: [{}, {}],
    }, '2026-10-21');
    assert.equal(r.lugares, 3);
    assert.equal(r.avisos, 12);
    assert.equal(r.canales, 2);
    assert.equal(r.frase, '3 lugares guardados · 12 avisos · 2 suscripciones a avisos, al 21 de octubre de 2026');
    assert.ok(!r.frase.includes('reportes'), 'un campo reportes en el export no entra al recibo');
  });

  test('un export incompleto o con basura no rompe la página', () => {
    for (const datos of [null, undefined, {}, { lugares: 'tres', avisos: 7, dispositivo: null }]) {
      const r = reciboDe(datos, '2026-10-21');
      assert.equal(r.lugares, 0);
      assert.equal(r.avisos, 0);
      assert.equal(r.canales, 0);
    }
    assert.equal(reciboDe({}, null).frase, '0 lugares guardados · 0 avisos');
  });

  test('la fecha se escribe en palabras y no corre un día por zona horaria', () => {
    assert.equal(fechaLarga('2026-10-21'), '21 de octubre de 2026');
    assert.equal(fechaLarga('2026-01-01'), '1 de enero de 2026');
    assert.equal(fechaLarga('2026-13-01'), null);
    assert.equal(fechaLarga('21-10-2026'), null);
  });
});
