/* Reducción de la foto de un reporte en el teléfono, antes de subirla (FIX-56).
   En una conexión rural un archivo de varios MB tarda minutos y el servidor lo
   rechaza sobre 8 MB (backend/reports.py); bajarla aquí evita las dos cosas.
   Funciones puras, sin DOM ni imports: las pruebas corren en node:test. */

/** Dimensiones proporcionales con el lado mayor acotado a `maxSide`; nunca amplía.
 *  Devuelve null con valores no utilizables (0, negativos, NaN). */
export function fitDimensions(width, height, maxSide = 1600) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  if (!Number.isFinite(maxSide) || maxSide <= 0) return null;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** Conviene reducir si es una imagen que pesa más de `maxBytes`.
 *  `file` basta con que tenga { size, type } (File del navegador o similar). */
export function shouldShrink(file, maxBytes = 1_500_000) {
  return Boolean(file)
    && typeof file.type === 'string' && file.type.startsWith('image/')
    && Number.isFinite(file.size) && file.size > maxBytes;
}
