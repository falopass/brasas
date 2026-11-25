/* Pruebas de web/js/push.js con node:test, sin DOM ni red. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { clearBadge, crearManejadorRecargaSw, detectIos, disablePush, enablePush, flushPendingSubscription, pushProblem, pushState, registerServiceWorker, urlBase64ToUint8Array } from '../../web/js/push.js';
import { marcarConfigFresca } from '../../web/js/config.js';
import { store } from '../../web/js/store.js';
import { api } from '../../web/js/api.js';

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

/* REND-02/seg: la clave pública VAPID viaja en la configuración FRESCA. Una suscripción nacida
 * con otra clave (el servidor rotó la suya) ya no sirve: el servidor no podría entregar avisos
 * con ella. Se da de baja y se crea otra con la clave actual, sin pedir permiso de nuevo;
 * si coincide, la suscripción se reutiliza tal cual. */
describe('enablePush: la clave pública fresca manda (rotación VAPID)', () => {
  const UNSUB = '/__push-unsubscribe-pending';
  // Otra clave de 65 bytes: distinta en un byte, para que la comparación no valga por longitud.
  const CLAVE_OTRA = (() => { const b = urlBase64ToUint8Array(CLAVE_B64); b[1] ^= 0xff; return b; })();

  let previos;
  let suscripcion;
  let unsubscribes;
  let subscribes;
  let posts;
  let borrados;

  const suscripcionCon = (applicationServerKey, endpoint) => ({
    options: { applicationServerKey },
    toJSON: () => ({ endpoint, keys: { p256dh: 'p256', auth: 'a' } }),
    unsubscribe: async () => { unsubscribes += 1; },
  });

  beforeEach(() => {
    previos = {
      window: globalThis.window,
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      Notification: globalThis.Notification,
      PushManager: globalThis.PushManager,
      matchMedia: globalThis.matchMedia,
      caches: globalThis.caches,
      pushSubscribe: api.pushSubscribe,
    };
    unsubscribes = 0;
    subscribes = [];
    posts = [];
    borrados = [];
    globalThis.window = globalThis;
    globalThis.Notification = { permission: 'granted' };
    globalThis.PushManager = function PushManager() {};
    globalThis.matchMedia = () => ({ matches: false });
    globalThis.caches = { open: async () => ({ match: async () => null, delete: async (k) => { borrados.push(k); } }) };
    const registro = {
      pushManager: {
        getSubscription: async () => suscripcion,
        subscribe: async (opts) => {
          subscribes.push(opts);
          return suscripcionCon(opts.applicationServerKey, 'https://push/nueva');
        },
      },
    };
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        userAgent: 'Mozilla/5.0 (X11; Linux x86_64) rv:1.0', platform: 'Linux x86_64', maxTouchPoints: 0,
        serviceWorker: { ready: Promise.resolve(registro) },
      },
    });
    api.pushSubscribe = async (payload) => { posts.push(payload); };
  });

  afterEach(() => {
    for (const clave of ['window', 'Notification', 'PushManager', 'matchMedia', 'caches']) {
      if (previos[clave] === undefined) delete globalThis[clave];
      else globalThis[clave] = previos[clave];
    }
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
    api.pushSubscribe = previos.pushSubscribe;
  });

  test('suscripción nacida con otra clave: se da de baja y se crea otra con la clave fresca', async () => {
    suscripcion = suscripcionCon(CLAVE_OTRA, 'https://push/vieja');
    await enablePush(CLAVE_URL, { permiso: Promise.resolve('granted') });
    assert.equal(unsubscribes, 1); // la suscripción vieja, con la clave rotada, se retira
    assert.equal(subscribes.length, 1);
    assert.equal(subscribes[0].userVisibleOnly, true);
    assert.deepEqual([...subscribes[0].applicationServerKey], [...urlBase64ToUint8Array(CLAVE_URL)]);
    assert.equal(posts.length, 1);
    assert.equal(posts[0].endpoint, 'https://push/nueva'); // al servidor llega la suscripción nueva
    assert.ok(borrados.includes(UNSUB)); // el alta que salió vuelve obsoleta cualquier baja pendiente
  });

  test('suscripción con la MISMA clave (byte a byte, en ArrayBuffer como la entrega el navegador): se reutiliza', async () => {
    suscripcion = suscripcionCon(urlBase64ToUint8Array(CLAVE_B64).buffer, 'https://push/vigente');
    await enablePush(CLAVE_URL, { permiso: Promise.resolve('granted') }); // CLAVE_URL es la misma clave en base64url
    assert.equal(unsubscribes, 0);
    assert.equal(subscribes.length, 0); // nada se vuelve a pedir: la suscripción sirve
    assert.equal(posts.length, 1);
    assert.equal(posts[0].endpoint, 'https://push/vigente');
  });

  test('sin suscripción: se crea una con la clave fresca y se da de alta', async () => {
    suscripcion = null;
    await enablePush(CLAVE_URL, { permiso: Promise.resolve('granted') });
    assert.equal(unsubscribes, 0);
    assert.equal(subscribes.length, 1);
    assert.deepEqual([...subscribes[0].applicationServerKey], [...urlBase64ToUint8Array(CLAVE_URL)]);
    assert.equal(posts[0].endpoint, 'https://push/nueva');
  });

  test('suscripción sin clave registrada: ante la duda se resuscribe', async () => {
    suscripcion = suscripcionCon(undefined, 'https://push/vieja');
    await enablePush(CLAVE_URL, { permiso: Promise.resolve('granted') });
    assert.equal(unsubscribes, 1);
    assert.equal(subscribes.length, 1); // no se afirma nada de lo que no se puede comparar
  });

  test('permiso denegado en el gesto: no suscribe ni da de alta nada', async () => {
    suscripcion = null;
    await assert.rejects(enablePush(CLAVE_URL, { permiso: Promise.resolve('denied') }), /permitir las notificaciones/);
    assert.equal(subscribes.length, 0);
    assert.equal(posts.length, 0);
  });
});

