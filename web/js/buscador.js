/* Buscador de comunas y localidades (MAPA-21, MAPA-167): lógica pura, sin DOM. Toma el
 * índice liviano (web/data/comunas-index.json: name, region, center, bbox) y el índice
 * diferido de localidades (web/data/localidades.json, generado por
 * scripts/build_localidades.py). Devuelve como máximo 8 resultados, primero las comunas
 * que coinciden por nombre y después por región; las localidades van al final. */

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

// Al empatar coincidencias entre localidades gana la de tipo más alto
// (ciudad antes que sector), como en scripts/build_localidades.py.
const ORDEN_TIPO = { ciudad: 0, pueblo: 1, villa: 2, sector: 3 };

/** Localidades del índice que coinciden con `texto`, mismo criterio que las comunas:
 *  nombre exacto, nombre que empieza igual, nombre que lo contiene y, al final, comuna.
 *  Una localidad sin `comuna` sigue encontrándose por su nombre. */
export function buscarLocalidades(index, texto) {
  const consulta = normalizar(texto).trim();
  if (!consulta || !Array.isArray(index)) return [];
  const buscado = ALIAS.get(consulta) || consulta;
  const terminos = buscado.split(/\s+/);
  const encontradas = [];
  for (const loc of index) {
    const nombre = normalizar(loc?.name);
    const comuna = normalizar(loc?.comuna);
    let orden = -1;
    if (terminos.every((t) => nombre.includes(t))) {
      orden = nombre === buscado ? 0 : nombre.startsWith(buscado) ? 1 : 2;
    } else if (terminos.every((t) => comuna.includes(t))) {
      orden = 3;
    }
    if (orden >= 0) encontradas.push({ loc, orden });
  }
  return encontradas
    .sort((a, b) => a.orden - b.orden
      || (ORDEN_TIPO[a.loc.tipo] ?? 9) - (ORDEN_TIPO[b.loc.tipo] ?? 9)
      || a.loc.name.localeCompare(b.loc.name, 'es'))
    .slice(0, MAX_RESULTADOS)
    .map((e) => e.loc);
}

/** Búsqueda combinada del mapa (MAPA-167): primero las comunas, después las localidades,
 *  con el mismo tope de 8. Cada resultado lleva `kind` para que la vista sepa si vuela a
 *  una caja (comuna) o a un punto (localidad). */
export function buscarLugares(comunasIndex, localidadesIndex, texto) {
  const comunas = buscarComunas(comunasIndex, texto).map((c) => ({ ...c, kind: 'comuna' }));
  const restantes = MAX_RESULTADOS - comunas.length;
  if (restantes <= 0) return comunas;
  const localidades = buscarLocalidades(localidadesIndex, texto)
    .slice(0, restantes)
    .map((l) => ({ ...l, kind: 'localidad' }));
  return [...comunas, ...localidades];
}
