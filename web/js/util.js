/* Utilidades compartidas: DOM, formato y fechas (hora de Chile continental). Las fechas y el
 * formato de números viven en formato.js — única fuente también para lite, pantalla y respuesta. */

import { parseUTC, TZ, TZ_LABEL, utcDate } from './formato.js';
export { TZ, TZ_LABEL, parseUTC, fmtNum, fmtTime, fmtDateTime, ago } from './formato.js';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);

class Raw {
  constructor(value) { this.value = value; }
  toString() { return this.value; }
}
const render = (v) => (v instanceof Raw ? v.value : v === null || v === undefined || v === false ? '' : escapeHtml(v));

/**
 * Plantilla HTML con escape automático de lo interpolado. Devuelve un fragmento confiable que
 * puede anidarse en otra plantilla (o arreglos de fragmentos) sin volver a escaparse.
 * raw() marca HTML confiable explícito. Asignar con el.innerHTML = String(fragmento).
 */
export function html(strings, ...values) {
  let out = '';
  strings.forEach((str, i) => {
    out += str;
    if (i < values.length) {
      const value = values[i];
      out += Array.isArray(value) ? value.map(render).join('') : render(value);
    }
  });
  return new Raw(out);
}
export const raw = (value) => new Raw(String(value));

export const fmtCompact = (n) => (Number.isFinite(n) ? new Intl.NumberFormat('es-CL', { notation: 'compact', maximumFractionDigits: 1 }).format(n) : '—');

export const fmtDay = (ymd, opts = {}) =>
  utcDate(`${ymd}T12:00:00Z`)?.toLocaleDateString('es-CL', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC', ...opts }) ?? '—';
export const fmtUTC = (iso) => {
  const date = utcDate(iso);
  return date ? `${date.toISOString().slice(11, 16)} UTC` : '—';
};
export const minutesSince = (iso, now = Date.now()) => {
  const date = utcDate(iso);
  return date ? (now - date.getTime()) / 60000 : Infinity;
};

export const todayChile = () => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date());

const CARDINALS = ['norte', 'noreste', 'este', 'sureste', 'sur', 'suroeste', 'oeste', 'noroeste'];
export const cardinal = (deg) => CARDINALS[Math.round(((deg % 360) + 360) % 360 / 45) % 8];
export const windFrom = (deg) => (Number.isFinite(deg) ? `desde el ${cardinal(deg)}` : '');

export function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dp = toRad(lat2 - lat1); const dl = toRad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

/** De los lugares guardados, el más cercano a un punto y hasta `top - 1` siguientes a ≤ 25 km.
 *  Pura y sin DOM: devuelve `{ nearest: { name, km }, others: [...] }` o null si ninguno sirve.
 *  `km` viene redondeado como en el resto de la app: < 10 con un decimal, si no, entero. */
export function nearestPlacesText(incident, places, maxKm = 50, top = 3) {
  if (!Number.isFinite(incident?.lat) || !Number.isFinite(incident?.lon)) return null;
  const roundKm = (km) => (km < 10 ? Math.round(km * 10) / 10 : Math.round(km));
  const found = (Array.isArray(places) ? places : [])
    .filter((p) => p && typeof p.name === 'string' && p.name.trim() && Number.isFinite(p.lat) && Number.isFinite(p.lon))
    .map((p) => ({ name: p.name, km: haversineKm(incident.lat, incident.lon, p.lat, p.lon) }))
    .filter((p) => p.km <= maxKm)
    .sort((a, b) => a.km - b.km);
  if (!found.length) return null;
  return {
    nearest: { name: found[0].name, km: roundKm(found[0].km) },
    others: found.slice(1).filter((p) => p.km <= 25).slice(0, Math.max(0, top - 1))
      .map((p) => ({ name: p.name, km: roundKm(p.km) })),
  };
}

