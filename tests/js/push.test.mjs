/* Pruebas de web/js/push.js con node:test, sin DOM ni red. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { pushProblem, urlBase64ToUint8Array } from '../../web/js/push.js';

// Clave de 65 bytes (punto no comprimido P-256, empieza en 0x04) en sus dos alfabetos.
const CLAVE_B64 = 'BAAlSm+Uud4DKE1yl7zhBitQdZq/5AkuU3idwucMMVZ7oMXqDzRZfqPI7RI3XIGmy/AVOl+Eqc7zGD1ih6zR9hs=';
const CLAVE_URL = 'BAAlSm-Uud4DKE1yl7zhBitQdZq_5AkuU3idwucMMVZ7oMXqDzRZfqPI7RI3XIGmy_AVOl-Eqc7zGD1ih6zR9hs';

describe('urlBase64ToUint8Array', () => {
  test('base64url con - y _ da los mismos bytes que base64 con + y /', () => {
    const esperado = [...Buffer.from(CLAVE_B64, 'base64')];
    assert.deepEqual([...urlBase64ToUint8Array(CLAVE_URL)], esperado);
    assert.deepEqual([...urlBase64ToUint8Array(CLAVE_B64)], esperado);
  });

  test('clave de 65 bytes: largo y primer byte 0x04', () => {
    const bytes = urlBase64ToUint8Array(CLAVE_URL);
    assert.equal(bytes.length, 65);
    assert.equal(bytes[0], 0x04);
  });

  test('rellena los tres restos de longitud', () => {
    assert.deepEqual([...urlBase64ToUint8Array('AQID')], [1, 2, 3]);
    assert.deepEqual([...urlBase64ToUint8Array('AQI')], [1, 2]);
    assert.deepEqual([...urlBase64ToUint8Array('AQ')], [1]);
  });

  test('un carácter inválido lanza y no devuelve bytes a medias', () => {
    assert.throws(() => urlBase64ToUint8Array('AAAA*AAA'));
  });
});

describe('pushProblem', () => {
  test('todo en orden no muestra problema', () => {
    assert.equal(pushProblem({ supported: true, permission: 'granted', standalone: true, isIos: false }), null);
  });

  test('iPhone sin instalar pide añadir a pantalla de inicio', () => {
    assert.deepEqual(pushProblem({ supported: false, permission: 'unsupported', standalone: false, isIos: true }), {
      title: 'Los avisos necesitan BRASA instalada',
      help: 'En iPhone o iPad: Compartir → Añadir a pantalla de inicio. Después abre BRASA desde ese ícono y activa los avisos.',
    });
  });

  test('permiso denegado explica cómo desbloquear', () => {
    assert.deepEqual(pushProblem({ supported: true, permission: 'denied', standalone: true, isIos: false }), {
      title: 'Avisos bloqueados',
      help: 'Los avisos están bloqueados para este sitio. Ábrelos así: candado en la barra de direcciones → Notificaciones → Permitir.',
    });
  });

  test('navegador sin soporte y sin iOS sugiere otro navegador', () => {
    assert.deepEqual(pushProblem({ supported: false, permission: 'unsupported', standalone: false, isIos: false }), {
      title: 'Este navegador no admite avisos',
      help: 'Prueba con Chrome, Edge o Firefox en su versión actual.',
    });
  });
});
