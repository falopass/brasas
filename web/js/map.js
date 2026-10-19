/* Mapa 2D (MapLibre): estilo propio claro/oscuro sobre OpenFreeMap, con base sin conexión de comunas reales. */
import { store } from './store.js';
import { circlePolygon, pixelKm, pixelSquare } from './util.js';

const OFM = 'https://tiles.openfreemap.org';
export const BASEMAPS = {
  mapa: { label: 'Mapa' },
  satelite: {
    label: 'Satélite',
    tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg'],
    attribution: '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless 2023</a> by EOX (datos Copernicus modificados, CC BY-NC-SA 4.0)',
    maxzoom: 15,
  },
  topo: {
    label: 'Relieve',
    tiles: ['https://a.tile.opentopomap.org/{z}/{x}/{y}.png', 'https://b.tile.opentopomap.org/{z}/{x}/{y}.png'],
    attribution: '© <a href="https://opentopomap.org" target="_blank" rel="noopener">OpenTopoMap</a> (CC-BY-SA), © OpenStreetMap',
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
// Apta para daltonismo (deuteranopía/protanopía), validada por scripts/local/validate_palette.mjs.
export const RISK_COLORS = { bajo: '#1a7f46', moderado: '#8f7a00', alto: '#c2571e', extremo: '#e50d06' };
// Anomalía de lluvia de la temporada: rampa seca (café) → húmeda (azul), distinguible de la de
// riesgo y apta para daltonismo (ΔE ≥ 12 entre niveles bajo deuteranopía/protanopía, criterio UX-13).
export const RAIN_COLORS = { muy_seco: '#93570a', seco: '#b08424', normal: '#7a7e72', humedo: '#2a837b', muy_humedo: '#1d6da8' };
// Niveles del peligro que llevan además una trama propia sobre el mapa (UX-20), en orden.
const RISK_TEX_LEVELS = ['bajo', 'moderado', 'alto', 'extremo'];
// Destellos GLM (rayos): cian, lejos del ámbar de los focos de calor y del violeta de los avisos.
export const LIGHTNING_COLOR = '#00b8d4';

function baseStyle(theme, basemap) {
  const c = PALETTE[theme];
  const sources = {
    comunas: { type: 'geojson', data: '/web/data/comunas.geojson', promoteId: 'code' },
    regiones: { type: 'geojson', data: '/web/data/regiones.geojson', promoteId: 'code' },
  };
  const layers = [{ id: 'background', type: 'background', paint: { 'background-color': basemap === 'mapa' ? c.land : c.ocean } }];
  if (basemap === 'mapa') {
    sources.omt = { type: 'vector', url: `${OFM}/planet`, attribution: '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' };
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
    { id: 'comunas-line', type: 'line', source: 'comunas', minzoom: 6, maxzoom: 11, paint: { 'line-color': c.comuna, 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 10, 1], 'line-opacity': ['interpolate', ['linear'], ['zoom'], 8.5, 1, 10.5, 0] } },
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
const OVERLAY_SOURCES = ['places', 'place-radius', 'detections', 'goes-pixels', 'reports', 'services', 'explore', 'official',
  'incident-hulls', 'lightning', 'case-footprint', 'case-points', 'case-goes', 'case-final', 'case-event', 'case-perimeter', 'pick'];

function addOverlays(map, theme) {
  const ring = theme === 'dark' ? '#0d0c0b' : '#ece6dc';
  for (const id of OVERLAY_SOURCES) if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: overlayData[id] || EMPTY });
  const add = (layer) => { if (!map.getLayer(layer.id)) map.addLayer(layer); };
  add({ id: 'case-final', type: 'line', source: 'case-final', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2, 'line-dasharray': [2, 1.5] } });
  // Borde oficial CONAF: línea continua verde azulada, distinta del perímetro importado (línea discontinua neutra).
  add({ id: 'case-perimeter', type: 'line', source: 'case-perimeter', paint: { 'line-color': '#1b9e77', 'line-width': 2.4, 'line-opacity': 0.9 } });
  add({ id: 'case-footprint-fill', type: 'fill', source: 'case-footprint', paint: { 'fill-color': '#d9471f', 'fill-opacity': 0.28 } });
  add({ id: 'case-footprint-line', type: 'line', source: 'case-footprint', paint: { 'line-color': '#ff7a2e', 'line-width': 1.4 } });
  add({ id: 'place-radius-fill', type: 'fill', source: 'place-radius', paint: { 'fill-color': '#3987e5', 'fill-opacity': 0.06 } });
  add({ id: 'place-radius-line', type: 'line', source: 'place-radius', paint: { 'line-color': '#3987e5', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
  // Huella aproximada de cada incidente abierto (DET-10): relleno tenue y borde por estado,
  // con los colores ya usados para su severidad. Apagada por defecto y bajo los focos.
  const hullStatus = ['match', ['get', 'status'], 'confirmado', RISK_COLORS.extremo, 'reportado', RISK_COLORS.extremo,
    'posible', RISK_COLORS.alto, 'controlado', RISK_COLORS.moderado, 'anomalia', RISK_COLORS.moderado, RISK_COLORS.alto];
  add({ id: 'incident-hulls-fill', type: 'fill', source: 'incident-hulls', layout: { visibility: 'none' }, paint: { 'fill-color': hullStatus, 'fill-opacity': 0.15 } });
  add({ id: 'incident-hulls-line', type: 'line', source: 'incident-hulls', layout: { visibility: 'none' }, paint: { 'line-color': hullStatus, 'line-width': 1.6 } });
  // Los píxeles GOES se dibujan con su forma real en el terreno (~2–3 km): cuadros, no puntos.
  add({ id: 'goes-pixels', type: 'fill', source: 'goes-pixels', paint: { 'fill-color': AGE_COLOR, 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.55, 24, 0.22, 168, 0.12] } });
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
  dot('detections-glow', 'detections', AGE_COLOR, ['*', 3, frpSize(2.6, 5)], { strokeWidth: 0,
    filter: ['==', ['get', 'reliable'], true], paint: { 'circle-blur': 1, 'circle-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.45, 24, 0.12] } });
  dot('detections-pulse', 'detections', 'rgba(0,0,0,0)', 6, { stroke: '#ff4b1f', strokeWidth: 1.6,
    filter: ['all', ['==', ['get', 'reliable'], true], ['<', ['get', 'age_h'], 3]], paint: { 'circle-stroke-opacity': 0 } });
  dot('explore', 'explore', '#ffb000', zoomSize(2.4, 5));
  dot('detections', 'detections', AGE_COLOR, frpSize(2.6, 5), { paint: { 'circle-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.45], 'circle-stroke-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.4] } });
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
const LINKED = { detections: ['detections-glow', 'detections-pulse'], places: ['places-halo'], 'risk-fill': RISK_TEX_LEVELS.map((l) => `risk-tex-${l}`) };

/** Latido de los focos confiables de menos de 3 h: un anillo que se expande y se apaga, cada 2,2 s. */
let pulseFrame = 0; let lastPulse = 0;
function pulse(now) {
  pulseFrame = requestAnimationFrame(pulse);
  if (!map?.getLayer('detections-pulse') || document.hidden || now - lastPulse < 33) return;
  if (map.getLayoutProperty('detections-pulse', 'visibility') === 'none' || !overlayData.detections?.features?.length) return;
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
    attributionControl: { compact: true, customAttribution: 'Límites: BCN · Detecciones: NASA FIRMS, NOAA GOES' },
    hash: false, dragRotate: true, pitchWithRotate: true, cooperativeGestures: false,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
  const geolocate = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false, showAccuracyCircle: true });
  map.addControl(geolocate, 'top-right');
  map.on('style.load', () => {
    addRiskPatterns(map, store.get('theme'));
    addOverlays(map, store.get('theme'));
    startPulse();
    applyComunaState();
    applyLayerVisibility();
    readyCallbacks.splice(0).forEach((fn) => fn(map));
  });
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
  for (const layer of ['detections', 'goes-pixels', 'places', 'reports', 'services', 'case-points', 'case-goes', 'explore', 'risk-fill', 'rain-fill', 'official', 'lightning']) {
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
  map?.getSource(source)?.setData(data);
}

const visibility = {};
export function show(layerIds, visible) {
  for (const id of [].concat(layerIds).flatMap((x) => [x, ...(LINKED[x] || [])])) {
    visibility[id] = visible;
    if (map?.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }
}
function applyLayerVisibility() {
  for (const [id, visible] of Object.entries(visibility)) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
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
function applyComunaState() {
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