/** Círculo geodésico aproximado como polígono GeoJSON (para radios de alerta). */
export function circlePolygon(lon, lat, radiusKm, steps = 64) {
  const coords = [];
  const dLat = radiusKm / 110.574;
  const dLon = radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * 2 * Math.PI;
    coords.push([lon + dLon * Math.cos(t), lat + dLat * Math.sin(t)]);
  }
  return { type: 'Polygon', coordinates: [coords] };
}

/** Cuadrado centrado de lado `sizeKm` (huella aproximada de un píxel satelital). */
export function pixelSquare(lon, lat, sizeKm) {
  const h = sizeKm / 2;
  const dLat = h / 110.574;
  const dLon = h / (111.32 * Math.cos((lat * Math.PI) / 180));
  return { type: 'Polygon', coordinates: [[[lon - dLon, lat - dLat], [lon + dLon, lat - dLat], [lon + dLon, lat + dLat], [lon - dLon, lat + dLat], [lon - dLon, lat - dLat]]] };
}

/* iCalendar (RFC 5545): escapar texto y plegar líneas a ≤75 octetos, cortando en bytes UTF-8. */
const icsText = (s) => String(s ?? '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
const icsFold = (line) => {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const parts = [];
  let start = 0, limit = 75;
  while (start < bytes.length) {
    let end = Math.min(start + limit, bytes.length);
    while (end > start && end < bytes.length && (bytes[end] & 0xc0) === 0x80) end--; // no cortar un carácter
    parts.push(new TextDecoder().decode(bytes.slice(start, end)));
    start = end;
    limit = 74; // el espacio inicial del pliegue ocupa un octeto
  }
  return parts.join('\r\n ');
};
const icsDate = (ymd) => ymd.replaceAll('-', '');
const icsNextDay = (ymd) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return null;
  return new Date(Date.parse(`${ymd}T00:00:00Z`) + 86400000).toISOString().slice(0, 10).replaceAll('-', '');
};

/** Calendario (.ics) con un evento de día completo por cada día con Botón Rojo de CONAF. */
export function botonRojoIcs({ comuna, days = [], url = '' }) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const desc = `CONAF pronostica condiciones favorables para incendios; no significa que haya fuego. Fuente: CONAF · Botón Rojo (https://www.arcgis.com/apps/dashboards/41ee3c691359437aa9df2a09d7f6124e)${url ? ` · Visto en BRASA: ${url}` : ''}`;
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//BRASA Chile//Boton Rojo//ES', 'CALSCALE:GREGORIAN'];
  for (const d of days.filter((x) => x?.boton_rojo_hours && x?.date)) {
    const end = icsNextDay(d.date);
    if (!end) continue;
    lines.push('BEGIN:VEVENT',
      `UID:boton-rojo-${icsText(comuna || 'comuna')}-${d.date}@brasa-chile`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${icsDate(d.date)}`,
      `DTEND;VALUE=DATE:${end}`,
      `SUMMARY:Botón Rojo en ${icsText(comuna || 'tu comuna')}`,
      `DESCRIPTION:${icsText(desc)}`,
      'END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return `${lines.map(icsFold).join('\r\n')}\r\n`;
}

/** Descarga un texto como archivo, sin pasar por el servidor. */
export function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const storage = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(`brasa:${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`brasa:${key}`, JSON.stringify(value)); } catch { /* almacenamiento no disponible */ }
  },
};

