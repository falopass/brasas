/* REND-02 (MAPA-181): carga de infraestructura crítica en teselas de 1° del encuadre visible.
 * pedirInfra, publicaInfra, loadInfra, onInfraMove y fallaInfra no se exportan de
 * web/js/views/mapa.js: la suite recorta esos bloques exactos de la fuente y los corre en
 * node:vm con dobles de fetch, setData, toast, getMap y de la sincronización de capas, al
 * estilo de las suites que leen fuente (mapa-radio, errores). Nada de la lógica está
 * reimplementado aquí: se ejecuta la fuente misma, con promesas controladas por ruta
 * (deferidos) y sin temporizadores. Cada escenario compila su propio contexto, aislado. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

import { INFRA_MINZOOM } from '../../web/js/map.js';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/mapa.js', import.meta.url)), 'utf8');
const URL_INDICE = '/web/data/infraestructura/indice.json';
const urlTesela = (clave) => `/web/data/infraestructura/${clave}.json`;
const AVISO = 'No se pudo cargar la infraestructura crítica.';

/* Recorta un bloque de mapa.js tal como está hoy: desde `desde` hasta `hasta` (null: solo
 * esa línea). Si la fuente cambia de lugar o de forma, el recorte falla nombrando el
 * contrato roto en lugar de pasar por alto otra conducta. */
const extraer = (desde, hasta, contrato) => {
  const inicio = SRC.indexOf(desde);
  assert.ok(inicio !== -1, `mapa.js ya no declara «${desde}» (${contrato})`);
  const fin = hasta === null ? SRC.indexOf('\n', inicio) : SRC.indexOf(hasta, inicio);
  assert.ok(fin > inicio, `mapa.js ya no declara «${hasta ?? 'cierre de línea'}» después de «${desde}» (${contrato})`);
  return SRC.slice(inicio, fin);
};

/* Los helpers de infraestructura con su estado real (mounted, layers, infraVuelo,
 * capaTicket, apagarCapa). `setMounted` es la única puerta extra: el resto es fuente. */
const compilarInfra = () => [
  extraer('let mounted = false;', null, 'estado de montaje'),
  extraer('const layers = {', null, 'estado de capas'),
  extraer('const infraVuelo = new Map()', 'const pedirInfra', 'promesas compartidas por clave'),
  extraer('const feat = (geometry, properties)', null, 'constructor de features'),
  extraer('const pedirInfra = (clave)', 'function publicaInfra()', 'carga por clave'),
  extraer('function publicaInfra()', 'async function loadOfficial', 'publicación de lo acumulado'),
  extraer('async function loadInfra(input, ticket)', 'const onInfraMove', 'lote de teselas del encuadre'),
  extraer('const onInfraMove', null, 'recarga al mover el mapa'),
  extraer('const capaTicket = {};', 'const msjRed', 'reversión con ticket'),
  extraer('function fallaInfra(input, ticket)', 'async function loadSmoke', 'aviso de fallo'),
  'return { pedirInfra, publicaInfra, loadInfra, onInfraMove, fallaInfra, layers, capaTicket, infraVuelo, infraLineas, infraPuntos, setMounted: (v) => { mounted = v; } };',
].join('\n');

/* Mapa doble: encuadre y zoom mutables, porque los lotes cambian de encuadre a mitad
 * del vuelo. Por defecto el encuadre cubre los pisos -36..-35 × -72..-71. */
const crearMapa = (estado = {}) => {
  const m = { zoom: 12, sur: -35.9, oeste: -71.9, norte: -34.1, este: -70.1, ...estado };
  return {
    estado: m,
    getZoom: () => m.zoom,
    getBounds: () => ({ getSouth: () => m.sur, getWest: () => m.oeste, getNorth: () => m.norte, getEast: () => m.este }),
  };
};

