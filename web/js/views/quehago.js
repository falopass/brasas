/* ¿Qué hago si…? (UX-11): en una emergencia nadie lee una lista larga. La persona toca su
 * situación y recibe dos o tres pasos cortos, los teléfonos y la fuente oficial.
 * Sin recomendaciones propias: cada rama sale del material oficial enlazado al final. */
import { show } from '../map.js';
import { speak, stopSpeak, synth } from '../speak.js';
import { phonesHtml } from '../ui.js';
import { $, fmtDay, html } from '../util.js';

// Cuándo se comprobó que las fuentes de cada rama responden; si cambias un paso o una URL, actualiza esta fecha.
export const REVISADO = '2026-10-23';
// «23 de octubre de 2026», legible en voz alta: se genera de REVISADO, no se repite a mano.
const revisadoLargo = fmtDay(REVISADO, { weekday: undefined, month: 'long', year: 'numeric' });

export const BRANCHES = [
  { q: 'Veo humo o fuego', id: 'humo-o-fuego',
    steps: [
      'Llama ya al 130 (CONAF) o al 132 (Bomberos) y da la ubicación exacta. No esperes a que lo vea BRASA.',
      'Aleja a las personas del lugar. No te acerques al foco ni bloquees los caminos por donde pasan los equipos de emergencia.',
      'Avisa a tus vecinos y a tu familia con un mensaje corto o una llamada breve.',
    ],
    sources: [
      ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
      ['CONAF', 'https://www.conaf.cl/'],
    ] },
  { q: 'Me ordenan evacuar', id: 'evacuar',
    steps: [
      'Sal de inmediato por la ruta que indique la autoridad. No esperes a ver las llamas.',
      'Lleva solo la mochila de emergencia, remedios, documentos y tus mascotas. No vuelvas a buscar cosas.',
      'Sigue a SENAPRED: las órdenes llegan por mensaje de emergencia al celular, por radio y en su sitio. No regreses hasta que la autoridad lo permita.',
    ],
    sources: [
      ['SENAPRED: alertas vigentes', 'https://senapred.cl/alertas/'],
      ['SENAPRED: incendios forestales', 'https://senapred.cl/incendios-forestales/'],
    ] },
  { q: 'Hay alguien que no puede salir solo', id: 'no-puede-salir',
    steps: [
      'Avisa ahora a un vecino o familiar cercano y acuerden quién la ayuda a salir. No lo dejes para después.',
      'Avisa a tu municipio (oficina de inclusión, discapacidad o salud): pregunta si tienen un registro de personas que necesitan ayuda para evacuar.',
      'Ten listos sus remedios, documentos y una salida que pueda usar. Salgan temprano, sin esperar la orden de evacuar.',
    ],
    sources: [
      ['SENADIS: qué hacer en caso de emergencia', 'https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia'],
      ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
    ] },
  { q: 'Tengo animales o animales de granja', id: 'animales',
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
  { q: 'Hay humo y no veo fuego', id: 'humo-sin-fuego',
    steps: [
      'Cierra ventanas y evita la actividad física al aire libre mientras el humo esté denso.',
      'Si tienes que salir, usa mascarilla N95 o KN95 y ropa de manga larga.',
      'Si el humo te alcanza, busca un lugar despejado sin vegetación, cúbrete nariz y boca y llama al 132.',
    ],
    sources: [
      ['SENAPRED: humo de incendios forestales', 'https://senapred.cl/humo-de-incendio-forestal/'],
      ['MINSAL: qué hacer ante incendios forestales', 'https://degreyd.minsal.cl/que-hacer-en-caso-de-incendios-forestales/'],
    ] },
  { q: 'Hay humo y en casa hay una persona sensible al humo', id: 'humo-personas-sensibles',
    steps: [
      'Si alguien en tu casa está embarazada, es niño o persona mayor, o tiene asma o EPOC, MINSAL aconseja salir del domicilio y trasladarse a una zona con menos humo.',
      'Si se quedan porque no hay orden de evacuar: cierra puertas y ventanas, no fumes ni prendas velas o inciensos y eviten el esfuerzo físico. Quien tiene una enfermedad respiratoria crónica debe seguir las indicaciones de su médico.',
      'Consulta en un centro de salud si aparece tos persistente, silbidos al respirar, mareos, vómitos, debilidad o ardor en los ojos. Si a alguien le cuesta respirar, vayan a un servicio de urgencias.',
    ],
    sources: [
      ['MINSAL: qué hacer ante incendios forestales', 'https://degreyd.minsal.cl/que-hacer-en-caso-de-incendios-forestales/'],
      ['SENAPRED: humo de incendios forestales', 'https://senapred.cl/humo-de-incendio-forestal/'],
    ] },
  { q: 'Se cortó la luz, el agua o la señal', id: 'sin-luz-agua-senal',
    steps: [
      'Abre el kit de emergencia: linterna con baterías, radio a pilas y baterías adicionales. Debe alcanzar para 48 a 72 horas.',
      'Cuida el agua guardada: el kit considera dos litros por persona al día, más dos litros adicionales, y cloro o tabletas para purificar el agua.',
      'Sin señal, manda el plan escrito: el directorio de contactos del Plan Familia Preparada (familiares, vecinos, servicios de emergencia y salud) y los roles de cada integrante dicen a quién avisar y quién hace qué.',
    ],
    sources: [
      ['SENAPRED: Kit de Emergencia', 'https://senapred.cl/kit-de-emergencia/'],
      ['SENAPRED: Familia Preparada', 'https://senapred.cl/familia-preparada/'],
    ] },
  { q: 'Vivo en el campo y veo el fuego acercarse', id: 'campo',
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
  async mount(container, { rest } = {}) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`
      <h1 class="view-title">¿Qué hago si…?</h1>
      <p class="lede">Toca lo que está pasando y te damos solo los pasos que importan ahora.</p>
      <p class="tiny muted">Fuentes comprobadas el ${revisadoLargo}. Ante una emergencia manda la autoridad: sigue a SENAPRED.</p>
      ${phonesHtml()}
      <h2 class="section">¿Qué está pasando?</h2>
      ${BRANCHES.map((b, i) => html`<details class="fold" id="quehago-${b.id}"><summary>${b.q}</summary><div>
        <ol class="steps">${b.steps.map((s) => html`<li>${s}</li>`)}</ol>
        ${synth ? html`<button class="btn btn-sm btn-speak" type="button" data-listen="${i}" aria-label="Escuchar los pasos: ${b.q}">Escuchar</button>` : ''}
        <button class="btn btn-sm" type="button" data-share="${i}" aria-label="Enviar estos pasos: ${b.q}">Enviar estos pasos</button>
        <p class="tiny muted" role="status" data-share-status="${i}"></p>
        <p class="tiny muted">${b.sources.length > 1 ? 'Fuentes' : 'Fuente'}: ${b.sources.map(([name, url], j) => html`${j ? ' · ' : ''}<a href="${url}" target="_blank" rel="noopener">${name} ↗</a>`)}</p>
        ${b.link ? html`<a class="btn btn-sm" style="margin-top:8px" href="${b.link[1]}">${b.link[0]}</a>` : ''}
      </div></details>`)}
      <p class="tiny muted">Las instrucciones de SENAPRED, CONAF, Bomberos y tu municipio siempre prevalecen. Si ya sabes qué hacer, actúa: BRASA es una ayuda ciudadana, no una alerta oficial.</p>`);
    container.querySelectorAll('[data-listen]').forEach((btn) => {
      const b = BRANCHES[Number(btn.dataset.listen)];
      btn.addEventListener('click', () => speak(`${b.q}. ${b.steps.join(' ')}`, btn));
    });
    // «Enviar estos pasos»: Web Share si existe; si no, el portapapeles. El aviso sale en el
    // role="status" de la misma rama; cancelar el diálogo de compartir (AbortError) no es un error.
    container.querySelectorAll('[data-share]').forEach((btn) => {
      const i = Number(btn.dataset.share);
      const b = BRANCHES[i];
      const status = container.querySelector(`[data-share-status="${i}"]`);
      btn.addEventListener('click', async () => {
        const text = `${b.q}\n\n${b.steps.map((s, j) => `${j + 1}. ${s}`).join('\n')}\n\nhttps://brasa-chile.ddiegosebastianbb.workers.dev/#/quehago/${b.id}\nLas instrucciones de SENAPRED, CONAF y tu municipio siempre prevalecen.`;
        try {
          if (navigator.share) {
            await navigator.share({ text });
            status.textContent = 'Pasos enviados.';
          } else {
            await navigator.clipboard.writeText(text);
            status.textContent = 'Pasos copiados al portapapeles.';
          }
        } catch (err) {
          if (err && err.name === 'AbortError') return;
          status.textContent = 'No se pudieron enviar los pasos. Copia el texto a mano.';
        }
      });
    });
    // Al abrir otra rama la lectura se detiene; también si se pliega la rama que suena.
    // Cada rama tiene su enlace: el hash se actualiza sin recargar ni mover el foco.
    const folds = container.querySelectorAll('details.fold');
    folds.forEach((d, i) => {
      d.addEventListener('toggle', () => {
        if (d.open || d.querySelector('.speaking')) stopSpeak();
        const propio = `#/quehago/${BRANCHES[i].id}`;
        if (d.open) history.replaceState(null, '', propio);
        else if (location.hash === propio) history.replaceState(null, '', '#/quehago');
      });
    });
    // #/quehago/<id> llega en rest[0]: abre solo esa rama; un id desconocido deja la lista cerrada.
    const pedida = BRANCHES.findIndex((b) => b.id === rest?.[0]);
    if (pedida >= 0) {
      folds[pedida].open = true;
      folds[pedida].scrollIntoView({ block: 'start' });
    }
  },
  unmount() { stopSpeak(); },
};
