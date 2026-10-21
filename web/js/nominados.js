/* Filtro de incendios nominados por comuna y temporada (sin DOM: se prueba con node:test). */

/* Nombre comparable: minúsculas, sin tildes ni «ñ», espacios simples (igual que fold() de pantalla.js). */
export const foldComuna = (s) => (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

/** Ítems que calzan con la comuna escrita (texto libre) y la temporada elegida, de mayor a menor superficie. */
export function filterNominados(items, { comuna = '', season = '' } = {}) {
  const key = foldComuna(comuna);
  return items
    .filter((i) => (!season || i.season === season) && (!key || foldComuna(i.comuna).includes(key)))
    .sort((a, b) => (b.ha || 0) - (a.ha || 0));
}

export const sumHa = (rows) => rows.reduce((s, i) => s + (i.ha || 0), 0);
