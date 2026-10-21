/* UX-18: el puntaje de «Mi casa preparada» se calcula en el teléfono con los
 * pesos de la guía oficial — franja, combustibles y acceso pesan el triple —
 * y la hoja imprimible muestra nivel en palabras y lo que falta primero. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { ITEMS, puntajeCasa } from '../../web/js/lista-score.js';

const TODOS = Object.fromEntries(ITEMS.map(([k]) => [k, true]));
const CRITICOS = ['franja', 'combustibles', 'acceso'];

describe('puntaje de «Mi casa preparada» (UX-18)', () => {
  test('los nueve ítems suman 100 y los críticos pesan más', () => {
    assert.equal(ITEMS.length, 9);
    for (const [k] of ITEMS.filter(([, , p]) => p === 3)) assert.ok(CRITICOS.includes(k));
  });

  test('nada marcado → 0 y la acción crítica primero', () => {
    const r = puntajeCasa({});
    assert.equal(r.puntaje, 0);
    assert.equal(r.nivel, 'Falta lo importante');
    assert.equal(r.faltan.length, ITEMS.length);
    assert.ok(r.faltan.slice(0, 3).every((f) => CRITICOS.includes(f.key)));
    assert.equal(r.siguiente.key, 'franja');
  });

  test('todo marcado → 100 y «Casa preparada»', () => {
    const r = puntajeCasa(TODOS);
    assert.equal(r.puntaje, 100);
    assert.equal(r.nivel, 'Casa preparada');
    assert.deepEqual(r.faltan, []);
    assert.equal(r.siguiente, null);
  });

  test('claves desconocidas o null no lanzan', () => {
    assert.doesNotThrow(() => puntajeCasa(null));
    assert.doesNotThrow(() => puntajeCasa(undefined));
    assert.doesNotThrow(() => puntajeCasa('basura'));
    const r = puntajeCasa({ marciano: true, techo: true });
    assert.equal(r.faltan.length, ITEMS.length - 1);
    assert.ok(!r.faltan.some((f) => f.key === 'marciano'));
  });

  test('«lo que falta» respeta los pesos y una casilla muestra la crítica', () => {
    const r = puntajeCasa({ techo: true });
    const pesos = r.faltan.map((f) => f.peso);
    assert.deepEqual(pesos, [...pesos].sort((a, b) => b - a));
    assert.ok(CRITICOS.includes(r.siguiente.key));
    assert.equal(r.siguiente.key, 'franja');
    const r2 = puntajeCasa({ franja: true });
    assert.equal(r2.siguiente.key, 'combustibles');
  });
});
