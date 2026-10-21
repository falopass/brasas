/* MAPA-143: la geometría comunal (1,9 MB) no viaja en el primer pintado del mapa. La
 * fuente arranca vacía y se pide cuando de verdad se usa: los límites comunales (zoom 6),
 * la coropleta de peligro o lluvia, o una comuna elegida. Sin navegador: la prueba viva
 * es la sonda de red en Chromium (el primer #/mapa solo pide regiones.geojson). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/map.js', import.meta.url)), 'utf8');

describe('polígonos comunales bajo demanda (MAPA-143)', () => {
  test('la fuente comunal del estilo arranca vacía', () => {
    assert.match(SRC, /comunas: \{ type: 'geojson', data: EMPTY, promoteId: 'code' \}/, 'la comunas.geojson vuelve al estilo inicial');
    assert.doesNotMatch(SRC, /comunas: \{ type: 'geojson', data: '\/web\/data\/comunas\.geojson'/, 'la fuente comunal vuelve a pedir el archivo al crear el mapa');
  });
  test('se pide una sola vez y solo cuando hace falta', () => {
    assert.match(SRC, /function ensureComunas\(\)[\s\S]{0,220}comunasPedidas = true;[\s\S]{0,80}setData\('\/web\/data\/comunas\.geojson'\)/);
    assert.match(SRC, /if \(map\.getZoom\(\) >= COMUNAS_ZOOM_MIN\) ensureComunas\(\)/, 'los límites comunales deben pedir la geometría');
    assert.match(SRC, /Object\.keys\(riskState \|\| \{\}\)\.length[\s\S]{0,80}ensureComunas\(\)/, 'la coropleta de peligro o lluvia debe pedir la geometría');
    assert.match(SRC, /if \(code !== null && code !== undefined\) ensureComunas\(\)/, 'una comuna elegida debe pedir la geometría');
  });
});