/* Compila un contexto por escenario con los dobles como globales. Dos ajustes de ámbito:
 * - las respuestas nacen dentro de vm (cap.json): pedirInfra recorre `body.lines` con
 *   for...of y expande `body.rows`, y no hay que depender de si los símbolos conocidos
 *   se comparten entre contextos;
 * - `setData` normaliza con JSON al capturar: el dato nace en el ámbito de vm y
 *   assert.deepEqual (estricto con los prototipos) no compara objetos de otro ámbito. */
const montar = ({ mapa = crearMapa() } = {}) => {
  const cap = { fetch: [], enVuelo: [], setData: [], toast: [], applyLayers: 0, syncCapaInputs: 0, legend: 0, syncBasemapCredit: 0, updateCapasUrl: 0 };
  const contexto = vm.createContext({
    INFRA_MINZOOM,
    fetch: (ruta) => { cap.fetch.push(ruta); return new Promise((res, rej) => cap.enVuelo.push({ ruta, res, rej })); },
    setData: (id, datos) => { cap.setData.push([id, JSON.parse(JSON.stringify(datos))]); },
    toast: (texto, tono) => { cap.toast.push([texto, tono]); },
    getMap: () => mapa,
    applyLayers: () => { cap.applyLayers += 1; },
    syncCapaInputs: () => { cap.syncCapaInputs += 1; },
    legend: () => { cap.legend += 1; },
    syncBasemapCredit: () => { cap.syncBasemapCredit += 1; },
    updateCapasUrl: () => { cap.updateCapasUrl += 1; },
  });
  cap.json = new vm.Script('JSON').runInContext(contexto); // el JSON del propio ámbito de vm
  const api = new vm.Script(`(() => {\n${compilarInfra()}\n})()`).runInContext(contexto);
  return { api, cap, mapa };
};

/* Responde el pedido en vuelo de una ruta; `caer` lo corta como error de red. */
const responder = (cap, ruta, { ok = true, body } = {}) => {
  const i = cap.enVuelo.findIndex((p) => p.ruta === ruta);
  assert.ok(i !== -1, `no hay pedido en vuelo de ${ruta}`);
  cap.enVuelo.splice(i, 1)[0].res({ ok, json: async () => cap.json.parse(JSON.stringify(body)) });
};
const caer = (cap, ruta) => {
  const i = cap.enVuelo.findIndex((p) => p.ruta === ruta);
  assert.ok(i !== -1, `no hay pedido en vuelo de ${ruta}`);
  cap.enVuelo.splice(i, 1)[0].rej(new TypeError('Failed to fetch'));
};

/* Deja correr la cola de microtareas sin reloj: una vuelta del ciclo de eventos alcanza
 * para todas las continuaciones ya encoladas y las que ellas encadenen. */
const asentar = () => new Promise((res) => setImmediate(res));

const conteo = (cap, ruta) => cap.fetch.filter((r) => r === ruta).length;
const publicados = (cap) => Object.fromEntries(cap.setData);
const indice = (claves) => ({ teselas: Object.fromEntries(claves.map((c) => [c, { bytes: 4200 }])) });
const tesela = (rows = [], lines = []) => ({ rows, lines });
const fila = (lon, lat, k = 'b', n = 'Cuartel 1', s = 'osm', d = 5) => [lon, lat, k, n, s, d];
const linea = (i, coordinates = [[-71.9, -35.9], [-71.1, -35.8]], n = 'Línea 110 kV') => ({ i, coordinates, n, kv: 110000, s: 'osm' });

