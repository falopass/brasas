/* Buscador de comunas (MAPA-21): lógica pura, sin DOM. Toma el índice liviano
 * (web/data/comunas-index.json: name, region, center, bbox) y devuelve como máximo
 * 8 comunas, primero las que coinciden por nombre y después por región. */

const MAX_RESULTADOS = 8;

// Atajos que la gente escribe y no están en el índice. «scl» es el código del
// aeropuerto de Santiago; se resuelve al nombre de la comuna, sin datos nuevos.
const ALIAS = new Map([['scl', 'santiago']]);

/** Minúsculas y sin diacríticos: «Ñuble» y «NUBLE» quedan iguales. */
export function normalizar(texto) {
  return String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

/** Comunas del índice que coinciden con `texto`, ordenadas y acotadas a 8.
 *  Nombre exacto, nombre que empieza igual, nombre que lo contiene y, al final,
 *  región. Un texto vacío o sin coincidencias devuelve [] (nunca lanza). */
export function buscarComunas(index, texto) {
  const consulta = normalizar(texto).trim();
  if (!consulta || !Array.isArray(index)) return [];
  const buscado = ALIAS.get(consulta) || consulta;
  const terminos = buscado.split(/\s+/);
  const encontradas = [];
  for (const comuna of index) {
    const nombre = normalizar(comuna?.name);
    const region = normalizar(comuna?.region);
    let orden = -1;
    if (terminos.every((t) => nombre.includes(t))) {
      orden = nombre === buscado ? 0 : nombre.startsWith(buscado) ? 1 : 2;
    } else if (terminos.every((t) => region.includes(t))) {
      orden = 3;
    }
    if (orden >= 0) encontradas.push({ comuna, orden });
  }
  return encontradas
    .sort((a, b) => a.orden - b.orden || a.comuna.name.localeCompare(b.comuna.name, 'es'))
    .slice(0, MAX_RESULTADOS)
    .map((e) => e.comuna);
}
