/* Pruebas de web/js/mapa-offline.js (MAPA-166): la matemática de teselas es pura y
 * el descargador se prueba con fetch y Cache API de mentira, sin red ni navegador. */
import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  armarPaquete, bboxLugar, borrarPaquete, descargarComuna, descargarMapa, descargarPaquete, descargarServiciosPaquete, descargarZonaVisible, GLYPH_RANGOS,
  leerPaquete, metaMapa, metaPaquetes, PARALELO, recursosDescarga, recursosDescargaBbox, serviciosPaquete,
  tesela, tieneMapaGuardado, teselasBbox, teselasLugar, TILEJSON_URL, Z_MAX, Z_MIN,
} from '../../web/js/mapa-offline.js';

const LUGAR = { id: 'p1', name: 'Casa', lat: -33.0, lon: -71.41, radius_km: 2 };
const PLANTILLA = 'https://tiles.openfreemap.org/planet/v1/{z}/{x}/{y}.pbf';

/* localStorage de mentira para la meta (patrón de inventario.test.mjs), restaurado al
 * salir: index.js junta todas las suites en un proceso y un global pegado rompe a las demás. */
const mem = new Map();
const localStorageOriginal = globalThis.localStorage;
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
after(() => {
  if (localStorageOriginal === undefined) delete globalThis.localStorage;
  else globalThis.localStorage = localStorageOriginal;
});

const cacheFake = () => {
  const m = new Map();
  return {
    _map: m,
    match: async (url) => m.get(typeof url === 'string' ? url : url.url),
    keys: async () => [...m.keys()].map((url) => ({ url })),
    put: async (url, res) => { m.set(typeof url === 'string' ? url : url.url, res); },
    delete: async (url) => m.delete(typeof url === 'string' ? url : url.url),
    matchAll: async () => [...m.values()],
  };
};

const respOk = (bytes, tipo = 'application/x-protobuf') => ({
  ok: true,
  headers: { get: () => tipo },
  arrayBuffer: async () => new Uint8Array(bytes).buffer,
});
const respTilejson = () => ({
  ok: true,
  headers: { get: () => 'application/json' },
  arrayBuffer: async () => new TextEncoder().encode(JSON.stringify({ tiles: [PLANTILLA] })).buffer,
});
const respJson = (data) => ({
  ok: true,
  status: 200,
  headers: { get: () => 'application/json' },
  arrayBuffer: async () => new TextEncoder().encode(JSON.stringify(data)).buffer,
});
const fetchFake = (handler) => {
  const calls = [];
  const fn = async (url) => { calls.push(url); return handler(url); };
  return { fn, calls };
};

describe('tesela (slippy map)', () => {
  test('el origen y el ecuador caen donde deben', () => {
    assert.deepEqual(tesela(0, 0, 0), [0, 0]);
    assert.deepEqual(tesela(-180, 85.0511, 1), [0, 0]);
    assert.deepEqual(tesela(0, 0, 1), [1, 1]);
    assert.deepEqual(tesela(179.9, -85.0511, 1), [1, 1]);
  });

  test('un punto de Chile conocido cae en su tesela', () => {
    // Quilpué (-71.41, -33.0) a zoom 13: valores calculados con la fórmula slippy map.
    const [x, y] = tesela(-71.41, -33.0, 13);
    const n = 2 ** 13;
    assert.ok(x === Math.floor(((-71.41 + 180) / 360) * n));
    assert.ok(y > 0 && y < n);
  });
});

describe('bboxLugar y teselasLugar', () => {
  test('la caja es simétrica alrededor del lugar y crece con el radio', () => {
    const [w, s, e, n] = bboxLugar(LUGAR);
    assert.ok(Math.abs((w + e) / 2 - LUGAR.lon) < 1e-9);
    assert.ok(Math.abs((s + n) / 2 - LUGAR.lat) < 1e-9);
    const grande = bboxLugar({ ...LUGAR, radius_km: 10 });
    assert.ok(grande[0] < w && grande[2] > e);
  });

  test('cubre el centro en todos los zooms 8–13, sin duplicados', () => {
    const lista = teselasLugar(LUGAR);
    const claves = new Set(lista.map((t) => `${t.z}/${t.x}/${t.y}`));
    assert.equal(claves.size, lista.length);
    for (let z = Z_MIN; z <= Z_MAX; z++) {
      const [cx, cy] = tesela(LUGAR.lon, LUGAR.lat, z);
      assert.ok(lista.some((t) => t.z === z && t.x === cx && t.y === cy), `falta la tesela central en z${z}`);
    }
    assert.ok(Math.min(...lista.map((t) => t.z)) === Z_MIN && Math.max(...lista.map((t) => t.z)) === Z_MAX);
  });

  test('un lugar más grande pide más teselas', () => {
    assert.ok(teselasLugar({ ...LUGAR, radius_km: 20 }).length > teselasLugar(LUGAR).length);
  });
});

