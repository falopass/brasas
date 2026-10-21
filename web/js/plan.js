/* Hoja imprimible del plan familiar (UX-41): /web/plan.html la muestra sin ventana
 * emergente, y el mismo texto sirve para «Compartir plan». Lee las mismas claves de
 * localStorage que la app (prefijo «brasa:»): el plan, su fecha de revisión, lo marcado
 * en la mochila y en «Mi casa preparada». Sin imports a propósito: la página queda fuera
 * del precache del service worker, así que las etiquetas se repiten aquí (las mismas de
 * views/preparate.js). */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);

export const PLAN_FIELDS = [
  ['encuentro', 'Punto de encuentro de la familia'],
  ['ruta1', 'Ruta de salida principal'],
  ['ruta2', 'Ruta alternativa'],
  ['contacto', 'Contacto fuera de la zona'],
  ['notas', 'Personas que necesitan ayuda para salir'],
];

const BAG_ITEMS = [
  ['agua', 'Agua para 2 a 3 días: al menos 2 litros por persona al día.'],
  ['comida', 'Alimentos no perecibles y abrelatas.'],
  ['remedios', 'Medicamentos de uso diario, recetas y botiquín.'],
  ['docs', 'Copia de documentos (carnet, escrituras, seguros) en bolsa plástica o en la nube.'],
  ['luz', 'Linterna, radio a pilas y pilas de repuesto.'],
  ['cargador', 'Cargador y batería externa para el celular.'],
  ['mascarilla', 'Mascarillas N95 o KN95 para el humo, y antiparras.'],
  ['ropa', 'Ropa de algodón de manga larga, zapatos cerrados y una frazada.'],
  ['dinero', 'Algo de dinero en efectivo.'],
  ['mascotas', 'Correa, transportador, agua y comida para mascotas.'],
  ['llaves', 'Copia de llaves de la casa y del auto.'],
];

/* La misma lista que HOME_CHECKLIST en views/preparate.js (ítem, texto y fuentes). */
export const HOME_ITEMS = [
  ['techo', 'Limpié techo y canaletas de hojas, ramas y basura seca.', ['casaConaf']],
  ['zona1', 'Dejé una franja de al menos 1,5 m alrededor de la casa sin material que arda (leña, pasto seco, muebles, plásticos).', ['casaConaf']],
  ['poda', 'Podé ramas a menos de 3 m del techo y las ramas bajas de los árboles cercanos (hasta ~2 m del suelo).', ['casaConaf']],
  ['pasto', 'Corté el pasto seco y retiré matorrales en un radio de 10 a 30 m, según el terreno.', ['casaConaf', 'manualConaf']],
  ['lena', 'Guardé leña, gas y combustibles lejos de la casa (al menos 10 m).', ['casaConaf']],
  ['cerco', 'Revisé cercos y bodegas de madera pegados a la vivienda.', ['casaConaf']],
  ['agua', 'Tengo manguera que alcanza todo el perímetro y una fuente de agua identificada.', ['casaConaf']],
  ['acceso', 'El acceso está despejado para que entren vehículos de emergencia, y el número de la casa se ve desde la calle.', ['manualConaf']],
  ['vecinos', 'Conversé con mis vecinos sobre cómo avisarnos y ayudarnos (personas mayores, con discapacidad o sin vehículo).', ['comunidadConaf']],
];

/* Las fuentes van al pie como texto porque la hoja impresa no tiene enlaces. */
const HOME_SRC = {
  casaConaf: 'conafprevencionincendios.cl/documento/manuales',
  manualConaf: 'Manual Comunitario CONAF 2022 (oficinavirtual.conaf.cl)',
  comunidadConaf: 'conaf.cl/incendios (Comunidades Preparadas)',
};

const PHONES = [
  ['130', 'CONAF · incendios forestales'],
  ['132', 'Bomberos'],
  ['131', 'SAMU · ambulancia'],
  ['133', 'Carabineros'],
];

const FUENTES = 'Fuentes oficiales: senapred.cl/familia-preparada · senapred.cl/kit-de-emergencia · conaf.cl/incendios (Comunidades Preparadas)';

