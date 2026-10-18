/**
 * BRASA Chile en Cloudflare.
 *
 * - La PWA (web/) se sirve como assets desde el borde.
 * - /api/* va al backend Python (FastAPI) que corre en un Cloudflare Container (una sola instancia).
 * - El contenedor guarda su respaldo en R2 a través de este Worker: llama a <PUBLIC_BASE_URL>/_internal/storage/<clave>
 *   con su INTERNAL_TOKEN, y el Worker lee o escribe en R2 (el contenedor no tiene credenciales de R2).
 *   La intercepción de salida (outboundByHost → storage.brasa) queda solo como respaldo: en producción
 *   esas solicitudes salían a internet y fallaban con 530.
 * - Un Cron Trigger dispara cada 10 minutos la ingesta GOES/FIRMS, las alertas y el riesgo.
 */
import { Container, getContainer } from '@cloudflare/containers';

export { ContainerProxy } from '@cloudflare/containers';

interface Env {
  ASSETS: Fetcher;
  BUCKET: R2Bucket;
  BACKEND: DurableObjectNamespace<BrasaBackend>;
  INTERNAL_TOKEN: string;
  PUBLIC_BASE_URL?: string;
  FIRMS_MAP_KEY?: string;
  FIRMS_SOURCES?: string;
  ADMIN_TOKEN?: string;
  TELEGRAM_BOT_TOKEN?: string;
  TELEGRAM_BOT_USERNAME?: string;
  TELEGRAM_WEBHOOK_SECRET?: string;
  CESIUM_ION_PUBLIC_TOKEN?: string;
  VAPID_CONTACT?: string;
  TURNSTILE_SITE_KEY?: string;
  TURNSTILE_SECRET?: string;
  REPORTS_LIMITER?: RateLimit;
  SUBSCRIBERS_LIMITER?: RateLimit;
}

const STORAGE_HOST = 'storage.brasa';
const STORAGE_PREFIXES = ['db/', 'photos/'];

/** Almacenamiento del contenedor → R2. Solo claves bajo db/ y photos/. */
async function storageHandler(req: Request, env: Env, path = new URL(req.url).pathname): Promise<Response> {
  const key = decodeURIComponent(path.replace(/^\/+/, ''));
  if (!STORAGE_PREFIXES.some((p) => key.startsWith(p)) || key.includes('..')) {
    return new Response('clave no permitida', { status: 403 });
  }
  if (req.method === 'GET') {
    const object = await env.BUCKET.get(key);
    if (!object) return new Response('no existe', { status: 404 });
    return new Response(object.body, { headers: { 'Content-Type': object.httpMetadata?.contentType || 'application/octet-stream' } });
  }
  if (req.method === 'PUT') {
    const body = await req.arrayBuffer();
    await env.BUCKET.put(key, body, { httpMetadata: { contentType: req.headers.get('Content-Type') || 'application/octet-stream' } });
    // Copia diaria de la base, por si un respaldo defectuoso pisara el anterior.
    if (key === 'db/brasa.db') {
      const day = new Date().toISOString().slice(0, 10);
      await env.BUCKET.put(`db/diario/${day}.db`, body, { httpMetadata: { contentType: 'application/vnd.sqlite3' } });
    }
    return new Response('ok');
  }
  return new Response('método no permitido', { status: 405 });
}

const STORAGE_ROUTE = '/_internal/storage/';

/** Compara el token sin filtrar por tiempo cuántos caracteres coinciden. */
function tokenMatches(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

export class BrasaBackend extends Container<Env> {
  defaultPort = 8000;
  // El cron llega cada 10 min: con 12 min de margen el contenedor queda caliente entre ciclos.
  sleepAfter = '12m';
  enableInternet = true;

  static outboundByHost = {
    [STORAGE_HOST]: (req: Request, env: Env) => storageHandler(req, env),
  };

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    this.envVars = {
      BRASA_STORAGE_URL: env.PUBLIC_BASE_URL ? `${env.PUBLIC_BASE_URL.replace(/\/+$/, '')}${STORAGE_ROUTE.slice(0, -1)}` : `http://${STORAGE_HOST}`,
      BRASA_SCHEDULER: '0',
      INTERNAL_TOKEN: env.INTERNAL_TOKEN ?? '',
      PUBLIC_BASE_URL: env.PUBLIC_BASE_URL ?? '',
      FIRMS_MAP_KEY: env.FIRMS_MAP_KEY ?? '',
      FIRMS_SOURCES: env.FIRMS_SOURCES ?? '',
      ADMIN_TOKEN: env.ADMIN_TOKEN ?? '',
      TELEGRAM_BOT_TOKEN: env.TELEGRAM_BOT_TOKEN ?? '',
      TELEGRAM_BOT_USERNAME: env.TELEGRAM_BOT_USERNAME ?? '',
      TELEGRAM_WEBHOOK_SECRET: env.TELEGRAM_WEBHOOK_SECRET ?? '',
      CESIUM_ION_PUBLIC_TOKEN: env.CESIUM_ION_PUBLIC_TOKEN ?? '',
      VAPID_CONTACT: env.VAPID_CONTACT ?? 'mailto:contacto@example.org',
      TURNSTILE_SITE_KEY: env.TURNSTILE_SITE_KEY ?? '',
      TURNSTILE_SECRET: env.TURNSTILE_SECRET ?? '',
    };
  }

  override onError(error: unknown): void {
    console.error('Error del contenedor BRASA:', error);
  }
}

