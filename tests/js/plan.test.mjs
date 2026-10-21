/* TEST-01: la hoja imprimible del plan familiar arma HTML a mano y su única
 * defensa contra inyección es escapeHtml en web/js/plan.js. Estas pruebas
 * cierran ese contrato: todo valor que escribe la persona sale escapado,
 * y las funciones puras (planText, fmtRevision) cumplen lo suyo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { HOME_ITEMS, PLAN_FIELDS, planSheet, planText, fmtRevision } from '../../web/js/plan.js';

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

describe('planSheet incluye «Mi casa preparada»', () => {
  test('con checks vacíos salen los 9 ítems sin marcar', () => {
    const sheet = planSheet({}, {});
    assert.ok(sheet.includes('Mi casa preparada'));
    assert.equal(HOME_ITEMS.length, 9);
    for (const [, texto] of HOME_ITEMS) assert.ok(sheet.includes(`[ ] ${texto}`));
  });

  test('marca [x] solo lo marcado en check:casa', () => {
    const sheet = planSheet({}, { casa: { techo: true } });
    assert.ok(sheet.includes('[x] Limpié techo y canaletas'));
    for (const [clave, texto] of HOME_ITEMS) {
      if (clave !== 'techo') assert.ok(sheet.includes(`[ ] ${texto}`), `«${clave}» no debería estar marcado`);
    }
  });

  test('un texto guardado con <script> sale escapado', () => {
    const sheet = planSheet({ notas: '<script>alert(1)</script>' }, { casa: { vecinos: true } });
    assert.ok(!sheet.includes('<script>'));
    assert.ok(sheet.includes('[x] Conversé con mis vecinos'));
  });

  test('no incluye datos de personas ni la ubicación del lugar', () => {
    const sheet = planSheet({}, { casa: { techo: true }, lugar: { name: 'Casa de prueba', lat: -33.05, lon: -71.4 } });
    assert.ok(!sheet.includes('Casa de prueba'));
    assert.ok(!sheet.includes('-33.05'));
    assert.ok(!sheet.includes('-71.4'));
  });

  test('sin check:casa la sección sale completa sin marcar y no lanza', () => {
    assert.doesNotThrow(() => planSheet({ encuentro: 'la plaza' }));
    const sheet = planSheet({ encuentro: 'la plaza' });
    for (const [, texto] of HOME_ITEMS) assert.ok(sheet.includes(`[ ] ${texto}`));
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