/* El reenvío de la suscripción vigente (rotación hecha por el service worker o reingreso)
 * sigue la misma regla: la clave FRESCA manda. resyncSubscription no se exporta: entra por
 * registerServiceWorker, que la dispara al registrar. Los POST van al mock de api. */
describe('resync de la suscripción: la clave fresca manda también al reenviar', () => {
  let previos;
  let listeners;
  let controller;
  let suscripcion;
  let unsubscribes;
  let subscribes;
  let posts;

  beforeEach(() => {
    previos = {
      window: globalThis.window,
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      document: globalThis.document,
      Notification: globalThis.Notification,
      PushManager: globalThis.PushManager,
      matchMedia: globalThis.matchMedia,
      setInterval: globalThis.setInterval,
      pushSubscribe: api.pushSubscribe,
    };
    listeners = {};
    controller = null;
    unsubscribes = 0;
    subscribes = [];
    posts = [];
    const registro = {
      pushManager: {
        getSubscription: async () => suscripcion,
        subscribe: async (opts) => {
          subscribes.push(opts);
          return { toJSON: () => ({ endpoint: 'https://push/nueva', keys: { p256dh: 'x', auth: 'y' } }) };
        },
      },
    };
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        userAgent: 'Mozilla/5.0 (X11; Linux x86_64) rv:1.0', platform: 'Linux x86_64', maxTouchPoints: 0,
        serviceWorker: {
          get controller() { return controller; },
          addEventListener: (tipo, fn) => { (listeners[tipo] ||= []).push(fn); },
          register: async () => ({ update: async () => {} }),
          ready: Promise.resolve(registro),
        },
      },
    });
    globalThis.window = globalThis;
    globalThis.Notification = { permission: 'granted' }; // pushEnabled(): hay avisos activados
    globalThis.PushManager = function PushManager() {};
    globalThis.matchMedia = () => ({ matches: false });
    globalThis.document = { addEventListener() {}, visibilityState: 'hidden' };
    globalThis.setInterval = () => 0; // sin el ciclo de actualización del SW real
    api.pushSubscribe = async (payload) => { posts.push(payload); };
    // La clave fresca de esta sesión: resync la espera con esperarConfig({fresca:true}).
    marcarConfigFresca();
    store.set('config', { push: { public_key: CLAVE_URL } });
  });

  afterEach(() => {
    for (const clave of ['window', 'Notification', 'PushManager', 'matchMedia']) {
      if (previos[clave] === undefined) delete globalThis[clave];
      else globalThis[clave] = previos[clave];
    }
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
    if (previos.document === undefined) delete globalThis.document;
    else globalThis.document = previos.document;
    globalThis.setInterval = previos.setInterval;
    api.pushSubscribe = previos.pushSubscribe;
    store.set('config', null);
  });

  // registerServiceWorker dispara el resync sin esperarlo: se dejan pasar los microturnos.
  const asentar = async () => {
    for (let i = 0; i < 10 && posts.length === 0; i += 1) await new Promise((r) => setTimeout(r, 1));
  };

  test('suscripción con otra clave: se da de baja, se resuscribe con la fresca y se reenvía la nueva', async () => {
    const otra = urlBase64ToUint8Array(CLAVE_B64);
    otra[1] ^= 0xff;
    suscripcion = { options: { applicationServerKey: otra }, unsubscribe: async () => { unsubscribes += 1; } };
    await registerServiceWorker(() => {});
    await asentar();
    assert.equal(unsubscribes, 1);
    assert.equal(subscribes.length, 1);
    assert.deepEqual([...subscribes[0].applicationServerKey], [...urlBase64ToUint8Array(CLAVE_URL)]);
    assert.equal(posts.length, 1);
    assert.equal(posts[0].endpoint, 'https://push/nueva');
  });

  test('suscripción con la misma clave: se reenvía la vigente, sin darla de baja ni resuscribir', async () => {
    suscripcion = {
      options: { applicationServerKey: urlBase64ToUint8Array(CLAVE_URL) },
      unsubscribe: async () => { unsubscribes += 1; },
      toJSON: () => ({ endpoint: 'https://push/vigente', keys: { p256dh: 'v', auth: 'v' } }),
    };
    await registerServiceWorker(() => {});
    await asentar();
    assert.equal(unsubscribes, 0);
    assert.equal(subscribes.length, 0);
    assert.equal(posts.length, 1); // el alta es un UPDATE idempotente: se reenvía tal cual
    assert.equal(posts[0].endpoint, 'https://push/vigente');
  });
});

