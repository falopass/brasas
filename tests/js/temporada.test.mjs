/* Pruebas de web/js/views/temporada.js (UX-52): el KPI de Botón Rojo declara el alcance
 * real del dato, la línea de estados desconocidos es opcional, y el estado de falla
 * conserva «Reintentar», los teléfonos y el foco en el selector (revisión sobre el código). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de speak.test.mjs (index.js las junta)
const { regionPropia, render, weekDiff } = await import('../../web/js/views/temporada.js');
const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/temporada.js', import.meta.url)), 'utf8');

const DATA = {
  season: '2025-2026',
  seasons: ['2025-2026', '2024-2025'],
  totals: { n: 3, ha: 10.5, en_combate: 1, controlados: 1, extinguidos: 1 },
  by_region: [],
  by_comuna: [],
  boton_rojo_days: 4,
  source: { name: 'CONAF', url: 'https://conaf.cl' },
  boton_rojo_source: { name: 'CONAF', url: 'https://conaf.cl', note: 'nota' },
  updated_at: '2026-10-20T12:00:00Z',
  not_official: 'no oficial',
};

describe('panorama de la temporada (UX-52)', () => {
  test('el KPI de Botón Rojo declara que solo cubre las últimas dos semanas', () => {
    const out = String(render(DATA));
    assert.ok(out.includes('últimas dos semanas'), 'el subtítulo debe dar el alcance real del dato');
  });
  test('sin unknown_status no se muestra la línea de estados desconocidos', () => {
    assert.ok(!String(render(DATA)).includes('no reconoce'));
    assert.ok(!String(render({ ...DATA, unknown_status: { n: 0 } })).includes('no reconoce'));
  });
  test('con unknown_status.n > 0 informa cuántos incendios traen estado desconocido', () => {
    const out = String(render({ ...DATA, unknown_status: { n: 2 } }));
    assert.ok(out.includes('2 incendios del reporte traen un estado que BRASA no reconoce'));
  });
  test('la falla de la consulta deja Reintentar y los teléfonos de emergencia', () => {
    assert.ok(SRC.includes('data-retry') && SRC.includes('>Reintentar<'));
    assert.ok(SRC.includes('tel:130') && SRC.includes('tel:132'));
  });
  test('al repintar el foco vuelve al selector y el cambio se anuncia', () => {
    assert.ok(SRC.includes('preventScroll: true'));
    assert.ok(SRC.includes('aria-live') && SRC.includes('cargada`'));
  });
});

describe('la semana contra la anterior (TEMP-31)', () => {
  const SEMANA = {
    desde: '2026-10-15', hasta: '2026-10-21', incendios: 8, ha: 120.5, dias_con_datos: 4,
    anterior: { desde: '2026-10-08', hasta: '2026-10-14', incendios: 0, ha: 0, dias_con_datos: 0 },
  };

  test('la diferencia se dice en palabras', () => {
    assert.equal(weekDiff(8, 0), '8 más que la semana pasada');
    assert.equal(weekDiff(2, 5), '3 menos que la semana pasada');
    assert.equal(weekDiff(3, 3), 'igual que la semana pasada');
  });

  test('la tarjeta «Esta semana» muestra la cifra, la diferencia y la nota', () => {
    const out = String(render({ ...DATA, semana: SEMANA }));
    assert.ok(out.includes('Esta semana'));
    assert.ok(out.includes('8 incendios informados por CONAF'));
    assert.ok(out.includes('8 más que la semana pasada'));
    assert.ok(out.includes('no es un pronóstico'));
  });

  test('sin bloque semana la tarjeta no aparece', () => {
    assert.ok(!String(render(DATA)).includes('Esta semana'));
    assert.ok(!String(render({ ...DATA, semana: null })).includes('Esta semana'));
  });
});

describe('tu región primero (TEMPORADA-02)', () => {
  const REGIONES = {
    ...DATA,
    totals: { n: 30, ha: 1000, en_combate: 5, controlados: 5, extinguidos: 5 },
    by_region: [
      { region: 'Valparaíso', n: 20, ha: 600, en_combate: 4 },
      { region: 'Maule', n: 12, ha: 340, en_combate: 1 },
      { region: 'Biobío', n: 8, ha: 60, en_combate: 0 },
    ],
    by_comuna: [],
  };
  const EN_TALCA = [{ id: 'p1', name: 'Casa', comuna: { name: 'Talca', region: 'Maule', region_code: 7 } }];

  test('con un lugar en Talca, Maule va primero y dice «Tu región»', () => {
    const out = String(render(REGIONES, EN_TALCA));
    assert.equal(regionPropia(EN_TALCA), 'Maule');
    assert.ok(out.indexOf('Maule') < out.indexOf('Valparaíso'), 'Maule debe encabezar la lista');
    assert.ok(out.includes('Tu región'));
    assert.ok(out.includes('aria-label="Maule, tu región: 12 incendios, 340 ha, el 34 % de la superficie del país"'));
    assert.ok(out.includes('34 % de la superficie del país'));
  });

  test('sin lugares guardados la lista queda como hoy', () => {
    const out = String(render(REGIONES));
    assert.ok(out.indexOf('Valparaíso') < out.indexOf('Maule'));
    assert.ok(!out.includes('Tu región'));
    assert.ok(!out.includes('de la superficie del país'));
  });

  test('el porcentaje se calcula sobre totals.ha y sin superficie no dice «0 %»', () => {
    assert.ok(String(render(REGIONES, EN_TALCA)).includes('34 % de la superficie del país'));
    const sinHa = { ...REGIONES, totals: { ...REGIONES.totals, ha: 0 } };
    const out = String(render(sinHa, EN_TALCA));
    assert.ok(out.includes('sin superficie informada'));
    assert.ok(!out.includes('0 % de la superficie'));
  });

  test('un lugar sin comuna no rompe la vista ni reordena', () => {
    const sinComuna = [{ id: 'p1', name: 'Casa' }, { id: 'p2', name: 'Otra', comuna: null }, { id: 'p3', comuna: { name: 'Talca' } }];
    assert.equal(regionPropia(sinComuna), '');
    const out = String(render(REGIONES, sinComuna));
    assert.ok(out.indexOf('Valparaíso') < out.indexOf('Maule'));
    assert.ok(!out.includes('Tu región'));
  });

  test('el nombre de la región sale escapado, también en el aria-label', () => {
    const malo = '<img src=x onerror=alert(1)>';
    const out = String(render({ ...REGIONES, by_region: [{ region: malo, n: 1, ha: 10, en_combate: 0 }] }, [{ comuna: { region: malo } }]));
    assert.ok(!out.includes('<img'));
    assert.ok(out.includes('&lt;img'));
    assert.ok(out.includes('aria-label="&lt;img'));
  });
});
