/* Pruebas de web/js/push.js con node:test, sin DOM ni red. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { detectIos, pushProblem, pushState, urlBase64ToUint8Array } from '../../web/js/push.js';

// Entorno de navegador completo; cada prueba cambia solo lo que le importa.
const entorno = (extra = {}) => ({
  hasServiceWorker: true,
  hasPushManager: true,
  hasNotification: true,
  permission: 'default',
  standalone: false,
  isIos: false,
  ...extra,
});

const IPHONE = { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', platform: 'iPhone', maxTouchPoints: 5 };
const IPAD = { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', platform: 'MacIntel', maxTouchPoints: 5 };
const MAC = { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', platform: 'MacIntel', maxTouchPoints: 0 };

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

describe('pushState', () => {
  test('escritorio completo con permiso default: soportado y sin problema (se puede pedir)', async () => {
    const state = await pushState(entorno());
    assert.deepEqual(state, { supported: true, permission: 'default', standalone: false, isIos: false });
    assert.equal(pushProblem(state), null);
  });

  test('falta cualquiera de las tres piezas: sin soporte y permiso unsupported', async () => {
    for (const falta of ['hasServiceWorker', 'hasPushManager', 'hasNotification']) {
      const state = await pushState(entorno({ [falta]: false, permission: 'granted' }));
      assert.deepEqual(state, { supported: false, permission: 'unsupported', standalone: false, isIos: false }, falta);
    }
  });

  test('iPhone sin instalar: pide añadir a pantalla de inicio, no el mensaje genérico', async () => {
    const state = await pushState(entorno({ hasPushManager: false, isIos: true }));
    assert.equal(pushProblem(state).title, 'Los avisos necesitan BRASA instalada');
  });

  test('iPhone instalado pero sin PushManager: navegador no compatible', async () => {
    const state = await pushState(entorno({ hasPushManager: false, standalone: true, isIos: true }));
    assert.equal(pushProblem(state).title, 'Este navegador no admite avisos');
  });

  test('permiso granted en un navegador completo: no hay problema', async () => {
    assert.equal(pushProblem(await pushState(entorno({ permission: 'granted' }))), null);
  });

  test('permiso denied: avisos bloqueados con la ruta del candado', async () => {
    const problem = pushProblem(await pushState(entorno({ permission: 'denied' })));
    assert.equal(problem.title, 'Avisos bloqueados');
    assert.match(problem.help, /candado/);
  });

  test('sin entorno lee navigator, window, matchMedia y Notification', async () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
    const previos = {
      window: globalThis.window,
      matchMedia: globalThis.matchMedia,
      Notification: globalThis.Notification,
      PushManager: globalThis.PushManager,
    };
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { ...IPHONE } });
    globalThis.window = globalThis;
    globalThis.matchMedia = () => ({ matches: false });
    globalThis.Notification = { permission: 'denied' };
    try {
      assert.deepEqual(await pushState(), { supported: false, permission: 'unsupported', standalone: false, isIos: true });
      globalThis.PushManager = function PushManager() {};
      Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { ...IPHONE, serviceWorker: {} } });
      assert.deepEqual(await pushState(), { supported: true, permission: 'denied', standalone: false, isIos: true });
    } finally {
      Object.defineProperty(globalThis, 'navigator', descriptor);
      for (const [clave, valor] of Object.entries(previos)) {
        if (valor === undefined) delete globalThis[clave];
        else globalThis[clave] = valor;
      }
    }
  });
});

describe('detectIos', () => {
  test('iPad que se declara MacIntel con pantalla táctil es iOS', () => {
    assert.equal(detectIos(IPAD), true);
  });

  test('Mac de escritorio (MacIntel sin tacto) no es iOS', () => {
    assert.equal(detectIos(MAC), false);
  });

  test('iPhone e iPad por user agent; Android y escritorio no', () => {
    assert.equal(detectIos(IPHONE), true);
    assert.equal(detectIos({ userAgent: 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X)', platform: 'iPad', maxTouchPoints: 5 }), true);
    assert.equal(detectIos({ userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8)', platform: 'Linux armv8l', maxTouchPoints: 5 }), false);
  });
});