describe('disablePush con el servidor sin señal', () => {
  const PENDING = '/__push-pending';
  const UNSUB = '/__push-unsubscribe-pending';
  let previos;
  let cacheStore;
  let unsubscribes;
  let posts;
  let deletes;
  let fallaRed;

  beforeEach(() => {
    previos = {
      window: globalThis.window,
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      Notification: globalThis.Notification,
      caches: globalThis.caches,
      pushSubscribe: api.pushSubscribe,
      pushUnsubscribe: api.pushUnsubscribe,
    };
    // El service worker había dejado una suscripción rotada pendiente de reenviar.
    cacheStore = new Map([[PENDING, { json: async () => ({ endpoint: 'https://push/vieja', keys: {} }) }]]);
    unsubscribes = 0;
    posts = 0;
    deletes = 0;
    fallaRed = true;
    globalThis.window = globalThis;
    globalThis.Notification = { permission: 'granted' };
    globalThis.caches = {
      open: async () => ({
        match: async (k) => cacheStore.get(k),
        put: async (k, r) => { cacheStore.set(k, r); },
        delete: async (k) => cacheStore.delete(k),
      }),
    };
    const subscription = { unsubscribe: async () => { unsubscribes += 1; } };
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: { serviceWorker: { ready: Promise.resolve({ pushManager: { getSubscription: async () => subscription } }) } },
    });
    api.pushSubscribe = async () => { posts += 1; };
    api.pushUnsubscribe = async () => { deletes += 1; if (fallaRed) throw new Error('sin señal'); };
  });

  afterEach(() => {
    for (const clave of ['window', 'Notification', 'caches']) {
      if (previos[clave] === undefined) delete globalThis[clave];
      else globalThis[clave] = previos[clave];
    }
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
    api.pushSubscribe = previos.pushSubscribe;
    api.pushUnsubscribe = previos.pushUnsubscribe;
  });

  test('un fallo del servidor no impide la baja local: no lanza y desuscribe una vez', async () => {
    await disablePush();
    assert.equal(unsubscribes, 1);
    assert.equal(deletes, 1);
    // La baja quedó anotada para reintentarla cuando vuelva la señal.
    assert.equal(cacheStore.has(UNSUB), true);
  });

  test('la entrada pendiente de suscripción queda borrada aunque el servidor falle', async () => {
    await disablePush();
    assert.equal(cacheStore.has(PENDING), false);
  });

  test('después de desactivar, flushPendingSubscription no vuelve a dar de alta', async () => {
    await disablePush();
    // Quedó una suscripción vieja en vuelo (o el service worker la rotó entretanto).
    cacheStore.set(PENDING, { json: async () => ({ endpoint: 'https://push/nueva', keys: {} }) });
    fallaRed = false; // volvió la señal: la baja anotada sí se reenvía, el alta no
    await flushPendingSubscription();
    assert.equal(posts, 0);
    assert.equal(deletes, 2);
    assert.equal(cacheStore.has(UNSUB), false);
    assert.equal(cacheStore.has(PENDING), true); // no se consumió: `disabled` manda
  });

  test('con servidor sano la baja sale completa y no deja marca pendiente', async () => {
    fallaRed = false;
    await disablePush();
    assert.equal(unsubscribes, 1);
    assert.equal(deletes, 1);
    assert.equal(cacheStore.has(PENDING), false);
    assert.equal(cacheStore.has(UNSUB), false);
  });
});

