/* MAPA-166 · «Tu zona sin señal»: descarga explícita del mapa de un lugar (teselas
 * OpenFreeMap z8-13 + glyphs). ToS OpenFreeMap: ≤3.000 teselas/50 MB y ≤4 en paralelo;
 * sin User-Agent propio en el navegador (docs/FUENTES.md). */
import { GLYPH_FONTS, OFM } from './map.js';
import { cardinal, haversineKm, storage } from './util.js';

// El SW no puede importar: el nombre se repite en sw.js.
export const TILE_CACHE = 'brasa-tiles';
export const TILEJSON_URL = `${OFM}/planet`;
export const Z_MIN = 8, Z_MAX = 13;
export const PARALELO = 4, DESCARGAS_TOPE = 3000; // topes de OpenFreeMap por descarga
export const BYTES_TOPE = 15 * 1024 * 1024; // tope propio ~15 MB por lugar

const META_KEY = 'mapa-offline';
// Bloques de 256 glyphs para nombres en español (tildes, extendidos, la g̃ mapudungun).
export const GLYPH_RANGOS = [0, 256, 512, 768, 1024, 8192];

/** (x, y) slippy-map de un lon/lat a zoom z. */
export function tesela(lon, lat, z) {
  const n = 2 ** z;
  const x = Math.min(n - 1, Math.max(0, Math.floor(((lon + 180) / 360) * n)));
  const phi = (Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI) / 180;
  const y = Math.min(n - 1, Math.max(0, Math.floor(((1 - Math.log(Math.tan(phi) + 1 / Math.cos(phi)) / Math.PI) / 2) * n)));
  return [x, y];
}

/** Bbox del círculo del lugar con su radio. */
export function bboxLugar({ lat, lon, radius_km }) {
  const r = Number.isFinite(radius_km) && radius_km > 0 ? radius_km : 5;
  const dLat = r / 110.574;
  const dLon = r / (111.32 * Math.cos((lat * Math.PI) / 180));
  return [lon - dLon, lat - dLat, lon + dLon, lat + dLat];
}

/** Teselas del lugar con su radio, z8-13. */
export function teselasLugar(lugar, zMin = Z_MIN, zMax = Z_MAX) {
  const [w, s, e, n] = bboxLugar(lugar);
  const out = [];
  for (let z = zMin; z <= zMax; z++) {
    const [x0, y0] = tesela(w, n, z);
    const [x1, y1] = tesela(e, s, z);
    for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) {
      for (let y = Math.min(y0, y1); y <= Math.max(y0, y1); y++) out.push({ z, x, y });
    }
  }
  return out;
}

/** URLs: glyphs primero (sin ellos no hay nombres), luego las teselas. */
export function recursosDescarga(lugar, plantilla) {
  const fuentes = GLYPH_FONTS.flatMap((f) =>
    GLYPH_RANGOS.map((r) => `${OFM}/fonts/${encodeURIComponent(f)}/${r}-${r + 255}.pbf`));
  return [...fuentes, ...teselasLugar(lugar).map(({ z, x, y }) =>
    plantilla.replace('{z}', z).replace('{x}', x).replace('{y}', y))];
}

// Un reintento a lo sumo: red, 5xx y 429 esperan y abandonan; 404 salta el recurso.
async function pedir(url, fetchImpl, reintenta = true) {
  try {
    const r = await fetchImpl(url);
    if (r.ok) return { body: await r.arrayBuffer() };
    if (r.status === 404) return { saltar: true };
    if (!reintenta || (r.status !== 429 && r.status < 500)) return null;
  } catch {
    if (!reintenta) return null;
  }
  await new Promise((r) => setTimeout(r, 1500));
  return pedir(url, fetchImpl, false);
}

export const metaMapa = () => storage.get(META_KEY, {}) || {};

export async function usoMapa() {
  if (typeof caches === 'undefined') return { recursos: 0, bytes: 0 };
  try {
    const rs = await (await caches.open(TILE_CACHE)).matchAll();
    let bytes = 0;
    for (const r of rs) bytes += (await r.blob()).size;
    return { recursos: rs.length, bytes };
  } catch { return { recursos: 0, bytes: 0 }; }
}

export async function borrarMapa() {
  if (typeof caches !== 'undefined') await caches.delete(TILE_CACHE);
  storage.set(META_KEY, {});
  storage.set(PAQUETE_KEY, {});
}

