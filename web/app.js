/* BRASA Chile MVP. Sin detecciones inventadas: solo API FIRMS e importaciones GeoJSON. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = {
    config: null, viewer: null, pointsCollection: null, polygonSources: [],
    mode: 'recent', region: 'maule', days: 3, start: '2017-01-24',
    observations: [], visible: [], dates: [], selectedDay: 2,
    playing: false, playTimer: null, loaded: false, requestId: 0, weatherRequestId: 0,
  };
  const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[ch]));
  const fmtNumber = (num, digits=0) => Number.isFinite(num) ? new Intl.NumberFormat('es-CL', {maximumFractionDigits:digits}).format(num) : '—';
  const fmtDate = (date) => new Date(`${date}T12:00:00Z`).toLocaleDateString('es-CL', {day:'numeric', month:'short', year:'numeric', timeZone:'UTC'});
  const fmtTime = (date) => new Date(date).toLocaleString('es-CL', {dateStyle:'medium', timeStyle:'short', timeZone:'America/Santiago'});
  const dateOffset = (str, offset) => { const date = new Date(`${str}T12:00:00Z`); date.setUTCDate(date.getUTCDate()+offset); return date.toISOString().slice(0,10); };
  const todayUTC = () => new Date().toISOString().slice(0,10);
  const setNotice = (message, error=false) => { $('notice').textContent = message; $('notice').classList.toggle('error',error); };

  function flyToRegion() {
    if (!state.viewer) return;
    const region = state.config.regions[state.region];
    const [lon,lat,height] = region.camera;
    state.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lon,lat,height),
      orientation: {heading:0,pitch:Cesium.Math.toRadians(-66),roll:0},
      duration: 1.45,
    });
    $('map-title').textContent = region.label.replace(' (aproximado)','');
  }

  function initGlobe() {
    if (!window.Cesium) throw new Error('No se pudo descargar el motor CesiumJS.');
    const ionToken = state.config.ion_public_token;
    if (ionToken) Cesium.Ion.defaultAccessToken = ionToken;
    const imagery = new Cesium.OpenStreetMapImageryProvider({url:'https://tile.openstreetmap.org/'});
    state.viewer = new Cesium.Viewer('cesium', {
      animation:false, baseLayerPicker:false, fullscreenButton:false, geocoder:false,
      homeButton:false, sceneModePicker:false, infoBox:false, timeline:false,
      selectionIndicator:false, navigationHelpButton:false,
      baseLayer: new Cesium.ImageryLayer(imagery),
      terrain: ionToken ? Cesium.Terrain.fromWorldTerrain() : undefined,
      contextOptions: {webgl: {alpha:false}},
    });
    state.viewer.scene.globe.enableLighting = false;
    state.viewer.scene.globe.depthTestAgainstTerrain = false; // MVP: puntos visibles aun sobre relieve alto; pendiente clamp real
    state.viewer.scene.skyAtmosphere.show = true;
    state.viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0b1b1f');
    // Los puntos primitivos escalan mucho mejor que una entidad HTML por detección.
    state.pointsCollection = state.viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    const handler = new Cesium.ScreenSpaceEventHandler(state.viewer.scene.canvas);
    handler.setInputAction((event) => {
      const hit = state.viewer.scene.pick(event.position);
      if (hit && hit.id && hit.id.brasaHotspot === true) showDetail(hit.id.record);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    flyToRegion();
  }

  function modeChange(mode) {
    stopPlaying();
    state.mode = mode;
    $('mode-recent').classList.toggle('selected',mode === 'recent');
    $('mode-historical').classList.toggle('selected',mode === 'historical');
    $('historical-date').disabled = mode !== 'historical';
    $('map-subtitle').textContent = mode === 'recent'
      ? 'Detecciones satelitales recientes · NASA FIRMS'
      : 'Exploración retrospectiva · NASA FIRMS / CONAF';
    $('map-mode-caption').textContent = mode === 'recent'
      ? 'Observaciones satelitales · no equivalen a incendios confirmados'
      : 'Evolución por fecha de observación · no es propagación continua del fuego';
    state.requestId++;
    $('refresh').disabled = false;
    state.loaded = false;
    state.observations = [];
    updateDates();
    paintDetections();
    setNotice('Pulsa «Consultar satélites» para cargar los registros seleccionados.');
  }

  function updateDates() {
    state.days = Number($('days').value);
    state.start = $('historical-date').value;
    const start = state.mode === 'recent' ? dateOffset(todayUTC(), 1-state.days) : state.start;
    state.dates = Array.from({length:state.days}, (_,index) => dateOffset(start,index));
    state.selectedDay = state.days-1;
    $('timeline-slider').max = String(state.days-1);
    $('timeline-slider').value = String(state.selectedDay);
    renderTimeline();
  }

  function renderTimeline() {
    const date = state.dates[state.selectedDay];
    $('timeline-day').textContent = date ? fmtDate(date) : '—';
    $('range-start').textContent = state.dates.length ? fmtDate(state.dates[0]) : '—';
    $('range-end').textContent = state.dates.length ? fmtDate(state.dates[state.dates.length-1]) : '—';
    $('timeline-end').textContent = state.mode === 'recent' ? 'Detecciones observadas · horas UTC' : 'Registros históricos · horas UTC';
  }

  function paintDetections() {
    state.visible = state.observations.filter((p) => p.date === state.dates[state.selectedDay]);
    const points = state.pointsCollection;
    if (points) {
      points.removeAll();
      if ($('show-points').checked) {
        for (const p of state.visible) {
          const mw = p.frp_mw ?? 0;
          const size = Math.max(7,Math.min(23,8+Math.sqrt(Math.max(0,mw))*1.2));
          points.add({
            position: Cesium.Cartesian3.fromDegrees(p.lon,p.lat,1500),
            color: Cesium.Color.fromCssColorString(mw>70 ? '#ff5634' : mw>25 ? '#ee8743' : '#ffe29a'),
            outlineColor: Cesium.Color.fromCssColorString('#502b20'),
            outlineWidth: 1.5, pixelSize:size,
            scaleByDistance:new Cesium.NearFarScalar(2000,1.5,3500000,.48),
            id:{brasaHotspot:true,record:p},
          });
        }
      }
    }
    $('count').textContent = state.loaded ? fmtNumber(state.visible.length) : '—';
    const maxFrp = state.visible.reduce((maximum,p)=>Math.max(maximum,p.frp_mw??0),0);
    $('frp').textContent = state.loaded && state.visible.length ? `${fmtNumber(maxFrp,1)} MW` : '—';
    $('sensors').textContent = state.loaded ? String(new Set(state.visible.map(p=>p.source)).size) : '—';
    $('count-note').textContent = state.loaded ? `De ${fmtNumber(state.observations.length)} observaciones en la ventana` : 'Esperando consulta';
    if (state.visible.length === 0 && state.loaded) {
      $('detail').innerHTML = '<div class="empty-icon">◎</div><strong>Sin detecciones para esta fecha</strong><p>La ausencia de observaciones en FIRMS no demuestra que no haya incendios. Podría no haberse registrado un paso satelital útil.</p>';
    } else {
      $('detail').innerHTML = '<div class="empty-icon">⌖</div><strong>Selecciona una detección</strong><p>Haz clic en un punto del mapa para revisar fecha, origen satelital y potencia radiativa.</p>';
    }
  }

  function showDetail(record) {
    const p = record;
    const entries = [
      ['Satélite / producto',p.source],
      ['Observación · hora Chile',fmtTime(p.observed_at)],
      ['Latitud',p.lat.toFixed(5)],['Longitud',p.lon.toFixed(5)],
      ['FRP (potencia radiativa)',p.frp_mw === null ? 'No informada' : `${fmtNumber(p.frp_mw,1)} MW`],
      ['Brillo radiométrico',p.brightness_k === null ? 'No informado' : `${fmtNumber(p.brightness_k,1)} K`],
      ['Confianza según producto',p.confidence ?? 'No informada'],
    ];
    $('detail').innerHTML = `<div class="detail-title">Detección satelital</div>${entries.map(([name,value])=>`<div class="detail-metric"><span>${escapeHtml(name)}</span><b>${escapeHtml(value)}</b></div>`).join('')}<p>Registro térmico sin confirmación independiente de incendio.</p>`;
  }

  async function fetchHotspots() {
    const requestId = ++state.requestId;
    stopPlaying();
    state.region = $('region').value;
    updateDates();
    flyToRegion();
    state.loaded = false;
    state.observations = [];
    paintDetections();
    $('refresh').disabled = true;
    setNotice('Consultando NASA FIRMS. Esto puede tardar unos segundos…');
    try {
      const query = new URLSearchParams({mode:state.mode,region:state.region,days:String(state.days)});
      if (state.mode === 'historical') query.set('start',state.start);
      const response = await fetch(`/api/hotspots?${query.toString()}`);
      const data = await response.json();
      if (requestId !== state.requestId) return;
      if (!response.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Error consultando la API.');
      }
      state.observations = data.points;
      state.loaded = true;
      const observedDates = new Set(data.points.map(p=>p.date));
      const latestAvailable = [...state.dates].reverse().find(d=>observedDates.has(d));
      if (latestAvailable) state.selectedDay = state.dates.indexOf(latestAvailable);
      $('timeline-slider').value = String(state.selectedDay);
      renderTimeline();
      paintDetections();
      const when = new Date(data.retrieved_at_utc).toLocaleTimeString('es-CL',{hour:'2-digit',minute:'2-digit',timeZone:'America/Santiago'});
      const notes = data.notices.length ? ` Hay ${data.notices.length} advertencia(s) de proveedor.` : '';
      setNotice(`${fmtNumber(data.points.length)} observaciones recibidas. Consulta: ${when} (hora Chile). Las cajas geográficas son aproximadas.${notes}`);
    } catch(error) {
      if (requestId === state.requestId) {
        setNotice(error.message || 'No fue posible consultar los datos.',true);
        state.loaded = false;
        paintDetections();
      }
    } finally {
      if (requestId === state.requestId) $('refresh').disabled = false;
    }
  }

  async function fetchWeather() {
    const requestId = ++state.weatherRequestId;
    const region = state.config.regions[state.region];
    const [lon,lat] = region.camera;
    ['weather-temp','weather-humidity','weather-wind','weather-direction'].forEach((id)=>$(id).textContent='…');
    try {
      const response = await fetch(`/api/weather?lat=${lat}&lon=${lon}`);
      if(!response.ok) throw new Error('Weather error');
      const {data} = await response.json();
      if (requestId !== state.weatherRequestId) return;
      $('weather-temp').textContent = Number.isFinite(data.temperature_2m) ? `${fmtNumber(data.temperature_2m,1)} °C` : '—';
      $('weather-humidity').textContent = Number.isFinite(data.relative_humidity_2m) ? `${fmtNumber(data.relative_humidity_2m)} %` : '—';
      $('weather-wind').textContent = Number.isFinite(data.wind_speed_10m) ? `${fmtNumber(data.wind_speed_10m)} km/h` : '—';
      $('weather-direction').textContent = Number.isFinite(data.wind_direction_10m) ? `${fmtNumber(data.wind_direction_10m)}°` : '—';
    } catch (_err) {if(requestId === state.weatherRequestId) ['weather-temp','weather-humidity','weather-wind','weather-direction'].forEach((id)=>$(id).textContent='—');}
  }

  function setTimelineDay(index) {
    state.selectedDay = Math.min(state.days-1,Math.max(0,index));
    $('timeline-slider').value = String(state.selectedDay);
    renderTimeline();
    paintDetections();
  }
  function stopPlaying(){
    state.playing = false;
    if (state.playTimer !== null) clearInterval(state.playTimer);
    state.playTimer = null;
    if ($('timeline-play')) $('timeline-play').textContent = '▶';
  }
  function togglePlaying(){
    if (state.playing) return stopPlaying();
    state.playing = true;
    $('timeline-play').textContent = 'Ⅱ';
    if (state.selectedDay === state.days-1) setTimelineDay(0);
    state.playTimer = setInterval(()=>{
      if (state.selectedDay >= state.days-1) return stopPlaying();
      setTimelineDay(state.selectedDay+1);
    },1500);
  }

  async function importGeoJSON(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 35*1024*1024) {setNotice('El archivo supera 35 MB. Simplifica el GeoJSON.',true);return;}
    try {
      const data = JSON.parse(await file.text());
      if (!['Feature','FeatureCollection','GeometryCollection','Polygon','MultiPolygon'].includes(data.type)) throw new Error('Archivo no es GeoJSON válido.');
      const source = await Cesium.GeoJsonDataSource.load(data,{
        stroke:Cesium.Color.fromCssColorString('#ed7b43'),
        strokeWidth:2.2,
        fill:Cesium.Color.fromCssColorString('#d96737').withAlpha(.24),
        clampToGround:true,
      });
      await state.viewer.dataSources.add(source);
      source.show=$('show-polygons').checked;
      state.polygonSources.push(source);
      setNotice(`Capa importada: ${file.name}. Cartografía aportada por el usuario (no verificada en el prototipo).`);
      if (source.entities.values.length && source.entities.values.length<20000) state.viewer.flyTo(source,{duration:1.4}).catch(()=>{});
    } catch (error) {setNotice(`No se pudo importar el GeoJSON: ${error.message}`,true);}
    event.target.value = '';
  }

  function setupEvents(){
    $('mode-recent').addEventListener('click',()=>modeChange('recent'));
    $('mode-historical').addEventListener('click',()=>modeChange('historical'));
    $('region').addEventListener('change',()=>{state.region=$('region').value;state.requestId++;$('refresh').disabled=false;flyToRegion();fetchWeather();state.loaded=false;state.observations=[];paintDetections();setNotice('Zona modificada. Consulta para cargar los registros.');});
    $('days').addEventListener('change',()=>{stopPlaying();state.requestId++;$('refresh').disabled=false;updateDates();state.loaded=false;state.observations=[];paintDetections();setNotice('Ventana modificada. Consulta para cargar los registros.');});
    $('historical-date').addEventListener('change',()=>{stopPlaying();state.requestId++;$('refresh').disabled=false;updateDates();state.loaded=false;state.observations=[];paintDetections();setNotice('Fecha modificada. Consulta para cargar los registros.');});
    $('refresh').addEventListener('click',fetchHotspots);
    $('recenter').addEventListener('click',flyToRegion);
    $('show-points').addEventListener('change',paintDetections);
    $('show-polygons').addEventListener('change',()=>state.polygonSources.forEach(s=>s.show=$('show-polygons').checked));
    $('geojson-file').addEventListener('change',importGeoJSON);
    $('view-2d').addEventListener('click',()=>{state.viewer.scene.morphTo2D(1.0);$('view-2d').classList.add('active');$('view-3d').classList.remove('active');});
    $('view-3d').addEventListener('click',()=>{state.viewer.scene.morphTo3D(1.0);$('view-3d').classList.add('active');$('view-2d').classList.remove('active');});
    $('timeline-slider').addEventListener('input',(event)=>{stopPlaying();setTimelineDay(Number(event.target.value));});
    $('timeline-start').addEventListener('click',()=>{stopPlaying();setTimelineDay(0);});
    $('timeline-prev').addEventListener('click',()=>{stopPlaying();setTimelineDay(state.selectedDay-1);});
    $('timeline-next').addEventListener('click',()=>{stopPlaying();setTimelineDay(state.selectedDay+1);});
    $('timeline-play').addEventListener('click',togglePlaying);
  }

  async function main(){
    try {
      const response = await fetch('/api/config');
      if (!response.ok) throw new Error('Servidor API no disponible');
      state.config = await response.json();
      const select = $('region');
      select.innerHTML = Object.entries(state.config.regions).map(([key,value])=>`<option value="${escapeHtml(key)}">${escapeHtml(value.label)}</option>`).join('');
      select.value=state.region;
      $('historical-date').max=todayUTC();
      updateDates();
      setupEvents();
      initGlobe();
      fetchWeather();
      if (state.config.firms_configured) fetchHotspots();
      else setNotice('La interfaz está lista. Agrega tu clave gratuita de NASA FIRMS en el archivo .env para cargar observaciones reales.',true);
    } catch (error) {
      setNotice(`No se pudo iniciar BRASA: ${error.message}`,true);
      $('map-failure').classList.remove('hidden');
      $('map-failure').textContent = `No se pudo inicializar Cesium: ${error.message}`;
    }
  }
  main();
})();
