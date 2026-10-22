// Pruebas del enrutado del Worker (OPS-22): la vista previa al compartir un incidente
// (/i/ y /og/) tiene que llegar al backend; antes caía en el 404 del Worker.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PAGINAS, assetPath, backendPath, sharePreview, sharePreviewResponse } from '../src/rutas.ts';

test('cada página bajo /web/ resuelve a su URL limpia (RUTAS-01)', () => {
  for (const pagina of PAGINAS) {
    for (const path of [`/web/${pagina}.html`, `/web/${pagina}`, `/${pagina}.html`, `/${pagina}`]) {
      assert.equal(assetPath(path), `/${pagina}`, path);
    }
  }
});

test('los archivos bajo /web/ que no son páginas conservan su ruta', () => {
  for (const [path, expected] of [
    ['/web/js/app.js', '/js/app.js'],
    ['/web/sitemap.xml', '/sitemap.xml'],
    ['/web/sw.js', '/sw.js'],
    ['/web/index.html', '/index.html'],
    ['/web/css/app.css', '/css/app.css'],
  ]) {
    assert.equal(assetPath(path), expected, path);
  }
});

test('una ruta que no es página del sitio no resuelve', () => {
  assert.equal(assetPath('/'), '/');
  assert.equal(assetPath('/no-existe'), null);
  assert.equal(assetPath('/no-existe.html'), null);
});

test('la API, la vista previa y el parte diario van al backend', () => {
  for (const path of [
    '/api/incidents',
    '/api/incidents/d8e9c96cac20',
    '/i/d8e9c96cac20',
    '/og/incident/d8e9c96cac20.png',
    '/r/2026-10-20',
    '/calendar/boton-rojo/13101.ics',
    '/docs',
    '/openapi.json',
  ]) {
    assert.equal(backendPath(path), true, path);
  }
});

test('las rutas del sitio no van al backend', () => {
  for (const path of [
    '/',
    '/index.html',
    '/admin',
    '/sw.js',
    '/manifest.webmanifest',
    '/robots.txt',
    '/web/js/app.js',
    '/i',
    '/og',
  ]) {
    assert.equal(backendPath(path), false, path);
  }
});

test('solo la vista previa al compartir lleva noindex y caché corta', () => {
  for (const path of ['/i/d8e9c96cac20', '/og/incident/d8e9c96cac20.png']) {
    assert.equal(sharePreview(path), true, path);
  }
  for (const path of ['/api/incidents', '/', '/web/js/app.js']) {
    assert.equal(sharePreview(path), false, path);
  }
});

test('la vista previa conserva cuerpo y estado y suma sus cabeceras', async () => {
  const original = new Response('contenido', {
    status: 200,
    headers: { 'Content-Type': 'text/html', 'Cache-Control': 'public, max-age=600' },
  });
  const out = sharePreviewResponse(original);
  assert.equal(await out.text(), 'contenido');
  assert.equal(out.status, 200);
  assert.equal(out.headers.get('Content-Type'), 'text/html');
  assert.equal(out.headers.get('X-Robots-Tag'), 'noindex');
  assert.equal(out.headers.get('Cache-Control'), 'public, max-age=60');
});
