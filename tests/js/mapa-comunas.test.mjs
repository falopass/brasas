/* MAPA-143 / PERF-10: la geometría comunal (1,9 MB) no viaja en el primer pintado ni
 * al acercar el mapa sin coropletas. La fuente arranca vacía (`EMPTY`), se descarga una
 * sola vez cuando hace falta (coropleta visible, comuna elegida o fondo sin conexión) y
 * queda cacheada en memoria (`comunasDatos`) para sobrevivir a `setStyle` sin red extra. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/map.js', import.meta.url)), 'utf8');
const STYLE_LOAD = SRC.slice(SRC.indexOf("map.on('style.load'"), SRC.indexOf("map.on('moveend'"));
const MOVEEND = SRC.slice(SRC.indexOf("map.on('moveend'"), SRC.indexOf("map.on('idle'"));
const ON_ERROR = SRC.slice(SRC.indexOf("map.on('error'"), SRC.indexOf('const hoverComuna'));
const ENSURE = SRC.slice(SRC.indexOf('function ensureComunas()'), SRC.indexOf('function applyComunaState()'));
const SHOW = SRC.slice(SRC.indexOf('export function show('), SRC.indexOf('function applyLayerVisibility()'));

describe('polígonos comunales bajo demanda y caché en memoria (MAPA-143 / PERF-10)', () => {
  test('la fuente comunal del estilo arranca vacía', () => {
    assert.match(SRC, /comunas: \{ type: 'geojson', data: EMPTY, promoteId: 'code' \}/, 'comunas.geojson vuelve al estilo inicial');
    assert.doesNotMatch(SRC, /comunas: \{ type: 'geojson', data: '\/web\/data\/comunas\.geojson'/, 'la fuente comunal vuelve a pedir el archivo al crear el mapa');
  });

  test('hacer zoom >= 6 sin coropleta, comuna ni modo offline ya no dispara ensureComunas()', () => {
    assert.doesNotMatch(STYLE_LOAD, /ensureComunas\(\)/, 'style.load no debe pedir comunas incondicionalmente al acercar');
    assert.doesNotMatch(MOVEEND, /if \(map\.getZoom\(\) >= COMUNAS_ZOOM_MIN\) ensureComunas\(\)/, 'moveend no debe pedir comunas solo por zoom >= 6');
    assert.match(MOVEEND, /store\.get\('basemapOffline'\) && map\.getZoom\(\) >= COMUNAS_ZOOM_MIN/, 'moveend solo pide comunas en modo offline con zoom >= 6');
    assert.match(ON_ERROR, /store\.set\('basemapOffline', true\);[\s\S]{0,60}ensureComunas\(\);/, 'el fallo del fondo debe pedir comunas en modo offline (MAPA-184)');
  });

  test('comunasDatos cachea el GeoJSON en memoria y style.load lo reutiliza sin volver a descargar', () => {
    assert.match(SRC, /let comunasDatos = null;/);
    assert.match(SRC, /let comunasPromesa = null;/);
    assert.match(ENSURE, /if \(comunasDatos\) \{[\s\S]{0,120}source\.setData\(comunasDatos\);[\s\S]{0,40}return;/, 'ensureComunas debe reutilizar comunasDatos en memoria');
    assert.match(ENSURE, /comunasPromesa \?\?= fetch\('\/web\/data\/comunas\.geojson'\)/, 'ensureComunas debe coalescer la descarga con comunasPromesa');
    assert.match(ENSURE, /\.catch\(\(\) => \{[\s\S]{0,80}comunasPromesa = null;/, 'un error debe limpiar comunasPromesa para permitir reintento');
    assert.match(STYLE_LOAD, /comunasCargadasEnEstilo = false;/, 'style.load debe marcar que el estilo nuevo necesita volver a inyectar los datos');
    assert.doesNotMatch(STYLE_LOAD, /comunasDatos = null/, 'style.load no debe borrar la caché comunasDatos');
  });

  test('activar una coropleta o seleccionar una comuna dispara ensureComunas()', () => {
    assert.match(SRC, /function comunasNecesarias\(\)[\s\S]{0,260}visibility\['risk-fill'\][\s\S]{0,40}visibility\['rain-fill'\][\s\S]{0,40}visibility\['senapred-fill'\]/);
    assert.match(SRC, /function comunasNecesarias\(\)[\s\S]{0,300}selectedComuna !== null && selectedComuna !== undefined/);
    assert.match(SRC, /function comunasNecesarias\(\)[\s\S]{0,360}store\.get\('basemapOffline'\)/);
    assert.match(SRC, /function applyComunaState\(\)[\s\S]{0,220}if \(comunasNecesarias\(\)\) ensureComunas\(\);/);
    assert.match(SHOW, /COROPLETAS_COMUNAS\.includes\(id\)[\s\S]{0,80}ensureComunas\(\);[\s\S]{0,40}applyComunaState\(\);/);
    assert.match(SRC, /export function selectComuna\(code\)[\s\S]{0,120}if \(code !== null && code !== undefined\) ensureComunas\(\);/);
  });
});
