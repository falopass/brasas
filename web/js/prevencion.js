/* UX-62: «Qué hacer hoy» según el nivel de riesgo de la comuna — módulo puro sin DOM.
 * Mismo patrón que calor.js: cada acción con su fuente oficial y su fecha de revisión;
 * un consejo sin fuente no se publica. Los textos salen de lo que ya dice la app
 * (Prepárate, Qué hago y la guía de avisos), no de redacción nueva. */
export const CONSULTA_FUENTES = '2026-10-23';

const MANUAL_CONAF = 'https://oficinavirtual.conaf.cl/archivos/recursos/insumos_tecnicos/Proteccion%20de%20Incendios%20Forestales/Manual%20comunitario%20%202022.pdf';
const COMUNIDADES_CONAF = 'https://www.conaf.cl/incendios/prevencion-y-mitigacion/comunidades-preparadas-frente-a-los-incendios-forestales/';
const SENAPRED_INCENDIOS = 'https://senapred.cl/incendios-forestales/';

// Días con aviso de calor de la DMC: las recomendaciones de salud van delante (MINSAL).
export const CALOR = [
  { text: 'toma agua a cada rato aunque no sientas sed', source: 'MINSAL', url: 'https://saludresponde.minsal.cl/altas-temperaturas/' },
  { text: 'evita el sol y el esfuerzo físico en las horas de más calor', source: 'SENAPRED', url: 'https://senapred.cl/calor-extremo/' },
];

export const ACCIONES = {
  bajo: [
    { text: 'revisa el plan familiar y el punto de encuentro', source: 'CONAF, Manual Comunitario', url: MANUAL_CONAF },
    { text: 'confirma que la vía de salida y el acceso de Bomberos estén despejados', source: 'CONAF', url: COMUNIDADES_CONAF },
  ],
  moderado: [
    { text: 'ten la mochila de emergencia y los documentos a mano', source: 'CONAF, Manual Comunitario', url: MANUAL_CONAF },
    { text: 'avisa a la persona mayor o a quien necesite ayuda para salir', source: 'SENAPRED', url: SENAPRED_INCENDIOS },
  ],
  alto: [
    { text: 'no hagas quemas ni uses herramientas que hagan chispas', source: 'CONAF', url: COMUNIDADES_CONAF },
    { text: 'despeja 10 metros alrededor de la casa y ten agua y una pala a mano', source: 'CONAF, Manual Comunitario', url: MANUAL_CONAF },
    { text: 'confirma con la persona mayor o quien necesite ayuda: con suerte tienen que salir temprano', source: 'SENAPRED', url: SENAPRED_INCENDIOS },
  ],
  extremo: [
    { text: 'no hagas quemas ni uses nada que haga chispas: cualquier brasa puede iniciar un incendio', source: 'CONAF', url: COMUNIDADES_CONAF },
    { text: 'deja la mochila, los documentos y la vía de salida listos, y avisa a quien necesite ayuda', source: 'SENAPRED', url: SENAPRED_INCENDIOS },
    { text: 'sigue a SENAPRED y a Bomberos; si te ordenan evacuar, sal de inmediato', source: 'SENAPRED', url: SENAPRED_INCENDIOS },
  ],
};

const NIVEL_PALABRA = { bajo: 'bajo', moderado: 'moderado', alto: 'alto', extremo: 'extremo' };

/** Acciones del día: las del nivel, con las de calor de MINSAL delante si hay aviso
 * de calor, sin duplicar textos. Nivel desconocido → []. */
export function accionesHoy(level, { calor = false } = {}) {
  const base = ACCIONES[level] || [];
  const todas = calor ? [...CALOR, ...base] : base;
  const vistos = new Set();
  return todas.filter((a) => a?.text && !vistos.has(a.text) && vistos.add(a.text));
}

/** La línea visible: «Hoy el riesgo es alto en tu comuna: <primera acción>.»
 * Sin nivel válido → cadena vacía. */
export function resumenHoy(level, opts = {}) {
  const acciones = accionesHoy(level, opts);
  if (!acciones.length || !NIVEL_PALABRA[level]) return '';
  return `Hoy el riesgo es ${NIVEL_PALABRA[level]} en tu comuna: ${acciones[0].text}.`;
}