const lee = (key, fallback) => {
  try {
    const v = localStorage.getItem(`brasa:${key}`);
    return v === null ? fallback : JSON.parse(v);
  } catch { return fallback; }
};

export const fmtRevision = (iso) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleDateString('es-CL', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'America/Santiago' })
    : 'sin registro';
};

/* El plan como texto plano, para navigator.share o el portapapeles. */
export function planText(plan = {}, checks = {}) {
  return [
    'Plan familiar de emergencia por incendio (BRASA Chile)', '',
    ...PLAN_FIELDS.map(([k, label]) => `${label}: ${String(plan[k] || '').trim() || '—'}`), '',
    'Mochila de emergencia:',
    ...BAG_ITEMS.map(([k, t]) => `${checks[k] ? '[x]' : '[ ]'} ${t}`), '',
    'Emergencias: CONAF 130 · Bomberos 132 · SAMU 131 · Carabineros 133', '',
    FUENTES,
  ].join('\n');
}

/* La hoja en HTML. Las clases (.meet, .phones, .bag…) las define /web/css/lista.css
 * y el <style> de plan.html; todo valor guardado por la usuaria se escapa. */
export function planSheet(plan = {}, checks = {}, updated = '') {
  const campos = PLAN_FIELDS.map(([k, label]) => {
    const v = String(plan[k] || '').trim();
    const celda = v ? `<span class="val">${escapeHtml(v)}</span>` : '<span class="blank" aria-hidden="true"></span>';
    return `<p class="meet"><b>${escapeHtml(label)}:</b>${celda}</p>`;
  }).join('');
  const casa = checks.casa || {};
  const mochila = BAG_ITEMS.map(([k, t]) => `<li>${checks[k] ? '[x]' : '[ ]'} ${escapeHtml(t)}</li>`).join('');
  const casaItems = HOME_ITEMS.map(([k, t]) => `<li>${casa[k] ? '[x]' : '[ ]'} ${escapeHtml(t)}</li>`).join('');
  const phones = PHONES.map(([n, l]) => `<li><b>${n}</b><span>${escapeHtml(l)}</span></li>`).join('');
  const fuentesCasa = [...new Set(HOME_ITEMS.flatMap(([, , srcs]) => srcs))]
    .filter((k) => k !== 'comunidadConaf') // Comunidades Preparadas ya está en FUENTES
    .map((k) => HOME_SRC[k]).join(' · ');
  return `<header><h1>Plan familiar de emergencia por incendio</h1>
    <p class="brand">BRASA Chile · pégalo en un lugar visible</p></header>
  <p class="official"><b>Si la autoridad ordena evacuar, salgan de inmediato.</b> Sigan las instrucciones de SENAPRED y del municipio.</p>
  <section aria-labelledby="plan-h"><h2 id="plan-h">Nuestro plan</h2>${campos}
    <p class="note">Última revisión: ${escapeHtml(fmtRevision(updated))}</p></section>
  <section aria-labelledby="tel-h"><h2 id="tel-h">Teléfonos de emergencia</h2>
    <ul class="phones">${phones}</ul></section>
  <section aria-labelledby="kit-h"><h2 id="kit-h">Mochila de emergencia</h2>
    <ul class="bag">${mochila}</ul></section>
  <section aria-labelledby="casa-h"><h2 id="casa-h">Mi casa preparada</h2>
    <ul class="bag">${casaItems}</ul></section>
  <footer><p class="tiny">${FUENTES}.</p>
    <p class="tiny">Preparación de la casa: ${fuentesCasa}.</p></footer>`;
}

/* En /web/plan.html: pinta la hoja con lo guardado en este dispositivo. */
const host = typeof document !== 'undefined' && document.getElementById('sheet');
if (host) {
  host.innerHTML = planSheet(lee('plan', {}), { ...lee('check:mochila', {}), casa: lee('check:casa', {}) }, lee('plan_updated', ''));
  document.getElementById('imprimir')?.addEventListener('click', () => window.print());
}
