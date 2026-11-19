/** Fallos del proxy del contenedor que significan «está arrancando», no un error de la app. */
const MARCAS_ARRANQUE = [
  'is not running',
  'not listening',
  'failed to start container',
  'suddenly disconnected',
  'error proxying request to container',
];

export function esFalloDeArranqueDelContenedor(body: string): boolean {
  const texto = body.toLowerCase();
  return texto.includes('container') && MARCAS_ARRANQUE.some((marca) => texto.includes(marca));
}
