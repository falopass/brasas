/* Recibo de datos del dispositivo (PRIV-03): resume el JSON de /api/me/export en una
 * frase que se lee en diez segundos. Puro: sin DOM, sin red y sin consola. */

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

/** «2026-10-21» (fecha de Chile) → «21 de octubre de 2026»; null si no es una fecha. */
export function fechaLarga(ymd) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(ymd ?? ''));
  const mes = m && MESES[Number(m[2]) - 1];
  return mes ? `${Number(m[3])} de ${mes} de ${m[1]}` : null;
}

const cantidad = (lista) => (Array.isArray(lista) ? lista.length : 0);
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

/** Lo que el export trae de este dispositivo. `hoy` es la fecha de Chile (AAAA-MM-DD).
 *  Los reportes ciudadanos no se cuentan: son anónimos y no cuelgan del dispositivo. */
export function reciboDe(datos, hoy) {
  const lugares = cantidad(datos?.lugares);
  const avisos = cantidad(datos?.avisos);
  const dispositivo = datos?.dispositivo ?? {};
  const canales = [dispositivo.suscripcion_push?.endpoint, dispositivo.telegram_chat_id].filter(Boolean).length;
  const piezas = [
    plural(lugares, 'lugar guardado', 'lugares guardados'),
    plural(avisos, 'aviso', 'avisos'),
    canales ? plural(canales, 'suscripción a avisos', 'suscripciones a avisos') : null,
  ].filter(Boolean);
  const fecha = fechaLarga(hoy);
  return { lugares, avisos, canales, fecha, frase: fecha ? `${piezas.join(' · ')}, al ${fecha}` : piezas.join(' · ') };
}
