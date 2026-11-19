/* PROD-05: planes de evacuación municipales publicados, enlazados desde «Mi zona».
 * Piloto: Quintero (plan comunal de incendios forestales, Municipalidad de Quintero).
 * Cada recurso lleva su fuente y la fecha de consulta. Un documento municipal es
 * material de preparación: nunca una ruta segura en tiempo real ni un reemplazo de
 * las órdenes de SENAPRED y del SAE, y BRASA no afirma que el plan esté vigente. */
export const CONSULTA_FUENTES = '2026-11-19';

const PLAN_QUINTERO = {
  comuna: 'Quintero',
  nombre: 'Plan comunal de prevención y evacuación ante incendios forestales',
  entidad: 'Municipalidad de Quintero',
  url: 'https://www.muniquintero.cl/wp-content/uploads/2026/10/PLAN-COMUNAL-VARIABLE-INCENDIOS-FORESTALES-EDICION-AGOSTO-2026-CON-DECRETO-3.pdf',
};

const POR_CODIGO = { 5107: PLAN_QUINTERO }; // 5107 = Quintero (Valparaíso), según web/data/comunas-index.json

/** El plan municipal de la comuna de un lugar guardado, o null si la comuna no tiene uno enlazado. */
export function planMunicipal(code) {
  return POR_CODIGO[Number(code)] || null;
}
