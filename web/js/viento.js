/* RISK-07 / MAPA-187: partículas y flechas de viento a 10 m sobre el mapa, en canvas
 * propio (sin dependencias). La grilla regular (base 1° país + subgrilla fina 0,25°
 * centro-sur, con pasos +0/+3/+6/+12 h y ráfagas) la precalcula el backend
 * (GET /api/wind/grid, cada 6 h): ninguna visita llama a Open-Meteo.
 * Se pausa con la pestaña oculta o la capa apagada; con prefers-reduced-motion o el
 * modo ahorro (UX-76) se dibujan flechas estáticas. */
import { fmtTime } from './formato.js';
import { getMap } from './map.js';
import { store } from './store.js';

export const FRESCA_MAX_H = 12;
export const PASOS_HORA = [0, 3, 6, 12];
const VIGENTE_TOL_MS = 90 * 60000;
// Cuatro tramos de color accesibles por rapidez del viento a 10 m (km/h).
export const WIND_BANDS = [
  { max: 15, color: '#5aa0d8', lightColor: '#1d4ed8', cls: 'sw-wind-1', label: '<15 km/h' },
  { max: 30, color: '#2ec4b6', lightColor: '#0f766e', cls: 'sw-wind-2', label: '15–30 km/h' },
  { max: 50, color: '#f59f00', lightColor: '#b45309', cls: 'sw-wind-3', label: '30–50 km/h' },
  { max: Infinity, color: '#e03131', lightColor: '#b91c1c', cls: 'sw-wind-4', label: '>50 km/h' },
];

let grid = null;
let vista = null;
let pasoHora = 0;
let pasoElegidoPorUsuario = false;
let canvas = null;
let raf = 0;
let corriendo = false;
const mqlReducido = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
let reducido = Boolean(mqlReducido?.matches);
// Flechas fijas en vez de animación: movimiento reducido del sistema o ahorro de batería.
const estatico = () => reducido || Boolean(store.get('ahorro'));

const N_PARTICULAS = 350;
const VIDA = 90; // frames por partícula antes de renacer

function bandaVelocidad(kmh) {
  if (!(kmh >= 15)) return 0;
  if (kmh < 30) return 1;
  if (kmh < 50) return 2;
  return 3;
}

/** Color de trazo para una rapidez del viento en km/h según WIND_BANDS. */
export function colorVelocidad(kmh, temaClaro = false) {
  const b = WIND_BANDS[bandaVelocidad(kmh)];
  return temaClaro ? b.lightColor : b.color;
}

/** True si la marca temporal `at` está dentro de ±90 min de `ahoraMs` (viento vigente). */
export function esPasoVigente(at, ahoraMs = Date.now()) {
  const ts = Date.parse(at);
  return Number.isFinite(ts) && Math.abs(ts - ahoraMs) <= VIGENTE_TOL_MS;
}

/** Paso horario de `raw.steps` cuya hora válida `at` está más cerca de `ahoraMs`.
 * Evita presentar el paso +0 h como vigente cuando la grilla tiene varias horas. */
export function pasoMasCercano(raw, ahoraMs = Date.now()) {
  if (!raw || typeof raw !== 'object' || !raw.steps || typeof raw.steps !== 'object') return 0;
  const keys = Object.keys(raw.steps).map(Number).filter((k) => Number.isFinite(k)).sort((a, b) => a - b);
  let mejorPaso = null;
  let mejorDiff = Infinity;
  for (const h of keys) {
    const st = raw.steps[String(h)];
    if (!st || !Array.isArray(st.speed)) continue;
    if (!st.speed.some((v) => v != null && Number.isFinite(v))) continue;
    const ts = Date.parse(st.at);
    if (!Number.isFinite(ts)) continue;
    const diff = Math.abs(ts - ahoraMs);
    if (diff < mejorDiff) {
      mejorDiff = diff;
      mejorPaso = h;
    }
  }
  if (mejorPaso !== null) return mejorPaso;
  return keys.includes(0) ? 0 : (keys[0] ?? 0);
}

/** Etiqueta para la leyenda en hora de Chile continental; solo dice «Ahora» si es vigente. */
export function etiquetaPasoViento(paso, at, ahoraMs = Date.now()) {
  const hora = at ? fmtTime(at) : '—';
  if (hora !== '—') {
    return esPasoVigente(at, ahoraMs) ? `Ahora (${hora})` : `${hora} (Chile)`;
  }
  return paso ? `+${paso} h` : '+0 h';
}

