/* Pruebas de web/js/enso.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { ensoCard, PHASE_LABEL } from '../../web/js/enso.js';

const DATA = {
  phase: 'nino', oni: 1.2, season: 'SON', year: 2025,
  updated_at: '2025-10-12T15:00:00Z', source: 'NOAA · CPC',
  source_url: 'https://www.cpc.ncep.noaa.gov/enso',
};

describe('ensoCard', () => {
  test('nino muestra El Niño con el ONI con signo, trimestre y enlace', () => {
    const out = String(ensoCard(DATA));
    assert.match(out, /El Niño/);
    assert.match(out, /ONI \+1,2 °C/);
    assert.match(out, /trimestre SON 2025/);
    assert.match(out, /actualizado 12 oct/);
    assert.match(out, /Fase cálida del Pacífico/);
    assert.match(out, /href="https:\/\/www\.cpc\.ncep\.noaa\.gov\/enso"/);
    assert.match(out, /NOAA · CPC/);
  });
  test('nina muestra La Niña con ONI negativo', () => {
    const out = String(ensoCard({ ...DATA, phase: 'nina', oni: -0.8 }));
    assert.match(out, /La Niña/);
    assert.match(out, /ONI -0,8 °C/);
    assert.match(out, /Fase fría del Pacífico/);
  });
  test('neutral muestra Neutral', () => {
    const out = String(ensoCard({ ...DATA, phase: 'neutral', oni: 0.1 }));
    assert.match(out, /Neutral/);
    assert.match(out, /estado neutro/);
  });
  test('PHASE_LABEL cubre las tres fases', () => {
    assert.deepEqual(PHASE_LABEL, { nino: 'El Niño', nina: 'La Niña', neutral: 'Neutral' });
  });
  test('sin phase u oni devuelve cadena vacía', () => {
    assert.equal(ensoCard(null), '');
    assert.equal(ensoCard(undefined), '');
    assert.equal(ensoCard({}), '');
    assert.equal(ensoCard({ ...DATA, phase: null }), '');
    assert.equal(ensoCard({ ...DATA, oni: null }), '');
    assert.equal(ensoCard({ ...DATA, oni: undefined }), '');
  });
  test('oni 0 sí es dato: la tarjeta se muestra', () => {
    assert.match(String(ensoCard({ ...DATA, phase: 'neutral', oni: 0 })), /ONI 0 °C/);
  });
  test('sin source_url no hay enlace', () => {
    const out = String(ensoCard({ ...DATA, source_url: null }));
    assert.doesNotMatch(out, /href=/);
  });
  test('el texto de la API se escapa, no se inyecta HTML', () => {
    const out = String(ensoCard({ ...DATA, source: '<script>x</script>', season: '<img src=y>' }));
    assert.doesNotMatch(out, /<script>|<img/);
    assert.match(out, /&lt;script&gt;/);
    assert.match(out, /&lt;img/);
  });
});
