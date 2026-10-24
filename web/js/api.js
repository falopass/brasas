/* Cliente de la API de BRASA. Identidad sin cuentas: un token aleatorio por dispositivo. */
import { storage } from './util.js';

export class ApiError extends Error {
  constructor(message, status, code, retryAfterS = null) { super(message); this.status = status; this.code = code; this.retryAfterS = retryAfterS; }
}

// Retry-After llega como segundos («7») o como fecha HTTP. Se acota a [0, 300]: una fecha
// pasada vale 0 y un valor ilegible, null.
const MAX_RETRY_AFTER_S = 300;
function parseRetryAfter(response) {
  const raw = (response.headers.get('Retry-After') || '').trim();
  if (!raw) return null;
  const s = /^\d+$/.test(raw) ? Number(raw) : (Date.parse(raw) - Date.now()) / 1000;
  return Number.isFinite(s) ? Math.min(MAX_RETRY_AFTER_S, Math.max(0, Math.ceil(s))) : null;
}

async function parse(response) {
  const type = response.headers.get('content-type') || '';
  const body = type.includes('json') ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    const detail = body?.detail;
    const retryAfter = parseRetryAfter(response);
    let message = `Error ${response.status}`;
    if (typeof detail === 'string') message = detail;
    else if (detail?.message) message = detail.message;
    else if (Array.isArray(detail) && detail[0]?.msg) message = `Dato inválido: ${detail.map((d) => d.loc?.slice(-1)[0]).join(', ')}`;
    else if (response.status >= 500) message = 'El servidor no pudo completar la solicitud.';
    if (response.status === 429) {
      message = retryAfter === null
        ? 'Demasiadas solicitudes desde tu red. Espera un momento y vuelve a intentarlo.'
        : `Demasiadas solicitudes desde tu red. Espera ${retryAfter} s y vuelve a intentarlo.`;
    }
    throw new ApiError(message, response.status, detail?.code, retryAfter);
  }
  return body;
}

// Tope de tiempo (FIX-45): ninguna vista queda «cargando» si la red rural responde mal.
// Lecturas y mutaciones normales: 12 s. Llamadas pesadas (exportación, polar de un caso,
// reportes y cualquier subida con adjunto): 60 s. La opción `timeout` (ms) lo amplía por llamada.
const DEFAULT_TIMEOUT_MS = 12_000;
const HEAVY_TIMEOUT_MS = 60_000;
// Pausa antes de reintentar una lectura que no llegó a salir por un microcorte de señal.
const NETWORK_RETRY_DELAY_MS = 1_200;

const isHeavy = (path, method, form) =>
  Boolean(form) || path === '/api/me/export' || (method === 'POST' && path.endsWith('/polar'));

// Combina el signal del llamador con el del tope. Sin AbortSignal.timeout (Safari < 16) se
// devuelve el signal original sin tope: preferimos eso a romper la app en navegadores antiguos.
function withTimeout(signal, ms) {
  if (typeof AbortSignal === 'undefined' || typeof AbortSignal.timeout !== 'function') return signal;
  const timeoutSignal = AbortSignal.timeout(ms);
  if (!signal) return timeoutSignal;
  if (typeof AbortSignal.any === 'function') return AbortSignal.any([signal, timeoutSignal]);
  // Sin AbortSignal.any (Safari < 17.4): encadena ambos signals a mano con un controlador.
  const ctrl = new AbortController();
  if (signal.aborted) ctrl.abort(signal.reason);
  else {
    signal.addEventListener('abort', () => ctrl.abort(signal.reason), { once: true });
    timeoutSignal.addEventListener('abort', () => ctrl.abort(timeoutSignal.reason), { once: true });
  }
  return ctrl.signal;
}

export async function request(path, { method = 'GET', body, auth = false, form, headers = {}, signal, timeout } = {}, retried = false) {
  const ms = timeout ?? (isHeavy(path, method, form) ? HEAVY_TIMEOUT_MS : DEFAULT_TIMEOUT_MS);
  const init = { method, headers: { ...headers }, signal: withTimeout(signal, ms) };
  const token = auth ? await deviceToken() : null;
  if (token) init.headers['X-Brasa-Token'] = token;
  if (form) init.body = form;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    if (err.name === 'TimeoutError') {
      throw new ApiError('El servidor no respondió a tiempo. Revisa tu conexión e inténtalo de nuevo.', 0, 'TIMEOUT');
    }
    if (err.name === 'AbortError') throw err;
    // Si el llamador ya abortó (cambio de vista), no hay nada que reintentar.
    if (signal?.aborted) throw signal.reason ?? err;
    // Lectura que no llegó a salir (cambio de celda, microcorte rural): un GET sin adjuntos
    // se reintenta una sola vez tras una pausa corta, reutilizando `init` para no alargar el
    // tope de tiempo. Las mutaciones nunca se repiten: duplicarían un reporte o un aviso.
    if (method === 'GET' && !form) {
      await new Promise((resolve) => setTimeout(resolve, NETWORK_RETRY_DELAY_MS));
      if (signal?.aborted) throw signal.reason ?? err;
      try {
        response = await fetch(path, init);
      } catch (retryErr) {
        if (retryErr.name === 'TimeoutError') {
          throw new ApiError('El servidor no respondió a tiempo. Revisa tu conexión e inténtalo de nuevo.', 0, 'TIMEOUT');
        }
        if (retryErr.name === 'AbortError') throw retryErr;
      }
    }
    if (!response) throw new ApiError('Sin conexión con el servidor de BRASA.', 0, 'OFFLINE');
  }
  // Si /api/status salió de la caché del service worker, guarda la fecha del dato (FIX-24). Solo esa
  // respuesta mueve la marca: es la que la píldora usa para declarar «sin conexión».
  if (path === '/api/status') storage.set('cached-at', response.headers.get('X-Brasa-Cached-At'));
  if (auth && response.status === 401) {
    // El servidor no reconoce el dispositivo (por ejemplo, base reiniciada). Solo se descarta si es el mismo
    // token que se usó: una respuesta tardía no debe borrar uno nuevo creado entretanto por otra solicitud.
    if (storage.get('token') === token) storage.set('token', null);
    if (!retried && !form) return request(path, { method, body, auth, headers, signal, timeout }, true);
  }
  try {
    return await parse(response);
  } catch (err) {
    // Un GET que choca con el límite del borde y pide una espera corta se repite una sola vez.
    // Las mutaciones no: repetir un POST podría duplicar un reporte o un aviso.
    if (method === 'GET' && !form && !retried && err.retryAfterS != null && err.retryAfterS <= 10) {
      await new Promise((resolve) => setTimeout(resolve, err.retryAfterS * 1000));
      return request(path, { method, body, auth, headers, signal, timeout }, true);
    }
    throw err;
  }
}

