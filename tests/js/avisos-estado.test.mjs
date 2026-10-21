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

  test('un foco a 40 km no es calor cerca: cae a «sin calor cerca»', () => {
    const r = estadoAvisos({ ...base, points: [alNorte(40)] });
    assert.match(r.titulo, /sin calor cerca/i);
    assert.equal(r.accion, null);
  });

  test('un foco de 9 h quedó fuera de la ventana del aviso y la nombra (6 h, no 48 h)', () => {
    const observed_at = new Date(Date.now() - 9 * 3600000).toISOString();
    const r = estadoAvisos({ ...base, points: [{ ...alNorte(8), observed_at }] });
    assert.match(r.cuerpo, /8 km/);
    assert.match(r.cuerpo, /hace 9 h/);
    assert.match(r.cuerpo, /ventana|6 h/);
    assert.doesNotMatch(r.cuerpo, /48 h/);
  });

  test('con datos atrasados el atraso manda sobre cualquier calor', () => {
    const r = estadoAvisos({ ...base, points: [alNorte(8)], status: { freshness: { stale: true } } });
    assert.match(`${r.titulo} ${r.cuerpo}`, /atrasad/i);
    assert.doesNotMatch(`${r.titulo} ${r.cuerpo}`, /umbral|puntos? de calor/);
    assert.equal(r.tono, 'warn');
  });

  test('un punto sin observed_at no inventa una hora ni imprime basura', () => {
    const r = estadoAvisos({ ...base, points: [alNorte(8)] });
    assert.doesNotMatch(r.cuerpo, /Invalid Date|NaN/);
    assert.match(r.cuerpo, /no dice a qué hora/i);
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
