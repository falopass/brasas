// Pruebas del enrutado del Worker (OPS-22): la vista previa al compartir un incidente
// (/i/ y /og/) tiene que llegar al backend; antes caía en el 404 del Worker.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { backendPath, sharePreview, sharePreviewResponse } from '../src/rutas.ts';

test('la API, la vista previa y el parte diario van al backend', () => {
  for (const path of [
    '/api/incidents',
    '/api/incidents/d8e9c96cac20',
    '/i/d8e9c96cac20',
    '/og/incident/d8e9c96cac20.png',
    '/r/2026-10-20',
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