describe('recursosDescarga', () => {
  test('va primero un glyph por rango y después las teselas con la plantilla', () => {
    const urls = recursosDescarga(LUGAR, PLANTILLA);
    const nTiles = teselasLugar(LUGAR).length;
    assert.equal(urls.length, GLYPH_RANGOS.length + nTiles);
    assert.ok(urls[0].endsWith('0-255.pbf'));
    assert.ok(urls.slice(0, GLYPH_RANGOS.length).every((u) => u.includes('/fonts/Noto%20Sans%20Regular/')));
    assert.ok(urls[GLYPH_RANGOS.length].match(/\/planet\/v1\/\d+\/\d+\/\d+\.pbf$/));
  });
});

describe('descargarMapa', () => {
  test('descarga completa: guarda todo y deja la meta del lugar', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache, ahora: () => '2026-10-26T12:00:00Z' });
    const total = recursosDescarga(LUGAR, PLANTILLA).length;
    assert.equal(r.completo, true);
    assert.equal(r.recursos, total);
    assert.equal(r.bytes, total * 100);
    assert.equal(cache._map.size, total + 1); // + el TileJSON
    const meta = metaMapa()[LUGAR.id];
    assert.equal(meta.completo, true);
    assert.equal(meta.at, '2026-10-26T12:00:00Z');
  });

  test('respeta el tope de bytes y lo declara incompleto', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache, topeBytes: 350 });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'tope');
    assert.ok(r.bytes <= 350 + PARALELO * 100); // las peticiones en vuelo terminan
    assert.ok(r.recursos < r.total);
  });

  test('en error de red corta tras un solo reintento y guarda lo que haya', async () => {
    const { fn, calls } = fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      throw new Error('sin red');
    });
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'red');
    assert.equal(cache._map.size, 1); // solo el TileJSON
    // Un reintento por recurso en cada uno de los PARALELO workers, y nada más.
    assert.equal(calls.filter((u) => u !== TILEJSON_URL).length, PARALELO * 2);
  });

  test('un 404 salta el recurso sin cortar la descarga', async () => {
    const { fn } = fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      if (url.includes('/fonts/')) return { ok: false, status: 404, headers: { get: () => null } };
      return respOk(10);
    });
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, true);
    assert.equal(r.recursos, r.total); // los 404 cuentan como revisados, no como bajados
    assert.ok(r.bytes < r.total * 10);
  });

  test('lo ya guardado en la caché no se vuelve a bajar ni a cobrar', async () => {
    const cache = cacheFake();
    const urls = recursosDescarga(LUGAR, PLANTILLA);
    await cache.put(urls[0], respOk(999));
    await cache.put(urls[1], respOk(999));
    const { fn, calls } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(10)));
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, true);
    assert.equal(r.recursos, r.total);
    assert.ok(!calls.includes(urls[0]) && !calls.includes(urls[1]));
    assert.equal(r.bytes, (r.total - 2) * 10);
  });
});

