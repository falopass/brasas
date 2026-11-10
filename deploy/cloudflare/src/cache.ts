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
import { claveCopia, COPIA_MAX_AGE_MS, esUrlCanonica, META_GENERADA } from './copias.ts';
import type { BucketCopias } from './copias.ts';

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
  // Banderas y claves públicas del cliente: la misma respuesta para todos, sin nada por
  // dispositivo. 60 s bastan: la app además guarda la última copia y la refresca sola.
  '/api/config': 60,
};

/** La copia vive hasta 10 min en el borde: es el máximo para seguir respondiendo con el dato
 *  anterior si el contenedor no responde. Al cliente se le entrega con la frescura de su ruta. */
const EDGE_CACHE_KEEP_S = 600;
const EDGE_FRESH_HEADER = 'x-brasa-fresh-until';

/** Sello (segundos de época) de cuándo se produjo el dato guardado: en `edgeFill` es su
 *  llenado y en una copia de R2 es su `generada`. Lo usan la corrección de edad de
 *  `/api/status` y la comparación borde↔R2, para no pisar una respuesta del contenedor
 *  más nueva que la copia. */
const EDGE_GENERADA_HEADER = 'x-brasa-generada';

/** Una recarga por clave y por aislamiento del Worker: la estampida tras un vencimiento pega una vez al contenedor. */
const edgeInflight = new Map<string, Promise<Response>>();

/** Último intento de recarga por clave: con el contenedor caído no se reintenta más de una vez por
 *  ventana de frescura, o cada visita a la copia vencida pegaría de nuevo al contenedor.
 *  Acotado por REINTENTOS_MAX (reintentos.ts lo expulsa FIFO). */
const edgeLastTry = new Map<string, number>();

/** Última consulta a R2 por clave canónica: a lo más una por ventana de frescura, igual que
 *  edgeLastTry acota la recarga al contenedor — si no, cada visita con el borde vencido
 *  pagaría una lectura de R2. */
const copiaLastTry = new Map<string, number>();

