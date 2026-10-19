/* Consejos de salud para los avisos de calor extremo de la DMC (AGUA-06).
 * Solo datos y una función pura, sin DOM: «Riesgo» los pinta hoy y «Mi zona»
 * podrá usarlos sin repetir el texto. Cero invención: cada consejo lleva la
 * fuente oficial que lo respalda (OMS, MINSAL, SENAPRED o SAMU); si no hay
 * fuente pública, el consejo no se publica.
 * Fuentes consultadas el 19 de octubre de 2026: */
export const CONSULTA_FUENTES = '2026-10-19';

export const NO_OFICIAL = 'BRASA no es una fuente oficial: sigue a SENAPRED (senapred.cl).';

export const CONSEJOS_CALOR = [
  { text: 'Toma agua a cada rato, aunque no sientas sed: con calor extremo el cuerpo se deshidrata sin avisar.',
    source: 'MINSAL: alerta de calor', url: 'https://www.minsal.cl/alerta-de-calor/' },
  { text: 'Evita el sol directo y el ejercicio al aire libre entre las 11 y las 17 h, las horas de más radiación.',
    source: 'SENAPRED: calor extremo', url: 'https://senapred.cl/calor-extremo/' },
  { text: 'Revisa seguido a las personas mayores, los niños y los enfermos crónicos; piel seca y roja, confusión o desmayo son golpe de calor: llama al SAMU 131.',
    source: 'MINSAL · Salud Responde', url: 'https://saludresponde.minsal.cl/altas-temperaturas/' },
];

/** ¿La lista de avisos de la DMC trae uno de calor? (kind lo asigna el backend: «viento» o «calor»). */
export const hayCalor = (avisos) => (avisos || []).some((a) => a.kind === 'calor');
