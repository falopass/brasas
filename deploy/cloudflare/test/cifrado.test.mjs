// Pruebas del cifrado en reposo del respaldo (SEC-06). Corre con `node --test` directo
// sobre el TS, igual que retention.test.mjs (el módulo solo usa WebCrypto).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { bytesDeClave, cifrarRespaldo, descifrarRespaldo, estaCifrado } from '../src/cifrado.ts';

const CLAVE = randomBytes(32);
const OTRA_CLAVE = randomBytes(32);
const SQLITE = new TextEncoder().encode('SQLite format 3\0cabecera-y-datos-de-prueba');

test('clave: acepta base64 de 32 bytes y rechaza lo demás', () => {
  assert.deepEqual(bytesDeClave(CLAVE.toString('base64')), new Uint8Array(CLAVE));
  assert.equal(bytesDeClave(randomBytes(16).toString('base64')), null); // 16 bytes
  assert.equal(bytesDeClave('no es base64!!!'), null);
  assert.equal(bytesDeClave(''), null);
  assert.equal(bytesDeClave(undefined), null);
});

test('ida y vuelta: lo que se cifra se descifra igual', async () => {
  const cifrado = await cifrarRespaldo(CLAVE, SQLITE);
  assert.equal(estaCifrado(cifrado), true);
  assert.equal(new TextDecoder().decode(cifrado.subarray(0, 6)), 'BRASA1');
  // Lo guardado no es un SQLite en claro: no empieza con la cabecera del formato.
  assert.notEqual(new TextDecoder().decode(cifrado.subarray(0, 15)), 'SQLite format 3');
  const plano = await descifrarRespaldo(CLAVE, cifrado.buffer);
  assert.deepEqual(new Uint8Array(plano), SQLITE);
});

test('cada escritura lleva un IV distinto', async () => {
  const a = await cifrarRespaldo(CLAVE, SQLITE);
  const b = await cifrarRespaldo(CLAVE, SQLITE);
  assert.notDeepEqual(a, b);
  assert.notDeepEqual(a.subarray(6, 18), b.subarray(6, 18)); // el IV no se repite
  assert.deepEqual(new Uint8Array(await descifrarRespaldo(CLAVE, a.buffer)), SQLITE);
  assert.deepEqual(new Uint8Array(await descifrarRespaldo(CLAVE, b.buffer)), SQLITE);
});

test('con otra clave el descifrado falla (tag GCM)', async () => {
  const cifrado = await cifrarRespaldo(CLAVE, SQLITE);
  await assert.rejects(descifrarRespaldo(OTRA_CLAVE, cifrado.buffer));
});

test('un byte alterado invalida el objeto', async () => {
  const cifrado = await cifrarRespaldo(CLAVE, SQLITE);
  cifrado[20] ^= 1;
  await assert.rejects(descifrarRespaldo(CLAVE, cifrado.buffer));
});

test('objeto sin cabecera se devuelve tal cual (respaldo anterior al cifrado)', async () => {
  const plano = SQLITE.buffer.slice(0);
  assert.equal(estaCifrado(new Uint8Array(plano)), false);
  assert.equal(await descifrarRespaldo(CLAVE, plano), plano); // con clave
  assert.equal(await descifrarRespaldo(null, plano), plano);  // sin clave
});

test('objeto cifrado sin clave lanza (el handler responde 500)', async () => {
  const cifrado = await cifrarRespaldo(CLAVE, SQLITE);
  await assert.rejects(descifrarRespaldo(null, cifrado.buffer));
});
