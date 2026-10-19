/* Pruebas de web/js/reportes.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { STATUS, caducado, latest, line } from '../../web/js/reportes.js';

const T0 = new Date('2026-10-19T12:00:00Z').getTime();
const EXPIRED_NOTE = 'Caducó sin revisar: el aviso esperó más tiempo del que el hecho sigue vigente.';
const base = {
  id: 'r1', created_at: '2026-10-19T09:00:00Z', lat: -35.427, lon: -71.655,
  kind: 'humo', kind_label: 'Humo visible', description: '', comuna: 'Talca',
  status: 'no_verificado', moderated_at: null, moderator_note: '', has_photo: false, photo_url: null,
};

describe('STATUS', () => {
  test('etiqueta los tres estados', () => {
    assert.equal(STATUS.no_verificado, 'En revisión');
    assert.equal(STATUS.verificado, 'Verificado');
    assert.equal(STATUS.descartado, 'Descartado');
  });
});

describe('line', () => {
  test('en revisión: tipo, antigüedad, comuna y estado', () => {
    const text = line({ ...base }, T0);
    assert.ok(text.includes('Humo visible'));
    assert.ok(text.includes('hace 3 h'));
    assert.ok(text.includes('Talca'));
    assert.ok(text.endsWith('En revisión'));
  });
  test('verificado con nota del moderador la incluye', () => {
    const text = line({ ...base, status: 'verificado', moderator_note: 'Se ve en el satélite.' }, T0);
    assert.ok(text.includes('Verificado'));
    assert.ok(text.endsWith('Se ve en el satélite.'));
  });
  test('descartado por caducidad muestra el motivo', () => {
    const text = line({ ...base, status: 'descartado', moderator_note: EXPIRED_NOTE }, T0);
    assert.ok(text.includes('Descartado'));
    assert.ok(text.includes('Caducó sin revisar'));
  });
  test('sin comuna usa las coordenadas tal como llegan (ya redondeadas por el servidor)', () => {
    assert.ok(line({ ...base, comuna: null }, T0).includes('-35.427, -71.655'));
  });
});

describe('caducado', () => {
  test('descartado con la nota de caducidad (por prefijo)', () => {
    assert.equal(caducado({ status: 'descartado', moderator_note: EXPIRED_NOTE }), true);
    assert.equal(caducado({ status: 'descartado', moderator_note: 'Caducó sin revisar' }), true);
  });
  test('descartado por otra razón no es caducado', () => {
    assert.equal(caducado({ status: 'descartado', moderator_note: 'Era una nube.' }), false);
    assert.equal(caducado({ status: 'descartado' }), false);
  });
  test('los demás estados no son caducados', () => {
    assert.equal(caducado({ ...base }), false);
    assert.equal(caducado({ ...base, status: 'verificado' }), false);
  });
});

describe('latest', () => {
  test('lista vacía o ausente devuelve lista vacía', () => {
    assert.deepEqual(latest([]), []);
    assert.deepEqual(latest(null), []);
    assert.deepEqual(latest(undefined), []);
  });
  test('se queda con los 5 más recientes', () => {
    const rows = latest(Array.from({ length: 8 }, (_, i) => ({ id: i })));
    assert.equal(rows.length, 5);
    assert.equal(rows.at(-1).id, 4);
  });
});
