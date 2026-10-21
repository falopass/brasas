/* ¿Qué hago si…? (UX-11): en una emergencia nadie lee una lista larga. La persona toca su
 * situación y recibe dos o tres pasos cortos, los teléfonos y la fuente oficial.
 * Sin recomendaciones propias: cada rama sale del material oficial enlazado al final. */
import { show } from '../map.js';
import { speak, stopSpeak, synth } from '../speak.js';
import { phonesHtml } from '../ui.js';
import { $, html } from '../util.js';

export const BRANCHES = [
  { q: 'Veo humo o fuego',
    steps: [
      'Llama ya al 130 (CONAF) o al 132 (Bomberos) y da la ubicación exacta. No esperes a que lo vea BRASA.',
      'Aleja a las personas del lugar. No te acerques al foco ni bloquees los caminos por donde pasan los equipos de emergencia.',
      'Avisa a tus vecinos y a tu familia con un mensaje corto o una llamada breve.',
    ],
    sources: [
      ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
      ['CONAF', 'https://www.conaf.cl/'],
    ] },
  { q: 'Me ordenan evacuar',
    steps: [
      'Sal de inmediato por la ruta que indique la autoridad. No esperes a ver las llamas.',
      'Lleva solo la mochila de emergencia, remedios, documentos y tus mascotas. No vuelvas a buscar cosas.',
      'Sigue a SENAPRED: las órdenes llegan por mensaje de emergencia al celular, por radio y en su sitio. No regreses hasta que la autoridad lo permita.',
    ],
    sources: [
      ['SENAPRED: alertas vigentes', 'https://senapred.cl/alertas/'],
      ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
    ] },
  { q: 'Hay alguien que no puede salir solo',
    steps: [
      'Avisa ahora a un vecino o familiar cercano y acuerden quién la ayuda a salir. No lo dejes para después.',
      'Avisa a tu municipio (oficina de inclusión, discapacidad o salud): pregunta si tienen un registro de personas que necesitan ayuda para evacuar.',
      'Ten listos sus remedios, documentos y una salida que pueda usar. Salgan temprano, sin esperar la orden de evacuar.',
    ],
    sources: [
      ['SENADIS: qué hacer en caso de emergencia', 'https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia'],
      ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
    ] },
  { q: 'Tengo animales o animales de granja',
    steps: [
      'El plan de traslado se decide antes: vehículo con combustible, animales separados por especie y jaulas o transportadores para los menores.',
      'Si ordenan evacuar, primero las personas: no demores la salida por los animales. Cuando la emergencia da tiempo, el traslado del ganado se coordina con el municipio.',
      'Si un animal queda atrás, déjalo en un lugar seguro con agua y comida, nunca atado, y deja un aviso visible con cuántos y qué animales hay.',
    ],
    sources: [
      ['SENAPRED/SAG: animales de traspatio (PDF)', 'https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5381/Recomendaciones%20Animales%20de%20Traspatio.pdf?sequence=1&isAllowed=y'],
      ['SENAPRED/SAG: animales de producción (PDF)', 'https://bibliogrd.senapred.gob.cl/bitstream/handle/123456789/5380/Recomendaciones%20Animales%20de%20Producci%C3%B3n.pdf?sequence=1&isAllowed=y'],
      ['SENAPRED: Dimensión Animal', 'https://senapred.cl/dimension-animal/'],
    ] },
  { q: 'Hay humo y no veo fuego',
    steps: [
      'Cierra ventanas y evita la actividad física al aire libre mientras el humo esté denso.',
      'Si tienes que salir, usa mascarilla N95 o KN95 y ropa de manga larga.',
      'Si el humo te alcanza, busca un lugar despejado sin vegetación, cúbrete nariz y boca y llama al 132.',
    ],
    sources: [
      ['SENAPRED: humo de incendios forestales', 'https://senapred.cl/humo-de-incendio-forestal/'],
      ['MINSAL: qué hacer ante incendios forestales', 'https://degreyd.minsal.cl/que-hacer-en-caso-de-incendios-forestales/'],
    ] },
  { q: 'Se cortó la luz, el agua o la señal',
    steps: [
      'Abre el kit de emergencia: linterna con baterías, radio a pilas y baterías adicionales. Debe alcanzar para 48 a 72 horas.',
      'Cuida el agua guardada: el kit considera dos litros por persona al día, más dos litros adicionales, y cloro o tabletas para purificar el agua.',
      'Sin señal, manda el plan escrito: el directorio de contactos del Plan Familia Preparada (familiares, vecinos, servicios de emergencia y salud) y los roles de cada integrante dicen a quién avisar y quién hace qué.',
    ],
    sources: [
      ['SENAPRED: Kit de Emergencia', 'https://senapred.cl/kit-de-emergencia/'],
      ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
    ] },
  { q: 'Vivo en el campo y veo el fuego acercarse',
    steps: [
      'Llama al 130 (CONAF) o al 132 (Bomberos) con la ubicación exacta: sector, camino y un punto de referencia. Avisa a los vecinos: en el campo la primera alarma es la gente.',
      'No esperes a ver las llamas para sacar a las personas. Decide hoy qué harás con los animales: si hay tiempo, sácalos por un camino despejado; si no, suéltalos en un lugar sin vegetación, nunca atados.',
      'Si todavía no hay orden de evacuar, deja la casa lista como indica CONAF: retira el pasto seco, las hojas y la leña de alrededor, cierra el gas y las ventanas, y ten el vehículo con la salida despejada.',
    ],
    sources: [
      ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
      ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
      ['CONAF: Comunidades Preparadas', 'https://www.conaf.cl/incendios/prevencion-y-mitigacion/comunidades-preparadas-frente-a-los-incendios-forestales/'],
      ['CONAF: Manual Comunitario 2022', 'https://oficinavirtual.conaf.cl/archivos/recursos/insumos_tecnicos/Proteccion%20de%20Incendios%20Forestales/Manual%20comunitario%20%202022.pdf'],
    ],
    link: ['Ver el riesgo de mi comuna', '#/riesgo'] },
];

