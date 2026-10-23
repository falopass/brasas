/* Resumen del historial de avisos por lugar (ALR-28): módulo puro, sin DOM.
 * `summaryByPlace(alerts)` devuelve [{ place, total, urgente, aviso,
 * kinds: {oficial, reporte, diario, prueba}, feedback: {sirvio, no_sirvio, quema} }]
 * ordenado por total descendente y, en empate, por nombre (es).
 * Avisos sin place → place: null (la vista los rotula «Sin lugar»); un kind o
 * feedback desconocido no se cuenta en ninguna categoría pero sí en `total`. */

const KINDS = ['oficial', 'reporte', 'diario', 'prueba'];
const FEEDBACK = ['sirvio', 'no_sirvio', 'quema'];

export function summaryByPlace(alerts) {
  const porLugar = new Map();
  for (const a of alerts || []) {
    const place = a?.place?.name || null;
    if (!porLugar.has(place)) {
      porLugar.set(place, {
        place, total: 0, urgente: 0, aviso: 0,
        kinds: Object.fromEntries(KINDS.map((k) => [k, 0])),
        feedback: Object.fromEntries(FEEDBACK.map((f) => [f, 0])),
      });
    }
    const fila = porLugar.get(place);
    fila.total += 1;
    if (a?.level === 'urgente') fila.urgente += 1;
    else if (a?.level === 'aviso') fila.aviso += 1;
    if (KINDS.includes(a?.kind)) fila.kinds[a.kind] += 1;
    if (FEEDBACK.includes(a?.feedback)) fila.feedback[a.feedback] += 1;
  }
  return [...porLugar.values()].sort((x, y) => y.total - x.total || (x.place || 'Sin lugar').localeCompare(y.place || 'Sin lugar', 'es'));
}
