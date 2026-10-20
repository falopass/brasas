/* Foto del reporte reducida en el teléfono antes de subirla: en una conexión rural,
 * un archivo de varios MB tarda minutos o el servidor lo rechaza (máximo 8 MB).
 * Funciones puras; la parte que decodifica y usa canvas vive en ui.js. */
export const FOTO_MAX_SIDE = 1600;             // igual que MAX_SIDE en backend/reports.py
export const FOTO_MAX_BYTES = 8 * 1024 * 1024; // igual que MAX_UPLOAD_BYTES
const SHRINK_BYTES = 1_500_000;

export function fitDimensions(width, height, maxSide = FOTO_MAX_SIDE) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0 || maxSide <= 0) return null;
  const scale = Math.min(1, maxSide / Math.max(width, height)); // nunca amplía
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

export function shouldShrink(file, maxBytes = SHRINK_BYTES) {
  return typeof file?.type === 'string' && file.type.startsWith('image/') && file.size > maxBytes;
}
