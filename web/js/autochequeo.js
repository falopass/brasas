/* Chequeo del producto desde el navegador (AUTO-11): módulo puro, sin DOM.
 * Pide con GET (mismo origen) las páginas y los endpoints que el vecino realmente
 * abre, mide cuánto tardan y dice qué hacer si algo falla. Nunca lanza: el fallo
 * de una sonda ES el resultado. */

export const TARGETS = [
  '/web/index.html', '/web/lite.html', '/web/lista.html', '/web/plan.html',
  '/web/preguntas.html', '/web/datos.html', '/web/respuesta.html', '/web/pantalla.html',
  '/web/admin.html',
  '/api/status', '/api/incidents', '/api/observations', '/api/risk', '/api/opendata', '/api/panorama',
];

export const LENTO_MS = 2500;
const TIMEOUT_MS = 8000;

/** Un objetivo con timeout de 8 s; devuelve {target, status, ms, ok, error}. */
export async function sonda(target, fetchImpl = fetch, nowFn = () => performance.now()) {
  const t0 = nowFn();
  try {
    const res = await fetchImpl(target, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    return { target, status: res.status, ms: Math.round(nowFn() - t0), ok: res.ok, error: null };
  } catch (err) {
    return { target, status: 0, ms: Math.round(nowFn() - t0), ok: false, error: err?.name === 'TimeoutError' || err?.name === 'AbortError' ? 'timeout' : 'sin conexión' };
  }
}

/** Todas las sondas en serie (suave con el servidor); devuelve la lista en el orden de TARGETS. */
export async function run(fetchImpl = fetch, nowFn = () => performance.now()) {
  const out = [];
  for (const t of TARGETS) out.push(await sonda(t, fetchImpl, nowFn));
  return out;
}

/** {total, ok, lentos, fallidos, peor}: «lento» pasa de LENTO_MS; «peor» es el más lento de los fallidos o lentos. */
export function summarize(results = []) {
  const fallidos = results.filter((r) => !r.ok);
  const lentos = results.filter((r) => r.ok && r.ms > LENTO_MS);
  const candidatos = [...fallidos, ...lentos];
  return {
    total: results.length,
    ok: results.length - fallidos.length,
    lentos: lentos.length,
    fallidos: fallidos.length,
    peor: candidatos.length ? candidatos.reduce((a, b) => (b.ms > a.ms ? b : a)) : null,
  };
}

/** Una frase por caso, sin jerga. */
export function advice(res) {
  if (!res.ok) {
    if (res.status >= 500) return 'el servidor está fallando en esta ruta';
    if (res.error === 'timeout') return 'tu conexión o el servidor no respondieron: prueba el modo liviano';
    return res.status === 0 ? 'no se pudo conectar: revisa tu señal' : `respondió con error ${res.status}`;
  }
  if (res.ms > LENTO_MS) return 'tarda demasiado: revísalo antes de la temporada';
  return 'responde bien';
}
