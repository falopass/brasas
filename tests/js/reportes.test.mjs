/* Pruebas de web/js/reportes.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { STATUS, caducado, cercanos, descartar, distancia, guardar, latest, line, marcarEnviado, pendientes, resumenCercanos, resumenFocos, testigos } from '../../web/js/reportes.js';

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

describe('cercanos', () => {
  const LAT = -35.427; const LON = -71.655;
  const rep = (id, hoursAgo, dLat = 0) => ({
    ...base, id, lat: LAT + dLat, created_at: new Date(T0 - hoursAgo * 3600000).toISOString(),
  });

  test('lista vacía o una consulta que falló (null) devuelve lista vacía', () => {
    assert.deepEqual(cercanos(null, LAT, LON), []);
    assert.deepEqual(cercanos(undefined, LAT, LON), []);
    assert.deepEqual(cercanos([], LAT, LON), []);
    assert.deepEqual(cercanos('error', LAT, LON), []);
  });
  test('coordenadas del punto inválidas devuelven lista vacía', () => {
    assert.deepEqual(cercanos([rep('a', 1)], null, LON), []);
    assert.deepEqual(cercanos([rep('a', 1)], NaN, LON), []);
    assert.deepEqual(cercanos([rep('a', 1)], LAT, 'x'), []);
  });
  test('filtra por radio y ordena del más nuevo al más viejo, con la distancia', () => {
    const rows = cercanos([rep('viejo', 5, 0.005), rep('nuevo', 1, 0.005), rep('lejos', 0.5, 0.03)], LAT, LON);
    assert.deepEqual(rows.map((r) => r.id), ['nuevo', 'viejo']);
    assert.ok(rows.every((r) => Number.isFinite(r.km) && r.km <= 2));
  });
  test('un reporte sin coordenadas válidas se omite', () => {
    const rows = cercanos([rep('ok', 1), { id: 'sin', created_at: base.created_at }, null], LAT, LON);
    assert.deepEqual(rows.map((r) => r.id), ['ok']);
  });
  test('el radio se puede abrir por argumento', () => {
    assert.equal(cercanos([rep('lejos', 1, 0.03)], LAT, LON).length, 0);
    assert.equal(cercanos([rep('lejos', 1, 0.03)], LAT, LON, 5).length, 1);
  });
});

describe('distancia', () => {
  test('metros bajo 1 km, redondeados a centenas', () => {
    assert.equal(distancia(0.66), 'a 700 m');
    assert.equal(distancia(0.04), 'a 100 m');
    assert.equal(distancia(0.96), 'a 1 km');
  });
  test('kilómetros desde 1 km', () => {
    assert.equal(distancia(1.24), 'a 1,2 km');
    assert.equal(distancia(23), 'a 23 km');
  });
  test('distancia ilegible devuelve vacío', () => {
    assert.equal(distancia(NaN), '');
    assert.equal(distancia(-1), '');
  });
});

describe('resumenCercanos', () => {
  const LAT = -35.427; const LON = -71.655;
  // ~700 m al sur del punto (0,0063° de latitud ≈ 700 m).
  const cerca = (extra = {}) => ({ ...base, lat: LAT - 0.0063, lon: LON, created_at: '2026-10-19T11:20:00Z', ...extra });

  test('sin cercanos o sin respuesta devuelve vacío', () => {
    assert.equal(resumenCercanos([], LAT, LON, T0), '');
    assert.equal(resumenCercanos(null, LAT, LON, T0), '');
  });
  test('un aviso: tipo, distancia, lugar, antigüedad y estado entre paréntesis', () => {
    const text = resumenCercanos([cerca()], LAT, LON, T0);
    assert.ok(text.startsWith('Un vecino reportó humo'));
    assert.ok(text.includes('a 700 m'));
    assert.ok(text.includes('en Talca'));
    assert.ok(text.includes('hace 40 min'));
    assert.ok(text.endsWith('(en revisión)'));
  });
  test('un aviso verificado lo dice con la palabra verificado', () => {
    assert.ok(resumenCercanos([cerca({ status: 'verificado' })], LAT, LON, T0).endsWith('(verificado)'));
  });
  test('varios: cuenta a los vecinos y marca los verificados, con el más reciente', () => {
    const rows = [cerca({ status: 'verificado' }), cerca({ id: 'r2', created_at: '2026-10-19T10:00:00Z' })];
    const text = resumenCercanos(rows, LAT, LON, T0);
    assert.ok(text.startsWith('2 vecinos reportaron cerca'));
    assert.ok(text.includes('1 verificado'));
    assert.ok(text.includes('el más reciente: humo a 700 m en Talca hace 40 min'));
  });
});

describe('resumenFocos', () => {
  const LAT = -35.427; const LON = -71.655;
  const foco = (hoursAgo, dLat = 0.01) => ({ lat: LAT + dLat, lon: LON, observed_at: new Date(T0 - hoursAgo * 3600000).toISOString() });

  test('sin puntos o una consulta que falló (null) devuelve vacío', () => {
    assert.equal(resumenFocos(null, LAT, LON, T0), '');
    assert.equal(resumenFocos([], LAT, LON, T0), '');
  });
  test('un punto cerca, en singular', () => {
    const text = resumenFocos([foco(2, 0.005)], LAT, LON, T0);
    assert.ok(text.includes('un punto de calor'));
    assert.ok(text.includes('hace 2 h'));
  });
  test('varios puntos: cuenta y da el más reciente', () => {
    const text = resumenFocos([foco(5, 0.01), foco(1, 0.02)], LAT, LON, T0);
    assert.ok(text.includes('2 puntos de calor'));
    assert.ok(text.includes('hace 1 h'));
  });
  test('un foco fuera del radio no cuenta', () => {
    assert.equal(resumenFocos([foco(1, 0.1)], LAT, LON, T0), '');
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

  test('el sexto reporte devuelve descartados con exactamente el más viejo', () => withOutbox(() => {
    for (let i = 0; i < 5; i++) guardar(entry(`q${i}`));
    const res = guardar(entry('q5'));
    assert.equal(res.id, 'q5');
    assert.equal(res.item.id, 'q5');
    assert.deepEqual(res.descartados, [{ id: 'q0', kind: 'humo', created_at: entry('q0').created_at }]);
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['q1', 'q2', 'q3', 'q4', 'q5']);
  }));

  test('guardar con un id ya en cola no duplica ni descarta', () => withOutbox(() => {
    guardar(entry('mismo'));
    const res = guardar({ ...entry('mismo'), description: 'otra' });
    assert.deepEqual(res.descartados, []);
    assert.equal(pendientes(T0).length, 1);
  }));

  test('un ítem vencido sale por TTL y no aparece como descartado', () => withOutbox(() => {
    guardar(entry('vencida', 25));
    for (let i = 0; i < 4; i++) guardar(entry(`f${i}`));
    assert.deepEqual(pendientes(T0).map((e) => e.id), ['f0', 'f1', 'f2', 'f3']);
    const res = guardar(entry('f4'));
    assert.deepEqual(res.descartados, []);
    assert.equal(pendientes(T0).length, 5);
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
