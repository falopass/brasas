/* MOV-03: instalar BRASA desde la vista «Más», sin ventanas automáticas. En
 * Android/Chrome el navegador avisa con beforeinstallprompt: se guarda aquí y
 * solo se lanza cuando la persona toca la fila. El módulo se importa junto con
 * la vista; si el evento llegó antes, la fila sencillamente no aparece (escuchar
 * desde el arranque es un pendiente de app.js). En iPhone/iPad no existe ese
 * evento: la fila muestra los pasos de Safari. */
import { detectIos } from './push.js';

let guardado = null;

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    // Sin preventDefault, Chrome mostraría su propio aviso en el momento menos pensado.
    event.preventDefault();
    guardado = event;
  });
  window.addEventListener('appinstalled', () => { guardado = null; });
}

/** Ya corre como app instalada (display-mode standalone, o el standalone de iOS). */
export const yaInstalada = () =>
  (typeof matchMedia !== 'undefined' && matchMedia('(display-mode: standalone)').matches)
  || (typeof navigator !== 'undefined' && navigator.standalone === true);

/** iPhone/iPad: no hay beforeinstallprompt; la invitación son los pasos de Safari. */
export const esIos = () => detectIos();

/** La invitación nativa está guardada y lista para lanzarse (Android/Chrome). */
export const hayInvitacion = () => guardado !== null;

/** Lanza la invitación guardada y devuelve si la persona aceptó. El evento se
 * gasta en un solo intento: tras llamarla hay que quitar la fila. */
export async function invitarAInstalar() {
  const evento = guardado;
  guardado = null;
  if (!evento) return false;
  evento.prompt();
  const { outcome } = await evento.userChoice;
  return outcome === 'accepted';
}