describe('pedirInfra: una promesa compartida por clave (REND-02)', () => {
  test('llamadas concurrentes del índice y de una tesela producen una sola petición cada una', async () => {
    const { api, cap } = montar();
    const indiceP = [api.pedirInfra('indice'), api.pedirInfra('indice'), api.pedirInfra('indice')];
    const teselaP = [api.pedirInfra('t/-36_-72'), api.pedirInfra('t/-36_-72')];
    assert.deepEqual(cap.fetch, [URL_INDICE, urlTesela('t/-36_-72')]);
    responder(cap, URL_INDICE, { body: indice(['-36_-72']) });
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)]) });
    // las tres llamadas del índice resuelven a lo mismo: body.teselas
    const valores = await Promise.all(indiceP);
    assert.equal(valores[0], valores[1]);
    assert.equal(valores[1], valores[2]);
    assert.ok(valores[0]['-36_-72'], 'el índice resuelve a body.teselas');
    assert.deepEqual(await Promise.all(teselaP), [true, true]);
    // una llamada posterior a la clave ya resuelta no vuelve a pedir
    await api.pedirInfra('t/-36_-72');
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 1);
    assert.ok(api.infraVuelo.has('t/-36_-72'), 'lo que llegó bien queda guardado');
  });

  test('lo que falla se suelta para reintentarlo, sea error del servidor o de red', async () => {
    const { api, cap } = montar();
    const p1 = api.pedirInfra('t/-36_-72');
    responder(cap, urlTesela('t/-36_-72'), { ok: false, body: {} });
    assert.equal(await p1, null);
    assert.ok(!api.infraVuelo.has('t/-36_-72'), 'la clave fallada se suelta');
    const p2 = api.pedirInfra('t/-36_-72');
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 2, 'soltarla hace que el intento siguiente la repita');
    caer(cap, urlTesela('t/-36_-72'));
    assert.equal(await p2, null);
    assert.ok(!api.infraVuelo.has('t/-36_-72'));
  });

  test('una tesela exige rows y lines como arreglos; nada queda a medias si no lo son', async () => {
    const { api, cap } = montar();
    const sinLineas = api.pedirInfra('t/a');
    responder(cap, urlTesela('t/a'), { body: { rows: [], lines: 'no es arreglo' } });
    assert.equal(await sinLineas, null);
    const sinRows = api.pedirInfra('t/b');
    responder(cap, urlTesela('t/b'), { body: { rows: 'no es arreglo', lines: [] } });
    assert.equal(await sinRows, null);
    assert.ok(!api.infraVuelo.has('t/a') && !api.infraVuelo.has('t/b'));
    assert.equal(api.infraPuntos.length, 0);
    assert.equal(api.infraLineas.size, 0);
  });

  test('el índice sin teselas es fallo y se suelta; con teselas queda guardado', async () => {
    const { api, cap } = montar();
    const vacio = api.pedirInfra('indice');
    responder(cap, URL_INDICE, { body: {} });
    assert.equal(await vacio, undefined, 'sin body.teselas no hay índice utilizable');
    assert.ok(!api.infraVuelo.has('indice'), 'el índice sin teselas se suelta para reintentarse');
    const bueno = api.pedirInfra('indice');
    responder(cap, URL_INDICE, { body: indice(['-36_-72']) });
    const valor = await bueno;
    assert.ok(valor?.['-36_-72'], 'el índice con teselas resuelve a body.teselas');
    assert.ok(api.infraVuelo.has('indice'), 'el índice que llegó bien queda guardado');
  });

  test('las líneas se deduplican por id y los puntos llegan como features completos', async () => {
    const { api, cap } = montar();
    const p = api.pedirInfra('t/-36_-72');
    responder(cap, urlTesela('t/-36_-72'), {
      body: tesela([fila(-71.9, -35.9), fila(-71.6, -35.7, 's', 'Hospital', 'minsal')], [linea('l1'), linea('l1'), linea('l2')]),
    });
    await p;
    assert.equal(api.infraLineas.size, 2, 'una línea repetida en el archivo queda una sola vez: manda su id');
    assert.equal(api.infraPuntos.length, 2);
    const [f1, f2] = api.infraPuntos;
    assert.equal(f1.type, 'Feature');
    assert.equal(f1.geometry.type, 'Point');
    assert.equal(f1.geometry.coordinates[0], -71.9);
    assert.equal(f1.geometry.coordinates[1], -35.9);
    assert.equal(f1.properties.k, 'b');
    assert.equal(f1.properties.n, 'Cuartel 1');
    assert.equal(f1.properties.s, 'osm');
    assert.equal(f1.properties.d, 5);
    assert.equal(f2.properties.k, 's');
    assert.equal(f2.properties.n, 'Hospital');
    assert.equal(f2.properties.s, 'minsal');
  });
});

