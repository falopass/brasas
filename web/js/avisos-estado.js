/* Por qué no ha llegado un aviso: una sola explicación priorizada para la vista Avisos.
 * Módulo puro, sin DOM ni imports, para probarlo con node:test y que la vista solo pinte. */

const CONFIABLES = ['alta', 'nominal', 'media'];

// Ventana real del motor de avisos: una detección más vieja jamás despierta un aviso.
// Espejo de backend/alerts.py MAX_AGE_H (= 6); si cambia allá, cambia aquí.
export const VENTANA_AVISO_H = 6;

// Misma aritmética y constante que util.js:haversineKm; este módulo no importa nada.
function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dp = toRad(lat2 - lat1); const dl = toRad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

/** Un foco despierta avisos si su señal es confiable y no viene de una fuente fija (volcán o industria). */
const alertable = (point) => CONFIABLES.includes(point?.confidence) && !point?.incident_fixed;

/** Edad en horas de una detección; `null` cuando `observed_at` falta o no se puede leer. */
function edadHoras(observedAt) {
  const t = Date.parse(observedAt);
  return Number.isFinite(t) ? Math.max(0, (Date.now() - t) / 3600000) : null;
}

/** «y se vio hace 9 h», o la verdad de que el dato no trae hora: nunca una hora inventada. */
function vistoHace(edadH) {
  if (edadH == null) return '; el dato no dice a qué hora se vio';
  return ` y se vio ${edadH < 1 ? 'hace menos de 1 h' : `hace ${Math.round(edadH)} h`}`;
}

/**
 * Focos dentro de 2× el radio de cada lugar guardado, del más cercano al más lejano.
 * Devuelve `{ place, point, km }` por cada cruce, incluidos los de fuente fija: quien decide
 * si cuentan como calor que avisa es `estadoAvisos`.
 */
export function focosCerca(places, points) {
  const focos = [];
  for (const place of Array.isArray(places) ? places : []) {
    if (!Number.isFinite(place?.lat) || !Number.isFinite(place?.lon) || !Number.isFinite(place?.radius_km)) continue;
    for (const point of Array.isArray(points) ? points : []) {
      if (!Number.isFinite(point?.lat) || !Number.isFinite(point?.lon)) continue;
      const km = haversineKm(place.lat, place.lon, point.lat, point.lon);
      if (km <= place.radius_km * 2) focos.push({ place, point, km });
    }
  }
  return focos.sort((a, b) => a.km - b.km);
}

/**
 * Explica el silencio de la vista Avisos: `{ titulo, cuerpo, accion, tono }` o `null` si ya hay avisos.
 * `accion` es `'agregar-lugar'`, `'activar-avisos'` o `null`; `tono`, `'info'` o `'warn'`.
 */
export function estadoAvisos({ places = [], alerts = [], points = [], status = null, permission = 'default' } = {}) {
  if (Array.isArray(alerts) && alerts.length) return null;
  const lugares = (Array.isArray(places) ? places : []).filter(
    (p) => p && typeof p.name === 'string' && Number.isFinite(p.lat) && Number.isFinite(p.lon) && Number.isFinite(p.radius_km),
  );
  if (!lugares.length) {
    return {
      titulo: 'No tienes lugares guardados',
      cuerpo: 'BRASA avisa solo por los lugares que guardas. Agrega tu casa y te llega un aviso cuando un satélite vea calor cerca.',
      accion: 'agregar-lugar',
      tono: 'info',
    };
  }
  if (permission !== 'granted') {
    return {
      titulo: 'Los avisos no están activados en este teléfono',
      cuerpo: 'Tus lugares están guardados, pero este teléfono no está recibiendo notificaciones de BRASA. El aviso igual queda en este historial; ábrelas para que te llegue aunque la app esté cerrada.',
      accion: 'activar-avisos',
      tono: 'warn',
    };
  }
  if (status?.freshness?.stale) {
    return {
      titulo: 'Los datos de los satélites están atrasados',
      cuerpo: 'La última actualización de los satélites está atrasada. Que no aparezca un aviso no significa que no haya fuego: revisa el mapa y, si ves humo o llamas, llama al 130 o al 132.',
      accion: null,
      tono: 'warn',
    };
  }
  const focos = focosCerca(lugares, points);
  const conUmbral = focos.filter(({ point }) => alertable(point));
  if (conUmbral.length) {
    const n = new Set(conUmbral.map((f) => f.point)).size;
    const { km, place, point } = conUmbral[0];
    const distancia = km < 1 ? 'menos de 1 km' : `${Math.round(km)} km`;
    const edadH = edadHoras(point.observed_at);
    const motivo = edadH != null && edadH > VENTANA_AVISO_H
      ? `El aviso solo mira las últimas ${VENTANA_AVISO_H} h, así que ese foco ya estaba fuera de su ventana.`
      : `No alcanzó el umbral para avisarte: puede ser una quema, una industria o un foco fuera del radio de aviso${edadH == null ? `, o una detección ya fuera de la ventana de ${VENTANA_AVISO_H} h del aviso` : ''}.`;
    return {
      titulo: 'Hubo calor cerca, pero no alcanzó el umbral',
      cuerpo: `Vimos ${n === 1 ? 'un punto de calor' : `${n} puntos de calor`} dentro del doble del radio de tus lugares. El más cercano quedó a ${distancia} de «${place.name}»${vistoHace(edadH)}. ${motivo}`,
      accion: null,
      tono: 'info',
    };
  }
  if (focos.length) {
    const n = new Set(focos.map((f) => f.point)).size;
    return {
      titulo: 'El calor cerca no despierta un aviso',
      cuerpo: `Vimos ${n === 1 ? 'un punto de calor' : `${n} puntos de calor`} dentro del doble del radio de tus lugares, pero BRASA no avisa por ese calor: la señal no era confiable o viene de una fuente fija, como un volcán o una industria.`,
      accion: null,
      tono: 'info',
    };
  }
  return {
    titulo: 'Sin calor cerca',
    cuerpo: `Los satélites no vieron calor dentro del doble del radio de tus lugares en las últimas 48 h. El aviso, además, solo mira las últimas ${VENTANA_AVISO_H} h: un foco más viejo tampoco te habría avisado. Un incendio recién empezado puede tardar en verse: si ves humo o llamas, llama al 130 o al 132.`,
    accion: null,
    tono: 'info',
  };
}