/** Etiqueta compacta para los botones del selector horario (cabe a 320 px). */
export function etiquetaBotonPaso(paso, at, ahoraMs = Date.now()) {
  const hora = at ? fmtTime(at) : '—';
  if (hora !== '—') {
    return esPasoVigente(at, ahoraMs) ? 'Ahora' : hora;
  }
  return paso ? `+${paso} h` : '+0 h';
}

function seleccionarPaso(bloque, paso) {
  if (bloque.steps && typeof bloque.steps === 'object') {
    const st = bloque.steps[String(paso)];
    if (st && Array.isArray(st.speed) && Array.isArray(st.dir)) return st;
    if (paso === 0 && Array.isArray(bloque.speed) && Array.isArray(bloque.dir)) return bloque;
    return null;
  }
  if (Array.isArray(bloque.speed) && Array.isArray(bloque.dir)) return bloque;
  return null;
}

function construirRegular(bloque, paso, fuente) {
  if (!bloque || typeof bloque !== 'object') return null;
  const { step, lat0, lon0, rows, cols } = bloque;
  if (
    !Number.isFinite(step) || step <= 0
    || !Number.isFinite(lat0) || !Number.isFinite(lon0)
    || !Number.isInteger(rows) || rows <= 0
    || !Number.isInteger(cols) || cols <= 0
  ) return null;
  const capa = seleccionarPaso(bloque, paso);
  if (!capa) return null;
  const speeds = capa.speed;
  const dirs = capa.dir;
  const gusts = Array.isArray(capa.gust) ? capa.gust : null;
  const n = rows * cols;
  const u = new Float32Array(n);
  const v = new Float32Array(n);
  const gust = new Float32Array(n);
  let rafagaMax = -Infinity;
  for (let i = 0; i < n; i += 1) {
    const spd = speeds[i];
    const dir = dirs[i];
    if (spd == null || dir == null || !Number.isFinite(spd) || !Number.isFinite(dir)) {
      u[i] = NaN;
      v[i] = NaN;
      gust[i] = NaN;
      continue;
    }
    // Convención meteorológica: `dir` es DE DÓNDE viene; sopla HACIA `dir + 180°`.
    const radTo = ((dir + 180) * Math.PI) / 180;
    u[i] = spd * Math.sin(radTo);
    v[i] = spd * Math.cos(radTo);
    const g = gusts?.[i];
    if (g != null && Number.isFinite(g)) {
      gust[i] = g;
      if (g > rafagaMax) rafagaMax = g;
    } else {
      gust[i] = NaN;
    }
  }
  return {
    step,
    lat0,
    lon0,
    rows,
    cols,
    bbox: Array.isArray(bloque.bbox) ? bloque.bbox : null,
    u,
    v,
    gust,
    at: capa.at || null,
    rafagaMax: rafagaMax > -Infinity ? rafagaMax : null,
    fuente,
  };
}

/** Precalcula vectores (u, v) y ráfagas en O(N) para muestreo bilineal O(1). */
export function prepararGrilla(raw, paso = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const pasosRaw = raw.steps && typeof raw.steps === 'object'
    ? Object.keys(raw.steps).map(Number).filter((k) => Number.isFinite(k)).sort((a, b) => a - b)
    : [];
  const pasos = pasosRaw.length ? pasosRaw : [0];
  const pedido = Number(paso);
  const pasoActivo = pasos.includes(pedido) ? pedido : (pasos.includes(0) ? 0 : pasos[0]);
  const base = construirRegular(raw, pasoActivo, 'base');
  const fine = raw.fine ? construirRegular(raw.fine, pasoActivo, 'fine') : null;
  let legado = null;
  let rafagaLegado = null;
  if (!base && Array.isArray(raw.points) && Array.isArray(raw.speed) && Array.isArray(raw.dir)) {
    const gusts = Array.isArray(raw.gust) ? raw.gust : null;
    if (gusts) {
      let mx = -Infinity;
      for (let i = 0; i < gusts.length; i += 1) {
        if (gusts[i] != null && Number.isFinite(gusts[i]) && gusts[i] > mx) mx = gusts[i];
      }
      if (mx > -Infinity) rafagaLegado = mx;
    }
    legado = { points: raw.points, speed: raw.speed, dir: raw.dir, gust: gusts };
  }
  const rafagas = [fine?.rafagaMax, base?.rafagaMax, rafagaLegado].filter((x) => x != null && Number.isFinite(x));
  const pasosAt = {};
  if (raw.steps && typeof raw.steps === 'object') {
    for (const h of pasos) {
      const at = raw.fine?.steps?.[String(h)]?.at || raw.steps[String(h)]?.at || null;
      if (at) pasosAt[String(h)] = at;
    }
  } else if (raw.computed_at) {
    pasosAt['0'] = raw.computed_at;
  }
  return {
    base,
    fine,
    legado,
    pasoHora: pasoActivo,
    pasos,
    pasosAt,
    at: fine?.at || base?.at || pasosAt[String(pasoActivo)] || raw.computed_at || null,
    computed_at: raw.computed_at || null,
    source: raw.source || null,
    rafagaMaxKmh: rafagas.length ? Math.max(...rafagas) : null,
  };
}

