/* TEST-01: la hoja imprimible del plan familiar arma HTML a mano y su única
 * defensa contra inyección es escapeHtml en web/js/plan.js. Estas pruebas
 * cierran ese contrato: todo valor que escribe la persona sale escapado,
 * y las funciones puras (planText, fmtRevision) cumplen lo suyo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { PLAN_FIELDS, planSheet, planText, fmtRevision } from '../../web/js/plan.js';

describe('planSheet escapa el texto de la persona', () => {
  test('un payload <img onerror> sale escapado y no queda <img', () => {
    const sheet = planSheet({ encuentro: '<img src=x onerror=alert(1)>' });
    assert.ok(sheet.includes('&lt;img src=x onerror=alert(1)&gt;'));
    assert.ok(!sheet.includes('<img'));
  });

  test('cada campo del plan sale escapado en la hoja', () => {
    const malicioso = '<script>alert(1)</script>';
    const plan = Object.fromEntries(PLAN_FIELDS.map(([k]) => [k, malicioso]));
    const sheet = planSheet(plan);
    assert.ok(!sheet.includes(malicioso));
    assert.ok(!sheet.includes('<script>'));
  });

  test('escapa &, <, > y comillas en el texto', () => {
    const sheet = planSheet({ contacto: '"<&>\' Rojo' });
    assert.ok(sheet.includes('&quot;&lt;&amp;&gt;&#39; Rojo'));
    assert.ok(!sheet.includes('"<&>\' Rojo'));
  });
});

describe('planText devuelve texto plano sin escapar', () => {
  test('el valor va crudo (para navigator.share / portapapeles)', () => {
    const t = planText({ ruta1: '<b>por el cerro</b>' });
    assert.ok(t.includes('Ruta de salida principal: <b>por el cerro</b>'));
    assert.ok(!t.includes('&lt;'));
  });

  test('marca [x] solo lo que viene marcado en checks', () => {
    const t = planText({}, { agua: true });
    assert.ok(t.includes('[x] Agua para 2 a 3 días'));
    assert.ok(t.includes('[ ] Alimentos no perecibles'));
  });
});

describe('planSheet sin plan', () => {
  test('deja celdas en blanco y no lanza', () => {
    const sheet = planSheet();
    assert.ok(sheet.includes('class="blank"'));
  });
});

describe('fmtRevision', () => {
  test('una cadena que no es fecha devuelve «sin registro»', () => {
    assert.equal(fmtRevision('no-es-fecha'), 'sin registro');
    assert.equal(fmtRevision(''), 'sin registro');
    assert.equal(fmtRevision(undefined), 'sin registro');
  });

  test('una fecha ISO devuelve texto con su año', () => {
    assert.ok(fmtRevision('2026-10-19T12:00:00Z').includes('2026'));
  });
});
