/* Pruebas de las funciones puras de web/js/views/alertas.js con node:test (UX-50):
 * kindLabel traduce el `kind` del aviso al motivo que lee la persona; sin `kind`
 * conocido devuelve '' y la vista no muestra etiqueta: nunca se inventa un motivo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { item, kindLabel } from '../../web/js/views/alertas.js';

describe('kindLabel', () => {
  test('traduce cada motivo conocido', () => {
    assert.equal(kindLabel('oficial'), 'CONAF informa');
    assert.equal(kindLabel('reporte'), 'Un vecino reportó');
    assert.equal(kindLabel('diario'), 'Prevención del día');
    assert.equal(kindLabel('prueba'), 'Prueba');
  });
  test('el aviso de la DMC lleva su etiqueta', () => {
    assert.equal(kindLabel('dmc'), 'Aviso de la DMC');
  });
  test('el aviso de aluvión lleva su etiqueta', () => {
    assert.equal(kindLabel('aluvion'), 'Lluvia en zona quemada');
  });
  test('un kind desconocido no inventa un motivo', () => {
    assert.equal(kindLabel('desconocido'), '');
    assert.equal(kindLabel(''), '');
  });
  test('sin kind no hay etiqueta', () => {
    assert.equal(kindLabel(undefined), '');
    assert.equal(kindLabel(null), '');
  });
});

describe('item', () => {
  const dmc = {
    id: 1, level: 'aviso', kind: 'dmc', title: 'Aviso de calor extremo',
    body: 'Calor extremo hasta el viernes', created_at: '2026-10-20T15:00:00Z',
    delivered: ['push'], url: '/#/mi-zona', dmc: { web: 'https://dmc.example/aviso' },
  };
  test('un aviso dmc conserva su texto y muestra la etiqueta', () => {
    const t = String(item(dmc));
    assert.match(t, /Calor extremo hasta el viernes/);
    assert.match(t, /Aviso de la DMC/);
    assert.match(t, /Dirección Meteorológica de Chile/);
    assert.match(t, /https:\/\/dmc\.example\/aviso/);
  });
  test('un aviso sin kind reconocido conserva su cuerpo', () => {
    const t = String(item({ ...dmc, kind: 'otro', dmc: null }));
    assert.match(t, /Calor extremo hasta el viernes/);
    assert.doesNotMatch(t, /tag/);
  });
  test('el aviso de aluvión muestra la fuente con su enlace', () => {
    const t = String(item({
      id: 2, level: 'aviso', kind: 'aluvion', title: 'Lluvia intensa sobre zona quemada',
      body: 'informado por CONAF, 900 ha', created_at: '2026-10-20T15:00:00Z',
      delivered: ['telegram'], url: '/#/mi-zona',
      aluvion: { fuente: 'conaf', fuente_url: 'https://github.com/deigeprif/public' },
    }));
    assert.match(t, /Fuente: CONAF/);
    assert.match(t, /href="https:\/\/github\.com\/deigeprif\/public"/);
    assert.match(t, /registro público/);
    const sat = String(item({
      id: 3, level: 'aviso', kind: 'aluvion', title: 'Lluvia intensa sobre zona quemada',
      body: 'los satélites vieron calor', created_at: '2026-10-20T15:00:00Z',
      delivered: ['push'], url: '/#/mi-zona',
      aluvion: { fuente: 'satelite', fuente_url: 'https://firms.modaps.eosdis.nasa.gov/' },
    }));
    assert.match(sat, /Fuente: NASA FIRMS/);
    assert.match(sat, /firms\.modaps\.eosdis\.nasa\.gov/);
  });
});
