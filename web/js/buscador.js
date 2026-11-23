/* Buscador de comunas, regiones y localidades (MAPA-21, MAPA-167): lógica pura, sin DOM.
 * Toma comunas-index.json y el diferido localidades.json. Máximo 8 resultados. */

const MAX_RESULTADOS = 8;

// «scl» es el código del aeropuerto de Santiago: se resuelve a la comuna, sin datos nuevos.
const ALIAS = new Map([['scl', 'santiago']]);
const ALIAS_REGION = new Map([['rm', 'metropolitana']]);
const PREFIJO_REGION = /^region\s+(?:de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+)?/;
// Islas oceánicas de Valparaíso (Isla de Pascua, Juan Fernández): al encuadrar la región
// completa se usa el territorio continental, igual que backend/geo.py.
const LON_CONTINENTAL_MIN = -76;

/** Minúsculas y sin diacríticos: «Ñuble» y «NUBLE» quedan iguales. */
export function normalizar(texto) {
  return String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

/** Clave de cotejo sin apóstrofes ni espacios extras: «ohiggins» calza con «O'Higgins». */
const clave = (texto) => normalizar(texto).replace(/['’]/g, '').replace(/\s+/g, ' ').trim();

/** Coincidencias puntuadas: 0 exacto, 1 prefijo, 2 contiene y 3 en `campo2`. */
function buscarConOrden(index, texto, campo2, empate) {
  const consulta = clave(texto);
  if (!consulta || !Array.isArray(index)) return [];
  const buscado = ALIAS.get(consulta) || consulta;
  const terminos = buscado.split(' ');
  const encontradas = [];
  for (const item of index) {
    const nombre = clave(item?.name);
    const otro = clave(item?.[campo2]);
    let orden = -1;
    if (terminos.every((t) => nombre.includes(t))) {
      orden = nombre === buscado ? 0 : nombre.startsWith(buscado) ? 1 : 2;
    } else if (terminos.every((t) => otro.includes(t))) {
      orden = 3;
    }
    if (orden >= 0) encontradas.push({ item, orden });
  }
  return encontradas.sort((a, b) => a.orden - b.orden
    || (empate ? empate(a.item, b.item) : 0)
    || a.item.name.localeCompare(b.item.name, 'es'));
}

/** Coincidencias acotadas a 8: nombre exacto, prefijo, contiene y al final `campo2`;
 *  `empate` desempata antes del nombre. */
function buscar(index, texto, campo2, empate) {
  return buscarConOrden(index, texto, campo2, empate)
    .slice(0, MAX_RESULTADOS)
    .map((e) => e.item);
}

export const buscarComunas = (index, texto) => buscar(index, texto, 'region');

// Al empatar gana el tipo más alto (ciudad antes que sector), como build_localidades.py.
const ORDEN_TIPO = { ciudad: 0, pueblo: 1, villa: 2, sector: 3 };

/** Localidades que coinciden con `texto` por `comuna` (MAPA-167). */
export const buscarLocalidades = (index, texto) =>
  buscar(index, texto, 'comuna', (a, b) => (ORDEN_TIPO[a.tipo] ?? 9) - (ORDEN_TIPO[b.tipo] ?? 9));

/** Regiones derivadas de `comunasIndex` con su caja continental, sin archivos nuevos. */
function regionesDesdeComunas(comunasIndex) {
  if (!Array.isArray(comunasIndex)) return [];
  const porNombre = new Map();
  for (const c of comunasIndex) {
    if (!c?.region || !Array.isArray(c.bbox) || c.bbox.length < 4) continue;
    let reg = porNombre.get(c.region);
    if (!reg) { reg = { name: c.region, cont: null, todo: null }; porNombre.set(c.region, reg); }
    const unir = (acc, [w, s, e, n]) => (acc ? [Math.min(acc[0], w), Math.min(acc[1], s), Math.max(acc[2], e), Math.max(acc[3], n)] : [w, s, e, n]);
    reg.todo = unir(reg.todo, c.bbox);
    if (c.bbox[0] >= LON_CONTINENTAL_MIN) reg.cont = unir(reg.cont, c.bbox);
  }
  return [...porNombre.values()].map((r) => ({ kind: 'region', name: r.name, bbox: r.cont || r.todo }));
}

/** Coincidencias de región (con soporte para «región del Maule», «RM» u «ohiggins»). */
function buscarRegionesConOrden(comunasIndex, texto) {
  const consulta = clave(texto);
  if (!consulta || !Array.isArray(comunasIndex)) return [];
  const explicita = PREFIJO_REGION.test(consulta);
  const sinPrefijo = consulta.replace(PREFIJO_REGION, '').trim();
  const buscado = ALIAS_REGION.get(sinPrefijo) || sinPrefijo;
  if (!buscado) return [];
  const terminos = buscado.split(' ');
  const encontradas = [];
  for (const item of regionesDesdeComunas(comunasIndex)) {
    const nombre = clave(item.name);
    if (!terminos.every((t) => nombre.includes(t))) continue;
    const orden = nombre === buscado ? 0 : nombre.startsWith(buscado) ? 1 : 2;
    encontradas.push({ item, orden, explicita });
  }
  return encontradas.sort((a, b) => a.orden - b.orden || a.item.name.localeCompare(b.item.name, 'es'));
}

export const buscarRegiones = (comunasIndex, texto) =>
  buscarRegionesConOrden(comunasIndex, texto).slice(0, MAX_RESULTADOS).map((e) => e.item);

/** Búsqueda combinada (MAPA-167): regiones, comunas y localidades, tope 8, `kind` por resultado. */
export function buscarLugares(comunasIndex, localidadesIndex, texto) {
  const consulta = clave(texto);
  if (!consulta) return [];
  const regiones = buscarRegionesConOrden(comunasIndex, texto);
  const explicitaRegion = regiones.some((r) => r.explicita);
  const comunas = buscarConOrden(comunasIndex, texto, 'region')
    .map((e) => ({ ...e, item: { ...e.item, kind: 'comuna' } }));
  const regClaves = new Set(regiones.map((r) => clave(r.item.name)));

  const comunasExactasMismaRegion = [];
  const restoComunasPorNombre = [];
  const comunasPorRegion = [];
  for (const c of comunas) {
    if (c.orden === 3) { comunasPorRegion.push(c.item); continue; }
    const cn = clave(c.item.name);
    const cr = clave(c.item.region);
    // Comuna homónima en la misma región (Valparaíso, Antofagasta, Arica, Maule): va junto a su región.
    // Comunas homónimas de otra región (O'Higgins en Aysén, Los Lagos en Los Ríos) ceden el primer lugar a la región.
    if (!explicitaRegion && c.orden === 0 && regClaves.has(cr) && cr.includes(cn)) {
      comunasExactasMismaRegion.push(c.item);
    } else {
      restoComunasPorNombre.push(c.item);
    }
  }
  const regionesFuertes = regiones.filter((r) => r.orden <= 1 || r.explicita).map((r) => r.item);
  const regionesResto = regiones.filter((r) => r.orden > 1 && !r.explicita).map((r) => r.item);
  const combinados = [
    ...comunasExactasMismaRegion,
    ...regionesFuertes,
    ...restoComunasPorNombre,
    ...regionesResto,
    ...comunasPorRegion,
  ].slice(0, MAX_RESULTADOS);

  const restantes = MAX_RESULTADOS - combinados.length;
  if (restantes <= 0) return combinados;
  const localidades = buscarLocalidades(localidadesIndex, texto)
    .slice(0, restantes)
    .map((l) => ({ ...l, kind: 'localidad' }));
  return [...combinados, ...localidades];
}

// Misma aritmética que util.js:haversineKm; este módulo no importa nada.
function distKm(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 6371.0088 * 2 * Math.asin(Math.sqrt(a));
}

/** Resuelve la comuna de un lugar contra `comunas-index.json` sin polígonos: primero usa
 *  `comuna.code`/`comuna_code` si ya vino del backend; si no, filtra por `bbox` que contiene
 *  el punto y desempata por centro de caja (así cabeceras periféricas como Chile Chico vs
 *  Cochrane en Puerto Bertrand no asignan la comuna vecina). */
export function comunaDePunto(lugar, comunasIndex) {
  if (!lugar || !Array.isArray(comunasIndex) || !comunasIndex.length) return null;
  const propio = Number(lugar.comuna?.code ?? lugar.comuna_code);
  if (Number.isFinite(propio)) {
    const exacta = comunasIndex.find((c) => Number(c?.code) === propio);
    if (exacta) return exacta;
  }
  if (!Number.isFinite(lugar.lon) || !Number.isFinite(lugar.lat)) return null;
  const { lon, lat } = lugar;
  const enCaja = comunasIndex.filter(
    (c) => Array.isArray(c?.bbox) && c.bbox.length >= 4
      && c.bbox[0] <= lon && lon <= c.bbox[2] && c.bbox[1] <= lat && lat <= c.bbox[3],
  );
  const pool = enCaja.length ? enCaja : comunasIndex;
  let best = null;
  let min = Infinity;
  for (const c of pool) {
    const punto = enCaja.length
      ? [(c.bbox[0] + c.bbox[2]) / 2, (c.bbox[1] + c.bbox[3]) / 2]
      : (Array.isArray(c?.center) && c.center.length >= 2 ? c.center
        : (Array.isArray(c?.bbox) && c.bbox.length >= 4 ? [(c.bbox[0] + c.bbox[2]) / 2, (c.bbox[1] + c.bbox[3]) / 2] : null));
    if (!punto) continue;
    const d = distKm(lat, lon, punto[1], punto[0]);
    if (d < min) { min = d; best = c; }
  }
  return best;
}
