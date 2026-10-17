/* Cliente de la API de BRASA. Identidad sin cuentas: un token aleatorio por dispositivo. */
import { storage } from './util.js';

export class ApiError extends Error {
  constructor(message, status, code) { super(message); this.status = status; this.code = code; }
}

async function parse(response) {
  const type = response.headers.get('content-type') || '';
  const body = type.includes('application/json') ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    const detail = body?.detail;
    let message = `Error ${response.status}`;
    if (typeof detail === 'string') message = detail;
    else if (detail?.message) message = detail.message;
    else if (Array.isArray(detail) && detail[0]?.msg) message = `Dato inválido: ${detail.map((d) => d.loc?.slice(-1)[0]).join(', ')}`;
    else if (response.status >= 500) message = 'El servidor no pudo completar la solicitud.';
    throw new ApiError(message, response.status, detail?.code);
  }
  return body;
}

export async function request(path, { method = 'GET', body, auth = false, form, headers = {}, signal } = {}) {
  const init = { method, headers: { ...headers }, signal };
  if (auth) init.headers['X-Brasa-Token'] = await deviceToken();
  if (form) init.body = form;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('Sin conexión con el servidor de BRASA.', 0, 'OFFLINE');
  }
  if (auth && response.status === 401) {
    storage.set('token', null); // el servidor no reconoce el dispositivo (por ejemplo, base reiniciada)
  }
  return parse(response);
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
  status: () => request('/api/status'),
  observations: (hours, reliable) => request(`/api/observations?hours=${hours}${reliable ? '&reliable=true' : ''}`),
  explore: (params) => request(`/api/explore?${new URLSearchParams(params)}`),
  risk: (day) => request(`/api/risk${day ? `?day=${day}` : ''}`),
  riskComuna: (code) => request(`/api/risk/${code}`),
  weather: (lat, lon) => request(`/api/weather?lat=${lat}&lon=${lon}`),
  locate: (lat, lon) => request(`/api/locate?lat=${lat}&lon=${lon}`),
  places: () => request('/api/places', { auth: true }),
  addPlace: (place) => request('/api/places', { method: 'POST', body: place, auth: true }),
  updatePlace: (id, place) => request(`/api/places/${id}`, { method: 'PATCH', body: place, auth: true }),
  deletePlace: (id) => request(`/api/places/${id}`, { method: 'DELETE', auth: true }),
  placeSummary: (id) => request(`/api/places/${id}/summary`, { auth: true }),
  nearbyServices: (lat, lon) => request(`/api/nearby-services?lat=${lat}&lon=${lon}`),
  me: () => request('/api/me', { auth: true }),
  alerts: () => request('/api/alerts', { auth: true }),
  testAlert: () => request('/api/alerts/test', { method: 'POST', auth: true }),
  pushSubscribe: (sub) => request('/api/push/subscribe', { method: 'POST', body: sub, auth: true }),
  pushUnsubscribe: () => request('/api/push/subscribe', { method: 'DELETE', auth: true }),
  telegramLink: () => request('/api/telegram/link', { method: 'POST', auth: true }),
  reports: () => request('/api/reports'),
  createReport: (form) => request('/api/reports', { method: 'POST', form }),
  cases: () => request('/api/cases'),
  caseDetail: (id) => request(`/api/cases/${id}`),
  caseWeather: (id) => request(`/api/cases/${id}/weather`),
  casePolar: (id) => request(`/api/cases/${id}/polar`),
  loadCasePolar: (id) => request(`/api/cases/${id}/polar`, { method: 'POST' }),
  caseGoes: (id) => request(`/web/data/cases/${id}.goes.json`),
  priorityComunas: () => request('/api/priority-comunas'),
};
