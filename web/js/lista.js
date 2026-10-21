/* UX-18: puntaje de «Mi casa preparada» en el dispositivo, sin servidor.
 * El cálculo vive en /web/js/lista-score.js (módulo puro, probado en
 * tests/js); aquí solo se enlazan las casillas, el localStorage y la
 * impresión. Ambos módulos van en el precache (SHELL de web/sw.js); si no
 * cargan, la hoja queda como siempre: casillas marcables a mano. */
import { ITEMS, puntajeCasa } from "/web/js/lista-score.js";

const CLAVE = "brasa:casa-preparada";
const lee = () => {
  try {
    const v = JSON.parse(localStorage.getItem(CLAVE));
    return v && typeof v === "object" ? v : {};
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
  document.getElementById("casa-score").hidden = false;
  document.getElementById("casa-score-num").textContent = `${r.puntaje}/100`;
  document.getElementById("casa-score-nivel").textContent = r.nivel;
  document.getElementById("casa-score-next").textContent = r.siguiente
    ? `Lo que falta primero: ${r.siguiente.accion}.`
    : "Todo listo: repásalo antes de cada temporada.";
};
casillas.forEach((c, i) => c?.addEventListener("change", () => {
  const estado = lee();
  estado[ITEMS[i][0]] = c.checked;
  guarda(estado);
  pinta();
}));
document.getElementById("casa-score-reset")?.addEventListener("click", () => {
  guarda({});
  casillas.forEach((c) => { c.checked = false; });
  pinta();
});
pinta();