const backend = (env: Env) => getContainer(env.BACKEND);

/** Igual a backend/security.py (tests/test_security.py lo verifica, incluidos los hashes de los scripts en línea). */
const CSP = "default-src 'self'; script-src 'self' 'sha256-eUoL+i2RTpiq2RS32FuMzQERs2h3pB9ALn8vNTUUPao=' 'sha256-p0zH+UTvt+QVQYNDdrv1l/WdM2Huerh8xgB6wbAH7/E=' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-eval' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; font-src 'self' data: https://cdn.jsdelivr.net; connect-src 'self' https:; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src https://challenges.cloudflare.com; frame-ancestors 'self'";

/** Rutas públicas del sitio → ruta dentro de web/ (el mismo mapa que usa backend/main.py).
 *  Los HTML se piden sin extensión: Workers Assets redirige /index.html → / y /admin.html → /admin. */
function assetPath(pathname: string): string | null {
  if (pathname === '/' || pathname === '/index.html') return '/';
  if (pathname === '/admin') return '/admin';
  if (pathname === '/sw.js' || pathname === '/manifest.webmanifest') return pathname;
  if (pathname === '/robots.txt') return '/robots.txt';
  if (pathname.startsWith('/web/')) return pathname.slice(4);
  return null;
}

async function serveAsset(request: Request, env: Env, path: string): Promise<Response> {
  const url = new URL(request.url);
  url.pathname = path;
  const response = await env.ASSETS.fetch(new Request(url.toString(), request));
  const headers = new Headers(response.headers);
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  headers.set('Permissions-Policy', 'geolocation=(self), camera=(self), microphone=()');
  headers.set('X-Frame-Options', 'SAMEORIGIN');
  headers.set('Strict-Transport-Security', 'max-age=31536000');
  if (path === '/' || path === '/admin') headers.set('Content-Security-Policy', CSP);
  if (path === '/' || path === '/admin' || path === '/sw.js') headers.set('Cache-Control', 'no-cache');
  if (path === '/sw.js') headers.set('Service-Worker-Allowed', '/');
  // Las fuentes no cambian de contenido sin cambiar de nombre: caché de un mes.
  if (path.startsWith('/vendor/fonts/')) headers.set('Cache-Control', 'public, max-age=2592000, immutable');
  return new Response(response.body, { status: response.status, headers });
}

// ---------------------------------------------------------------- caché del borde (OPS-03)

/** GET públicos con copia en la caché del borde y sus segundos de frescura. En un megaincendio
 *  miles de personas abren el mapa a la vez: una copia de 30-60 s quita casi toda la carga del
 *  contenedor sin mostrar datos más viejos que medio ciclo. Vencida, se responde con la copia y
 *  se revalida en segundo plano (stale-while-revalidate): un contenedor lento no se nota. */
