/* Política de privacidad y términos de uso (SEC-01, SEC-08): versión sencilla primero y el detalle después.
 * Página de solo lectura, enlazada desde Ajustes y desde el formulario de lugar. */
import { show } from '../map.js';
import { $, dual, html } from '../util.js';

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
      <p class="lede">${dual('Lo esencial en un minuto; el detalle completo más abajo. BRASA es un proyecto ciudadano y la Ley 21.719 nos obliga a contarte esto con claridad.',
        'Política de privacidad conforme a la Ley 21.719 de protección de datos personales (vigente el 1 de diciembre de 2026) y términos de uso del servicio.')}</p>

      <h2 class="section">En simple</h2>
      <ul class="list">
        <li><b>Sin cuentas ni correos.</b> BRASA no te pide nombre, correo ni teléfono: todo funciona con un identificador aleatorio que solo vive en este dispositivo.</li>
        <li><b>Guardamos lo que nos das:</b> tus lugares, el historial de avisos y, si los activas, las llaves para notificaciones push o Telegram.</li>
        <li><b>Nada se vende ni se comparte.</b> No hay publicidad ni rastreadores. Tampoco guardamos tu IP ni tu navegador.</li>
        <li><b>Todo tiene fecha de vencimiento:</b> avisos máximo 12 meses, reportes sin publicar 90 días, reportes publicados 2 años.</li>
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
        <li><b>Tu dispositivo y sus lugares:</b> hasta que los borres tú o nos pidas supresión.</li>
      </ul>

      <h2 class="section">Tus derechos</h2>
      <p class="small">La Ley 21.719 te da derechos de acceso, rectificación, cancelación (supresión), oposición y portabilidad. En BRASA se ejercen así:</p>
      <ul class="list">
        <li><b>Acceso y portabilidad:</b> Ajustes → «Descargar mis datos» baja un JSON con todo lo guardado de tu dispositivo.</li>
        <li><b>Supresión:</b> Ajustes → «Borrar todos mis datos» elimina el dispositivo y, en cascada, lugares, avisos y suscripciones. Sin vuelta atrás.</li>
        <li><b>Rectificación:</b> puedes editar o borrar cada lugar desde «Mi zona», y quitar la marca «persona mayor» en cualquier momento.</li>
        <li><b>Oposición:</b> deja de usar BRASA y borra tus datos; no hay perfiles ni reutilización posterior.</li>
      </ul>
      <p class="small">Los reportes ciudadanos se guardan sin identificador: no hay forma de saber cuáles son tuyos, así que no podemos mostrarlos ni borrarlos por dispositivo (tampoco un tercero podría vincularlos contigo). Si algo no puedes ejercer solo, escríbenos abriendo un issue en <a href="https://github.com/falopass/brasas/issues" target="_blank" rel="noopener">github.com/falopass/brasas</a>.</p>

      <h2 class="section">La marca «persona mayor»</h2>
      <p class="small">Es un consentimiento explícito y opcional: la pides solo si en el lugar vive alguien que necesita ayuda para salir. Lo único que cambia es que cualquier calor dentro del radio se avisa como <b>urgente</b>. Si compartes el enlace familiar del lugar, quien lo abra verá también esa marca: por eso te avisamos antes de compartir. Puedes quitarla cuando quieras editando el lugar.</p>

      <h2 class="section">Términos de uso</h2>
      <ul class="list">
        <li><b>BRASA no es un sistema oficial de alerta.</b> Es una ayuda ciudadana construida sobre datos públicos de satélites y de CONAF. La autoridad es <a href="https://senapred.cl/" target="_blank" rel="noopener">SENAPRED</a>: si ordena evacuar, hazlo.</li>
        <li><b>Sin garantía:</b> los satélites pueden no ver un foco (nubes, horario de pasada) o verlo tarde; BRASA puede fallar o estar desactualizado. No respondemos por daños derivados de confiar solo en esta herramienta.</li>
        <li><b>Reportes:</b> lo que publicas se muestra a todo el mundo con tu ubicación aproximada. No publiques datos de terceros ni contenido ilegal; un moderador puede descartar tu reporte.</li>
        <li>Texto completo en <a href="https://github.com/falopass/brasas/blob/main/docs/TERMINOS.md" target="_blank" rel="noopener">docs/TERMINOS.md</a> del repositorio.</li>
      </ul>
      <p class="tiny muted" style="margin-top:16px">Emergencias reales: <a href="tel:130">130</a> CONAF · <a href="tel:132">132</a> Bomberos · <a href="tel:133">133</a> Carabineros.</p>`);
  },
};