describe('publicaInfra: publica lo acumulado solo montado, prendido y pendiente', () => {
  test('desmontado, apagado o sin dato pendiente no publica; después publica una sola vez', async () => {
    const { api, cap } = montar();
    const p = api.pedirInfra('t/-36_-72');
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    await p;
    api.publicaInfra(); // la vista no está montada
    assert.equal(cap.setData.length, 0);
    api.setMounted(true);
    api.publicaInfra(); // montada, pero la capa está apagada
    assert.equal(cap.setData.length, 0);
    api.layers.infra = true;
    api.publicaInfra(); // montada, prendida y con dato pendiente
    assert.deepEqual(cap.setData.map(([id]) => id), ['infra-puntos', 'infra-lineas']);
    api.publicaInfra(); // ya se publicó: no queda dato pendiente
    assert.equal(cap.setData.length, 2);
    const datos = publicados(cap);
    assert.deepEqual(datos['infra-puntos'], {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-71.9, -35.9] }, properties: { k: 'b', n: 'Cuartel 1', s: 'osm', d: 5 } }],
    });
    assert.equal(datos['infra-lineas'].features.length, 1);
    assert.equal(datos['infra-lineas'].features[0].properties.kv, 110000);
  });
});

describe('loadInfra: el lote del encuadre, completo o nada (REND-02 / MAPA-181)', () => {
  test('pide el índice y solo las teselas que el índice declara dentro del encuadre', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    const lote = api.loadInfra({ checked: true }, 1);
    // el índice declara dos claves del encuadre y una lejana
    responder(cap, URL_INDICE, { body: indice(['-36_-72', '-35_-71', '-40_-73']) });
    await asentar();
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 1);
    assert.equal(conteo(cap, urlTesela('t/-35_-71')), 1);
    assert.equal(conteo(cap, urlTesela('t/-40_-73')), 0, 'una tesela declarada fuera del encuadre no se pide');
    assert.equal(conteo(cap, urlTesela('t/-36_-71')), 0, 'un piso del encuadre que el índice no declara no se pide');
    assert.equal(conteo(cap, urlTesela('t/-35_-72')), 0, 'un piso del encuadre que el índice no declara no se pide');
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    responder(cap, urlTesela('t/-35_-71'), { body: tesela([fila(-71.2, -35.3, 't', 'Subestación')], [linea('l2')]) });
    await lote;
    const datos = publicados(cap);
    assert.deepEqual(Object.keys(datos).sort(), ['infra-lineas', 'infra-puntos']);
    assert.equal(datos['infra-puntos'].features.length, 2);
    assert.equal(datos['infra-puntos'].features[1].properties.k, 't');
    assert.equal(datos['infra-lineas'].features.length, 2);
    assert.equal(cap.toast.length, 0);
    assert.ok(api.layers.infra, 'una carga completa no revierte la capa');
    assert.equal(cap.applyLayers, 0, 'una carga exitosa no toca los interruptores');
  });

  test('con zoom bajo el mínimo, o sin mapa, solo se pide el índice', async () => {
    const bajo = montar({ mapa: crearMapa({ zoom: INFRA_MINZOOM - 1 }) });
    bajo.api.setMounted(true);
    bajo.api.layers.infra = true;
    const loteBajo = bajo.api.loadInfra({ checked: true }, 1);
    responder(bajo.cap, URL_INDICE, { body: indice(['-36_-72']) });
    await loteBajo;
    assert.deepEqual(bajo.cap.fetch, [URL_INDICE], 'el índice (pequeño) sí se pide bajo el zoom mínimo');
    assert.equal(bajo.cap.setData.length, 0, 'a zoom bajo no se publican teselas');
    assert.equal(bajo.cap.toast.length, 0);
    assert.ok(bajo.api.layers.infra, 'no hubo fallo: la capa no se revierte');
    const sin = montar({ mapa: null });
    sin.api.setMounted(true);
    sin.api.layers.infra = true;
    const loteSin = sin.api.loadInfra({ checked: true }, 1);
    responder(sin.cap, URL_INDICE, { body: indice(['-36_-72']) });
    await loteSin;
    assert.deepEqual(sin.cap.fetch, [URL_INDICE]);
    assert.equal(sin.cap.setData.length, 0);
  });

  test('índice caído o sin teselas revierte la capa con el aviso exacto', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    api.capaTicket.infra = 1; // setCapa registra el ticket antes de disparar la carga
    const input = { checked: true };
    const lote = api.loadInfra(input, 1);
    responder(cap, URL_INDICE, { ok: false, body: {} });
    await lote;
    assert.deepEqual(cap.fetch, [URL_INDICE], 'con el índice caído no se pide ninguna tesela');
    assert.deepEqual(cap.toast, [[AVISO, 'error']]);
    assert.equal(api.layers.infra, false, 'la capa se revierte');
    assert.equal(input.checked, false, 'la casilla se suelta');
    assert.equal(cap.applyLayers, 1);
    assert.equal(cap.syncCapaInputs, 1);
    assert.equal(cap.legend, 1);
    assert.equal(cap.syncBasemapCredit, 1);
    assert.equal(cap.updateCapasUrl, 1);
    assert.equal(cap.setData.length, 0);
    assert.ok(!api.infraVuelo.has('indice'), 'el índice caído queda libre para reintentarse');
    // un índice que llegó sin teselas es el mismo contrato
    const sinTeselas = montar();
    sinTeselas.api.setMounted(true);
    sinTeselas.api.layers.infra = true;
    sinTeselas.api.capaTicket.infra = 1;
    const lote2 = sinTeselas.api.loadInfra({ checked: true }, 1);
    responder(sinTeselas.cap, URL_INDICE, { body: {} });
    await lote2;
    assert.deepEqual(sinTeselas.cap.toast, [[AVISO, 'error']]);
    assert.equal(sinTeselas.api.layers.infra, false);
  });

  test('si una tesela del encuadre falla no se publica nada y la capa se revierte', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    api.capaTicket.infra = 1; // setCapa registra el ticket antes de disparar la carga
    const input = { checked: true };
    const lote = api.loadInfra(input, 1);
    responder(cap, URL_INDICE, { body: indice(['-36_-72', '-36_-71']) });
    await asentar();
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    responder(cap, urlTesela('t/-36_-71'), { ok: false, body: {} });
    await lote;
    assert.equal(cap.setData.length, 0, 'lote incompleto: no se publica nada, aunque una tesela llegó');
    assert.deepEqual(cap.toast, [[AVISO, 'error']]);
    assert.equal(api.layers.infra, false);
    assert.equal(input.checked, false);
    assert.equal(cap.applyLayers, 1);
    // lo que llegó bien queda guardado para el próximo intento; lo fallado, libre
    assert.ok(api.infraVuelo.has('t/-36_-72'));
    assert.ok(!api.infraVuelo.has('t/-36_-71'));
  });

  test('la tesela fallida se reintenta al volver a prender y no duplica puntos ni líneas', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    api.capaTicket.infra = 1; // setCapa registra el ticket antes de disparar la carga
    const input = { checked: true };
    const fallo = api.loadInfra(input, 1);
    responder(cap, URL_INDICE, { body: indice(['-36_-72', '-36_-71']) });
    await asentar();
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    responder(cap, urlTesela('t/-36_-71'), { ok: false, body: {} });
    await fallo;
    assert.equal(api.layers.infra, false);
    // la persona vuelve a prender la capa (setCapa: ticket nuevo y casilla marcada)
    api.layers.infra = true;
    api.capaTicket.infra = 2;
    input.checked = true;
    const reintento = api.loadInfra(input, 2);
    await asentar();
    assert.equal(conteo(cap, URL_INDICE), 1, 'el índice no se vuelve a pedir');
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 1, 'la tesela que ya llegó no se vuelve a pedir');
    assert.equal(conteo(cap, urlTesela('t/-36_-71')), 2, 'la tesela fallida sí se reintenta');
    responder(cap, urlTesela('t/-36_-71'), { body: tesela([fila(-71.4, -35.8)], [linea('l2')]) });
    await reintento;
    const datos = publicados(cap);
    assert.equal(datos['infra-puntos'].features.length, 2, 'los puntos de ambas teselas, cada uno una vez');
    assert.equal(datos['infra-lineas'].features.length, 2, 'l1 y l2, sin duplicar');
    assert.equal(cap.toast.length, 1, 'solo avisó el fallo: el reintento exitoso no avisa');
    assert.ok(api.layers.infra);
    assert.equal(input.checked, true);
  });

  test('una línea compartida por teselas vecinas se dibuja una sola vez', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    const lote = api.loadInfra({ checked: true }, 1);
    responder(cap, URL_INDICE, { body: indice(['-36_-72', '-36_-71']) });
    await asentar();
    // la misma línea (mismo id) aparece en ambas teselas: cruza el borde entre pisos
    const tramo = [[-71.9, -35.9], [-71.1, -35.8]];
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1', tramo)]) });
    responder(cap, urlTesela('t/-36_-71'), { body: tesela([fila(-71.4, -35.8)], [linea('l1', tramo)]) });
    await lote;
    const datos = publicados(cap);
    assert.equal(datos['infra-puntos'].features.length, 2, 'hay dos filas de puntos; los vértices de la línea no crean puntos');
    assert.deepEqual(datos['infra-puntos'].features.map((f) => f.geometry.coordinates).sort((a, b) => a[0] - b[0]),
      [[-71.9, -35.9], [-71.4, -35.8]]);
    assert.equal(datos['infra-lineas'].features.length, 1, 'dos teselas vecinas, una sola línea: manda su id');
    assert.deepEqual(datos['infra-lineas'].features[0].geometry.coordinates, tramo);
    assert.equal(datos['infra-lineas'].features[0].properties.kv, 110000);
  });

  test('un encuadre sin teselas declaradas publica lo ya acumulado y pendiente', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    // la tesela se cargó con la capa apagada: quedó acumulada sin publicar
    const p = api.pedirInfra('t/-36_-72');
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    await p;
    assert.equal(cap.setData.length, 0);
    // la persona prende la capa en un encuadre que el índice no declara
    api.layers.infra = true;
    const lote = api.loadInfra({ checked: true }, 1);
    responder(cap, URL_INDICE, { body: indice(['-40_-73']) });
    await lote;
    assert.equal(cap.fetch.length, 2, 'solo el índice y la tesela ya pedida: ninguna del encuadre nuevo');
    assert.equal(conteo(cap, urlTesela('t/-40_-73')), 0);
    const datos = publicados(cap);
    assert.equal(datos['infra-puntos'].features.length, 1, 'publicó lo acumulado del encuadre anterior');
    assert.equal(datos['infra-lineas'].features.length, 1);
    assert.equal(cap.toast.length, 0);
    assert.ok(api.layers.infra);
  });

  test('desmontar o apagar la capa a mitad del vuelo no publica ni avisa', async () => {
    // desmontada la vista con la tesela en vuelo: el dato llega pero no se publica
    const desmontado = montar();
    desmontado.api.setMounted(true);
    desmontado.api.layers.infra = true;
    const lote1 = desmontado.api.loadInfra({ checked: true }, 1);
    responder(desmontado.cap, URL_INDICE, { body: indice(['-36_-72']) });
    await asentar();
    desmontado.api.setMounted(false);
    responder(desmontado.cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)]) });
    await lote1;
    assert.equal(desmontado.cap.setData.length, 0, 'desmontada la vista no se publica');
    assert.equal(desmontado.cap.toast.length, 0);
    assert.equal(desmontado.cap.applyLayers, 0);
    // desmontada con fallo: tampoco avisa
    const desmontadoFallo = montar();
    desmontadoFallo.api.setMounted(true);
    desmontadoFallo.api.layers.infra = true;
    const lote2 = desmontadoFallo.api.loadInfra({ checked: true }, 1);
    responder(desmontadoFallo.cap, URL_INDICE, { body: indice(['-36_-72']) });
    await asentar();
    desmontadoFallo.api.setMounted(false);
    responder(desmontadoFallo.cap, urlTesela('t/-36_-72'), { ok: false, body: {} });
    await lote2;
    assert.equal(desmontadoFallo.cap.toast.length, 0, 'desmontada la vista, el fallo del lote no avisa');
    assert.equal(desmontadoFallo.cap.applyLayers, 0);
    assert.ok(desmontadoFallo.api.layers.infra, 'la capa queda como estaba: nadie la reclamó');
    // apagada la capa con fallo en vuelo: ni avisa ni vuelve a tocar los interruptores
    const apagado = montar();
    apagado.api.setMounted(true);
    apagado.api.layers.infra = true;
    const input = { checked: true };
    const lote3 = apagado.api.loadInfra(input, 1);
    responder(apagado.cap, URL_INDICE, { body: indice(['-36_-72']) });
    await asentar();
    apagado.api.layers.infra = false;
    responder(apagado.cap, urlTesela('t/-36_-72'), { ok: false, body: {} });
    await lote3;
    assert.equal(apagado.cap.setData.length, 0);
    assert.equal(apagado.cap.toast.length, 0, 'apagada la capa, el fallo del lote no avisa');
    assert.equal(apagado.cap.applyLayers, 0, 'ni vuelve a tocar los interruptores');
    assert.equal(input.checked, true, 'la casilla de la persona queda como la dejó');
  });

  test('un ticket viejo no apaga ni avisa una capa que la persona volvió a prender', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    api.capaTicket.infra = 1;
    const input = { checked: true };
    const lote = api.loadInfra(input, 1);
    responder(cap, URL_INDICE, { body: indice(['-36_-72']) });
    await asentar();
    // la persona apagó y volvió a prender mientras la tesela seguía en vuelo: el ticket avanzó
    api.capaTicket.infra = 2;
    responder(cap, urlTesela('t/-36_-72'), { ok: false, body: {} });
    await lote;
    assert.equal(cap.toast.length, 0, 'el fracaso del lote viejo no avisa');
    assert.equal(api.layers.infra, true, 'la capa que la persona volvió a prender sigue prendida');
    assert.equal(input.checked, true);
    assert.equal(cap.applyLayers, 0);
    assert.equal(cap.setData.length, 0);
  });

  test('el fallo de un lote superado no apaga la capa cuando el lote más nuevo terminó bien', async () => {
    const { api, cap, mapa } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    const input = { checked: true };
    // lote 1: encuadre que declara t/-36_-72
    const lote1 = api.loadInfra(input, 1);
    responder(cap, URL_INDICE, { body: indice(['-36_-72', '-34_-71']) });
    await asentar();
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 1);
    // la vista se movió: lote 2 con un encuadre que declara t/-34_-71
    mapa.estado.sur = -33.9;
    mapa.estado.oeste = -70.9;
    mapa.estado.norte = -33.1;
    mapa.estado.este = -70.1;
    const lote2 = api.loadInfra(input, 2);
    await asentar();
    assert.equal(conteo(cap, urlTesela('t/-34_-71')), 1, 'el lote nuevo pide su tesela');
    assert.equal(conteo(cap, URL_INDICE), 1, 'el índice sigue compartido entre lotes');
    // orden de respuestas invertido: la del lote nuevo llega primero y bien
    responder(cap, urlTesela('t/-34_-71'), { body: tesela([fila(-70.5, -33.5, 'e', 'Escuela')]) });
    await lote2;
    assert.equal(publicados(cap)['infra-puntos'].features.length, 1, 'el lote nuevo publicó');
    assert.equal(cap.toast.length, 0);
    // recién ahora cae la tesela del lote viejo: ya superado, no puede revertir la capa
    responder(cap, urlTesela('t/-36_-72'), { ok: false, body: {} });
    await Promise.allSettled([lote1]);
    assert.equal(cap.toast.length, 0, 'el fallo del lote superado no avisa');
    assert.equal(api.layers.infra, true, 'la capa sigue prendida: el lote más nuevo terminó bien');
    assert.equal(cap.applyLayers, 0);
    assert.equal(input.checked, true);
  });
});