const EDGE_CACHE_TTL: Record<string, number> = {
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
const edgeInflight = new Map<string, Promise<Response | null>>();

async function edgeFill(key: Request, request: Request, env: Env, freshFor: number): Promise<Response | null> {
  // Al contenedor se le pide sin comprimir: el borde vuelve a comprimir según cada cliente y una
  // sola variante de la caché sirve a navegadores y a clientes simples.
  const headers = new Headers(request.headers);
  headers.set('accept-encoding', 'identity');
  const response = await proxyToBackend(new Request(request, { headers }), env);
  if (!response.ok || response.headers.has('set-cookie')) return null;
  const stored = new Response(response.body, response);
  stored.headers.set('Cache-Control', `public, max-age=${EDGE_CACHE_KEEP_S}`);
  stored.headers.set(EDGE_FRESH_HEADER, String(Math.floor(Date.now() / 1000) + freshFor));
  await caches.default.put(key, stored.clone());
  return stored;
}

function edgeLoad(key: Request, request: Request, env: Env, freshFor: number): Promise<Response | null> {
  const name = key.url;
  let pending = edgeInflight.get(name);
  if (!pending) {
    pending = edgeFill(key, request, env, freshFor).finally(() => edgeInflight.delete(name));
    edgeInflight.set(name, pending);
  }
  return pending;
}

function serveEdge(hit: Response, kind: string, freshFor: number): Response {
  const out = new Response(hit.body, hit);
  // Lo que vive en el borde (10 min) no es lo que puede guardar el navegador: se repone la frescura.
  out.headers.set('Cache-Control', `public, max-age=${freshFor}`);
  out.headers.set('X-Brasa-Cache', kind);
  return out;
}

async function cachedApi(request: Request, env: Env, ctx: ExecutionContext, freshFor: number): Promise<Response> {
  // La clave lleva solo la URL: cookies y cabeceras personales no dividen la caché.
  const key = new Request(request.url, { method: 'GET' });
  const hit = await caches.default.match(key);
  if (hit) {
    const stale = Number(hit.headers.get(EDGE_FRESH_HEADER) || 0) * 1000 <= Date.now();
    if (stale) ctx.waitUntil(edgeLoad(key, request, env, freshFor));
    return serveEdge(hit, stale ? 'stale' : 'hit', freshFor);
  }
  const filled = (await edgeLoad(key, request, env, freshFor))?.clone() ?? null;
  if (filled) return serveEdge(filled, 'miss', freshFor);
  return proxyToBackend(request, env); // el backend falló o no es cacheable: pasa directo
}

// ------------------------------------------------- límite de solicitudes en el borde (OPS-05)

/** POST públicos con tope en el borde (bindings `ratelimits` de wrangler.jsonc). Es la muralla
 *  de afuera contra inundaciones; el presupuesto fino por hora lo mantiene la app (routes/common.py). */
function edgeLimiter(env: Env, pathname: string): RateLimit | undefined {
  if (pathname === '/api/reports') return env.REPORTS_LIMITER;
  if (pathname === '/api/subscribers') return env.SUBSCRIBERS_LIMITER;
  return undefined;
}

async function proxyToBackend(request: Request, env: Env): Promise<Response> {
  const headers = new Headers(request.headers);
  headers.set('X-Forwarded-For', request.headers.get('CF-Connecting-IP') || '');
  headers.set('X-Forwarded-Proto', 'https');
  try {
    const response = await backend(env).fetch(new Request(request, { headers }));
    // Recién desplegado o despertando, el contenedor puede no estar listo: se responde 503 «iniciando»
    // (la app reintenta sola y muestra «Conectando…») en vez de un 500 que parece una falla.
    if (response.status === 500 && (await response.clone().text()).includes('container is not running')) {
      return Response.json(
        { detail: 'El servidor de BRASA está iniciando. Intenta en unos segundos.' },
        { status: 503, headers: { 'Retry-After': '5' } },
      );
    }
    return response;
  } catch (error) {
    console.error('Backend no disponible:', error);
    return Response.json(
      { detail: 'El servidor de BRASA está iniciando o no está disponible. Intenta en unos segundos.' },
      { status: 503, headers: { 'Retry-After': '10' } },
    );
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname.startsWith('/api/internal')) return new Response('No encontrado', { status: 404 });
    if (pathname.startsWith(STORAGE_ROUTE)) {
      // 403 (no 404): un token equivocado nunca debe parecer «no hay respaldo» y hacer partir con la base vacía.
      if (!tokenMatches(request.headers.get('X-Internal-Token'), env.INTERNAL_TOKEN)) return new Response('Prohibido', { status: 403 });
      return storageHandler(request, env, pathname.slice(STORAGE_ROUTE.length));
    }
    if (request.method === 'POST') {
      const limiter = edgeLimiter(env, pathname);
      if (limiter) {
        const { success } = await limiter.limit({ key: request.headers.get('CF-Connecting-IP') || 'sin-ip' });
        if (!success) {
          return Response.json(
            { detail: { code: 'RATE_LIMITED', message: 'Demasiadas solicitudes. Intenta nuevamente en unos minutos.' } },
            { status: 429, headers: { 'Retry-After': '60' } },
          );
        }
      }
    }
    if (pathname.startsWith('/api/') || pathname === '/docs' || pathname === '/openapi.json') {
      const freshFor = request.method === 'GET'
        ? Object.keys(EDGE_CACHE_TTL).find((p) => pathname === p || pathname.startsWith(`${p}/`))
        : undefined;
      if (freshFor) return cachedApi(request, env, ctx, EDGE_CACHE_TTL[freshFor]);
      return proxyToBackend(request, env);
    }
    const asset = assetPath(pathname);
    if (asset) return serveAsset(request, env, asset);
    return new Response('No encontrado', { status: 404 });
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil((async () => {
      // wait=1: la petición queda abierta hasta que el ciclo termina. Sin esto el contenedor
      // responde 202 al instante y se suspende entre disparos; las tareas del final del ciclo
      // (riesgo, FWI, lluvia) se quedaban a medias y `last_cycle` nunca se cerraba.
      const response = await backend(env).fetch(new Request('http://backend/api/internal/tick?wait=1', {
        method: 'POST',
        headers: { 'X-Internal-Token': env.INTERNAL_TOKEN },
      }));
      console.log('Ciclo BRASA', response.status, await response.text());
    })());
  },
} satisfies ExportedHandler<Env>;
