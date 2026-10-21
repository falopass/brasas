/* UX-18: puntaje de «Mi casa preparada» en el dispositivo, sin servidor.
 * El cálculo vive en ./lista-score.js (módulo puro, probado en tests/js);
 * aquí solo se enlazan las casillas, el localStorage y la impresión. Ambos
 * módulos van en el SHELL del service worker, así que el puntaje también
 * funciona sin conexión; si algo falla, la hoja queda como siempre:
 * casillas marcables a mano. */
import { ITEMS, puntajeCasa } from './lista-score.js';

const CLAVE = 'brasa:casa-preparada';
const lee = () => {
  try {
    const v = JSON.parse(localStorage.getItem(CLAVE));
    return v && typeof v === 'object' ? v : {};
  } catch { return {}; }
};
const guarda = (estado) => {
  try { localStorage.setItem(CLAVE, JSON.stringify(estado)); }
  catch { /* localStorage bloqueado (modo privado): el puntaje se recalcula igual */ }
};
const casillas = ITEMS.map(([k]) => document.getElementById(`casa-${k}`));
const pinta = () => {
  const estado = lee();
  casillas.forEach((c, i) => { c.checked = estado[ITEMS[i][0]] === true; });
  const r = puntajeCasa(estado);
  document.getElementById('casa-score').hidden = false;
  document.getElementById('casa-score-num').textContent = `${r.puntaje}/100`;
  document.getElementById('casa-score-nivel').textContent = r.nivel;
  document.getElementById('casa-score-next').textContent = r.siguiente
    ? `Lo que falta primero: ${r.siguiente.accion}.`
    : 'Todo listo: repásalo antes de cada temporada.';
};
casillas.forEach((c, i) => c?.addEventListener('change', () => {
  const estado = lee();
  estado[ITEMS[i][0]] = c.checked;
  guarda(estado);
  pinta();
}));
document.getElementById('casa-score-reset')?.addEventListener('click', () => {
  guarda({});
  casillas.forEach((c) => { c.checked = false; });
  pinta();
});
pinta();

/* Marca de generación de la hoja imprimible (FIX-35): el papel pegado en el
 * refrigerador debe decir de cuándo es; si no, una hoja de la temporada pasada
 * parece vigente. Si el script no corre, el renglón queda en blanco para
 * escribir la fecha a mano. */
export const fechaGeneracion = (now = new Date()) =>
  now.toLocaleString('es-CL', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Santiago',
  });

const marcaGeneracion = document.getElementById('generada');
if (marcaGeneracion) marcaGeneracion.textContent = fechaGeneracion();