/** Descarga del lugar: TileJSON → glyphs → teselas, PARALELO a la vez; corta al tope. */
export async function descargarMapa(lugar, { onProgreso, fetchImpl = globalThis.fetch?.bind(globalThis), cache = null, ahora = () => new Date().toISOString(), topeBytes = BYTES_TOPE, topeDescargas = DESCARGAS_TOPE } = {}) {
  if (!fetchImpl) throw new Error('Este navegador no puede descargar mapas.');
  const almacen = cache ?? (await caches.open(TILE_CACHE));
  // La copia del TileJSON fija la versión de teselas que el mapa usará sin señal.
  const tj = await pedir(TILEJSON_URL, fetchImpl);
  if (!tj?.body) throw new Error('Sin conexión con la fuente de teselas.');
  const plantilla = JSON.parse(new TextDecoder().decode(tj.body))?.tiles?.[0];
  if (!plantilla) throw new Error('La fuente de teselas no trajo su plantilla.');
  await almacen.put(TILEJSON_URL, new Response(tj.body, { headers: { 'Content-Type': 'application/json' } }));

  const recursos = recursosDescarga(lugar, plantilla);
  const total = recursos.length;
  // Lo ya guardado (teselas compartidas entre lugares) no se baja ni cobra dos veces.
  const presentes = new Set((await almacen.keys()).map((k) => k.url));
  let i = 0;
  let hechas = 0;
  let nuevas = 0;
  let bytes = 0;
  let corte = null;
  const avance = () => onProgreso?.({ hechas, total, bytes });
  avance();
  const worker = async () => {
    while (i < recursos.length && !corte) {
      if (nuevas >= topeDescargas || bytes >= topeBytes) { corte = 'tope'; break; }
      const url = recursos[i++];
      if (presentes.has(url)) { hechas++; avance(); continue; }
      const r = await pedir(url, fetchImpl);
      if (r === null) { corte = 'red'; break; }
      hechas++;
      if (!r.saltar) {
        nuevas++;
        bytes += r.body.byteLength;
        // Solo el cuerpo: un Vary podría romper el match del SW.
        await almacen.put(url, new Response(r.body));
      }
      avance();
    }
  };
  await Promise.all(Array.from({ length: PARALELO }, worker));
  const resumen = { at: ahora(), recursos: hechas, total, bytes, completo: !corte, motivo: corte || 'completo' };
  const m = metaMapa();
  m[lugar.id] = resumen;
  storage.set(META_KEY, m);
  return resumen;
}

/* PROD-01 · «Paquete sin señal»: sobre la misma descarga de teselas guarda la
 * geometría comunal, los servicios cercanos ya disponibles por las APIs públicas y
 * la guía de Prepárate, en la misma caché `brasa-tiles` (sin tocar el service worker). */
export const PAQUETE_PREFIX = '/api/paquete-sin-senal/';
export const PAQUETE_KEY = 'paquete-offline';
const PAQUETE_VERSION = 1;
const SERVICIOS_POR_GRUPO = 12;

const paqueteUrl = (id) => `${PAQUETE_PREFIX}${encodeURIComponent(id)}.json`;
const jsonCache = async (cache) => cache || (typeof caches !== 'undefined' ? caches.open(TILE_CACHE) : null);
const decodeJson = async (res) => {
  if (!res?.body) return null;
  try { return JSON.parse(new TextDecoder().decode(res.body)); } catch { return null; }
};
const pedirJson = async (url, fetchImpl) => decodeJson(await pedir(url, fetchImpl));

export const metaPaquetes = () => storage.get(PAQUETE_KEY, {}) || {};

export async function leerPaquete(id, { cache } = {}) {
  const almacen = await jsonCache(cache);
  if (!almacen || !id) return null;
  try {
    const res = await almacen.match(paqueteUrl(id));
    return res ? await res.json() : null;
  } catch { return null; }
}

export async function borrarPaquete(id = null, { cache } = {}) {
  const almacen = await jsonCache(cache);
  const meta = metaPaquetes();
  if (almacen) {
    try {
      if (id) await almacen.delete(paqueteUrl(id));
      else {
        for (const req of await almacen.keys()) {
          const url = typeof req === 'string' ? req : req.url;
          if (url.includes(PAQUETE_PREFIX)) await almacen.delete(url);
        }
      }
    } catch { /* la metadata se limpia igual */ }
  }
  if (id) delete meta[id]; else Object.keys(meta).forEach((k) => delete meta[k]);
  storage.set(PAQUETE_KEY, meta);
}

const COMUNA_INDEX_URL = '/web/data/comunas-index.json';
const COMUNA_GEOJSON_URL = '/web/data/comunas.geojson';

const comunaCodeDe = (lugar, index) => {
  const propia = Number(lugar?.comuna?.code ?? lugar?.comuna_code);
  if (Number.isFinite(propia)) return propia;
  let best = null; let min = Infinity;
  for (const c of index || []) {
    if (!Array.isArray(c?.center)) continue;
    const d = haversineKm(lugar.lat, lugar.lon, c.center[1], c.center[0]);
    if (d < min) { min = d; best = c.code; }
  }
  return best;
};

