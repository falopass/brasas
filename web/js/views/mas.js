/* «Más» (UX-80): lo que no cabe en la barra inferior del celular. Las secciones que
 * antes eran pestañas —Prepárate, Historia, Temporada, ¿Qué hago si…? y Calidad— y
 * los accesos que vivían repartidos (ajustes, preguntas, privacidad y las hojas sin
 * mapa), cerrando con los teléfonos de emergencia siempre a mano. */
import { show } from '../map.js';
import { openSettings, phonesHtml } from '../ui.js';
import { $, html, raw } from '../util.js';

/* Íconos de las secciones: los mismos del riel (app.js los usa para la barra);
 * acá se repiten porque importar app.js ejecutaría el arranque de la app. */
const ICONS = {
  preparate: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m9 12 2 2 4-4"/></svg>',
  casos: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  temporada: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M8 20v-6M12 20V6M16 20v-10"/></svg>',
  quehago: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M9.8 9.2a2.3 2.3 0 0 1 4.5.7c0 1.5-2.3 1.9-2.3 3.3"/><path d="M12 16.6v.1"/></svg>',
  calidad: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5 7L14 5l2.5 7H21"/></svg>',
  ajustes: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h9M19 8h1M4 16h3M13 16h7"/><circle cx="16" cy="8" r="2"/><circle cx="10" cy="16" r="2"/></svg>',
  preguntas: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-12.4 7.5L4 20.5l1.5-4.6A8.5 8.5 0 1 1 21 11.5Z"/><path d="M10 9.5a2 2 0 0 1 3.9.6c0 1.3-1.9 1.7-1.9 3"/><path d="M12 15.6v.1"/></svg>',
  privacidad: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/></svg>',
  liviana: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15.5h6"/></svg>',
  imprimir: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 8V3h10v5"/><rect x="4" y="8" width="16" height="8.5" rx="2"/><path d="M7 13.5h10V21H7v-7.5Z"/></svg>',
};

const SECCIONES = [
  { href: '#/preparate', ico: 'preparate', titulo: 'Prepárate', linea: 'Tu plan, tu kit y tu casa, antes de que haga falta.' },
  { href: '#/casos', ico: 'casos', titulo: 'Historia', linea: 'Incendios que marcaron a Chile, reconstruidos hora a hora.' },
  { href: '#/temporada', ico: 'temporada', titulo: 'Temporada', linea: 'Cómo va la temporada de incendios según el reporte oficial de CONAF.' },
  { href: '#/quehago', ico: 'quehago', titulo: '¿Qué hago si…?', linea: 'Solo los pasos que importan en cada emergencia.' },
  { href: '#/calidad', ico: 'calidad', titulo: 'Calidad de los datos', linea: 'De dónde sale cada dato y si llega a tiempo.' },
];

const ACCESOS = [
  { id: 'mas-ajustes', ico: 'ajustes', titulo: 'Ajustes', linea: 'Letra, colores, detalle y modo ahorro.' },
  { href: '/web/preguntas.html', ico: 'preguntas', titulo: 'Preguntas frecuentes', linea: 'Las dudas de siempre, respondidas corto.' },
  { href: '#/privacidad', ico: 'privacidad', titulo: 'Privacidad', linea: 'Qué guarda BRASA en este teléfono y cómo borrarlo.' },
  { href: '/web/lite.html', ico: 'liviana', titulo: 'Versión liviana', linea: 'Sin mapa: lo justo para cuando la señal es mala.' },
  { href: '/web/lista.html', ico: 'imprimir', titulo: 'Hoja para imprimir', linea: 'Los teléfonos y los pasos, en una hoja para el refrigerador.', externo: true },
];

/* Una fila por acceso: ancla real o botón (Ajustes abre su modal, no una ruta). */
const fila = (s) => {
  const inner = html`<span class="mas-ico" aria-hidden="true">${raw(ICONS[s.ico])}</span>
    <span class="grow"><b class="small">${s.titulo}</b><span class="tiny muted" style="display:block">${s.linea}</span></span>`;
  if (s.id) return html`<li><button type="button" class="row-btn" id="${s.id}">${inner}</button></li>`;
  if (s.externo) return html`<li><a class="row-btn" href="${s.href}" target="_blank" rel="noopener">${inner}</a></li>`;
  return html`<li><a class="row-btn" href="${s.href}">${inner}</a></li>`;
};

export default {
  id: 'mas',
  nav: false,
  sheet: 'half',
  mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`
      <h1 class="view-title">Más</h1>
      <p class="lede">Las secciones que no caben en la barra y los accesos de siempre.</p>
      <ul class="list">${SECCIONES.map(fila)}</ul>
      <h2 class="section">Ajustes y accesos</h2>
      <ul class="list">${ACCESOS.map(fila)}</ul>
      <h2 class="section">Emergencias</h2>
      ${phonesHtml()}
      <p class="tiny muted" style="margin-top:10px">BRASA es una ayuda ciudadana, no una alerta oficial: sigue a SENAPRED y a la autoridad local.</p>`);
    $('#mas-ajustes', container).addEventListener('click', openSettings);
  },
};
