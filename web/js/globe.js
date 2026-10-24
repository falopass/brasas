/* Vista 3D (CesiumJS), cargada solo cuando se pide. Comparte hora y datos con el mapa 2D. */
import { fmtNum } from './formato.js';

const CESIUM_VERSION = '1.145.0';
const CESIUM_BASE = `https://cdn.jsdelivr.net/npm/cesium@${CESIUM_VERSION}/Build/Cesium/`;
const CESIUM_DEADLINE_MS = 20000;
export const CESIUM_DEADLINE_MESSAGE = 'La vista 3D pesa unos 6 MB y no cargó en 20 s. En una conexión lenta, usa el mapa 2D: los mismos focos están ahí.';
const CESIUM_UNAVAILABLE_MESSAGE = 'La vista 3D no está disponible en esta conexión. Usa el mapa 2D: los mismos focos están ahí.';
let loading = null;
let cesiumFailed = false;
let viewer = null;
let footprintSource = null;
let points = null;
let terrainOn = false;
let visibilityHandler = null;
let globeContainer = null;
let globeLive = null;
let globeText = '';

const focoValido = (d) => d && Number.isFinite(d.lat) && Number.isFinite(d.lon);

/** Lo que el lienzo 3D no puede decir solo: cuántos focos hay, cuántos son de menos de
 *  una hora, si se ve la zona con calor y si el terreno tiene relieve (UX-04). Pura. */
export function describeGlobe(dots = [], footprint = null, terrain = false) {
  const validos = (Array.isArray(dots) ? dots : []).filter(focoValido);
  const partes = [];
  if (!validos.length) {
    partes.push('sin focos de calor a la vista');
  } else {
    const recientes = validos.filter((d) => d.age_h < 1).length;
    let s = validos.length === 1 ? '1 foco de calor' : `${fmtNum(validos.length)} focos de calor`;
    if (recientes) s += `, ${fmtNum(recientes)} de menos de 1 hora`;
    partes.push(s);
  }
  partes.push(footprint ? 'La zona con calor está marcada' : 'Sin zona con calor marcada');
  partes.push(terrain ? 'Con relieve' : 'Terreno plano');
  return `Vista 3D: ${partes.join('. ')}.`;
}

// El aria-label nombra la región y el <p role="status"> lo anuncia; el texto se
// reescribe solo si cambió, porque un aria-live que repite vuelve a leer lo mismo.
function announceGlobe(dots, footprint) {
  const text = describeGlobe(dots, footprint, terrainOn);
  if (globeContainer) globeContainer.setAttribute('aria-label', text);
  if (globeLive && text !== globeText) { globeText = text; globeLive.textContent = text; }
}

/** Plazo para una promesa: si vence, rechaza con el mensaje dado y no deja el temporizador vivo. */
export function withDeadline(promise, ms, message) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), ms); }),
  ]).finally(() => clearTimeout(timer));
}

function loadCesium() {
  if (window.Cesium) return Promise.resolve(window.Cesium);
  if (cesiumFailed) return Promise.reject(new Error(CESIUM_UNAVAILABLE_MESSAGE));
  if (!loading) {
    window.CESIUM_BASE_URL = CESIUM_BASE;
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = `${CESIUM_BASE}Widgets/widgets.css`;
    document.head.append(css);
    const script = document.createElement('script');
    script.src = `${CESIUM_BASE}Cesium.js`;
    const descarga = new Promise((resolve, reject) => {
      script.onload = () => resolve(window.Cesium);
      script.onerror = () => reject(new Error('No se pudo descargar la vista 3D. Revisa tu conexión o usa el mapa 2D: los mismos focos están ahí.'));
      document.head.append(script);
    });
    loading = withDeadline(descarga, CESIUM_DEADLINE_MS, CESIUM_DEADLINE_MESSAGE).catch((err) => {
      script.remove(); css.remove(); loading = null; cesiumFailed = true;
      throw err;
    });
  }
  return loading;
}

/** Con la pestaña oculta no se piden cuadros (PERF-01); al volver, el bucle se reanuda. */
export function renderLoopFor(hidden, current) {
  return hidden ? false : current;
}

function pauseWithHiddenTab() {
  if (visibilityHandler) return;
  visibilityHandler = () => {
    viewer.useDefaultRenderLoop = renderLoopFor(document.hidden, true);
    if (!document.hidden) viewer.scene.requestRender();
  };
  document.addEventListener('visibilitychange', visibilityHandler);
}

