/* Pruebas de web/js/reportes.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { STATUS, caducado, descartar, guardar, latest, line, marcarEnviado, pendientes, testigos } from '../../web/js/reportes.js';

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

describe('testigos', () => {
  test('sin corroboraciones no hay etiqueta', () => {
    assert.equal(testigos({ ...base }), '');
    assert.equal(testigos({ ...base, corroboraciones: 0 }), '');
    assert.equal(testigos(null), '');
  });
  test('cuenta el primer aviso más las corroboraciones y aclara que no es oficial', () => {
    const text = testigos({ ...base, corroboraciones: 1 });
    assert.ok(text.includes('2 vecinos lo vieron'));
    assert.ok(text.includes('no es una verificación oficial'));
    assert.ok(testigos({ ...base, corroboraciones: 4 }).includes('5 vecinos lo vieron'));
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

describe('cola sin conexión (brasa:outbox)', () => {
  // localStorage de mentira, instalado por test y restaurado al salir (otras suites del mismo
  // proceso instalan el suyo; ver api.test.mjs).
  const withOutbox = (fn) => {
    const mem = new Map();
    globalThis.localStorage = {
      getItem: (k) => (mem.has(k) ? mem.get(k) : null),
      setItem: (k, v) => mem.set(k, String(v)),
      removeItem: (k) => mem.delete(k),
    };
    const prev = globalThis.localStorage;
    try { fn(mem); } finally {
      if (prev === undefined) delete globalThis.localStorage; else globalThis.localStorage = prev;
    }
  };
  const entry = (id, hoursAgo = 0) => ({
    id, kind: 'humo', lat: -35.427, lon: -71.655, description: `desc ${id}`,
    created_at: new Date(T0 - hoursAgo * 3600000).toISOString(),
  });
  const stored = (mem) => JSON.parse(mem.get('brasa:outbox') || '[]');

  test('guardar escribe en brasa:outbox con id y created_at propios', () => withOutbox((mem) => {
    const item = guardar({ kind: 'llamas', lat: -35.4, lon: -71.6, description: 'columna blanca' });
    assert.ok(item.id);
    const [saved] = stored(mem);
    assert.equal(saved.id, item.id);
    assert.equal(saved.kind, 'llamas');
    assert.equal(saved.lat, -35.4);
    assert.ok(saved.created_at);
  }));

  test('pendientes sale de la más vieja a la más nueva', () => withOutbox(() => {
    guardar(entry('viejo'));
    guardar(entry('nuevo'));
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['viejo', 'nuevo']);
  }));

  test('tope de 5: al superar, se descarta el más viejo', () => withOutbox(() => {
    for (let i = 0; i < 7; i++) guardar(entry(`q${i}`));
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['q2', 'q3', 'q4', 'q5', 'q6']);
  }));

  test('a las 24 h vencen y salen de la cola', () => withOutbox((mem) => {
    guardar(entry('fresca'));
    guardar(entry('vencida', 25));
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['fresca']);
    assert.deepEqual(stored(mem).map((e) => e.id), ['fresca']);
  }));

  test('guardar con un id ya en cola no duplica', () => withOutbox(() => {
    guardar(entry('mismo'));
    guardar({ ...entry('mismo'), description: 'nueva desc' });
    assert.equal(pendientes(T0).length, 1);
    assert.equal(pendientes(T0)[0].description, 'nueva desc');
  }));

  test('un envío exitoso (marcarEnviado) limpia la entrada', () => withOutbox((mem) => {
    guardar(entry('enviada'));
    marcarEnviado('enviada');
    assert.deepEqual(pendientes(T0), []);
    assert.deepEqual(stored(mem), []);
  }));

  test('descartar la saca sin enviar', () => withOutbox(() => {
    guardar(entry('a'));
    guardar(entry('b'));
    descartar('a');
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['b']);
  }));
});
