/* PROD-05: plan de evacuación municipal por comuna, enlazado desde «Mi zona» (piloto: Quintero).
 * Es material de preparación: nunca una ruta segura en tiempo real ni un reemplazo de SENAPRED/SAE. */
const PLANES = { 5107: { nombre: 'Plan comunal de prevención y evacuación ante incendios forestales', entidad: 'Municipalidad de Quintero', url: 'https://www.muniquintero.cl/wp-content/uploads/2026/10/PLAN-COMUNAL-VARIABLE-INCENDIOS-FORESTALES-EDICION-AGOSTO-2026-CON-DECRETO-3.pdf' } };
export const planMunicipal = (code) => PLANES[Number(code)] || null;
