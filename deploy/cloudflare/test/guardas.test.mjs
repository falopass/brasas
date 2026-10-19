// Pruebas de las guardas del Worker (OPS-15): token interno y cabeceras de seguridad.
// Corre con `node --test` directo sobre el TS, igual que retention.test.mjs.
// `crypto.subtle.timingSafeEqual` existe solo en el runtime de Workers: se apoya en la
// versión de node:crypto (misma semántica: igualdad en tiempo constante).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { timingSafeEqual } from 'node:crypto';
import { securityHeaders, tokenMatches } from '../src/guardas.ts';

crypto.subtle.timingSafeEqual ??= timingSafeEqual;

const CSP = 'default-src test';

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
