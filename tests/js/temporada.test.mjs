/* Pruebas de web/js/views/temporada.js (UX-52): el KPI de Botón Rojo declara el alcance
 * real del dato, la línea de estados desconocidos es opcional, y el estado de falla
 * conserva «Reintentar», los teléfonos y el foco en el selector (revisión sobre el código). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de speak.test.mjs (index.js las junta)
const { render } = await import('../../web/js/views/temporada.js');
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
