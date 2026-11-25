/* Pineo textual del arranque de la configuración en web/js/app.js (REND-02).
 *
 * app.js corre al cargar la página: toca document y window de arranque y no es importable en
 * node. Aquí solo se fija, con inspección textual mínima, el contrato que la suite de node no
 * puede ejecutar: la copia guardada se siembra SIN marca (solo sirve para pintar), pedirConfig
 * marca la configuración fresca ANTES de dejarla en el store —para que quien espera la fresca
 * (reportes, push) la vea en ese mismo evento y no confunda la copia con la vigente— y la
 * petición nunca bloquea el arranque. El recorrido funcional real lo cubre config_check.py en
 * el CI (ventana pendiente, conservación de foco y valores); esperarConfig y marcarConfigFresca
 * se prueban a fondo en config.test.mjs. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/app.js', import.meta.url)), 'utf8');

describe('arranque de la configuración en app.js (pineo textual mínimo)', () => {
  test('la copia guardada se siembra en el store tal cual, sin marca', () => {
    assert.match(SRC, /if \(copia\) store\.set\('config', copia\);/);
  });

  test('pedirConfig marca la configuración fresca ANTES de dejarla en el store', () => {
    // La copia del service worker también se pinta con store.set('config', fresca), pero sin
    // marca; lo que se fija es que la marca preceda inmediatamente al set de la rama fresca.
    assert.match(SRC, /marcarConfigFresca\(\);\s*store\.set\('config', fresca\);/,
      'la marca va justo antes del store.set: quien espera la fresca la ve en ese evento');
  });

  test('la marca se pone una sola vez: la siembra de la copia no puede valer por fresca', () => {
    assert.equal(SRC.split('marcarConfigFresca();').length - 1, 1);
  });

  test('la configuración la pide api.config y el arranque no la espera', () => {
    assert.match(SRC, /await api\.config\(\)/);
    assert.match(SRC, /pedirConfig\(\);/); // en segundo plano: REND-02, sin await del arranque
  });
});
