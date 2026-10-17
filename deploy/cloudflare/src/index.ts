/**
 * BRASA Chile en Cloudflare.
 *
 * - La PWA (web/) se sirve como assets desde el borde.
 * - /api/* va al backend Python (FastAPI) que corre en un Cloudflare Container (una sola instancia).
 * - El contenedor guarda su respaldo en R2 a través de este Worker: sus solicitudes a
 *   http://storage.brasa/<clave> se interceptan aquí (sin credenciales dentro del contenedor).
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
}

const STORAGE_HOST = 'storage.brasa';
const STORAGE_PREFIXES = ['db/', 'photos/'];

/** Almacenamiento del contenedor → R2. Solo claves bajo db/ y photos/. */
async function storageHandler(req: Request, env: Env): Promise<Response> {
  const key = decodeURIComponent(new URL(req.url).pathname.replace(/^\/+/, ''));
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
      BRASA_STORAGE_URL: `http://${STORAGE_HOST}`,
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
    };
  }

  override onError(error: unknown): void {
    console.error('Error del contenedor BRASA:', error);
  }
}

const backend = (env: Env) => getContainer(env.BACKEND);

/** Rutas públicas del sitio → ruta dentro de web/ (el mismo mapa que usa backend/main.py).
 *  Los HTML se piden sin extensión: Workers Assets redirige /index.html → / y /admin.html → /admin. */
function assetPath(pathname: string): string | null {
  if (pathname === '/' || pathname === '/index.html') return '/';
  if (pathname === '/admin') return '/admin';
  if (pathname === '/sw.js' || pathname === '/manifest.webmanifest') return pathname;
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
  if (path === '/' || path === '/admin' || path === '/sw.js') headers.set('Cache-Control', 'no-cache');
  if (path === '/sw.js') headers.set('Service-Worker-Allowed', '/');
  return new Response(response.body, { status: response.status, headers });
}

async function proxyToBackend(request: Request, env: Env): Promise<Response> {
  const headers = new Headers(request.headers);
  headers.set('X-Forwarded-For', request.headers.get('CF-Connecting-IP') || '');
  headers.set('X-Forwarded-Proto', 'https');
  try {
    return await backend(env).fetch(new Request(request, { headers }));
  } catch (error) {
    console.error('Backend no disponible:', error);
    return Response.json(
      { detail: 'El servidor de BRASA está iniciando o no está disponible. Intenta en unos segundos.' },
      { status: 503, headers: { 'Retry-After': '10' } },
    );
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname.startsWith('/api/internal')) return new Response('No encontrado', { status: 404 });
    if (pathname.startsWith('/api/') || pathname === '/docs' || pathname === '/openapi.json') {
      return proxyToBackend(request, env);
    }
    const asset = assetPath(pathname);
    if (asset) return serveAsset(request, env, asset);
    return new Response('No encontrado', { status: 404 });
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil((async () => {
      const response = await backend(env).fetch(new Request('http://backend/api/internal/tick', {
        method: 'POST',
        headers: { 'X-Internal-Token': env.INTERNAL_TOKEN },
      }));
      console.log('Ciclo BRASA', response.status, await response.text());
    })());
  },
} satisfies ExportedHandler<Env>;
