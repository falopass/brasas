// El «Monitoreo de ingesta» se dispara desde el Cron Trigger del Worker (OPS-01): GitHub Actions
// retrasa su propio cron, así que el Worker abre una corrida workflow_dispatch cada 15 minutos.
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MONITORING_CRON, dispatchMonitoring } from '../src/monitoreo.ts';

test('wrangler declara los cron de ingesta y monitoreo', () => {
  const wrangler = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  assert.ok(wrangler.includes('"*/10 * * * *"'), 'falta el cron de ingesta de 10 minutos');
  assert.ok(wrangler.includes('"*/15 * * * *"'), 'falta el cron de monitoreo de 15 minutos');
  assert.equal(MONITORING_CRON, '*/15 * * * *');
});

test('dispara el workflow de monitoreo en main con el token del Worker', async () => {
  const llamadas = [];
  const fetchImpl = async (url, init) => {
    llamadas.push({ url, init });
    return new Response(null, { status: 204 });
  };
  await dispatchMonitoring({ GITHUB_MONITOR_TOKEN: 'token-de-prueba' }, fetchImpl);
  assert.equal(llamadas.length, 1);
  assert.equal(llamadas[0].url, 'https://api.github.com/repos/falopass/brasas/actions/workflows/monitoreo.yml/dispatches');
  assert.equal(llamadas[0].init.method, 'POST');
  assert.equal(llamadas[0].init.headers.Authorization, 'Bearer token-de-prueba');
  assert.deepEqual(JSON.parse(llamadas[0].init.body), { ref: 'main' });
});

test('sin token no llama a GitHub', async () => {
  let llamadas = 0;
  await assert.rejects(
    dispatchMonitoring({}, async () => {
      llamadas += 1;
      return new Response(null, { status: 204 });
    }),
    /GITHUB_MONITOR_TOKEN/,
  );
  assert.equal(llamadas, 0);
});

test('un HTTP distinto de 204 es error', async () => {
  await assert.rejects(
    dispatchMonitoring({ GITHUB_MONITOR_TOKEN: 'token-de-prueba' }, async () => new Response('sin permiso', { status: 403 })),
    /HTTP 403/,
  );
});