/** Avisos breves en pantalla (también se anuncian a lectores de pantalla). */
export function toast(message, kind = 'info', ms = 4200, action = null) {
  const host = $('#toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast toast-${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.textContent = message;
  if (action) {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'toast-action'; btn.textContent = action.label;
    btn.addEventListener('click', action.onClick);
    el.append(btn);
  }
  host.append(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, ms);
}

export const RISK = {
  bajo: { label: 'Bajo', icon: '●', cls: 'risk-bajo', plain: 'El clima no ayuda al fuego. Igual, cuidado con quemas y chispas.' },
  moderado: { label: 'Moderado', icon: '▲', cls: 'risk-moderado', plain: 'Calor o sequedad: un fuego podría avanzar si hay viento.' },
  alto: { label: 'Alto', icon: '◆', cls: 'risk-alto', plain: 'Día peligroso: un fuego pequeño puede crecer rápido. No hagas quemas.' },
  extremo: { label: 'Extremo', icon: '■', cls: 'risk-extremo', plain: 'Muy peligroso: mucho calor, aire seco y viento a la vez. Cualquier chispa puede iniciar un incendio.' },
};
export const riskChip = (level, extra = '') => {
  const r = RISK[level];
  return r ? html`<span class="risk-chip ${r.cls}"><span aria-hidden="true">${r.icon}</span>${r.label}${extra}</span>` : html`<span class="risk-chip risk-none">Sin dato</span>`;
};

export const SENSOR_LABEL = { ABI: 'GOES (geoestacionario)', VIIRS: 'VIIRS (órbita polar)', MODIS: 'MODIS (órbita polar)' };
export const pixelKm = (obs) => (obs.sensor === 'ABI' ? 2.5 : obs.sensor === 'MODIS' ? 1 : 0.375);

/** Isotermas: anillos irregulares alrededor de una fuente de calor (la forma de BRASA).
 *  Deterministas por `seed`, para que el dibujo no cambie entre renders. Devuelve los `d` de cada anillo. */
export function isothermPaths({ rings = 4, r0 = 14, step = 9, cx = 50, cy = 50, seed = 7, wobble = 0.09 } = {}) {
  let s = seed;
  const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
  const paths = [];
  for (let k = 0; k < rings; k++) {
    const r = r0 + k * step;
    const a2 = wobble * (0.6 + rnd()); const a3 = wobble * 0.7 * rnd(); const p2 = rnd() * 6.283; const p3 = rnd() * 6.283;
    const pts = [];
    for (let i = 0; i < 72; i++) {
      const t = (i / 72) * 6.283;
      const rr = r * (1 + a2 * Math.sin(2 * t + p2) + a3 * Math.sin(3 * t + p3));
      pts.push(`${(cx + rr * Math.cos(t)).toFixed(1)},${(cy + rr * Math.sin(t)).toFixed(1)}`);
    }
    paths.push(`M${pts.join('L')}Z`);
  }
  return paths;
}

/** La brasa con sus isotermas, como SVG en línea. `tone` elige la rampa de calor según el estado. */
let svgSeq = 0;
export function emberSvg({ tone = 'brasa', rings = 4, seed = 7, size = 100 } = {}) {
  const id = `eg-${tone}-${seed}-${++svgSeq}`;
  const rings_ = isothermPaths({ rings, seed, r0: 17, step: 8.5 })
    .map((d, i) => `<path class="iso iso-${i}" d="${d}" pathLength="1" style="--k:${i}"/>`).join('');
  return raw(`<svg class="ember ember-${tone}" viewBox="0 0 100 100" width="${size}" height="${size}" aria-hidden="true" focusable="false">
    <defs><radialGradient id="${id}" cx="50%" cy="46%" r="55%"><stop offset="0" class="eg-0"/><stop offset=".45" class="eg-1"/><stop offset="1" class="eg-2"/></radialGradient></defs>
    <g class="isos">${rings_}</g><circle class="halo" cx="50" cy="50" r="15"/><circle class="core" cx="50" cy="50" r="11" fill="url(#${id})"/></svg>`);
}

/** Dos niveles de lectura: la versión sencilla se ve por defecto; la técnica, con «Lectura detallada». */
export const dual = (plain, tech) => html`<span class="x-plain">${plain}</span><span class="x-tech">${tech}</span>`;
const CARD_FULL = { N: 'norte', NE: 'noreste', E: 'este', SE: 'sureste', S: 'sur', SO: 'suroeste', O: 'oeste', NO: 'noroeste' };
/** «del sur» / «hacia el norte» en palabras, a partir del rumbo en grados (de dónde viene el viento). */
export const windWords = (deg) => {
  if (!Number.isFinite(deg)) return null;
  const from = CARD_FULL[cardinal(deg)] || cardinal(deg);
  const to = CARD_FULL[cardinal(deg + 180)] || cardinal(deg + 180);
  return { from, to };
};

/** Radar de un lugar: tu casa al centro, el radio de aviso, los puntos de calor en su rumbo y distancia
 *  reales, y la flecha del viento (hacia dónde sopla). Escala: el borde es el doble del radio. */
export function radarSvg({ radiusKm, nearby = [], wind = null, now = Date.now() }) {
  const head = `rd-head-${++svgSeq}`;
  const R = 44; const C = 50; const maxKm = radiusKm * 2;
  const dots = nearby.filter((o) => o.distance_km <= maxKm).slice(0, 40).map((o) => {
    const r = (o.distance_km / maxKm) * R; const a = ((o.bearing_deg ?? 0) - 90) * Math.PI / 180;
    const age = (now - parseUTC(o.observed_at).getTime()) / 3600000;
    const color = age < 1 ? '#ff4b1f' : age < 6 ? '#ff7a2e' : age < 24 ? '#ffa54a' : '#ffd38f';
    const cls = `rd-dot${o.reliable ? '' : ' rd-weak'}${o.upwind && o.inside_radius ? ' rd-upwind' : ''}`;
    return `<circle class="${cls}" cx="${(C + r * Math.cos(a)).toFixed(1)}" cy="${(C + r * Math.sin(a)).toFixed(1)}" r="${o.reliable ? 3.2 : 2.4}" fill="${color}"/>`;
  }).join('');
  let arrow = '';
  if (wind && Number.isFinite(wind.direction) && wind.speed > 1) {
    // La flecha cruza el radar en la dirección hacia la que sopla el viento.
    const to = (wind.direction + 180 - 90) * Math.PI / 180;
    const x1 = C - Math.cos(to) * 30; const y1 = C - Math.sin(to) * 30; const x2 = C + Math.cos(to) * 30; const y2 = C + Math.sin(to) * 30;
    arrow = `<g class="rd-wind"><line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" marker-end="url(#${head})"/></g>`;
  }
  return raw(`<svg class="radar" viewBox="0 0 100 100" role="img" aria-label="Radar del lugar: puntos de calor cercanos y dirección del viento">
    <defs><marker id="${head}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" class="rd-head"/></marker></defs>
    <circle class="rd-ring rd-outer" cx="50" cy="50" r="${R}"/><circle class="rd-ring rd-alert" cx="50" cy="50" r="${R / 2}"/>
    <line class="rd-axis" x1="50" y1="4" x2="50" y2="96"/><line class="rd-axis" x1="4" y1="50" x2="96" y2="50"/>
    <text class="rd-n" x="50" y="3.5">N</text>
    <circle class="rd-sweep" cx="50" cy="50" r="${R}"/>
    ${arrow}${dots}
    <circle class="rd-home" cx="50" cy="50" r="4"/></svg>`);
}
export const cardWord = (abbr) => CARD_FULL[abbr] || abbr;

/** Redibuja un panel sin perder el lugar: conserva el desplazamiento y el foco (por id o data-*). */
export function keepPlace(container, renderFn) {
  const top = container.scrollTop;
  const active = document.activeElement && container.contains(document.activeElement) ? document.activeElement : null;
  const key = active && (active.id ? `#${CSS.escape(active.id)}` : [...active.attributes].filter((a) => a.name.startsWith('data-'))
    .map((a) => `[${a.name}="${CSS.escape(a.value)}"]`).join(''));
  renderFn();
  container.scrollTop = top;
  if (key) container.querySelector(key)?.focus({ preventScroll: true });
}
