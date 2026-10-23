import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const { pronosticoTexto } = await import('../../web/js/trendview.js');

describe('pronosticoTexto (UX-63)', () => {
  test('explica la escala, la fuente y lo que no es', () => {
    const t = pronosticoTexto();
    assert.match(t, /bajo, moderado, alto y extremo/);
    assert.match(t, /Open-Meteo/);
    assert.match(t, /no una medición|no es una medición/);
    assert.doesNotMatch(t, /predicción|habrá un incendio/i);
  });
});
