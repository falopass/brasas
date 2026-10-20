/* Tarjeta breve del estado ENSO (El Niño / La Niña) de la NOAA, para la vista Riesgo. */
import { dual, fmtNum, html, parseUTC, TZ } from './util.js';

export const PHASE_LABEL = { nino: 'El Niño', nina: 'La Niña', neutral: 'Neutral' };

const PHASE_LINE = {
  nino: 'Fase cálida del Pacífico',
  nina: 'Fase fría del Pacífico',
  neutral: 'El Pacífico está en estado neutro',
};

/** HTML de la tarjeta «Cómo viene la temporada» (fase, ONI y trimestre). Cadena vacía si falta
 *  `phase` u `oni` (incluida la respuesta degradada de la API): nunca un valor inventado. */
export function ensoCard(d) {
  if (!d?.phase || d.oni == null) return '';
  const updated = d.updated_at
    ? parseUTC(d.updated_at).toLocaleDateString('es-CL', { day: 'numeric', month: 'short', timeZone: TZ }) : null;
  const facts = [
    PHASE_LABEL[d.phase] || d.phase,
    `ONI ${d.oni > 0 ? '+' : ''}${fmtNum(d.oni, 1)} °C`,
    d.season ? `trimestre ${d.season}${d.year ? ` ${d.year}` : ''}` : null,
    updated ? `actualizado ${updated}` : null,
  ].filter(Boolean).join(' · ');
  return html`<div class="callout" style="margin-top:10px"><b>Cómo viene la temporada · ${facts}</b>
    ${dual(`${PHASE_LINE[d.phase] || 'Estado del Pacífico'}; es contexto de la temporada, no un pronóstico de incendios.`,
      'ONI: anomalía de la temperatura del mar en la región Niño 3.4, media de 3 meses. Inclina la temporada; no predice incendios.')}
    ${d.source_url ? html`<a href="${d.source_url}" target="_blank" rel="noopener">${d.source || 'Fuente'} ↗</a>` : ''}</div>`;
}
