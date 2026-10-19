/** Guardas del Worker: token interno y cabeceras de seguridad. Funciones puras, sin bindings:
 *  las pruebas las importan directo con `node --test` (index.ts carga @cloudflare/containers). */

/** Compara el token sin filtrar por tiempo cuántos caracteres coinciden. */
export function tokenMatches(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

/** Cabeceras de seguridad al servir los assets (la CSP la declara index.ts y llega como parámetro). */
export function securityHeaders(path: string, csp: string): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'geolocation=(self), camera=(self), microphone=()',
    'X-Frame-Options': 'SAMEORIGIN',
    'Strict-Transport-Security': 'max-age=31536000',
  };
  if (path === '/' || path === '/admin') headers['Content-Security-Policy'] = csp;
  if (path === '/' || path === '/admin' || path === '/sw.js') headers['Cache-Control'] = 'no-cache';
  if (path === '/sw.js') headers['Service-Worker-Allowed'] = '/';
  // Las fuentes no cambian de contenido sin cambiar de nombre: caché de un mes.
  if (path.startsWith('/vendor/fonts/')) headers['Cache-Control'] = 'public, max-age=2592000, immutable';
  return headers;
}