describe('onInfraMove: recarga al mover, con las mismas llaves que la carga (REND-02)', () => {
  test('solo recarga con la vista montada y la capa prendida', () => {
    const { api, cap } = montar();
    api.onInfraMove();
    assert.equal(cap.fetch.length, 0, 'desmontada la vista no recarga');
    api.setMounted(true);
    api.onInfraMove();
    assert.equal(cap.fetch.length, 0, 'con la capa apagada no recarga');
    api.layers.infra = true;
    api.onInfraMove();
    assert.equal(conteo(cap, URL_INDICE), 1, 'montada y prendida recarga: pide el índice');
  });

  test('reentrada inmediata (dos moveend seguidos) no duplica peticiones ni datos', async () => {
    const { api, cap } = montar();
    api.setMounted(true);
    api.layers.infra = true;
    api.capaTicket.infra = 3;
    api.onInfraMove();
    api.onInfraMove();
    assert.equal(conteo(cap, URL_INDICE), 1, 'el índice se pide una sola vez aunque se reentra');
    responder(cap, URL_INDICE, { body: indice(['-36_-72']) });
    await asentar();
    assert.equal(conteo(cap, urlTesela('t/-36_-72')), 1, 'la tesela también se pide una sola vez');
    responder(cap, urlTesela('t/-36_-72'), { body: tesela([fila(-71.9, -35.9)], [linea('l1')]) });
    await asentar();
    assert.equal(cap.setData.length, 2, 'una sola publicación');
    const datos = publicados(cap);
    assert.equal(datos['infra-puntos'].features.length, 1, 'cada punto una vez');
    assert.equal(datos['infra-lineas'].features.length, 1);
    assert.equal(cap.toast.length, 0);
    assert.ok(api.layers.infra);
  });
});

