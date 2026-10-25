/* Mapa 2D (MapLibre): estilo propio claro/oscuro sobre OpenFreeMap (datos © OpenStreetMap
   contributors, ODbL; esquema OpenMapTiles, CC-BY), con base sin conexión de comunas reales.
   MAPA-105: solo capas base de licencia abierta y con su crédito siempre visible en el mapa
   (la atribución queda expandida, `compact: false`); la satelital es EOxCloudless 2016 de
   EOX (CC BY 4.0) — ver docs/FUENTES.md «Mapas base». */
import { CELL_ZOOM_MAX, decimatePoints } from './capas.js';
import { store } from './store.js';
import { circlePolygon, pixelKm, pixelSquare } from './util.js';
import { SMOKE_COLOR, SMOKE_OPACITY } from './smoke.js';

const OFM = 'https://tiles.openfreemap.org';
export const BASEMAPS = {
  mapa: { label: 'Mapa' },
  satelite: {
    label: 'Satélite',
    tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2016_3857/default/g/{z}/{y}/{x}.jpg'],
    attribution: 'EOxCloudless 2016 – <a href="https://cloudless.eox.at" target="_blank" rel="noopener">https://cloudless.eox.at</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016, CC BY 4.0)',
    maxzoom: 14,
  },
  topo: {
    label: 'Relieve',
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
// Destellos GLM (rayos): cian, lejos del ámbar de los focos de calor y del violeta de los avisos.
export const LIGHTNING_COLOR = '#00b8d4';
// Reexportado para la leyenda del mapa; la carga del conjunto sigue siendo diferida.
export { SMOKE_COLOR };

// Zoom desde el que se dibujan los límites comunales (`comunas-line`): hasta ahí nadie
// necesita la geometría comunal completa.
const COMUNAS_ZOOM_MIN = 6;

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
      { id: 'landcover-wood', type: 'fill', source: 'omt', 'source-layer': 'landcover', filter: ['==', ['get', 'class'], 'wood'], paint: { 'fill-color': c.wood, 'fill-opacity': 0.7 } },
      { id: 'landcover-grass', type: 'fill', source: 'omt', 'source-layer': 'landcover', filter: ['in', ['get', 'class'], ['literal', ['grass', 'farmland', 'scrub']]], paint: { 'fill-color': c.grass, 'fill-opacity': 0.5 } },
      { id: 'landuse-urban', type: 'fill', source: 'omt', 'source-layer': 'landuse', filter: ['in', ['get', 'class'], ['literal', ['residential', 'suburb', 'neighbourhood', 'commercial', 'industrial']]], paint: { 'fill-color': c.urban, 'fill-opacity': 0.8 } },
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
    // Trama por nivel sobre risk-fill (UX-20): el peligro se distingue también en grises y
    // con daltonismo, sin tocar la paleta. fill-pattern no acepta feature-state en MapLibre
    // (solo zoom/feature) y los filtros prohíben feature-state, así que hay una capa por
    // nivel con filtro por code; la lista de códigos la ajusta applyComunaState. Quedan por
    // encima de risk-fill, pero el hit-test de MapLibre es por capa: hover, click y cursor
    // siguen llegando a risk-fill, que se mantiene como la capa de interacción.
    ...RISK_TEX_LEVELS.map((level) => ({
      id: `risk-tex-${level}`, type: 'fill', source: 'comunas',
      layout: { visibility: 'none' }, filter: ['==', ['get', 'code'], -1],
      paint: { 'fill-pattern': `risk-pat-${level}`, 'fill-opacity': 0.35 },
    })),
    { id: 'rain-fill', type: 'fill', source: 'comunas', layout: { visibility: 'none' },
      paint: { 'fill-color': ['match', ['coalesce', ['feature-state', 'rain'], 'none'], 'muy_seco', RAIN_COLORS.muy_seco, 'seco', RAIN_COLORS.seco, 'normal', RAIN_COLORS.normal, 'humedo', RAIN_COLORS.humedo, 'muy_humedo', RAIN_COLORS.muy_humedo, 'rgba(0,0,0,0)'],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.72, ['boolean', ['feature-state', 'selected'], false], 0.75, 0.5] } },
    // Límites simplificados (~600 m): se desvanecen con zoom alto, donde el mapa base aporta el detalle.
    { id: 'comunas-line', type: 'line', source: 'comunas', minzoom: COMUNAS_ZOOM_MIN, maxzoom: 11, paint: { 'line-color': c.comuna, 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 10, 1], 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8.5, 1, 10.5, 0] } },
    { id: 'comuna-selected', type: 'line', source: 'comunas', filter: ['==', ['get', 'code'], -1], paint: { 'line-color': theme === 'dark' ? '#ffffff' : '#111111', 'line-width': 2.2 } },
    { id: 'regiones-line', type: 'line', source: 'regiones', maxzoom: 11.5, paint: { 'line-color': c.region, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 9, 1.6], 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8.5, 1, 11, 0] } },
  );
  if (basemap === 'mapa') {
    layers.push(
      { id: 'place-labels-minor', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 9, filter: ['in', ['get', 'class'], ['literal', ['village', 'suburb', 'hamlet']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:es'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': 11 },
        paint: { 'text-color': c.minorLabel, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.4 } },
      { id: 'place-labels', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 4, filter: ['in', ['get', 'class'], ['literal', ['city', 'town']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:es'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 11, 10, 14] },
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

const EMPTY = { type: 'FeatureCollection', features: [] };
const OVERLAY_SOURCES = ['places', 'place-radius', 'place-lines', 'detections', 'goes-pixels', 'reports', 'services', 'explore', 'official',
  'incident-hulls', 'incident-rings', 'lightning', 'smoke', 'case-footprint', 'case-points', 'case-goes', 'case-final', 'case-event', 'case-perimeter', 'pick', 'scars', 'official-perimeter'];

function addOverlays(map, theme) {
  const ring = theme === 'dark' ? '#0d0c0b' : '#ece6dc';
  for (const id of OVERLAY_SOURCES) if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: overlayData[id] || EMPTY });
  const add = (layer) => { if (!map.getLayer(layer.id)) map.addLayer(layer); };
  // Humo GOES-19 (DET-16): velo de aerosol bajo todo lo puntual; apagado hasta que se pide.
  add({ id: 'smoke-fill', type: 'fill', source: 'smoke', layout: { visibility: 'none' },
    paint: { 'fill-color': SMOKE_COLOR[theme], 'fill-opacity': SMOKE_OPACITY } });
  // Cicatrices de la temporada (AGUA-01): relleno tenue y borde punteado. Es la huella de
  // calor observada, no un perímetro, y el trazo debe leerse como aproximado.
  add({ id: 'scars-fill', type: 'fill', source: 'scars', paint: { 'fill-color': '#8a4b2a', 'fill-opacity': 0.16 } });
  add({ id: 'scars-line', type: 'line', source: 'scars', paint: { 'line-color': '#8a4b2a', 'line-width': 1.6, 'line-dasharray': [3, 2] } });
  add({ id: 'case-final', type: 'line', source: 'case-final', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2, 'line-dasharray': [2, 1.5] } });
  // Borde oficial CONAF: línea continua verde azulada, distinta del perímetro importado (línea discontinua neutra).
  add({ id: 'case-perimeter', type: 'line', source: 'case-perimeter', paint: { 'line-color': '#1b9e77', 'line-width': 2.4, 'line-opacity': 0.9 } });
  add({ id: 'case-footprint-fill', type: 'fill', source: 'case-footprint', paint: { 'fill-color': '#d9471f', 'fill-opacity': 0.28 } });
  add({ id: 'case-footprint-line', type: 'line', source: 'case-footprint', paint: { 'line-color': '#ff7a2e', 'line-width': 1.4 } });
  // Perímetro oficial de CONAF (OFI-17): neutro y a trazos, para no confundirlo con la huella satelital naranja.
  add({ id: 'official-perimeter-fill', type: 'fill', source: 'official-perimeter', paint: { 'fill-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'fill-opacity': 0.08 } });
  add({ id: 'official-perimeter-line', type: 'line', source: 'official-perimeter', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2.2, 'line-dasharray': [2.5, 1.8] } });
  add({ id: 'place-radius-fill', type: 'fill', source: 'place-radius', paint: { 'fill-color': '#3987e5', 'fill-opacity': 0.06 } });
  add({ id: 'place-radius-line', type: 'line', source: 'place-radius', paint: { 'line-color': '#3987e5', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
  // Línea del lugar al foco confiable más cercano dentro de su radio de aviso (MAPA-153):
  // punteada, con la etiqueta «4,2 km · al noreste» en la mitad. Es ayuda visual, no aviso.
  add({ id: 'place-lines', type: 'line', source: 'place-lines',
    paint: { 'line-color': '#3987e5', 'line-width': 1.6, 'line-dasharray': [2, 2] } });
  add({ id: 'place-lines-label', type: 'symbol', source: 'place-lines',
    layout: { 'symbol-placement': 'line-center', 'text-field': ['get', 'label'], 'text-font': ['Noto Sans Regular'], 'text-size': 11 },
    paint: { 'text-color': theme === 'dark' ? '#ece6dc' : '#17120e', 'text-halo-color': theme === 'dark' ? '#100f0d' : '#efe9df', 'text-halo-width': 1.4 } });
  // Huella aproximada de cada incidente abierto (DET-10): relleno tenue y borde por estado,
  // con los colores ya usados para su severidad. Apagada por defecto y bajo los focos.
  const hullStatus = ['match', ['get', 'status'], 'confirmado', RISK_COLORS.extremo, 'reportado', RISK_COLORS.extremo,
    'posible', RISK_COLORS.alto, 'controlado', RISK_COLORS.moderado, 'anomalia', RISK_COLORS.moderado, RISK_COLORS.alto];
  add({ id: 'incident-hulls-fill', type: 'fill', source: 'incident-hulls', layout: { visibility: 'none' }, paint: { 'fill-color': hullStatus, 'fill-opacity': 0.15 } });
  add({ id: 'incident-hulls-line', type: 'line', source: 'incident-hulls', layout: { visibility: 'none' }, paint: { 'line-color': hullStatus, 'line-width': 1.6 } });
  // Los píxeles GOES se dibujan con su forma real en el terreno (~2–3 km): cuadros, no puntos.
  // De lejos (bajo CELL_ZOOM_MAX) no se dibujan: los mismos focos ya aparecen agrupados por celda.
  add({ id: 'goes-pixels', type: 'fill', source: 'goes-pixels', minzoom: CELL_ZOOM_MAX, paint: { 'fill-color': AGE_COLOR, 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.55, 24, 0.22, 168, 0.12] } });
  add({ id: 'goes-pixels-line', type: 'line', source: 'goes-pixels', minzoom: 8, paint: { 'line-color': AGE_COLOR, 'line-width': 1, 'line-opacity': 0.8 } });
  add({ id: 'case-goes', type: 'fill', source: 'case-goes', paint: { 'fill-color': ['step', ['get', 'age_h'], '#ff4b1f', 1, '#ff7a2e', 3, '#ffa54a'], 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.75, 3, 0.35, 12, 0.12] } });
  // Lo puntual es una brasa: núcleo con borde del color del suelo y, en los focos, un halo difuso.
  const dot = (id, source, color, radius, extra = {}) => add({
    id, type: 'circle', source, ...(extra.filter ? { filter: extra.filter } : {}),
    paint: { 'circle-color': color, 'circle-radius': radius, 'circle-stroke-color': extra.stroke || ring, 'circle-stroke-width': extra.strokeWidth ?? 1.2, ...(extra.paint || {}) },
  });
  const zoomSize = (a, b) => ['interpolate', ['linear'], ['zoom'], 4, a, 11, b];
  const frpSize = (r4, r10) => ['interpolate', ['linear'], ['zoom'],
    4, ['+', r4, ['*', 0.08, ['sqrt', ['coalesce', ['get', 'frp_mw'], 0]]]],
    10, ['+', r10, ['*', 0.25, ['sqrt', ['coalesce', ['get', 'frp_mw'], 0]]]]];
  // Celdas de la vista general (MAPA-01): un punto por grupo; glow y latido solo para focos sueltos.
  const detRadius = ['case', ['has', 'count'],
    ['interpolate', ['linear'], ['get', 'count'], 1, 9, 30, 14, 150, 21, 600, 28],
    frpSize(2.6, 5)];
  dot('detections-glow', 'detections', AGE_COLOR, ['*', 3, frpSize(2.6, 5)], { strokeWidth: 0,
    filter: ['all', ['==', ['get', 'reliable'], true], ['!', ['has', 'count']]], paint: { 'circle-blur': 1, 'circle-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.45, 24, 0.12] } });
  dot('detections-pulse', 'detections', 'rgba(0,0,0,0)', 6, { stroke: '#ff4b1f', strokeWidth: 1.6,
    filter: ['all', ['==', ['get', 'reliable'], true], ['<', ['get', 'age_h'], 3], ['!', ['has', 'count']]], paint: { 'circle-stroke-opacity': 0 } });
  dot('explore', 'explore', '#ffb000', zoomSize(2.4, 5));
  dot('detections', 'detections', AGE_COLOR, detRadius, { stroke: FOCO_STROKE[theme], strokeWidth: 1.4,
    paint: { 'circle-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.45], 'circle-stroke-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.4] } });
  add({ id: 'detections-count', type: 'symbol', source: 'detections', filter: ['>', ['get', 'count'], 1],
    layout: { 'text-field': ['to-string', ['get', 'count']], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#17120e' } });
  // Anillo por incidente abierto a escala país (MAPA-152): solo bajo CELL_ZOOM_MAX, donde
  // los focos ya se agrupan en celdas. Color = estado (la escala de las huellas), radio
  // proporcional a sus detecciones; las anomalías no son incendios y no llevan anillo.
  add({ id: 'incident-rings', type: 'circle', source: 'incident-rings', maxzoom: CELL_ZOOM_MAX,
    filter: ['in', ['get', 'status'], ['literal', ['posible', 'reportado', 'confirmado', 'controlado']]],
    paint: { 'circle-color': 'rgba(0,0,0,0)',
      'circle-radius': ['interpolate', ['linear'], ['min', ['coalesce', ['get', 'n'], 1], 300], 1, 7, 10, 11, 50, 16, 300, 24],
      'circle-stroke-color': hullStatus, 'circle-stroke-width': 2.4, 'circle-stroke-opacity': 0.95 } });
  dot('case-points', 'case-points', ['step', ['get', 'age_h'], '#ff4b1f', 1, '#ff7a2e', 3, '#ffa54a'], zoomSize(2.4, 5));
  dot('reports', 'reports', '#6250d6', 6, { stroke: '#ffffff', strokeWidth: 2 });
  dot('lightning', 'lightning', LIGHTNING_COLOR, zoomSize(2.2, 4.2), { stroke: '#ffffff', strokeWidth: 1 });
  // Incendio informado por CONAF: anillo grueso (oficial), distinto del punto de calor satelital.
  dot('official', 'official', ring, ['match', ['get', 'status'], 'extinguido', 4.5, 7], {
    stroke: ['match', ['get', 'status'], 'confirmado', '#d4231a', 'controlado', '#e8a317', '#8a8378'], strokeWidth: 3.2 });
  dot('services', 'services', ['match', ['get', 'kind'], 'assembly_point', '#0ca30c', 'hospital', '#e34948', 'clinic', '#e87ba4', 'fire_station', '#eb6834', '#3987e5'], 6, { stroke: '#ffffff', strokeWidth: 1.5 });
  dot('places-halo', 'places', '#3987e5', 16, { strokeWidth: 0, paint: { 'circle-opacity': 0.18, 'circle-blur': 0.6 } });
  dot('places', 'places', '#3987e5', 7, { stroke: '#ffffff', strokeWidth: 2.5 });
  dot('case-event', 'case-event', 'rgba(0,0,0,0)', 16, { stroke: theme === 'dark' ? '#ffffff' : '#12100e', strokeWidth: 2.5 });
  dot('pick', 'pick', '#3987e5', 8, { stroke: '#ffffff', strokeWidth: 2.5 });
}

// Capas que siguen la visibilidad de otra (halo y latido de los focos, halo de los lugares,
// tramas del nivel de peligro, que acompañan siempre a risk-fill).
const LINKED = { detections: ['detections-glow', 'detections-pulse', 'detections-count', 'incident-rings'], 'goes-pixels': ['goes-pixels-line'], places: ['places-halo', 'place-lines', 'place-lines-label'], 'risk-fill': RISK_TEX_LEVELS.map((l) => `risk-tex-${l}`) };

/** Latido de los focos confiables de menos de 3 h: un anillo que se expande y se apaga, cada 2,2 s. */
// Ventana de reposo: sin datos nuevos ni interacción durante este tiempo, el ciclo duerme.
export const LATIDO_REPOSO_MS = 20_000;
let pulseFrame = 0; let lastPulse = 0;
let ultimoDatoFocos = 0; let ultimoToque = 0;

/** Decide si el latido debe seguir pidiendo frames (pura, testeable en Node): capa a la vista,
 *  al menos un foco de menos de 3 h, movimiento no reducido y actividad reciente — dato nuevo
 *  (`ultimoCambio`) o interacción (`quietoDesde`: el instante desde el que el mapa quedó quieto)
 *  dentro de la ventana de reposo. */
export function latidoVigente({ visible, focosRecientes, ahora, ultimoCambio, quietoDesde, movimientoReducido = false }) {
  if (movimientoReducido || !visible || !focosRecientes) return false;
  const activo = (ts) => Number.isFinite(ts) && ahora - ts <= LATIDO_REPOSO_MS;
  return activo(ultimoCambio) || activo(quietoDesde);
}

// El anillo solo se pinta en focos confiables de menos de 3 h (filtro de la capa): sin esos,
// animar sería repintar por nada.
const hayFocoReciente = () => (overlayData.detections?.features || [])
  .some((f) => f.properties?.reliable === true && f.properties?.age_h < 3);

function pulse(now) {
  pulseFrame = 0;
  if (!map?.getLayer('detections-pulse')) return;
  // Con la pestaña oculta el navegador ya pausa los rAF: se deja un frame pendiente para retomar al volver.
  if (document.hidden) { pulseFrame = requestAnimationFrame(pulse); return; }
  if (!latidoVigente({
    visible: map.getLayoutProperty('detections-pulse', 'visibility') !== 'none',
    focosRecientes: hayFocoReciente(),
    ahora: now,
    ultimoCambio: ultimoDatoFocos,
    quietoDesde: ultimoToque,
    movimientoReducido: matchMedia('(prefers-reduced-motion: reduce)').matches,
  })) return; // Dormido de verdad: lo despiertan setData('detections'), moveend, style.load y tocar el lienzo.
  pulseFrame = requestAnimationFrame(pulse);
  if (now - lastPulse < 33) return;
  lastPulse = now;
  const t = (now % 2200) / 2200;
  const e = 1 - (1 - t) ** 3;
  const z = map.getZoom();
  // A escala país el latido es discreto (muchos focos juntos); al acercarse crece.
  const near = Math.max(0, Math.min(1, (z - 5) / 5));
  map.setPaintProperty('detections-pulse', 'circle-radius', 3 + e * (7 + 17 * near));
  map.setPaintProperty('detections-pulse', 'circle-stroke-opacity', (0.5 + 0.35 * near) * (1 - t));
}
function startPulse() {
  if (pulseFrame || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  pulseFrame = requestAnimationFrame(pulse);
}

const overlayData = {};
let map = null;
let currentBasemap = 'mapa';
let riskState = null;
let rainState = null;
let selectedComuna = null;
let hoveredComuna = null;
const readyCallbacks = [];

export function getMap() { return map; }
export function onReady(fn) { if (map?.isStyleLoaded() && map.getSource('detections')) fn(map); else readyCallbacks.push(fn); }

export function initMap(container) {
  const theme = store.get('theme');
  map = new maplibregl.Map({
    container, style: baseStyle(theme, currentBasemap), center: [-71.2, -35.4], zoom: 4.6, minZoom: 2.5, maxZoom: 17,
    // compact: false → el crédito de las capas base queda expandido también en el celular
    // (MAPA-105): la licencia de cada base se lee sin tocar el botón «i».
    attributionControl: { compact: false, customAttribution: 'Límites: BCN · Detecciones: NASA FIRMS, NOAA GOES' },
    hash: false, dragRotate: true, pitchWithRotate: true, cooperativeGestures: false,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
  const geolocate = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false, showAccuracyCircle: true });
  map.addControl(geolocate, 'top-right');
  map.on('style.load', () => {
    comunasPedidas = false; // un estilo nuevo vuelve a dejar la fuente comunal vacía
    addRiskPatterns(map, store.get('theme'));
    addOverlays(map, store.get('theme'));
    startPulse();
    applyComunaState();
    if (map.getZoom() >= COMUNAS_ZOOM_MIN) ensureComunas();
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
    if (map.getZoom() >= COMUNAS_ZOOM_MIN) ensureComunas();
  });
  // Un toque o clic en el lienzo también cuenta como actividad y despierta el latido.
  map.getCanvas().addEventListener('pointerdown', () => { ultimoToque = performance.now(); startPulse(); });
  map.on('idle', updateSummary);
  map.on('error', (e) => {
    // Teselas o fuentes externas no disponibles: la base sin conexión (comunas BCN) sigue visible.
    if (e?.sourceId === 'omt' || e?.sourceId === 'raster') store.set('basemapOffline', true);
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
  for (const layer of ['risk-fill', 'rain-fill']) {
    map.on('mousemove', layer, hoverComuna);
    map.on('mouseleave', layer, unhoverComuna);
  }
  for (const layer of ['detections', 'goes-pixels', 'places', 'reports', 'services', 'case-points', 'case-goes', 'explore', 'risk-fill', 'rain-fill', 'official', 'lightning', 'scars-fill', 'incident-rings']) {
    map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
  }
  return map;
}

export function setTheme(theme) {
  if (!map) return;
  map.setStyle(baseStyle(theme, currentBasemap), { diff: false });
}

export function setBasemap(name) {
  currentBasemap = name;
  store.set('basemapOffline', false);
  map?.setStyle(baseStyle(store.get('theme'), name), { diff: false });
}
export const basemap = () => currentBasemap;

export function setData(source, data) {
  overlayData[source] = data;
  if (source === 'detections') { ultimoDatoFocos = performance.now(); refreshDetections(); startPulse(); return; }
  map?.getSource(source)?.setData(data);
  updateSummary();
}

// Banda de zoom entera vigente; la agrupación por celda se recalcula solo al cambiar de banda.
let densityBand = -1;
/** Decimación de focos (MAPA-01): overlayData.detections guarda el dato crudo y la fuente
 *  recibe la vista agrupada por celda del zoom actual (intacta desde CELL_ZOOM_MAX). */
function refreshDetections() {
  if (!map?.getSource('detections')) return;
  const raw = overlayData.detections || EMPTY;
  const t0 = performance.now();
  const view = decimatePoints(raw, Math.floor(map.getZoom()));
  const ms = performance.now() - t0;
  map.getSource('detections').setData(view);
  lastAgrupados = view.features.length;
  updateSummary();
  // Medida de MAPA-01 en consola: features que se dibujan y tiempo de render.
  map.once('idle', () => {
    const drawn = ['detections', 'goes-pixels'].reduce((n, l) => n + (map?.getLayer(l) ? map.queryRenderedFeatures({ layers: [l] }).length : 0), 0);
    console.debug(`BRASA mapa: ${raw.features.length} focos → ${view.features.length} features (${drawn} en pantalla) · decimación ${ms.toFixed(1)} ms`);
  });
}

const visibility = {};
export function show(layerIds, visible) {
  for (const id of [].concat(layerIds).flatMap((x) => [x, ...(LINKED[x] || [])])) {
    visibility[id] = visible;
    if (map?.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }
  startPulse(); // Si los focos vuelven a estar a la vista, el latido se re-evalúa en el próximo frame.
  updateSummary();
}
function applyLayerVisibility() {
  for (const [id, visible] of Object.entries(visibility)) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
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
  ['scars-fill', 'cicatrices'],
  ['reports', 'avisos de vecinos'],
  ['places', 'lugares'],
  ['incident-hulls-fill', 'huellas'],
  ['lightning', 'rayos'],
  ['viento', 'viento'],
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
 *  puntos agrupados, cuántos incendios de CONAF, qué capas están prendidas y la edad del
 *  dato más reciente. `reciente` es una marca de tiempo (ms); `ahora` la referencia (ms). */
export function resumenMapa({ focos = [], agrupados = 0, incendios = 0, reportes = 0, capas = [], ahora = 0, reciente = null }) {
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
  return `Mapa: ${partes.join('. ')}.`;
}

// El texto se reescribe solo si cambió: un aria-live que repite lo mismo vuelve a anunciarlo.
let summaryText = '';
let lastAgrupados = 0;

function updateSummary() {
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
  });
  if (text !== summaryText) { summaryText = text; el.textContent = text; }
}

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
// La geometría comunal se pide una sola vez y solo cuando hace falta (MAPA-143).
let comunasPedidas = false;
function ensureComunas() {
  const source = map?.getSource('comunas');
  if (comunasPedidas || !source) return;
  comunasPedidas = true;
  source.setData('/web/data/comunas.geojson');
}
function applyComunaState() {
  // La coropleta de peligro o de lluvia se pinta sobre los polígonos comunales.
  if (Object.keys(riskState || {}).length || Object.keys(rainState || {}).length) ensureComunas();
  if (!map?.getSource('comunas')) return;
  map.removeFeatureState({ source: 'comunas' });
  if (riskState) for (const [code, r] of Object.entries(riskState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { level: r.level });
  if (rainState) for (const [code, r] of Object.entries(rainState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { rain: r.level });
  // Las tramas no pueden leer feature-state: cada capa risk-tex-* pinta solo las comunas de su nivel.
  const texCodes = Object.fromEntries(RISK_TEX_LEVELS.map((l) => [l, []]));
  if (riskState) for (const [code, r] of Object.entries(riskState)) texCodes[r.level]?.push(Number(code));
  for (const level of RISK_TEX_LEVELS) {
    const id = `risk-tex-${level}`;
    if (map.getLayer(id)) map.setFilter(id, ['in', ['get', 'code'], ['literal', texCodes[level]]]);
  }
  if (selectedComuna !== null) selectComuna(selectedComuna);
}
export function selectComuna(code) {
  selectedComuna = code;
  if (code !== null && code !== undefined) ensureComunas();
  if (map?.getLayer('comuna-selected')) map.setFilter('comuna-selected', ['==', ['get', 'code'], code ?? -1]);
}

/** Márgenes de cámara: en el celular la hoja inferior tapa parte del mapa. */
function viewPadding(base = 40) {
  if (window.innerWidth >= 900) return { top: base + 30, bottom: base, left: base, right: base + 30 };
  const sheet = document.querySelector('#panel')?.getBoundingClientRect().height || 0;
  const visible = window.innerHeight - 64 - sheet;
  const bottom = Math.min(sheet + 12, window.innerHeight * 0.75);
  return visible < 160 ? { top: 70, bottom: 20, left: 16, right: 16 } : { top: 70, bottom, left: 16, right: 50 };
}
export function fly(lon, lat, zoom = 11, opts = {}) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
  map?.flyTo({ center: [lon, lat], zoom, speed: 1.4, curve: 1.5, essential: true, padding: viewPadding(20), ...opts });
}
export function fitBbox([w, s, e, n], padding = 40) {
  map?.fitBounds([[w, s], [e, n]], { padding: viewPadding(padding), duration: 1100, maxZoom: 13 });
}

// ---------------------------------------------------------------- constructores de GeoJSON
export function detectionsGeoJSON(points, now = Date.now()) {
  const dots = []; const squares = [];
  for (const p of points) {
    const age = (now - Date.parse(p.observed_at)) / 3600000;
    const props = { id: p.id, age_h: Math.max(0, age), frp_mw: p.frp_mw, sensor: p.sensor, reliable: ['alta', 'nominal', 'media'].includes(p.confidence) };
    dots.push({ type: 'Feature', id: dots.length, geometry: { type: 'Point', coordinates: [p.lon, p.lat] }, properties: props });
    if (p.sensor === 'ABI') squares.push({ type: 'Feature', geometry: pixelSquare(p.lon, p.lat, pixelKm(p)), properties: props });
  }
  return { dots: { type: 'FeatureCollection', features: dots }, squares: { type: 'FeatureCollection', features: squares } };
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
