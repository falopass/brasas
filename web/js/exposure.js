/* Exposición por comuna: quiénes viven donde el fuego puede llegar.
 * Lee censo_2024.json (OFI-07), interfaz.json (OFI-08) y campamentos.json (OFI-25)
 * como archivos estáticos, una sola vez por sesión. Si falta el dato de una fuente
 * para una comuna que sí está en otra, la sección lo dice en vez de callarlo. */
import { ago, fmtNum, html } from './util.js';

let censoPromise = null;
let interfazPromise = null;
let campamentosPromise = null;
/* true solo si las tres descargas de la última loadExposureIndex respondieron.
 * Un índice con una fuente en null no se conserva: la próxima petición reintenta. */
let fuentesOk = false;
export const exposureFuentesOk = () => fuentesOk;

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

function campamentos() {
  return (campamentosPromise ??= load('/web/data/campamentos.json').catch(() => { campamentosPromise = null; return null; }));
}

function campamentoDe(campData, code) {
  const list = Array.isArray(campData?.comunas) ? campData.comunas : [];
  return list.find((c) => String(c.code) === String(code)) || null;
}

/* Tope de la estimación: 80.000 viviendas del Censo y 2.000 hogares en campamentos
 * saturan su tramo. Por encima de eso el factor no sube más. */
const TOPE_VIVIENDAS = 80000;
const TOPE_HOGARES_CAMP = 2000;

/** Factor orientativo de exposición, entre 1 y 2.
 *  1 sin señales. Suma 0,40 si hay interfaz urbano-forestal,
 *  hasta 0,30 según viviendas del Censo 2024 y hasta 0,30 según hogares
 *  del catastro de campamentos MINVU. Estimación de BRASA, no un índice oficial. */
export function exposureFactor(partes) {
  const ha = Number(partes?.ha_interfaz);
  const viv = Number(partes?.viviendas);
  const hog = Number(partes?.n_hogares ?? partes?.n_hogares_campamentos);
  const porInterfaz = Number.isFinite(ha) && ha > 0 ? 0.4 : 0;
  const porViviendas = Number.isFinite(viv) && viv > 0 ? 0.3 * Math.min(1, viv / TOPE_VIVIENDAS) : 0;
  const porCampamentos = Number.isFinite(hog) && hog > 0 ? 0.3 * Math.min(1, hog / TOPE_HOGARES_CAMP) : 0;
  return Math.min(2, Math.max(1, 1 + porInterfaz + porViviendas + porCampamentos));
}

/** Diccionario code → { factor } para ordenar el ranking por peligro × exposición.
 *  Sin red o sin archivos devuelve un objeto vacío y el ranking usa factor 1. */
export async function loadExposureIndex() {
  fuentesOk = false;
  const [censoData, interfazData, campData] = await Promise.all([
    censo().catch(() => null),
    interfaz(),
    campamentos(),
  ]);
  fuentesOk = censoData != null && interfazData != null && campData != null;
  const censoPorCodigo = new Map((censoData?.comunas || []).map((c) => [String(c.code), c]));
  const interfazPorCodigo = interfazData?.comunas || {};
  const campPorCodigo = new Map((Array.isArray(campData?.comunas) ? campData.comunas : []).map((c) => [String(c.code), c]));
  const codes = new Set([...censoPorCodigo.keys(), ...Object.keys(interfazPorCodigo), ...campPorCodigo.keys()]);
  const out = {};
  for (const code of codes) {
    const row = censoPorCodigo.get(code);
    const zona = interfazPorCodigo[code];
    const camp = campPorCodigo.get(code);
    out[code] = {
      factor: exposureFactor({
        ha_interfaz: zona?.ha_interfaz,
        viviendas: row?.viviendas,
        n_hogares: camp?.n_hogares,
      }),
    };
  }
  return out;
}

/* RISK-23: la ficha institucional de la comuna (bloque `temporada.cicatrices`,
 * huella de detecciones de los últimos 90 días), una petición perezosa cacheada por comuna. */
const fichaPromises = {};

function ficha(code) {
  return (fichaPromises[code] ??= Promise.resolve().then(() => fetch(`/api/comuna/${code}`))
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => { delete fichaPromises[code]; return null; }));
}

/** Las cifras de la sección ya resueltas: el número de cada JSON oficial, o null donde
 *  falte o no sea un número (un «null» del archivo nunca llega a la pantalla). */
export function exposureNumbers(row, zona, camp) {
  const num = (v) => (Number.isFinite(v) ? v : null);
  const base = {
    poblacion: num(row?.poblacion),
    viviendas: num(row?.viviendas),
    ha_interfaz: num(zona?.ha_interfaz),
    pct_comuna: num(zona?.pct_comuna),
  };
  // Dos argumentos conservan las cuatro cifras: hay pruebas que comparan el objeto entero.
  if (arguments.length < 3) return base;
  return {
    ...base,
    n_campamentos: num(camp?.n_campamentos),
    n_hogares_campamentos: num(camp?.n_hogares),
  };
}

