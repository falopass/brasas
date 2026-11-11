/* Pruebas del filtro de incendios nominados (web/js/nominados.js) y del catálogo de la vista
 * Historia (web/js/views/casos.js): filtros por región, hash y cercanía, sin navegador.
 * casos.js importa ui.js, que registra un listener «online» al cargar: se usa un stub. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { filterNominados, foldComuna, sumHa } from '../../web/js/nominados.js';

globalThis.window = { addEventListener() {} };
const { filaNominado, filtrarPorRegion, ordenarPorCercania, paintNominados, regionesDe, regionFromHash, tarjetaHtml, meteoDeHoy, comparadorHtml, sinReconstruccion } = await import('../../web/js/views/casos.js');
const CASES = JSON.parse(readFileSync(fileURLToPath(new URL('../../web/data/cases.json', import.meta.url)), 'utf8')).cases;
const SRC_CASOS = readFileSync(fileURLToPath(new URL('../../web/js/views/casos.js', import.meta.url)), 'utf8');

const ITEMS = [
  { name: 'UNO', comuna: 'Ñiquén', season: '2016-2017', ha: 100 },
  { name: 'DOS', comuna: 'Ñiquén', season: '2023-2024', ha: 50 },
  { name: 'TRES', comuna: 'Chillán', season: '2016-2017', ha: 200.5 },
  { name: 'CUATRO', comuna: 'Chillán Viejo', season: '2016-2017', ha: 75 },
  { name: 'CINCO', comuna: 'Quirihue', season: '2016-2017', ha: 300 },
];

describe('foldComuna', () => {
  test('minúsculas, sin tildes y «ñ» pasa a «n»', () => {
    assert.equal(foldComuna('  Ñuble  '), 'nuble');
    assert.equal(foldComuna('Quilpué'), 'quilpue');
    assert.equal(foldComuna('RÍO   IBÁÑEZ'), 'rio ibanez');
  });
  test('vacío y nulos', () => {
    assert.equal(foldComuna(''), '');
    assert.equal(foldComuna(null), '');
    assert.equal(foldComuna(undefined), '');
  });
});

describe('filterNominados', () => {
  test('comuna exacta', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Quirihue' }).map((i) => i.name), ['CINCO']);
  });
  test('sin tildes ni ñ encuentra la comuna con ellas', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen' }).map((i) => i.name), ['UNO', 'DOS']);
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Chillan Viejo' }).map((i) => i.name), ['CUATRO']);
  });
  test('el texto libre calza por prefijo («chillan» trae Chillán y Chillán Viejo)', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'chillan' }).map((i) => i.name), ['TRES', 'CUATRO']);
  });
  test('sin resultados', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Springfield' }), []);
  });
  test('se combina con la temporada', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen', season: '2016-2017' }).map((i) => i.name), ['UNO']);
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen', season: '2020-2021' }), []);
  });
  test('solo temporada, como antes', () => {
    assert.equal(filterNominados(ITEMS, { season: '2023-2024' }).length, 1);
    assert.equal(filterNominados(ITEMS, { season: '2016-2017' }).length, 4);
    assert.equal(filterNominados(ITEMS, {}).length, 5);
  });
  test('ordena de mayor a menor superficie', () => {
    assert.deepEqual(filterNominados(ITEMS, { season: '2016-2017' }).map((i) => i.ha), [300, 200.5, 100, 75]);
  });
});

describe('sumHa', () => {
  test('suma las hectáreas del filtro actual', () => {
    assert.equal(sumHa(filterNominados(ITEMS, { season: '2016-2017' })), 675.5);
    assert.equal(sumHa(filterNominados(ITEMS, { comuna: 'niquen' })), 150);
    assert.equal(sumHa([]), 0);
  });
});

describe('regionesDe', () => {
  test('devuelve las regiones únicas, separando los casos con varias', () => {
    assert.deepEqual(regionesDe(CASES), ['Biobío', 'Valparaíso', 'Ñuble', 'La Araucanía', 'Maule', 'Magallanes']);
  });
});

describe('filtrarPorRegion', () => {
  test('«Maule» devuelve solo Las Máquinas 2017', () => {
    assert.deepEqual(filtrarPorRegion(CASES, 'Maule').map((c) => c.id), ['las-maquinas-2017']);
  });
  test('«Todas» y vacío devuelven los nueve casos', () => {
    assert.equal(filtrarPorRegion(CASES, 'Todas').length, 9);
    assert.equal(filtrarPorRegion(CASES, '').length, 9);
  });
  test('una región compartida trae todos los casos que la incluyen', () => {
    assert.deepEqual(filtrarPorRegion(CASES, 'Biobío').map((c) => c.id), ['penco-lirquen-2026', 'nuble-biobio-araucania-2023']);
  });
});

describe('regionFromHash', () => {
  test('lee la región del hash y devuelve «» cuando no viene', () => {
    assert.equal(regionFromHash('#/casos?region=Maule'), 'Maule');
    assert.equal(regionFromHash('#/casos'), '');
    assert.equal(regionFromHash('#/casos/las-maquinas-2017'), '');
  });
  test('decodifica regiones con espacios y tildes', () => {
    assert.equal(regionFromHash(`#/casos?region=${encodeURIComponent('La Araucanía')}`), 'La Araucanía');
  });
});

describe('ordenarPorCercania', () => {
  test('pone primero el caso más cercano al lugar guardado', () => {
    const curico = { lat: -34.98, lon: -71.24 }; // Curicó, Maule
    assert.equal(ordenarPorCercania(CASES, curico)[0].id, 'las-maquinas-2017');
  });
  test('sin lugar mantiene el orden del archivo', () => {
    assert.deepEqual(ordenarPorCercania(CASES, null).map((c) => c.id), CASES.map((c) => c.id));
    assert.deepEqual(ordenarPorCercania(CASES, { lat: 'x' }).map((c) => c.id), CASES.map((c) => c.id));
  });
});

describe('comparadorHtml', () => {
  test('sin pronóstico no inventa el clima de hoy y cita la fuente de cada caso', () => {
    const t = String(comparadorHtml(null, CASES));
    assert.match(t, /Condiciones de hoy vs\. grandes incendios/);
    assert.match(t, /No inventamos la temperatura/);
    assert.match(t, /Rocuant/);
    assert.match(t, /China Muerta/);
    assert.match(t, /Timaukel/);
    assert.match(t, /archive-api\.open-meteo\.com/);
    assert.doesNotMatch(t, /hoy \d/);
  });
  test('con pronóstico contrasta calor, humedad y viento', () => {
    const t = String(comparadorHtml({ lugar: 'Curicó', tmax: 33, rhmin: 20, windmax: 45 }, CASES));
    assert.match(t, /En Curicó/);
    assert.match(t, /por sobre/);
    assert.match(t, /más seco que/);
    assert.match(t, /más viento que/);
    assert.match(t, /Parecerse no significa que hoy se repita ese fuego/);
  });
  test('un caso con una cifra nula no entra al comparador', () => {
    const casos = CASES.map((c) => (c.id === 'timaukel-2022' ? { ...c, climate: { ...c.climate, rhmin_pct: null } } : c));
    assert.doesNotMatch(String(comparadorHtml(null, casos)), /Timaukel/);
  });
});

describe('sinReconstruccion', () => {
  test('sin detecciones ni cuadros no hay reproductor que mostrar', () => {
    assert.equal(sinReconstruccion({ frames: [], events: [] }, 0), true);
    assert.equal(sinReconstruccion({ frames: [], events: [] }, 3), false);
    assert.equal(sinReconstruccion({ frames: [{ t: '2022-01-25T00:00Z' }], events: [] }, 0), false);
  });
});

describe('meteoDeHoy', () => {
  test('sin lugar, sin índice o sin cifras devuelve null', () => {
    assert.equal(meteoDeHoy({}), null);
    assert.equal(meteoDeHoy({ places: [{ lat: -34.98, lon: -71.24 }], comunasIndex: [], risk: { comunas: {} } }), null);
  });
  test('toma la comuna más cercana al primer lugar', () => {
    const hoy = meteoDeHoy({
      places: [{ lat: -34.98, lon: -71.24, name: 'Casa' }],
      comunasIndex: [{ code: 7301, name: 'Curicó', center: [-71.24, -34.98] }],
      risk: { date: '2026-11-04', comunas: { 7301: { tmax: 31, rhmin: 22, windmax: 35 } } },
      hoy: '2026-11-04',
    });
    assert.equal(hoy.lugar, 'Curicó');
    assert.equal(hoy.tmax, 31);
    assert.equal(hoy.rhmin, 22);
    assert.equal(hoy.windmax, 35);
  });
  test('solo compara el pronóstico del día de hoy en Chile', () => {
    const base = {
      places: [{ lat: -34.98, lon: -71.24, name: 'Casa' }],
      comunasIndex: [{ code: 7301, name: 'Curicó', center: [-71.24, -34.98] }],
      risk: { date: '2026-11-05', comunas: { 7301: { tmax: 33, rhmin: 20, windmax: 45 } } },
      hoy: '2026-11-04',
    };
    assert.equal(meteoDeHoy(base), null);
    assert.equal(meteoDeHoy({ ...base, risk: { ...base.risk, date: '2026-11-04' } }).tmax, 33);
  });
  test('sin lugares guardados usa la comuna abierta en Riesgo', () => {
    const hoy = meteoDeHoy({
      places: [],
      riskComuna: 7301,
      comunasIndex: [{ code: 7301, name: 'Curicó', center: [-71.24, -34.98] }],
      risk: { date: '2026-11-04', comunas: { 7301: { tmax: 31, rhmin: 22, windmax: 35 } } },
      hoy: '2026-11-04',
    });
    assert.equal(hoy.lugar, 'Curicó');
  });
  test('una cifra ausente queda en null y no se compara como cero', () => {
    const hoy = meteoDeHoy({
      places: [{ lat: -34.98, lon: -71.24, name: 'Casa' }],
      comunasIndex: [{ code: 7301, name: 'Curicó', center: [-71.24, -34.98] }],
      risk: { date: '2026-11-04', comunas: { 7301: { tmax: 31, rhmin: null, windmax: 35 } } },
      hoy: '2026-11-04',
    });
    assert.equal(hoy.rhmin, null);
    const t = String(comparadorHtml(hoy, CASES));
    assert.doesNotMatch(t, /humedad hoy 0 %/);
    assert.doesNotMatch(t, /más seco que/);
  });
});

describe('tarjetaHtml', () => {
  test('la tarjeta es un enlace real a la vista del caso', () => {
    const t = String(tarjetaHtml(CASES.find((c) => c.id === 'las-maquinas-2017')));
    assert.match(t, /^<a\b/);
    assert.match(t, /href="#\/casos\/las-maquinas-2017"/);
    assert.doesNotMatch(t, /tabindex=|role=/);
  });
  test('con distancia marca «a N km de tu lugar»', () => {
    const t = String(tarjetaHtml(CASES[0], 60));
    assert.match(t, /a 60 km de tu lugar/);
  });
});

const INDEX = [
  { code: 7301, name: 'Hualañé', region: 'Maule' },
  { code: 13101, name: 'Ñuñoa', region: 'Metropolitana' },
];

// UX-VISTAS: errores y estados vacíos que nombran lo que falló y dicen qué hacer.
describe('mensajes de error y estados vacíos de Historia (UX-VISTAS)', () => {
  test('el catálogo y la ficha nombran la consulta que falló', () => {
    assert.match(SRC_CASOS, /No se pudieron cargar los incendios históricos\. Revisa tu conexión/);
    assert.match(SRC_CASOS, /No se pudo cargar este incendio histórico\. Revisa tu conexión/);
  });
  test('la ficha de un caso conserva «Reintentar» y los teléfonos del bloque compartido', () => {
    assert.match(SRC_CASOS, /errorConSalida\(container\.querySelector\('#case-err'\)/);
  });
  test('el buscador de nominados no deja que el teléfono corrija la comuna', () => {
    const input = SRC_CASOS.match(/<input[^>]*id="nom-comuna"[^>]*>/)?.[0] || '';
    for (const attr of ['enterkeyhint="search"', 'autocapitalize="off"', 'autocorrect="off"', 'spellcheck="false"']) {
      assert.ok(input.includes(attr), `nom-comuna sin ${attr}`);
    }
  });
  test('la lista de nominados falla con dual y «Reintentar», y suelta la promesa rechazada', () => {
    assert.match(SRC_CASOS, /nominadosPromise = null/);
    assert.match(SRC_CASOS, /No se pudo cargar la lista de incendios con nombre/);
    assert.match(SRC_CASOS, /data-retry-nom/);
  });
  test('un filtro de región sin casos propone quitarlo', () => {
    assert.match(SRC_CASOS, /Quita el filtro/);
    assert.match(SRC_CASOS, /Ningún incendio histórico en/);
  });
  test('los enlaces «↗» de las revisiones llevan nombre accesible', () => {
    assert.match(SRC_CASOS, /aria-label="Abrir la fuente: \$\{r\.source\}">↗<\/a>/);
  });
});

describe('paintNominados sin resultados (UX-VISTAS)', () => {
  const falso = () => ({ innerHTML: '', textContent: '' });
  test('con comuna escrita dice qué hacer', () => {
    const meta = falso();
    paintNominados(falso(), meta, ITEMS, { comuna: 'Springfield' });
    assert.match(meta.textContent, /Ningún incendio con nombre en «Springfield»/);
    assert.match(meta.textContent, /Prueba con otra comuna o borra la búsqueda/);
  });
  test('solo con temporada sugiere «Todas las temporadas»', () => {
    const meta = falso();
    paintNominados(falso(), meta, ITEMS, { season: '1999-2000' });
    assert.match(meta.textContent, /Ningún incendio con nombre en la temporada 1999-2000/);
    assert.match(meta.textContent, /Prueba con «Todas las temporadas»/);
  });
});

describe('filaNominado', () => {
  test('una comuna conocida enlaza a la ficha de riesgo', () => {
    const t = String(filaNominado({ name: 'El fuego', comuna: 'Hualañé', ha: 12.5, season: '2024-2025' }, INDEX));
    assert.match(t, /href="#\/riesgo\?comuna=7301"/);
    assert.match(t, /aria-label="Ver el riesgo de Hualañé"/);
    assert.match(t, /12,5 ha/);
  });
  test('una comuna desconocida queda como texto plano', () => {
    const t = String(filaNominado({ name: 'El fuego', comuna: 'Springfield', ha: 1, season: '2024-2025' }, INDEX));
    assert.doesNotMatch(t, /href="#\/riesgo/);
    assert.match(t, /Springfield/);
  });
});