describe('paquete sin señal (PROD-01)', () => {
  const COMUNA = {
    code: '13101', name: 'Quilpué', region: 'Valparaíso', area_km2: 480,
    geometry: { type: 'Polygon', coordinates: [[[-71.5, -33.1], [-71.3, -33.1], [-71.3, -32.9], [-71.5, -32.9], [-71.5, -33.1]]] },
    attribution: 'BCN · chile-geojson',
  };
  const CERCA = {
    source: 'OpenStreetMap (Overpass)',
    items: [
      { id: 'node/1', kind: 'fire_station', kind_label: 'Cuartel de Bomberos', name: 'Bomberos', lat: -33.01, lon: -71.42, distance_km: 1.2, direction: 'norte' },
      { id: 'node/2', kind: 'assembly_point', kind_label: 'Punto de encuentro', name: 'Plaza', lat: -33.02, lon: -71.43, distance_km: 2.4, direction: 'noreste' },
    ],
  };
  const CRITICA = {
    source: 'OpenStreetMap (Overpass)', status: 'ok',
    items: [
      { id: 'node/3', category: 'escuelas', kind: 'school', kind_label: 'Escuela', name: 'Escuela Norte', lat: -33.03, lon: -71.44, distance_km: 3.1, bearing_deg: 90, direction: 'este' },
      { id: 'node/4', category: 'salud', kind: 'clinic', kind_label: 'Centro de salud', name: 'CESFAM', lat: -33.04, lon: -71.45, distance_km: 4.2, bearing_deg: 180, direction: 'sur' },
      { id: 'node/5', category: 'agua', kind: 'water_tower', kind_label: 'Copa de agua', name: 'Torre de agua', lat: -33.05, lon: -71.46, distance_km: 5.5, bearing_deg: 270, direction: 'oeste' },
    ],
  };

  test('serviciosPaquete agrupa sin duplicar y ordena por distancia', () => {
    const s = serviciosPaquete(CERCA, CRITICA, LUGAR);
    assert.deepEqual(s.emergencia.map((x) => x.id), ['node/1', 'node/2']);
    assert.deepEqual(s.salud.map((x) => x.nombre), ['CESFAM']);
    assert.deepEqual(s.escuelas.map((x) => x.nombre), ['Escuela Norte']);
    assert.deepEqual(s.agua.map((x) => x.nombre), ['Torre de agua']);
    assert.equal(s.energia.length, 0);
  });

  test('armarPaquete declara fuentes, límites y la guía recibida', () => {
    const pkg = armarPaquete({ lugar: LUGAR, comuna: COMUNA, cerca: CERCA, critica: CRITICA, guia: { titulo: 'Guía' }, ahora: () => '2026-11-20T00:00:00Z' });
    assert.equal(pkg.comuna.name, 'Quilpué');
    assert.equal(pkg.limite_urbano, null);
    assert.equal(pkg.guia?.titulo, 'Guía');
    assert.ok(pkg.fuentes.includes('OpenStreetMap · Overpass API'));
    assert.ok(pkg.notas.some((n) => n.includes('límite urbano')));
    assert.equal(pkg.generado_at, '2026-11-20T00:00:00Z');
  });

  test('descargarPaquete guarda el JSON en brasa-tiles y permite leerlo y borrarlo', async () => {
    const { fn } = fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      if (url.includes('comunas-index.json')) return respJson([{ code: '13101', name: 'Quilpué', region: 'Valparaíso', center: [-71.42, -33.05], bbox: [-71.5, -33.1, -71.3, -32.9] }]);
      if (url.includes('comunas.geojson')) return respJson({ type: 'FeatureCollection', attribution: 'BCN · chile-geojson', features: [{ type: 'Feature', properties: { code: '13101', name: 'Quilpué', region: 'Valparaíso', area_km2: 480 }, geometry: COMUNA.geometry }] });
      if (url.includes('/api/nearby-services')) return respJson(CERCA);
      if (url.includes('/api/terrain/downwind-infrastructure')) return respJson(CRITICA);
      return respOk(10);
    });
    const cache = cacheFake();
    const r = await descargarPaquete(LUGAR, {
      fetchImpl: fn, cache, ahora: () => '2026-11-20T01:00:00Z', guia: { titulo: 'Guía' }, topeDescargas: 2,
    });
    assert.equal(r.paquete.comuna.name, 'Quilpué');
    assert.equal(r.paquete.servicios.agua.length, 1);
    assert.equal(r.paquete.mapa.completo, false); // el tope de prueba corta el mapa, no el paquete
    const guardado = await leerPaquete(LUGAR.id, { cache });
    assert.equal(guardado.comuna.name, 'Quilpué');
    assert.equal(metaPaquetes()[LUGAR.id].agua, 1);
    await borrarPaquete(LUGAR.id, { cache });
    assert.equal(await leerPaquete(LUGAR.id, { cache }), null);
    assert.equal(metaPaquetes()[LUGAR.id], undefined);
  });

  test('descargarServiciosPaquete marca unavailable y respuestas inválidas como error', async () => {
    const { fn } = fetchFake((url) => {
      if (url.includes('/api/nearby-services')) return respJson({ source: 'OSM', items: [] });
      if (url.includes('/api/terrain/downwind-infrastructure')) return respJson({ status: 'unavailable', items: [] });
      return respJson({});
    });
    const r = await descargarServiciosPaquete(LUGAR, { fetchImpl: fn });
    assert.equal(r.cerca.items.length, 0);
    assert.equal(r.critica, null);
    assert.equal(r.errores.length, 1);
    assert.ok(r.errores[0].includes('infraestructura'));
  });

  test('descargarPaquete conserva servicios válidos si una fuente falla y queda incompleto', async () => {
    const LUGAR2 = { ...LUGAR, id: 'p2', name: 'Casa 2' };
    const base = (critica) => fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      if (url.includes('comunas-index.json')) return respJson([{ code: '13101', name: 'Quilpué', region: 'Valparaíso', center: [-71.42, -33.05], bbox: [-71.5, -33.1, -71.3, -32.9] }]);
      if (url.includes('comunas.geojson')) return respJson({ type: 'FeatureCollection', attribution: 'BCN · chile-geojson', features: [{ type: 'Feature', properties: { code: '13101', name: 'Quilpué', region: 'Valparaíso', area_km2: 480 }, geometry: COMUNA.geometry }] });
      if (url.includes('/api/nearby-services')) return respJson(CERCA);
      if (url.includes('/api/terrain/downwind-infrastructure')) return respJson(critica);
      return respOk(1);
    });
    const cache = cacheFake();
    const ok = await descargarPaquete(LUGAR2, { fetchImpl: base(CRITICA).fn, cache, ahora: () => '2026-11-20T01:00:00Z', guia: { titulo: 'Guía' }, topeDescargas: 10000 });
    assert.equal(ok.paquete.servicios.agua.length, 1);
    const malo = await descargarPaquete(LUGAR2, { fetchImpl: base({ status: 'unavailable', items: [] }).fn, cache, ahora: () => '2026-11-20T02:00:00Z', guia: { titulo: 'Guía' }, topeDescargas: 10000 });
    assert.equal(malo.errores.length, 1);
    assert.equal(malo.paquete.servicios.agua.length, 1);
    assert.equal(malo.paquete.servicios_at, '2026-11-20T01:00:00Z');
    assert.equal(malo.paquete.generado_at, '2026-11-20T02:00:00Z');
    assert.equal(metaPaquetes()[LUGAR2.id].completo, false);
    assert.equal(metaPaquetes()[LUGAR2.id].agua, 1);
    const movido = await descargarPaquete({ ...LUGAR2, lat: -33.01 }, { fetchImpl: base({ status: 'unavailable', items: [] }).fn, cache, ahora: () => '2026-11-20T03:00:00Z', guia: { titulo: 'Guía' }, topeDescargas: 10000 });
    assert.equal(movido.errores.length, 1);
    assert.equal(movido.paquete.servicios.agua.length, 0);
    assert.equal(movido.paquete.servicios_at, '2026-11-20T03:00:00Z');
    await borrarPaquete(LUGAR2.id, { cache });
  });
});


