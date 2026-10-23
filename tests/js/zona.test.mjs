/* Pruebas de las funciones puras de web/js/views/zona.js con node:test (QA-54):
 * guidanceFor, statusText, dayStrip, officialBlock y placeBody producen el texto
 * que una persona lee en una emergencia. zona.js toca `window` al cargar (detección
 * de speechSynthesis) y ui.js, que importa en cadena, registra un listener `online`
 * a nivel de módulo, así que se importa con un global mínimo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} }; // ui.js se suscribe a «online» al importarse
const {
  GUIDANCE, OLDER_GUIDANCE, STATUS, URGENT_TEXT,
  dayStrip, guidanceFor, loadTemporada, officialBlock, placeBody, placeCard, statusText,
  weekLine, whyDangerous,
} = await import('../../web/js/views/zona.js');
const { digest, snapshot } = await import('../../web/js/cambios.js');

const STATUSES = ['urgente', 'aviso', 'riesgo', 'tranquilo'];

describe('guidanceFor', () => {
  test('cada estado devuelve una lista no vacía de pasos en texto', () => {
    for (const s of STATUSES) {
      const steps = guidanceFor(s, false);
      assert.ok(Array.isArray(steps) && steps.length > 0, s);
      for (const step of steps) assert.equal(typeof step, 'string');
    }
  });
  test('con persona mayor, su paso va primero y se conservan los demás', () => {
    for (const s of STATUSES) {
      const steps = guidanceFor(s, true);
      assert.equal(steps[0], OLDER_GUIDANCE[s], s);
      assert.equal(steps.length, GUIDANCE[s].length + 1, s);
      assert.deepEqual(steps.slice(1), GUIDANCE[s], s);
    }
  });
  test('estado desconocido no revienta sin persona mayor (devuelve undefined)', () => {
    // Comportamiento actual: GUIDANCE[otro] es undefined; con olderAdult sí lanza
    // (spread sobre undefined). Se prueba lo real, no lo ideal.
    assert.equal(guidanceFor('inexistente', false), undefined);
    assert.throws(() => guidanceFor('inexistente', true), TypeError);
  });
});

describe('statusText', () => {
  test('cada estado devuelve una frase no vacía', () => {
    for (const s of STATUSES) {
      const text = statusText(s);
      assert.equal(typeof text, 'string');
      assert.ok(text.length > 10, s);
    }
  });
  test('urgente usa la causa cuando viene', () => {
    assert.equal(statusText('urgente', { conaf: true, satelite: true }), URGENT_TEXT.ambos);
    assert.equal(statusText('urgente', { conaf: true }), URGENT_TEXT.conaf);
    assert.equal(statusText('urgente', { persona_mayor: true }), URGENT_TEXT.persona_mayor);
    assert.equal(statusText('urgente', { satelite: true }), URGENT_TEXT.satelite);
    assert.equal(statusText('urgente'), URGENT_TEXT.satelite); // resúmenes antiguos sin causa
  });
  test('los estados no urgentes ignoran la causa', () => {
    assert.equal(statusText('tranquilo', { conaf: true }), STATUS.tranquilo.text);
  });
});

describe('dayStrip', () => {
  const day = (i, extra = {}) => ({
    date: `2026-10-${String(20 + i).padStart(2, '0')}`, level: 'alto',
    tmax: 32, rhmin: 18, windmax: 25, ...extra,
  });
  test('7 días de riesgo producen 7 celdas con su explicación', () => {
    const out = String(dayStrip(Array.from({ length: 7 }, (_, i) => day(i))));
    assert.equal((out.match(/day-cell/g) || []).length, 7);
    assert.ok(out.includes('peligro alto'));
    assert.ok(out.includes('data-daytip'));
  });
  test('más de 7 días se recorta a 7', () => {
    const out = String(dayStrip(Array.from({ length: 9 }, (_, i) => day(i))));
    assert.equal((out.match(/day-cell/g) || []).length, 7);
  });
  test('lista vacía o ausente muestra el aviso y no rompe', () => {
    for (const out of [String(dayStrip([])), String(dayStrip(null)), String(dayStrip())]) {
      assert.ok(out.includes('aparecerá pronto'));
      assert.ok(!out.includes('day-cell'));
    }
  });
  test('Botón Rojo de CONAF se menciona en el tip y para el lector de pantalla', () => {
    const out = String(dayStrip([day(0, { boton_rojo_hours: 4 })]));
    assert.ok(out.includes('Botón Rojo'));
    assert.ok(out.includes('br-mark'));
  });
});

describe('officialBlock', () => {
  test('sin incendio ni fuente no lanza y sigue apuntando a SENAPRED', () => {
    const out = String(officialBlock(null));
    assert.ok(out.includes('SENAPRED'));
    assert.ok(out.includes('senapred.cl/alertas'));
    assert.ok(!out.includes('CONAF:'), 'sin oficial no hay línea de CONAF');
  });
  test('con incendio oficial incluye nombre, estado y origen', () => {
    const out = String(officialBlock(
      { name: 'Las Trancas', status_raw: 'EN CURSO', started_at: '2026-10-19T15:00:00Z' },
      { url: 'https://www.conaf.cl/incendios/', name: 'CONAF' },
    ));
    assert.ok(out.includes('Las Trancas'));
    assert.ok(out.includes('en curso'), 'el estado se muestra en minúsculas');
    assert.ok(out.includes('Fuente:') && out.includes('https://www.conaf.cl/incendios/'));
  });
  test('escapa el nombre del incendio', () => {
    const out = String(officialBlock({ name: '<b>x</b>', started_at: '2026-10-19T15:00:00Z' }));
    assert.ok(out.includes('&lt;b&gt;x&lt;/b&gt;'));
    assert.ok(!out.includes('<b>x</b>'));
  });
});

describe('placeBody', () => {
  test('sin resumen no afirma calma: muestra «sin hora de actualización» (FIX-51)', () => {
    const out = String(placeBody({ name: 'Mi casa', radius_km: 5 }, null));
    assert.ok(out.includes('Sin hora de actualización'));
    assert.ok(!out.includes('Sin calor'), 'un fallo de consulta no puede leerse como «no hay fuego»');
    assert.ok(out.includes('radar'), 'incluye el radar SVG');
  });
  test('con resumen y data_as_of sí dice «sin calor»', () => {
    const out = String(placeBody({ name: 'Mi casa', radius_km: 5 }, { data_as_of: '2026-10-20T12:00:00Z' }));
    assert.ok(out.includes('Sin calor'));
    assert.ok(out.includes('10 km'), 'el barrido sin calor es a 2× el radio');
  });
  test('incluye el punto de calor más cercano con distancia y antigüedad', () => {
    const out = String(placeBody({ name: 'Casa', radius_km: 5 }, {
      nearby: [{ distance_km: 1.2, bearing_deg: 90, direction: 'E', satellite: 'VIIRS', observed_at: '2026-10-19T12:00:00Z', inside_radius: true, reliable: true }],
    }));
    assert.ok(out.includes('Un punto de calor') || out.includes('punto'));
    assert.ok(out.includes('1,2 km'));
  });
  test('escapa HTML en los campos interpolados', () => {
    const out = String(placeBody({ name: '<b>x</b>', radius_km: 5 }, {
      nearby: [{ distance_km: 1.2, bearing_deg: 0, direction: 'N', satellite: '<b>x</b>', observed_at: '2026-10-19T12:00:00Z', inside_radius: true, reliable: true }],
    }));
    assert.ok(!out.includes('<b>x</b>'), 'ni el nombre ni el satélite entran como HTML');
    assert.ok(out.includes('&lt;b&gt;x&lt;/b&gt;'));
    // placeBody no muestra place.name: el nombre lo renderiza la tarjeta (placeCard).
  });
});

/* OFI-30: la tarjeta muestra lo que pasó la temporada pasada en la comuna del lugar.
 * El fixture replica la forma real de web/data/temporada-2526.json: `comunas` es una
 * lista de objetos con `code` numérico, `incendios` y `hectareas`. */
