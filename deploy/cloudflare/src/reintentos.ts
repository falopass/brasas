/** Registro acotado del último intento de revalidación por clave: evita que cada visita a una
 *  copia vencida golpee al contenedor caído, sin crecer para siempre (los parámetros de las URL
 *  lo multiplican). Lleno, expulsa la más vieja: solo se pierde el freno, no la corrección.
 *  Solo sintaxis de tipos borrable — la prueba lo importa directo con `node --test`. */

export const REINTENTOS_MAX = 500;

export function recuerdaIntento(map: Map<string, number>, name: string, nowMs: number): void {
  if (map.size >= REINTENTOS_MAX && !map.has(name)) map.delete(map.keys().next().value!);
  map.set(name, nowMs);
}
