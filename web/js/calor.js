/* Consejos de salud para los avisos de calor extremo de la DMC (AGUA-06).
 * Solo datos y funciones puras, sin DOM: «Riesgo» los pinta hoy y «Mi zona»
 * podrá usarlos sin repetir el texto. Cero invención: cada consejo lleva la
 * fuente oficial que lo respalda (OMS, MINSAL, SENAPRED o SAMU); si no hay
 * fuente pública, el consejo no se publica. `revisarConsejos` es la guarda
 * que hace cumplir esa promesa: la corre tests/js/calor.test.mjs.
 * Fuentes consultadas el 21 de octubre de 2026: */
export const CONSULTA_FUENTES = '2026-10-21';

export const NO_OFICIAL = 'BRASA no es una fuente oficial: sigue a SENAPRED (senapred.cl).';

/* Lista blanca de instituciones oficiales: el host de cada `url` debe ser
 * uno de estos dominios o un subdominio de ellos. La guarda de Python
 * (tests/test_fuentes_enlaces.py) tiene su propia lista, más amplia porque
 * cubre también Prepárate y «¿Qué hago si…?». */
export const DOMINIOS_OFICIALES = ['minsal.cl', 'senapred.cl', 'saludresponde.minsal.cl', 'who.int', 'samu.cl'];

export const CONSEJOS_CALOR = [
  { text: 'Toma agua a cada rato, aunque no sientas sed: con calor extremo el cuerpo se deshidrata sin avisar.',
    source: 'MINSAL: alerta de calor', url: 'https://www.minsal.cl/alerta-de-calor/' },
  { text: 'Evita el sol directo y el ejercicio al aire libre entre las 11 y las 17 h, las horas de más radiación.',
    source: 'SENAPRED: calor extremo', url: 'https://senapred.cl/calor-extremo/' },
  { text: 'Revisa seguido a las personas mayores, los niños y los enfermos crónicos; piel seca y roja, confusión o desmayo son golpe de calor: llama al SAMU 131.',
    source: 'MINSAL · Salud Responde', url: 'https://saludresponde.minsal.cl/altas-temperaturas/' },
  { text: 'No enciendas fuego ni uses herramientas que echen chispas (esmeril, soldadora, desbrozadora) cerca de vegetación seca: con calor extremo un incendio parte con una sola chispa.',
    source: 'SENAPRED: incendios forestales', url: 'https://www.senapred.cl/incendios-forestales/' },
  { text: 'Nunca dejes a niños, personas mayores ni mascotas dentro del auto estacionado, aunque sea a la sombra o con las ventanas abiertas: el interior se calienta en minutos.',
    source: 'MINSAL: calor extremo', url: 'https://degreyd.minsal.cl/que-hacer-en-caso-de-calor-extremo/' },
];

/* Guarda de publicación (QA-207): devuelve { ok, problemas } con la lista de
 * todo lo que impediría publicar los consejos — URL que no sea https, host
 * fuera de DOMINIOS_OFICIALES, texto fuera de 40-240 caracteres, fuente
 * vacía, URL repetida o una CONSULTA_FUENTES que no sea fecha ISO o que sea
 * futura. `hoy` (AAAA-MM-DD) lo inyecta quien la llama: el módulo no mira
 * el reloj. */
export function revisarConsejos(consejos, hoy) {
  const problemas = [];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(CONSULTA_FUENTES) || Number.isNaN(Date.parse(`${CONSULTA_FUENTES}T00:00:00Z`))) {
    problemas.push(`CONSULTA_FUENTES no es una fecha ISO válida: «${CONSULTA_FUENTES}»`);
  } else if (CONSULTA_FUENTES > hoy) {
    problemas.push(`CONSULTA_FUENTES «${CONSULTA_FUENTES}» es futura respecto de hoy «${hoy}»`);
  }
  const vistas = new Set();
  for (const c of consejos) {
    const donde = (c.source || '').trim() || c.url || 'sin fuente';
    if (!c.source || !c.source.trim()) problemas.push(`consejo sin fuente: «${(c.text || '').slice(0, 50)}»`);
    const largo = (c.text || '').trim().length;
    if (largo < 40 || largo > 240) problemas.push(`«${donde}»: texto de ${largo} caracteres, debe tener entre 40 y 240`);
    let u;
    try {
      u = new URL(c.url || '');
    } catch {
      problemas.push(`«${donde}»: URL inválida «${c.url}»`);
      continue;
    }
    if (u.protocol !== 'https:') problemas.push(`«${donde}»: la URL no es https: ${c.url}`);
    if (!DOMINIOS_OFICIALES.some((d) => u.hostname === d || u.hostname.endsWith(`.${d}`))) {
      problemas.push(`«${donde}»: «${u.hostname}» no es un dominio oficial (${DOMINIOS_OFICIALES.join(', ')})`);
    }
    if (vistas.has(c.url)) problemas.push(`«${donde}»: URL repetida ${c.url}`);
    vistas.add(c.url);
  }
  return { ok: problemas.length === 0, problemas };
}

/** ¿La lista de avisos de la DMC trae uno de calor? (kind lo asigna el backend: «viento» o «calor»). */
export const hayCalor = (avisos) => (avisos || []).some((a) => a.kind === 'calor');