function rotarVector(u, v, bearing, speed, gust, fuente) {
  const radB = (bearing * Math.PI) / 180;
  const cosB = Math.cos(radB);
  const sinB = Math.sin(radB);
  // Identidad exacta de sin(θ − β) y −cos(θ − β) sobre componentes (u, v).
  const vxKmh = u * cosB - v * sinB;
  const vyKmh = -(u * sinB + v * cosB);
  return { vx: vxKmh / 30, vy: vyKmh / 30, speed, gust, u, v, fuente };
}

/** Muestreo O(1) con interpolación bilineal sobre una grilla regular precalculada. */
export function interpolarEnGrilla(reg, lon, lat, bearing = 0) {
  if (!reg || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  const frRaw = (lat - reg.lat0) / reg.step;
  const fcRaw = (lon - reg.lon0) / reg.step;
  // La grilla base (1°, centros en .5) cubre media celda hacia el borde (±0,5°, y hasta 1°
  // al norte para incluir Visviri/General Lagos en -17,6°); la fina mantiene borde acotado
  // para caer limpiamente al 1° fuera de su bbox.
  const esBase = reg.fuente === 'base' && reg.step >= 0.5;
  const tolSurOesteEste = esBase ? 0.5 : 0.25;
  const tolNorte = esBase ? 1.0 : 0.25;
  if (
    frRaw < -tolSurOesteEste
    || frRaw > reg.rows - 1 + tolNorte
    || fcRaw < -tolSurOesteEste
    || fcRaw > reg.cols - 1 + tolSurOesteEste
  ) return null;
  const fr = Math.max(0, Math.min(reg.rows - 1, frRaw));
  const fc = Math.max(0, Math.min(reg.cols - 1, fcRaw));
  const r0 = Math.floor(fr);
  const c0 = Math.floor(fc);
  const r1 = Math.min(reg.rows - 1, r0 + 1);
  const c1 = Math.min(reg.cols - 1, c0 + 1);
  const dy = fr - r0;
  const dx = fc - c0;
  const cols = reg.cols;
  const i00 = r0 * cols + c0;
  const i01 = r0 * cols + c1;
  const i10 = r1 * cols + c0;
  const i11 = r1 * cols + c1;
  const w00 = (1 - dy) * (1 - dx);
  const w01 = (1 - dy) * dx;
  const w10 = dy * (1 - dx);
  const w11 = dy * dx;

  let su = 0;
  let sv = 0;
  let sw = 0;
  let sg = 0;
  let swg = 0;
  if (!Number.isNaN(reg.u[i00])) {
    su += reg.u[i00] * w00; sv += reg.v[i00] * w00; sw += w00;
    if (!Number.isNaN(reg.gust[i00])) { sg += reg.gust[i00] * w00; swg += w00; }
  }
  if (!Number.isNaN(reg.u[i01])) {
    su += reg.u[i01] * w01; sv += reg.v[i01] * w01; sw += w01;
    if (!Number.isNaN(reg.gust[i01])) { sg += reg.gust[i01] * w01; swg += w01; }
  }
  if (!Number.isNaN(reg.u[i10])) {
    su += reg.u[i10] * w10; sv += reg.v[i10] * w10; sw += w10;
    if (!Number.isNaN(reg.gust[i10])) { sg += reg.gust[i10] * w10; swg += w10; }
  }
  if (!Number.isNaN(reg.u[i11])) {
    su += reg.u[i11] * w11; sv += reg.v[i11] * w11; sw += w11;
    if (!Number.isNaN(reg.gust[i11])) { sg += reg.gust[i11] * w11; swg += w11; }
  }
  if (sw <= 0) return null;
  const u = su / sw;
  const v = sv / sw;
  const gust = swg > 0 ? sg / swg : null;
  const speed = Math.hypot(u, v);
  return rotarVector(u, v, bearing, speed, gust, reg.fuente);
}

/** Interpola el viento en (lon, lat): prioriza la subgrilla fina 0,25°, cae a la base 1° y,
 *  solo ante payloads legados sin rows/cols, usa respaldo por punto más cercano. */
export function interpolarViento(vistaActiva, lon, lat, bearing = 0) {
  if (!vistaActiva || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (vistaActiva.fine) {
    const fino = interpolarEnGrilla(vistaActiva.fine, lon, lat, bearing);
    if (fino) return fino;
  }
  if (vistaActiva.base) return interpolarEnGrilla(vistaActiva.base, lon, lat, bearing);
  const leg = vistaActiva.legado;
  if (!leg) return null;
  let mejor = -1;
  let dm = Infinity;
  for (let i = 0; i < leg.points.length; i += 1) {
    const [plat, plon] = leg.points[i];
    const d = (plat - lat) ** 2 + (plon - lon) ** 2;
    if (d < dm) { dm = d; mejor = i; }
  }
  if (mejor < 0 || leg.speed[mejor] == null || leg.dir[mejor] == null) return null;
  const speed = leg.speed[mejor];
  const radTo = ((leg.dir[mejor] + 180) * Math.PI) / 180;
  const u = speed * Math.sin(radTo);
  const v = speed * Math.cos(radTo);
  const g = leg.gust?.[mejor];
  const gust = g != null && Number.isFinite(g) ? g : null;
  return rotarVector(u, v, bearing, speed, gust, 'legado');
}

function asegurarCanvas() {
  const map = getMap();
  if (!map) return null;
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:5';
    map.getCanvasContainer().append(canvas);
  }
  const { width, height } = map.getContainer().getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(width));
  canvas.height = Math.max(1, Math.round(height));
  return canvas;
}

