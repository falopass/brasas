/* La hoja imprimible (/web/lista.html) debe decir cuándo se generó: un papel
 * de la temporada pasada con apariencia de actual es peor que no tenerlo.
 * La marca va en hora de Chile (America/Santiago), igual que fmtRevision
 * del plan familiar en web/js/plan.js. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { fechaGeneracion } from '../../web/js/lista.js';

describe('fechaGeneracion', () => {
  test('marca la fecha y la hora de Chile', () => {
    const texto = fechaGeneracion(new Date('2026-02-15T12:00:00Z'));
    assert.ok(texto.includes('febrero'), texto);
    assert.ok(texto.includes('2026'), texto);
    assert.match(texto, /\d{1,2}:\d{2}/, texto); // la hora con minutos
  });

  test('usa America/Santiago y no UTC', () => {
    // 02:00 UTC del 1 de marzo son las 23:00 del 28 de febrero en Santiago (UTC-3, horario de verano).
    const texto = fechaGeneracion(new Date('2026-03-01T02:00:00Z'));
    assert.ok(texto.includes('febrero'), texto);
    assert.ok(!texto.includes('marzo'), texto);
  });
});
