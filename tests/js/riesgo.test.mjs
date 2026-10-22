/* Pruebas de forecastAge en web/js/views/riesgo.js con node:test, sin navegador.
 * riesgo.js importa ui.js, que registra un listener «online» al cargar: se usa un stub,
 * igual que en zona.test.mjs (index.js junta todas las suites en un proceso). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { forecastAge, forecastNote, filtrarPorRegion, resumenPorNivel } = await import('../../web/js/views/riesgo.js');

const NOW = Date.parse('2026-10-21T00:00:00Z');
const hoursAgo = (h) => new Date(NOW - h * 3600000).toISOString();

describe('forecastAge', () => {
  test('un pronóstico de hace 1 h está al día', () => {
    assert.deepEqual(forecastAge(hoursAgo(1), NOW), { horas: 1, nivel: 'al-dia' });
  });
  test('uno de hace 7 h quedó atrasado', () => {
    assert.equal(forecastAge(hoursAgo(7), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(7), NOW).horas, 7);
  });
  test('uno de hace 30 h cuenta como sin dato', () => {
    assert.equal(forecastAge(hoursAgo(30), NOW).nivel, 'sin-dato');
  });
  test('sin computed_at no hay dato', () => {
    assert.equal(forecastAge(undefined, NOW).nivel, 'sin-dato');
    assert.equal(forecastAge(null, NOW).nivel, 'sin-dato');
    assert.equal(forecastAge('', NOW).nivel, 'sin-dato');
  });
  test('una fecha ilegible no lanza y cuenta como sin dato', () => {
    assert.equal(forecastAge('no-es-fecha', NOW).nivel, 'sin-dato');
    assert.equal(forecastAge('2026-13-99T99:99', NOW).nivel, 'sin-dato');
  });
  test('los bordes son exactos: < 6 h al día, 6–24 h atrasado, > 24 h sin dato', () => {
    assert.equal(forecastAge(hoursAgo(5.99), NOW).nivel, 'al-dia');
    assert.equal(forecastAge(hoursAgo(6), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(24), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(24.01), NOW).nivel, 'sin-dato');
  });
  test('una fecha en el futuro no da horas negativas', () => {
    assert.deepEqual(forecastAge(new Date(NOW + 3600000).toISOString(), NOW), { horas: 0, nivel: 'al-dia' });
  });
  test('una fecha ISO sin Z se lee como UTC', () => {
    assert.equal(forecastAge('2026-10-20T23:00:00', NOW).nivel, 'al-dia');
  });
});

describe('forecastNote', () => {
  test('con más de 24 h dice «Sin dato de hoy» y no lo presenta como el de hoy', () => {
    const out = String(forecastNote(hoursAgo(30), NOW));
    assert.match(out, /Sin dato de hoy/);
    assert.match(out, /callout-warn/);
    assert.match(out, /últimos calculados/);
    assert.match(out, /no ser el peligro de hoy/);
  });
  test('sin fecha también dice «Sin dato de hoy»', () => {
    assert.match(String(forecastNote(undefined, NOW)), /Sin dato de hoy/);
  });
  test('un pronóstico al día no lleva el aviso de sin dato', () => {
    const out = String(forecastNote(hoursAgo(1), NOW));
    assert.doesNotMatch(out, /Sin dato de hoy/);
    assert.match(out, /Pronóstico calculado/);
  });
});

/* Fixture del ranking regional (RIESGO-102): 4 comunas en dos regiones, con la misma
 * forma que arma load() — code + datos de /api/risk + la ficha del comunas-index. */
const RANKED = [
  { code: 7101, level: 'alto', score: 80, comuna: { name: 'Talca', region: 'Maule' } },
  { code: 7301, level: 'moderado', score: 50, comuna: { name: 'Curicó', region: 'Maule' } },
  { code: 8101, level: 'extremo', score: 95, comuna: { name: 'Concepción', region: 'Biobío' } },
  { code: 8301, level: 'bajo', score: 10, comuna: { name: 'Los Ángeles', region: 'Biobío' } },
];

describe('filtrarPorRegion', () => {
  test('una región deja solo sus comunas, en el orden del ranking', () => {
    const maule = filtrarPorRegion(RANKED, 'Maule');
    assert.deepEqual(maule.map((r) => r.comuna.name), ['Talca', 'Curicó']);
  });
  test('sin región (Todo Chile) devuelve el ranking completo', () => {
    assert.equal(filtrarPorRegion(RANKED, null).length, 4);
    assert.equal(filtrarPorRegion(RANKED, '').length, 4);
    assert.equal(filtrarPorRegion(RANKED, undefined).length, 4);
  });
  test('una región sin comunas devuelve lista vacía', () => {
    assert.deepEqual(filtrarPorRegion(RANKED, 'Aysén'), []);
  });
  test('una fila sin ficha de comuna no rompe el filtro', () => {
    const suelta = [{ code: 9999, level: 'bajo', comuna: null }];
    assert.equal(filtrarPorRegion([...RANKED, ...suelta], 'Maule').length, 2);
    assert.equal(filtrarPorRegion([...RANKED, ...suelta], null).length, 5);
  });
});

describe('resumenPorNivel', () => {
  test('cuenta cada nivel y el total', () => {
    assert.deepEqual(resumenPorNivel(RANKED), { total: 4, extremo: 1, alto: 1, moderado: 1, bajo: 1 });
    assert.deepEqual(resumenPorNivel(filtrarPorRegion(RANKED, 'Maule')), { total: 2, extremo: 0, alto: 1, moderado: 1, bajo: 0 });
  });
  test('lista vacía da todo en cero', () => {
    assert.deepEqual(resumenPorNivel([]), { total: 0, extremo: 0, alto: 0, moderado: 0, bajo: 0 });
    assert.deepEqual(resumenPorNivel(null), { total: 0, extremo: 0, alto: 0, moderado: 0, bajo: 0 });
  });
  test('un nivel desconocido no se inventa: no entra al conteo', () => {
    const raro = [{ code: 1, level: 'inventado', comuna: { name: 'X', region: 'Maule' } }];
    assert.deepEqual(resumenPorNivel(raro), { total: 1, extremo: 0, alto: 0, moderado: 0, bajo: 0 });
  });
});
