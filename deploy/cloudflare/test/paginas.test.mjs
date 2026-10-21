// Las páginas del sitio (OPS-26): Assets con html_handling redirige /x.html → /x, así que
// /web/<página>.html llega al navegador como 307 hacia /<página>. Si assetPath no conoce
// la URL limpia, la página da 404 en producción aunque exista en web/ (le pasaba a la
// hoja de emergencia /lista.html y a las URL del sitemap).
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assetPath } from '../src/rutas.ts';

const WEB = new URL('../../../web/', import.meta.url);
const PAGINAS = readdirSync(WEB).filter((f) => f.endsWith('.html'));

/** Resuelve una URL pública hasta la ruta que Assets sirve con 200, o null si el Worker
 *  corta con 404. Emula html_handling de Assets: /x.html redirige a /x (/index.html a /). */
function resuelve(url) {
  for (let i = 0; i < 4; i++) {
    const asset = assetPath(url);
    if (!asset) return null;
    if (!asset.endsWith('.html')) return asset;
    url = asset === '/index.html' ? '/' : asset.slice(0, -'.html'.length);
  }
  return null;
}

test('toda página de web/ resuelve por su URL pública /web/<página>.html', () => {
  assert.ok(PAGINAS.length >= 8, `se esperaban las páginas del sitio, hay ${PAGINAS.length}`);
  for (const file of PAGINAS) {
    assert.ok(resuelve(`/web/${file}`), `/web/${file} termina en 404`);
  }
});

test('toda página resuelve por su URL limpia y por /<página>.html', () => {
  for (const file of PAGINAS) {
    const limpia = file === 'index.html' ? '/' : `/${file.slice(0, -'.html'.length)}`;
    assert.ok(resuelve(limpia), `${limpia} termina en 404`);
    assert.ok(resuelve(`/${file}`), `/${file} termina en 404`);
  }
});

test('cada URL del sitemap resuelve', () => {
  const sitemap = readFileSync(new URL('sitemap.xml', WEB), 'utf8');
  const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname);
  assert.ok(locs.length > 0, 'el sitemap no tiene <loc>');
  for (const loc of locs) {
    assert.ok(resuelve(loc), `${loc} del sitemap termina en 404`);
  }
});

test('las páginas que no existen siguen en 404', () => {
  for (const path of ['/noexiste', '/noexiste.html', '/web/noexiste.html', '/api/incidents', '/i/abc']) {
    assert.equal(resuelve(path), null, path);
  }
});