async function edgeFill(key: Request, request: Request, alBackend: AlBackend, freshFor: number): Promise<Response> {
  // Al contenedor se le pide sin comprimir: el borde vuelve a comprimir según cada cliente y una
  // sola variante de la caché sirve a navegadores y a clientes simples.
  const headers = new Headers(request.headers);
  headers.set('accept-encoding', 'identity');
  const response = await alBackend(new Request(request, { headers }));
  if (!response.ok || response.headers.has('set-cookie')) return response;
  const stored = new Response(response.body, response);
  const ahora_s = Math.floor(Date.now() / 1000);
  stored.headers.set('Cache-Control', `public, max-age=${EDGE_CACHE_KEEP_S}`);
  stored.headers.set(EDGE_GENERADA_HEADER, String(ahora_s));
  stored.headers.set(EDGE_FRESH_HEADER, String(ahora_s + freshFor));
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

async function serveStaleStatus(hit: Response, kind: string, freshFor: number): Promise<Response> {
  // El estado declara la edad del dato calculada al generarse; vencida, se corrige para no
  // presentar información vieja como vigente (la píldora «Datos de hace N min» dice la verdad).
  const out = serveEdge(hit, kind, freshFor);
  try {
    const data: any = await out.clone().json();
    const f = data?.freshness;
    if (!f || typeof f.stale_after_s !== 'number') return out;
    const generada_s = Number(hit.headers.get(EDGE_GENERADA_HEADER) || 0)
      || Number(hit.headers.get(EDGE_FRESH_HEADER)) - freshFor;
    const elapsed_s = Math.max(0, Math.floor(Date.now() / 1000) - generada_s);
    if (!elapsed_s) return out;
    // Misma regla que backend/freshness.py: viejo si no hay marca o la edad pasa su umbral,
    // y una familia también con 2+ corridas seguidas en error pasada la regla base. El `stale`
    // global es la disyunción — una fuente atrasada (GOES caída) no puede quedar oculta.
    if (typeof f.age_seconds === 'number') f.age_seconds += elapsed_s;
    let vieja = f.age_seconds == null || f.age_seconds > f.stale_after_s;
    if (f.products && typeof f.products === 'object') {
      for (const p of Object.values(f.products) as any[]) {
        if (!p) continue;
        if (typeof p.age_seconds === 'number') p.age_seconds += elapsed_s;
        const limite = typeof p.stale_after_s === 'number' ? p.stale_after_s : f.stale_after_s;
        p.stale = p.age_seconds == null || p.age_seconds > limite
          || (Number(p.fallos_seguidos) >= 2 && p.age_seconds > f.stale_after_s);
        vieja = vieja || p.stale;
      }
    }
    f.stale = vieja;
    const rewritten = new Response(JSON.stringify(data), out);
    // El JSON cambió de largo: con el Content-Length viejo la respuesta quedaba truncada.
    rewritten.headers.delete('content-length');
    return rewritten;
  } catch { /* cuerpo no JSON: se entrega tal cual */ }
  return out;
}

/** La copia de R2 de una URL canónica, lista para guardar en el borde, o null si no
 *  existe, ya venció (más de COPIA_MAX_AGE_MS), es más vieja que lo que el borde ya
 *  guarda (`minGenerada`) o R2 falló. La frescura queda anclada a la lectura (igual que
 *  `edgeFill` ancla a su llenado) y el sello `x-brasa-generada` conserva el instante en
 *  que se produjo el dato: así `serveStaleStatus` corrige la edad desde la generación
 *  real y el borde absorbe el tráfico durante su ventana. */
async function leerCopiaVigente(url: URL, copias: BucketCopias, freshFor: number, minGenerada: number): Promise<Response | null> {
  let objeto;
  try {
    objeto = await copias.get(claveCopia(url.pathname + url.search));
  } catch (error) {
    console.error('No se pudo leer la copia pública de R2:', error);
    return null;
  }
  if (!objeto) return null;
  const generada = Number(objeto.customMetadata?.[META_GENERADA]);
  if (!Number.isFinite(generada) || Date.now() - generada >= COPIA_MAX_AGE_MS || generada < minGenerada) return null;
  const ahora_s = Math.floor(Date.now() / 1000);
  return new Response(objeto.body, {
    headers: {
      'content-type': objeto.httpMetadata?.contentType || 'application/json',
      'Cache-Control': `public, max-age=${EDGE_CACHE_KEEP_S}`,
      [EDGE_FRESH_HEADER]: String(ahora_s + freshFor),
      [EDGE_GENERADA_HEADER]: String(Math.floor(generada / 1000)),
    },
  });
}

export async function cachedApi(request: Request, ctx: ExecutionContext, freshFor: number, alBackend: AlBackend, copias?: BucketCopias): Promise<Response> {
  // La clave lleva solo la URL: cookies y cabeceras personales no dividen la caché.
  const key = new Request(request.url, { method: 'GET' });
  const hit = await caches.default.match(key);
  const url = new URL(request.url);
  if (hit) {
    const stale = Number(hit.headers.get(EDGE_FRESH_HEADER) || 0) * 1000 <= Date.now();
    if (!stale) return serveEdge(hit, 'hit', freshFor);
  }
  // Sin copia vigente en el borde (ausente o vencida): una URL canónica mira la copia
  // de R2 antes de tocar al contenedor (OPS-817), porque despertarlo cuesta ~28 s. Una
  // entrada sin sello de generación no se puede comparar y una copia que no la adelanta
  // no la pisa: en ambos casos se conserva el camino vencida + revalidación de siempre.
  if (copias && esUrlCanonica(url)) {
    const generadaBorde = hit ? Number(hit.headers.get(EDGE_GENERADA_HEADER) || 0) * 1000 || Infinity : 0;
    if (generadaBorde < Infinity && (copiaLastTry.get(key.url) || 0) <= Date.now() - freshFor * 1000) {
      recuerdaIntento(copiaLastTry, key.url, Date.now());
      const copia = await leerCopiaVigente(url, copias, freshFor, generadaBorde);
      if (copia) {
        await caches.default.put(key, copia.clone());
        return url.pathname === '/api/status' ? serveStaleStatus(copia, 'snapshot', freshFor) : serveEdge(copia, 'snapshot', freshFor);
      }
    }
  }
  if (hit) {
    if ((edgeLastTry.get(key.url) || 0) < Date.now() - freshFor * 1000) ctx.waitUntil(edgeLoad(key, request, alBackend, freshFor));
    return url.pathname === '/api/status' ? serveStaleStatus(hit, 'stale', freshFor) : serveEdge(hit, 'stale', freshFor);
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
