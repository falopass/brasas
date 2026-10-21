/* Consejos de salud para los avisos de calor extremo de la DMC (AGUA-06).
 * Solo datos y funciones puras, sin DOM: «Riesgo» los pinta hoy y «Mi zona»
 * podrá usarlos sin repetir el texto. Cero invención: cada consejo lleva la
 * fuente oficial que lo respalda (OMS, MINSAL, SENAPRED o SAMU); si no hay
 * fuente pública, el consejo no se publica, y `revisarConsejos` lo comprueba
 * antes de publicar (QA-207).
 * Fuentes consultadas el 21 de octubre de 2026: */
export const CONSULTA_FUENTES = '2026-10-21';

export const NO_OFICIAL = 'BRASA no es una fuente oficial: sigue a SENAPRED (senapred.cl).';

/* Lista blanca de la guarda: el host vale por sí mismo o como subdominio suyo. */
export const DOMINIOS_OFICIALES = ['minsal.cl', 'senapred.cl', 'saludresponde.minsal.cl', 'who.int', 'samu.cl'];

export const CONSEJOS_CALOR = [
  { text: 'Toma agua a cada rato, aunque no sientas sed: con calor extremo el cuerpo se deshidrata sin avisar.',
    source: 'MINSAL: alerta de calor', url: 'https://www.minsal.cl/alerta-de-calor/' },
  { text: 'Evita el sol directo y el ejercicio al aire libre entre las 11 y las 17 h, las horas de más radiación.',
    source: 'SENAPRED: calor extremo', url: 'https://senapred.cl/calor-extremo/' },
  { text: 'Revisa seguido a las personas mayores, los niños y los enfermos crónicos; piel seca y roja, confusión o desmayo son golpe de calor: llama al SAMU 131.',
    source: 'MINSAL · Salud Responde', url: 'https://saludresponde.minsal.cl/altas-temperaturas/' },
  { text: 'No prendas fuego ni uses herramientas que echen chispas cerca de pasto seco: con calor y baja humedad, una chispa basta para iniciar un incendio.',
    source: 'SENAPRED: incendios forestales', url: 'https://senapred.cl/incendios-forestales/' },
  { text: 'Nunca dejes a niños, personas mayores ni mascotas dentro del auto estacionado, aunque sea a la sombra o con las ventanas abiertas: el interior se calienta en minutos.',
    source: 'MINSAL: calor extremo', url: 'https://degreyd.minsal.cl/que-hacer-en-caso-de-calor-extremo/' },
];

const MIN_TEXTO = 40;
const MAX_TEXTO = 240;

/** Guarda de publicación (QA-207): un consejo solo sale si su enlace es https de un
 *  dominio oficial, su texto mide entre 40 y 240 caracteres, trae fuente y ninguna URL
 *  se repite. `hoy` (AAAA-MM-DD) se inyecta para no leer el reloj aquí dentro.
 *  Devuelve `{ok, problemas}`; `problemas` está vacío cuando `ok`. */
export function revisarConsejos(consejos, hoy) {
  const problemas = [];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(CONSULTA_FUENTES) || Number.isNaN(Date.parse(CONSULTA_FUENTES))) {
    problemas.push(`CONSULTA_FUENTES no es una fecha AAAA-MM-DD: «${CONSULTA_FUENTES}»`);
  } else if (hoy && CONSULTA_FUENTES > hoy) {
    problemas.push(`CONSULTA_FUENTES (${CONSULTA_FUENTES}) está en el futuro: hoy es ${hoy}`);
  }
  const urls = new Set();
  for (const [i, c] of (consejos || []).entries()) {
    const n = `consejo ${i + 1}`;
    const text = String(c?.text ?? '').trim();
    const source = String(c?.source ?? '').trim();
    const url = String(c?.url ?? '').trim();
    if (text.length < MIN_TEXTO || text.length > MAX_TEXTO) {
      problemas.push(`${n}: el texto debe medir entre ${MIN_TEXTO} y ${MAX_TEXTO} caracteres (mide ${text.length})`);
    }
    if (!source) problemas.push(`${n}: falta la fuente oficial`);
    let host = '';
    try { host = new URL(url).hostname; } catch { /* URL malformada: queda sin host */ }
    if (!url.startsWith('https://') || !host) {
      problemas.push(`${n}: la URL debe ser https y abrir: «${url}»`);
    } else if (!DOMINIOS_OFICIALES.some((d) => host === d || host.endsWith(`.${d}`))) {
      problemas.push(`${n}: «${host}» no es un dominio oficial (${DOMINIOS_OFICIALES.join(', ')})`);
    }
    if (urls.has(url)) problemas.push(`${n}: la URL está repetida: ${url}`);
    urls.add(url);
  }
  return { ok: problemas.length === 0, problemas };
}

/** ¿La lista de avisos de la DMC trae uno de calor? (kind lo asigna el backend: «viento» o «calor»). */
export const hayCalor = (avisos) => (avisos || []).some((a) => a.kind === 'calor');
