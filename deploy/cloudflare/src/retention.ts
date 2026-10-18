/** Retención de las copias diarias de la base: la política de privacidad promete que los
 *  respaldos se conservan hasta 24 horas. Solo sintaxis de tipos borrable — la prueba
 *  (test/retention.test.mjs) lo importa directo con `node --test`, sin compilar. */

export const DIARIO_PREFIX = 'db/diario/';

/** Copias diarias se borran a las 24 horas de subidas, no por el nombre del día:
 *  el archivo se sobrescribe todo el día y lo que manda es cuándo se escribió. */
export const RETENCION_MS = 24 * 60 * 60 * 1000;

export function copiasVencidas(objects: { key: string; uploaded: Date }[], nowMs: number): string[] {
  return objects
    .filter((o) => o.key.startsWith(DIARIO_PREFIX) && nowMs - o.uploaded.getTime() > RETENCION_MS)
    .map((o) => o.key);
}