let tokenPromise = null;
export function deviceToken() {
  const saved = storage.get('token');
  if (saved) return Promise.resolve(saved);
  if (!tokenPromise) {
    tokenPromise = request('/api/subscribers', { method: 'POST' })
      .then(({ token }) => { storage.set('token', token); return token; })
      .finally(() => { tokenPromise = null; });
  }
  return tokenPromise;
}

export const api = {
  config: () => request('/api/config'),
  status: (history) => request(`/api/status${history ? `?history=${history}` : ''}`),
  observations: (hours, reliable) => request(`/api/observations?hours=${hours}${reliable ? '&reliable=true' : ''}`),
  explore: (params) => request(`/api/explore?${new URLSearchParams(params)}`),
  risk: (day) => request(`/api/risk${day ? `?day=${day}` : ''}`),
  riskComuna: (code) => request(`/api/risk/${code}`),
  riskTrend: (code, weeks = 1) => request(`/api/risk/${code}/trend?weeks=${weeks}`),
  panorama: (comunaCode, season) => request(`/api/panorama?comuna=${comunaCode}${season ? `&season=${season}` : ''}`),
  weather: (lat, lon) => request(`/api/weather?lat=${lat}&lon=${lon}`),
  locate: (lat, lon) => request(`/api/locate?lat=${lat}&lon=${lon}`),
  places: () => request('/api/places', { auth: true }),
  addPlace: (place) => request('/api/places', { method: 'POST', body: place, auth: true }),
  updatePlace: (id, place) => request(`/api/places/${id}`, { method: 'PATCH', body: place, auth: true }),
  deletePlace: (id) => request(`/api/places/${id}`, { method: 'DELETE', auth: true }),
  placeSummary: (id) => request(`/api/places/${id}/summary`, { auth: true }),
  placeHistory: (id, days = 30) => request(`/api/places/${id}/history?days=${days}`, { auth: true }),
  sharePlace: (id) => request(`/api/places/${id}/share`, { method: 'POST', auth: true }),
  unsharePlace: (id) => request(`/api/places/${id}/share`, { method: 'DELETE', auth: true }),
  shared: (token) => request(`/api/shared/${encodeURIComponent(token)}`),
  nearbyServices: (lat, lon) => request(`/api/nearby-services?lat=${lat}&lon=${lon}`),
  me: () => request('/api/me', { auth: true }),
  exportMe: () => request('/api/me/export', { auth: true }),
  deleteMe: () => request('/api/me', { method: 'DELETE', auth: true }),
  alerts: (params) => request(params ? `/api/alerts?${new URLSearchParams(params)}` : '/api/alerts', { auth: true }),
  feedbackAlert: (id, value) => request(`/api/alerts/${id}/feedback`, { method: 'POST', body: { value }, auth: true }),
  testAlert: () => request('/api/alerts/test', { method: 'POST', auth: true }),
  pushSubscribe: (sub) => request('/api/push/subscribe', { method: 'POST', body: sub, auth: true }),
  pushUnsubscribe: () => request('/api/push/subscribe', { method: 'DELETE', auth: true }),
  telegramLink: () => request('/api/telegram/link', { method: 'POST', auth: true }),
  reports: (hours = 72) => request(`/api/reports?hours=${hours}`),
  createReport: async (form) => {
    // El token es opcional en el servidor: si el registro del dispositivo falla (límite por
    // IP u otro error), el reporte sale igual, sin autor. Los demás llamados sí exigen token.
    const token = await deviceToken().catch(() => null);
    return request('/api/reports', { method: 'POST', form, headers: token ? { 'X-Brasa-Token': token } : {} });
  },
  cases: () => request('/api/cases'),
  caseDetail: (id) => request(`/api/cases/${id}`),
  caseWeather: (id) => request(`/api/cases/${id}/weather`),
  casePolar: (id) => request(`/api/cases/${id}/polar`),
  loadCasePolar: (id) => request(`/api/cases/${id}/polar`, { method: 'POST' }),
  caseGoes: (id) => request(`/web/data/cases/${id}.goes.json`),
  priorityComunas: () => request('/api/priority-comunas'),
  incidents: (hours = 48, hulls = false) => request(`/api/incidents?hours=${hours}${hulls ? '&hulls=1' : ''}`),
  enso: () => request('/api/climate/enso'),
  officialFires: () => request('/api/official-fires'),
  incident: (id) => request(`/api/incidents/${encodeURIComponent(id)}`),
  scars: () => request('/api/opendata/scars.geojson'),
  incidentReports: (id) => request(`/api/incidents/${encodeURIComponent(id)}/reports`),
};
