/* Etiquetas y utilidades de incidente compartidas por la portada, las tarjetas y la ficha:
 * módulo liviano para que la vista completa (views/incendio.js) no entre al arranque. */
import { request } from './api.js';
import { storage, toast } from './util.js';

/** Cada estado: tono visual, título y explicación sencilla; la definición exacta, para la lectura detallada. */
export const INCIDENT = {
  anomalia: { tone: 'aviso', short: 'Señal de calor', title: 'Una señal de calor', text: 'Un satélite vio calor una vez. Puede ser un incendio, una quema o una industria: aún no hay más pruebas.', tech: 'Anomalía: una sola detección confiable o solo detecciones de confianza baja.' },
  posible: { tone: 'riesgo', short: 'Posible incendio', title: 'Posible incendio', text: 'Los satélites vieron calor en el mismo lugar más de una vez, o dos satélites distintos lo vieron. Es probable que sea fuego.', tech: 'Posible: ≥ 2 detecciones confiables en momentos distintos, o 2 sensores distintos (p. ej. GOES + VIIRS).' },
  reportado: { tone: 'urgente', short: 'Visto por vecinos', title: 'Posible incendio, también visto por vecinos', text: 'Además del satélite, un vecino avisó de fuego o humo cerca y BRASA revisó su aviso.', tech: 'Reportado: evidencia satelital + reporte ciudadano verificado por moderación a ≤ 3 km.' },
  confirmado: { tone: 'urgente', short: 'Confirmado por CONAF', title: 'Incendio informado por CONAF', text: 'CONAF informa este incendio. Sigue las instrucciones de SENAPRED y de la autoridad local.', tech: 'Confirmado: unido a un incendio del reporte público de CONAF a ≤ 3 km. BRASA no confirma por su cuenta.' },
  controlado: { tone: 'aviso', short: 'Controlado', title: 'Controlado según CONAF', text: 'CONAF lo informa como controlado. Aún puede haber humo o rebrotes.', tech: 'Controlado: según el reporte público de CONAF.' },
  extinguido: { tone: 'tranquilo', short: 'Sin calor nuevo', title: 'Sin calor nuevo', text: 'Los satélites no ven calor aquí hace más de un día. No significa «apagado oficialmente», salvo que CONAF lo informe.', tech: 'Extinguido: 24 h sin detecciones nuevas, o extinguido según CONAF si está unido a su reporte.' },
  descartado: { tone: 'tranquilo', short: 'Descartado', title: 'Punto descartado', text: 'BRASA no lo cuenta como incendio de Chile ni avisa por él.', tech: 'Descartado: el incidente quedó sin comuna chilena —sus detecciones cayeron fuera del país—; la fila se conserva para auditoría y sale con la purga normal.' },
};
const FIXED = { tone: 'tranquilo', short: 'Fuente fija', title: 'Calor de una fuente fija', text: 'Este calor aparece siempre en el mismo lugar (un volcán o una industria). Por eso BRASA no avisa por él.', tech: 'Fuente fija probable: toda la evidencia cae en un volcán activo o en una celda con calor ≥ 8 días de los últimos 30.' };

export const incidentInfo = (inc) => (inc.fixed_source ? FIXED : INCIDENT[inc.status] || INCIDENT.anomalia);

/** ALR-44 «seguir un incendio»: un solo botón para la ficha y las tarjetas del mapa (popup.js).
 *  Sin suscriptor lleva a «avisarme» (`sinCuenta`); `target` = { incident_id, official_ref }. */
export const enlazarSeguimiento = (btn, target, sinCuenta) => {
  if (!btn) return;
  let seg = null;
  const pinta = () => {
    btn.textContent = seg ? 'Dejar de seguir' : 'Seguir este incendio';
    btn.setAttribute('aria-pressed', String(!!seg));
  };
  if (storage.get('token')) {
    request('/api/me/follows', { auth: true }).then(({ follows = [] }) => {
      seg = follows.find((s) => (target.incident_id && s.incident_id === target.incident_id)
        || (target.official_ref && s.official_ref === target.official_ref)) || null;
      pinta();
    }).catch(() => {});
  }
  btn.addEventListener('click', async () => {
    if (!storage.get('token')) { sinCuenta?.(); return; }
    btn.disabled = true;
    try {
      if (seg) {
        await request(`/api/me/follows/${seg.id}`, { method: 'DELETE', auth: true });
        seg = null;
        toast('Dejaste de seguir este incendio.');
      } else {
        seg = (await request('/api/me/follows', { method: 'POST', body: target, auth: true })).follow || target;
        toast('Siguiendo: avisa si CONAF lo confirma, cambia de estado o suma calor.');
      }
      pinta();
    } catch (err) {
      toast(err?.message || 'No se pudo guardar el seguimiento.', 'error');
    } finally { btn.disabled = false; }
  });
};
