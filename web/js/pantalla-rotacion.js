/* BRASA · pantalla pública: parseo puro de ?comunas= y ?rotar= (rotación entre
 * comunas). Sin DOM ni estado global: recibe el query string y devuelve los
 * parámetros listos para resolveComuna (web/js/pantalla.js) y los segundos de
 * rotación. Probado en tests/js/pantalla-rotacion.test.mjs. */

const SEGUNDOS_DEF = 45;
/* Piso técnico de 5 s (la verificación del modo rota con ?rotar=5). Para que una
 * pantalla municipal dé tiempo de leerse, lo razonable es 25 s o más. */
const SEGUNDOS_MIN = 5;
const SEGUNDOS_MAX = 300;

/* Nombre comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py: _fold). */
const fold = (s) => s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

/* parseRotation(search) → { params: [...], segundos }
 * search: query string, con o sin «?» inicial. params son los trozos de ?comunas=
 * (código o nombre, mismos valores que acepta ?comuna=), sin vacíos ni duplicados
 * insensibles a tildes y mayúsculas. segundos es ?rotar= acotado a [5, 300];
 * ausente, cero, negativo o no numérico cae a 45. */
export function parseRotation(search) {
  const query = new URLSearchParams(typeof search === 'string' ? search : '');
  const seen = new Set();
  const params = [];
  for (const trozo of (query.get('comunas') ?? '').split(',')) {
    const p = trozo.trim();
    const key = fold(p);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    params.push(p);
  }
  const n = Number(query.get('rotar'));
  const segundos = Number.isFinite(n) && n > 0
    ? Math.min(Math.max(Math.round(n), SEGUNDOS_MIN), SEGUNDOS_MAX)
    : SEGUNDOS_DEF;
  return { params, segundos };
}

export { fold };
