/* BRASA · tiempos de respuesta oficiales (web/respuesta.html): página pública de solo
 * lectura con las medianas de detección → aviso → despacho calculadas sobre las marcas que
 * CONAF publica en su reporte de incendios (GET /api/opendata/response.json, OPS-23).
 * Solo GET públicos y agregados por temporada, tramo de superficie y comuna:
 * sin mapa, sin token, sin localStorage ni datos personales. */

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

const TZ = 'America/Santiago';
const parseUTC = (s) => new Date(s.endsWith('Z') || s.includes('+') ? s : `${s}Z`);
const fmtNum = (n, digits = 0) => (Number.isFinite(n)
  ? new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits }).format(n) : '—');
const fmtDateTime = (iso) => parseUTC(iso).toLocaleString('es-CL',
  { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });

/* Mediana de minutos legible: «45 min», «2,5 h», «3,2 días». Sin dato → «—». */
const fmtSpan = (m) => (!Number.isFinite(m) ? '—'
  : m < 90 ? `${fmtNum(Math.round(m))} min`
  : m < 2880 ? `${fmtNum(m / 60, 1)} h`
  : `${fmtNum(m / 1440, 1)} días`);

const mediana = (s) => (Number.isFinite(s?.median_min) ? fmtSpan(s.median_min) : '—');
const BUCKET_LABEL = { '<1 ha': 'menos de 1 ha', '1-10': '1 a 10 ha', '10-100': '10 a 100 ha', '>100': 'más de 100 ha' };

class ApiFail extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function get(path) {
  let response;
  try {
    response = await fetch(path);
  } catch {
    throw new ApiFail('Sin conexión con el servidor de BRASA.', 0);
  }
  if (!response.ok) throw new ApiFail(`Error ${response.status}`, response.status);
  return response.json();
}

function statusMsg(text, retry = false) {
  const box = $('#status');
  box.replaceChildren();
  if (text) box.append(text);
  if (retry) {
    const btn = el('button', 'retry', 'Reintentar');
    btn.type = 'button';
    btn.addEventListener('click', load);
    box.append(el('br'), btn);
  }
}

function kpi(label, s) {
  const card = el('div', 'kpi');
  card.append(el('small', null, label), el('strong', null, mediana(s)),
    el('span', null, `${fmtNum(s?.n)} incendios con ambas marcas`));
  return card;
}

function paint(res) {
  if (!res.count) {
    $('#vacio-nota').textContent = res.note || 'Todavía no hay suficientes incendios con horas publicadas.';
    $('#vacio').hidden = false;
  } else {
    $('#season').textContent = res.season || '';
    $('#resumen-n').textContent = `${fmtNum(res.count)} incendios en el reporte de la temporada ${res.season}.`;
    $('#kpis').replaceChildren(
      kpi('De la detección al aviso a los equipos', res.overall?.detection_to_alert),
      kpi('Del aviso al despacho de recursos', res.overall?.alert_to_dispatch));
    $('#resumen').hidden = false;
    if (res.buckets?.length) {
      $('#tabla-tamano').replaceChildren(...res.buckets.map((b) => {
        const tr = el('tr');
        tr.append(el('td', null, BUCKET_LABEL[b.bucket] || b.bucket),
          el('td', 'num', fmtNum(b.n_fires)),
          el('td', 'num', mediana(b.detection_to_alert)),
          el('td', 'num', mediana(b.alert_to_dispatch)));
        return tr;
      }));
      $('#por-tamano').hidden = false;
    }
    if (res.comunas?.length) {
      $('#tabla-comuna').replaceChildren(...res.comunas.map((c) => {
        const tr = el('tr');
        tr.append(el('td', null, c.comuna),
          el('td', 'num', fmtNum(c.n)),
          el('td', 'num', mediana(c.detection_to_alert)));
        return tr;
      }));
      $('#por-comuna').hidden = false;
    }
  }
  $('#metodo').textContent = res.method || '';
  $('#excluidos').textContent = res.count
    ? `Sin marcas calculables: ${fmtNum(res.excluded)} de ${fmtNum(res.count)} incendios del reporte quedan fuera de las medianas.`
    : '';
  const fuente = $('#fuente');
  fuente.replaceChildren();
  fuente.append('Fuente: CONAF / GEPRIF-DEI · ');
  if (res.source_url) {
    const a = el('a', null, res.source || 'reporte público de incendios');
    a.href = res.source_url;
    a.target = '_blank';
    a.rel = 'noopener';
    fuente.append(a);
  } else {
    fuente.append(res.source || 'reporte público de incendios');
  }
  fuente.append(`${res.season ? ` · temporada ${res.season}` : ''}${res.generated_at ? ` · resumen del ${fmtDateTime(res.generated_at)}` : ''}`);
}

async function load() {
  statusMsg('Cargando…');
  const season = new URLSearchParams(location.search).get('season');
  const path = `/api/opendata/response.json${season ? `?season=${encodeURIComponent(season)}` : ''}`;
  try {
    paint(await get(path));
    statusMsg('');
  } catch (err) {
    statusMsg(`No se pudo cargar el resumen de tiempos de respuesta. ${err.message}`, true);
  }
}

load();