export async function openGlobe(container, { ionToken, camera }) {
  const Cesium = await loadCesium();
  if (!viewer) {
    if (ionToken) Cesium.Ion.defaultAccessToken = ionToken;
    const imagery = new Cesium.UrlTemplateImageryProvider({
      url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2016_3857/default/g/{z}/{y}/{x}.jpg',
      maximumLevel: 14, credit: 'EOxCloudless 2016 by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016, CC BY 4.0)',
    });
    terrainOn = Boolean(ionToken);
    viewer = new Cesium.Viewer(container, {
      animation: false, timeline: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
      navigationHelpButton: false, fullscreenButton: false, infoBox: false, selectionIndicator: false,
      baseLayer: new Cesium.ImageryLayer(imagery),
      terrain: terrainOn ? Cesium.Terrain.fromWorldTerrain() : undefined,
    });
    viewer.scene.globe.depthTestAgainstTerrain = terrainOn;
    viewer.scene.globe.enableLighting = false;
    points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    footprintSource = new Cesium.CustomDataSource('huella');
    viewer.dataSources.add(footprintSource);
    // El lienzo habla: región con nombre, un <p role="status"> con el resumen y la
    // leyenda de la edad de los focos (el color solo no basta, WCAG 1.4.1).
    container.setAttribute('role', 'region');
    globeContainer = container;
    globeLive = document.createElement('p');
    globeLive.className = 'sr-only';
    globeLive.setAttribute('role', 'status');
    globeLive.setAttribute('aria-live', 'polite');
    const leyenda = document.createElement('div');
    leyenda.className = 'map-legend';
    leyenda.setAttribute('role', 'group');
    leyenda.setAttribute('aria-label', 'Edad de cada foco en la vista 3D');
    // Esquina libre: abajo a la izquierda está la leyenda del mapa y a la derecha, más abajo, el readout.
    leyenda.style.cssText = 'left:auto;right:12px;bottom:80px';
    leyenda.innerHTML = `<div class="legend-title">Edad de cada foco</div>
      <div class="legend-row"><span class="legend-item"><span class="sw" style="background:#ff4b1f"></span>menos de 1 h</span>
        <span class="legend-item"><span class="sw" style="background:#ff7a2e"></span>entre 1 y 3 h</span>
        <span class="legend-item"><span class="sw" style="background:#ffa54a;opacity:.6"></span>más de 3 h</span></div>`;
    container.append(globeLive, leyenda);
    announceGlobe([], null);
  }
  pauseWithHiddenTab();
  if (camera) flyGlobe(camera[0], camera[1], camera[2]);
  return { terrain: terrainOn };
}

export function flyGlobe(lon, lat, height = 60000) {
  if (!viewer) return;
  const Cesium = window.Cesium;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(lon, lat - height / 160000, height * 0.75),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(-38), roll: 0 }, duration: 1.6,
  });
}

/** footprint: geometría GeoJSON (Polygon/MultiPolygon) o null; dots: [{lon, lat, age_h}] */
export function updateGlobe(footprint, dots) {
  if (!viewer) return;
  const validos = (Array.isArray(dots) ? dots : []).filter(focoValido);
  announceGlobe(validos, footprint);
  if (!footprint && !validos.length) return;
  const Cesium = window.Cesium;
  footprintSource.entities.removeAll();
  if (footprint) {
    const polys = footprint.type === 'Polygon' ? [footprint.coordinates] : footprint.type === 'MultiPolygon' ? footprint.coordinates : [];
    for (const rings of polys) {
      const outer = rings[0].flat();
      footprintSource.entities.add({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(outer),
            rings.slice(1).map((r) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(r.flat())))),
          material: Cesium.Color.fromCssColorString('#d9471f').withAlpha(0.38),
          outline: false,
          classificationType: terrainOn ? Cesium.ClassificationType.TERRAIN : undefined,
          heightReference: terrainOn ? Cesium.HeightReference.CLAMP_TO_GROUND : undefined,
        },
      });
    }
  }
  points.removeAll();
  for (const d of validos) {
    const color = d.age_h < 1 ? '#ff4b1f' : d.age_h < 3 ? '#ff7a2e' : '#ffa54a';
    points.add({
      position: Cesium.Cartesian3.fromDegrees(d.lon, d.lat, terrainOn ? 2500 : 200),
      color: Cesium.Color.fromCssColorString(color).withAlpha(d.age_h < 3 ? 1 : 0.6),
      pixelSize: d.age_h < 1 ? 9 : 7, outlineColor: Cesium.Color.BLACK.withAlpha(0.6), outlineWidth: 1,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    });
  }
  viewer.scene.requestRender();
}