function agregarFlecha(cubetas, x, y, vxKmh, vyKmh, speed) {
  const mag = Math.hypot(vxKmh, vyKmh);
  if (mag < 0.1) return;
  const ux = vxKmh / mag;
  const uy = vyKmh / mag;
  const len = 7 + Math.min(15, speed / 3.5);
  const tx = x + ux * len;
  const ty = y + uy * len;
  const head = Math.min(5, len * 0.4);
  const wx1 = tx - (ux * 0.8 + uy * 0.5) * head;
  const wy1 = ty - (uy * 0.8 - ux * 0.5) * head;
  const wx2 = tx - (ux * 0.8 - uy * 0.5) * head;
  const wy2 = ty - (uy * 0.8 + ux * 0.5) * head;
  const segs = cubetas[bandaVelocidad(speed)];
  segs.push(x, y, tx, ty, tx, ty, wx1, wy1, tx, ty, wx2, wy2);
}

function pintarCubetas(ctx, cubetas, lineWidth) {
  const claro = store.get('theme') === 'light';
  ctx.globalCompositeOperation = 'source-over';
  ctx.lineWidth = claro ? Math.max(lineWidth, 2) : lineWidth;
  ctx.lineCap = 'round';
  for (let b = 0; b < cubetas.length; b += 1) {
    const segs = cubetas[b];
    if (!segs.length) continue;
    ctx.strokeStyle = claro ? WIND_BANDS[b].lightColor : WIND_BANDS[b].color;
    ctx.beginPath();
    for (let i = 0; i < segs.length; i += 4) {
      ctx.moveTo(segs[i], segs[i + 1]);
      ctx.lineTo(segs[i + 2], segs[i + 3]);
    }
    ctx.stroke();
  }
}

function dentroDeFina(fine, lon, lat) {
  const latMax = fine.lat0 + (fine.rows - 1) * fine.step;
  const lonMax = fine.lon0 + (fine.cols - 1) * fine.step;
  const tol = fine.step * 0.5;
  return lat >= fine.lat0 - tol && lat <= latMax + tol && lon >= fine.lon0 - tol && lon <= lonMax + tol;
}

