/* Por qué no ha llegado un aviso (web/js/avisos-estado.js): sin lugares, sin permiso,
 * con calor bajo el umbral o con datos atrasados. Sin DOM ni navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { estadoAvisos, focosCerca } from '../../web/js/avisos-estado.js';

const KM_POR_GRADO = (Math.PI / 180) * 6371.0088;
const talca = { id: 'p1', name: 'Talca', lat: -35.42, lon: -71.60, radius_km: 10 };
const alNorte = (km) => ({ id: `foco-${km}`, lat: talca.lat + km / KM_POR_GRADO, lon: talca.lon, confidence: 'alta' });
const base = { places: [talca], alerts: [], points: [], status: null, permission: 'granted' };

describe('focosCerca', () => {
  test('cruza lugares y focos hasta 2× el radio y ordena por distancia', () => {
    const focos = focosCerca([talca], [alNorte(25), alNorte(7)]);
    assert.equal(focos.length, 1);
    assert.ok(Math.abs(focos[0].km - 7) < 0.01);
    assert.equal(focos[0].place.name, 'Talca');
  });

  test('un foco a 40 km con radio 10 queda fuera: 2× el radio son 20 km', () => {
    assert.deepEqual(focosCerca([talca], [alNorte(40)]), []);
  });
});

describe('estadoAvisos', () => {
  test('sin lugares pide agregar uno y no habla de notificaciones', () => {
    const r = estadoAvisos({ places: [], alerts: [], points: [], status: null, permission: 'granted' });
    assert.equal(r.accion, 'agregar-lugar');
    assert.doesNotMatch(r.cuerpo, /notificaci/i);
  });

  test('con lugares y sin permiso pide activar los avisos', () => {
    const r = estadoAvisos({ ...base, permission: 'denied' });
    assert.equal(r.accion, 'activar-avisos');
  });

  test('con un foco confiable a 7 km explica el umbral con la distancia', () => {
    const r = estadoAvisos({ ...base, points: [alNorte(7)] });
    assert.match(r.cuerpo, /7 km/);
    assert.match(r.cuerpo, /umbral|no alcanzó/);
    assert.doesNotMatch(r.cuerpo, /no hay fuego/i);
  });

  test('un foco a 40 km no es calor cerca: cae a «sin calor cerca en las últimas 48 h»', () => {
    const r = estadoAvisos({ ...base, points: [alNorte(40)] });
    assert.match(r.titulo, /sin calor cerca en las últimas 48 h/i);
    assert.equal(r.accion, null);
  });

  test('con datos atrasados lo dice y no promete tranquilidad', () => {
    const r = estadoAvisos({ ...base, status: { freshness: { stale: true } } });
    assert.match(`${r.titulo} ${r.cuerpo}`, /atrasad/i);
    assert.doesNotMatch(`${r.titulo} ${r.cuerpo}`, /tranquil/i);
  });

  test('con avisos no se pinta diagnóstico', () => {
    assert.equal(estadoAvisos({ ...base, alerts: [{ id: 1 }] }), null);
  });

  test('el calor de una fuente fija no se explica como umbral', () => {
    const r = estadoAvisos({ ...base, points: [{ ...alNorte(3), incident_fixed: true }] });
    assert.doesNotMatch(r.titulo, /umbral/i);
    assert.match(r.cuerpo, /fuente fija|volcán/i);
  });
});
