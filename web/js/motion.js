/* Movimiento de BRASA. Cada animación responde a algo real:
 *  - entrada de una vista: sus partes llegan en orden de lectura, una sola vez por navegación;
 *  - cifras: cuentan hasta su valor al aparecer (no durante la reproducción de un caso);
 *  - barrido: cuando llegan datos nuevos, una pasada norte→sur cruza el mapa, como escanea GOES.
 * Con «reducir movimiento» activado nada de esto corre y el contenido aparece tal cual. */

export const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

let enterUntil = 0;

/** Abre una ventana breve en la que el próximo render de la vista se anima (tras navegar). */
export function armEnter(ms = 4000) { enterUntil = performance.now() + ms; }

function choreograph(root) {
  const parts = [...root.children].filter((el) => el.nodeType === 1);
  parts.forEach((el, i) => { el.style.setProperty('--i', String(Math.min(i, 9))); el.classList.add('enter'); });
  setTimeout(() => parts.forEach((el) => el.classList.remove('enter')), 1600);
}

const NUM = /^(\d{1,3}(?:\.\d{3})*|\d+)(,\d+)?(\s?\D.*)?$/;
function countUp(el) {
  const text = el.textContent.trim();
  const m = text.match(NUM);
  if (!m) return;
  const target = Number(m[1].replace(/\./g, '') + (m[2] ? `.${m[2].slice(1)}` : ''));
  if (!Number.isFinite(target) || target < 2) return;
  const digits = m[2] ? m[2].length - 1 : 0;
  const suffix = m[3] || '';
  const fmt = new Intl.NumberFormat('es-CL', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const t0 = performance.now(); const dur = Math.min(1100, 500 + target * 4);
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / dur);
    const eased = 1 - (1 - p) ** 4;
    el.textContent = fmt.format(target * eased) + suffix;
    if (p < 1 && el.isConnected) requestAnimationFrame(tick);
    else el.textContent = text;
  };
  requestAnimationFrame(tick);
}

/** Observa el contenedor de vistas: anima lo que entra mientras la ventana de entrada está abierta. */
export function watchView(container) {
  new MutationObserver(() => {
    if (reduced() || performance.now() > enterUntil) return;
    if (container.querySelector('.view-title')?.textContent.startsWith('Cargando')) return;
    enterUntil = 0;
    choreograph(container);
    container.querySelectorAll('[data-count], .kpi strong, .hero-figure').forEach(countUp);
  }).observe(container, { childList: true });
}

/** La pasada del satélite sobre el mapa. */
export function scanPass() {
  const el = document.getElementById('scan');
  if (!el || reduced()) return;
  el.classList.remove('run');
  void el.offsetWidth; // reinicia la animación
  el.classList.add('run');
}
