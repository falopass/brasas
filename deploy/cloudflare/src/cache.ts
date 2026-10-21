/** Caché del borde para los GET públicos de la API (OPS-03).
 *
 * En un megaincendio miles de personas abren el mapa a la vez: una copia de 30-60 s
 * quita casi toda la carga del contenedor sin mostrar datos más viejos que medio ciclo.
 * Vencida, se responde con la copia y se revalida en segundo plano (stale-while-revalidate).
 *
 * Vive en su propio módulo (sin dependencias del Worker) para que las pruebas lo importen
 * directo con `node --test`: el backend se inyecta como `alBackend`. Solo sintaxis de tipos
 * borrable, igual que reintentos.ts. */
import { recuerdaIntento } from './reintentos.ts';

type AlBackend = (request: Request) => Promise<Response>;

/** GET públicos con copia en la caché del borde y sus segundos de frescura. En un megaincendio
 *  miles de personas abren el mapa a la vez: una copia de 30-60 s quita casi toda la carga del
 *  contenedor sin mostrar datos más viejos que medio ciclo. Vencida, se responde con la copia y
 *  se revalida en segundo plano (stale-while-revalidate): un contenedor lento no se nota. */
export const EDGE_CACHE_TTL: Record<string, number> = {
  '/api/observations': 45,
  '/api/incidents': 45,
  '/api/official-fires': 60,
  '/api/risk': 60,
  '/api/status': 30,
};

/** La copia vive hasta 10 min en el borde: es el máximo para seguir respondiendo con el dato
 *  anterior si el contenedor no responde. Al cliente se le entrega con la frescura de su ruta. */
const EDGE_CACHE_KEEP_S = 600;
const EDGE_FRESH_HEADER = 'x-brasa-fresh-until';

/** Una recarga por clave y por aislamiento del Worker: la estampida tras un vencimiento pega una vez al contenedor. */
const edgeInflight = new Map<string, Promise<Response>>();

/** Último intento de recarga por clave: con el contenedor caído no se reintenta más de una vez por
 *  ventana de frescura, o cada visita a la copia vencida pegaría de nuevo al contenedor.
 *  Acotado por REINTENTOS_MAX (reintentos.ts lo expulsa FIFO). */
const edgeLastTry = new Map<string, number>();

async function edgeFill(key: Request, request: Request, alBackend: AlBackend, freshFor: number): Promise<Response> {
  // Al contenedor se le pide sin comprimir: el borde vuelve a comprimir según cada cliente y una
  // sola variante de la caché sirve a navegadores y a clientes simples.
  const headers = new Headers(request.headers);
  headers.set('accept-encoding', 'identity');
  const response = await alBackend(new Request(request, { headers }));
  if (!response.ok || response.headers.has('set-cookie')) return response;
  const stored = new Response(response.body, response);
  stored.headers.set('Cache-Control', `public, max-age=${EDGE_CACHE_KEEP_S}`);
  stored.headers.set(EDGE_FRESH_HEADER, String(Math.floor(Date.now() / 1000) + freshFor));
  await caches.default.put(key, stored.clone());
  return stored;
}

function edgeLoad(key: Request, request: Request, alBackend: AlBackend, freshFor: number): Promise<Response> {
  const name = key.url;
  recuerdaIntento(edgeLastTry, name, Date.now());
  let pending = edgeInflight.get(name);
  if (!pending) {
    pending = edgeFill(key, request, alBackend, freshFor).finally(() => edgeInflight.delete(name));
    edgeInflight.set(name, pending);
  }
  return pending;
}

function serveEdge(hit: Response, kind: string, freshFor: number): Response {
  const out = new Response(hit.body, hit);
  // Lo que vive en el borde (10 min) no es lo que puede guardar el navegador: se repone la frescura.
  // Vencida, no se deja guardar: la próxima consulta vuelve al borde y dispara la revalidación.
  out.headers.set('Cache-Control', kind === 'stale' ? 'public, max-age=0' : `public, max-age=${freshFor}`);
  out.headers.set('X-Brasa-Cache', kind);
  return out;
}

async function serveStaleStatus(hit: Response, freshFor: number): Promise<Response> {
  // El estado declara la edad del dato calculada al generarse; vencida, se corrige para no
  // presentar información vieja como vigente (la píldora «Datos de hace N min» dice la verdad).
  const out = serveEdge(hit, 'stale', freshFor);
  try {
    const data: any = await out.clone().json();
    const f = data?.freshness;
    if (typeof f?.age_seconds === 'number' && typeof f?.stale_after_s === 'number') {
      const generatedAt = Number(hit.headers.get(EDGE_FRESH_HEADER)) - freshFor;
      f.age_seconds += Math.max(0, Math.floor(Date.now() / 1000) - generatedAt);
      f.stale = f.age_seconds > f.stale_after_s;
      const rewritten = new Response(JSON.stringify(data), out);
      // El JSON cambió de largo: con el Content-Length viejo la respuesta quedaba truncada.
      rewritten.headers.delete('content-length');
      return rewritten;
    }
  } catch { /* cuerpo no JSON: se entrega tal cual */ }
  return out;
}

export async function cachedApi(request: Request, ctx: ExecutionContext, freshFor: number, alBackend: AlBackend): Promise<Response> {
  // La clave lleva solo la URL: cookies y cabeceras personales no dividen la caché.
  const key = new Request(request.url, { method: 'GET' });
  const hit = await caches.default.match(key);
  if (hit) {
    const stale = Number(hit.headers.get(EDGE_FRESH_HEADER) || 0) * 1000 <= Date.now();
    if (stale && (edgeLastTry.get(key.url) || 0) < Date.now() - freshFor * 1000) ctx.waitUntil(edgeLoad(key, request, alBackend, freshFor));
    if (!stale) return serveEdge(hit, 'hit', freshFor);
    return new URL(request.url).pathname === '/api/status' ? serveStaleStatus(hit, freshFor) : serveEdge(hit, 'stale', freshFor);
  }
  const filled = (await edgeLoad(key, request, alBackend, freshFor)).clone();
  if (filled.headers.has(EDGE_FRESH_HEADER)) return serveEdge(filled, 'miss', freshFor);
  // No se pudo guardar (el contenedor falló o la respuesta trae set-cookie): se entrega esa misma
  // respuesta sin volver a consultar, y sin dejar que ninguna caché la retenga. Ojo: la respuesta
  // del binding llega con cabeceras inmutables y su .clone() también, así que hay que reconstruirla
  // antes de marcarla — un `headers.set` directo lanzaba TypeError y Cloudflare respondía 1101
  // en vez del 4xx/5xx real (OPS-34).
  const out = new Response(filled.body, filled);
  out.headers.set('Cache-Control', 'no-store');
  out.headers.set('X-Brasa-Cache', 'pass');
  return out;
}
