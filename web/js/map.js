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
  dark: {
    background: '#0f1719', ocean: '#0b1316', water: '#10242c', land: '#18222a', chile: '#1b272d', wood: '#18282a', grass: '#1a2726',
    urban: '#222d33', road: '#33424a', roadMajor: '#4a5a62', boundary: '#5d6b70', comuna: 'rgba(170,190,195,0.16)',
    region: 'rgba(200,215,218,0.42)', label: '#c9d3d6', labelHalo: '#0f1719', minorLabel: '#93a2a6',
  },
  light: {
    background: '#ece8df', ocean: '#cfe0e6', water: '#bcd6df', land: '#f3f0e9', chile: '#f6f3ec', wood: '#dfe6d2', grass: '#e7ead9',
    urban: '#e6e0d6', road: '#ffffff', roadMajor: '#f2d9b9', boundary: '#8f8a80', comuna: 'rgba(80,70,60,0.18)',
    region: 'rgba(70,60,50,0.45)', label: '#2c2a26', labelHalo: '#f6f3ec', minorLabel: '#5e5a52',
  },
};

// Edad de la detección → color (rampa secuencial ámbar: lo más reciente es lo más intenso).
export const AGE_BINS = [
  { maxH: 1, color: '#ff4b1f', label: '< 1 h' },
  { maxH: 6, color: '#ff7a2e', label: '1–6 h' },
  { maxH: 24, color: '#ffa54a', label: '6–24 h' },
  { maxH: Infinity, color: '#ffd38f', label: '> 24 h' },
];
const AGE_COLOR = ['step', ['get', 'age_h'], AGE_BINS[0].color, 1, AGE_BINS[1].color, 6, AGE_BINS[2].color, 24, AGE_BINS[3].color];
export const RISK_COLORS = { bajo: '#0ca30c', moderado: '#fab219', alto: '#ec835a', extremo: '#d03b3b' };

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

const EMPTY = { type: 'FeatureCollection', features: [] };
const OVERLAY_SOURCES = ['places', 'place-radius', 'detections', 'goes-pixels', 'reports', 'services', 'explore',
  'case-footprint', 'case-points', 'case-goes', 'case-final', 'case-event', 'pick'];