describe('guardas de fuente de mapa.js (REND-02)', () => {
  test('el moveend de infraestructura se enlaza al montar y se retira al desmontar', () => {
    const montado = SRC.slice(SRC.indexOf('async mount(container'));
    assert.ok(montado.includes("m.on('moveend', onInfraMove)"), 'mount ya no enlaza el moveend de infraestructura');
    const desmontado = SRC.slice(SRC.indexOf('unmount() {'));
    assert.ok(desmontado.includes("m?.off('moveend', onInfraMove)"), 'unmount ya no retira el moveend de infraestructura');
  });

  test('encender la casilla de infraestructura dispara loadInfra con su input y el ticket recién emitido', () => {
    const setCapa = SRC.slice(SRC.indexOf('async function setCapa'), SRC.indexOf('function loadComunasIndex'));
    assert.ok(setCapa.includes('infra: loadInfra'), 'la casilla de infraestructura ya no carga en diferido');
    assert.ok(setCapa.includes('await lazy(input, ticket)'), 'la carga diferida ya no recibe el input y el ticket');
  });

  test('onInfraMove viaja con el ticket vigente de la capa', () => {
    const recarga = extraer('const onInfraMove', null, 'recarga al mover el mapa');
    assert.ok(recarga.includes('mounted && layers.infra'), 'la recarga exige montaje y capa prendida');
    assert.ok(recarga.includes('capaTicket.infra'), 'la recarga viaja con el ticket vigente');
  });

  test('el umbral publicado es zoom 10, compartido con map.js', () => {
    assert.equal(INFRA_MINZOOM, 10, 'el umbral de infraestructura cambió: revisar leyenda y esta suite');
  });
});
