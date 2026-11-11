/* VIS-03 · correcciones de revisión del filtro por distancia.
 * La regla que decide qué incidentes se ven con radio vive en data.js (pura) y la
 * usan por igual la lista «Posibles incendios» y los anillos/huellas del mapa; lo
 * que solo existe en la vista (repintado de capas, aviso de fuente caída) se
 * revisa leyendo la fuente, como hace errores.test.mjs. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { filtrarPorDistancia, fireIncidents } from '../../web/js/data.js';

const leer = (rel) => readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), 'utf8');
// Talca como referencia: el foco «cerca» cae a ~9 km, el «lejos» en Santiago (~250 km).
const CENTRO = { lat: -35.4264, lon: -71.6554 };
const foco = (id, over = {}) => ({ id, observed_at: '2026-11-11T10:00:00Z', lat: -35.35, lon: -71.65, ...over });
const OBS = [
  foco(1, { incident_id: 'inc-a', incident_status: 'confirmado', incident_n: 5, comuna: 'Talca' }),
  foco(2, { incident_id: 'inc-a', incident_status: 'confirmado', incident_n: 5, observed_at: '2026-11-11T09:00:00Z', lat: -35.36, lon: -71.66 }),
  foco(3, { incident_id: 'inc-b', incident_status: 'descartado', incident_n: 2 }),
  foco(4, { incident_id: 'inc-c', incident_status: 'posible', incident_fixed: true, incident_n: 2 }),
  foco(5, { incident_status: 'posible' }), // sin incidente
];

describe('fireIncidents: la regla única de la lista y el mapa (VIS-03)', () => {
  test('un incidente entra solo si tiene un miembro en la lista dada', () => {
    const filas = fireIncidents(OBS);
    assert.deepEqual(filas.map((i) => i.id), ['inc-a']);
  });

  test('la cifra de la fila cuenta los miembros visibles, no el total del incidente', () => {
    const inc = fireIncidents(OBS)[0];
    assert.equal(inc.vistos, 2); // dos miembros dentro del recorte
    assert.equal(inc.n, 5); // el total publicado se conserva aparte
  });

  test('si parte del incidente quedó fuera del radio, vistos baja pero la fila sigue', () => {
    const obs = [
      foco(1, { incident_id: 'inc-x', incident_status: 'posible', incident_n: 4 }),
      foco(2, { incident_id: 'inc-x', incident_status: 'posible', incident_n: 4, lat: -33.44, lon: -70.66 }),
    ];
    const inc = fireIncidents(filtrarPorDistancia(obs, CENTRO, 10))[0];
    assert.equal(inc.id, 'inc-x');
    assert.equal(inc.vistos, 1);
  });

  test('la fila guarda la coordenada del miembro más reciente con lat/lon', () => {
    const inc = fireIncidents(OBS)[0];
    assert.equal(inc.lat, -35.35); // el de las 10:00, no el de las 09:00
    // Un miembro nuevo sin coordenadas no borra la posición conocida.
    const inc2 = fireIncidents([
      foco(1, { incident_id: 'i', incident_status: 'posible', observed_at: '2026-11-11T09:00:00Z' }),
      foco(2, { incident_id: 'i', incident_status: 'posible', observed_at: '2026-11-11T10:00:00Z', lat: undefined, lon: undefined }),
    ])[0];
    assert.equal(inc2.lat, -35.35);
  });

  test('con radio la lista queda recortada: miembro dentro entra, sin miembro dentro sale', () => {
    const obs = [
      foco(1, { incident_id: 'inc-borde', incident_status: 'posible', incident_n: 8 }), // miembro a ~9 km
      foco(2, { incident_id: 'inc-remoto', incident_status: 'confirmado', incident_n: 3, lat: -33.44, lon: -70.66 }),
    ];
    const filas = fireIncidents(filtrarPorDistancia(obs, CENTRO, 10));
    assert.deepEqual(filas.map((i) => i.id), ['inc-borde']);
  });
});

describe('mapa.js aplica la misma regla en todas partes (VIS-03)', () => {
  const src = leer('web/js/views/mapa.js');

  test('los anillos usan la regla de la lista, no el centro publicado', () => {
    const pintar = src.slice(src.indexOf('function pintarIncidentes'));
    assert.ok(pintar.includes('fireIncidents(focosFiltrados())'), 'los anillos dejaron de usar la regla de la lista');
    assert.ok(!pintar.slice(0, pintar.indexOf('setData')).includes('haversineKm'), 'los anillos siguen filtrando por el centro publicado');
  });

  test('al aplicar, quitar o mover el radio se repintan focos, CONAF e incidentes', () => {
    const aplicar = src.slice(src.indexOf('function aplicarRadio'), src.indexOf('function elegirDistancia'));
    assert.ok(aplicar.includes('repintarPanel'), 'aplicarRadio no repinta el panel');
    const onReadyLine = src.match(/onReady\(\(\) => \{[^}]+\}\)/);
    assert.ok(onReadyLine, 'render no reafirma las capas tras repintar');
    for (const fn of ['pintarFocos()', 'pintarOficiales()', 'pintarIncidentes()', 'pintarCirculoRadio()']) {
      assert.ok(onReadyLine[0].includes(fn), `el repintado con radio no incluye ${fn}`);
    }
  });

  test('al salir de la vista las capas compartidas vuelven a todo Chile', () => {
    const unmount = src.slice(src.indexOf('unmount()'));
    for (const fn of ['pintarFocos()', 'pintarOficiales()', 'pintarIncidentes()']) {
      assert.ok(unmount.includes(fn), `unmount no restaura ${fn}`);
    }
  });

  test('al llegar /api/incidents el panel se repinta y la distancia usa su centro de respaldo', () => {
    const carga = src.slice(src.indexOf('async function loadIncidents'), src.indexOf('alLlegarObservaciones'));
    assert.ok(carga.includes('render(viewEl'), 'loadIncidents no repinta el panel al llegar incidentes');
    assert.ok(src.includes('distDe(i, incidentesPorId.get(i.id))'), 'la fila no usa el centro publicado de respaldo');
  });

  test('una fuente caída avisa junto a los datos que ya se veían', () => {
    assert.ok(src.includes('official.length || officialError'), 'la lista de CONAF tapa el aviso de falla');
    assert.ok(src.includes('fires.length || incidentesError'), 'la lista de incidentes tapa el aviso de falla');
    assert.ok(src.includes('La lista conserva la última consulta'), 'el aviso no distingue datos previos');
  });
});
