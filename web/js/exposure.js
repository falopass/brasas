/* Exposición por comuna: quiénes viven donde el fuego puede llegar.
 * Lee censo_2024.json (OFI-07) e interfaz.json (OFI-08) como archivos estáticos,
 * una sola vez por sesión. Sin dato de una comuna, la línea no se muestra. */
import { ago, fmtNum, html } from './util.js';

let censoPromise = null;
let interfazPromise = null;

const load = (path) => fetch(path).then((r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
});

function censo() {
  return (censoPromise ??= load('/web/data/censo_2024.json').catch((e) => { censoPromise = null; throw e; }));
}

function interfaz() {
  return (interfazPromise ??= load('/web/data/interfaz.json').catch(() => { interfazPromise = null; return null; }));
}

/** Sección «¿A quién afecta?» de la ficha de comuna: población, viviendas y zona de
 *  interfaz urbano-forestal, cada cifra con su fuente y fecha. Nunca lanza: sin datos
 *  o sin conexión devuelve cadena vacía. */
export async function exposureSection(code) {
  const censoData = await censo().catch(() => null);
  const interfazData = await interfaz();
  const row = (censoData?.comunas || []).find((c) => c.code === code);
  const zona = interfazData?.comunas?.[String(code)];
  if (!row && !zona) return '';
  return html`<h2 class="section" style="margin-top:14px">¿A quién afecta?</h2>
    <div class="callout">
      ${row ? html`<p class="small"><b>${fmtNum(row.poblacion)} personas</b> y <b>${fmtNum(row.viviendas)} viviendas</b> en la comuna <span class="tiny muted">(INE · Censo 2024)</span>.</p>` : ''}
      ${zona ? html`<p class="small"><b>${fmtNum(zona.ha_interfaz)} ha</b> en zona de interfaz urbano-forestal: donde las casas y la vegetación se tocan <span class="tiny muted">(el ${fmtNum(zona.pct_comuna, 1)} % de la comuna · CONAF GEPRIF)</span>.</p>` : ''}
      <p class="tiny muted" style="margin-top:6px">Fuentes:
        ${row ? html`<a href="https://censo2024.ine.gob.cl/resultados/" target="_blank" rel="noopener">INE · Censo 2024 ↗</a> (${ago(censoData.fetched_at)})` : ''}${row && zona ? ' · ' : ''}${zona ? html`<a href="https://deigeprif.com" target="_blank" rel="noopener">CONAF GEPRIF · Zonas Interfaz ↗</a> (${ago(interfazData.fetched_at)})` : ''}</p>
    </div>`;
}
