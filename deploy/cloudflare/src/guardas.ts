/** Guardas del Worker: token interno y cabeceras de seguridad. Funciones puras, sin bindings:
 *  las pruebas las importan directo con `node --test` (index.ts carga @cloudflare/containers). */

export const BASE_SECURITY_HEADERS: Record<string, string> = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(self), camera=(self), microphone=()',
  'X-Frame-Options': 'SAMEORIGIN',
  'Strict-Transport-Security': 'max-age=31536000',
};

/** Compara el token sin filtrar por tiempo cuántos caracteres coinciden. */
export function tokenMatches(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

/** Indica si el Content-Type corresponde a un documento HTML (`text/html`, con o sin parámetros). */
export function isHtmlContentType(contentType: string | null | undefined): boolean {
  if (!contentType) return false;
  return contentType.split(';', 1)[0].trim().toLowerCase() === 'text/html';
}

/** Cabeceras de seguridad al servir los assets (la CSP la declara index.ts y llega como parámetro). */
export function securityHeaders(path: string, csp: string, contentType?: string | null): Record<string, string> {
  const headers: Record<string, string> = { ...BASE_SECURITY_HEADERS };
  if (isHtmlContentType(contentType) || path === '/' || path === '/admin') headers['Content-Security-Policy'] = csp;
  if (path === '/' || path === '/admin' || path === '/sw.js') headers['Cache-Control'] = 'no-cache';
  if (path === '/sw.js') headers['Service-Worker-Allowed'] = '/';
  // Las fuentes no cambian de contenido sin cambiar de nombre: caché de un mes.
  if (path.startsWith('/vendor/fonts/')) headers['Cache-Control'] = 'public, max-age=2592000, immutable';
  return headers;
}

/** Agrega la CSP y las cabeceras de seguridad base a cualquier respuesta `text/html` (assets,
 *  contenedor o R2) sin duplicar ni pisar las que el backend o una etapa previa ya hayan enviado. */
export function withHtmlSecurityHeaders(response: Response, csp: string): Response {
  if (response.status === 204 || response.status === 304) return response;
  if (!isHtmlContentType(response.headers.get('Content-Type'))) return response;
  const missingBase = Object.entries(BASE_SECURITY_HEADERS).filter(([name]) => !response.headers.has(name));
  const hasCsp = response.headers.has('Content-Security-Policy');
  if (missingBase.length === 0 && hasCsp) return response;
  const headers = new Headers(response.headers);
  for (const [name, value] of missingBase) headers.set(name, value);
  if (!hasCsp) headers.set('Content-Security-Policy', csp);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
