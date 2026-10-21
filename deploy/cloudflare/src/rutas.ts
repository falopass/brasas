/** Rutas que sirve el contenedor Python. Funciones puras, sin bindings: las pruebas las
 *  importan directo con `node --test` (index.ts carga @cloudflare/containers). */

/** La API, la vista previa al compartir y /r/ (el parte diario, cuando exista).
 *  Sin esto, /i/ y /og/ caían en el 404 del Worker (OPS-22). */
export function backendPath(pathname: string): boolean {
  return (
    ['/api/', '/i/', '/og/', '/r/'].some((prefix) => pathname.startsWith(prefix)) ||
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
