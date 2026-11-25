/* Aviso de atmósfera en altura y suelo compartido por la ficha de comuna (riesgo.js) y la
 * del incendio (incendio.js): una sola copia del texto dual y de los umbrales. */
import { ago, dual, fmtDateTime, fmtNum, html, TZ_LABEL } from './util.js';

const HAINES_LEVEL = {
  muy_bajo: { label: 'muy bajo', plain: 'aire estable y húmedo en altura, con poco impulso para que un incendio crezca en columna.' },
  bajo: { label: 'bajo', plain: 'aire relativamente estable en altura, con poco aporte adicional al avance del fuego.' },
  moderado: { label: 'moderado', plain: 'aire seco o algo inestable en altura: un incendio activo puede avivarse con más facilidad.' },
  alto: { label: 'alto', plain: 'aire muy seco e inestable en altura: alto potencial de crecimiento rápido o columna de humo.' },
};

const hainesMeta = (h) => {
  const key = h?.level && HAINES_LEVEL[h.level]
    ? h.level
    : h.index >= 6 ? 'alto' : h.index === 5 ? 'moderado' : h.index === 4 ? 'bajo' : 'muy_bajo';
  return HAINES_LEVEL[key];
};

/** Atmósfera en altura y suelo (Open-Meteo · ECMWF IFS): Índice de Haines (2–6), VPD,
 *  humedad superficial del suelo y CAPE. Vacío si no llega ningún valor numérico válido.
 *  `mt` es el margen superior en px del aviso (cada ficha conserva el suyo). */
export function atmosphereCallout(atmos, mt = 10) {
  if (!atmos || typeof atmos !== 'object') return '';
  const h = atmos.haines && Number.isFinite(atmos.haines.index) ? atmos.haines : null;
  const hasVpd = Number.isFinite(atmos.vpd_kpa);
  const hasSoil1 = Number.isFinite(atmos.soil_moisture_0_to_1cm);
  const hasSoil7 = Number.isFinite(atmos.soil_moisture_0_to_7cm);
  const hasCape = Number.isFinite(atmos.cape_j_kg);
  if (!h && !hasVpd && !hasSoil1 && !hasSoil7 && !hasCape) return '';

  const warn = Boolean((h && h.index >= 5) || (hasVpd && atmos.vpd_kpa >= 3.0));
  const hInfo = h ? hainesMeta(h) : null;

  let hainesLine = '';
  if (h) {
    const hTech = [`Índice de Haines ${fmtNum(h.index, 0)}/6 (${hInfo.label})`];
    if (h.variant || h.levels_hpa) {
      hTech.push([h.variant ? `variante ${h.variant}` : '', h.levels_hpa ? `${h.levels_hpa} hPa` : ''].filter(Boolean).join(' · '));
    }
    if (Number.isFinite(h.stability) && Number.isFinite(h.moisture)) {
      hTech.push(`estabilidad ${fmtNum(h.stability, 0)}/3, humedad ${fmtNum(h.moisture, 0)}/3`);
    }
    if (Number.isFinite(h.lapse_c)) hTech.push(`ΔT ${fmtNum(h.lapse_c, 1)} °C`);
    if (Number.isFinite(h.dewpoint_depression_c)) hTech.push(`T-Td ${fmtNum(h.dewpoint_depression_c, 1)} °C`);
    hainesLine = html`<span class="small" style="display:block;margin-top:4px">${dual(
      `Aire en altura (${hInfo.label}): ${hInfo.plain}`,
      `${hTech.join(' · ')}.`,
    )}</span>`;
  }

  const plainMetrics = [];
  const techMetrics = [];
  if (hasVpd) {
    const vpdLabel = atmos.vpd_kpa >= 3.0 ? 'muy alta' : atmos.vpd_kpa >= 1.5 ? 'alta' : 'moderada o baja';
    plainMetrics.push(`Sequedad del aire: ${vpdLabel} (${fmtNum(atmos.vpd_kpa, 1)} kPa)`);
    techMetrics.push(`VPD ${fmtNum(atmos.vpd_kpa, 2)} kPa`);
  }
  if (hasSoil1 || hasSoil7) {
    const plainSoil = [
      hasSoil1 ? `${fmtNum(atmos.soil_moisture_0_to_1cm * 100, 1)} % (0–1 cm)` : '',
      hasSoil7 ? `${fmtNum(atmos.soil_moisture_0_to_7cm * 100, 1)} % (0–7 cm)` : '',
    ].filter(Boolean).join(' y ');
    const techSoil = [
      hasSoil1 ? `0–1 cm ${fmtNum(atmos.soil_moisture_0_to_1cm, 2)} m³/m³` : '',
      hasSoil7 ? `0–7 cm ${fmtNum(atmos.soil_moisture_0_to_7cm, 2)} m³/m³` : '',
    ].filter(Boolean).join(' · ');
    plainMetrics.push(`Humedad superficial del suelo: ${plainSoil}`);
    techMetrics.push(`Suelo ${techSoil}`);
  }
  if (hasCape) {
    const capeLabel = atmos.cape_j_kg > 1500 ? 'alta' : atmos.cape_j_kg >= 500 ? 'moderada' : 'baja';
    plainMetrics.push(`Inestabilidad para tormentas: ${capeLabel}`);
    techMetrics.push(`CAPE ${fmtNum(atmos.cape_j_kg, 0)} J/kg`);
  }

  const peakText = atmos.observed_at ? `pico previsto ${fmtDateTime(atmos.observed_at)} (${TZ_LABEL})` : '';
  const fetchedAge = atmos.fetched_at ? ago(atmos.fetched_at) : '';
  const fetchedText = fetchedAge && fetchedAge !== 'sin datos' ? `consultado ${fetchedAge}` : '';
  const timeMeta = [peakText, fetchedText].filter(Boolean).join(' · ');
  const srcName = atmos.source?.name || 'Open-Meteo · ECMWF IFS';
  const srcUrl = atmos.source?.url ?? 'https://open-meteo.com/en/docs';

  return html`<div class="callout${warn ? ' callout-warn' : ''}" style="margin-top:${mt}px"><b>${dual(
    h ? `Atmósfera y sequedad · el fuego podría crecer: ${hInfo.label}` : 'Atmósfera y sequedad',
    h ? `Atmósfera en altura y suelo · Haines ${fmtNum(h.index, 0)}/6` : 'Atmósfera en altura y suelo',
  )}</b>${hainesLine}${plainMetrics.length ? html`<span class="small" style="display:block;margin-top:4px">${dual(
    `${plainMetrics.join(' · ')}.`,
    `${techMetrics.join(' · ')}.`,
  )}</span>` : ''}<span class="tiny muted" style="display:block;margin-top:4px">Pronóstico de modelo (no es medición en terreno). Fuente: ${srcUrl ? html`<a href="${srcUrl}" target="_blank" rel="noopener">${srcName} ↗</a>` : srcName}${timeMeta ? ` · ${timeMeta}` : ''}.</span></div>`;
}