export default {
  id: 'quehago',
  nav: false,
  sheet: 'half',
  async mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`
      <h1 class="view-title">¿Qué hago si…?</h1>
      <p class="lede">Toca lo que está pasando y te damos solo los pasos que importan ahora.</p>
      ${phonesHtml()}
      <h2 class="section">¿Qué está pasando?</h2>
      ${BRANCHES.map((b, i) => html`<details class="fold"><summary>${b.q}</summary><div>
        <ol class="steps">${b.steps.map((s) => html`<li>${s}</li>`)}</ol>
        ${synth ? html`<button class="btn btn-sm btn-speak" type="button" data-listen="${i}" aria-label="Escuchar los pasos: ${b.q}">Escuchar</button>` : ''}
        <p class="tiny muted">${b.sources.length > 1 ? 'Fuentes' : 'Fuente'}: ${b.sources.map(([name, url], j) => html`${j ? ' · ' : ''}<a href="${url}" target="_blank" rel="noopener">${name} ↗</a>`)}</p>
        ${b.link ? html`<a class="btn btn-sm" style="margin-top:8px" href="${b.link[1]}">${b.link[0]}</a>` : ''}
      </div></details>`)}
      <p class="tiny muted">Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen. Si ya sabes qué hacer, actúa: BRASA es una ayuda ciudadana, no una alerta oficial.</p>`);
    container.querySelectorAll('[data-listen]').forEach((btn) => {
      const b = BRANCHES[Number(btn.dataset.listen)];
      btn.addEventListener('click', () => speak(`${b.q}. ${b.steps.join(' ')}`, btn));
    });
    // Al abrir otra rama la lectura se detiene; también si se pliega la rama que suena.
    container.querySelectorAll('details.fold').forEach((d) => {
      d.addEventListener('toggle', () => { if (d.open || d.querySelector('.speaking')) stopSpeak(); });
    });
  },
  unmount() { stopSpeak(); },
};