describe('teselasBbox (MAPA-184)', () => {
  const clave = (t) => `${t.z}/${t.x}/${t.y}`;

  test('con bboxLugar(LUGAR) coincide con teselasLugar', () => {
    const a = teselasBbox(bboxLugar(LUGAR)).map(clave).sort();
    const b = teselasLugar(LUGAR).map(clave).sort();
    assert.deepEqual(a, b);
  });

  test('cubre un bbox de Chile central sin duplicados en Z_MIN..Z_MAX', () => {
    const bbox = [-72.0, -33.8, -70.4, -32.0];
    const lista = teselasBbox(bbox);
    const claves = new Set(lista.map(clave));
    assert.equal(claves.size, lista.length);
    for (let z = Z_MIN; z <= Z_MAX; z++) {
      const [x0, y1] = tesela(bbox[0], bbox[1], z);
      const [x1, y0] = tesela(bbox[2], bbox[3], z);
      for (const [x, y] of [[x0, y0], [x1, y1], [x0, y1], [x1, y0]]) {
        assert.ok(claves.has(`${z}/${x}/${y}`), `falta la esquina ${x}/${y} en z${z}`);
      }
    }
    assert.equal(Math.min(...lista.map((t) => t.z)), Z_MIN);
    assert.equal(Math.max(...lista.map((t) => t.z)), Z_MAX);
  });

  test('un rango de zoom explícito limita los niveles devueltos', () => {
    const niveles = new Set(teselasBbox(bboxLugar(LUGAR), 9, 10).map((t) => t.z));
    assert.deepEqual([...niveles].sort((a, b) => a - b), [9, 10]);
  });
});

