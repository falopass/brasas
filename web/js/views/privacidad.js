/* Política de privacidad y términos de uso (SEC-01, SEC-08): versión sencilla primero y el detalle después.
 * Enlazada desde Ajustes y desde el formulario de lugar; los derechos también se ejercen aquí mismo.
 * Los párrafos de la política viven en web/data/privacidad.json (PESO-05): la vista los pide una
 * sola vez, los pinta en el orden del archivo y, si no llegan, muestra el aviso con «Reintentar»
 * y los teléfonos de emergencia (errorConSalida), nunca una página en blanco. */
import { api } from '../api.js';
import { errorConSalida } from '../errores.js';
import { borrarMapa, descargarMapa, metaMapa, TILE_CACHE, usoMapa } from '../mapa-offline.js';
import { show } from '../map.js';
import { reciboDe } from '../recibo.js';
import { inventarioLocal, store } from '../store.js';
import { closeModal, openModal } from '../ui.js';
import { $, ago, download, dual, fmtNum, html, storage, todayChile, toast } from '../util.js';

const PREF_LABEL = { theme: 'colores', text: 'tamaño de letra', detail: 'nivel de detalle' };
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
const unir = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} y ${items.at(-1)}`);

let politicaPromise = null;
/* Una sola descarga por sesión, como en exposure.js; si falla, la promesa se libera para
 * que «Reintentar» vuelva a pedir el archivo. */
const politica = () => (politicaPromise ??= fetch('/web/data/privacidad.json')
  .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .catch((err) => { politicaPromise = null; throw err; }));

/* Un segmento del JSON: texto plano o {b} negrita, {a,href} enlace, {m} nota chica atenuada,
 * {d:[simple,técnico]} las dos redacciones o {s:[…]} un <span> que envuelve segmentos (las
 * fichas de fuentes van en un solo ítem flex de la lista). Todo sale por html``, así que el
 * contenido del archivo se escapa igual que cualquier otro dato. */
const seg = (s) => {
  if (typeof s === 'string') return s;
  if (s.b !== undefined) return html`<b>${s.b}</b>`;
  if (s.a !== undefined) {
    return s.href?.startsWith('http')
      ? html`<a href="${s.href}" target="_blank" rel="noopener">${s.a}</a>`
      : html`<a href="${s.href}">${s.a}</a>`;
  }
  if (s.m !== undefined) return html`<span class="tiny muted">${s.m}</span>`;
  if (Array.isArray(s.s)) return html`<span>${s.s.map(seg)}</span>`;
  if (Array.isArray(s.d)) return dual(s.d[0], s.d[1]);
  return '';
};

/* Marcado que solo esta vista puede armar: el inventario del teléfono y los botones de
 * derechos van dentro del orden que declara el JSON, como «slots». */
const SLOTS = {
  'en-este-telefono': () => html`
    <h2 class="section">Qué hay en este teléfono ahora mismo</h2>
    <p class="small">Esto es lo que hay guardado en <b>este</b> teléfono. Se lee aquí mismo: abrir esta sección no envía nada.</p>
    <div id="pr-local"><p class="small muted">Revisando este teléfono…</p></div>
    <div class="btn-row">
      <button class="btn btn-sm" type="button" id="pr-clear-outbox" disabled>Borrar los reportes que esperan señal</button>
      <button class="btn btn-sm btn-danger" type="button" id="pr-forget">Olvidar este dispositivo</button>
    </div>
    <h2 class="section">El mapa de tus lugares sin señal</h2>
    <p class="small">${dual(
      'En un incendio grande las redes se saturan. Con Wi-Fi puedes descargar el mapa de un lugar y, si después te quedas sin señal, BRASA sigue mostrando sus calles y nombres. Nada se descarga solo: solo cuando lo pides aquí.',
      'Teselas de OpenFreeMap del entorno (zoom 8-13, ~15 MB) + nombres, en la caché «brasa-tiles». Sin descarga en segundo plano.')}</p>
    <div id="pr-mapas"><p class="small muted">Revisando el mapa guardado…</p></div>
    <p class="small" id="pr-local-status" role="status" aria-live="polite"></p>`,
  'derechos': () => html`<div class="field" id="pr-rights">
    <div class="btn-row">
      <button class="btn btn-sm" type="button" id="pr-export">Descargar mis datos (JSON)</button>
      <button class="btn btn-sm btn-danger" type="button" id="pr-delete">Borrar todos mis datos</button>
    </div>
  </div>`,
};

const bloque = (b) => {
  if (b.slot) return SLOTS[b.slot]?.() ?? '';
  if (b.lista) return html`<ul class="list">${b.lista.map((item) => html`<li>${item.map(seg)}</li>`)}</ul>`;
  return html`<p class="${b.clase || 'small'}">${(b.p || []).map(seg)}</p>`;
};

const seccion = (s) => (s.slot
  ? (SLOTS[s.slot]?.() ?? '')
  : html`<h2 class="section">${s.titulo}</h2>${(s.bloques || []).map(bloque)}`);

/** Las cuatro líneas del inventario local (SEC-01), en palabras simples y sin valores:
 *  solo conteos y nombres de preferencia. Pura y sin DOM para poder probarla. */
export function lineasInventario(inv) {
  const cola = [];
  if (inv.reportes_en_cola) cola.push(`${plural(inv.reportes_en_cola, 'reporte esperando', 'reportes esperando')} señal`);
  if (inv.reportes_vencidos) cola.push(`${plural(inv.reportes_vencidos, 'venció', 'vencieron')} sin enviarse`);
  const detalleCola = [
    inv.reportes_en_cola ? 'Se enviarán solos al volver la conexión.' : '',
    inv.reportes_vencidos ? 'Pasado un día ya no sirven para una emergencia y se quitaron de la cola.' : '',
  ].filter(Boolean).join(' ');
  return [
    inv.token
      ? html`<li><b>1 identificador de este dispositivo.</b> Es un número aleatorio que BRASA usa para reconocer tus lugares y avisos; no dice quién eres.</li>`
      : html`<li><b>Sin identificador guardado.</b> BRASA no reconoce este teléfono todavía.</li>`,
    cola.length
      ? html`<li><b>${cola.join('; ')}.</b> ${detalleCola}</li>`
      : html`<li><b>No hay reportes esperando señal.</b></li>`,
    inv.preferencias.length
      ? html`<li><b>Preferencias:</b> ${unir(inv.preferencias.map((key) => PREF_LABEL[key]))}. Solo cambian cómo se ve BRASA en este teléfono.</li>`
      : html`<li><b>Sin preferencias guardadas:</b> BRASA usa el tema oscuro, la letra normal y la lectura sencilla.</li>`,
    inv.cache_api
      ? html`<li><b>${plural(inv.cache_api, 'copia', 'copias')} de datos para ver sin señal.</b> Pueden incluir tus lugares y avisos si ya los abriste aquí.</li>`
      : html`<li><b>Sin copias para ver sin señal.</b></li>`,
  ];
}

let mounted = false;
let offPlaces = null;

export default {
  id: 'privacidad',
  nav: false,
  sheet: 'full',
  async mount(container) {
    mounted = true;
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`<h1 class="view-title">Privacidad y tus datos</h1><div id="pr-cuerpo"></div>`);
    const cuerpo = $('#pr-cuerpo', container);

    const cargar = async () => {
      let data;
      try {
        data = await politica();
      } catch (err) {
        errorConSalida(cuerpo, err, cargar);
        return;
      }
      cuerpo.innerHTML = String(html`
        <p class="tiny muted">${data.actualizacion}</p>
        <p class="lede">${(data.lede || []).map(seg)}</p>
        <div class="callout" id="pr-recibo" hidden></div>
        ${(data.secciones || []).map(seccion)}
        <p class="tiny muted" style="margin-top:16px">Emergencias reales: <a href="tel:130">130</a> CONAF · <a href="tel:132">132</a> Bomberos · <a href="tel:133">133</a> Carabineros.</p>`);

      // Inventario local (SEC-01): la persona ve conteos de lo que hay en su teléfono, nunca el
      // token, coordenadas ni el texto de un reporte. Las acciones borran solo lo que nombran.
      let inventario = null;

      const anunciar = (texto) => { $('#pr-local-status', container).textContent = texto; };

      const pintarInventario = async () => {
        inventario = await inventarioLocal();
        const host = $('#pr-local', container);
        if (!host) return;
        host.innerHTML = String(html`<ul class="list">${lineasInventario(inventario)}</ul>`);
        $('#pr-clear-outbox', container).disabled = inventario.reportes_en_cola === 0;
      };

      const borrarCachesApi = async () => {
        if (!('caches' in window)) return;
        const keys = await caches.keys();
        // MAPA-166: brasa-tiles también es una «copia para ver sin señal» de este teléfono.
        await Promise.all(keys.filter((k) => k.endsWith('-api') || k === TILE_CACHE).map((k) => caches.delete(k)));
      };

      const borrarCola = () => {
        const n = inventario?.reportes_en_cola ?? 0;
        if (!n) return;
        openModal(html`<h2 id="modal-title">¿Borrar los reportes que esperan señal?</h2>
          <p>${n === 1 ? 'Se borra 1 reporte que aún no se envió.' : `Se borran ${n} reportes que aún no se enviaron.`} No hay forma de recuperarlos.</p>
          <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="outbox-yes">Sí, borrarlos</button>
            <button class="btn btn-ghost" type="button" id="outbox-no">Cancelar</button></div>`, (b) => {
          b.querySelector('#outbox-no').addEventListener('click', closeModal);
          b.querySelector('#outbox-yes').addEventListener('click', async () => {
            localStorage.removeItem('brasa:outbox');
            closeModal();
            await pintarInventario();
            anunciar(n === 1 ? 'Se borró 1 reporte que esperaba señal. No se envió.' : `Se borraron ${n} reportes que esperaban señal. No se enviaron.`);
          });
        });
      };

      const olvidarDispositivo = () => {
        openModal(html`<h2 id="modal-title">¿Olvidar este dispositivo?</h2>
          <p>Se borra el identificador de BRASA, tus preferencias (colores, letra y detalle) y las copias guardadas para ver sin señal. Tus lugares y avisos seguirán en el servidor, pero sin ese identificador ya no se pueden consultar ni borrar desde este teléfono.</p>
          <p>Si quieres eliminarlos también, cancela y usa primero «Borrar todos mis datos». Los reportes que esperan señal se conservan y se enviarán al volver la conexión.</p>
          <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="forget-yes">Sí, olvidar</button>
            <button class="btn btn-ghost" type="button" id="forget-no">Cancelar</button></div>`, (b) => {
          b.querySelector('#forget-no').addEventListener('click', closeModal);
          b.querySelector('#forget-yes').addEventListener('click', async () => {
            ['token', 'theme', 'text', 'detail', 'cached-at', 'mapa-offline'].forEach((key) => localStorage.removeItem(`brasa:${key}`));
            // El tema se aplica en caliente (mapa incluido) y después se borra la marca: queda el de fábrica.
            document.dispatchEvent(new CustomEvent('brasa:theme', { detail: 'dark' }));
            localStorage.removeItem('brasa:theme');
            delete document.documentElement.dataset.text;
            delete document.documentElement.dataset.detail;
            // Sin token, los lugares que quedaban en memoria no deben seguir visibles.
            store.set('places', []);
            await borrarCachesApi();
            closeModal();
            await pintarInventario();
            pintarRecibo({});  // sin token el recibo no puede leer nada: vuelve a cero
            anunciar('Listo: este teléfono ya no tiene identificador de BRASA ni preferencias. La próxima vez que entres se creará uno nuevo.');
          });
        });
      };

      container.querySelector('#pr-clear-outbox').addEventListener('click', borrarCola);
      container.querySelector('#pr-forget').addEventListener('click', olvidarDispositivo);
      await pintarInventario();

      // MAPA-166: descarga explícita por lugar y borrado de brasa-tiles, ambos aquí.
      const mb = (b) => `${fmtNum(b / 1048576, 1)} MB`;
      let descargando = false;

      const pintarMapas = async () => {
        const host = $('#pr-mapas', container);
        if (!host) return;
        const places = store.get('places') || [];
        const meta = metaMapa();
        const uso = await usoMapa();
        host.innerHTML = String(html`
          ${places.length ? html`<ul class="list">${places.map((p) => {
            const m = meta[p.id];
            const estado = m?.completo ? `Mapa descargado ${ago(m.at)} · ${mb(m.bytes)}`
              : m ? `Descarga incompleta: ${m.recursos} de ${m.total} recursos · ${mb(m.bytes)}`
              : 'Sin mapa descargado';
            return html`<li><div class="grow"><b>${p.name}</b><div class="tiny muted">${estado}</div></div>
              <button class="btn btn-sm" type="button" data-mapa="${p.id}"${descargando ? ' disabled' : ''}>${m?.completo ? 'Actualizar' : 'Descargar mapa'}</button></li>`;
          })}</ul>` : html`<p class="small">No hay lugares guardados en este teléfono: guarda uno en «Mi zona» para poder descargar su mapa.</p>`}
          <div class="btn-row" style="margin-top:8px">
            <button class="btn btn-sm btn-danger" type="button" id="pr-tiles-del"${uso.recursos ? '' : ' disabled'}>Borrar el mapa sin señal${uso.recursos ? ` (${mb(uso.bytes)})` : ''}</button>
          </div>`);
        host.querySelectorAll('[data-mapa]').forEach((b) => b.addEventListener('click', () => descargar(b.dataset.mapa)));
        $('#pr-tiles-del', host)?.addEventListener('click', borrarMapas);
      };

      const descargar = async (placeId) => {
        const p = (store.get('places') || []).find((x) => x.id === placeId);
        if (!p || descargando) return;
        descargando = true;
        await pintarMapas();
        try {
          const r = await descargarMapa(p, {
            onProgreso: ({ hechas, total, bytes }) => anunciar(`«${p.name}»: ${hechas} de ${total} recursos · ${mb(bytes)}`),
          });
          anunciar(r.completo
            ? `Listo: el mapa de «${p.name}» quedó guardado (${r.recursos} recursos, ${mb(r.bytes)}).`
            : r.motivo === 'tope'
              ? `«${p.name}» llegó al tope de ~15 MB: quedaron ${r.recursos} de ${r.total} recursos (${mb(r.bytes)} bajados).`
              : `Se cortó la descarga de «${p.name}» por la conexión: quedaron ${r.recursos} de ${r.total} recursos (${mb(r.bytes)} bajados).`);
        } catch (err) {
          anunciar(`No se pudo descargar el mapa de «${p.name}»: ${err.message || 'error de red'}.`);
        }
        descargando = false;
        await pintarMapas();
      };

      const borrarMapas = () => {
        openModal(html`<h2 id="modal-title">¿Borrar el mapa sin señal?</h2>
          <p>Se borran las teselas y los nombres descargados en este teléfono. Sin ellos, sin señal el mapa vuelve a mostrar solo los límites de las regiones.</p>
          <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="tiles-yes">Sí, borrarlo</button>
            <button class="btn btn-ghost" type="button" id="tiles-no">Cancelar</button></div>`, (b) => {
          b.querySelector('#tiles-no').addEventListener('click', closeModal);
          b.querySelector('#tiles-yes').addEventListener('click', async () => {
            await borrarMapa();
            closeModal();
            await pintarMapas();
            anunciar('Se borró el mapa sin señal de este teléfono.');
          });
        });
      };

      offPlaces = store.on('places', () => { if (mounted) pintarMapas(); });
      await pintarMapas();

      // Recibo (PRIV-03): lo mismo que descargan o borran los botones, contado antes de
      // tocarlos. Sin dispositivo registrado se muestran ceros sin crear uno por leer la
      // política; si el export falla, no se muestra nada y la prosa queda igual.
      const recibo = $('#pr-recibo', container);
      const pintarRecibo = (datos) => {
        recibo.innerHTML = String(html`<b>Esto es lo que BRASA guarda de este dispositivo:</b> ${reciboDe(datos, todayChile()).frase}.
          <div class="tiny muted" style="margin-top:6px">Los dos botones de abajo descargan o borran estos datos. Los reportes ciudadanos no se cuentan: son anónimos y no cuelgan del dispositivo.</div>`);
        recibo.hidden = false;
      };
      if (storage.get('token')) api.exportMe().then(pintarRecibo).catch(() => {});
      else pintarRecibo({});

      // Los derechos se ejercen en esta misma página, con la misma API y semántica que en Ajustes.
      const exportData = async () => {
        try {
          const data = await api.exportMe();
          download(`brasa-mis-datos-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(data, null, 2), 'application/json');
          toast('Descarga lista.');
        } catch (err) { toast(err.message, 'error', 8000, { label: 'Reintentar', onClick: exportData }); }
      };
      const wipe = async () => {
        try {
          await api.deleteMe();
          Object.keys(localStorage).filter((k) => k.startsWith('brasa:')).forEach((k) => localStorage.removeItem(k));
          // El service worker guarda lugares y avisos en caché para verlos sin señal: también se borran.
          await borrarCachesApi();
          closeModal();
          document.dispatchEvent(new CustomEvent('brasa:places-changed'));
          $('#pr-rights').innerHTML = String(html`<div class="callout callout-ok"><b>Listo: ya no queda nada de este dispositivo.</b>
            Se borraron tus lugares, avisos y suscripciones; si vuelves a usar BRASA, partirá desde cero.</div>`);
          await pintarInventario();
          pintarRecibo({});  // el recibo no puede seguir mostrando lo que se acaba de borrar
        } catch (err) {
          // El resultado va dentro del modal: un <dialog> abierto tapa los avisos flotantes (toast).
          openModal(html`<h2 id="modal-title">No se pudo borrar</h2>
            <p>${err.message}</p><p><b>No se borró nada:</b> tus datos siguen guardados.</p>
            <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="wipe-retry">Reintentar</button>
              <button class="btn btn-ghost" type="button" id="wipe-cancel">Cancelar</button></div>`, (b) => {
            b.querySelector('#wipe-retry').addEventListener('click', wipe);
            b.querySelector('#wipe-cancel').addEventListener('click', closeModal);
          });
        }
      };
      container.querySelector('#pr-export').addEventListener('click', exportData);
      container.querySelector('#pr-delete').addEventListener('click', () => {
        openModal(html`<h2 id="modal-title">¿Borrar todos tus datos?</h2>
          <p>Se borran para siempre: tus lugares guardados, su historial de avisos y la suscripción de este dispositivo (push y Telegram). No hay forma de recuperarlos.</p>
          <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="del-yes">Sí, borrar todo</button>
            <button class="btn btn-ghost" type="button" id="del-no">Cancelar</button></div>`, (b) => {
          b.querySelector('#del-no').addEventListener('click', closeModal);
          b.querySelector('#del-yes').addEventListener('click', wipe);
        });
      });
    };

    await cargar();
  },
  unmount() {
    mounted = false;
    offPlaces?.();
    offPlaces = null;
  },
};
