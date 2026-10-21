/** Rutas que sirve el contenedor Python. Funciones puras, sin bindings: las pruebas las
 *  importan directo con `node --test` (index.ts carga @cloudflare/containers). */

/** Páginas estáticas del sitio (web/<nombre>.html), por su URL limpia. Assets con
 *  html_handling redirige /<nombre>.html → /<nombre>, así que la limpia es la que
 *  tiene que resolver (OPS-26: /web/lista.html → /lista caía en el 404 del Worker).
 *  También se acepta /<nombre>.html, que algunos enlaces usan. */
const PAGINAS = new Set([
  'admin',
  'colegios',
  'datos',
  'lista',
  'lite',
  'pantalla',
  'plan',
  'preguntas',
  'respuesta',
]);

/** Rutas públicas del sitio → ruta dentro de web/ (el mismo mapa que usa backend/main.py).
 *  Los HTML se piden sin extensión: Workers Assets redirige /index.html → / y /admin.html → /admin. */
export function assetPath(pathname: string): string | null {
  if (pathname === '/' || pathname === '/index.html') return '/';
  if (pathname === '/sw.js' || pathname === '/manifest.webmanifest') return pathname;
  if (pathname === '/robots.txt') return '/robots.txt';
  if (pathname.startsWith('/web/')) return pathname.slice(4);
  const pagina = pathname.slice(1).replace(/\.html$/, '');
  return PAGINAS.has(pagina) ? `/${pagina}` : null;
}

/** La API, la vista previa al compartir, /r/ (el parte diario, cuando exista) y /calendar/
 *  (el .ics de Botón Rojo que enlaza Mi zona). Sin esto, /i/, /og/ y /calendar/ caían en el
 *  404 del Worker (OPS-22, OPS-35). */
export function backendPath(pathname: string): boolean {
  return (
    ['/api/', '/i/', '/og/', '/r/', '/calendar/'].some((prefix) => pathname.startsWith(prefix)) ||
    pathname === '/docs' ||
    pathname === '/openapi.json'
  );
}

/** La vista previa de un incidente: no se indexa y se refresca pronto, porque la
 *  tarjeta cambia con el estado del incendio. */
export function sharePreview(pathname: string): boolean {
  return pathname.startsWith('/i/') || pathname.startsWith('/og/');
}

/** Copia la respuesta del backend con las cabeceras de la vista previa. */
export function sharePreviewResponse(response: Response): Response {
  const out = new Response(response.body, response);
  out.headers.set('X-Robots-Tag', 'noindex');
  out.headers.set('Cache-Control', 'public, max-age=60');
  return out;
}
