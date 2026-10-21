/* Guardas de «¿Qué hago si…?» (UX-11): es la página que alguien abre con el incendio encima.
 * Cada rama sale de material oficial, tiene pocos pasos y no habla de predicciones (QA-79).
 * quehago.js importa speak.js, que lee `window` al cargar. index.js junta todas las suites en
 * un proceso y esta corre antes que speak.test.mjs: importarla aquí dejaría `synth` en null y
 * rompería las pruebas de voz, así que se importa en un hilo aparte con el stub mínimo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';

const BRANCHES = await new Promise((resolve, reject) => {
  const url = new URL('../../web/js/views/quehago.js', import.meta.url).href;
  const worker = new Worker(`
    const { parentPort } = require('node:worker_threads');
    globalThis.window = { addEventListener() {} }; // ui.js se suscribe a «online» al importarse
    import(${JSON.stringify(url)}).then((m) => { parentPort.postMessage(m.BRANCHES); parentPort.close(); }, (e) => { throw e; });
  `, { eval: true });
  worker.once('message', resolve);
  worker.once('error', reject);
});

const OFICIALES = ['senapred.cl', 'conaf.cl', 'minsal.cl', 'senadis.gob.cl', 'sag.gob.cl'];
const PROHIBIDAS = ['prediccion', 'predecir', 'va a llegar'];
const JERGA = ['protocolo', 'gestion', 'operativo', 'infraestructura', 'logistica', 'interfaz', 'monitoreo', 'interinstitucional', 'resiliencia'];
const PERSONA = /\b(veo|me|tengo|hay|se|mi|mis|estoy|somos|puedo)\b/;

// Sin tildes ni mayúsculas: la guarda no depende de cómo se escribió la palabra.
const plano = (s) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const visible = (b) => [b.q, ...b.steps, ...b.sources.map(([name]) => name)].join(' ');

const esOficial = (url) => {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && OFICIALES.some((d) => u.hostname === d || u.hostname.endsWith(`.${d}`));
  } catch { return false; }
};

describe('ramas de ¿Qué hago si…?', () => {
  test('la página tiene las siete ramas, incluidas la de luz, agua o señal y la rural', () => {
    assert.equal(BRANCHES.length, 7);
    assert.ok(BRANCHES.some((b) => /luz/i.test(b.q) && /se[ñn]al/i.test(b.q)));
    assert.ok(BRANCHES.some((b) => /campo|parcela/i.test(b.q)));
  });

  test('cada rama tiene entre 1 y 3 pasos', () => {
    for (const b of BRANCHES) {
      assert.ok(Array.isArray(b.steps), b.q);
      assert.ok(b.steps.length >= 1 && b.steps.length <= 3, `${b.q}: ${b.steps.length} pasos`);
      for (const s of b.steps) assert.ok(s.trim().length > 0, b.q);
    }
  });

  test('cada rama cita al menos una URL https de un dominio oficial', () => {
    for (const b of BRANCHES) {
      assert.ok(Array.isArray(b.sources) && b.sources.length > 0, `${b.q} sin fuentes`);
      assert.ok(b.sources.some(([, url]) => esOficial(url)), `${b.q} sin fuente oficial: ${b.sources.map(([, u]) => u).join(', ')}`);
    }
  });

  test('la rama de humo o fuego nombra el 130 y el 132', () => {
    const b = BRANCHES.find((x) => /humo o fuego/i.test(x.q));
    assert.ok(b, 'falta la rama «Veo humo o fuego»');
    const texto = b.steps.join(' ');
    assert.ok(texto.includes('130'), 'debe nombrar el 130 (CONAF)');
    assert.ok(texto.includes('132'), 'debe nombrar el 132 (Bomberos)');
  });

  test('ningún texto visible habla de predicciones (QA-79)', () => {
    for (const b of BRANCHES) {
      const texto = plano(visible(b));
      for (const p of PROHIBIDAS) assert.ok(!texto.includes(p), `${b.q}: contiene «${p}»`);
    }
  });

  test('cada título se reconoce sin jerga y habla de la persona', () => {
    for (const b of BRANCHES) {
      const titulo = plano(b.q);
      assert.ok(b.q.length <= 60, `${b.q}: título demasiado largo`);
      for (const j of JERGA) assert.ok(!titulo.includes(j), `${b.q}: jerga «${j}»`);
      assert.match(titulo, PERSONA, `${b.q}: el título no está escrito desde quien lo vive`);
    }
  });
});

describe('rama de luz, agua o señal', () => {
  const rama = BRANCHES.find((b) => /luz/i.test(b.q) && /se[ñn]al/i.test(b.q));

  test('sus pasos salen de las dos páginas de SENAPRED', () => {
    const urls = rama.sources.map(([, url]) => url);
    assert.ok(urls.includes('https://senapred.cl/kit-de-emergencia/'));
    assert.ok(urls.includes('https://senapred.cl/familia-preparada/'));
  });

  test('los pasos cubren agua, luz y comunicaciones', () => {
    const texto = plano(rama.steps.join(' '));
    assert.ok(texto.includes('agua'), 'agua');
    assert.ok(texto.includes('linterna') || texto.includes('luz'), 'luz');
    assert.ok(texto.includes('radio') || texto.includes('directorio'), 'comunicaciones');
  });
});

describe('rama rural (campo o parcela)', () => {
  const rama = BRANCHES.find((b) => /campo|parcela/i.test(b.q));

  test('existe y enlaza al riesgo de la comuna', () => {
    assert.ok(rama, 'falta la rama rural');
    assert.deepEqual(rama.link, ['Ver el riesgo de mi comuna', '#/riesgo']);
  });

  test('sus fuentes son solo de SENAPRED y CONAF', () => {
    const hosts = rama.sources.map(([, url]) => new URL(url).hostname);
    for (const h of hosts) {
      assert.ok(h === 'senapred.cl' || h.endsWith('.senapred.cl') || h === 'conaf.cl' || h.endsWith('.conaf.cl'), h);
    }
  });
});
