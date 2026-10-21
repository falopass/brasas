/* Política de privacidad y términos de uso (SEC-01, SEC-08): versión sencilla primero y el detalle después.
 * Enlazada desde Ajustes y desde el formulario de lugar; los derechos también se ejercen aquí mismo. */
import { api } from '../api.js';
import { show } from '../map.js';
import { closeModal, openModal } from '../ui.js';
import { $, download, dual, html, toast } from '../util.js';

export default {
  id: 'privacidad',
  nav: false,
  sheet: 'full',
  async mount(container) {
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line', 'reports'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`
      <h1 class="view-title">Privacidad y tus datos</h1>
      <p class="tiny muted">Última actualización: 21 de octubre de 2026.</p>
      <p class="lede">${dual('Lo esencial en un minuto; el detalle completo más abajo. BRASA es un proyecto ciudadano y la Ley 21.719 nos obliga a contarte esto con claridad.',
        'Política de privacidad conforme a la Ley 21.719 de protección de datos personales (vigente el 1 de diciembre de 2026) y términos de uso del servicio.')}</p>

      <h2 class="section">En simple</h2>
      <ul class="list">
        <li><b>Sin cuentas ni correos.</b> BRASA no te pide nombre, correo ni teléfono: todo funciona con un identificador aleatorio que solo vive en este dispositivo.</li>
        <li><b>Guardamos lo que nos das:</b> tus lugares, el historial de avisos y, si los activas, las llaves para notificaciones push o Telegram.</li>
        <li><b>Nada se vende ni se comparte.</b> No hay publicidad ni rastreadores. Tampoco guardamos tu IP ni tu navegador.</li>
        <li><b>Todo tiene fecha de vencimiento:</b> avisos máximo 12 meses, reportes sin publicar 90 días, reportes publicados 2 años y respaldo de la base hasta 24 horas.</li>
        <li><b>Tus datos son tuyos:</b> en Ajustes puedes descargarlos en un JSON o borrar todo para siempre, sin preguntas.</li>
        <li><b>BRASA no es una alerta oficial:</b> en una emergencia sigue a SENAPRED y llama al 130 (CONAF) o 132 (Bomberos).</li>
      </ul>

      <h2 class="section">Qué guardamos y por qué</h2>
      <ul class="list">
        <li><b>Identificador del dispositivo</b> (token aleatorio): sirve para juntar tus lugares y avisos bajo un mismo paraguas sin pedirte una cuenta. <span class="tiny muted">Nace cuando entras a BRASA y se borra con todo lo demás si pides supresión.</span></li>
        <li><b>Lugares guardados</b> (nombre, coordenadas, radio, tipo y la marca «persona mayor»): son la base para calcular qué detecciones te afectan.</li>
        <li><b>Historial de avisos</b> (qué se avisó, cuándo y por qué canal): para que puedas revisar qué pasó. Se borra a los 12 meses.</li>
        <li><b>Suscripciones de aviso</b> (endpoint y llaves de notificación push, o tu chat de Telegram si lo vinculas): solo sirven para enviarte el aviso.</li>
        <li><b>Reportes ciudadanos</b> (qué viste, ubicación aproximada, foto opcional): los revisa un voluntario antes de publicarse. No llevan tu identificador ni tu nombre: son anónimos por diseño.</li>
        <li><b>Enlace familiar</b> (si lo activas): un enlace de solo lectura que muestra el estado del lugar — y su marca «persona mayor», si existe — a quien lo tenga.</li>
      </ul>
      <p class="small muted">No guardamos dirección IP, navegador (User-Agent), ni perfiles de uso. Las direcciones IP se usan solo en memoria para frenar abusos (límite de solicitudes) y se pierden al apagar el servidor.</p>

      <h2 class="section">Dónde queda todo</h2>
      <p class="small">El servicio corre en <b>Cloudflare</b>: la aplicación en un contenedor, los datos en una base SQLite y sus respaldos y las fotos de reportes en el almacenamiento R2. Esto implica una <b>transferencia internacional de datos</b>: los servidores pueden estar fuera de Chile. Todo viaja cifrado por HTTPS y las fotos se sirven solo a través de la aplicación.</p>

      <h2 class="section">Cuánto tiempo</h2>
      <ul class="list">
        <li><b>Avisos a tu dispositivo:</b> máximo 12 meses; luego se borran solos.</li>
        <li><b>Reportes sin verificar o descartados:</b> 90 días, con su foto.</li>
        <li><b>Reportes verificados:</b> 2 años, con su foto.</li>
        <li><b>Observaciones satelitales</b> (puntos de calor, no son datos de personas): 45 días.</li>
        <li><b>Respaldo de la base:</b> la copia de seguridad se renueva con cada cambio y sus copias diarias se conservan hasta 24 horas; lo que borras desaparece del respaldo en a lo más un día.</li>
        <li><b>Tu dispositivo y sus lugares:</b> hasta que los borres tú o nos pidas supresión.</li>
      </ul>

      <h2 class="section">Tus derechos</h2>
      <p class="small">La Ley 21.719 te da derechos de acceso, rectificación, cancelación (supresión), oposición y portabilidad. En BRASA se ejercen así:</p>
      <ul class="list">
        <li><b>Acceso y portabilidad:</b> «Descargar mis datos» (aquí abajo o en Ajustes) baja un JSON con todo lo guardado de tu dispositivo.</li>
        <li><b>Supresión:</b> «Borrar todos mis datos» (aquí abajo o en Ajustes) elimina el dispositivo y, en cascada, lugares, avisos y suscripciones. Sin vuelta atrás.</li>
        <li><b>Rectificación:</b> puedes editar o borrar cada lugar desde «Mi zona», y quitar la marca «persona mayor» en cualquier momento.</li>
        <li><b>Oposición:</b> deja de usar BRASA y borra tus datos; no hay perfiles ni reutilización posterior.</li>
      </ul>
      <div class="field" id="pr-rights">
        <div class="btn-row">
          <button class="btn btn-sm" type="button" id="pr-export">Descargar mis datos (JSON)</button>
          <button class="btn btn-sm btn-danger" type="button" id="pr-delete">Borrar todos mis datos</button>
        </div>
      </div>
      <p class="small">Los reportes ciudadanos se guardan sin identificador: no hay forma de saber cuáles son tuyos, así que no podemos mostrarlos ni borrarlos por dispositivo (tampoco un tercero podría vincularlos contigo). Si algo no puedes ejercer solo, escríbenos abriendo un issue en <a href="https://github.com/falopass/brasas/issues" target="_blank" rel="noopener">github.com/falopass/brasas</a>.</p>

      <h2 class="section">La marca «persona mayor»</h2>
      <p class="small">Es un consentimiento explícito y opcional: la pides solo si en el lugar vive alguien que necesita ayuda para salir. Lo único que cambia es que cualquier calor dentro del radio se avisa como <b>urgente</b>. Si compartes el enlace familiar del lugar, quien lo abra verá también esa marca: por eso te avisamos antes de compartir. Puedes quitarla cuando quieras editando el lugar.</p>

      <h2 class="section">De dónde vienen los datos</h2>
      <p class="small">${dual('Nada de lo que ves es inventado: cada capa sale de una fuente pública, con su nombre y su hora.',
        'Cada capa cita su fuente y su hora; ninguna se completa con datos simulados. Las licencias son las declaradas por cada proveedor.')}</p>
      <ul class="list">
        <li><span><b>NASA FIRMS</b>: ${dual('los puntos de calor que ven los satélites VIIRS y MODIS al pasar sobre Chile',
          'detecciones térmicas VIIRS (375 m) y MODIS (1 km): productos NRT en vivo y archivo SP para la historia')}.
          Sin licencia declarada · <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
        <li><span><b>NOAA GOES-19</b>: ${dual('el satélite que mira Chile cada 10 minutos, incluidos los rayos',
          'calor ABI L2 FDC cada 10 min y rayos GLM (LCFA), ambos desde el bucket público')}.
          Datos abiertos en AWS Open Data, sin clave · <a href="https://registry.opendata.aws/noaa-goes/" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
        <li><span><b>CONAF GEPRIF</b>: ${dual('los incendios informados oficialmente y el pronóstico «Botón Rojo» por comuna',
          'reporte público de incendios de la temporada (CSV) y pronóstico Botón Rojo a 5 días por comuna')}.
          Sin licencia declarada; el tablero declara la información propiedad de CONAF · <a href="https://deigeprif.com/" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
        <li><span><b>DMC</b>: ${dual('los avisos oficiales de viento y calor extremo de la Dirección Meteorológica de Chile',
          'avisos CAP 1.2 de viento y calor extremo, con el polígono de cada zona')}.
          Dominio público, según el propio RSS · <a href="https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
        <li><span><b>Open-Meteo</b>: ${dual('el pronóstico de viento, calor y humedad, y el clima registrado en los casos históricos',
          'pronóstico horario a 7 días y reanálisis ERA5 para los casos')}.
          Uso gratuito no comercial · <a href="https://open-meteo.com/" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
        <li><span><b>OpenStreetMap / Overpass</b>: ${dual('los puntos de encuentro, hospitales y cuarteles cerca de cada lugar',
          'puntos de encuentro y servicios de emergencia (hospitales, bomberos, policía), en caché 24 h')}.
          © OpenStreetMap, con atribución · <a href="https://www.openstreetmap.org/" target="_blank" rel="noopener">fuente oficial</a>.</span></li>
      </ul>
      <p class="small muted">Las capas de CONAF se usan citando a CONAF como fuente; la autorización formal para redistribuirlas está en trámite. El detalle de cada fuente, su licencia y las reglas de interpretación están en <a href="https://github.com/falopass/brasas/blob/main/docs/FUENTES.md" target="_blank" rel="noopener">docs/FUENTES.md</a> del repositorio.</p>

      <h2 class="section">Términos de uso</h2>
      <ul class="list">
        <li><b>BRASA no es un sistema oficial de alerta.</b> Es una ayuda ciudadana construida sobre datos públicos de satélites y de CONAF. La autoridad es <a href="https://senapred.cl/" target="_blank" rel="noopener">SENAPRED</a>: si ordena evacuar, hazlo.</li>
        <li><b>Sin garantía:</b> los satélites pueden no ver un foco (nubes, horario de pasada) o verlo tarde; BRASA puede fallar o estar desactualizado. No respondemos por daños derivados de confiar solo en esta herramienta.</li>
        <li><b>Reportes:</b> lo que publicas se muestra a todo el mundo con tu ubicación aproximada. No publiques datos de terceros ni contenido ilegal; un moderador puede descartar tu reporte.</li>
        <li>Qué se acepta, qué se rechaza y los plazos de revisión: <a href="https://github.com/falopass/brasas/blob/main/docs/POLITICA_REPORTES.md" target="_blank" rel="noopener">política de contenido de los reportes</a> en el repositorio.</li>
        <li>Texto completo en <a href="https://github.com/falopass/brasas/blob/main/docs/TERMINOS.md" target="_blank" rel="noopener">docs/TERMINOS.md</a> del repositorio.</li>
      </ul>
      <p class="tiny muted" style="margin-top:16px">Emergencias reales: <a href="tel:130">130</a> CONAF · <a href="tel:132">132</a> Bomberos · <a href="tel:133">133</a> Carabineros.</p>`);

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
        if ('caches' in window) {
          const keys = await caches.keys();
          await Promise.all(keys.filter((k) => k.endsWith('-api')).map((k) => caches.delete(k)));
        }
        closeModal();
        document.dispatchEvent(new CustomEvent('brasa:places-changed'));
        $('#pr-rights').innerHTML = String(html`<div class="callout callout-ok"><b>Listo: ya no queda nada de este dispositivo.</b>
          Se borraron tus lugares, avisos y suscripciones; si vuelves a usar BRASA, partirá desde cero.</div>`);
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
  },
};