function dibujarFlechas(map, cv) {
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (!vista) return;
  const bearing = map.getBearing();
  const radB = (bearing * Math.PI) / 180;
  const cosB = Math.cos(radB);
  const sinB = Math.sin(radB);
  const zoom = typeof map.getZoom === 'function' ? map.getZoom() : 6;
  const cubetas = WIND_BANDS.map(() => []);

  const agregarGrilla = (reg, stride, omitirEnFina) => {
    for (let r = 0; r < reg.rows; r += stride) {
      const lat = reg.lat0 + r * reg.step;
      for (let c = 0; c < reg.cols; c += stride) {
        const lon = reg.lon0 + c * reg.step;
        if (omitirEnFina && vista.fine && dentroDeFina(vista.fine, lon, lat)) continue;
        const idx = r * reg.cols + c;
        const u = reg.u[idx];
        if (Number.isNaN(u)) continue;
        const v = reg.v[idx];
        const { x, y } = map.project([lon, lat]);
        if (x < -16 || y < -16 || x > cv.width + 16 || y > cv.height + 16) continue;
        const vxKmh = u * cosB - v * sinB;
        const vyKmh = -(u * sinB + v * cosB);
        agregarFlecha(cubetas, x, y, vxKmh, vyKmh, Math.hypot(u, v));
      }
    }
  };

  if (vista.fine) {
    const stride = zoom < 6 ? 3 : (zoom < 7.5 ? 2 : 1);
    agregarGrilla(vista.fine, stride, false);
  }
  if (vista.base) {
    agregarGrilla(vista.base, 1, Boolean(vista.fine));
  } else if (vista.legado) {
    const leg = vista.legado;
    for (let i = 0; i < leg.points.length; i += 1) {
      const [plat, plon] = leg.points[i];
      if (leg.speed[i] == null || leg.dir[i] == null) continue;
      const { x, y } = map.project([plon, plat]);
      if (x < -16 || y < -16 || x > cv.width + 16 || y > cv.height + 16) continue;
      const radTo = ((leg.dir[i] + 180) * Math.PI) / 180;
      const u = leg.speed[i] * Math.sin(radTo);
      const v = leg.speed[i] * Math.cos(radTo);
      agregarFlecha(cubetas, x, y, u * cosB - v * sinB, -(u * sinB + v * cosB), leg.speed[i]);
    }
  }
  pintarCubetas(ctx, cubetas, 1.5);
}

function animar(map, cv) {
  const ctx = cv.getContext('2d');
  const partes = Array.from({ length: N_PARTICULAS }, () => ({
    x: Math.random() * cv.width, y: Math.random() * cv.height, vida: Math.random() * VIDA,
  }));
  // Cuatro cubetas reutilizables por banda de color: máximo 4 ctx.stroke() por cuadro.
  const cubetas = WIND_BANDS.map(() => []);
  const paso = () => {
    if (!corriendo || document.hidden || !vista) { raf = 0; return; }
    // Estela: cada cuadro apaga un poco lo ya dibujado en vez de borrarlo, y la
    // partícula deja un trazo que dice hacia dónde y cuán rápido sopla.
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0,0,0,.08)';
    ctx.fillRect(0, 0, cv.width, cv.height);
    const bearing = map.getBearing();
    for (let b = 0; b < cubetas.length; b += 1) cubetas[b].length = 0;
    for (let i = 0; i < partes.length; i += 1) {
      const p = partes[i];
      const ll = map.unproject([p.x, p.y]);
      const v = interpolarViento(vista, ll.lng, ll.lat, bearing);
      if (v && (v.vx || v.vy)) {
        const nx = p.x + v.vx * 3;
        const ny = p.y + v.vy * 3;
        cubetas[bandaVelocidad(v.speed)].push(p.x, p.y, nx, ny);
        p.x = nx;
        p.y = ny;
        p.vida -= 1;
      } else {
        p.vida -= 5;
      }
      if (p.vida <= 0 || p.x < 0 || p.y < 0 || p.x > cv.width || p.y > cv.height) {
        p.x = Math.random() * cv.width;
        p.y = Math.random() * cv.height;
        p.vida = VIDA;
      }
    }
    pintarCubetas(ctx, cubetas, 1.4);
    raf = requestAnimationFrame(paso);
  };
  if (!raf) raf = requestAnimationFrame(paso);
}

// Al mover el mapa las estelas (píxeles de pantalla) ya no calzan con el terreno: se
// borran; las flechas fijas del modo sin movimiento se vuelven a colocar.
function alMover() {
  if (!corriendo || !canvas) return;
  if (estatico()) dibujarFlechas(getMap(), canvas);
  else canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
}

function alRedimensionar() {
  if (!corriendo || !canvas) return;
  const cv = asegurarCanvas();
  if (cv && estatico()) dibujarFlechas(getMap(), cv);
}

