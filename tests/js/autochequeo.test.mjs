import test from 'node:test';
import assert from 'node:assert/strict';
import { advice, run, summarize, TARGETS } from '../../web/js/autochequeo.js';

const res = (over = {}) => ({ target: '/web/lista.html', status: 200, ms: 100, ok: true, error: null, ...over });

test('TARGETS incluye las nueve páginas y los seis GET', () => {
  const paginas = ['index', 'lite', 'lista', 'plan', 'preguntas', 'datos', 'respuesta', 'pantalla', 'admin']
    .map((n) => `/web/${n}.html`);
  for (const p of paginas) assert.ok(TARGETS.includes(p), `falta ${p}`);
  for (const a of ['/api/status', '/api/incidents', '/api/observations', '/api/risk', '/api/opendata', '/api/panorama']) {
    assert.ok(TARGETS.includes(a), `falta ${a}`);
  }
});

test('summarize con todo ok', () => {
  const s = summarize([res(), res({ ms: 900 })]);
  assert.deepEqual(s, { total: 2, ok: 2, lentos: 0, fallidos: 0, peor: null });
});

test('summarize con un 500 y un lento', () => {
  const s = summarize([res({ status: 500, ok: false, ms: 300 }), res({ ms: 4000 }), res()]);
  assert.equal(s.fallidos, 1);
  assert.equal(s.lentos, 1);
  assert.equal(s.peor.ms, 4000);
});

test('advice por caso', () => {
  assert.equal(advice(res()), 'responde bien');
  assert.match(advice(res({ status: 503, ok: false })), /el servidor está fallando/);
  assert.match(advice(res({ status: 0, ok: false, error: 'timeout' })), /modo liviano/);
  assert.match(advice(res({ ms: 3000 })), /tarda demasiado/);
});

test('run usa fetchImpl y sobrevive errores', async () => {
  const fakeFetch = async (t) => {
    if (t.includes('incidents')) throw new Error('x');
    return { status: 200, ok: true };
  };
  const out = await run(fakeFetch, () => 0);
  assert.equal(out.length, TARGETS.length);
  assert.equal(out.find((r) => r.target === '/api/incidents').ok, false);
});
