/* Mapa 2D (MapLibre): estilo propio claro/oscuro sobre OpenFreeMap (datos © OpenStreetMap
   contributors, ODbL; esquema OpenMapTiles, CC-BY), con base sin conexión de comunas reales.
   MAPA-105: solo capas base de licencia abierta. En escritorio el control de atribución
   de MapLibre va expandido (`compact: false`). En móvil (<= 899 px) la barra sobre el
   lienzo se oculta para despejar el mapa; los créditos y enlaces de cada fondo se
   consultan en «Capas», en «De dónde vienen los datos» del panel y en «Calidad de los
   datos» (`#/calidad`). La satelital es EOxCloudless 2016 de EOX (CC BY 4.0): ver
   docs/FUENTES.md «Mapas base». */
import { CELL_ZOOM_MAX, decimatePoints, elegirObjetivo } from './capas.js';
import { fechaGibs, GIBS, GIBS_ATTRIBUTION, gibsTileUrl, tiempoGibs, WMS_LAYERS, wmsTileUrl } from './gibs.js';
import { store } from './store.js';
import { circlePolygon, heatBlob, pixelKm, seedFrom } from './util.js';
import { SMOKE_COLOR, SMOKE_DENSITY_COLOR, smokeFillColorExpr, smokeFillOpacityExpr } from './smoke.js';

export const OFM = 'https://tiles.openfreemap.org';
// Familia de glyphs de las etiquetas del estilo (nombres de lugares, conteos y
// etiquetas propias): mapa-offline.js la descarga junto con las teselas (MAPA-166).
export const GLYPH_FONTS = ['Noto Sans Regular'];
export const BASEMAPS = {
  mapa: { label: 'Mapa' },
  satelite: {
    label: 'Satélite',
    tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg'],
    attribution: 'EOxCloudless 2016 – <a href="https://cloudless.eox.at" target="_blank" rel="noopener">https://cloudless.eox.at</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016, CC BY 4.0)',
    maxzoom: 14,
  },
  topo: {
    label: 'Topográfico',
    tiles: ['https://a.tile.opentopomap.org/{z}/{x}/{y}.png', 'https://b.tile.opentopomap.org/{z}/{x}/{y}.png'],
    attribution: '© <a href="https://opentopomap.org" target="_blank" rel="noopener">OpenTopoMap</a> (CC-BY-SA), © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    maxzoom: 17,
  },
};

const PALETTE = {
  // Carbón y ceniza, como la interfaz: el mapa es suelo, los focos son lo único encendido.
  dark: {
    background: '#100f0d', ocean: '#0a0b0c', water: '#0c1012', land: '#171512', chile: '#1a1815', wood: '#191a15', grass: '#1b1a16',
    urban: '#24211d', road: '#2e2a25', roadMajor: '#4a443c', boundary: '#6b6358', comuna: 'rgba(237,231,221,0.12)',
    region: 'rgba(237,231,221,0.36)', label: '#d9d2c6', labelHalo: '#100f0d', minorLabel: '#9a9184',
  },
  light: {
    background: '#e6dfd3', ocean: '#cfd3d1', water: '#c5ccca', land: '#ece6dc', chile: '#efe9df', wood: '#dcdccb', grass: '#e4e0d0',
    urban: '#ddd5c7', road: '#f6f2ea', roadMajor: '#d8c9b2', boundary: '#857c6f', comuna: 'rgba(18,16,14,0.16)',
    region: 'rgba(18,16,14,0.42)', label: '#12100e', labelHalo: '#efe9df', minorLabel: '#5a5247',
  },
};

// Edad de la detección → color (rampa secuencial ámbar: lo más reciente es lo más intenso).
export const AGE_BINS = [
  { maxH: 1, color: '#ff4b1f', label: 'Hace menos de 1 h' },
  { maxH: 6, color: '#ff7a2e', label: '1 a 6 h' },
  { maxH: 24, color: '#ffa54a', label: '6 a 24 h' },
  { maxH: Infinity, color: '#ffd38f', label: 'Más de 1 día' },
];
const AGE_COLOR = ['step', ['get', 'age_h'], AGE_BINS[0].color, 1, AGE_BINS[1].color, 6, AGE_BINS[2].color, 24, AGE_BINS[3].color];
const CASE_AGE = ['step', ['get', 'age_h'], AGE_BINS[0].color, 1, AGE_BINS[1].color, 3, AGE_BINS[2].color];
// Borde del foco (MAPA-151): sobre el suelo claro los ámbar pálidos no llegan a 3:1 por sí
// solos, así que el contraste lo pone el borde — tinta oscura en tema claro, carbón en oscuro.
// Lo mide scripts/local/validate_palette.mjs contra el suelo de cada tema.
export const FOCO_STROKE = { dark: '#0d0c0b', light: '#17120e' };
// Apta para daltonismo (deuteranopía/protanopía), validada por scripts/local/validate_palette.mjs.
export const RISK_COLORS = { bajo: '#1a7f46', moderado: '#8f7a00', alto: '#c2571e', extremo: '#e50d06' };
// Anomalía de lluvia de la temporada: rampa seca (café) → húmeda (azul), distinguible de la de
// riesgo y apta para daltonismo (ΔE ≥ 12 entre niveles bajo deuteranopía/protanopía, criterio UX-13).
export const RAIN_COLORS = { muy_seco: '#93570a', seco: '#b08424', normal: '#7a7e72', humedo: '#2a837b', muy_humedo: '#1d6da8' };
// Niveles del peligro que llevan además una trama propia sobre el mapa (UX-20), en orden.
const RISK_TEX_LEVELS = ['bajo', 'moderado', 'alto', 'extremo'];
// Clase oficial de la alerta SENAPRED → color de la coropleta (OFI-207): los propios de
// SENAPRED (temprana preventiva en verde, amarilla y roja); «otra» es un aviso sin clase
// conocida, en neutro. SENAPRED_TEX mapea cada clase a una trama risk-pat-* ya dibujada,
// para que el tipo no dependa solo del color.
export const SENAPRED_COLORS = { roja: '#d4231a', amarilla: '#e8a317', temprana_preventiva: '#1a7f46', otra: '#8a8378' };
const SENAPRED_TEX = { roja: 'extremo', amarilla: 'alto', temprana_preventiva: 'bajo', otra: 'moderado' };
const SENAPRED_TIPOS = ['roja', 'amarilla', 'temprana_preventiva', 'otra'];
// Destellos GLM (rayos): cian, lejos del ámbar de los focos de calor y del violeta de los avisos.
export const LIGHTNING_COLOR = '#00b8d4';
// Reexportado para la leyenda del mapa; la carga del conjunto sigue siendo diferida.
export { SMOKE_COLOR, SMOKE_DENSITY_COLOR };

// Zoom desde el que se dibujan los límites comunales (`comunas-line`): la geometría
// solo se descarga si hay coropleta visible, comuna elegida o fondo sin conexión (PERF-10).
const COMUNAS_ZOOM_MIN = 6;
const COROPLETAS_COMUNAS = ['risk-fill', 'rain-fill', 'senapred-fill'];

