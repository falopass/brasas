/** Copias públicas en R2 (OPS-817): las respuestas canónicas que la app pide al
 *  cargar se guardan en el bucket tras cada ciclo de ingesta y el borde las sirve
 *  mientras el contenedor despierta, sin pagar el arranque en frío (~28 s medido).
 *  Sin dependencias del Worker, igual que cache.ts: las pruebas lo importan directo
 *  con `node --test` — solo sintaxis de tipos borrable. */

/** Prefijo de las copias en el bucket. El contenedor no escribe aquí: storageHandler
 *  (index.ts) solo admite claves bajo db/ y photos/. */
export const COPIAS_PREFIX = 'public/';

/** customMetadata con el instante de generación (epoch en milisegundos, como texto). */
export const META_GENERADA = 'generada';

/** La copia se sirve mientras tenga menos de 25 minutos: el cron la renueva cada
 *  10 min, así que una más vieja indica que el ciclo lleva rato sin escribir
 *  (contenedor caído o último ciclo fallido) y el borde vuelve a su camino de antes. */
export const COPIA_MAX_AGE_MS = 25 * 60 * 1000;

/** Las URL exactas que la app pide al cargar: idénticas para todas las personas y
 *  solo cambian cuando corre la ingesta. Salen de web/js/api.js con los valores por
 *  defecto del arranque (obsHours = 24 en store.js, api.incidents() = 48 h; /api/risk
 *  sin `day` es el día en curso). Otros hours, bbox, history, day y las rutas
 *  personales nunca son canónicas. tests/test_copias_canonicas.py coteja esta lista
 *  con el frontend: si cambia una plantilla o un default, se actualiza aquí. */
export const URLS_CANONICAS: readonly string[] = [
  '/api/status',
  '/api/config',
  '/api/official-fires',
  '/api/risk',
  '/api/incidents?hours=48',
  '/api/observations?hours=24',
];

const CANONICAS = new Set<string>(URLS_CANONICAS);

/** ¿La URL pedida es canónica? La comparación es sobre path + consulta exactos. */
export function esUrlCanonica(url: URL): boolean {
  return CANONICAS.has(url.pathname + url.search);
}

/** Clave R2 de una URL canónica: `public/api/status`, `public/api/observations?hours=24`. */
export function claveCopia(urlCanonica: string): string {
  return COPIAS_PREFIX + urlCanonica.replace(/^\/+/, '');
}

/** Lo que las copias necesitan del bucket: un R2Bucket cumple por estructura. Se
 *  inyecta como dependencia (igual que `alBackend` en cache.ts) para probar en Node. */
export interface BucketCopias {
  get(key: string): Promise<{
    body: ReadableStream;
    httpMetadata?: { contentType?: string };
    customMetadata?: Record<string, string>;
  } | null>;
  put(key: string, value: ArrayBuffer, options?: {
    httpMetadata?: { contentType?: string };
    customMetadata?: Record<string, string>;
  }): Promise<unknown>;
}

type AlBackend = (request: Request) => Promise<Response>;

/** Tras un ciclo bueno el contenedor ya está despierto: se pide cada URL canónica sin
 *  compresión y se guardan las respuestas 200 en R2 con el instante de generación.
 *  Un fallo en una copia se registra y no interrumpe las demás ni el ciclo. */
export async function guardarCopias(alBackend: AlBackend, bucket: BucketCopias, generada = Date.now()): Promise<void> {
  for (const url of URLS_CANONICAS) {
    try {
      const res = await alBackend(new Request(`http://backend${url}`, {
        headers: { 'accept-encoding': 'identity' },
      }));
      if (res.status !== 200) {
        console.error(`Copia pública ${url}: el contenedor respondió ${res.status}`);
        continue;
      }
      await bucket.put(claveCopia(url), await res.arrayBuffer(), {
        httpMetadata: { contentType: res.headers.get('content-type') || 'application/json' },
        customMetadata: { [META_GENERADA]: String(generada) },
      });
    } catch (error) {
      console.error(`Copia pública ${url} no se pudo guardar:`, error);
    }
  }
}