/** Minutos desde `computed_at` de la grilla cargada; null si aún no hay. */
export function edadGrillaMin() {
  if (!grid?.computed_at) return null;
  return Math.max(0, (Date.now() - Date.parse(grid.computed_at)) / 60000);
}

/** Horizonte horario activo (0, 3, 6 o 12 h). */
export function getPasoHora() {
  return vista ? vista.pasoHora : pasoHora;
}

/** Pasos horarios disponibles en la grilla cargada. */
export function pasosDisponibles() {
  return vista ? [...vista.pasos] : [...PASOS_HORA];
}

/** Metadatos del paso activo para la leyenda y los controles de la vista. */
export function infoVientoActivo() {
  return {
    pasoHora: getPasoHora(),
    at: vista?.at || null,
    pasos: vista ? [...vista.pasos] : [],
    pasosAt: vista?.pasosAt ? { ...vista.pasosAt } : {},
    tieneFina: Boolean(vista?.fine),
    fuente: vista?.source || grid?.source || null,
    rafagaMaxKmh: vista?.rafagaMaxKmh ?? null,
  };
}

/** Cambia el horizonte horario en caliente sin volver a pedir la grilla al servidor. */
export function setPasoHora(h) {
  const n = Number(h);
  if (!Number.isFinite(n)) return getPasoHora();
  pasoHora = n;
  pasoElegidoPorUsuario = true;
  if (grid) {
    vista = prepararGrilla(grid, pasoHora);
    pasoHora = vista ? vista.pasoHora : 0;
    const map = getMap();
    if (corriendo && canvas && map) {
      if (estatico()) dibujarFlechas(map, canvas);
      else canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    }
  }
  return getPasoHora();
}

async function cargar() {
  if (grid) return grid;
  const res = await fetch('/api/wind/grid');
  if (res.status === 404) throw new Error('sin grilla'); // 404 honesto: aún no la calcula el ciclo
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  grid = await res.json();
  return grid;
}

/** Enciende la capa: carga la grilla y arranca el canvas sobre el mapa.
 * Devuelve 'ok' o 'vieja' (grilla con más de FRESCA_MAX_H: no se anima; la leyenda
 * muestra la edad). Lanza si no hay grilla o no hay mapa. */
export async function encender() {
  await cargar();
  if (!pasoElegidoPorUsuario) pasoHora = pasoMasCercano(grid);
  vista = prepararGrilla(grid, pasoHora);
  pasoHora = vista ? vista.pasoHora : 0;
  // PERF-15: se pide y espera el motor aunque la vista ya esté pintada.
  const { ensureMap } = await import('./app.js');
  await ensureMap();
  const map = getMap();
  if (!map || !grid || !vista) throw new Error('sin mapa');
  const edad = edadGrillaMin();
  if (edad !== null && edad > FRESCA_MAX_H * 60) return 'vieja';
  corriendo = true;
  const cv = asegurarCanvas();
  if (!cv) return 'ok';
  map.off('move', alMover);
  map.on('move', alMover);
  map.off('resize', alRedimensionar);
  map.on('resize', alRedimensionar);
  if (estatico()) dibujarFlechas(map, cv);
  else animar(map, cv);
  return 'ok';
}

/** Apaga la capa: detiene el RAF y borra el canvas. */
export function apagar() {
  corriendo = false;
  pasoElegidoPorUsuario = false;
  const map = getMap();
  map?.off('move', alMover);
  map?.off('resize', alRedimensionar);
  grid = null;
  vista = null;
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  canvas?.remove();
  canvas = null;
}

function actualizarModoMovimiento() {
  const map = getMap();
  if (!corriendo || !canvas || !map || !vista) return;
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  if (estatico()) dibujarFlechas(map, canvas);
  else animar(map, canvas);
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    const map = getMap();
    if (!corriendo || !canvas || !map || !vista) return;
    if (document.hidden && raf) { cancelAnimationFrame(raf); raf = 0; }
    else if (!document.hidden && !raf && !estatico()) animar(map, canvas);
  });
}

mqlReducido?.addEventListener?.('change', (e) => {
  reducido = Boolean(e.matches);
  actualizarModoMovimiento();
});

// El interruptor de ahorro cambia el viento en caliente: animación ↔ flechas fijas.
store.on('ahorro', actualizarModoMovimiento);

// Al alternar tema claro/oscuro, las flechas estáticas se repintan con la paleta adecuada.
store.on('theme', () => {
  const map = getMap();
  if (!corriendo || !canvas || !map || !vista) return;
  if (estatico()) dibujarFlechas(map, canvas);
});
