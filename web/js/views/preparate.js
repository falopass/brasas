/* Prepárate: prevención, plan familiar, casa preparada y qué hacer. La mayoría de los incendios los causan personas. */
import { api } from '../api.js';
import { show } from '../map.js';
import { phonesHtml } from '../ui.js';
import { $, escapeHtml, html, storage } from '../util.js';

const HOME_CHECKLIST = [
  ['techo', 'Limpié techo y canaletas de hojas, ramas y basura seca.'],
  ['zona1', 'Dejé una franja de al menos 1,5 m alrededor de la casa sin material que arda (leña, pasto seco, muebles, plásticos).'],
  ['poda', 'Podé ramas a menos de 3 m del techo y las ramas bajas de los árboles cercanos (hasta ~2 m del suelo).'],
  ['pasto', 'Corté el pasto seco y retiré matorrales en un radio de 10 a 30 m, según el terreno.'],
  ['lena', 'Guardé leña, gas y combustibles lejos de la casa (al menos 10 m).'],
  ['cerco', 'Revisé cercos y bodegas de madera pegados a la vivienda.'],
  ['agua', 'Tengo manguera que alcanza todo el perímetro y una fuente de agua identificada.'],
  ['acceso', 'El acceso está despejado para que entren vehículos de emergencia, y el número de la casa se ve desde la calle.'],
  ['vecinos', 'Conversé con mis vecinos sobre cómo avisarnos y ayudarnos (personas mayores, con discapacidad o sin vehículo).'],
];

