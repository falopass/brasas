/* Pruebas de web/js/capas.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { CAPAS, capasFromUrl, capasToUrl, decimatePoints, senapredPorComuna, toggleCapa } from '../../web/js/capas.js';

const BASE = { focos: true, incendios: true, risk: false, aire: false, rain: false, scars: false, reports: true, places: true, hulls: false, lightning: false };
const TODAS_OFF = Object.fromEntries(CAPAS.map((c) => [c.key, false]));

describe('toggle de capas (MAPA-01)', () => {
  test('apaga una capa sin mutar el estado anterior', () => {
    const next = toggleCapa(BASE, 'focos', false);
    assert.equal(next.focos, false);
    assert.equal(BASE.focos, true);
    assert.equal(next.incendios, true);
  });
  test('enciende una capa apagada', () => {
    assert.equal(toggleCapa(BASE, 'aire', true).aire, true);
  });
  test('peligro y lluvia son excluyentes (dos coropletas se taparían)', () => {
    const s = toggleCapa({ ...BASE, rain: true }, 'risk', true);
    assert.equal(s.risk, true);
    assert.equal(s.rain, false);
    const r = toggleCapa({ ...BASE, risk: true }, 'rain', true);
    assert.equal(r.rain, true);
    assert.equal(r.risk, false);
  });
});

describe('la URL refleja las capas activas (?capas=)', () => {
  test('capasToUrl lista solo las activas, en el orden fijo del control', () => {
    assert.equal(capasToUrl(BASE), 'focos,incendios,avisos,lugares');
    assert.equal(capasToUrl({ ...BASE, incendios: false, risk: true }), 'focos,riesgo,avisos,lugares');
    assert.equal(capasToUrl({ focos: false, incendios: false, risk: false, aire: false }), '');
  });
  test('capasFromUrl activa solo las capas listadas', () => {
    assert.deepEqual(capasFromUrl('focos,riesgo'), { ...TODAS_OFF, focos: true, risk: true });
    assert.deepEqual(capasFromUrl('focos,riesgo'), Object.fromEntries(CAPAS.map((c) => [c.key, ['focos', 'riesgo'].includes(c.url)])));
  });
  test('un enlace viejo (?capas=focos,riesgo) devuelve lo mismo que antes (MAPA-130)', () => {
    const s = capasFromUrl('focos,riesgo');
    assert.equal(s.focos, true);
    assert.equal(s.incendios, false);
    assert.equal(s.risk, true);
    assert.equal(s.aire, false);
  });
  test('los seis nombres nuevos prenden su capa y apagan las demás', () => {
    assert.deepEqual(capasFromUrl('lluvia,cicatrices,rayos'), { ...TODAS_OFF, rain: true, scars: true, lightning: true });
    assert.deepEqual(capasFromUrl('huellas,avisos,lugares'), { ...TODAS_OFF, hulls: true, reports: true, places: true });
  });
  test('capasToUrl escribe las diez capas activas en el orden del control', () => {
    assert.equal(capasToUrl({ focos: true, incendios: true, risk: true, aire: true, rain: true, scars: true, reports: true, places: true, hulls: true, lightning: true }),
      'focos,incendios,riesgo,aire,lluvia,cicatrices,avisos,lugares,huellas,rayos');
    assert.equal(capasToUrl({ ...TODAS_OFF, lightning: true, focos: true }), 'focos,rayos');
  });
  test('prender lluvia apaga riesgo y viceversa (exclusión del control)', () => {
    const s = toggleCapa({ ...BASE, risk: true }, 'rain', true);
    assert.equal(s.rain, true);
    assert.equal(s.risk, false);
    const r = toggleCapa({ ...BASE, rain: true }, 'risk', true);
    assert.equal(r.risk, true);
    assert.equal(r.rain, false);
  });
  test('sin parámetro: null (se usan los valores por defecto)', () => {
    assert.equal(capasFromUrl(undefined), null);
    assert.equal(capasFromUrl(null), null);
  });
  test('?capas= vacío apaga las diez (se distingue de «sin parámetro»)', () => {
    assert.deepEqual(capasFromUrl(''), TODAS_OFF);
  });
  test('nombres desconocidos y espacios se ignoran', () => {
    assert.deepEqual(capasFromUrl('focos, otra,,aire'), { ...TODAS_OFF, focos: true, aire: true });
  });
  test('un nombre repetido en el parámetro no se cuenta dos veces', () => {
    assert.deepEqual(capasFromUrl('focos,focos'), { ...TODAS_OFF, focos: true });
    assert.equal(capasToUrl(capasFromUrl('focos,focos,aire')), 'focos,aire');
  });
  test('claves y nombres de URL del control son únicos (ningún merge puede duplicar un toggle)', () => {
    assert.equal(new Set(CAPAS.map((c) => c.key)).size, CAPAS.length);
    assert.equal(new Set(CAPAS.map((c) => c.url)).size, CAPAS.length);
  });
  test('ida y vuelta: parse de lo serializado conserva el estado', () => {
    const state = { ...BASE, aire: true, incendios: false, places: false };
    assert.deepEqual(capasFromUrl(capasToUrl(state)), { ...TODAS_OFF, focos: true, aire: true, reports: true });
  });
});

describe('capa de alertas SENAPRED (OFI-207)', () => {
  test('senapred apaga riesgo y lluvia, y ellas la apagan a ella (coropletas excluyentes)', () => {
    const s = toggleCapa({ ...BASE, risk: true, rain: true }, 'senapred', true);
    assert.equal(s.senapred, true);
    assert.equal(s.risk, false);
    assert.equal(s.rain, false);
    assert.equal(toggleCapa({ ...BASE, senapred: true }, 'risk', true).senapred, false);
    assert.equal(toggleCapa({ ...BASE, senapred: true }, 'rain', true).senapred, false);
  });
  test('senapredPorComuna pinta cada comuna con la clase más grave que la nombra', () => {
    const { tipos, porComuna } = senapredPorComuna([
      { tipo: 'amarilla', comunas: [13101, 16101] },
      { tipo: 'roja', comunas: [13101] },
      { tipo: 'temprana_preventiva', comunas: [16101] },
    ]);
    assert.deepEqual(tipos, { 13101: 'roja', 16101: 'amarilla' });
    assert.equal(porComuna[13101].length, 2);
    assert.equal(porComuna[16101].length, 2);
  });
  test('senapredPorComuna: sin territorio no pinta y un tipo desconocido cuenta como «otra»', () => {
    const { tipos } = senapredPorComuna([{ tipo: 'roja', comunas: [] }, { tipo: 'aviso', comunas: [7101] }, { tipo: 'amarilla' }]);
    assert.deepEqual(tipos, { 7101: 'otra' });
    assert.deepEqual(senapredPorComuna(null), { tipos: {}, porComuna: {} });
    assert.deepEqual(senapredPorComuna([]), { tipos: {}, porComuna: {} });
  });
});

describe('agrupación de focos por celda', () => {
  const pt = (lon, lat, properties) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties });
  const fc = {
    type: 'FeatureCollection',
    features: [
      pt(-70.0, -33.0, { id: 1, age_h: 2, frp_mw: 5, reliable: true, sensor: 'VIIRS' }),
      pt(-70.02, -33.01, { id: 2, age_h: 5, frp_mw: 9, reliable: false, sensor: 'ABI' }),
      pt(-75.0, -35.0, { id: 3, age_h: 1, frp_mw: 3, reliable: true, sensor: 'ABI' }),
    ],
  };
  test('zoom lejano agrupa los puntos cercanos y cuenta los miembros', () => {
    const out = decimatePoints(fc, 5);
    assert.equal(out.type, 'FeatureCollection');
    assert.equal(out.features.length, 2);
    const cell = out.features.find((f) => f.properties.count > 1);
    assert.equal(cell.properties.count, 2);
    assert.equal(cell.properties.id, undefined, 'una celda no es una detección: sin id para la ficha');
    // La celda hereda lo más útil: el calor más reciente, el FRP mayor y si algo es confiable.
    assert.equal(cell.properties.age_h, 2);
    assert.equal(cell.properties.frp_mw, 9);
    assert.equal(cell.properties.reliable, true);
    const single = out.features.find((f) => !f.properties.count);
    assert.equal(single.properties.id, 3, 'el punto aislado conserva su id (sigue abriendo su ficha)');
  });
  test('los celdas se ubican en el centroide de sus miembros', () => {
    const out = decimatePoints(fc, 5);
    const cell = out.features.find((f) => f.properties.count > 1);
    const [lon, lat] = cell.geometry.coordinates;
    assert.ok(Math.abs(lon - -70.01) < 0.001 && Math.abs(lat - -33.005) < 0.001);
  });
  test('zoom cercano devuelve la colección intacta', () => {
    assert.equal(decimatePoints(fc, 8), fc);
  });
  test('la celda se ensancha al alejarse (misma vista, más agrupación)', () => {
    const lejos = decimatePoints(fc, 2);
    assert.equal(lejos.features.length, 1);
    assert.equal(lejos.features[0].properties.count, 3);
  });
  test('la suma de los números del mapa es el total de detecciones del panel (MAPA-144)', () => {
    // El mapa cuenta detecciones, igual que la tarjeta «puntos de calor» del panel: agrupar
    // no puede cambiar el total que lee el vecino en ninguno de los zooms.
    for (const zoom of [2, 3, 4, 5, 6]) {
      const suma = decimatePoints(fc, zoom).features.reduce((n, f) => n + (f.properties.count || 1), 0);
      assert.equal(suma, fc.features.length, `zoom ${zoom}: el mapa cuenta ${suma} y el panel ${fc.features.length}`);
    }
  });
});
