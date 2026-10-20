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

describe('puntaje de la mochila y descarga del plan (UX-53)', () => {
  test('la mochila se pinta y se enlaza como lista evaluada', () => {
    assert.match(SRC, /checklist\('mochila', BAG_CHECKLIST, true/, 'la mochila debe evaluarse con puntaje');
    assert.match(SRC, /bindChecklist\(container, 'mochila', BAG_CHECKLIST, true/, 'bindChecklist de la mochila debe recibir scored');
  });
  test('existe el botón «Descargar plan» en la vista', () => {
    assert.ok(SRC.includes('id="download-plan"'), 'preparate.js debe tener el botón de descarga');
    assert.ok(SRC.includes('Descargar plan'), 'el botón debe decir «Descargar plan»');
  });
  test('la descarga arma un archivo .txt y libera el URL', () => {
    assert.ok(SRC.includes('plan-familiar-brasa.txt'), 'el archivo debe llamarse plan-familiar-brasa.txt');
    assert.ok(SRC.includes('createObjectURL') && SRC.includes('revokeObjectURL'), 'debe usar Blob URL y revocarlo');
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
