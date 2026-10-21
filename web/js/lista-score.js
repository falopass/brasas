/* Autoevaluación «Mi casa preparada» de la hoja imprimible (UX-18).
 * Módulo puro, sin DOM ni imports: recibe el estado de las nueve casillas de
 * lista.html ({techo: true, franja: false, …}) y devuelve el puntaje. El DOM
 * y el localStorage los resuelve el <script type="module"> de la propia página,
 * porque lista.html se precarga en el service worker y no puede arrastrar más
 * módulos que el suyo. */

/* Tabla de pesos (CONT-05): la guía oficial trata como críticos la franja sin
 * material que arda, la leña y los combustibles lejos de la casa y el acceso
 * despejado para vehículos de emergencia; pesan el triple que el resto. */
export const ITEMS = [
  ['techo', 'Limpiar el techo y las canaletas de hojas, ramas y basura seca', 1],
  ['franja', 'Dejar una franja de al menos 1,5 m sin material que arda alrededor de la casa', 3],
  ['ramas', 'Podar las ramas cerca del techo y las ramas bajas de los árboles', 1],
  ['pasto', 'Cortar el pasto seco y retirar matorrales', 1],
  ['combustibles', 'Guardar la leña, el gas y los combustibles lejos de la casa', 3],
  ['cercos', 'Revisar cercos y bodegas de madera pegados a la vivienda', 1],
  ['manguera', 'Tener manguera que alcance todo el perímetro y una fuente de agua', 1],
  ['acceso', 'Despejar el acceso para vehículos de emergencia y hacer visible el número', 3],
  ['vecinos', 'Conversar con los vecinos cómo avisarse y ayudarse', 1],
];

const TOTAL = ITEMS.reduce((suma, [, , peso]) => suma + peso, 0);

/* estado → {puntaje, nivel, faltan, siguiente}. `nivel` siempre en palabras:
 * «Falta lo importante» (<50), «Vas bien» (50-99) o «Casa preparada» (100).
 * `faltan` son los ítems pendientes de mayor a menor peso (empate: orden de la
 * guía) y `siguiente` el primero de ellos, o null si no falta nada. */
export function puntajeCasa(estado) {
  const marcado = estado && typeof estado === 'object' ? estado : {};
  let suma = 0;
  const faltan = [];
  for (const [key, accion, peso] of ITEMS) {
    if (marcado[key] === true) suma += peso;
    else faltan.push({ key, accion, peso });
  }
  faltan.sort((a, b) => b.peso - a.peso);
  const puntaje = Math.round((100 * suma) / TOTAL);
  const nivel = puntaje >= 100 ? 'Casa preparada' : puntaje >= 50 ? 'Vas bien' : 'Falta lo importante';
  return { puntaje, nivel, faltan, siguiente: faltan[0] ?? null };
}
