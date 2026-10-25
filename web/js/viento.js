/* RISK-07: partículas de viento a 10 m sobre el mapa, en canvas propio (sin dependencias).
 * La grilla la precalcula el backend (GET /api/wind/grid, cada 6 h): ninguna visita llama
 * a Open-Meteo. Se pausa con la pestaña oculta o la capa apagada; con
 * prefers-reduced-motion o el modo ahorro (UX-76) se dibujan flechas estáticas. */
import { getMap, onReady } from './map.js';
import { store } from './store.js';

let grid = null;
let canvas = null;
let raf = 0;
let corriendo = false;
const REDUCIDO = matchMedia('(prefers-reduced-motion: reduce)').matches;
// Flechas fijas en vez de animación: movimiento reducido del sistema o ahorro de batería.
const estatico = () => REDUCIDO || Boolean(store.get('ahorro'));

const N_PARTICULAS = 350;
const VIDA = 90; // frames por partícula antes de renacer

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

/* El mapa se puede rotar (dragRotate): el ángulo geográfico en pantalla es dir - bearing.
 * Con bearing 90° el norte geográfico apunta a la izquierda de la pantalla, así que el
 * ángulo en pantalla es (dir + 180 - bearing): un viento hacia el norte dibuja arriba
 * solo con bearing 0. */
function vientoEn(lon, lat, bearing) {
  if (!grid) return null;
  let mejor = null, dm = Infinity;
  for (let i = 0; i < grid.points.length; i += 1) {
    const [plat, plon] = grid.points[i];
    const d = (plat - lat) ** 2 + (plon - lon) ** 2;
    if (d < dm) { dm = d; mejor = i; }
  }
  if (mejor === null || grid.speed[mejor] == null || grid.dir[mejor] == null) return null;
  // wind_direction_10m es DE DÓNDE viene: la partícula viaja hacia dir + 180°, rotada
  // por el bearing del mapa.
  const rad = ((grid.dir[mejor] + 180 - bearing) * Math.PI) / 180;
  return { vx: Math.sin(rad) * (grid.speed[mejor] / 30), vy: -Math.cos(rad) * (grid.speed[mejor] / 30) };
}

function dibujarFlechas(map, cv) {
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.strokeStyle = '#5aa0d8';
  ctx.lineWidth = 1.5;
  for (let i = 0; i < grid.points.length; i += 1) {
    const [plat, plon] = grid.points[i];
    if (grid.speed[i] == null || grid.dir[i] == null) continue;
    const { x, y } = map.project([plon, plat]);
    if (x < 0 || y < 0 || x > cv.width || y > cv.height) continue;
    const rad = ((grid.dir[i] + 180 - map.getBearing()) * Math.PI) / 180;
    const len = 6 + Math.min(14, grid.speed[i] / 4);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.sin(rad) * len, y - Math.cos(rad) * len);
    ctx.stroke();
  }
}

function animar(map, cv) {
  const ctx = cv.getContext('2d');
  const partes = Array.from({ length: N_PARTICULAS }, () => ({
    x: Math.random() * cv.width, y: Math.random() * cv.height, vida: Math.random() * VIDA,
  }));
  const paso = () => {
    if (!corriendo || document.hidden) { raf = 0; return; }
    ctx.fillStyle = 'rgba(0,0,0,0)';
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.strokeStyle = 'rgba(90,160,216,0.75)';
    ctx.lineWidth = 1;
    for (const p of partes) {
      const ll = map.unproject([p.x, p.y]);
      const v = vientoEn(ll.lng, ll.lat, map.getBearing()) || { vx: 0, vy: 0 };
      const nx = p.x + v.vx * 3;
      const ny = p.y + v.vy * 3;
      if (v.vx || v.vy) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(nx, ny); ctx.stroke(); }
      p.x = nx; p.y = ny; p.vida -= 1;
      if (p.vida <= 0 || p.x < 0 || p.y < 0 || p.x > cv.width || p.y > cv.height) {
        p.x = Math.random() * cv.width; p.y = Math.random() * cv.height; p.vida = VIDA;
      }
    }
    raf = requestAnimationFrame(paso);
  };
  if (!raf) raf = requestAnimationFrame(paso);
}

export const FRESCA_MAX_H = 12;

/** Minutos desde `computed_at` de la grilla cargada; null si aún no hay. */
export function edadGrillaMin() {
  if (!grid?.computed_at) return null;
  return Math.max(0, (Date.now() - Date.parse(grid.computed_at)) / 60000);
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
  const map = getMap();
  if (!map || !grid) throw new Error('sin mapa');
  const edad = edadGrillaMin();
  if (edad !== null && edad > FRESCA_MAX_H * 60) return 'vieja';
  corriendo = true;
  const cv = asegurarCanvas();
  if (!cv) return 'ok';
  if (estatico()) dibujarFlechas(map, cv);
  else animar(map, cv);
  return 'ok';
}

/** Apaga la capa: detiene el RAF y borra el canvas (la grilla queda cacheada). */
export function apagar() {
  corriendo = false;
  grid = null;
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  canvas?.remove();
  canvas = null;
}

document.addEventListener('visibilitychange', () => {
  const map = getMap();
  if (!corriendo || !canvas || !map || !grid) return;
  if (document.hidden && raf) { cancelAnimationFrame(raf); raf = 0; }
  else if (!document.hidden && !raf && !estatico()) animar(map, canvas);
});

// El interruptor de ahorro cambia el viento en caliente: animación ↔ flechas fijas.
store.on('ahorro', () => {
  const map = getMap();
  if (!corriendo || !canvas || !map || !grid) return;
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  if (estatico()) dibujarFlechas(map, canvas);
  else animar(map, canvas);
});
