// Pruebas de las guardas del Worker (OPS-15): token interno y cabeceras de seguridad.
// Corre con `node --test` directo sobre el TS, igual que retention.test.mjs.
// `crypto.subtle.timingSafeEqual` existe solo en el runtime de Workers: se apoya en la
// versión de node:crypto (misma semántica: igualdad en tiempo constante).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { timingSafeEqual } from 'node:crypto';
import {
  BASE_SECURITY_HEADERS,
  isHtmlContentType,
  securityHeaders,
  tokenMatches,
  withHtmlSecurityHeaders,
} from '../src/guardas.ts';

crypto.subtle.timingSafeEqual ??= timingSafeEqual;

const CSP = 'default-src test';

function respuestaInmutable(body, init) {
  const r = new Response(body, init);
  const tira = () => { throw new TypeError('immutable'); };
  Object.assign(r.headers, { set: tira, append: tira, delete: tira });
  return r;
}

test('token: coincide solo el token exacto', () => {
  assert.equal(tokenMatches('secreto', 'secreto'), true);
  assert.equal(tokenMatches('otro', 'secreto'), false);
  assert.equal(tokenMatches('secret', 'secreto'), false); // distinto largo
});

test('token: vacío, nulo o sin esperar nunca coincide', () => {
  assert.equal(tokenMatches('', 'secreto'), false);
  assert.equal(tokenMatches(null, 'secreto'), false);
  assert.equal(tokenMatches('secreto', ''), false);
  assert.equal(tokenMatches('secreto', undefined), false);
  assert.equal(tokenMatches(null, undefined), false);
});

test('cabeceras: / y /admin llevan CSP', () => {
  for (const path of ['/', '/admin']) {
    const headers = securityHeaders(path, CSP);
    assert.equal(headers['Content-Security-Policy'], CSP);
  }
});

test('cabeceras: cualquier ruta con Content-Type text/html lleva CSP', () => {
  for (const path of ['/lite', '/lista', '/admin.html', '/otra.html']) {
    const headers = securityHeaders(path, CSP, 'text/html; charset=utf-8');
    assert.equal(headers['Content-Security-Policy'], CSP, path);
  }
});

test('cabeceras: /sw.js lleva Service-Worker-Allowed y no CSP', () => {
  const headers = securityHeaders('/sw.js', CSP);
  assert.equal(headers['Service-Worker-Allowed'], '/');
  assert.equal(headers['Content-Security-Policy'], undefined);
  assert.equal(headers['Cache-Control'], 'no-cache');
});

test('cabeceras: una ruta cualquiera no lleva CSP ni caché especial', () => {
  const headers = securityHeaders('/api/risk', CSP);
  assert.equal(headers['Content-Security-Policy'], undefined);
  assert.equal(headers['Cache-Control'], undefined);
  assert.equal(headers['Service-Worker-Allowed'], undefined);
});

test('cabeceras: nosniff y HSTS van en todas', () => {
  for (const path of ['/', '/admin', '/sw.js', '/api/risk', '/robots.txt']) {
    const headers = securityHeaders(path, CSP);
    assert.equal(headers['X-Content-Type-Options'], 'nosniff');
    assert.equal(headers['Strict-Transport-Security'], 'max-age=31536000');
    assert.equal(headers['X-Frame-Options'], 'SAMEORIGIN');
  }
});

test('isHtmlContentType reconoce text/html con o sin parámetros y rechaza otros tipos', () => {
  for (const tipo of ['text/html', 'text/html; charset=utf-8', 'TEXT/HTML; charset=UTF-8', ' text/html ; charset=utf-8 ']) {
    assert.equal(isHtmlContentType(tipo), true, tipo);
  }
  for (const tipo of [null, undefined, '', 'application/json', 'text/plain', 'text/javascript', 'text/html-fragment']) {
    assert.equal(isHtmlContentType(tipo), false, String(tipo));
  }
});

test('withHtmlSecurityHeaders agrega CSP y cabeceras base a respuestas HTML de assets, contenedor o R2', async () => {
  for (const contentType of ['text/html', 'text/html; charset=utf-8']) {
    const entrada = respuestaInmutable('<h1>Hola</h1>', {
      status: 200,
      headers: { 'Content-Type': contentType, 'Cache-Control': 'public, max-age=1800' },
    });
    const salida = withHtmlSecurityHeaders(entrada, CSP);
    assert.equal(salida.status, 200);
    assert.equal(await salida.text(), '<h1>Hola</h1>');
    assert.equal(salida.headers.get('Content-Security-Policy'), CSP);
    assert.equal(salida.headers.get('Cache-Control'), 'public, max-age=1800');
    for (const [name, value] of Object.entries(BASE_SECURITY_HEADERS)) {
      assert.equal(salida.headers.get(name), value, name);
    }
  }
});

test('withHtmlSecurityHeaders no duplica ni pisa la CSP ni las cabeceras enviadas por el backend', () => {
  const cspBackend = "default-src 'self'; object-src 'none'";
  const entrada = respuestaInmutable('<h1>Comuna</h1>', {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Security-Policy': cspBackend,
      'X-Frame-Options': 'SAMEORIGIN',
    },
  });
  const salida = withHtmlSecurityHeaders(entrada, CSP);
  assert.equal(salida.headers.get('Content-Security-Policy'), cspBackend);
  assert.deepEqual(salida.headers.getSetCookie?.() ?? [], []);
  // Solo debe existir una cabecera CSP y completarse las faltantes (como HSTS).
  const cspHeaders = [...salida.headers.entries()].filter(([k]) => k.toLowerCase() === 'content-security-policy');
  assert.equal(cspHeaders.length, 1);
  assert.equal(salida.headers.get('Strict-Transport-Security'), 'max-age=31536000');
});

test('withHtmlSecurityHeaders no toca respuestas que no son HTML ni 204/304', () => {
  const json = new Response('{"ok":true}', { headers: { 'Content-Type': 'application/json' } });
  const js = new Response('console.log(1)', { headers: { 'Content-Type': 'text/javascript; charset=utf-8' } });
  const empty = new Response(null, { status: 204, headers: { 'Content-Type': 'text/html' } });
  const notModified = new Response(null, { status: 304, headers: { 'Content-Type': 'text/html' } });
  for (const res of [json, js, empty, notModified]) {
    const salida = withHtmlSecurityHeaders(res, CSP);
    assert.equal(salida, res);
    assert.equal(salida.headers.get('Content-Security-Policy'), null);
  }
});
