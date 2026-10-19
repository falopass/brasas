/* Prepárate: prevención, plan familiar, casa preparada y qué hacer. La mayoría de los incendios los causan personas. */
import { api } from '../api.js';
import { show } from '../map.js';
import { phonesHtml } from '../ui.js';
import { $, dual, escapeHtml, html, storage } from '../util.js';

/* Fuentes oficiales citadas recomendación por recomendación (CONT-05). Listadas en docs/FUENTES.md. */
const SRC = {
  casaConaf: ['CONAF: cómo preparar la casa y el entorno', 'https://www.conafprevencionincendios.cl/documento/manuales/'],
  manualConaf: ['CONAF: Manual Comunitario 2022 (PDF)', 'https://oficinavirtual.conaf.cl/archivos/recursos/insumos_tecnicos/Proteccion%20de%20Incendios%20Forestales/Manual%20comunitario%20%202022.pdf'],
  comunidadConaf: ['CONAF: Comunidades Preparadas', 'https://www.conaf.cl/incendios/prevencion-y-mitigacion/comunidades-preparadas-frente-a-los-incendios-forestales/'],
  kitSenapred: ['SENAPRED: kit de emergencia', 'https://senapred.cl/kit-de-emergencia/'],
  familiaSenapred: ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
  incendioSenapred: ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
  humoSenapred: ['SENAPRED: humo de incendios forestales', 'https://senapred.cl/humo-de-incendio-forestal/'],
  mascotasSenapred: ['SENAPRED: kit de emergencia para mascotas (PDF)', 'https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/3342/01_kit_emergencia_mascotas_SENAPRED%202023.pdf?sequence=5&isAllowed=y'],
  minsal: ['MINSAL: qué hacer ante incendios forestales', 'https://degreyd.minsal.cl/que-hacer-en-caso-de-incendios-forestales/'],
};

const srcs = (keys) => html`<span class="tiny muted" style="display:block">${keys.length > 1 ? 'Fuentes' : 'Fuente'}: ${keys.map((k, i) => html`${i ? ' · ' : ''}<a href="${SRC[k][1]}" target="_blank" rel="noopener">${SRC[k][0]} ↗</a>`)}</span>`;