/** Sección «¿A quién afecta?» de la ficha de comuna: población, viviendas y zona de
 *  interfaz urbano-forestal, cada cifra con su fuente y fecha. Nunca lanza: sin datos
 *  o sin conexión devuelve cadena vacía. */
export async function exposureSection(code) {
  const [censoData, interfazData, campData, fichaData] = await Promise.all([
    censo().catch(() => null),
    interfaz(),
    campamentos(),
    ficha(code),
  ]);
  const row = (censoData?.comunas || []).find((c) => String(c.code) === String(code));
  const zona = interfazData?.comunas?.[String(code)];
  const camp = campamentoDe(campData, code);
  const n = exposureNumbers(row, zona, camp);
  if (!row && !zona && !(n.n_campamentos > 0)) return '';
  const cic = fichaData?.temporada?.cicatrices;
  return html`<h2 class="section" style="margin-top:14px">¿A quién afecta?</h2>
    <div class="callout">
      ${row
        ? html`<p class="small"><b>${fmtNum(n.poblacion)} personas</b> y <b>${fmtNum(n.viviendas)} viviendas</b> en la comuna <span class="tiny muted">(INE · Censo 2024)</span>.</p>`
        : html`<p class="small muted">No tenemos el dato del Censo 2024 para esta comuna.</p>`}
      ${zona
        ? html`<p class="small"><b>${fmtNum(n.ha_interfaz)} ha</b> en zona de interfaz urbano-forestal: donde las casas y la vegetación se tocan <span class="tiny muted">(el ${fmtNum(n.pct_comuna, 1)} % de la superficie de la comuna · CONAF GEPRIF)</span>.</p>`
        : html`<p class="small muted">No tenemos el dato de zona de interfaz urbano-forestal para esta comuna.</p>`}${cic?.ha > 0
        ? html`
      <p class="small">En los últimos 90 días, los satélites vieron calor en <b>${fmtNum(cic.ha)} ha</b> de esta comuna (${fmtNum(cic.n_incidentes)} ${cic.n_incidentes === 1 ? 'foco' : 'focos'} con ficha) <span class="tiny muted">(huella de detecciones, no el perímetro oficial de CONAF)</span>.</p>`
        : cic?.note ? html`
      <p class="small muted">${cic.note}</p>` : ''}${n.n_campamentos > 0 ? html`
      <p class="small"><b>${fmtNum(n.n_campamentos)} ${n.n_campamentos === 1 ? 'campamento' : 'campamentos'}</b> (${fmtNum(n.n_hogares_campamentos)} hogares) registrados en el catastro público <span class="tiny muted">(MINVU · Catastro de Campamentos)</span>.</p>` : ''}
      <p class="tiny muted" style="margin-top:6px">Fuentes:
        ${row ? html`<a href="https://censo2024.ine.gob.cl/resultados/" target="_blank" rel="noopener">INE · Censo 2024 ↗</a> (${ago(censoData.fetched_at)})` : ''}${row && zona ? ' · ' : ''}${zona ? html`<a href="https://deigeprif.com" target="_blank" rel="noopener">CONAF GEPRIF · Zonas Interfaz ↗</a> (${ago(interfazData.fetched_at)})` : ''}${n.n_campamentos > 0 ? html`${row || zona ? ' · ' : ''}<a href="https://geoide.minvu.cl/server/rest/services/Catastros/Catastros_campamentos/FeatureServer" target="_blank" rel="noopener">MINVU · Catastro de Campamentos ↗</a>${campData?.generated_at ? ` (${ago(campData.generated_at)})` : ''}` : ''}</p>
    </div>`;
}

/** Destila censo + interfaz a lo que muestra la vista compartida «Lo que hay alrededor»:
 *  población y viviendas del Censo 2024 y si la comuna tiene zonas de interfaz.
 *  null cuando la comuna no está en el censo: sin censo no hay nada que contar. */
export function comunaExposureOf(censoData, interfazData, code, campData = null) {
  const row = (censoData?.comunas || []).find((c) => String(c.code) === String(code));
  if (!row) return null;
  const base = { poblacion: row.poblacion, viviendas: row.viviendas, interfaz: Boolean(interfazData?.comunas?.[String(code)]) };
  // Tres argumentos conservan población, viviendas e interfaz. El cuarto suma campamentos.
  if (arguments.length < 4) return base;
  const list = campData?.comunas;
  // Sin lista no hay catastro: null, nunca un cero inventado. Cero solo si la lista cargó y la comuna no está.
  if (!Array.isArray(list)) return { ...base, n_campamentos: null, n_hogares_campamentos: null };
  const camp = list.find((c) => String(c.code) === String(code));
  return { ...base, n_campamentos: camp?.n_campamentos ?? 0, n_hogares_campamentos: camp?.n_hogares ?? 0 };
}

/** El resumen de arriba con los archivos estáticos ya descargados. Nunca lanza:
 *  sin datos o sin conexión devuelve null y la vista simplemente no muestra la sección. */
export async function comunaExposure(code) {
  const [censoData, interfazData, campData] = await Promise.all([
    censo().catch(() => null),
    interfaz(),
    campamentos(),
  ]);
  return comunaExposureOf(censoData, interfazData, code, campData);
}