describe('clearBadge (UX-75)', () => {
  const KEY = '/__badge-count';
  let previos;
  let cacheStore;

  beforeEach(() => {
    previos = {
      window: globalThis.window,
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      caches: globalThis.caches,
    };
    cacheStore = new Map();
    globalThis.window = globalThis;
    globalThis.caches = {
      open: async () => ({ put: async (k, r) => { cacheStore.set(k, await r.text()); } }),
    };
  });

  afterEach(() => {
    for (const clave of ['window', 'caches']) {
      if (previos[clave] === undefined) delete globalThis[clave];
      else globalThis[clave] = previos[clave];
    }
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
  });

  test('con Badging API limpia el ícono y deja el contador en cero', async () => {
    let limpiadas = 0;
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: { clearAppBadge: async () => { limpiadas += 1; } },
    });
    await clearBadge();
    assert.equal(limpiadas, 1);
    assert.equal(cacheStore.get(KEY), '0');
  });

  test('sin Badging API igual deja el contador en cero y no lanza', async () => {
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} });
    await assert.doesNotReject(clearBadge());
    assert.equal(cacheStore.get(KEY), '0');
  });
});

describe('registerServiceWorker (actualización del SW)', () => {
  let previos;
  let listeners;
  let controller;

  const dispararControllerChange = () => {
    controller = { postMessage: () => {} }; // un service worker nuevo toma el control
    for (const fn of listeners.controllerchange || []) fn();
  };

  beforeEach(() => {
    previos = {
      navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
      document: globalThis.document,
      setInterval: globalThis.setInterval,
    };
    listeners = {};
    controller = null;
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        serviceWorker: {
          get controller() { return controller; },
          addEventListener: (tipo, fn) => { (listeners[tipo] ||= []).push(fn); },
          register: async () => ({ update: async () => {} }),
        },
      },
    });
    globalThis.document = { addEventListener: () => {}, visibilityState: 'hidden' };
    // Sin intervalo real: la prueba no debe dejar el proceso vivo.
    globalThis.setInterval = () => 0;
  });

  afterEach(() => {
    if (previos.navigator) Object.defineProperty(globalThis, 'navigator', previos.navigator);
    else delete globalThis.navigator;
    if (previos.document === undefined) delete globalThis.document;
    else globalThis.document = previos.document;
    globalThis.setInterval = previos.setInterval;
  });

  test('pestaña abierta antes de la primera instalación: avisa desde la segunda toma de control', async () => {
    let avisos = 0;
    await registerServiceWorker(() => { avisos += 1; });
    dispararControllerChange(); // instalación inicial: no es una actualización
    assert.equal(avisos, 0);
    dispararControllerChange(); // una versión nueva toma el control
    assert.equal(avisos, 1);
    dispararControllerChange(); // y solo una vez por toma de control
    assert.equal(avisos, 2);
  });

  test('pestaña ya controlada: la primera toma de control nueva avisa al instante', async () => {
    controller = { postMessage: () => {} };
    let avisos = 0;
    await registerServiceWorker(() => { avisos += 1; });
    dispararControllerChange();
    assert.equal(avisos, 1);
  });
});

