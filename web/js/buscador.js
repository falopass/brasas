/* Buscador de comunas y localidades (MAPA-21, MAPA-167): lógica pura, sin DOM. Toma
 * comunas-index.json y el diferido localidades.json. Máximo 8: comunas primero. */

const MAX_RESULTADOS = 8;

// «scl» es el código del aeropuerto de Santiago: se resuelve a la comuna, sin datos nuevos.
const ALIAS = new Map([['scl', 'santiago']]);

/** Minúsculas y sin diacríticos: «Ñuble» y «NUBLE» quedan iguales. */
export function normalizar(texto) {
  return String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

/** Coincidencias acotadas a 8: nombre exacto, prefijo, contiene y al final `campo2`;
 *  `empate` desempata antes del nombre. */
function buscar(index, texto, campo2, empate) {
  const consulta = normalizar(texto).trim();
  if (!consulta || !Array.isArray(index)) return [];
  const buscado = ALIAS.get(consulta) || consulta;
  const terminos = buscado.split(/\s+/);
  const encontradas = [];
  for (const item of index) {
    const nombre = normalizar(item?.name);
    const otro = normalizar(item?.[campo2]);
    let orden = -1;
    if (terminos.every((t) => nombre.includes(t))) {
      orden = nombre === buscado ? 0 : nombre.startsWith(buscado) ? 1 : 2;
    } else if (terminos.every((t) => otro.includes(t))) {
      orden = 3;
    }
    if (orden >= 0) encontradas.push({ item, orden });
  }
  return encontradas
    .sort((a, b) => a.orden - b.orden
      || (empate ? empate(a.item, b.item) : 0)
      || a.item.name.localeCompare(b.item.name, 'es'))
    .slice(0, MAX_RESULTADOS)
    .map((e) => e.item);
}

export const buscarComunas = (index, texto) => buscar(index, texto, 'region');

// Al empatar gana el tipo más alto (ciudad antes que sector), como build_localidades.py.
const ORDEN_TIPO = { ciudad: 0, pueblo: 1, villa: 2, sector: 3 };

/** Localidades que coinciden con `texto` por `comuna` (MAPA-167). */
export const buscarLocalidades = (index, texto) =>
  buscar(index, texto, 'comuna', (a, b) => (ORDEN_TIPO[a.tipo] ?? 9) - (ORDEN_TIPO[b.tipo] ?? 9));

/** Búsqueda combinada (MAPA-167): comunas primero, tope 8, `kind` por resultado. */
export function buscarLugares(comunasIndex, localidadesIndex, texto) {
  const comunas = buscarComunas(comunasIndex, texto).map((c) => ({ ...c, kind: 'comuna' }));
  const restantes = MAX_RESULTADOS - comunas.length;
  if (restantes <= 0) return comunas;
  const localidades = buscarLocalidades(localidadesIndex, texto)
    .slice(0, restantes)
    .map((l) => ({ ...l, kind: 'localidad' }));
  return [...comunas, ...localidades];
}
