/* Utilidades compartidas: DOM, formato y fechas (hora de Chile). */

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

export const TZ = 'America/Santiago';
const nf = (digits) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
export const fmtNum = (n, digits = 0) => (Number.isFinite(n) ? nf(digits).format(n) : '—');
export const fmtCompact = (n) => (Number.isFinite(n) ? new Intl.NumberFormat('es-CL', { notation: 'compact', maximumFractionDigits: 1 }).format(n) : '—');

export const parseUTC = (s) => new Date(s.endsWith('Z') || s.includes('+') ? s : `${s}Z`);
export const fmtTime = (iso) => parseUTC(iso).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
export const fmtDateTime = (iso) => parseUTC(iso).toLocaleString('es-CL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
export const fmtDay = (ymd, opts = {}) => new Date(`${ymd}T12:00:00Z`).toLocaleDateString('es-CL', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC', ...opts });
export const fmtUTC = (iso) => `${parseUTC(iso).toISOString().slice(11, 16)} UTC`;

/** "hace 12 min", "hace 3 h", "hace 2 días" */
export function ago(iso, now = Date.now()) {
  if (!iso) return 'sin datos';
  const minutes = Math.round((now - parseUTC(iso).getTime()) / 60000);
  if (minutes < 1) return 'recién';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}
export const minutesSince = (iso, now = Date.now()) => (iso ? (now - parseUTC(iso).getTime()) / 60000 : Infinity);

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

export const storage = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(`brasa:${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`brasa:${key}`, JSON.stringify(value)); } catch { /* almacenamiento no disponible */ }
  },
};

export function debounce(fn, ms = 200) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

/** Avisos breves en pantalla (también se anuncian a lectores de pantalla). */
export function toast(message, kind = 'info', ms = 4200) {
  const host = $('#toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast toast-${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.textContent = message;
  host.append(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, ms);
}

export const RISK = {
  bajo: { label: 'Bajo', icon: '●', cls: 'risk-bajo' },
  moderado: { label: 'Moderado', icon: '▲', cls: 'risk-moderado' },
  alto: { label: 'Alto', icon: '◆', cls: 'risk-alto' },
  extremo: { label: 'Extremo', icon: '■', cls: 'risk-extremo' },
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
export function emberSvg({ tone = 'brasa', rings = 4, seed = 7, size = 100 } = {}) {
  const id = `eg-${tone}-${seed}`;
  const rings_ = isothermPaths({ rings, seed, r0: 17, step: 8.5 })
    .map((d, i) => `<path class="iso iso-${i}" d="${d}" pathLength="1" style="--k:${i}"/>`).join('');
  return raw(`<svg class="ember ember-${tone}" viewBox="0 0 100 100" width="${size}" height="${size}" aria-hidden="true" focusable="false">
    <defs><radialGradient id="${id}" cx="50%" cy="46%" r="55%"><stop offset="0" class="eg-0"/><stop offset=".45" class="eg-1"/><stop offset="1" class="eg-2"/></radialGradient></defs>
    <g class="isos">${rings_}</g><circle class="halo" cx="50" cy="50" r="15"/><circle class="core" cx="50" cy="50" r="11" fill="url(#${id})"/></svg>`);
}