describe('placeCard · temporada 2025-26', () => {
  const place = { id: 'p1', name: 'Mi casa', radius_km: 5, comuna: { code: 7101, name: 'Talca' } };
  const summary = { status: 'tranquilo' };
  const temporada = {
    temporada: '2025-2026',
    source: 'https://raw.githubusercontent.com/deigeprif/public/main/reporte/incendios_totales_25_26.csv',
    comunas: [
      { code: 7101, name: 'Talca', region: 'Maule', incendios: 42, hectareas: 1234.5, mes_peak: '2026-01', max_ha: 800 },
    ],
  };

  test('con la comuna en el archivo muestra incendios y hectáreas con su fuente', () => {
    const out = String(placeCard(place, summary, null, temporada));
    assert.ok(out.includes('Temporada 2025-26'));
    assert.ok(out.includes('42 incendios'));
    assert.ok(out.includes('1.234,5 ha'));
    assert.ok(out.includes('CONAF GEPRIF'));
    assert.ok(out.includes('no es el pronóstico de hoy'));
  });
  test('comuna ausente del archivo no muestra el bloque', () => {
    const out = String(placeCard({ ...place, comuna: { code: 9999, name: 'Inexistente' } }, summary, null, temporada));
    assert.ok(!out.includes('Temporada 2025-26'));
    assert.ok(out.includes('place-card'), 'la tarjeta se pinta igual');
  });
  test('lugar sin comuna conocida no muestra el bloque', () => {
    const out = String(placeCard({ ...place, comuna: null }, summary, null, temporada));
    assert.ok(!out.includes('Temporada 2025-26'));
  });
  test('con la carga fallida (null) la tarjeta se pinta igual que hoy', () => {
    const conDatos = String(placeCard(place, summary, null, temporada));
    const sinDatos = String(placeCard(place, summary, null, null));
    assert.ok(!sinDatos.includes('Temporada 2025-26'));
    assert.ok(sinDatos.includes('place-card'));
    assert.notEqual(conDatos, sinDatos, 'solo cambia el bloque de temporada');
  });
  test('el cargador nunca lanza: fetch que falla devuelve null', async () => {
    const orig = globalThis.fetch;
    globalThis.fetch = () => Promise.reject(new Error('sin red'));
    try {
      assert.equal(await loadTemporada(), null);
    } finally {
      globalThis.fetch = orig;
    }
  });
});