const HOME_CHECKLIST = [
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

const BAG_CHECKLIST = [
  ['agua', 'Agua para 2 a 3 días: al menos 2 litros por persona al día.', ['kitSenapred']],
  ['comida', 'Alimentos no perecibles y abrelatas.', ['kitSenapred']],
  ['remedios', 'Medicamentos de uso diario, recetas y botiquín.', ['kitSenapred']],
  ['docs', 'Copia de documentos (carnet, escrituras, seguros) en bolsa plástica o en la nube.', ['kitSenapred']],
  ['luz', 'Linterna, radio a pilas y pilas de repuesto.', ['kitSenapred']],
  ['cargador', 'Cargador y batería externa para el celular.', ['manualConaf']],
  ['mascarilla', 'Mascarillas N95 o KN95 para el humo, y antiparras.', ['humoSenapred']],
  ['ropa', 'Ropa de algodón de manga larga, zapatos cerrados y una frazada.', ['kitSenapred', 'incendioSenapred']],
  ['dinero', 'Algo de dinero en efectivo.', ['kitSenapred']],
  ['mascotas', 'Correa, transportador, agua y comida para mascotas.', ['mascotasSenapred']],
  ['llaves', 'Copia de llaves de la casa y del auto.', ['kitSenapred']],
];

/* UX-18: con `scored`, la lista es una autoevaluación. Puntaje = % de ítems marcados sobre el total;
   todos pesan igual. El avance queda en localStorage (`brasa:check:<id>`), solo en este dispositivo. */
function checklist(id, items, scored = false) {
  const state = storage.get(`check:${id}`, {});
  const done = items.filter(([k]) => state[k]).length;
  const pct = Math.round((done / items.length) * 100);
  const next = scored ? items.find(([k]) => !state[k]) : null;
  const bar = html`<div class="progress" data-bar="${id}" aria-hidden="true"><i style="width:${pct}%"></i></div>`;
  return html`${scored ? html`<div class="scorebar"><span class="score-pill" id="${id}-score" aria-live="polite">${pct}/100</span>${bar}</div>` : bar}
    <p class="tiny muted" style="margin:6px 0 4px"><span id="${id}-count">${done} de ${items.length} listos</span>${scored ? html` · <button type="button" class="reset-link" id="${id}-reset">Empezar de nuevo</button>` : ''}</p>
    ${scored ? html`<p class="small" id="${id}-next">${next ? html`Siguiente paso: ${next[1]}` : 'Tu casa está lista; ahora el plan familiar.'}</p>` : ''}
    <ul class="checklist" data-list="${id}">${items.map(([k, text, src]) => html`<li class="${state[k] ? 'done' : ''}">
      <input type="checkbox" id="${id}-${k}" data-key="${k}" ${state[k] ? 'checked' : ''} /><div><label for="${id}-${k}">${text}</label>${srcs(src)}</div></li>`)}</ul>`;
}

function bindChecklist(container, id, items, scored = false) {
  const list = container.querySelector(`[data-list="${id}"]`);
  const bar = container.querySelector(`[data-bar="${id}"]`).firstElementChild;
  const refresh = () => {
    const state = storage.get(`check:${id}`, {});
    const done = items.filter(([k]) => state[k]).length;
    const pct = Math.round((done / items.length) * 100);
    bar.style.width = `${pct}%`;
    container.querySelector(`#${id}-count`).textContent = `${done} de ${items.length} listos`;
    if (!scored) return;
    container.querySelector(`#${id}-score`).textContent = `${pct}/100`;
    const next = items.find(([k]) => !state[k]);
    container.querySelector(`#${id}-next`).textContent = next ? `Siguiente paso: ${next[1]}` : 'Tu casa está lista; ahora el plan familiar.';
  };
  list.addEventListener('change', (e) => {
    const state = storage.get(`check:${id}`, {});
    state[e.target.dataset.key] = e.target.checked;
    storage.set(`check:${id}`, state);
    e.target.closest('li').classList.toggle('done', e.target.checked);
    refresh();
  });
  container.querySelector(`#${id}-reset`)?.addEventListener('click', () => {
    storage.set(`check:${id}`, {});
    for (const input of list.querySelectorAll('input')) input.checked = false;
    for (const li of list.querySelectorAll('.done')) li.classList.remove('done');
    refresh();
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
    <small>Fuentes oficiales: senapred.cl/familia-preparada · senapred.cl/kit-de-emergencia · conaf.cl/incendios (Comunidades Preparadas)</small>
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
      <p class="lede">En Chile, la gran mayoría de los incendios forestales los causan personas, por descuido o de forma intencional (el 99 % tiene origen humano, según <a href="${SRC.incendioSenapred[1]}" target="_blank" rel="noopener">SENAPRED ↗</a>). Prevenir y prepararse salva casas y vidas.</p>
      ${phonesHtml()}
      <h2 class="section">Mi casa o parcela preparada</h2>
      <p class="small muted">Tu avance se guarda solo en este dispositivo.</p>
      ${checklist('casa', HOME_CHECKLIST, true)}
      <h2 class="section">Mochila de emergencia</h2>
      ${checklist('mochila', BAG_CHECKLIST)}
      <h2 class="section">Plan familiar</h2>
      <form id="plan" class="card">${PLAN_FIELDS.map(([k, label, ph]) => html`<div class="field"><label for="plan-${k}">${label}</label>
        <input class="input" id="plan-${k}" data-key="${k}" placeholder="${ph}" value="${plan[k] || ''}" maxlength="140" /></div>`)}
        <div class="btn-row"><button type="button" class="btn btn-primary" id="print-plan">Imprimir plan</button><a class="btn btn-sm" href="/lista.html">Hoja para imprimir / refrigerador</a><span class="tiny muted" id="plan-saved" style="align-self:center"></span></div></form>
      ${srcs(['familiaSenapred', 'manualConaf'])}
      <h2 class="section">Si hay un incendio cerca</h2>
      <details class="fold" open><summary>Antes: cuando hay riesgo o humo a lo lejos</summary><div><ul>
        <li>Mantente informado por SENAPRED, CONAF, tu municipio y las radios locales. Deja activados los mensajes de emergencia del celular.${srcs(['incendioSenapred', 'manualConaf'])}</li>
        <li>Ten la mochila lista, el auto con combustible y estacionado mirando hacia la salida.${srcs(['kitSenapred', 'manualConaf'])}</li>
        <li>Ubica a tus mascotas y a las personas que necesitarán ayuda para salir.${srcs(['familiaSenapred', 'mascotasSenapred'])}</li></ul></div></details>
      <details class="fold"><summary>Durante: si la autoridad ordena evacuar</summary><div><ul>
        <li><b>Sal de inmediato</b> por la ruta indicada. No esperes a ver las llamas ni te quedes a defender la casa.${srcs(['minsal', 'incendioSenapred'])}</li>
        <li>Si la instrucción es evacuar a pie, sal a pie: los autos atascan las calles por donde pasan Bomberos y otros vecinos.${srcs(['incendioSenapred', 'minsal'])}</li>
        <li>Lleva a tus mascotas. Si de verdad no puedes, no las dejes amarradas ni encerradas: suéltalas para que puedan escapar.${srcs(['incendioSenapred', 'mascotasSenapred'])}</li>
        <li>Avisa a tu familia por mensaje de texto o WhatsApp en vez de llamar: las líneas se saturan y las necesitan las emergencias.${srcs(['incendioSenapred', 'manualConaf'])}</li>
        <li>Cierra puertas y ventanas al salir, desconecta el gas si alcanzas a hacerlo sin demorarte.${srcs(['minsal', 'manualConaf'])}</li>
        <li>Usa ropa de algodón de manga larga, zapatos cerrados y mascarilla para el humo.${srcs(['incendioSenapred', 'humoSenapred'])}</li>
        <li>Si quedas atrapado por el humo, busca un lugar despejado (sin vegetación), cúbrete nariz y boca, y llama al 132.${srcs(['humoSenapred', 'incendioSenapred'])}</li>
        <li>No vuelvas a buscar pertenencias. No regreses porque ya no ves llamas: el fuego puede rebrotar o cambiar de dirección.${srcs(['incendioSenapred'])}</li>
        <li>Si te sorprende el fuego en un parque o sendero, sigue a los guardaparques y aléjate hacia zonas sin vegetación. No subas laderas: el fuego sube más rápido de lo que corres.${srcs(['incendioSenapred', 'manualConaf'])}</li></ul></div></details>
      <details class="fold"><summary>Después: al volver</summary><div><ul>
        <li>Regresa solo cuando la autoridad lo permita. Puede haber brasas ocultas, árboles inestables y cables cortados.${srcs(['incendioSenapred', 'manualConaf'])}</li>
        <li>Revisa techos, entretechos y bodegas por focos encendidos durante los días siguientes.${srcs(['manualConaf'])}</li>
        <li>Después de un incendio, los cerros quemados absorben menos agua: con lluvias intensas aumenta el riesgo de aluviones y deslizamientos.${srcs(['manualConaf'])}</li></ul></div></details>
      <h2 class="section">Si necesitas ayuda para salir</h2>
      <div class="card"><p class="small">Si en tu casa hay una persona con discapacidad, con movilidad reducida o que depende de un equipo o un tratamiento, preparen su salida con tiempo.</p>
        <ul>
          <li><b>Una red de apoyo con nombre y teléfono.</b> Familiares, amigos o vecinos que sepan cómo ayudarte: mover una silla de ruedas, darte un medicamento o avisar a quien no oye o no ve. Anótalos en el plan familiar de arriba. <span class="tiny muted">Fuentes: <a href="https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia" target="_blank" rel="noopener">SENADIS ↗</a> · <a href="https://senapred.cl/familia-preparada/" target="_blank" rel="noopener">SENAPRED: Familia Preparada ↗</a></span></li>
          <li><b>Pregunta en tu municipalidad.</b> En la oficina de inclusión o discapacidad (o en salud municipal), consulta si tienen un registro o protocolo para las personas que pueden necesitar ayuda para evacuar: la guía oficial pide a los municipios considerarlas en sus planes comunales, pero cada comuna tiene su propio proceso. <span class="tiny muted">Fuente: <a href="https://www.senadis.gob.cl/descarga/i/8212/documento" target="_blank" rel="noopener">Guía SENADIS y CITRID (PDF) ↗</a></span></li>
          <li><b>Una salida que puedas usar.</b> Tu ruta de evacuación debe ser accesible y tener una alternativa; mantén despejadas puertas y pasillos. Si vives en edificio, calcula el tiempo y los apoyos para bajar por escaleras. <span class="tiny muted">Fuente: <a href="https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia" target="_blank" rel="noopener">SENADIS ↗</a></span></li>
          <li><b>Medicamentos, documentos y equipos.</b> Suma a la mochila los medicamentos de cada día con copia de las recetas y la información del tratamiento, copia del carnet y, si dependes de un equipo médico, un generador portátil o baterías para mantenerlo encendido. <span class="tiny muted">Fuentes: <a href="https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia" target="_blank" rel="noopener">SENADIS ↗</a> · <a href="https://senapred.cl/kit-de-emergencia/" target="_blank" rel="noopener">SENAPRED: kit de emergencia ↗</a></span></li>
          <li><b>Si recibes un tratamiento médico.</b> Acuerda con tu consultorio u hospital cómo continuarlo si hay que evacuar. <span class="tiny muted">Fuente: <a href="https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia" target="_blank" rel="noopener">SENADIS ↗</a></span></li>
          <li><b>Tu animal de asistencia también.</b> Inclúyelo en el plan con su alimento, su identificación y cómo sale contigo. <span class="tiny muted">Fuente: <a href="https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia" target="_blank" rel="noopener">SENADIS ↗</a></span></li>
        </ul></div>
      <h2 class="section">Mascotas y animales de la parcela</h2>
      <div class="card"><p class="small">${dual('En el campo, los animales son una de las razones por las que la gente duda en evacuar. Decidir hoy qué hacer con ellos te ayuda a salir a tiempo.',
        'En zonas rurales los animales son un motivo frecuente para no evacuar. Estas son las recomendaciones de la Mesa Temática Dimensión Animal (SENAPRED, SAG, INDAP, ODEPA y Colmevet).')}</p>
        <ul>
          <li><b>El plan de traslado se hace antes.</b> ${dual('Anota qué animales tienes y cuántos, dibuja un plano simple de la parcela (casa, corrales, accesos y un lugar seguro) y acuerda quién los saca y cómo: vehículo con combustible, animales separados por especie y jaulas o transportadores para los menores.', 'Listado de especies y cantidad, plano del predio con corrales y zona segura, vehículo con combustible y animales de traspatio en espacios protegidos separados por especie.')} <span class="tiny muted">Fuentes: <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5381/Recomendaciones%20Animales%20de%20Traspatio.pdf?sequence=1&isAllowed=y" target="_blank" rel="noopener">SENAPRED/SAG: animales de traspatio (PDF) ↗</a> · <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5380/Recomendaciones%20Animales%20de%20Producci%C3%B3n.pdf?sequence=1&isAllowed=y" target="_blank" rel="noopener">animales de producción (PDF) ↗</a></span></li>
          <li><b>Si ordenan evacuar, primero las personas.</b> ${dual('No demores tu salida por los animales: en evacuaciones masivas la recomendación oficial es que las personas salgan a pie. Cuando la emergencia da tiempo, el traslado del ganado se coordina con el municipio.', 'En evacuaciones masivas se prioriza la evacuación de personas a pie; en emergencias de manifestación lenta, la evacuación de ganado se coordina con el municipio.')} <span class="tiny muted">Fuentes: <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5381/Recomendaciones%20Animales%20de%20Traspatio.pdf?sequence=1&isAllowed=y" target="_blank" rel="noopener">SENAPRED/SAG: animales de traspatio (PDF) ↗</a> · <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5380/Recomendaciones%20Animales%20de%20Producci%C3%B3n.pdf?sequence=1&isAllowed=y" target="_blank" rel="noopener">animales de producción (PDF) ↗</a></span></li>
          <li><b>Si un animal queda atrás.</b> ${dual('Déjalo en un lugar seguro de la casa o de la parcela, lejos de lo que pueda caerse, con agua y comida; nunca atado ni encerrado. Si vives en un lugar aislado, deja un aviso visible en la puerta con cuántos y qué animales hay, para orientar a los rescatistas.', 'Sitio seguro transitorio con agua y alimento, sin atar ni amarrar; indicación escrita visible con cantidad y especies para los organismos de rescate.')} <span class="tiny muted">Fuente: <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/3345/recomendaciones_tenencia_responsable_mascotas.pdf?sequence=5&isAllowed=y" target="_blank" rel="noopener">SENAPRED: tenencia responsable de mascotas en emergencias (PDF) ↗</a></span></li>
          <li><b>Un kit para ellos también.</b> ${dual('Junto a la mochila de la familia, ten listos su transportador o correa, comida, agua y sus remedios.', 'Kit de emergencia para mascotas: transportador, alimento, agua e insumos de higiene y salud.')} <span class="tiny muted">Fuente: <a href="https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/3342/01_kit_emergencia_mascotas_SENAPRED%202023.pdf?sequence=5&isAllowed=y" target="_blank" rel="noopener">SENAPRED: kit de emergencia para mascotas (PDF) ↗</a></span></li>
        </ul>
        <p class="tiny muted">BRASA no agrega recomendaciones propias: cada punto sale de la fuente oficial enlazada. Todas estas guías están reunidas en <a href="https://senapred.cl/dimension-animal/" target="_blank" rel="noopener">SENAPRED: Dimensión Animal ↗</a>.</p></div>
      <h2 class="section">Prevenir</h2>
      <details class="fold" open><summary>Lo que nunca debes hacer en verano</summary><div><ul>
        <li>Quemar basura, pastizales o rastrojos sin autorización. Las quemas agrícolas requieren aviso a CONAF y pueden prohibirse en días de alto riesgo.${srcs(['incendioSenapred'])}</li>
        <li>Usar esmeriles, soldadoras o cortadoras cerca de pasto seco, sobre todo en días de calor y viento.${srcs(['incendioSenapred'])}</li>
        <li>Hacer fogatas o asados fuera de lugares habilitados, o botar colillas encendidas.${srcs(['incendioSenapred', 'minsal'])}</li>
        <li>Dejar vidrios y basura en el campo, o elevar globos de papel con fuego.${srcs(['minsal'])}</li></ul>
        <a class="btn btn-sm" href="https://www.conaf.cl/" target="_blank" rel="noopener">Quemas y prevención en CONAF ↗</a></div></details>
      <details class="fold"><summary>Denunciar a quien provoca un incendio</summary><div>
        <p>Si ves a alguien iniciando fuego, llama al <b>130</b> o al <b>133</b>. Para denunciar de forma anónima, usa <b>Denuncia Seguro *4242</b>. Indica lugar, hora y una descripción; no te expongas.${srcs(['incendioSenapred'])}</p></div></details>
      <h2 class="section">Para colegios y juntas de vecinos</h2>
      <div class="card small"><p><b>Una actividad de 30 minutos:</b> revisen juntos el mapa de riesgo de la comuna en BRASA, identifiquen las rutas de salida del barrio y los puntos de encuentro, y completen el plan familiar para llevarlo a casa.</p>
        <p class="muted">Usa el botón «Imprimir plan» para entregar una hoja por familia.</p></div>
      <h2 class="section">Comunas prioritarias</h2>
      <div id="priority"><p class="small muted">Cargando…</p></div>
      <h2 class="section">Lo que viene en BRASA</h2>
      <div class="callout small"><b>Lluvias y aluviones después del fuego.</b> El suelo quemado absorbe mucho menos agua. Con la zona quemada, la pendiente del cerro y la lluvia pronosticada, BRASA podrá avisar dónde hay riesgo de aluvión el invierno siguiente.<span class="x-tech"> Variables: área quemada, pendiente (DEM), precipitación pronosticada e isoterma 0 °C.</span></div>
      <p class="tiny muted" style="margin-top:14px">Recomendaciones generales de preparación, cada una enlazada a su fuente oficial. Las instrucciones de <a href="https://senapred.cl/" target="_blank" rel="noopener">SENAPRED ↗</a>, <a href="https://www.conaf.cl/" target="_blank" rel="noopener">CONAF ↗</a>, Bomberos y tu municipio siempre prevalecen.</p>`);
    bindChecklist(container, 'casa', HOME_CHECKLIST, true);
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