export async function descargarComuna(lugar, { fetchImpl = globalThis.fetch?.bind(globalThis) } = {}) {
  const [index, fc] = await Promise.all([pedirJson(COMUNA_INDEX_URL, fetchImpl), pedirJson(COMUNA_GEOJSON_URL, fetchImpl)]);
  if (!index || !fc) throw new Error('No se pudo descargar la geometría comunal.');
  const code = comunaCodeDe(lugar, index);
  const feature = (fc.features || []).find((f) => String(f?.properties?.code) === String(code));
  if (!feature) throw new Error('No se encontró el límite de la comuna de este lugar.');
  return {
    code,
    name: feature.properties?.name || index.find((c) => String(c.code) === String(code))?.name || '',
    region: feature.properties?.region || '',
    area_km2: feature.properties?.area_km2 ?? null,
    geometry: feature.geometry,
    attribution: fc.attribution || 'BCN · chile-geojson',
  };
}

const KIND_NEARBY = {
  assembly_point: 'Punto de encuentro', hospital: 'Hospital', clinic: 'Centro de salud',
  fire_station: 'Cuartel de Bomberos', police: 'Carabineros',
};
const CATEGORY_CRITICA = { escuelas: 'Escuela', salud: 'Centro de salud', energia: 'Infraestructura eléctrica', agua: 'Agua' };

