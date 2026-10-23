/* La hoja A4 de emergencia (/lista.html) debe ser alcanzable desde la interfaz:
 * este test revisa que la vista Prepárate la enlace (REV-11). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';
import { planSheet, planText } from '../../web/js/plan.js';
import { diasDesde, estadoTarea, MANTENIMIENTO, vence } from '../../web/js/mantenimiento.js';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/preparate.js', import.meta.url)), 'utf8');

/* preparate.js importa speak.js, que lee `window` al cargar. index.js junta todas las
 * suites en un proceso y esta corre antes que speak.test.mjs: importarla aquí dejaría
 * `synth` en null y rompería las pruebas de voz, así que la vista se importa en un hilo
 * aparte con el stub mínimo y se pide un resumen en datos planos (mismo patrón que
 * quehago.test.mjs). */
const M = await new Promise((resolve, reject) => {
  const url = new URL('../../web/js/views/preparate.js', import.meta.url).href;
  const comunasPath = fileURLToPath(new URL('../../web/data/comunas-index.json', import.meta.url));
  const worker = new Worker(`
    const { parentPort } = require('node:worker_threads');
    const { readFileSync } = require('node:fs');
    globalThis.window = { addEventListener() {} }; // ui.js se suscribe a «online» al importarse
    const comunas = JSON.parse(readFileSync(${JSON.stringify(comunasPath)}, 'utf8'));
    import(${JSON.stringify(url)}).then((m) => {
      const niveles = ['bajo', 'moderado', 'alto', 'extremo'].map((nivel) => m.accionesDeHoy({ nivel, lugar: { name: 'Talca' } }).acciones);
      parentPort.postMessage({
        emergencia: m.EMERGENCIA.map((b) => ({ id: b.id, pasos: b.pasos.length })),
        textoDurante: m.textoEmergencia(m.EMERGENCIA[1]),
        talca: m.comunaDelLugar({ lon: -71.6035, lat: -35.4211 }, comunas),
        sinLugar: [m.comunaDelLugar(null, comunas), m.comunaDelLugar({ lon: -71.6, lat: -35.4 }, null), m.comunaDelLugar({ lon: -71.6 }, comunas)],
        extremo: m.accionesDeHoy({ nivel: 'extremo', lugar: { name: 'Talca' } }),
        sinNivel: [m.accionesDeHoy({ nivel: null, lugar: { name: 'Talca' } }), m.accionesDeHoy({ nivel: 'bajo' })],
        niveles,
      });
      parentPort.close();
    }, (e) => { throw e; });
  `, { eval: true });
  worker.once('message', resolve);
  worker.once('error', reject);
});

describe('enlace a la hoja de emergencia', () => {
  test('la vista Prepárate enlaza a /lista.html', () => {
    assert.ok(SRC.includes('href="/lista.html"'), 'preparate.js debe enlazar a /lista.html');
  });
  test('la hoja del refrigerador abre en otra pestaña (PREP-04)', () => {
    assert.match(SRC, /href="\/lista\.html" target="_blank" rel="noopener"/);
  });
});

describe('«Si hay un incendio cerca» se puede escuchar (PREP-04)', () => {
  test('los tres bloques existen y cada uno pinta su botón «Escuchar»', () => {
    assert.deepEqual(M.emergencia.map((b) => b.id), ['antes', 'durante', 'después']);
    for (const b of M.emergencia) assert.ok(b.pasos >= 3, b.id);
    assert.ok(SRC.includes('data-listen'), 'cada bloque debe pintar un botón con data-listen');
    assert.ok(SRC.includes('Escuchar los pasos:'), 'el aria-label debe decir qué se escucha');
  });
  test('la locución sale de la misma estructura que se pinta', () => {
    assert.ok(M.textoDurante.startsWith('Durante: si la autoridad ordena evacuar.'));
    assert.ok(M.textoDurante.includes('Sal de inmediato'), 'el texto leído incluye los pasos del bloque');
    assert.ok(!M.textoDurante.includes('<'), 'la voz no debe leer etiquetas HTML');
    assert.ok(SRC.includes('speak(textoEmergencia(b)'), 'speak() debe leer el mismo arreglo que el HTML');
  });
  test('la lectura se corta al plegar o al salir de la vista', () => {
    assert.ok(SRC.includes("addEventListener('toggle'"), 'los details deben escuchar «toggle»');
    assert.ok(SRC.includes('unmount() { stopSpeak(); }'), 'la vista debe detener la voz al salir');
  });
});

