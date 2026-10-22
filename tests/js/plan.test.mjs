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

describe('planSheet incluye «Mi casa preparada»', () => {
  test('sin nada guardado salen los 9 ítems sin marcar', () => {
    const sheet = planSheet({}, {});
    assert.ok(sheet.includes('Mi casa preparada'));
    assert.equal(HOME_ITEMS.length, 9);
    for (const [, texto] of HOME_ITEMS) assert.ok(sheet.includes(`[ ] ${texto}`), `sin marcar: ${texto}`);
  });

  test('marca [x] solo lo que está marcado en check:casa', () => {
    const sheet = planSheet({}, { casa: { techo: true } });
    assert.ok(sheet.includes(`[x] ${HOME_ITEMS[0][1]}`));
    assert.equal(sheet.split('[x]').length - 1, 1);
    for (const [, texto] of HOME_ITEMS.slice(1)) assert.ok(sheet.includes(`[ ] ${texto}`), `sin marcar: ${texto}`);
  });

  test('las marcas de la mochila llegan por checks, como antes', () => {
    const sheet = planSheet({}, { agua: true });
    assert.ok(sheet.includes('[x] Agua para 2 a 3 días'));
    assert.ok(sheet.includes('[ ] Alimentos no perecibles'));
  });

  test('un texto con <script> sigue saliendo escapado', () => {
    const sheet = planSheet({ encuentro: '<script>alert(1)</script>' }, { casa: { techo: true } });
    assert.ok(sheet.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
    assert.ok(!sheet.includes('<script>'));
  });

  test('no pinta datos de personas ni la ubicación del lugar', () => {
    const sheet = planSheet({ encuentro: 'Plaza' }, {
      casa: { techo: true }, nombre: 'Ana Pérez', lat: -33.05, lon: -71.4, lugar: { name: 'Parcela Los Aromos' },
    });
    for (const ajeno of ['Ana Pérez', '-33.05', '-71.4', 'Parcela Los Aromos']) assert.ok(!sheet.includes(ajeno), `se filtró: ${ajeno}`);
  });

  test('sin check:casa en localStorage la sección sale completa y no lanza', async () => {
    const guardado = new Map([['brasa:plan', '{}'], ['brasa:check:mochila', '{}']]);
    const hoja = { innerHTML: '' };
    globalThis.localStorage = { getItem: (k) => (guardado.has(k) ? guardado.get(k) : null) };
    globalThis.document = { getElementById: (id) => (id === 'sheet' ? hoja : null) };
    try {
      await import(`../../web/js/plan.js?sin-casa=${Date.now()}`);
      assert.ok(hoja.innerHTML.includes('Mi casa preparada'));
      for (const [, texto] of HOME_ITEMS) assert.ok(hoja.innerHTML.includes(`[ ] ${texto}`), `sin marcar: ${texto}`);
    } finally {
      delete globalThis.localStorage;
      delete globalThis.document;
    }
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