describe('crearManejadorRecargaSw (recarga única con SW nuevo)', () => {
  const modalFalso = () => {
    const oyentes = {};
    return {
      open: false,
      dataset: {},
      addEventListener: (tipo, fn) => { oyentes[tipo] = fn; },
      // El navegador encola el `close` del diálogo como tarea (spec de HTML), no lo dispara
      // síncrono: la prueba respeta ese orden para no inventar carreras.
      cerrar: () => { const fn = oyentes.close; delete oyentes.close; if (fn) setTimeout(fn, 0); },
    };
  };
  const cuerpoFalso = () => {
    const clases = new Set();
    return {
      clases,
      classList: {
        contains: (c) => clases.has(c),
        add: (c) => clases.add(c),
        delete: (c) => clases.delete(c),
      },
    };
  };
  const tick = () => new Promise((r) => setTimeout(r, 5));
  const armar = (modal, body) => {
    const recargas = { n: 0 };
    const avisos = { n: 0 };
    const alActualizar = crearManejadorRecargaSw({
      modal,
      body,
      yaRecargo: () => false, // primera actualización de la pestaña: toca recargar
      recargar: () => { recargas.n += 1; },
      avisar: () => { avisos.n += 1; },
    });
    return { alActualizar, recargas, avisos };
  };

  test('sin formulario ni elección recarga una vez y después avisa', () => {
    const modal = modalFalso();
    let ya = false; // la marca de yaRecargoSw: false = esta pestaña aún no recargó
    let recargas = 0, avisos = 0;
    const alActualizar = crearManejadorRecargaSw({
      modal,
      body: cuerpoFalso(),
      yaRecargo: () => ya,
      recargar: () => { recargas += 1; },
      avisar: () => { avisos += 1; },
    });
    alActualizar();
    assert.equal(recargas, 1);
    ya = true; // la pestaña ya recargó con la versión nueva
    alActualizar();
    assert.equal(avisos, 1);
    assert.equal(recargas, 1);
  });

  test('con el formulario abierto difiere la recarga hasta el cierre', async () => {
    const modal = modalFalso();
    modal.open = true;
    const { alActualizar, recargas } = armar(modal, cuerpoFalso());
    alActualizar();
    assert.equal(recargas.n, 0);
    modal.open = false; // la persona cierra el formulario
    modal.cerrar();
    await tick();
    assert.equal(recargas.n, 1);
  });

  test('«Marcarlo en el mapa»: ni el cierre temporal ni la elección recargan; recarga al cerrar el formulario', async () => {
    const modal = modalFalso();
    modal.open = true;
    const body = cuerpoFalso();
    const { alActualizar, recargas } = armar(modal, body);

    // Llega la actualización con el formulario abierto: se difiere.
    alActualizar();
    assert.equal(recargas.n, 0);

    // «Marcarlo en el mapa»: pickOnMap cierra el diálogo y marca `picking` en el mismo bloque
    // síncrono; el `close` encolado llega después, cuando la elección ya está en curso.
    modal.open = false;
    modal.cerrar();
    body.clases.add('picking');
    await tick();
    assert.equal(recargas.n, 0); // el borrador sigue a salvo

    // La elección termina y el formulario vuelve a abrirse; la persona lo cierra de verdad.
    body.clases.delete('picking');
    modal.open = true;
    modal.open = false;
    modal.cerrar();
    await tick();
    assert.equal(recargas.n, 1);
  });

  test('si ya recargó en esta pestaña, avisa en vez de recargar', () => {
    const modal = modalFalso();
    let avisos = 0;
    const alActualizar = crearManejadorRecargaSw({
      modal,
      body: cuerpoFalso(),
      yaRecargo: () => true,
      recargar: () => { throw new Error('no debía recargar'); },
      avisar: () => { avisos += 1; },
    });
    alActualizar();
    assert.equal(avisos, 1);
  });
});
