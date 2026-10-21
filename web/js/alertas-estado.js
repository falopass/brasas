/* Estado del historial de avisos: lógica pura, sin DOM ni imports de la app,
 * para probarla con node:test y que la vista solo pinte. */

export function estadoInicial() {
  return { alerts: [], total: 0, nextBefore: null, loading: false, error: '', retry: null };
}

/* Llegó una página del servidor: `more` agrega a lo cargado, sin `more` reemplaza.
 * El error y su reintento se limpian: el intento salió bien.
 * Un reintento puede traer la misma página dos veces (la respuesta se perdió tras
 * procesarse): deduplica por `id` conservando el orden de llegada, y la copia más
 * nueva reemplaza a la anterior en su posición —el aviso pudo cambiar de estado,
 * feedback o level—. Un aviso sin `id` se conserva tal cual: no se inventa identidad.
 * `total` es siempre el del servidor y la lista nunca queda más larga que él.
 * Si el servidor devuelve el mismo cursor que se pidió, se asume el final:
 * «Cargar más» deja de ofrecerse en vez de pedir la misma página para siempre. */
export function conPagina(state, data, more) {
  const merged = more ? [...state.alerts, ...(data.alerts || [])] : (data.alerts || []);
  const pos = new Map();
  const alerts = [];
  for (const a of merged) {
    if (a?.id == null) { alerts.push(a); continue; }
    if (pos.has(a.id)) { alerts[pos.get(a.id)] = a; continue; }
    pos.set(a.id, alerts.length);
    alerts.push(a);
  }
  const total = data.total ?? alerts.length;
  const cursorPedido = more ? state.nextBefore : null;
  return {
    ...state,
    alerts: Number.isFinite(total) ? alerts.slice(0, total) : alerts,
    total,
    nextBefore: data.next_before && data.next_before !== cursorPedido ? data.next_before : null,
    loading: false, error: '', retry: null,
  };
}

/* Falló la lectura: lo ya cargado se conserva y `retry` recuerda qué pedía el intento. */
export function conFallo(state, mensaje, more) {
  return { ...state, loading: false, error: mensaje, retry: more ? 'siguiente' : 'inicial' };
}
