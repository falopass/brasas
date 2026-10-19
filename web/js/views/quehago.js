/* ¿Qué hago si…? (UX-11): en una emergencia nadie lee una lista larga. La persona toca su
 * situación y recibe dos o tres pasos cortos, los teléfonos y la fuente oficial.
 * Sin recomendaciones propias: cada rama sale del material oficial enlazado al final. */
import { show } from '../map.js';
import { phonesHtml } from '../ui.js';
import { $, html } from '../util.js';

const BRANCHES = [
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
      ${BRANCHES.map((b) => html`<details class="fold"><summary>${b.q}</summary><div>
        <ol class="steps">${b.steps.map((s) => html`<li>${s}</li>`)}</ol>
        <p class="tiny muted">${b.sources.length > 1 ? 'Fuentes' : 'Fuente'}: ${b.sources.map(([name, url], i) => html`${i ? ' · ' : ''}<a href="${url}" target="_blank" rel="noopener">${name} ↗</a>`)}</p>
      </div></details>`)}
      <p class="tiny muted">Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen. Si ya sabes qué hacer, actúa: BRASA es una ayuda ciudadana, no una alerta oficial.</p>`);
  },
};
