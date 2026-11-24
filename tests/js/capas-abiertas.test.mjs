/* Pruebas unitarias de PR 7: GWIS WMS (OFI-34), ESA WorldCover 10 m (MAPA-185) y Terreno 3D (MAPA-189). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  GWIS_ATTRIBUTION,
  GWIS_WMS_HOST,
  WMS_LAYERS,
  WORLDCOVER_ATTRIBUTION,
  WORLDCOVER_CLASSES,
  WORLDCOVER_WMS_HOST,
  wmsTileUrl,
} from '../../web/js/gibs.js';
import { CAPAS, COROPLETAS, capasFromUrl, capasToUrl, PRIORIDAD_TOQUE, seleccionarCoropleta, toggleCapa } from '../../web/js/capas.js';
import { AWS_DEM_SOURCE, CONAF_WUI, INFRA_COLORS, INFRA_MINZOOM, terreno3dPermitido } from '../../web/js/map.js';

describe('capas WMS abiertas: GWIS (OFI-34) y ESA WorldCover (MAPA-185)', () => {
  test('GWIS usa MapServer WMS 1.1.1 en EPSG:3857 con STYLES= y TIME solo en ecmwf.ranking', () => {
    const rankUrl = wmsTileUrl(WMS_LAYERS.gwis_ranking, '2026-11-23')[0];
    assert.ok(rankUrl.startsWith(`${GWIS_WMS_HOST}?`));
    assert.ok(rankUrl.includes('VERSION=1.1.1'));
    assert.ok(rankUrl.includes('SRS=EPSG:3857'));
    assert.ok(rankUrl.includes('LAYERS=ecmwf.ranking'));
    assert.ok(rankUrl.includes('STYLES=&'));
    assert.ok(rankUrl.includes('WIDTH=512&HEIGHT=512'));
    assert.ok(rankUrl.includes('BBOX={bbox-epsg-3857}'));
    assert.ok(rankUrl.includes('TIME=2026-11-23'));

    const baUrl = wmsTileUrl(WMS_LAYERS.gwis_ba, '2026-11-23')[0];
    assert.ok(baUrl.includes('LAYERS=nrt.ba.month'));
    assert.ok(baUrl.includes('STYLES=&'));
    assert.ok(!baUrl.includes('TIME='), 'nrt.ba.month es ventana móvil de 30 días, sin TIME');
    assert.match(GWIS_ATTRIBUTION, /CC BY 4\.0/);
  });

  test('ESA WorldCover apunta a TiTiler Terrascope con la capa 2021 v200 y licencia CC BY 4.0', () => {
    const wcUrl = wmsTileUrl(WMS_LAYERS.worldcover)[0];
    assert.ok(wcUrl.startsWith(`${WORLDCOVER_WMS_HOST}?`));
    assert.ok(wcUrl.includes('titiler.terrascope.be/wms'));
    assert.ok(wcUrl.includes('LAYERS=esa-worldcover-map-10m-2021-v2_map'));
    assert.ok(wcUrl.includes('SRS=EPSG:3857'));
    assert.ok(wcUrl.includes('WIDTH=256&HEIGHT=256'));
    assert.ok(!wcUrl.includes('TIME='));
    assert.match(WORLDCOVER_ATTRIBUTION, /ESA WorldCover/);
    assert.match(WORLDCOVER_ATTRIBUTION, /CC BY 4\.0/);
    assert.equal(WORLDCOVER_CLASSES.length, 7);
  });
});

describe('exclusiones mutuas y URL para GWIS, WorldCover y Terreno 3D', () => {
  const todasOff = Object.fromEntries(CAPAS.map((c) => [c.key, false]));

  test('COROPLETAS conserva las tres capas comunales para los radios', () => {
    assert.deepEqual(COROPLETAS, ['risk', 'rain', 'senapred']);
  });

  test('GWIS y las coropletas comunales son mutuamente excluyentes', () => {
    const a = toggleCapa({ ...todasOff, risk: true }, 'gwis_ranking', true);
    assert.equal(a.gwis_ranking, true);
    assert.equal(a.risk, false);

    const b = toggleCapa(a, 'gwis_ba', true);
    assert.equal(b.gwis_ba, true);
    assert.equal(b.gwis_ranking, false);

    const c = seleccionarCoropleta(b, 'senapred');
    assert.equal(c.senapred, true);
    assert.equal(c.gwis_ba, false);
    assert.equal(c.gwis_ranking, false);
  });

  test('capasFromUrl y capasToUrl soportan los nuevos nombres de capa', () => {
    const parsed = capasFromUrl('gwis-peligro,cobertura,terreno3d');
    assert.equal(parsed.gwis_ranking, true);
    assert.equal(parsed.worldcover, true);
    assert.equal(parsed.terreno3d, true);
    assert.equal(capasToUrl(parsed), 'gwis-peligro,cobertura,terreno3d');
  });
});

describe('Terreno 3D (MAPA-189): respaldo AWS y modo ahorro', () => {
  test('AWS_DEM_SOURCE declara formato terrarium z15 y atribución', () => {
    assert.equal(AWS_DEM_SOURCE.type, 'raster-dem');
    assert.equal(AWS_DEM_SOURCE.encoding, 'terrarium');
    assert.equal(AWS_DEM_SOURCE.maxzoom, 15);
    assert.equal(AWS_DEM_SOURCE.tileSize, 256);
    assert.ok(AWS_DEM_SOURCE.tiles[0].includes('s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'));
    assert.match(AWS_DEM_SOURCE.attribution, /AWS Terrain Tiles/);
  });

  test('terreno3dPermitido bloquea auto-activación con saveData o reducedMotion', () => {
    assert.equal(terreno3dPermitido({ saveData: false, reducedMotion: false }), true);
    assert.equal(terreno3dPermitido({ saveData: true, reducedMotion: false }), false);
    assert.equal(terreno3dPermitido({ saveData: false, reducedMotion: true }), false);
  });
});

describe('Zonas de Interfaz Urbano-Forestal CONAF GEPRIF (MAPA-183)', () => {
  const todasOff = Object.fromEntries(CAPAS.map((c) => [c.key, false]));

  test('CONAF_WUI declara URL {z}/{y}/{x}.pbf, sourceLayer union_result_3857 y 4 símbolos oficiales', () => {
    assert.equal(CONAF_WUI.tiles.length, 1);
    assert.ok(CONAF_WUI.tiles[0].includes('riesgo_interfaz_tiled/VectorTileServer/tile/{z}/{y}/{x}.pbf'));
    assert.ok(!CONAF_WUI.tiles[0].includes('{z}/{x}/{y}'), 'ArcGIS VectorTileServer usa orden {z}/{y}/{x}');
    assert.equal(CONAF_WUI.minzoom, 2);
    assert.equal(CONAF_WUI.maxzoom, 15);
    assert.deepEqual(CONAF_WUI.bounds, [-75.3457, -55.964, -66.5444, -17.5544]);
    assert.equal(CONAF_WUI.sourceLayer, 'union_result_3857');
    assert.deepEqual(CONAF_WUI.levels.map((l) => l.symbol), [3, 4, 5, 6]);
    assert.deepEqual(CONAF_WUI.levels.map((l) => l.key), ['bajo', 'medio', 'alto', 'muy_alto']);
    assert.deepEqual(CONAF_WUI.levels.map((l) => l.color), ['#86BABD', '#F1FB7B', '#F7A248', '#F0261C']);
    assert.match(CONAF_WUI.attribution, /CONAF · GEPRIF Zonas de Interfaz/);
    assert.match(CONAF_WUI.attribution, /https:\/\/deigeprif\.com\//);
  });

  test('capasFromUrl y capasToUrl soportan interfaz (wui)', () => {
    const parsed = capasFromUrl('interfaz');
    assert.equal(parsed.wui, true);
    assert.equal(capasToUrl(parsed), 'interfaz');

    const combinado = capasFromUrl('focos,riesgo,interfaz');
    assert.equal(combinado.focos, true);
    assert.equal(combinado.risk, true);
    assert.equal(combinado.wui, true);
    assert.equal(capasToUrl(combinado), 'focos,riesgo,interfaz');
  });

  test('wui no es excluyente con coropletas comunales ni con GWIS', () => {
    assert.ok(!COROPLETAS.includes('wui'));

    const conRiesgo = toggleCapa({ ...todasOff, risk: true }, 'wui', true);
    assert.equal(conRiesgo.risk, true);
    assert.equal(conRiesgo.wui, true);

    const conSenapred = seleccionarCoropleta(conRiesgo, 'senapred');
    assert.equal(conSenapred.senapred, true);
    assert.equal(conSenapred.risk, false);
    assert.equal(conSenapred.wui, true);

    const conGwis = toggleCapa(conSenapred, 'gwis_ranking', true);
    assert.equal(conGwis.gwis_ranking, true);
    assert.equal(conGwis.senapred, false);
    assert.equal(conGwis.wui, true);
  });
});

describe('Infraestructura crítica (MAPA-181)', () => {
  const todasOff = Object.fromEntries(CAPAS.map((c) => [c.key, false]));

  test('CAPAS registra infra: url infraestructura, etiqueta visible y apagada por defecto', () => {
    const capa = CAPAS.find((c) => c.key === 'infra');
    assert.ok(capa, 'CAPAS no tiene la capa infra');
    assert.equal(capa.url, 'infraestructura');
    assert.equal(capa.label, 'Infraestructura crítica');
    assert.equal(capa.on, false, 'la capa de infraestructura crítica va apagada por defecto');
  });

  test('capasFromUrl y capasToUrl soportan infraestructura', () => {
    const parsed = capasFromUrl('infraestructura');
    assert.equal(parsed.infra, true);
    assert.equal(capasToUrl(parsed), 'infraestructura');

    const combinado = capasFromUrl('focos,infraestructura');
    assert.equal(combinado.focos, true);
    assert.equal(combinado.infra, true);
    assert.equal(capasToUrl(combinado), 'focos,infraestructura');
  });

  test('infra no apaga las coropletas comunales ni viceversa', () => {
    assert.ok(!COROPLETAS.includes('infra'));

    const conCoropleta = toggleCapa({ ...todasOff, infra: true }, 'risk', true);
    assert.equal(conCoropleta.risk, true);
    assert.equal(conCoropleta.infra, true);

    const conInfra = toggleCapa(conCoropleta, 'infra', true);
    assert.equal(conInfra.infra, true);
    assert.equal(conInfra.risk, true);

    const conSenapred = seleccionarCoropleta(conInfra, 'senapred');
    assert.equal(conSenapred.senapred, true);
    assert.equal(conSenapred.risk, false);
    assert.equal(conSenapred.infra, true, 'elegir una coropleta comunal no apaga infra');
  });

  test('INFRA_MINZOOM, INFRA_COLORS y prioridad de toque de puntos y líneas', () => {
    assert.equal(INFRA_MINZOOM, 10);
    assert.deepEqual(Object.keys(INFRA_COLORS).sort(), ['b', 'e', 'l', 's', 't']);
    assert.equal(INFRA_COLORS.b, '#c92a2a');
    assert.equal(INFRA_COLORS.s, '#087f5b');
    assert.equal(INFRA_COLORS.e, '#1971c2');
    assert.equal(INFRA_COLORS.t, '#a83cc9');
    assert.equal(INFRA_COLORS.l, '#a83cc9');
    assert.ok(PRIORIDAD_TOQUE['infra-puntos'] < PRIORIDAD_TOQUE['infra-lineas'], 'un punto gana el toque sobre una línea');
  });
});