// Exportada solo para las pruebas de atribución (MAPA-105); el flujo real entra por initMap.
export function baseStyle(theme, basemap) {
  const c = PALETTE[theme];
  const sources = {
    // La geometría comunal (1,9 MB) no viaja en el primer pintado: se pide con ensureComunas
    // cuando los límites comunales, la coropleta o una comuna elegida la necesitan (MAPA-143).
    comunas: { type: 'geojson', data: EMPTY, promoteId: 'code' },
    regiones: { type: 'geojson', data: '/web/data/regiones.geojson', promoteId: 'code' },
  };
  const layers = [{ id: 'background', type: 'background', paint: { 'background-color': basemap === 'mapa' ? c.land : c.ocean } }];
  if (basemap === 'mapa') {
    sources.omt = { type: 'vector', url: `${OFM}/planet`, attribution: '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' };
    layers.push(
      { id: 'offline-chile', type: 'fill', source: 'regiones', paint: { 'fill-color': c.chile } },
      // Los tintes de suelo (MAPA-195) no se evalúan a escala país (zoom<6): en cada
      // repintada del arranque eran 3 rellenos vectoriales extra sin aporte visible.
      { id: 'landcover-wood', type: 'fill', source: 'omt', 'source-layer': 'landcover', minzoom: 6, filter: ['==', ['get', 'class'], 'wood'], paint: { 'fill-color': c.wood, 'fill-opacity': 0.7 } },
      { id: 'landcover-grass', type: 'fill', source: 'omt', 'source-layer': 'landcover', minzoom: 6, filter: ['in', ['get', 'class'], ['literal', ['grass', 'farmland', 'scrub']]], paint: { 'fill-color': c.grass, 'fill-opacity': 0.5 } },
      { id: 'landuse-urban', type: 'fill', source: 'omt', 'source-layer': 'landuse', minzoom: 6, filter: ['in', ['get', 'class'], ['literal', ['residential', 'suburb', 'neighbourhood', 'commercial', 'industrial']]], paint: { 'fill-color': c.urban, 'fill-opacity': 0.8 } },
      { id: 'water', type: 'fill', source: 'omt', 'source-layer': 'water', paint: { 'fill-color': c.water } },
      { id: 'waterway', type: 'line', source: 'omt', 'source-layer': 'waterway', minzoom: 8, paint: { 'line-color': c.water, 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.5, 14, 2] } },
      { id: 'roads-minor', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 10, filter: ['in', ['get', 'class'], ['literal', ['minor', 'service', 'track', 'tertiary']]], paint: { 'line-color': c.road, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.4, 16, 3] } },
      { id: 'roads-major', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 5, filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary']]], paint: { 'line-color': c.roadMajor, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.5, 10, 1.6, 16, 6] } },
      { id: 'boundary-country', type: 'line', source: 'omt', 'source-layer': 'boundary', filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]], paint: { 'line-color': c.boundary, 'line-width': 1.2, 'line-dasharray': [3, 2] } },
    );
  } else {
    sources.raster = { type: 'raster', tiles: BASEMAPS[basemap].tiles, tileSize: 256, maxzoom: BASEMAPS[basemap].maxzoom, attribution: BASEMAPS[basemap].attribution };
    layers.push({ id: 'offline-chile', type: 'fill', source: 'regiones', paint: { 'fill-color': c.chile } });
    layers.push({ id: 'raster', type: 'raster', source: 'raster', paint: { 'raster-opacity': 1 } });
  }
  layers.push(
    { id: 'risk-fill', type: 'fill', source: 'comunas', layout: { visibility: 'none' },
      paint: { 'fill-color': ['match', ['coalesce', ['feature-state', 'level'], 'none'], 'bajo', RISK_COLORS.bajo, 'moderado', RISK_COLORS.moderado, 'alto', RISK_COLORS.alto, 'extremo', RISK_COLORS.extremo, 'rgba(0,0,0,0)'],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.72, ['boolean', ['feature-state', 'selected'], false], 0.75, 0.5] } },
    // Trama por nivel sobre risk-fill (UX-20): el peligro se distingue también en grises y con
    // daltonismo, sin tocar la paleta. fill-pattern no acepta feature-state en MapLibre (solo
    // zoom/feature) y los filtros lo prohíben: una capa por nivel con filtro por code, que ajusta
    // applyComunaState. Quedan sobre risk-fill, pero el hit-test es por capa: hover, click y cursor
    // siguen llegando a risk-fill, la capa de interacción.
    ...RISK_TEX_LEVELS.map((level) => ({
      id: `risk-tex-${level}`, type: 'fill', source: 'comunas',
      layout: { visibility: 'none' }, filter: ['==', ['get', 'code'], -1],
      paint: { 'fill-pattern': `risk-pat-${level}`, 'fill-opacity': 0.35 },
    })),
    { id: 'rain-fill', type: 'fill', source: 'comunas', layout: { visibility: 'none' },
      paint: { 'fill-color': ['match', ['coalesce', ['feature-state', 'rain'], 'none'], 'muy_seco', RAIN_COLORS.muy_seco, 'seco', RAIN_COLORS.seco, 'normal', RAIN_COLORS.normal, 'humedo', RAIN_COLORS.humedo, 'muy_humedo', RAIN_COLORS.muy_humedo, 'rgba(0,0,0,0)'],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.72, ['boolean', ['feature-state', 'selected'], false], 0.75, 0.5] } },
    // Alertas oficiales de SENAPRED por comuna (OFI-207): mismo mecanismo que risk-fill —
    // feature-state 'senapred' para el color y una capa de trama por clase, porque
    // fill-pattern no puede leer feature-state.
    { id: 'senapred-fill', type: 'fill', source: 'comunas', layout: { visibility: 'none' },
      paint: { 'fill-color': ['match', ['coalesce', ['feature-state', 'senapred'], 'none'], 'roja', SENAPRED_COLORS.roja, 'amarilla', SENAPRED_COLORS.amarilla, 'temprana_preventiva', SENAPRED_COLORS.temprana_preventiva, 'otra', SENAPRED_COLORS.otra, 'rgba(0,0,0,0)'],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.72, ['boolean', ['feature-state', 'selected'], false], 0.75, 0.5] } },
    ...SENAPRED_TIPOS.map((tipo) => ({
      id: `senapred-tex-${tipo}`, type: 'fill', source: 'comunas',
      layout: { visibility: 'none' }, filter: ['==', ['get', 'code'], -1],
      paint: { 'fill-pattern': `risk-pat-${SENAPRED_TEX[tipo]}`, 'fill-opacity': 0.35 },
    })),
    // Límites simplificados (~600 m): se desvanecen con zoom alto, donde el mapa base aporta el detalle.
    { id: 'comunas-line', type: 'line', source: 'comunas', minzoom: COMUNAS_ZOOM_MIN, maxzoom: 11, paint: { 'line-color': c.comuna, 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 10, 1], 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8.5, 1, 10.5, 0] } },
    { id: 'comuna-selected', type: 'line', source: 'comunas', filter: ['==', ['get', 'code'], -1], paint: { 'line-color': theme === 'dark' ? '#ffffff' : '#111111', 'line-width': 2.2 } },
    { id: 'regiones-line', type: 'line', source: 'regiones', maxzoom: 11.5, paint: { 'line-color': c.region, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 9, 1.6], 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8.5, 1, 11, 0] } },
  );
  if (basemap === 'mapa') {
    layers.push(
      { id: 'place-labels-minor', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 9, filter: ['in', ['get', 'class'], ['literal', ['village', 'suburb', 'hamlet']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:es'], ['get', 'name']], 'text-font': GLYPH_FONTS, 'text-size': 11 },
        paint: { 'text-color': c.minorLabel, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.4 } },
      { id: 'place-labels', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 4, filter: ['in', ['get', 'class'], ['literal', ['city', 'town']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:es'], ['get', 'name']], 'text-font': GLYPH_FONTS, 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 11, 10, 14] },
        paint: { 'text-color': c.label, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.6 } },
    );
  }
  return { version: 8, glyphs: `${OFM}/fonts/{fontstack}/{range}.pbf`, sources, layers };
}

// Trama por nivel, dibujada en canvas (sin dependencias): puntos, diagonal, cruzado y malla
// fina, de menos a más densa. La tinta sigue el tema; addImage no sobrevive a setStyle, así
// que las imágenes se registran de nuevo en cada style.load.
function riskPattern(theme, level) {
  const size = 16;
  const cv = document.createElement('canvas');
  cv.width = cv.height = size * 2;
  const ctx = cv.getContext('2d');
  ctx.scale(2, 2);
  ctx.strokeStyle = ctx.fillStyle = theme === 'dark' ? '#ece6dc' : '#12100e';
  ctx.lineWidth = 1.4;
  if (level === 'bajo') {
    for (const [x, y] of [[4, 4], [12, 4], [4, 12], [12, 12]]) { ctx.beginPath(); ctx.arc(x, y, 1.3, 0, Math.PI * 2); ctx.fill(); }
  } else {
    ctx.beginPath();
    for (let i = -size; i <= size; i += level === 'extremo' ? 4 : 8) {
      ctx.moveTo(i, 0); ctx.lineTo(i + size, size);
      if (level !== 'moderado') { ctx.moveTo(i, size); ctx.lineTo(i + size, 0); }
    }
    ctx.stroke();
  }
  // addImage no acepta HTMLCanvasElement en MapLibre 5: hay que entregar ImageData.
  return ctx.getImageData(0, 0, cv.width, cv.height);
}
function addRiskPatterns(m, theme) {
  for (const level of RISK_TEX_LEVELS) {
    const id = `risk-pat-${level}`;
    if (!m.hasImage(id)) m.addImage(id, riskPattern(theme, level), { pixelRatio: 2 });
  }
}

// Relieve sombreado opcional (MAPA-155): teselas DEM de Mapterhorn — sobre Chile son
// Copernicus DEM GLO-30 (~30 m, z0-12), «full, free and open» (INV-29,
// docs/investigacion/INV-29-relieve.md). La fuente se agrega al prender la capa, para que el
// arranque no pague el TileJSON ni las teselas.
const DEM_SOURCE = {
  type: 'raster-dem',
  tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'],
  encoding: 'terrarium',
  tileSize: 512,
  maxzoom: 12,
  attribution: '© <a href="https://mapterhorn.com/attribution" target="_blank" rel="noopener">Mapterhorn</a> · Copernicus DEM GLO-30',
};
// Respaldo y detalle fino en quebradas (z13-15, MAPA-189): AWS Terrain Tiles (USGS / Mapzen).
export const AWS_DEM_SOURCE = {
  type: 'raster-dem',
  tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
  encoding: 'terrarium',
  tileSize: 256,
  maxzoom: 15,
  attribution: '© <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">AWS Terrain Tiles</a> · USGS / Mapzen',
};

const TERRENO_EXAGGERATION = 1.3;
const TERRENO_AWS_ZOOM = 13;
let terreno3dActivo = false;
let demFallbackAws = false;
let terrenoDemActual = null; // 'mapterhorn' | 'aws' | null

/** Decide si conviene autoactivar el relieve 3D (p. ej. al abrir un enlace compartido):
 *  con ahorro de datos o movimiento reducido devuelve false. Función pura para pruebas. */
export function terreno3dPermitido({ saveData = false, reducedMotion = false } = {}) {
  return !saveData && !reducedMotion;
}

/** Fuente DEM actualmente aplicada al relieve 3D ('mapterhorn', 'aws' o null si está apagado). */
export function getTerrenoDemFuente() {
  return terreno3dActivo ? terrenoDemActual : null;
}

/** Indica si el respaldo AWS Terrain Tiles quedó activo tras un fallo de Mapterhorn. */
export function isDemFallbackAws() {
  return demFallbackAws;
}

function notificarCambioDem() {
  if (typeof document !== 'undefined') {
    document.dispatchEvent(new CustomEvent('brasa:terreno-dem-cambio', { detail: getTerrenoDemFuente() }));
  }
}

function ensureDemSource(id) {
  if (!map) return;
  if (id === 'terrain-dem-aws') {
    if (!map.getSource('terrain-dem-aws')) map.addSource('terrain-dem-aws', AWS_DEM_SOURCE);
  } else if (!map.getSource('hillshade-dem')) {
    map.addSource('hillshade-dem', DEM_SOURCE);
  }
}

// Opacidad unificada para capas raster de contexto (NASA GIBS, WMS externas y relieve, UX-82):
// no toca la capa base satelital/topográfica (`raster`).
const RASTER_OPACITY_MIN = 0.15;
let rasterOpacity = 0.75;
const relieveExaggeration = () => Math.min(1, Math.max(0.05, Number((0.6 * rasterOpacity).toFixed(3))));

export function getRasterOpacity() { return rasterOpacity; }

/** Ajusta la opacidad de las capas raster de contexto (GIBS, WMS y relieve) entre 0,15 y 1,
 *  sin tocar la capa base satélite/topográfico. Se conserva tras `style.load`. */
export function setRasterOpacity(valor) {
  const n = Number(valor);
  if (!Number.isFinite(n)) return rasterOpacity;
  rasterOpacity = Math.min(1, Math.max(RASTER_OPACITY_MIN, n));
  for (const key of Object.keys(GIBS)) {
    if (gibsState[key]) gibsState[key].opacity = rasterOpacity;
    const lid = `gibs-${key}-raster`;
    if (getLayerSafe(lid)) map.setPaintProperty(lid, 'raster-opacity', rasterOpacity);
  }
  for (const key of Object.keys(WMS_LAYERS)) {
    if (wmsState[key]) wmsState[key].opacity = rasterOpacity;
    const lid = `wms-${key}-raster`;
    if (getLayerSafe(lid)) map.setPaintProperty(lid, 'raster-opacity', rasterOpacity);
  }
  if (getLayerSafe('gibs-caso-raster')) map.setPaintProperty('gibs-caso-raster', 'raster-opacity', rasterOpacity);
  if (getLayerSafe('relieve-hillshade')) map.setPaintProperty('relieve-hillshade', 'hillshade-exaggeration', relieveExaggeration());
  return rasterOpacity;
}

/** Agrega la fuente DEM y la capa hillshade si faltan: justo bajo `risk-fill`, es decir
 *  debajo de las coropletas comunales, de los límites y de todo lo puntual. */
function addRelieve() {
  if (!map) return;
  const demId = demFallbackAws ? 'terrain-dem-aws' : 'hillshade-dem';
  ensureDemSource(demId);
  const existing = map.getLayer('relieve-hillshade');
  if (existing && existing.source !== demId) map.removeLayer('relieve-hillshade');
  if (!map.getLayer('relieve-hillshade')) {
    map.addLayer({ id: 'relieve-hillshade', type: 'hillshade', source: demId,
      paint: { 'hillshade-exaggeration': relieveExaggeration() } }, map.getLayer('risk-fill') ? 'risk-fill' : undefined);
  } else {
    map.setPaintProperty('relieve-hillshade', 'hillshade-exaggeration', relieveExaggeration());
  }
}

function ensureRelieve() {
  if (!estiloListo()) return; // el estilo aún carga: style.load la re-agrega vía visibility
  addRelieve();
}

/** Prende o apaga el relieve sombreado; al prender crea la fuente DEM en diferido. */
export function setRelieve(visible) {
  if (visible) ensureRelieve();
  show('relieve-hillshade', visible);
}

function elegirDemTerreno() {
  const usarAws = demFallbackAws || (map ? map.getZoom() >= TERRENO_AWS_ZOOM : false);
  return usarAws ? { id: 'terrain-dem-aws', fuente: 'aws' } : { id: 'hillshade-dem', fuente: 'mapterhorn' };
}

function applyTerreno3d() {
  if (!map) return;
  if (!terreno3dActivo) {
    terrenoDemActual = null;
    if (typeof map.setTerrain === 'function') map.setTerrain(null);
    return;
  }
  const { id, fuente } = elegirDemTerreno();
  ensureDemSource(id);
  if (typeof map.setTerrain === 'function') {
    map.setTerrain({ source: id, exaggeration: TERRENO_EXAGGERATION });
  }
  const cambio = terrenoDemActual !== fuente;
  terrenoDemActual = fuente;
  if (cambio) notificarCambioDem();
}

function ensureTerreno3d() {
  if (!estiloListo()) return; // style.load lo reaplica al terminar de cargar
  applyTerreno3d();
}

/** Prende o apaga el terreno 3D nativo de MapLibre (MAPA-189) con inclinación de cámara. */
export function setTerreno3d(visible) {
  const next = Boolean(visible);
  const cambio = next !== terreno3dActivo;
  terreno3dActivo = next;
  visibility.terreno3d = next;
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (next) {
    ensureTerreno3d();
    if (map && map.getPitch() < 20) {
      if (reduced) map.jumpTo({ pitch: 52 });
      else map.easeTo({ pitch: 52, duration: 400 });
    }
  } else {
    // setTerrain(null) no debe quedar bloqueado por isStyleLoaded(): mientras haya
    // teselas DEM en vuelo, isStyleLoaded() devuelve false y el mapa quedaba atrapado
    // en modo terrain-drape degradando capas vectoriales (p. ej. huellas de calor).
    if (map && typeof map.setTerrain === 'function') {
      try { map.setTerrain(null); } catch { /* estilo aún sin inicializar */ }
    }
    terrenoDemActual = null;
    if (cambio && map && map.getPitch() > 0) {
      if (reduced) map.jumpTo({ pitch: 0 });
      else map.easeTo({ pitch: 0, duration: 300 });
    }
  }
  updateSummary();
}

// ---------------------------------------------------------------- capas satelitales NASA GIBS (MAPA-180)
// Raster WMTS encima del fondo (EOxCloudless 2016 queda intacto como base) y debajo de
// las coropletas y lo puntual. La fuente se crea en diferido al prender la capa, como el
// relieve; fecha y opacidad viven en el estado para recrearla tras cambiar de estilo o de día.
const gibsState = {}; // key de GIBS → { visible, time, opacity }
let gibsDia = 'ayer';

export function getGibsDia() { return gibsDia; }

/** Alterna las capas NASA GIBS diarias entre «hoy» y «ayer» (UTC) y refresca sus fuentes. */
export function setGibsDia(dia) {
  const next = dia === 'hoy' ? 'hoy' : 'ayer';
  const cambio = next !== gibsDia;
  gibsDia = next;
  for (const [key, def] of Object.entries(GIBS)) {
    if (def.tipo !== 'diaria') continue;
    const st = gibsState[key];
    if (!st) continue;
    const time = tiempoGibs(def, gibsDia);
    if (cambio || st.time !== time) {
      st.time = time;
      refreshGibsDate(key);
    }
  }
  return gibsDia;
}

// Agrega (o solo actualiza la opacidad de) la fuente y capa raster de una capa GIBS.
// Sin guarda de estilo: la llaman ensureGibs (interactivo, con guarda) y ensureGibsAll
// (style.load, donde isStyleLoaded() aún da false tras agregar las fuentes).
function addGibs(key) {
  const st = gibsState[key];
  const def = GIBS[key];
  if (!st || !def || !map) return;
  const sid = `gibs-${key}`;
  const lid = `gibs-${key}-raster`;
  const opacity = Number.isFinite(st.opacity) ? st.opacity : rasterOpacity;
  if (!map.getSource(sid)) map.addSource(sid, { type: 'raster', tiles: gibsTileUrl(def, st.time), tileSize: 256, maxzoom: def.maxzoom, attribution: GIBS_ATTRIBUTION });
  if (!map.getLayer(lid)) {
    map.addLayer({ id: lid, type: 'raster', source: sid, paint: { 'raster-opacity': opacity } }, 'risk-fill');
  } else {
    map.setPaintProperty(lid, 'raster-opacity', opacity);
  }
}

function ensureGibs(key) {
  if (!estiloListo()) return; // el estilo aún carga: style.load la re-agrega vía ensureGibsAll
  addGibs(key);
}

/** Recree la fuente de una capa GIBS con su fecha vigente (cambio «Hoy / Ayer»). */
export function refreshGibsDate(key) {
  const st = gibsState[key];
  if (!st) return;
  const sid = `gibs-${key}`;
  const lid = `gibs-${key}-raster`;
  if (getLayerSafe(lid)) map.removeLayer(lid);
  if (getSourceSafe(sid)) map.removeSource(sid);
  if (st.visible) ensureGibs(key);
  show(lid, st.visible);
}

/** Prende o apaga una capa GIBS del mapa en vivo; `opts` trae time/opacity parciales. */
export function setGibs(key, opts = {}) {
  const def = GIBS[key];
  if (!def) return;
  const prev = gibsState[key] || {};
  const time = opts.time ?? prev.time ?? tiempoGibs(def, gibsDia);
  const opacity = Number.isFinite(opts.opacity)
    ? Math.min(1, Math.max(0.05, opts.opacity))
    : (Number.isFinite(prev.opacity) ? prev.opacity : rasterOpacity);
  const visible = opts.visible !== undefined ? Boolean(opts.visible) : Boolean(prev.visible);
  gibsState[key] = { visible, time, opacity };
  if (visible) ensureGibs(key);
  show(`gibs-${key}-raster`, visible);
  updateSummary();
}

/** Opacidad de una capa GIBS (0–1), sin recrear la fuente. */
export function setGibsOpacity(key, opacity) {
  const st = gibsState[key];
  if (!st || !Number.isFinite(opacity)) return;
  st.opacity = Math.min(1, Math.max(0.05, opacity));
  const lid = `gibs-${key}-raster`;
  if (getLayerSafe(lid)) map.setPaintProperty(lid, 'raster-opacity', st.opacity);
}

/** Escena histórica de un caso (casos.js): una sola capa raster con la fecha del caso.
 *  `scene` = { key, date, def } de gibs.js; null la apaga. Sobrevive a setStyle:
 *  ensureGibsAll la repone desde gibsEscenaScene. */
let gibsEscena = null;
let gibsEscenaScene = null;

function addEscena() {
  const scene = gibsEscenaScene;
  if (!scene?.def || !map) return;
  const sid = 'gibs-caso';
  const lid = 'gibs-caso-raster';
  if (!map.getSource(sid)) map.addSource(sid, { type: 'raster', tiles: gibsTileUrl(scene.def, scene.date), tileSize: 256, maxzoom: scene.def.maxzoom, attribution: GIBS_ATTRIBUTION });
  if (!map.getLayer(lid)) {
    map.addLayer({ id: lid, type: 'raster', source: sid, paint: { 'raster-opacity': rasterOpacity } }, 'risk-fill');
    show(lid, true);
  } else {
    map.setPaintProperty(lid, 'raster-opacity', rasterOpacity);
  }
  gibsEscena = { sid, lid };
}

export function setGibsEscena(scene) {
  if (gibsEscena?.sid && getLayerSafe(gibsEscena.lid)) { show(gibsEscena.lid, false); map.removeLayer(gibsEscena.lid); }
  if (gibsEscena?.sid && getSourceSafe(gibsEscena.sid)) map.removeSource(gibsEscena.sid);
  gibsEscena = null;
  gibsEscenaScene = scene?.def ? scene : null;
  if (!gibsEscenaScene || !map?.isStyleLoaded()) return;
  addEscena();
  updateSummary();
}

function ensureGibsAll() {
  for (const key of Object.keys(gibsState)) if (gibsState[key].visible) addGibs(key);
  if (gibsEscenaScene) addEscena(); // la imagen del caso también sobrevive al cambio de fondo/tema
}

// ---------------------------------------------------------------- capas WMS abiertas (OFI-34 GWIS, MAPA-185 ESA WorldCover)
// Mismo patrón diferido que GIBS: se montan al encenderse debajo de `risk-fill`,
// sobreviven a `style.load` y obedecen al deslizador único `setRasterOpacity()`.
const wmsState = {}; // key de WMS_LAYERS → { visible, fecha, opacity }

function addWms(key) {
  const st = wmsState[key];
  const def = WMS_LAYERS[key];
  if (!st || !def || !map) return;
  const sid = `wms-${key}`;
  const lid = `wms-${key}-raster`;
  const opacity = Number.isFinite(st.opacity) ? st.opacity : rasterOpacity;
  if (!map.getSource(sid)) {
    map.addSource(sid, {
      type: 'raster',
      tiles: wmsTileUrl(def, st.fecha),
      tileSize: def.tileSize,
      maxzoom: def.maxzoom,
      attribution: def.attribution,
    });
  }
  if (!map.getLayer(lid)) {
    map.addLayer({ id: lid, type: 'raster', source: sid, paint: { 'raster-opacity': opacity } }, map.getLayer('risk-fill') ? 'risk-fill' : undefined);
  } else {
    map.setPaintProperty(lid, 'raster-opacity', opacity);
  }
}

function ensureWms(key) {
  if (!estiloListo()) return;
  addWms(key);
}

/** Prende o apaga una capa WMS externa (GWIS o ESA WorldCover); crea la fuente en diferido. */
export function setWmsLayer(key, opts = {}) {
  const def = WMS_LAYERS[key];
  if (!def) return;
  const prev = wmsState[key] || {};
  const fecha = def.requiereFecha ? (opts.fecha ?? prev.fecha ?? fechaGibs('hoy')) : null;
  const opacity = Number.isFinite(opts.opacity)
    ? Math.min(1, Math.max(RASTER_OPACITY_MIN, opts.opacity))
    : (Number.isFinite(prev.opacity) ? prev.opacity : rasterOpacity);
  const visible = opts.visible !== undefined ? Boolean(opts.visible) : Boolean(prev.visible);
  const cambioFecha = def.requiereFecha && prev.fecha && prev.fecha !== fecha;
  const cambio = prev.visible !== visible || prev.fecha !== fecha || prev.opacity !== opacity;
  wmsState[key] = { visible, fecha, opacity };
  const sid = `wms-${key}`;
  const lid = `wms-${key}-raster`;
  if (cambioFecha) {
    if (getLayerSafe(lid)) map.removeLayer(lid);
    if (getSourceSafe(sid)) map.removeSource(sid);
  }
  if (visible) ensureWms(key);
  show(lid, visible);
  if (cambio) updateSummary();
}

/** Fecha UTC consultada por una capa WMS con parámetro `TIME` (como `gwis_ranking`). */
export function getWmsFecha(key) {
  return wmsState[key]?.fecha || (WMS_LAYERS[key]?.requiereFecha ? fechaGibs('hoy') : null);
}

function ensureWmsAll() {
  for (const key of Object.keys(wmsState)) if (wmsState[key].visible) addWms(key);
}

// ---------------------------------------------------------------- zonas de interfaz urbano-forestal CONAF GEPRIF (MAPA-183)
// Teselas vectoriales ArcGIS (riesgo_interfaz_tiled): orden {z}/{y}/{x}, maxzoom 15 con
// overzoom limpio en MapLibre. Se crea en diferido solo al encender la capa y sobrevive a setStyle.
export const CONAF_WUI = {
  tiles: ['https://tiles.arcgis.com/tiles/A1ELWse9bRAi2JiV/arcgis/rest/services/riesgo_interfaz_tiled/VectorTileServer/tile/{z}/{y}/{x}.pbf'],
  minzoom: 2,
  maxzoom: 15,
  bounds: [-75.3457, -55.964, -66.5444, -17.5544],
  sourceLayer: 'union_result_3857',
  attribution: '<a href="https://deigeprif.com/" target="_blank" rel="noopener">CONAF · GEPRIF Zonas de Interfaz</a>',
  levels: [
    { key: 'bajo', symbol: 3, label: 'Bajo', color: '#86BABD', cls: 'sw-wui-bajo' },
    { key: 'medio', symbol: 4, label: 'Medio', color: '#F1FB7B', cls: 'sw-wui-medio' },
    { key: 'alto', symbol: 5, label: 'Alto', color: '#F7A248', cls: 'sw-wui-alto' },
    { key: 'muy_alto', symbol: 6, label: 'Muy alto', color: '#F0261C', cls: 'sw-wui-muy-alto' },
  ],
};

let wuiVisible = false;

function addWui() {
  if (!map) return;
  if (!map.getSource('conaf-wui')) {
    map.addSource('conaf-wui', {
      type: 'vector',
      tiles: CONAF_WUI.tiles,
      minzoom: CONAF_WUI.minzoom,
      maxzoom: CONAF_WUI.maxzoom,
      bounds: CONAF_WUI.bounds,
      attribution: CONAF_WUI.attribution,
    });
  }
  if (!map.getLayer('conaf-wui-fill')) {
    const beforeId = map.getLayer('comunas-line') ? 'comunas-line'
      : (map.getLayer('smoke-fill') ? 'smoke-fill' : undefined);
    map.addLayer({
      id: 'conaf-wui-fill',
      type: 'fill',
      source: 'conaf-wui',
      'source-layer': CONAF_WUI.sourceLayer,
      filter: ['in', ['get', '_symbol'], ['literal', [3, 4, 5, 6]]],
      paint: {
        'fill-color': ['match', ['get', '_symbol'], 3, '#86BABD', 4, '#F1FB7B', 5, '#F7A248', 6, '#F0261C', 'transparent'],
        'fill-opacity': 0.52,
      },
    }, beforeId);
  }
}

function ensureWui() {
  if (!estiloListo()) return; // style.load la agrega vía wuiVisible
  addWui();
}

/** Prende o apaga las zonas de interfaz urbano-forestal (WUI) de CONAF GEPRIF (MAPA-183); crea la fuente en diferido. */
export function setWui(visible) {
  const next = Boolean(visible);
  wuiVisible = next;
  if (next) ensureWui();
  show('conaf-wui-fill', next);
}

const EMPTY = { type: 'FeatureCollection', features: [] };
const OVERLAY_SOURCES = ['places', 'place-radius', 'place-lines', 'detections', 'goes-pixels', 'reports', 'services', 'explore', 'official',
  'incident-hulls', 'incident-rings', 'lightning', 'smoke', 'case-footprint', 'case-points', 'case-goes', 'case-final', 'case-event', 'case-perimeter', 'case-affected', 'pick', 'scars', 'snaspe', 'official-perimeter', 'seleccion', 'filtro-radio'];

// «zoom» solo puede ir en el interpolate de más afuera: anidado en un `case` o un `*`,
// MapLibre rechaza la capa entera y los focos no se dibujan. porZoom() lo deja arriba.
const potencia = ['sqrt', ['coalesce', ['get', 'frp_mw'], 0]];
const celda = ['interpolate', ['linear'], ['coalesce', ['get', 'count'], 1], 1, 9, 30, 14, 150, 21, 600, 28];
const porZoom = (f) => ['interpolate', ['linear'], ['zoom'],
  4, f(['+', 3, ['*', 0.1, potencia]]), 10, f(['+', 5.5, ['*', 0.3, potencia]])];
// Isoterma en reposo (latido dormido o movimiento reducido): «reciente» se lee igual.
const ISOTERMA_REPOSO = porZoom((r) => ['case', ['has', 'count'], ['+', 5, celda], ['*', 2.2, r]]);

// Exportada solo para la prueba de expresiones (tests/js/map.test.mjs).
export function addOverlays(map, theme) {
  const ring = theme === 'dark' ? '#0d0c0b' : '#ece6dc';
  for (const id of OVERLAY_SOURCES) if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: overlayData[id] || EMPTY });
  const add = (layer) => { if (!map.getLayer(layer.id)) map.addLayer(layer); };
  // Humo GOES-19 (DET-16 / DET-48): velo de aerosol bajo todo lo puntual; color y opacidad
  // suben con la densidad cualitativa de ABI-L2-AODF cuando hay espesor óptico diurno.
  const smokeColor = smokeFillColorExpr(theme);
  const smokeOpacity = smokeFillOpacityExpr();
  add({ id: 'smoke-fill', type: 'fill', source: 'smoke', layout: { visibility: 'none' },
    paint: { 'fill-color': smokeColor, 'fill-opacity': smokeOpacity } });
  // Borde difuminado: el humo no tiene orilla y el producto llega en píxeles.
  add({ id: 'smoke-edge', type: 'line', source: 'smoke', layout: { visibility: 'none', 'line-join': 'round' },
    paint: { 'line-color': smokeColor, 'line-opacity': smokeOpacity, 'line-blur': 10, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 6, 10, 22] } });
  // Áreas protegidas (SNASPE): relleno y borde bajo las cicatrices y todo lo puntual.
  add({ id: 'snaspe-fill', type: 'fill', source: 'snaspe', layout: { visibility: 'none' },
    paint: { 'fill-color': '#2b8a3e', 'fill-opacity': 0.16 } });
  add({ id: 'snaspe-line', type: 'line', source: 'snaspe', layout: { visibility: 'none' },
    paint: { 'line-color': '#2b8a3e', 'line-width': 1.5 } });
  // Cicatrices (AGUA-01, CONAF-HIST-10Y y UX-82): contorno discontinuo para históricas CONAF
  // y relleno más marcado sin trazo punteado para el calor satelital de los últimos 90 días.
  add({ id: 'scars-fill', type: 'fill', source: 'scars',
    paint: { 'fill-color': '#8a4b2a', 'fill-opacity': ['case', ['==', ['get', 'kind'], 'historica'], 0.14, 0.34] } });
  add({ id: 'scars-line', type: 'line', source: 'scars', filter: ['==', ['get', 'kind'], 'historica'],
    paint: { 'line-color': '#8a4b2a', 'line-width': 1.8, 'line-dasharray': [3, 2] } });
  add({ id: 'case-final', type: 'line', source: 'case-final', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2, 'line-dasharray': [2, 1.5] } });
  // Borde oficial CONAF: línea continua verde azulada, distinta del perímetro importado (línea discontinua neutra).
  add({ id: 'case-perimeter', type: 'line', source: 'case-perimeter', paint: { 'line-color': '#1b9e77', 'line-width': 2.4, 'line-opacity': 0.9 } });
  // MAPA-191: área quemada cartografiada por Copernicus EMS (fecha fija del producto), debajo de la huella térmica.
  add({ id: 'case-affected-fill', type: 'fill', source: 'case-affected', paint: { 'fill-color': '#3b5bdb', 'fill-opacity': 0.2 } });
  add({ id: 'case-affected-line', type: 'line', source: 'case-affected', paint: { 'line-color': '#3b5bdb', 'line-width': 1.6, 'line-opacity': 0.9 } });
  add({ id: 'case-footprint-fill', type: 'fill', source: 'case-footprint', paint: { 'fill-color': '#d9471f', 'fill-opacity': 0.28 } });
  add({ id: 'case-footprint-line', type: 'line', source: 'case-footprint', paint: { 'line-color': '#ff7a2e', 'line-width': 1.4 } });
  // Perímetro oficial de CONAF (OFI-17): neutro y a trazos, para no confundirlo con la huella satelital naranja.
  add({ id: 'official-perimeter-fill', type: 'fill', source: 'official-perimeter', paint: { 'fill-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'fill-opacity': 0.08 } });
  add({ id: 'official-perimeter-line', type: 'line', source: 'official-perimeter', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2.2, 'line-dasharray': [2.5, 1.8] } });
  add({ id: 'place-radius-fill', type: 'fill', source: 'place-radius', paint: { 'fill-color': '#3987e5', 'fill-opacity': 0.06 } });
  add({ id: 'place-radius-line', type: 'line', source: 'place-radius', paint: { 'line-color': '#3987e5', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
  // Círculo del filtro por distancia (VIS-03): la vista solo alimenta la fuente.
  add({ id: 'filtro-radio-fill', type: 'fill', source: 'filtro-radio', paint: { 'fill-color': '#3987e5', 'fill-opacity': 0.05 } });
  add({ id: 'filtro-radio-line', type: 'line', source: 'filtro-radio', paint: { 'line-color': '#3987e5', 'line-width': 1.8, 'line-dasharray': [3, 2] } });
  // Línea del lugar al foco confiable más cercano dentro de su radio de aviso (MAPA-153):
  // punteada, con la etiqueta «4,2 km · al noreste» en la mitad. Es ayuda visual, no aviso.
  add({ id: 'place-lines', type: 'line', source: 'place-lines',
    paint: { 'line-color': '#3987e5', 'line-width': 1.6, 'line-dasharray': [2, 2] } });
  add({ id: 'place-lines-label', type: 'symbol', source: 'place-lines',
    layout: { 'symbol-placement': 'line-center', 'text-field': ['get', 'label'], 'text-font': GLYPH_FONTS, 'text-size': 11 },
    paint: { 'text-color': theme === 'dark' ? '#ece6dc' : '#17120e', 'text-halo-color': theme === 'dark' ? '#100f0d' : '#efe9df', 'text-halo-width': 1.4 } });
  // Huella aproximada de cada incidente abierto (DET-10): relleno tenue y borde por estado,
  // con los colores ya usados para su severidad. Apagada por defecto y bajo los focos.
  const hullStatus = ['match', ['get', 'status'], 'confirmado', RISK_COLORS.extremo, 'reportado', RISK_COLORS.extremo,
    'posible', RISK_COLORS.alto, 'controlado', RISK_COLORS.moderado, 'anomalia', RISK_COLORS.moderado, RISK_COLORS.alto];
  add({ id: 'incident-hulls-fill', type: 'fill', source: 'incident-hulls', layout: { visibility: 'none' }, paint: { 'fill-color': hullStatus, 'fill-opacity': 0.15 } });
  // El contorno va con «Focos de calor» desde zoom 7 (MAPA-163): sin él, cada incidente
  // se veía como puntos sueltos. El relleno sigue pidiendo el interruptor «Huellas».
  add({ id: 'incident-hulls-line', type: 'line', source: 'incident-hulls', minzoom: CELL_ZOOM_MAX, layout: { visibility: 'none' }, paint: { 'line-color': hullStatus, 'line-width': 1.6 } });
  // Anillos GOES (~2–3 km), no perímetros: el centro vacío deja ver el terreno.
  // Bajo CELL_ZOOM_MAX se usan focos agrupados; de lejos baja la opacidad.
  add({ id: 'goes-pixels', type: 'fill', source: 'goes-pixels', minzoom: CELL_ZOOM_MAX, paint: { 'fill-color': AGE_COLOR, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], CELL_ZOOM_MAX, ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.2, 24, 0.08, 168, 0.045], 13, ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.65, 24, 0.26, 168, 0.14]] } });
  add({ id: 'goes-pixels-line', type: 'line', source: 'goes-pixels', minzoom: 8, paint: { 'line-color': AGE_COLOR, 'line-width': 1, 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.18, 13, 0.6] } });
  add({ id: 'case-goes', type: 'fill', source: 'case-goes', paint: { 'fill-color': CASE_AGE, 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.75, 3, 0.35, 12, 0.12] } });
  add({ id: 'case-goes-line', type: 'line', source: 'case-goes', paint: { 'line-color': CASE_AGE, 'line-width': 1, 'line-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.9, 3, 0.5, 12, 0.2] } });
  // Lo puntual es una brasa: núcleo con borde del color del suelo y, en los focos, un halo difuso.
  const dot = (id, source, color, radius, extra = {}) => add({
    id, type: 'circle', source, ...(extra.filter ? { filter: extra.filter } : {}),
    paint: { 'circle-color': color, 'circle-radius': radius, 'circle-stroke-color': extra.stroke || ring, 'circle-stroke-width': extra.strokeWidth ?? 1.2, ...(extra.paint || {}) },
  });
  const zoomSize = (a, b) => ['interpolate', ['linear'], ['zoom'], 4, a, 11, b];
  const fiable = ['==', ['get', 'reliable'], true];
  const suelto = ['!', ['has', 'count']];
  // Celdas de la vista general (MAPA-01): un punto por grupo, con su número.
  const detRadius = porZoom((r) => ['case', ['has', 'count'], celda, r]);
  // Resplandor: más ancho con la potencia, más tenue con las horas.
  dot('detections-glow', 'detections', AGE_COLOR, porZoom((r) => ['case', ['has', 'count'], ['*', 1.7, celda], ['*', 3.2, r]]), { strokeWidth: 0,
    filter: fiable, paint: { 'circle-blur': 1, 'circle-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.55, 6, 0.3, 24, 0.12] } });
  // Latido: isoterma en los confiables de menos de 3 h (dos en los de menos de 1 h); engruesa con la potencia.
  const isoterma = (id, horas, opacidad) => dot(id, 'detections', 'rgba(0,0,0,0)', ISOTERMA_REPOSO, { stroke: AGE_COLOR,
    strokeWidth: ['interpolate', ['linear'], potencia, 0, 1.4, 14, 3],
    filter: ['all', fiable, ['<', ['get', 'age_h'], horas]], paint: { 'circle-stroke-opacity': opacidad,
      // Sin transición: el latido ya anima por JS (pulse); con la transición por defecto
      // (300 ms) MapLibre repintaría cada frame entre cambios y anularía la cadencia (MAPA-193).
      'circle-radius-transition': { duration: 0 }, 'circle-stroke-opacity-transition': { duration: 0 } } });
  isoterma('detections-pulse', 3, 0.5);
  isoterma('detections-pulse2', 1, 0);
  dot('explore', 'explore', '#ffb000', zoomSize(2.4, 5));
  dot('detections', 'detections', AGE_COLOR, detRadius, { stroke: FOCO_STROKE[theme], strokeWidth: 1.4,
    paint: { 'circle-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.45], 'circle-stroke-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.4] } });
  // Centro incandescente: lo recién visto arde en claro y se apaga en seis horas.
  dot('detections-hot', 'detections', '#fff1c9', porZoom((r) => ['*', 0.42, r]), { strokeWidth: 0,
    filter: ['all', fiable, suelto, ['<', ['get', 'age_h'], 6]], paint: { 'circle-blur': 0.35, 'circle-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.95, 1, 0.6, 6, 0] } });
  add({ id: 'detections-count', type: 'symbol', source: 'detections', filter: ['>', ['coalesce', ['get', 'count'], 0], 1],
    layout: { 'text-field': ['to-string', ['get', 'count']], 'text-font': GLYPH_FONTS, 'text-size': 11, 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#17120e' } });
  // Anillo por incidente abierto a escala país (MAPA-152): solo bajo CELL_ZOOM_MAX, donde
  // los focos ya se agrupan en celdas. Color = estado (la escala de las huellas), radio
  // proporcional a sus detecciones; las anomalías no son incendios y no llevan anillo.
  add({ id: 'incident-rings', type: 'circle', source: 'incident-rings', maxzoom: CELL_ZOOM_MAX,
    filter: ['in', ['get', 'status'], ['literal', ['posible', 'reportado', 'confirmado', 'controlado']]],
    paint: { 'circle-color': 'rgba(0,0,0,0)',
      'circle-radius': ['interpolate', ['linear'], ['min', ['coalesce', ['get', 'n'], 1], 300], 1, 7, 10, 11, 50, 16, 300, 24],
      'circle-stroke-color': hullStatus, 'circle-stroke-width': 2.4, 'circle-stroke-opacity': 0.95 } });
  dot('case-points', 'case-points', CASE_AGE, zoomSize(2.4, 5));
  dot('reports', 'reports', '#6250d6', 6, { stroke: '#ffffff', strokeWidth: 2 });
  dot('lightning', 'lightning', LIGHTNING_COLOR, zoomSize(2.2, 4.2), { stroke: '#ffffff', strokeWidth: 1 });
  // Incendio informado por CONAF: anillo grueso (oficial), distinto del punto de calor satelital.
  // A escala de país va hueco: debajo queda la celda de focos y su número se tiene que leer.
  dot('official', 'official', ['step', ['zoom'], 'rgba(0,0,0,0)', CELL_ZOOM_MAX, ring], ['match', ['get', 'status'], 'extinguido', 4.5, 7], {
    stroke: ['match', ['get', 'status'], 'confirmado', '#d4231a', 'controlado', '#e8a317', '#8a8378'], strokeWidth: 3.2 });
  dot('services', 'services', ['match', ['get', 'kind'], 'assembly_point', '#0ca30c', 'hospital', '#e34948', 'clinic', '#e87ba4', 'fire_station', '#eb6834', '#3987e5'], 6, { stroke: '#ffffff', strokeWidth: 1.5 });
  dot('places-halo', 'places', '#3987e5', 16, { strokeWidth: 0, paint: { 'circle-opacity': 0.18, 'circle-blur': 0.6 } });
  dot('places', 'places', '#3987e5', 7, { stroke: '#ffffff', strokeWidth: 2.5 });
  dot('case-event', 'case-event', 'rgba(0,0,0,0)', 16, { stroke: theme === 'dark' ? '#ffffff' : '#12100e', strokeWidth: 2.5 });
  dot('pick', 'pick', '#3987e5', 8, { stroke: '#ffffff', strokeWidth: 2.5 });
  // Etiquetas de incendios (MAPA-163): desde zoom 8 el estado y la comuna de cada
  // incidente abierto y el nombre de cada incendio de CONAF. Sin «hace X»: la etiqueta
  // no se refresca sola. La colisión la decide MapLibre (no se fuerza superposición).
  const labelInk = theme === 'dark' ? '#ece6dc' : '#17120e';
  const labelHalo = theme === 'dark' ? '#100f0d' : '#efe9df';
  add({ id: 'incident-labels', type: 'symbol', source: 'incident-rings', minzoom: 8,
    layout: { 'text-field': ['get', 'label'], 'text-font': GLYPH_FONTS, 'text-size': 12, 'text-variable-anchor': ['top', 'bottom', 'left', 'right', 'top-left', 'top-right', 'bottom-left', 'bottom-right'], 'text-radial-offset': 1.1, 'text-max-width': 9 },
    paint: { 'text-color': labelInk, 'text-halo-color': labelHalo, 'text-halo-width': 1.4 } });
  add({ id: 'official-labels', type: 'symbol', source: 'official', minzoom: 8,
    layout: { 'text-field': ['get', 'label'], 'text-font': GLYPH_FONTS, 'text-size': 12, 'text-variable-anchor': ['top', 'bottom', 'left', 'right', 'top-left', 'top-right', 'bottom-left', 'bottom-right'], 'text-radial-offset': 1.1, 'text-max-width': 9 },
    paint: { 'text-color': labelInk, 'text-halo-color': labelHalo, 'text-halo-width': 1.4 } });
  // Anillo de selección (MAPA-158): marca el punto cuya ficha está abierta. Va último
  // para quedar encima de todo; solo el borde, sin relleno — blanco en oscuro, tinta en claro.
  dot('seleccion', 'seleccion', 'rgba(0,0,0,0)', 13, { stroke: theme === 'dark' ? '#ffffff' : '#17120e', strokeWidth: 2.4 });
}

// Capas que siguen la visibilidad de otra (halo y latido de los focos, halo de los lugares,
// tramas del nivel de peligro, que acompañan siempre a risk-fill).
const LINKED = { 'smoke-fill': ['smoke-edge'], 'snaspe-fill': ['snaspe-line'], detections: ['detections-glow', 'detections-pulse', 'detections-pulse2', 'detections-hot', 'detections-count', 'incident-rings', 'incident-hulls-line', 'incident-labels'], official: ['official-labels'], 'goes-pixels': ['goes-pixels-line'], 'case-goes': ['case-goes-line'], places: ['places-halo', 'place-lines', 'place-lines-label'], 'risk-fill': RISK_TEX_LEVELS.map((l) => `risk-tex-${l}`), 'senapred-fill': SENAPRED_TIPOS.map((t) => `senapred-tex-${t}`) };

/** Latido de los focos confiables de menos de 3 h: una isoterma que se abre y se apaga cada 2,2 s
 *  (dos, a contratiempo, en los de menos de 1 h). */
// Ventana de reposo: sin datos nuevos ni interacción durante este tiempo, el ciclo duerme.
export const LATIDO_REPOSO_MS = 10_000;
let pulseFrame = 0; let lastPulse = 0;
let ultimoDatoFocos = 0; let ultimoToque = 0;

/** Decide si el latido debe seguir pidiendo frames (pura, testeable en Node): capa a la vista,
 *  al menos un foco de menos de 3 h, movimiento no reducido ni modo ahorro (UX-76) y actividad
 *  reciente — dato nuevo (`ultimoCambio`) o interacción (`quietoDesde`: el instante desde el
 *  que el mapa quedó quieto) dentro de la ventana de reposo. */
export function latidoVigente({ visible, focosRecientes, ahora, ultimoCambio, quietoDesde, movimientoReducido = false, ahorro = false }) {
  if (ahorro || movimientoReducido || !visible || !focosRecientes) return false;
  const activo = (ts) => Number.isFinite(ts) && ahora - ts <= LATIDO_REPOSO_MS;
  return activo(ultimoCambio) || activo(quietoDesde);
}

/** Cadencia del repintado del latido (MAPA-193): el latido es ambiente (período de 2,2 s),
 *  así que en pantallas táctiles —donde cada repintado del mapa es una tarea larga costosa
 *  en gama media— baja a ~10 fps; con ratón se mantiene fluido a ~30 fps. */
export function cadenciaLatidoMs(coarse) { return coarse ? 100 : 33; }

// El anillo solo se pinta en focos confiables de menos de 3 h (filtro de la capa): sin esos,
// animar sería repintar por nada.
const hayFocoReciente = () => (overlayData.detections?.features || [])
  .some((f) => f.properties?.reliable === true && f.properties?.age_h < 3);

function pulse(now) {
  pulseFrame = 0;
  if (!getLayerSafe('detections-pulse')) return;
  // Con la pestaña oculta el navegador ya pausa los rAF: se deja un frame pendiente para retomar al volver.
  if (document.hidden) { pulseFrame = requestAnimationFrame(pulse); return; }
  if (!latidoVigente({
    visible: map.getLayoutProperty('detections-pulse', 'visibility') !== 'none',
    focosRecientes: hayFocoReciente(),
    ahora: now,
    ultimoCambio: ultimoDatoFocos,
    quietoDesde: ultimoToque,
    movimientoReducido: matchMedia('(prefers-reduced-motion: reduce)').matches,
    ahorro: Boolean(store.get('ahorro')),
  })) {
    // Dormido de verdad: lo despiertan setData('detections'), moveend, style.load, tocar el lienzo y soltar el modo ahorro.
    map.setPaintProperty('detections-pulse', 'circle-radius', ISOTERMA_REPOSO);
    map.setPaintProperty('detections-pulse', 'circle-stroke-opacity', 0.5);
    map.setPaintProperty('detections-pulse2', 'circle-stroke-opacity', 0);
    return;
  }
  pulseFrame = requestAnimationFrame(pulse);
  if (now - lastPulse < cadenciaLatidoMs(matchMedia('(pointer: coarse)').matches)) return;
  lastPulse = now;
  const z = map.getZoom();
  // A escala país el anillo sale de una celda (más ancha); al acercarse, de cada foco.
  const near = Math.max(0, Math.min(1, (z - 5) / 5));
  const [desde, hasta] = z < CELL_ZOOM_MAX ? [10, 34] : [4, 12 + 18 * near];
  ['detections-pulse', 'detections-pulse2'].forEach((id, i) => {
    const t = ((now / 2200) + i * 0.5) % 1;
    map.setPaintProperty(id, 'circle-radius', desde + (1 - (1 - t) ** 3) * (hasta - desde));
    map.setPaintProperty(id, 'circle-stroke-opacity', (0.55 + 0.3 * near) * (1 - t) ** 1.5);
  });
}
function startPulse() {
  if (pulseFrame || matchMedia('(prefers-reduced-motion: reduce)').matches || store.get('ahorro')) return;
  pulseFrame = requestAnimationFrame(pulse);
}

// UX-76 parte 2: con `ahorro` el latido se apaga como con prefers-reduced-motion (el frame
// en curso se evalúa y duerme solo); al soltarlo despierta sin esperar la próxima interacción.
store.on('ahorro', (on) => { if (!on && map) startPulse(); });

const overlayData = {};
// Safari puede montar la vista antes de style.load: MapLibre lanza si se toca una capa/fuente sin estilo.
function getLayerSafe(id) { try { return map?.getLayer(id) || null; } catch { return null; } }
function getSourceSafe(id) { try { return map?.getSource(id) || null; } catch { return null; } }
let map = null;
// MapLibre `isStyleLoaded()` vuelve a false mientras descarga cualquier tesela (DEM, WMS, WUI):
// `estiloCargado` distingue «el estilo ya cargó» de «hay teselas en vuelo» y se reinicia en setStyle.
let estiloCargado = false;
function estiloListo() { return Boolean(map && (estiloCargado || map.isStyleLoaded?.())); }
let currentBasemap = 'mapa';
let riskState = null;
let rainState = null;
let senapredState = null;
let selectedComuna = null;
let hoveredComuna = null;
const readyCallbacks = [];

export function getMap() { return map; }
export function onReady(fn) { if (map?.isStyleLoaded() && getSourceSafe('detections')) fn(map); else readyCallbacks.push(fn); }

/* Toque sobre el mapa (MAPA-157): las vistas anuncian qué capa abre qué ficha con
 * registrarToque(capa, abrir) y un único map.on('click') reparte cada toque al
 * candidato de más prioridad (PRIORIDAD_TOQUE) y, a empate, al más cercano al
 * dedo — un toque, un solo resultado. La mano del escritorio solo sale sobre
 * capas registradas: ya no hay una lista fija en initMap. */
const toques = new Map();

export function registrarToque(capa, abrir) {
  toques.set(capa, abrir);
  const mano = () => { if (map) map.getCanvas().style.cursor = 'pointer'; };
  const fuera = () => { if (map) map.getCanvas().style.cursor = ''; };
  map?.on('mouseenter', capa, mano);
  map?.on('mouseleave', capa, fuera);
  return () => {
    if (toques.get(capa) === abrir) toques.delete(capa);
    map?.off('mouseenter', capa, mano);
    map?.off('mouseleave', capa, fuera);
  };
}

/** Un toque repartido entre las capas registradas: con dedo el objetivo admite
 *  12 px de margen (con mouse, 4). Un punto cuenta su distancia al toque; un
 *  polígono tocado siempre va con 0. Sin candidatos, avisa `brasa:toque-vacio`.
 *  Mientras `pickOnMap` espera su punto (body.picking) el resolutor no actúa. */
function resolverToque(e) {
  if (document.body.classList.contains('picking')) return;
  const capas = [...toques.keys()].filter((id) => getLayerSafe(id));
  const r = matchMedia('(pointer: coarse)').matches ? 12 : 4;
  const { x, y } = e.point;
  const box = [[x - r, y - r], [x + r, y + r]];
  const candidatos = (capas.length ? map.queryRenderedFeatures(box, { layers: capas }) : []).map((feature) => {
    let distPx = 0;
    if (feature.geometry?.type === 'Point') {
      const p = map.project(feature.geometry.coordinates);
      distPx = Math.hypot(p.x - x, p.y - y);
    }
    return { capa: feature.layer.id, feature, distPx };
  });
  const objetivo = elegirObjetivo(candidatos);
  if (!objetivo) { document.dispatchEvent(new CustomEvent('brasa:toque-vacio')); return; }
  toques.get(objetivo.capa)?.(objetivo.feature, e.lngLat, e);
}

/* Textos de los controles de MapLibre en español (VIS-01): sin `locale` los
 * aria-label y title salen en inglés («Find my location», «Zoom in»). Las
 * claves son las del defaultLocale del maplibre-gl.js que el repo sirve. */
const MAP_LOCALE = {
  'AttributionControl.MapFeedback': 'Comentarios sobre el mapa',
  'AttributionControl.ToggleAttribution': 'Mostrar u ocultar la atribución',
  'FullscreenControl.Enter': 'Pantalla completa',
  'FullscreenControl.Exit': 'Salir de pantalla completa',
  'GeolocateControl.FindMyLocation': 'Encontrar mi ubicación',
  'GeolocateControl.LocationNotAvailable': 'Ubicación no disponible',
  'LogoControl.Title': 'Logotipo de MapLibre',
  'Map.Title': 'Mapa',
  'Marker.Title': 'Marcador del mapa',
  'NavigationControl.ResetBearing': 'Arrastra para girar el mapa; haz clic para volver al norte',
  'NavigationControl.ZoomIn': 'Acercar',
  'NavigationControl.ZoomOut': 'Alejar',
  'Popup.Close': 'Cerrar la ventana',
  'ScaleControl.Feet': 'pies',
  'ScaleControl.Kilometers': 'km',
  'ScaleControl.Meters': 'm',
  'ScaleControl.Miles': 'mi',
  'ScaleControl.NauticalMiles': 'mn',
  'TerrainControl.Disable': 'Desactivar el relieve',
  'TerrainControl.Enable': 'Activar el relieve',
};

// MAPA-194: en táctil el lienzo se pinta a pixelRatio 2 aunque el teléfono reporte más
// (gama media dpr≈3: cada repintado baja ~55 % de píxeles); con ratón no se fija la opción.
export function pixelRatioMapa(coarse, dpr) { return coarse ? Math.min(dpr || 1, 2) : undefined; }

export function initMap(container) {
  estiloCargado = false;
  const theme = store.get('theme');
  const coarse = matchMedia('(pointer: coarse)').matches;
  map = new maplibregl.Map({
    container, style: baseStyle(theme, currentBasemap), center: [-71.2, -35.4], zoom: 4.6, minZoom: 2.5, maxZoom: 17,
    locale: MAP_LOCALE, pixelRatio: pixelRatioMapa(coarse, globalThis.devicePixelRatio),
    // En escritorio `compact: false` deja el crédito expandido (MAPA-105), sin el botón «i».
    // En móvil (<= 899 px) la barra sobre el lienzo se oculta; los créditos y enlaces de
    // cada fondo están en «Capas», en «De dónde vienen los datos» y en `#/calidad`.
    attributionControl: { compact: false, customAttribution: 'Límites: BCN · Detecciones: NASA FIRMS, NOAA GOES' },
    hash: false, dragRotate: true, pitchWithRotate: true, cooperativeGestures: false,
  });
  // MAPA-159: con dedo ni rotación ni inclinación (dos dedos solo acercan y giran el
  // mapa siempre a 0°), y el +/− no se monta: en pantalla chica estorba y no hace falta.
  // Con puntero fino (mouse, teclado del e2e) el control va igual que siempre.
  if (coarse) {
    map.touchZoomRotate.disableRotation();
    map.touchPitch.disable();
  } else {
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  }
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
  const geolocate = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false, showAccuracyCircle: true });
  map.addControl(geolocate, 'top-right');
  // MZ-10: tras «Mi ubicación», la pantalla «¿Hay fuego cerca de ti?» con lo que hay
  // alrededor (focos, CONAF, incidentes). Vive en cerca.js, pedido aquí (no suma al arranque).
  geolocate.on('geolocate', (e) => {
    import('./cerca.js')
      .then(({ abrirTrasGeolocate }) => abrirTrasGeolocate({ lat: e.coords.latitude, lon: e.coords.longitude }))
      .catch(() => {});
  });
  // «Actualizar» manual bajo «Mi ubicación»; módulo diferido por el tope de peso.
  import('./refresco.js').then((m) => m.montar(map)).catch(() => {});
  // El esqueleto sale con el primer cuadro del estilo propio: 'load' espera además las
  // teselas externas y con red lenta dejaba «Cargando el mapa…» sobre un mapa ya usable.
  map.once('style.load', () => map.once('render', () => {
    const skel = container.querySelector('#map-skel');
    skel?.classList.add('fuera');
    setTimeout(() => skel?.remove(), 600);
  }));
  map.on('style.load', () => {
    estiloCargado = true;
    comunasCargadasEnEstilo = false; // un estilo nuevo vacía la fuente comunal; comunasDatos sigue en memoria (PERF-10)
    addRiskPatterns(map, store.get('theme'));
    addOverlays(map, store.get('theme'));
    startPulse();
    applyComunaState();
    if (visibility['relieve-hillshade']) addRelieve();
    ensureGibsAll();
    ensureWmsAll();
    if (wuiVisible) addWui();
    if (terreno3dActivo) applyTerreno3d();
    applyLayerVisibility();
    refreshDetections();
    readyCallbacks.splice(0).forEach((fn) => fn(map));
  });
  // La agrupación por celda solo cambia al cruzar un zoom entero: el pan no redibuja nada.
  map.on('moveend', () => {
    ultimoToque = performance.now();
    startPulse();
    const band = Math.min(Math.floor(map.getZoom()), CELL_ZOOM_MAX);
    if (band !== densityBand) { densityBand = band; refreshDetections(); }
    if ((store.get('basemapOffline') && map.getZoom() >= COMUNAS_ZOOM_MIN)
      || (comunasNecesarias() && !comunasCargadasEnEstilo)) ensureComunas();
  });
  // MAPA-189: al acercarse a quebradas (z>=13), cambia a AWS Terrain Tiles (z13-15); al alejarse vuelve a GLO-30.
  map.on('zoomend', () => {
    if (!terreno3dActivo || demFallbackAws || !estiloListo()) return;
    const { fuente } = elegirDemTerreno();
    if (fuente !== terrenoDemActual) applyTerreno3d();
  });
  // Un toque o clic en el lienzo también cuenta como actividad y despierta el latido.
  map.getCanvas().addEventListener('pointerdown', () => { ultimoToque = performance.now(); startPulse(); });
  map.on('idle', updateSummary);
  map.on('error', (e) => {
    // Teselas o fuentes externas no disponibles: la base sin conexión (comunas BCN) sigue visible.
    if (e?.sourceId === 'omt' || e?.sourceId === 'raster') {
      store.set('basemapOffline', true);
      if (map.getZoom() >= COMUNAS_ZOOM_MIN) ensureComunas();
    }
    // MAPA-189: si Mapterhorn falla, conmuta limpiamente al respaldo AWS Terrain Tiles.
    const errUrl = String(e?.error?.url || e?.url || '');
    if (!demFallbackAws && (e?.sourceId === 'hillshade-dem' || errUrl.includes('tiles.mapterhorn.com'))) {
      demFallbackAws = true;
      if (visibility['relieve-hillshade'] && estiloListo()) {
        addRelieve();
        show('relieve-hillshade', true);
      }
      if (terreno3dActivo && estiloListo()) applyTerreno3d();
      notificarCambioDem();
    }
  });
  const hoverComuna = (e) => {
    const code = e.features?.[0]?.id;
    if (code === hoveredComuna) return;
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: false });
    hoveredComuna = code ?? null;
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: true });
  };
  const unhoverComuna = () => {
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: false });
    hoveredComuna = null;
  };
  for (const layer of ['risk-fill', 'rain-fill', 'senapred-fill']) {
    map.on('mousemove', layer, hoverComuna);
    map.on('mouseleave', layer, unhoverComuna);
  }
  // Un solo listener reparte todos los toques (MAPA-157); las capas que abren
  // algo se anuncian con registrarToque desde cada vista.
  map.on('click', resolverToque);
  actualizarPadding();
  return map;
}

export function setTheme(theme) {
  if (!map) return;
  estiloCargado = false;
  map.setStyle(baseStyle(theme, currentBasemap), { diff: false });
}

export function setBasemap(name) {
  currentBasemap = name;
  store.set('basemapOffline', false);
  if (map) {
    estiloCargado = false;
    map.setStyle(baseStyle(store.get('theme'), name), { diff: false });
  }
  updateSummary();
}
export const basemap = () => currentBasemap;

export function setData(source, data) {
  overlayData[source] = data;
  if (source === 'detections') { ultimoDatoFocos = performance.now(); refreshDetections(); startPulse(); return; }
  getSourceSafe(source)?.setData(data);
  updateSummary();
}

// Banda de zoom entera vigente; la agrupación por celda se recalcula solo al cambiar de banda.
let densityBand = -1;
/** Decimación de focos (MAPA-01): overlayData.detections guarda el dato crudo y la fuente
 *  recibe la vista agrupada por celda del zoom actual (intacta desde CELL_ZOOM_MAX). */
function refreshDetections() {
  const src = getSourceSafe('detections');
  if (!src) return;
  const raw = overlayData.detections || EMPTY;
  const t0 = performance.now();
  const view = decimatePoints(raw, Math.floor(map.getZoom()));
  const ms = performance.now() - t0;
  src.setData(view);
  lastAgrupados = view.features.length;
  updateSummary();
  // Medida de MAPA-01 en consola, solo con depuración activa: queryRenderedFeatures en
  // cada idle cuesta un readback de GPU por pan/zoom (PERF-10), inútil en producción.
  if (debugMapa()) {
    map.once('idle', () => {
      const drawn = ['detections', 'goes-pixels'].reduce((n, l) => n + (getLayerSafe(l) ? map.queryRenderedFeatures({ layers: [l] }).length : 0), 0);
      console.debug(`BRASA mapa: ${raw.features.length} focos → ${view.features.length} features (${drawn} en pantalla) · decimación ${ms.toFixed(1)} ms`);
    });
  }
}

/** Depuración del mapa (MAPA-192): `?debug=1` en la URL o `localStorage` «brasa:debug-mapa» = 1.
 *  Apagada por defecto: la medida de foco dibujado no paga readback de GPU en cada idle. */
export function debugMapa() {
  if (new URLSearchParams(globalThis.location?.search || '').get('debug') === '1') return true;
  try { return globalThis.localStorage?.getItem('brasa:debug-mapa') === '1'; } catch { return false; }
}

const visibility = {};
export function show(layerIds, visible) {
  const expanded = [].concat(layerIds).flatMap((x) => [x, ...(LINKED[x] || [])]);
  for (const id of expanded) {
    visibility[id] = visible;
    if (getLayerSafe(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }
  if (visible && expanded.some((id) => COROPLETAS_COMUNAS.includes(id))) {
    ensureComunas();
    applyComunaState();
  }
  startPulse(); // Si los focos vuelven a estar a la vista, el latido se re-evalúa en el próximo frame.
  updateSummary();
}
function applyLayerVisibility() {
  for (const [id, visible] of Object.entries(visibility)) if (getLayerSafe(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
}

// ---------------------------------------------------------------- resumen para lector de pantalla
// El lienzo WebGL se anuncia como «región» sin contenido: #map-summary (role=status) lo
// describe en texto. Orden igual al panel «Qué mostrar en el mapa»: id → nombre en claro.
const CAPA_NOMBRES = [
  ['detections', 'focos'],
  ['official', 'incendios'],
  ['risk-fill', 'peligro de incendio'],
  ['smoke-fill', 'humo'],
  ['rain-fill', 'lluvia'],
  ['senapred-fill', 'alertas de SENAPRED'],
  ['scars-fill', 'cicatrices'],
  ['snaspe-fill', 'áreas protegidas'],
  ['conaf-wui-fill', 'interfaz urbano-forestal'],
  ['reports', 'avisos de vecinos'],
  ['places', 'lugares'],
  ['incident-hulls-fill', 'huellas'],
  ['lightning', 'rayos'],
  ['viento', 'viento'],
  ['relieve-hillshade', 'relieve'],
  ['terreno3d', 'relieve 3D'],
  ['wms-worldcover-raster', 'uso de suelo'],
  ['wms-gwis_ranking-raster', 'peligro inusual GWIS'],
  ['wms-gwis_ba-raster', 'área quemada 30 días GWIS'],
  ['gibs-goes-raster', 'imagen GOES'],
  ['gibs-viirs-raster', 'imagen VIIRS'],
  ['gibs-aod-raster', 'aerosol'],
  ['gibs-caso-raster', 'imagen del caso'],
  ['services', 'servicios'],
  ['explore', 'exploración'],
];

const separadorMiles = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');

function haceTxt(ms) {
  const min = Math.max(0, Math.round(ms / 60000));
  if (min < 1) return 'recién';
  if (min < 60) return `hace ${min} ${min === 1 ? 'minuto' : 'minutos'}`;
  const h = Math.round(min / 60);
  if (h < 48) return `hace ${h} ${h === 1 ? 'hora' : 'horas'}`;
  const d = Math.round(h / 24);
  return `hace ${d} ${d === 1 ? 'día' : 'días'}`;
}

/** La frase que dice lo que el lienzo no puede anunciar: cuántos focos hay y en cuántos
 *  puntos agrupados, cuántos incendios de CONAF, qué capas están prendidas, el fondo
 *  activo, la señal y las capas en carga. `reciente` y `ahora` son marcas de tiempo (ms). */
export function resumenMapa({
  focos = [], agrupados = 0, incendios = 0, reportes = 0, capas = [],
  ahora = 0, reciente = null, fondo = '', sinConexion = false, cargando = [],
} = {}) {
  const partes = [];
  const n = focos.length;
  if (!n) {
    partes.push('sin focos de calor a la vista');
  } else {
    let s = n === 1 ? '1 foco de calor' : `${separadorMiles(n)} focos de calor`;
    if (agrupados > 0 && agrupados < n) s += ` en ${separadorMiles(agrupados)} ${agrupados === 1 ? 'punto agrupado' : 'puntos agrupados'}`;
    if (reciente !== null && ahora) s += `; el más reciente ${haceTxt(ahora - reciente)}`;
    partes.push(s);
  }
  partes.push(incendios ? `${separadorMiles(incendios)} ${incendios === 1 ? 'incendio informado' : 'incendios informados'} por CONAF` : 'Sin incendios informados por CONAF');
  if (reportes) partes.push(`${separadorMiles(reportes)} ${reportes === 1 ? 'reporte' : 'reportes'} de vecinos`);
  partes.push(`Capas: ${capas.length ? capas.join(', ') : 'ninguna'}`);
  const nombreFondo = typeof fondo === 'string' ? fondo.trim() : '';
  if (nombreFondo) partes.push(`Fondo: ${nombreFondo}${sinConexion ? ' (sin señal)' : ''}`);
  else if (sinConexion) partes.push('Mapa sin conexión');
  const enCarga = Array.isArray(cargando) ? cargando.filter(Boolean) : [];
  if (enCarga.length) partes.push(`Cargando: ${enCarga.join(', ')}`);
  return `Mapa: ${partes.join('. ')}.`;
}

// El texto se reescribe solo si cambió: un aria-live que repite lo mismo vuelve a anunciarlo.
let summaryText = '';
let lastAgrupados = 0;
let loadingLayers = [];

/** Informa al lector de pantalla qué capas diferidas se están cargando (UX-82). */
export function setMapLoadingLayers(nombres) {
  loadingLayers = Array.isArray(nombres) ? nombres.map((n) => String(n || '').trim()).filter(Boolean) : [];
  updateSummary();
}

function updateSummary() {
  if (typeof document === 'undefined') return;
  const el = document.getElementById('map-summary');
  if (!el) return;
  const features = overlayData.detections?.features || [];
  let minAge = Infinity;
  for (const f of features) {
    const age = f.properties?.age_h;
    if (Number.isFinite(age) && age < minAge) minAge = age;
  }
  const ahora = Date.now();
  const text = resumenMapa({
    focos: features,
    agrupados: lastAgrupados,
    incendios: overlayData.official?.features?.length || 0,
    reportes: overlayData.reports?.features?.length || 0,
    capas: CAPA_NOMBRES.filter(([id]) => visibility[id]).map(([, nombre]) => nombre),
    ahora,
    reciente: Number.isFinite(minAge) ? ahora - minAge * 3600000 : null,
    fondo: BASEMAPS[currentBasemap]?.label || '',
    sinConexion: Boolean(store.get('basemapOffline')),
    cargando: loadingLayers,
  });
  if (text !== summaryText) { summaryText = text; el.textContent = text; }
}
store.on('basemapOffline', updateSummary);

/** Pinta el índice de riesgo comunal (feature-state) y lo reaplica tras cambiar de estilo. */
export function setRisk(comunas) {
  riskState = comunas;
  applyComunaState();
}
/** Lo mismo para la anomalía de lluvia de la temporada (feature-state «rain»). */
export function setRain(rain) {
  rainState = rain;
  applyComunaState();
}
/** Y para la clase de alerta SENAPRED que nombra cada comuna (feature-state «senapred», OFI-207). */
export function setSenapred(tipos) {
  senapredState = tipos;
  applyComunaState();
}
// La geometría comunal (1,9 MB) se descarga una sola vez bajo demanda real y se
// conserva en memoria tras setStyle (MAPA-143 / PERF-10).
let comunasDatos = null;
let comunasPromesa = null;
let comunasCargadasEnEstilo = false;
function comunasNecesarias() {
  return Boolean(visibility['risk-fill'] || visibility['rain-fill'] || visibility['senapred-fill'])
    || (selectedComuna !== null && selectedComuna !== undefined)
    || Boolean(store.get('basemapOffline'));
}
function ensureComunas() {
  const source = getSourceSafe('comunas');
  if (comunasCargadasEnEstilo || !source) return;
  if (comunasDatos) {
    comunasCargadasEnEstilo = true;
    source.setData(comunasDatos);
    return;
  }
  comunasPromesa ??= fetch('/web/data/comunas.geojson')
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      comunasDatos = data;
      comunasPromesa = null;
      const src = getSourceSafe('comunas');
      if (src && !comunasCargadasEnEstilo && comunasNecesarias()) {
        comunasCargadasEnEstilo = true;
        src.setData(comunasDatos);
      }
      return comunasDatos;
    })
    .catch(() => {
      comunasPromesa = null;
      return null;
    });
}
function applyComunaState() {
  // Las coropletas (peligro, lluvia, alertas SENAPRED), una comuna elegida o el fondo
  // sin conexión piden los polígonos comunales; sin eso la fuente queda vacía (PERF-10).
  if (comunasNecesarias()) ensureComunas();
  if (!getSourceSafe('comunas')) return;
  map.removeFeatureState({ source: 'comunas' });
  if (riskState) for (const [code, r] of Object.entries(riskState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { level: r.level });
  if (rainState) for (const [code, r] of Object.entries(rainState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { rain: r.level });
  if (senapredState) for (const [code, t] of Object.entries(senapredState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { senapred: t });
  // Las tramas no pueden leer feature-state: cada capa risk-tex-*/senapred-tex-* pinta
  // solo las comunas de su nivel/clase.
  const texCodes = Object.fromEntries(RISK_TEX_LEVELS.map((l) => [l, []]));
  if (riskState) for (const [code, r] of Object.entries(riskState)) texCodes[r.level]?.push(Number(code));
  for (const level of RISK_TEX_LEVELS) {
    const id = `risk-tex-${level}`;
    if (getLayerSafe(id)) map.setFilter(id, ['in', ['get', 'code'], ['literal', texCodes[level]]]);
  }
  const senCodes = Object.fromEntries(SENAPRED_TIPOS.map((t) => [t, []]));
  if (senapredState) for (const [code, t] of Object.entries(senapredState)) senCodes[t]?.push(Number(code));
  for (const tipo of SENAPRED_TIPOS) {
    const id = `senapred-tex-${tipo}`;
    if (getLayerSafe(id)) map.setFilter(id, ['in', ['get', 'code'], ['literal', senCodes[tipo]]]);
  }
  if (selectedComuna !== null) selectComuna(selectedComuna);
}
export function selectComuna(code) {
  selectedComuna = code;
  if (code !== null && code !== undefined) ensureComunas();
  if (getLayerSafe('comuna-selected')) map.setFilter('comuna-selected', ['==', ['get', 'code'], code ?? -1]);
}

/** Márgenes de cámara: en el celular la hoja inferior (o la ficha abierta) tapa parte
 *  del mapa. `sheetPx` guarda la altura objetivo de la hoja (app.js la publica junto al
 *  estado), así el vuelo que sigue a bajarla ya no usa su altura anterior (MAPA-158). */
function viewPadding(base = 40) {
  if (window.innerWidth >= 900) return { top: base + 30, bottom: base, left: base, right: base + 30 };
  const tapado = Math.max(
    store.get('sheetPx') || document.querySelector('#panel')?.getBoundingClientRect().height || 0,
    store.get('fichaPx') || 0,
  );
  const visible = window.innerHeight - 64 - tapado;
  const bottom = Math.min(tapado + 12, window.innerHeight * 0.75);
  // Arriba, 112 px: la barra de arriba y la de controles del mapa terminan en 106.
  return visible < 160 ? { top: 70, bottom: 20, left: 16, right: 16 } : { top: 112, bottom, left: 16, right: 50 };
}

/** Acolchado real del lienzo bajo 900 px (MAPA-158): la hoja o la ficha tapan la franja
 *  inferior y el centro de cámara sube para que el punto elegido quede sobre ellas.
 *  Las alturas las publican app.js (`sheetPx`) y popup.js (`fichaPx`).
 *  `setPadding` cancela el vuelo en curso: con la cámara en movimiento espera al «moveend» (MAPA-168). */
function actualizarPadding() {
  if (!map) return;
  if (map.isMoving()) { map.once('moveend', actualizarPadding); return; }
  const bottom = window.innerWidth < 900 ? Math.max(store.get('sheetPx') || 0, store.get('fichaPx') || 0) : 0;
  map.setPadding({ top: 0, left: 0, right: 0, bottom });
}
store.on('sheetPx', actualizarPadding);
store.on('fichaPx', actualizarPadding);
export function fly(lon, lat, zoom = 11, opts = {}) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
  if (!map) { onReady(() => fly(lon, lat, zoom, opts)); return; }
  map.flyTo({ center: [lon, lat], zoom, speed: 1.4, curve: 1.5, essential: true, padding: viewPadding(20), ...opts });
}
export function fitBbox([w, s, e, n], padding = 40, maxZoom = 13) {
  if (!map) { onReady(() => fitBbox([w, s, e, n], padding, maxZoom)); return; }
  const p = viewPadding(padding);
  // Acolchado que excede el lienzo (hoja casi abierta) aborta el ajuste con «cannot fit within canvas».
  // clientHeight: píxeles CSS, la unidad del padding — canvas.height sería física (×devicePixelRatio).
  const h = map.getCanvas().clientHeight;
  // fitBounds suma su padding al acolchado fijo del lienzo (MAPA-158), que ya cuenta la hoja.
  const fijo = map.getPadding().bottom;
  p.bottom = Math.max(12, p.bottom - fijo);
  if (p.top + p.bottom + fijo > h - 80) p.bottom = Math.max(12, h - 80 - p.top - fijo);
  map.fitBounds([[w, s], [e, n]], { padding: p, duration: 1100, maxZoom });
}

// ---------------------------------------------------------------- constructores de GeoJSON
export function detectionsGeoJSON(points, now = Date.now()) {
  const dots = []; const blobs = [];
  for (const p of points) {
    const age = (now - Date.parse(p.observed_at)) / 3600000;
    // observed_at malformado → NaN → el estilo de MapLibre advierte «number expected, null»; 999 h lo pinta apagado, no fresco.
    // frp_mw puede venir null (ABI): las expresiones de potencia esperan número y reciben 0.
    const frp = Number(p.frp_mw);
    const props = { id: p.id, age_h: Number.isFinite(age) ? Math.max(0, age) : 999, frp_mw: Number.isFinite(frp) ? frp : 0, sensor: p.sensor, reliable: ['alta', 'nominal', 'media'].includes(p.confidence) };
    dots.push({ type: 'Feature', id: dots.length, geometry: { type: 'Point', coordinates: [p.lon, p.lat] }, properties: props });
    if (p.sensor === 'ABI') blobs.push({ type: 'Feature', geometry: heatBlob(p.lon, p.lat, pixelKm(p) / Math.sqrt(Math.PI), seedFrom(p.id), { hueco: 0.6 }), properties: props });
  }
  return { dots: { type: 'FeatureCollection', features: dots }, blobs: { type: 'FeatureCollection', features: blobs } };
}

export function placesGeoJSON(places) {
  return {
    points: { type: 'FeatureCollection', features: places.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lon, p.lat] }, properties: { id: p.id, name: p.name } })) },
    radius: { type: 'FeatureCollection', features: places.map((p) => ({ type: 'Feature', geometry: circlePolygon(p.lon, p.lat, p.radius_km), properties: { id: p.id } })) },
  };
}

export function pointsGeoJSON(items, propsFn = (i) => i) {
  return { type: 'FeatureCollection', features: items.map((i) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [i.lon, i.lat] }, properties: propsFn(i) })) };
}

export const EMPTY_FC = EMPTY;
