/* MZ-05: «Desde tu última visita» — módulo puro, sin DOM ni fetch.
 * `snapshot` resume lo que el vecino vio y `digest` lo compara con la visita anterior.
 * Nada se inventa: si un dato falta, su frase simplemente no aparece. */
import { fmtNum, RISK } from './util.js';

const MESES_MS = 86400000;
const DIAS_SEMANA = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

const nivelPalabra = (level) => (RISK[level]?.label || level || 'sin dato').toLowerCase();

/** Resumen de la visita: focos dentro del radio de cada lugar, riesgo por comuna y avisos.
 * `summaries` puede ser Map (vista) u objeto plano (pruebas). */
export function snapshot({ places = [], summaries, avisos = 0, now } = {}) {
  const get = (id) => (summaries instanceof Map ? summaries.get(id) : (summaries || {})[id]);
  const focos = [];
  const riesgo = {};
  const comunas = {};
  for (const p of places || []) {
    const s = get(p.id);
    for (const o of s?.nearby || []) {
      if (o.id != null && Number.isFinite(o.distance_km)) focos.push({ id: o.id, km: o.distance_km });
    }
    const code = p.comuna?.code;
    if (code != null) {
      comunas[code] = p.comuna.name;
      if (s?.risk_days?.[0]?.level) riesgo[code] = s.risk_days[0].level;
    }
  }
  return { at: now || new Date().toISOString(), placeIds: places.map((p) => p.id), focos, riesgo, comunas, avisos };
}

/** {dias, frases}: las frases salen solo de datos presentes en ambas visitas.
 * `prev` nulo, corrupto o con fecha inválida → {dias: 0, frases: []}. */
export function digest(prev, now) {
  const t0 = Date.parse(prev?.at ?? '');
  const t1 = Date.parse(now?.at ?? '');
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return { dias: 0, frases: [] };
  const dias = Math.floor((t1 - t0) / MESES_MS);
  const frases = [];
  if (dias >= 2) frases.push(`Hace ${fmtNum(dias)} días que no entrabas`);
  const antes = new Map((prev.focos || []).map((f) => [f.id, f.km]));
  const nuevos = (now.focos || []).filter((f) => f && f.id != null && !antes.has(f.id));
  if (nuevos.length) {
    const kms = nuevos.map((f) => f.km).filter(Number.isFinite);
    frases.push(`${nuevos.length === 1 ? 'Un foco nuevo' : `${fmtNum(nuevos.length)} focos nuevos`}${kms.length ? ` a menos de ${fmtNum(Math.round(Math.min(...kms)))} km de tu casa` : ''}`);
  }
  for (const [code, nivel] of Object.entries(now.riesgo || {})) {
    const previo = prev.riesgo?.[code];
    if (previo && previo !== nivel) {
      const nombre = now.comunas?.[code] || prev.comunas?.[code] || 'tu comuna';
      frases.push(`El riesgo en ${nombre} pasó de ${nivelPalabra(previo)} a ${nivelPalabra(nivel)}`);
    }
  }
  if (Number.isFinite(prev.avisos) && prev.avisos > 0 && (now.avisos ?? 0) === 0) {
    frases.push('Ya no hay avisos de la DMC en tu comuna');
  } else if (Number.isFinite(prev.avisos) && Number.isFinite(now.avisos) && now.avisos > prev.avisos) {
    frases.push(`${fmtNum(now.avisos - prev.avisos)} aviso(s) nuevo(s) en tu zona`);
  }
  if (!frases.length) {
    const dia = new Intl.DateTimeFormat('es-CL', { weekday: 'long', timeZone: 'America/Santiago' }).format(t0);
    frases.push(`Nada cambió desde el ${dia}`);
  }
  return { dias, frases };
}
