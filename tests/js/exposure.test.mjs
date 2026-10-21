/* Pruebas de web/js/exposure.js: la sección «¿A quién afecta?» cruza el Censo 2024
 * (censo_2024.json, OFI-07) y la interfaz urbano-forestal (interfaz.json, OFI-08).
 * El módulo nunca lanza y una fila que falta borra la sección en silencio: si un
 * JSON oficial cambia de forma, tiene que notarse aquí y no en la ficha vacía. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { comunaExposureOf, exposureNumbers } from '../../web/js/exposure.js';

const AHORA = new Date().toISOString();
const CENSO = { fetched_at: AHORA, comunas: [{ code: 1101, name: 'Iquique', poblacion: 199587, viviendas: 75372 }] };
const INTERFAZ = { fetched_at: AHORA, comunas: { '1101': { ha_interfaz: 2735.3, pct_comuna: 1.03 } } };

let seq = 0;
/** Corre exposureSection con fetch fingido; instancia nueva del módulo en cada
 *  llamada porque las promesas de los JSON se cachean a nivel de módulo. */
const seccion = async (censoData, interfazData, code = 1101) => {
  globalThis.fetch = async (path) => {
    const data = path.includes('censo') ? censoData : interfazData;
    if (data instanceof Error) throw data;
    return { ok: true, json: async () => data };
  };
  const mod = await import(`../../web/js/exposure.js?case=${++seq}`);
  return String(await mod.exposureSection(code));
};

describe('exposureNumbers', () => {
  test('resuelve los números de ambas fuentes', () => {
    assert.deepEqual(exposureNumbers(CENSO.comunas[0], INTERFAZ.comunas['1101']),
      { poblacion: 199587, viviendas: 75372, ha_interfaz: 2735.3, pct_comuna: 1.03 });
  });
  test('null donde falte el dato, sin importar cuál fuente falta', () => {
    assert.deepEqual(exposureNumbers(null, null),
      { poblacion: null, viviendas: null, ha_interfaz: null, pct_comuna: null });
    assert.deepEqual(exposureNumbers({ code: 1101, poblacion: 10 }, { pct_comuna: 2 }),
      { poblacion: 10, viviendas: null, ha_interfaz: null, pct_comuna: 2 });
  });
  test('un campo en null o que no es número queda en null, nunca en «null»', () => {
    const n = exposureNumbers({ poblacion: null, viviendas: 'x' }, { ha_interfaz: NaN, pct_comuna: 1 });
    assert.equal(n.poblacion, null);
    assert.equal(n.viviendas, null);
    assert.equal(n.ha_interfaz, null);
  });
});

describe('exposureSection', () => {
  test('censo e interfaz presentes: el HTML es exactamente el que ya se ve', async () => {
    assert.equal(await seccion(CENSO, INTERFAZ), `<h2 class="section" style="margin-top:14px">¿A quién afecta?</h2>
    <div class="callout">
      <p class="small"><b>199.587 personas</b> y <b>75.372 viviendas</b> en la comuna <span class="tiny muted">(INE · Censo 2024)</span>.</p>
      <p class="small"><b>2.735 ha</b> en zona de interfaz urbano-forestal: donde las casas y la vegetación se tocan <span class="tiny muted">(el 1 % de la superficie de la comuna · CONAF GEPRIF)</span>.</p>
      <p class="tiny muted" style="margin-top:6px">Fuentes:
        <a href="https://censo2024.ine.gob.cl/resultados/" target="_blank" rel="noopener">INE · Censo 2024 ↗</a> (recién) · <a href="https://deigeprif.com" target="_blank" rel="noopener">CONAF GEPRIF · Zonas Interfaz ↗</a> (recién)</p>
    </div>`);
  });
  test('censo sin interfaz: el censo se muestra y se dice que falta el dato de interfaz', async () => {
    const out = await seccion(CENSO, { fetched_at: AHORA, comunas: {} });
    assert.ok(out.includes('199.587 personas'));
    assert.ok(out.includes('No tenemos el dato de zona de interfaz urbano-forestal'));
    assert.ok(!out.includes('GEPRIF'));
  });
  test('interfaz sin censo: la interfaz se muestra y se dice que falta el dato del censo', async () => {
    const out = await seccion({ fetched_at: AHORA, comunas: [] }, INTERFAZ);
    assert.ok(out.includes('2.735 ha'));
    assert.ok(out.includes('No tenemos el dato del Censo 2024'));
    assert.ok(!out.includes('personas'));
  });
  test('el porcentaje se declara como superficie, no como población', async () => {
    const out = await seccion(CENSO, INTERFAZ);
    assert.ok(out.includes('% de la superficie de la comuna'));
  });
  test('sin censo ni interfaz la sección devuelve cadena vacía', async () => {
    assert.equal(await seccion({ fetched_at: AHORA, comunas: [] }, { fetched_at: AHORA, comunas: {} }), '');
  });
  test('el código calza como número y como texto, en los dos sentidos', async () => {
    assert.ok((await seccion(CENSO, INTERFAZ, '1101')).includes('personas'));
    const censoTexto = { fetched_at: AHORA, comunas: [{ code: '1101', poblacion: 5, viviendas: 2 }] };
    assert.ok((await seccion(censoTexto, INTERFAZ, 1101)).includes('5 personas'));
  });
  test('un campo del JSON en null no se imprime como «null»', async () => {
    const censoNull = { fetched_at: AHORA, comunas: [{ code: 1101, poblacion: null, viviendas: 75372 }] };
    const out = await seccion(censoNull, { fetched_at: AHORA, comunas: {} });
    assert.ok(!out.includes('null'));
    assert.ok(out.includes('— personas'));
  });
  test('un fetch que falla devuelve cadena vacía, sin lanzar', async () => {
    assert.equal(await seccion(new Error('sin red'), new Error('sin red')), '');
  });
});

describe('comunaExposureOf', () => {
  test('acepta el código como número y como texto, como exposureSection', () => {
    const conNumero = comunaExposureOf(CENSO, INTERFAZ, 1101);
    const conTexto = comunaExposureOf(CENSO, INTERFAZ, '1101');
    assert.ok(conNumero);
    assert.deepEqual(conTexto, conNumero);
    assert.equal(conNumero.poblacion, 199587);
    assert.equal(conNumero.interfaz, true);
  });
  test('una comuna que no está en el censo devuelve null', () => {
    assert.equal(comunaExposureOf(CENSO, INTERFAZ, 9999), null);
  });
  test('en el censo sin interfaz: interfaz queda en false, no en silencio', () => {
    const res = comunaExposureOf(CENSO, { fetched_at: AHORA, comunas: {} }, 1101);
    assert.equal(res.interfaz, false);
    assert.equal(res.viviendas, 75372);
  });
});
