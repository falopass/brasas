// Descifra un respaldo db/* de BRASA en su propio archivo.
// Formato (deploy/cloudflare/src/cifrado.ts, SEC-06): cabecera «BRASA1» (6 B) + IV (12 B) +
// ciphertext AES-256-GCM. La clave llega en el entorno DB_ENC_KEY (base64 de 32 bytes).
// Uso: node scripts/descifrar_respaldo.mjs <archivo>
// Sin dependencias: WebCrypto del propio Node. Sale 0 sin tocar nada si el archivo no está cifrado.
import { readFileSync, writeFileSync } from 'node:fs';

const MAGIA = Buffer.from('BRASA1');
const IV_BYTES = 12;

const ruta = process.argv[2];
if (!ruta) {
  console.error('uso: node descifrar_respaldo.mjs <archivo>');
  process.exit(2);
}
const datos = readFileSync(ruta);
if (!datos.subarray(0, MAGIA.length).equals(MAGIA)) process.exit(0); // sin cifrar: nada que hacer

const clave = Buffer.from(process.env.DB_ENC_KEY ?? '', 'base64');
if (clave.length !== 32) {
  console.error('DB_ENC_KEY ausente o inválida (base64 de 32 bytes, el secreto del Worker)');
  process.exit(1);
}
try {
  const key = await crypto.subtle.importKey('raw', clave, 'AES-GCM', false, ['decrypt']);
  const plano = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: datos.subarray(MAGIA.length, MAGIA.length + IV_BYTES) },
    key,
    datos.subarray(MAGIA.length + IV_BYTES),
  );
  writeFileSync(ruta, Buffer.from(plano));
} catch {
  console.error('descifrado falló: clave incorrecta u objeto dañado');
  process.exit(1);
}
