/* Estado del historial de avisos: lógica pura, sin DOM ni imports de la app,
 * para probarla con node:test y que la vista solo pinte. */

export function estadoInicial() {
  return { alerts: [], total: 0, nextBefore: null, loading: false, error: '', retry: null };
}

/* Llegó una página del servidor: `more` agrega a lo cargado, sin `more` reemplaza.
 * El error y su reintento se limpian: el intento salió bien. */
export function conPagina(state, data, more) {
  const alerts = more ? [...state.alerts, ...(data.alerts || [])] : (data.alerts || []);
  return {
    ...state, alerts, total: data.total ?? alerts.length,
    nextBefore: data.next_before || null, loading: false, error: '', retry: null,
  };
}

/* Falló la lectura: lo ya cargado se conserva y `retry` recuerda qué pedía el intento. */
export function conFallo(state, mensaje, more) {
  return { ...state, loading: false, error: mensaje, retry: more ? 'siguiente' : 'inicial' };
}
