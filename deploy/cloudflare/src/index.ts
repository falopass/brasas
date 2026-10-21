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
import { copiasVencidas, DIARIO_PREFIX } from './retention';
import { assetPath, backendPath, sharePreview, sharePreviewResponse } from './rutas';
import { securityHeaders, tokenMatches } from './guardas';
import { bytesDeClave, cifrarRespaldo, descifrarRespaldo } from './cifrado';
import { cachedApi, EDGE_CACHE_TTL } from './cache';

export { securityHeaders, tokenMatches };

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
  DB_ENC_KEY?: string;
}

const STORAGE_HOST = 'storage.brasa';
const STORAGE_PREFIXES = ['db/', 'photos/'];

/** Almacenamiento del contenedor → R2. Solo claves bajo db/ y photos/. */
async function storageHandler(req: Request, env: Env, path = new URL(req.url).pathname): Promise<Response> {
  const key = decodeURIComponent(path.replace(/^\/+/, ''));
  if (!STORAGE_PREFIXES.some((p) => key.startsWith(p)) || key.includes('..')) {
    return new Response('clave no permitida', { status: 403 });
  }
  // SEC-06: las claves db/* llevan los datos de las personas y reposan cifradas (AES-256-GCM)
  // en R2; la clave es el secreto DB_ENC_KEY. Las fotos quedan como están.
  const clave = key.startsWith('db/') ? bytesDeClave(env.DB_ENC_KEY) : null;
  if (req.method === 'GET') {
    const object = await env.BUCKET.get(key);
    if (!object) return new Response('no existe', { status: 404 });
    const headers = { 'Content-Type': object.httpMetadata?.contentType || 'application/octet-stream' };
    if (!key.startsWith('db/')) return new Response(object.body, { headers });
    try {
      return new Response(await descifrarRespaldo(clave, await object.arrayBuffer()), { headers });
    } catch (error) {
      console.error(`No se pudo descifrar ${key}:`, error);
      return new Response('respaldo cifrado: DB_ENC_KEY ausente o incorrecta', { status: 500 });
    }
  }
  if (req.method === 'PUT') {
    const body = await req.arrayBuffer();
    // Sin clave se rechaza la subida en vez de dejar la base en claro: el fallo queda
    // visible en backup_error de /api/status hasta que se configure DB_ENC_KEY.
    if (key.startsWith('db/') && !clave) return new Response('DB_ENC_KEY no configurada o inválida en el Worker', { status: 500 });
    await env.BUCKET.put(key, clave ? await cifrarRespaldo(clave, body) : body, { httpMetadata: { contentType: req.headers.get('Content-Type') || 'application/octet-stream' } });
    // Copia diaria de la base, por si un respaldo defectuoso pisara el anterior (IV propio).
    if (key === 'db/brasa.db') {
      const day = new Date().toISOString().slice(0, 10);
      const copia = clave ? await cifrarRespaldo(clave, body) : body;
      await env.BUCKET.put(`db/diario/${day}.db`, copia, { httpMetadata: { contentType: 'application/vnd.sqlite3' } });
    }
    return new Response('ok');
  }
  return new Response('método no permitido', { status: 405 });
}

const STORAGE_ROUTE = '/_internal/storage/';

/** Borra las copias `db/diario/` con más de 24 horas (el cron las barre cada 10 minutos). */
async function pruneDailyCopies(env: Env): Promise<void> {
  try {
    const list = await env.BUCKET.list({ prefix: DIARIO_PREFIX });
    const vencidas = copiasVencidas(list.objects, Date.now());
    if (vencidas.length) await env.BUCKET.delete(vencidas);
  } catch (error) {
    console.error('No se pudieron borrar las copias diarias vencidas:', error);
  }
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
const CSP = "default-src 'self'; script-src 'self' 'sha256-eUoL+i2RTpiq2RS32FuMzQERs2h3pB9ALn8vNTUUPao=' 'sha256-+wse2WpUTWtZGnnnNWFw1BQigwl2iD/hE3FBP5Euz9s=' 'sha256-p0zH+UTvt+QVQYNDdrv1l/WdM2Huerh8xgB6wbAH7/E=' 'sha256-kmXeAukLKNxKmB8usZ0mMw3+GQ9GZV5RKcRS8d/h6AY=' https://cdn.jsdelivr.net https://challenges.cloudflare.com 'unsafe-eval' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; font-src 'self' data: https://cdn.jsdelivr.net; connect-src 'self' https:; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src https://challenges.cloudflare.com; frame-ancestors 'self'";

async function serveAsset(request: Request, env: Env, path: string): Promise<Response> {
  const url = new URL(request.url);
  url.pathname = path;
  const response = await env.ASSETS.fetch(new Request(url.toString(), request));
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(securityHeaders(path, CSP))) headers.set(name, value);
  return new Response(response.body, { status: response.status, headers });
}

// ------------------------------------------- caché del borde (OPS-03): vive en cache.ts

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
    if (backendPath(pathname)) {
      const freshFor = request.method === 'GET'
        ? Object.keys(EDGE_CACHE_TTL).find((p) => pathname === p || pathname.startsWith(`${p}/`))
        : undefined;
      const response = freshFor
        ? await cachedApi(request, ctx, EDGE_CACHE_TTL[freshFor], (req) => proxyToBackend(req, env))
        : await proxyToBackend(request, env);
      return sharePreview(pathname) ? sharePreviewResponse(response) : response;
    }
    const asset = assetPath(pathname);
    if (asset) return serveAsset(request, env, asset);
    return new Response('No encontrado', { status: 404 });
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    // Copias diarias de la base: se conservan hasta 24 horas y luego se borran.
    ctx.waitUntil(pruneDailyCopies(env));
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
