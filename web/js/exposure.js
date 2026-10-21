/* Exposición por comuna: quiénes viven donde el fuego puede llegar.
 * Lee censo_2024.json (OFI-07) e interfaz.json (OFI-08) como archivos estáticos,
 * una sola vez por sesión. Si falta el dato de una fuente para una comuna que sí
 * está en la otra, la sección lo dice en vez de callarlo. */
import { ago, fmtNum, html } from './util.js';

let censoPromise = null;
let interfazPromise = null;

const load = (path) => fetch(path).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
});

function censo() {
  return (censoPromise ??= load('/web/data/censo_2024.json').catch((e) => { censoPromise = null; throw e; }));
}

function interfaz() {
  return (interfazPromise ??= load('/web/data/interfaz.json').catch(() => { interfazPromise = null; return null; }));
}

/** Las cifras de la sección ya resueltas: el número de cada JSON oficial, o null donde
 *  falte o no sea un número (un «null» del archivo nunca llega a la pantalla). */
export function exposureNumbers(row, zona) {
  const num = (v) => (Number.isFinite(v) ? v : null);
  return {
    poblacion: num(row?.poblacion),
    viviendas: num(row?.viviendas),
    ha_interfaz: num(zona?.ha_interfaz),
    pct_comuna: num(zona?.pct_comuna),
  };
}

/** Sección «¿A quién afecta?» de la ficha de comuna: población, viviendas y zona de
 *  interfaz urbano-forestal, cada cifra con su fuente y fecha. Nunca lanza: sin datos
 *  o sin conexión devuelve cadena vacía. */
export async function exposureSection(code) {
  const censoData = await censo().catch(() => null);
  const interfazData = await interfaz();
  const row = (censoData?.comunas || []).find((c) => String(c.code) === String(code));
  const zona = interfazData?.comunas?.[String(code)];
  if (!row && !zona) return '';
  const n = exposureNumbers(row, zona);
  return html`<h2 class="section" style="margin-top:14px">¿A quién afecta?</h2>
    <div class="callout">
      ${row
        ? html`<p class="small"><b>${fmtNum(n.poblacion)} personas</b> y <b>${fmtNum(n.viviendas)} viviendas</b> en la comuna <span class="tiny muted">(INE · Censo 2024)</span>.</p>`
        : html`<p class="small muted">No tenemos el dato del Censo 2024 para esta comuna.</p>`}
      ${zona
        ? html`<p class="small"><b>${fmtNum(n.ha_interfaz)} ha</b> en zona de interfaz urbano-forestal: donde las casas y la vegetación se tocan <span class="tiny muted">(el ${fmtNum(n.pct_comuna, 1)} % de la superficie de la comuna · CONAF GEPRIF)</span>.</p>`
        : html`<p class="small muted">No tenemos el dato de zona de interfaz urbano-forestal para esta comuna.</p>`}
      <p class="tiny muted" style="margin-top:6px">Fuentes:
        ${row ? html`<a href="https://censo2024.ine.gob.cl/resultados/" target="_blank" rel="noopener">INE · Censo 2024 ↗</a> (${ago(censoData.fetched_at)})` : ''}${row && zona ? ' · ' : ''}${zona ? html`<a href="https://deigeprif.com" target="_blank" rel="noopener">CONAF GEPRIF · Zonas Interfaz ↗</a> (${ago(interfazData.fetched_at)})` : ''}</p>
    </div>`;
}

/** Destila censo + interfaz a lo que muestra la vista compartida «Lo que hay alrededor»:
 *  población y viviendas del Censo 2024 y si la comuna tiene zonas de interfaz.
 *  null cuando la comuna no está en el censo: sin censo no hay nada que contar. */
export function comunaExposureOf(censoData, interfazData, code) {
  const row = (censoData?.comunas || []).find((c) => String(c.code) === String(code));
  if (!row) return null;
  return { poblacion: row.poblacion, viviendas: row.viviendas, interfaz: Boolean(interfazData?.comunas?.[String(code)]) };
}

/** El resumen de arriba con los archivos estáticos ya descargados. Nunca lanza:
 *  sin datos o sin conexión devuelve null y la vista simplemente no muestra la sección. */
export async function comunaExposure(code) {
  const censoData = await censo().catch(() => null);
  const interfazData = await interfaz();
  return comunaExposureOf(censoData, interfazData, code);
}