function addOverlays(map, theme) {
  const ring = theme === 'dark' ? '#0f1719' : '#fbfaf7';
  for (const id of OVERLAY_SOURCES) if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: overlayData[id] || EMPTY });
  const add = (layer) => { if (!map.getLayer(layer.id)) map.addLayer(layer); };
  add({ id: 'case-final', type: 'line', source: 'case-final', paint: { 'line-color': theme === 'dark' ? '#e8e2d4' : '#3a3530', 'line-width': 2, 'line-dasharray': [2, 1.5] } });
  add({ id: 'case-footprint-fill', type: 'fill', source: 'case-footprint', paint: { 'fill-color': '#d9471f', 'fill-opacity': 0.28 } });
  add({ id: 'case-footprint-line', type: 'line', source: 'case-footprint', paint: { 'line-color': '#ff7a2e', 'line-width': 1.4 } });
  add({ id: 'place-radius-fill', type: 'fill', source: 'place-radius', paint: { 'fill-color': '#3987e5', 'fill-opacity': 0.06 } });
  add({ id: 'place-radius-line', type: 'line', source: 'place-radius', paint: { 'line-color': '#3987e5', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
  add({ id: 'goes-pixels', type: 'fill', source: 'goes-pixels', paint: { 'fill-color': AGE_COLOR, 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.55, 24, 0.22, 168, 0.12] } });
  add({ id: 'goes-pixels-line', type: 'line', source: 'goes-pixels', minzoom: 8, paint: { 'line-color': AGE_COLOR, 'line-width': 1, 'line-opacity': 0.8 } });
  add({ id: 'case-goes', type: 'fill', source: 'case-goes', paint: { 'fill-color': ['step', ['get', 'age_h'], '#ff4b1f', 1, '#ff7a2e', 3, '#ffa54a'], 'fill-opacity': ['interpolate', ['linear'], ['get', 'age_h'], 0, 0.75, 3, 0.35, 12, 0.12] } });
  add({ id: 'explore', type: 'circle', source: 'explore', paint: { 'circle-color': '#ffb000', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 2.5, 10, 6], 'circle-stroke-color': ring, 'circle-stroke-width': 1.2 } });
  add({ id: 'detections', type: 'circle', source: 'detections',
    paint: { 'circle-color': AGE_COLOR, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, ['+', 2.5, ['*', 0.06, ['sqrt', ['coalesce', ['get', 'frp_mw'], 0]]]], 10, ['+', 6, ['*', 0.25, ['sqrt', ['coalesce', ['get', 'frp_mw'], 0]]]]],
      'circle-stroke-color': ring, 'circle-stroke-width': 1.5, 'circle-opacity': ['case', ['==', ['get', 'reliable'], true], 1, 0.55] } });
  add({ id: 'case-points', type: 'circle', source: 'case-points', paint: { 'circle-color': ['step', ['get', 'age_h'], '#ff4b1f', 1, '#ff7a2e', 3, '#ffa54a'], 'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 2.5, 12, 6], 'circle-stroke-color': ring, 'circle-stroke-width': 1 } });
  add({ id: 'reports', type: 'circle', source: 'reports', paint: { 'circle-color': '#6250d6', 'circle-radius': 7, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
  add({ id: 'services', type: 'circle', source: 'services', paint: { 'circle-color': ['match', ['get', 'kind'], 'assembly_point', '#0ca30c', 'hospital', '#e34948', 'clinic', '#e87ba4', 'fire_station', '#eb6834', '#3987e5'], 'circle-radius': 6, 'circle-stroke-color': ring, 'circle-stroke-width': 2 } });
  add({ id: 'places', type: 'circle', source: 'places', paint: { 'circle-color': '#3987e5', 'circle-radius': 8, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } });
  add({ id: 'case-event', type: 'circle', source: 'case-event', paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-radius': 16, 'circle-stroke-color': theme === 'dark' ? '#ffffff' : '#111', 'circle-stroke-width': 2 } });
  add({ id: 'pick', type: 'circle', source: 'pick', paint: { 'circle-color': '#3987e5', 'circle-radius': 9, 'circle-stroke-color': '#fff', 'circle-stroke-width': 3 } });
}

const overlayData = {};
let map = null;
let currentBasemap = 'mapa';
let riskState = null;
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
    addOverlays(map, store.get('theme'));
    applyRisk();
    applyLayerVisibility();
    readyCallbacks.splice(0).forEach((fn) => fn(map));
  });
  map.on('error', (e) => {
    // Teselas o fuentes externas no disponibles: la base sin conexión (comunas BCN) sigue visible.
    if (e?.sourceId === 'omt' || e?.sourceId === 'raster') store.set('basemapOffline', true);
  });
  map.on('mousemove', 'risk-fill', (e) => {
    const code = e.features?.[0]?.id;
    if (code === hoveredComuna) return;
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: false });
    hoveredComuna = code ?? null;
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: true });
  });
  map.on('mouseleave', 'risk-fill', () => {
    if (hoveredComuna !== null) map.setFeatureState({ source: 'comunas', id: hoveredComuna }, { hover: false });
    hoveredComuna = null;
  });
  for (const layer of ['detections', 'goes-pixels', 'places', 'reports', 'services', 'case-points', 'case-goes', 'explore', 'risk-fill']) {
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
  for (const id of [].concat(layerIds)) {
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
  applyRisk();
}
function applyRisk() {
  if (!map?.getSource('comunas')) return;
  map.removeFeatureState({ source: 'comunas' });
  if (riskState) for (const [code, r] of Object.entries(riskState)) map.setFeatureState({ source: 'comunas', id: Number(code) }, { level: r.level });
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
