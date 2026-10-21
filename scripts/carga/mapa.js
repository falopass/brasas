// Prueba de carga del mapa de BRASA (OPS-04): 500 personas simultáneas durante 10 minutos.
// Uso: k6 run -e BASE_URL=https://… scripts/carga/mapa.js   — ver README.md.
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
// 1 = incluye el alta de suscriptor y /api/places (endpoints por dispositivo, con tope por IP).
const WITH_PRIVATE = __ENV.WITH_PRIVATE === '1';

export const options = {
  scenarios: {
    mapa: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 500 }, // subida: el susto de un megaincendio
        { duration: '8m', target: 500 }, // meseta: 500 simultáneos
        { duration: '1m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],     // menos del 1 % de errores
    http_req_duration: ['p(95)<2000'],  // p95 bajo 2 s
  },
};

// Lo que pide la app al abrir el mapa (web/js/app.js + views/mapa.js): la página, las fuentes
// de datos del mapa y las API públicas, en paralelo como lo hace el navegador. Los polígonos
// comunales (comunas.geojson, 1,9 MB) no van aquí: el mapa los pide al acercarse a los
// límites comunales o al encender la coropleta (MAPA-143).
const PRIMERA_CARGA = [
  '/',
  '/web/data/regiones.geojson',
  '/api/config',
  '/api/status',
  '/api/observations?hours=24',
  '/api/incidents?hours=48',
  '/api/official-fires',
  '/api/risk',
  '/api/reports',
];

function pedir(res, etiqueta) {
  const ok = check(res, { '200 o 304': (r) => r.status === 200 || r.status === 304 });
  if (!ok) console.error(`${etiqueta} → HTTP ${res.status}`);
  return ok;
}

export default function () {
  for (const res of http.batch(PRIMERA_CARGA.map((path) => ['GET', `${BASE}${path}`]))) {
    pedir(res, res.request.url.replace(BASE, ''));
  }
  let token = '';
  if (WITH_PRIVATE) {
    const alta = http.post(`${BASE}/api/subscribers`);
    if (pedir(alta, '/api/subscribers')) {
      token = alta.json('token');
      pedir(http.get(`${BASE}/api/places`, { headers: { 'X-Brasa-Token': token } }), '/api/places');
    }
  }
  // La app repide /api/status cada 60 s y /api/observations cada 120 s (web/js/app.js).
  for (let i = 0; i < 10; i++) {
    sleep(60);
    pedir(http.get(`${BASE}/api/status`), '/api/status');
    if (i % 2 === 0) pedir(http.get(`${BASE}/api/observations?hours=24`), '/api/observations');
  }
}