describe('puntaje de la mochila y descarga del plan (UX-53)', () => {
  test('la mochila se pinta y se enlaza como lista evaluada', () => {
    assert.match(SRC, /checklist\('mochila', BAG_CHECKLIST, true/, 'la mochila debe evaluarse con puntaje');
    assert.match(SRC, /bindChecklist\(container, 'mochila', BAG_CHECKLIST, true/, 'bindChecklist de la mochila debe recibir scored');
  });
  test('existe el botón «Descargar plan» en la vista', () => {
    assert.ok(SRC.includes('id="download-plan"'), 'preparate.js debe tener el botón de descarga');
    assert.ok(SRC.includes('Descargar plan'), 'el botón debe decir «Descargar plan»');
  });
  test('la descarga arma un archivo .txt y libera el URL', () => {
    assert.ok(SRC.includes('plan-familiar-brasa.txt'), 'el archivo debe llamarse plan-familiar-brasa.txt');
    assert.ok(SRC.includes('createObjectURL') && SRC.includes('revokeObjectURL'), 'debe usar Blob URL y revocarlo');
  });
});

describe('hoja imprimible del plan familiar (UX-41)', () => {
  test('la hoja escapa los valores guardados', () => {
    const sheet = planSheet({ encuentro: '<b>plaza</b>' });
    assert.ok(sheet.includes('&lt;b&gt;plaza&lt;/b&gt;'));
    assert.ok(!sheet.includes('<b>plaza</b>'));
  });
  test('planText incluye los campos y lo marcado en la mochila', () => {
    const t = planText({ ruta1: 'por el cerro' }, { agua: true });
    assert.ok(t.includes('Ruta de salida principal: por el cerro'));
    assert.ok(t.includes('[x] Agua para 2 a 3 días'));
    assert.ok(t.includes('[ ] Copia de llaves'));
  });
});

describe('mantenimiento de la casa con fecha (PREP-03)', () => {
  const hoy = new Date('2026-06-15T12:00:00Z');
  const hace = (dias) => new Date(hoy.getTime() - dias * 86400000).toISOString();
  test('sin fecha válida devuelve sin-registrar y null nunca revienta', () => {
    for (const mala of [null, undefined, '', 'ayer', '2026-13-45']) {
      assert.equal(estadoTarea(mala, 6, hoy), 'sin-registrar', String(mala));
    }
    assert.equal(vence(null, 6, hoy), null);
    assert.equal(diasDesde(null, hoy), null);
  });
  test('hecha hace 100 días con caducidad de 6 meses sigue al día', () => {
    assert.equal(estadoTarea(hace(100), 6, hoy), 'al-dia');
    assert.equal(vence(hace(100), 6, hoy), false);
  });
  test('hecha hace 200 días con caducidad de 6 meses toca de nuevo', () => {
    assert.equal(estadoTarea(hace(200), 6, hoy), 'toca');
    assert.equal(vence(hace(200), 6, hoy), true);
  });
  test('con caducidad de 12 meses, 364 días sigue al día y 366 toca', () => {
    assert.equal(estadoTarea(hace(364), 12, hoy), 'al-dia');
    assert.equal(vence(hace(364), 12, hoy), false);
    assert.equal(estadoTarea(hace(366), 12, hoy), 'toca');
  });
  test('diasDesde cuenta días completos', () => {
    assert.equal(diasDesde(hace(8), hoy), 8);
    assert.equal(diasDesde(hoy.toISOString(), hoy), 0);
  });
  test('la lista trae 5 tareas y cada una cita una fuente ya declarada en la vista', () => {
    assert.equal(MANTENIMIENTO.length, 5);
    for (const t of MANTENIMIENTO) {
      assert.ok(t.clave && t.texto && Number.isFinite(t.meses) && t.fuente, `tarea incompleta: ${t.clave}`);
      assert.match(SRC, new RegExp(`\\n  ${t.fuente}: \\[`), `la fuente «${t.fuente}» debe existir en el diccionario SRC`);
    }
  });
  test('la vista pinta la etiqueta «toca de nuevo» y guarda fechas aparte', () => {
    assert.ok(SRC.includes('toca de nuevo'), 'la vista debe pintar la etiqueta de las tareas vencidas');
    assert.ok(SRC.includes('check:casa:fechas'), 'las fechas se guardan bajo check:casa:fechas');
    assert.ok(SRC.includes('data-list="mantenimiento"'), 'el bloque tiene su propia lista');
    assert.ok(!SRC.includes("checklist('mantenimiento'"), 'el mantenimiento no suma al puntaje existente');
  });
});

describe('comunas prioritarias sin verificar (OFI-05)', () => {
  test('la ficha no presenta como oficial una lista sin verificar', () => {
    assert.ok(SRC.includes('Sin verificar:'), 'la lista sin verificar debe anunciarse como tal');
  });
});

describe('comunaDelLugar', () => {
  test('resuelve la comuna más cercana al lugar (Talca)', () => {
    assert.equal(M.talca, 7101);
  });
  test('sin lugar o sin índice devuelve null', () => {
    assert.deepEqual(M.sinLugar, [null, null, null]);
  });
});

describe('accionesDeHoy', () => {
  test('con nivel y lugar devuelve título, 3 acciones y fuente', () => {
    const hoy = M.extremo;
    assert.equal(hoy.acciones.length, 3);
    assert.ok(hoy.titulo.includes('Talca'));
    assert.ok(hoy.titulo.includes('extremo'));
    assert.ok(hoy.fuente.includes('no una alerta oficial'));
  });
  test('sin nivel o sin lugar devuelve null', () => {
    assert.deepEqual(M.sinNivel, [null, null]);
  });
  test('los cuatro niveles tienen listas distintas', () => {
    const listas = M.niveles;
    for (let i = 0; i < listas.length; i++) {
      for (let j = i + 1; j < listas.length; j++) {
        assert.notDeepEqual(listas[i], listas[j], `${i} vs ${j}`);
      }
    }
  });
  test('la vista solo pinta la tarjeta con el riesgo guardado hoy', () => {
    assert.ok(SRC.includes("store.get('risk')"), 'la vista debe leer el riesgo del store');
    assert.ok(SRC.includes('#/mi-zona'), 'la tarjeta debe enlazar a mi-zona');
  });
});