describe('descargarZonaVisible (MAPA-184)', () => {
  const BBOX = bboxLugar(LUGAR);

  test('guarda TileJSON, glyphs y teselas del bbox y deja la meta zona-visible', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarZonaVisible(BBOX, { fetchImpl: fn, cache, ahora: () => '2026-11-21T12:00:00Z' });
    const urls = recursosDescargaBbox(BBOX, PLANTILLA);
    assert.equal(urls.length, GLYPH_RANGOS.length + teselasBbox(BBOX).length);
    assert.equal(r.completo, true);
    assert.equal(r.recursos, urls.length);
    assert.equal(cache._map.size, urls.length + 1); // + el TileJSON
    assert.ok(cache._map.has(TILEJSON_URL));
    assert.ok(urls.every((u) => cache._map.has(u)));
    const meta = metaMapa()['zona-visible'];
    assert.ok(meta, 'falta la meta zona-visible');
    assert.equal(meta.completo, true);
    assert.equal(meta.at, '2026-11-21T12:00:00Z');
  });

  test('respeta topeBytes y lo declara incompleto', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarZonaVisible(BBOX, { fetchImpl: fn, cache, topeBytes: 350 });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'tope');
    assert.ok(r.bytes <= 350);
    assert.equal(metaMapa()['zona-visible'].completo, false);
  });

  test('rechaza de inmediato una vista demasiado alejada sin pedir teselas ni agotar memoria', async () => {
    const { fn, calls } = fetchFake(() => respOk(100));
    const cache = cacheFake();
    const r = await descargarZonaVisible([-180, -60, 180, 60], { fetchImpl: fn, cache });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'tope');
    assert.equal(r.recursos, 0);
    assert.equal(calls.length, 0);
  });
});

describe('tieneMapaGuardado (MAPA-184)', () => {
  test('false sin meta ni TileJSON; true con TileJSON en caché; true con meta guardada', async () => {
    mem.clear();
    const vacia = cacheFake();
    assert.equal(await tieneMapaGuardado({ cache: vacia }), false);

    const conTilejson = cacheFake();
    await conTilejson.put(TILEJSON_URL, respTilejson());
    assert.equal(await tieneMapaGuardado({ cache: conTilejson }), true);

    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(10)));
    await descargarMapa(LUGAR, { fetchImpl: fn, cache: cacheFake() });
    assert.equal(await tieneMapaGuardado({ cache: cacheFake() }), true);
    mem.clear();
  });
});

describe('descargarComuna con comuna_code: null', () => {
  test('ignora comuna_code null (sin convertirlo en 0) y resuelve por punto-en-polígono antes que centro más cercano', async () => {
    const lugar = { id: 'pb', name: 'Puerto Bertrand', lat: -47.0151, lon: -72.8275, comuna_code: null };
    const { fn } = fetchFake((url) => {
      if (url.includes('comunas-index.json')) {
        return respJson([
          { code: 11301, name: 'Cochrane', region: 'Aysén', center: [-72.57, -47.25], bbox: [-73.5, -47.9, -71.8, -47.1] },
          { code: 11401, name: 'Chile Chico', region: 'Aysén', center: [-71.73, -46.54], bbox: [-73.3, -47.2, -71.6, -46.4] },
        ]);
      }
      if (url.includes('comunas.geojson')) {
        return respJson({
          type: 'FeatureCollection',
          attribution: 'BCN',
          features: [
            {
              type: 'Feature',
              properties: { code: 11301, name: 'Cochrane', region: 'Aysén', area_km2: 8900 },
              geometry: { type: 'Polygon', coordinates: [[[-73.5, -47.9], [-71.8, -47.9], [-71.8, -47.1], [-73.5, -47.1], [-73.5, -47.9]]] },
            },
            {
              type: 'Feature',
              properties: { code: 11401, name: 'Chile Chico', region: 'Aysén', area_km2: 5900 },
              geometry: { type: 'Polygon', coordinates: [[[-73.3, -47.1], [-71.6, -47.1], [-71.6, -46.4], [-73.3, -46.4], [-73.3, -47.1]]] },
            },
          ],
        });
      }
      return respJson({});
    });
    const c = await descargarComuna(lugar, { fetchImpl: fn });
    assert.equal(c.code, 11401);
    assert.equal(c.name, 'Chile Chico');
  });
});