// MZ-03: la frase «por qué es peligroso» sin inventar valores faltantes.
describe('whyDangerous (MZ-03)', () => {
  test('día completo con Botón Rojo', () => {
    const t = whyDangerous({ level: 'alto', tmax: 34, rhmin: 18, windmax: 30, boton_rojo_hours: 6 });
    assert.match(t, /34 °C.*humedad 18 %.*viento de 30 km\/h/s);
    assert.match(t, /Botón Rojo/);
    assert.match(t, /no significa que haya fuego/);
  });
  test('sin viento omite esa parte y no escribe null ni undefined', () => {
    const t = whyDangerous({ level: 'moderado', tmax: 30, rhmin: 40 });
    assert.match(t, /30 °C/);
    assert.doesNotMatch(t, /viento|null|undefined/);
  });
  test('rhmin en 0 es un valor válido', () => {
    assert.match(whyDangerous({ level: 'alto', rhmin: 0 }), /humedad 0 %/);
  });
  test('sin nivel o sin día devuelve cadena vacía', () => {
    assert.equal(whyDangerous(undefined), '');
    assert.equal(whyDangerous({ tmax: 30 }), '');
  });
});

// RISK-22: la frase de pronóstico de la semana pasada.
describe('weekLine (RISK-22)', () => {
  test('sin trend, sin filas o todo sin_anterior → vacío', () => {
    assert.equal(weekLine(null), '');
    assert.equal(weekLine({ rows: [] }), '');
    assert.equal(weekLine({ rows: [{ change: 'sin_anterior' }, { change: 'sin_anterior' }] }), '');
  });
  test('con subidas y bajas menciona los conteos y es pronóstico, no hecho', () => {
    const t = weekLine({ rows: [{ change: 'sube' }], summary: { sube: 2, baja: 1, igual: 2, sin_anterior: 0 } });
    assert.match(t, /subió en 2/);
    assert.match(t, /bajó en 1/);
    assert.doesNotMatch(t, /hubo|habrá/i);
  });
  test('con filas mixtas y sin summary no revienta', () => {
    const t = weekLine({ rows: [{ change: 'igual' }] });
    assert.match(t, /se mantiene igual/);
  });
});

// MZ-05: snapshot y digest de «Desde tu última visita».
describe('cambios · snapshot/digest (MZ-05)', () => {
  const place = { id: 'c1', comuna: { code: 7301, name: 'Talca' } };
  const summaries = (level) => ({ c1: { nearby: [{ id: 'o1', distance_km: 8 }], risk_days: [{ level }] } });
  test('primera visita: sin frases', () => {
    const ahora = snapshot({ places: [place], summaries: summaries('alto'), now: '2026-10-20T12:00:00Z' });
    assert.deepEqual(digest(null, ahora), { dias: 0, frases: [] });
  });
  test('foco nuevo, riesgo que sube y avisos que desaparecen', () => {
    const antes = { at: '2026-10-18T12:00:00Z', focos: [], riesgo: { 7301: 'moderado' }, comunas: { 7301: 'Talca' }, avisos: 2 };
    const ahora = snapshot({ places: [place], summaries: summaries('alto'), avisos: 0, now: '2026-10-21T12:00:00Z' });
    const d = digest(antes, ahora);
    assert.equal(d.dias, 3);
    assert.ok(d.frases.some((f) => /foco nuevo a menos de 8 km/.test(f)));
    assert.ok(d.frases.some((f) => /El riesgo en Talca pasó de moderado a alto/.test(f)));
    assert.ok(d.frases.some((f) => /Ya no hay avisos/.test(f)));
  });
  test('snapshot corrupto no rompe y nombre de comuna llega crudo (la vista escapa)', () => {
    assert.deepEqual(digest({ at: 'no es fecha' }, snapshot({ places: [] })), { dias: 0, frases: [] });
    const antes = { at: '2026-10-19T12:00:00Z', focos: [], riesgo: { 1: 'bajo' }, comunas: { 1: '<b>x</b>' }, avisos: 0 };
    const ahora = { at: '2026-10-20T12:00:00Z', focos: [], riesgo: { 1: 'alto' }, comunas: { 1: '<b>x</b>' }, avisos: 0 };
    const d = digest(antes, ahora);
    assert.ok(d.frases.some((f) => f.includes('<b>x</b>')));
  });
});
