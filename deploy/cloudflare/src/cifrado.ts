/** Cifrado en reposo del respaldo (SEC-06): AES-256-GCM con WebCrypto sobre las claves db/*.
 *  La clave llega en el secreto DB_ENC_KEY del Worker (base64, 32 bytes). Funciones puras, sin
 *  bindings: las pruebas las importan directo con `node --test` (index.ts carga @cloudflare/containers).
 *  Formato del objeto: cabecera BRASA1 (6 B) + IV aleatorio (12 B) + ciphertext con tag GCM.
 *  Lo que no empieza con BRASA1 se lee tal cual: los respaldos anteriores al cifrado siguen sirviendo. */

const MAGIA = new TextEncoder().encode('BRASA1');
const IV_BYTES = 12;

/** Decodifica DB_ENC_KEY. Null si falta, no es base64 o no son 32 bytes. */
export function bytesDeClave(secreto: string | undefined): Uint8Array | null {
  if (!secreto) return null;
  try {
    const bytes = Uint8Array.from(atob(secreto), (c) => c.charCodeAt(0));
    return bytes.byteLength === 32 ? bytes : null;
  } catch {
    return null;
  }
}

/** True si el objeto ya viene cifrado con este formato. */
export function estaCifrado(datos: Uint8Array): boolean {
  return MAGIA.every((b, i) => datos[i] === b);
}

/** Cifra con un IV nuevo en cada llamada: BRASA1 + IV + ciphertext. */
export async function cifrarRespaldo(clave: Uint8Array, datos: ArrayBuffer | Uint8Array): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey('raw', clave as BufferSource, 'AES-GCM', false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const cuerpo = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, datos));
  const out = new Uint8Array(MAGIA.length + IV_BYTES + cuerpo.length);
  out.set(MAGIA);
  out.set(iv, MAGIA.length);
  out.set(cuerpo, MAGIA.length + IV_BYTES);
  return out;
}

/** Devuelve el plaintext si el objeto lleva cabecera BRASA1; si no, los bytes tal cual.
 *  Sin clave válida y con objeto cifrado, lanza (el llamador responde 500). */
export async function descifrarRespaldo(clave: Uint8Array | null, datos: ArrayBuffer): Promise<ArrayBuffer> {
  const bytes = new Uint8Array(datos);
  if (!estaCifrado(bytes)) return datos;
  if (!clave) throw new Error('objeto cifrado y DB_ENC_KEY ausente o inválida');
  const key = await crypto.subtle.importKey('raw', clave as BufferSource, 'AES-GCM', false, ['decrypt']);
  return crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: bytes.subarray(MAGIA.length, MAGIA.length + IV_BYTES) },
    key,
    bytes.subarray(MAGIA.length + IV_BYTES),
  );
}