const servicioNormal = (raw, lugar, tipoFallback, fuente) => {
  const lat = Number(raw?.lat); const lon = Number(raw?.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const distance = Number.isFinite(raw.distance_km) ? raw.distance_km : haversineKm(lugar.lat, lugar.lon, lat, lon);
  const bearing = Number.isFinite(raw.bearing_deg) ? raw.bearing_deg : null;
  return {
    id: raw.id || `${lat.toFixed(5)},${lon.toFixed(5)}`,
    nombre: raw.name || raw.kind_label || tipoFallback,
    tipo: tipoFallback,
    lat, lon,
    distance_km: Math.round(distance * 100) / 100,
    direction: raw.direction || (bearing === null ? '' : cardinal(bearing)),
    fuente,
  };
};

const porDistancia = (a, b) => a.distance_km - b.distance_km;
const recortar = (items) => items.sort(porDistancia).slice(0, SERVICIOS_POR_GRUPO);

export function serviciosPaquete(cerca, critica, lugar) {
  const servicios = { emergencia: [], salud: [], escuelas: [], agua: [], energia: [] };
  const vistos = new Set();
  const add = (grupo, item) => {
    if (!item) return;
    const key = `${grupo}:${item.id}`;
    if (vistos.has(key)) return;
    vistos.add(key);
    servicios[grupo].push(item);
  };
  for (const raw of cerca?.items || []) {
    const tipo = KIND_NEARBY[raw.kind] || raw.kind_label || 'Servicio';
    const item = servicioNormal(raw, lugar, tipo, cerca.source || 'OpenStreetMap (Overpass)');
    if (!item) continue;
    if (['assembly_point', 'fire_station', 'police'].includes(raw.kind)) add('emergencia', item);
    else if (['hospital', 'clinic'].includes(raw.kind)) add('salud', item);
  }
  for (const raw of critica?.items || []) {
    const tipo = CATEGORY_CRITICA[raw.category] || raw.kind_label || 'Servicio';
    const item = servicioNormal(raw, lugar, tipo, critica.source || 'OpenStreetMap (Overpass)');
    if (!item) continue;
    if (raw.category === 'escuelas') add('escuelas', item);
    else if (raw.category === 'salud') add('salud', item);
    else if (raw.category === 'agua') add('agua', item);
    else if (raw.category === 'energia') add('energia', item);
  }
  return Object.fromEntries(Object.entries(servicios).map(([k, v]) => [k, recortar(v)]));
}

export function armarPaquete({ lugar, comuna = null, cerca = null, critica = null, guia = null, mapa = null, ahora = () => new Date().toISOString() }) {
  const servicios = serviciosPaquete(cerca, critica, lugar);
  const at = ahora();
  return {
    version: PAQUETE_VERSION,
    lugar: { id: lugar.id, name: lugar.name, lat: lugar.lat, lon: lugar.lon, radius_km: lugar.radius_km || null },
    comuna,
    limite_urbano: null,
    servicios,
    servicios_at: at,
    guia,
    mapa,
    fuentes: [
      ...(comuna ? ['BCN · límites comunales'] : []),
      'OpenStreetMap · Overpass API',
      'OpenFreeMap · teselas del mapa',
      ...(guia ? ['BRASA · guía de Prepárate'] : []),
    ],
    notas: [
      'La cobertura de OpenStreetMap es incompleta en zonas rurales; confirma servicios con tu municipio.',
      'Los puntos de encuentro oficiales los define cada municipio y SENAPRED.',
      'El límite urbano no tiene una capa propia descargable: el fondo vectorial de OpenStreetMap sí muestra la mancha urbana.',
      'Los puntos de agua son infraestructura registrada en OpenStreetMap (plantas, torres y tratamiento), no necesariamente agua potable de emergencia.',
    ],
    generado_at: at,
  };
}

const NEARBY_URL = (lugar) => `/api/nearby-services?lat=${lugar.lat}&lon=${lugar.lon}`;
const CRITICA_URL = (lugar) => `/api/terrain/downwind-infrastructure?lat=${lugar.lat}&lon=${lugar.lon}&scope=all&per_category=15`;

export async function descargarServiciosPaquete(lugar, { fetchImpl = globalThis.fetch?.bind(globalThis) } = {}) {
  const errores = [];
  const leer = async (url, nombre, valida) => {
    let data = null;
    try { data = await pedirJson(url, fetchImpl); }
    catch (err) { errores.push(`${nombre}: ${err.message}`); return null; }
    if (!valida(data)) {
      errores.push(`${nombre}: respuesta no disponible`);
      return null;
    }
    return data;
  };
  const [cerca, critica] = await Promise.all([
    leer(NEARBY_URL(lugar), 'servicios cercanos', (v) => Array.isArray(v?.items)),
    leer(CRITICA_URL(lugar), 'infraestructura crítica', (v) => v?.status === 'ok' && Array.isArray(v?.items)),
  ]);
  return { cerca, critica, errores };
}

export async function descargarPaquete(lugar, {
  onProgreso, fetchImpl = globalThis.fetch?.bind(globalThis), cache = null,
  ahora = () => new Date().toISOString(), guia = null, ...opcionesMapa
} = {}) {
  if (!lugar?.id || !Number.isFinite(lugar.lat) || !Number.isFinite(lugar.lon)) throw new Error('Elige un lugar guardado con coordenadas.');
  const almacen = await jsonCache(cache);
  const mapa = await descargarMapa(lugar, {
    ...opcionesMapa,
    fetchImpl,
    cache: almacen,
    ahora,
    onProgreso: (p) => onProgreso?.({ fase: 'mapa', ...p }),
  });
  onProgreso?.({ fase: 'datos', total: 2, hechas: 0 });
  const comuna = await descargarComuna(lugar, { fetchImpl });
  onProgreso?.({ fase: 'datos', total: 2, hechas: 1 });
  const { cerca, critica, errores } = await descargarServiciosPaquete(lugar, { fetchImpl });
  const previo = await leerPaquete(lugar.id, { cache: almacen });
  const paquete = armarPaquete({ lugar, comuna, cerca, critica, guia, mapa, ahora });
  // Si una fuente de servicios falla, no se pisa con listas vacías lo que ya estaba guardado
  // para la MISMA ubicación: se conserva el snapshot anterior y el paquete queda incompleto.
  // Si el lugar se movió, esas distancias/direcciones ya no sirven y no se heredan.
  const mismaUbicacion = previo?.lugar && Number.isFinite(Number(previo.lugar.lat)) && Number.isFinite(Number(previo.lugar.lon))
    && Math.abs(Number(previo.lugar.lat) - lugar.lat) < 1e-6 && Math.abs(Number(previo.lugar.lon) - lugar.lon) < 1e-6;
  if (errores.length && mismaUbicacion) {
    paquete.servicios = { emergencia: [], salud: [], escuelas: [], agua: [], energia: [], ...(previo.servicios || {}) };
    paquete.servicios_at = previo.servicios_at || previo.generado_at || paquete.servicios_at;
  }
  if (errores.length) paquete.errores = errores;
  const cuerpo = JSON.stringify(paquete);
  const bytes = new TextEncoder().encode(cuerpo).byteLength;
  await almacen.put(paqueteUrl(lugar.id), new Response(cuerpo, { headers: { 'Content-Type': 'application/json; charset=utf-8' } }));
  const meta = metaPaquetes();
  meta[lugar.id] = {
    at: ahora(), bytes, completo: Boolean(mapa?.completo) && errores.length === 0,
    servicios: Object.values(paquete.servicios).reduce((n, v) => n + v.length, 0),
    agua: paquete.servicios.agua.length,
    errores: errores.length,
  };
  storage.set(PAQUETE_KEY, meta);
  return { paquete, bytes, mapa, errores };
}
