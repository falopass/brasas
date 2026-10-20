/* Vista 3D (CesiumJS), cargada solo cuando se pide. Comparte hora y datos con el mapa 2D. */
const CESIUM_VERSION = '1.145.0';
const CESIUM_BASE = `https://cdn.jsdelivr.net/npm/cesium@${CESIUM_VERSION}/Build/Cesium/`;
let loading = null;
let viewer = null;
let footprintSource = null;
let points = null;
let terrainOn = false;
let visibilityHandler = null;

function loadCesium() {
  if (window.Cesium) return Promise.resolve(window.Cesium);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      window.CESIUM_BASE_URL = CESIUM_BASE;
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = `${CESIUM_BASE}Widgets/widgets.css`;
      document.head.append(css);
      const script = document.createElement('script');
      script.src = `${CESIUM_BASE}Cesium.js`;
      script.onload = () => resolve(window.Cesium);
      script.onerror = () => { loading = null; reject(new Error('No se pudo descargar CesiumJS (vista 3D). Revisa tu conexión.')); };
      document.head.append(script);
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
      url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg',
      maximumLevel: 14, credit: 'Sentinel-2 cloudless 2023 by EOX (Copernicus, CC BY-NC-SA 4.0)',
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
  for (const d of dots) {
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

export const globeOpen = () => Boolean(viewer);