const BAG_CHECKLIST = [
  ['agua', 'Agua para 3 días (unos 4 litros por persona al día).'],
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

function checklist(id, items) {
  const state = storage.get(`check:${id}`, {});
  const done = items.filter(([k]) => state[k]).length;
  return html`<div class="progress" aria-hidden="true"><i style="width:${Math.round((done / items.length) * 100)}%"></i></div>
    <p class="tiny muted" style="margin:6px 0 4px" id="${id}-count">${done} de ${items.length} listos</p>
    <ul class="checklist" data-list="${id}">${items.map(([k, text]) => html`<li class="${state[k] ? 'done' : ''}">
      <input type="checkbox" id="${id}-${k}" data-key="${k}" ${state[k] ? 'checked' : ''} /><label for="${id}-${k}">${text}</label></li>`)}</ul>`;
}

function bindChecklist(container, id, items) {
  const list = container.querySelector(`[data-list="${id}"]`);
  list.addEventListener('change', (e) => {
    const state = storage.get(`check:${id}`, {});
    state[e.target.dataset.key] = e.target.checked;
    storage.set(`check:${id}`, state);
    e.target.closest('li').classList.toggle('done', e.target.checked);
    const done = items.filter(([k]) => state[k]).length;
    container.querySelector(`#${id}-count`).textContent = `${done} de ${items.length} listos`;
    list.previousElementSibling.previousElementSibling.firstElementChild.style.width = `${Math.round((done / items.length) * 100)}%`;
  });
}

const PLAN_FIELDS = [
  ['encuentro', 'Punto de encuentro de la familia', 'Ej.: plaza frente a la escuela'],
  ['ruta1', 'Ruta de salida principal', 'Ej.: Av. Principal hacia el centro'],
  ['ruta2', 'Ruta alternativa', 'Ej.: camino interior hacia la carretera'],
  ['contacto', 'Contacto fuera de la zona', 'Nombre y teléfono'],
  ['notas', 'Personas que necesitan ayuda para salir', 'Ej.: abuela, vecino con movilidad reducida'],
];

function printPlan() {
  const plan = storage.get('plan', {});
  const bag = storage.get('check:mochila', {});
  const w = window.open('', '_blank');
  if (!w) return;
  const rows = PLAN_FIELDS.map(([k, label]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(plan[k] || '________________________________')}</td></tr>`).join('');
  const bagRows = BAG_CHECKLIST.map(([k, t]) => `<li>${bag[k] ? '[X]' : '[ ]'} ${escapeHtml(t)}</li>`).join('');
  w.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Plan de emergencia · BRASA Chile</title>
    <style>body{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;color:#111;line-height:1.4}h1{font-size:22px;margin:0}
    table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border:1px solid #bbb;padding:8px;text-align:left;vertical-align:top}th{width:38%;background:#f3f1ec}
    .phones{display:flex;gap:8px;flex-wrap:wrap}.phones div{border:2px solid #d03b3b;border-radius:8px;padding:6px 10px}.phones b{font-size:20px;display:block}
    ul{padding-left:18px}small{color:#555}</style></head><body>
    <h1>Plan familiar de emergencia por incendio</h1><small>Preparado con BRASA Chile · pégalo en un lugar visible</small>
    <table>${rows}</table>
    <h2>Números de emergencia</h2><div class="phones"><div><b>130</b>CONAF</div><div><b>132</b>Bomberos</div><div><b>131</b>SAMU</div><div><b>133</b>Carabineros</div></div>
    <h2>Mochila de emergencia</h2><ul>${bagRows}</ul>
    <p><b>Si la autoridad ordena evacuar, salgan de inmediato.</b> Sigan las instrucciones de SENAPRED y del municipio.</p>
    </body></html>`);
  w.document.close();
  // La ventana hereda la política de seguridad (sin scripts en línea): se imprime desde aquí.
  w.focus();
  w.print();
}

async function priorityBlock(container) {
  const host = container.querySelector('#priority');
  try {
    const data = await api.priorityComunas();
    host.innerHTML = String(data.verified && data.comunas.length
      ? html`<p class="small">${data.title}: ${data.comunas.length} comunas. Fuente: <a href="${data.source_url}" target="_blank" rel="noopener">${data.source}</a>.</p>`
      : html`<div class="callout small"><b>${data.title}.</b> ${data.note}</div>`);
  } catch { host.textContent = ''; }
}

export default {
  id: 'preparate',
  sheet: 'full',
  async mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event', 'explore'], false);
    $('#map-legend').innerHTML = '';
    const plan = storage.get('plan', {});
    container.innerHTML = String(html`
      <h1 class="view-title">El verano se prepara antes</h1>
      <p class="lede">En Chile, la gran mayoría de los incendios forestales los causan personas, por descuido o de forma intencional (según CONAF, sobre el 95 %). Prevenir y prepararse salva casas y vidas.</p>
      ${phonesHtml()}
      <h2 class="section">Mi casa o parcela preparada</h2>
      <p class="small muted">Tu avance se guarda solo en este dispositivo.</p>
      ${checklist('casa', HOME_CHECKLIST)}
      <h2 class="section">Mochila de emergencia</h2>
      ${checklist('mochila', BAG_CHECKLIST)}
      <h2 class="section">Plan familiar</h2>
      <form id="plan" class="card">${PLAN_FIELDS.map(([k, label, ph]) => html`<div class="field"><label for="plan-${k}">${label}</label>
        <input class="input" id="plan-${k}" data-key="${k}" placeholder="${ph}" value="${plan[k] || ''}" maxlength="140" /></div>`)}
        <div class="btn-row"><button type="button" class="btn btn-primary" id="print-plan">Imprimir plan</button><span class="tiny muted" id="plan-saved" style="align-self:center"></span></div></form>
      <h2 class="section">Si hay un incendio cerca</h2>
      <details class="fold" open><summary>Antes: cuando hay riesgo o humo a lo lejos</summary><div><ul>
        <li>Mantente informado por SENAPRED, CONAF, tu municipio y las radios locales. Deja activados los mensajes de emergencia del celular.</li>
        <li>Ten la mochila lista, el auto con combustible y estacionado mirando hacia la salida.</li>
        <li>Ubica a tus mascotas y a las personas que necesitarán ayuda para salir.</li></ul></div></details>
      <details class="fold"><summary>Durante: si la autoridad ordena evacuar</summary><div><ul>
        <li><b>Sal de inmediato</b> por la ruta indicada. No esperes a ver las llamas ni te quedes a defender la casa.</li>
        <li>Cierra puertas y ventanas al salir, desconecta el gas si alcanzas a hacerlo sin demorarte.</li>
        <li>Usa ropa de algodón de manga larga, zapatos cerrados y mascarilla para el humo.</li>
        <li>Si quedas atrapado por el humo, busca un lugar despejado (sin vegetación), cúbrete nariz y boca, y llama al 132.</li>
        <li>No vuelvas a buscar pertenencias.</li></ul></div></details>
      <details class="fold"><summary>Después: al volver</summary><div><ul>
        <li>Regresa solo cuando la autoridad lo permita. Puede haber brasas ocultas, árboles inestables y cables cortados.</li>
        <li>Revisa techos, entretechos y bodegas por focos encendidos durante los días siguientes.</li>
        <li>Después de un incendio, los cerros quemados absorben menos agua: con lluvias intensas aumenta el riesgo de aluviones y deslizamientos.</li></ul></div></details>
      <h2 class="section">Prevenir</h2>
      <details class="fold" open><summary>Lo que nunca debes hacer en verano</summary><div><ul>
        <li>Quemar basura, pastizales o rastrojos sin autorización. Las quemas agrícolas requieren aviso a CONAF y pueden prohibirse en días de alto riesgo.</li>
        <li>Usar esmeriles, soldadoras o cortadoras cerca de pasto seco, sobre todo en días de calor y viento.</li>
        <li>Hacer fogatas o asados fuera de lugares habilitados, o botar colillas encendidas.</li>
        <li>Dejar vidrios y basura en el campo, o elevar globos de papel con fuego.</li></ul>
        <a class="btn btn-sm" href="https://www.conaf.cl/" target="_blank" rel="noopener">Quemas y prevención en CONAF ↗</a></div></details>
      <details class="fold"><summary>Denunciar a quien provoca un incendio</summary><div>
        <p>Si ves a alguien iniciando fuego, llama al <b>130</b> o al <b>133</b>. Para denunciar de forma anónima, usa <b>Denuncia Seguro *4242</b>. Indica lugar, hora y una descripción; no te expongas.</p></div></details>
      <h2 class="section">Para colegios y juntas de vecinos</h2>
      <div class="card small"><p><b>Una actividad de 30 minutos:</b> revisen juntos el mapa de riesgo de la comuna en BRASA, identifiquen las rutas de salida del barrio y los puntos de encuentro, y completen el plan familiar para llevarlo a casa.</p>
        <p class="muted">Usa el botón «Imprimir plan» para entregar una hoja por familia.</p></div>
      <h2 class="section">Comunas prioritarias</h2>
      <div id="priority"><p class="small muted">Cargando…</p></div>
      <h2 class="section">Lo que viene en BRASA</h2>
      <div class="callout small"><b>Lluvias y aluviones después del fuego.</b> El suelo quemado absorbe mucho menos agua. Con la zona quemada, la pendiente del cerro y la lluvia pronosticada, BRASA podrá avisar dónde hay riesgo de aluvión el invierno siguiente.<span class="x-tech"> Variables: área quemada, pendiente (DEM), precipitación pronosticada e isoterma 0 °C.</span></div>
      <p class="tiny muted" style="margin-top:14px">Recomendaciones generales de preparación. Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen.</p>`);
    bindChecklist(container, 'casa', HOME_CHECKLIST);
    bindChecklist(container, 'mochila', BAG_CHECKLIST);
    container.querySelector('#plan').addEventListener('input', (e) => {
      const current = storage.get('plan', {});
      current[e.target.dataset.key] = e.target.value;
      storage.set('plan', current);
      container.querySelector('#plan-saved').textContent = 'Guardado en este dispositivo.';
    });
    container.querySelector('#print-plan').addEventListener('click', printPlan);
    priorityBlock(container);
  },
};
