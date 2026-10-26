/* MAPA-166 · «Tu zona sin señal»: descarga explícita del mapa de un lugar (teselas
 * OpenFreeMap z8-13 + glyphs). ToS OpenFreeMap: ≤3.000 teselas/50 MB y ≤4 en paralelo;
 * sin User-Agent propio en el navegador (docs/FUENTES.md). */
import { GLYPH_FONTS, OFM } from './map.js';
import { storage } from './util.js';

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
