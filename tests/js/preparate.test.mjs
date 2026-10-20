/* La hoja A4 de emergencia (/lista.html) debe ser alcanzable desde la interfaz:
 * este test revisa que la vista Prepárate la enlace (REV-11). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { planSheet, planText } from '../../web/js/plan.js';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/preparate.js', import.meta.url)), 'utf8');

describe('enlace a la hoja de emergencia', () => {
  test('la vista Prepárate enlaza a /lista.html', () => {
    assert.ok(SRC.includes('href="/lista.html"'), 'preparate.js debe enlazar a /lista.html');
  });
});

describe('hoja imprimible del plan familiar (UX-41)', () => {
  test('la hoja escapa los valores guardados', () => {
    const sheet = planSheet({ encuentro: '<b>plaza</b>' });
    assert.ok(sheet.includes('&lt;b&gt;plaza&lt;/b&gt;'));
    assert.ok(!sheet.includes('<b>plaza</b>'));
  });
  test('planText incluye los campos y lo marcado en la mochila', () => {
    const t = planText({ ruta1: 'por el cerro' }, { agua: true });
    assert.ok(t.includes('Ruta de salida principal: por el cerro'));
    assert.ok(t.includes('[x] Agua para 2 a 3 días'));
    assert.ok(t.includes('[ ] Copia de llaves'));
  });
});
