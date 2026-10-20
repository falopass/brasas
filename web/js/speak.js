/* Lectura en voz alta (UX-02), el mismo patrón que web/js/views/zona.js y web/js/lite.js:
 * «Escuchar» solo se crea cuando hay speechSynthesis (exportado como `synth`), un solo
 * «leyendo» a la vez y la etiqueta pasa a «Detener». La vista que lo usa debe llamar
 * stopSpeak() al repintar o desmontar para no dejar una voz huérfana sonando; si el
 * repintado repite la misma frase, adopt() re-vincula el botón nuevo sin cortarla. */
export const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
let speakingBtn = null;
let spokenText = null; // la frase que suena: adopt() la compara con la del repintado
let seq = 0; // generación de la lectura: el onend de una frase vieja no pisa la nueva

/* Chrome y Edge entregan getVoices() vacío hasta que terminan de cargar las voces
 * (voiceschanged), y varios Android hasta la primera locución. Sin voz elegida solo
 * queda u.lang, que el motor puede ignorar: se espera un tope y, si no llega, se
 * habla igual en es-CL en vez de dejar el botón en «Detener» sin voz. */
const VOICES_WAIT = 1000;

function setSpeaking(btn, on) {
  btn.classList.toggle('speaking', on);
  btn.textContent = on ? 'Detener' : 'Escuchar';
}

export function stopSpeak() {
  seq += 1;
  if (speakingBtn) { setSpeaking(speakingBtn, false); speakingBtn = null; }
  spokenText = null;
  synth?.cancel();
}

/* Repintado con la misma frase (UX-47): el botón nuevo queda en «Detener» y la voz sigue.
   Devuelve false si no hay nada que adoptar: otra frase, o ninguna lectura en curso. */
export function adopt(text, btn) {
  if (!synth || !btn || spokenText !== text) return false;
  if (speakingBtn && speakingBtn !== btn) setSpeaking(speakingBtn, false);
  speakingBtn = btn;
  setSpeaking(btn, true);
  return true;
}

/* es-CL primero; si el equipo no la tiene, cualquier español antes que la voz del
   sistema. Normaliza es_CL y es_419, que algunos navegadores entregan con guion bajo. */
export function pickVoice(voices) {
  const lang = (v) => (v?.lang || '').replace('_', '-').toLowerCase();
  return (voices || []).find((v) => lang(v) === 'es-cl')
    || (voices || []).find((v) => lang(v) === 'es-419')
    || (voices || []).find((v) => lang(v).startsWith('es'))
    || null;
}

/* Una sola espera por voiceschanged; al vencer el tope se relee la lista por si el
   evento se perdió, y si sigue vacía se habla igual sin voz. */
function waitVoices() {
  return new Promise((resolve) => {
    let done = false;
    const onChanged = () => finish(synth.getVoices?.() || []);
    const timer = setTimeout(() => finish(synth.getVoices?.() || []), VOICES_WAIT);
    function finish(list) {
      if (done) return;
      done = true;
      clearTimeout(timer);
      synth.removeEventListener?.('voiceschanged', onChanged);
      resolve(list);
    }
    synth.addEventListener?.('voiceschanged', onChanged);
  });
}

function start(text, voices) {
  const u = new SpeechSynthesisUtterance(text);
  const voice = pickVoice(voices);
  u.voice = voice;
  u.lang = voice ? (voice.lang || 'es-CL').replace('_', '-') : 'es-CL';
  const mine = seq;
  u.onend = u.onerror = () => {
    if (mine !== seq) return;
    spokenText = null;
    if (speakingBtn) { setSpeaking(speakingBtn, false); speakingBtn = null; }
  };
  synth.speak(u);
}

export function speak(text, btn) {
  if (!synth) return;
  if (speakingBtn === btn) { stopSpeak(); return; }
  stopSpeak();
  speakingBtn = btn;
  spokenText = text;
  setSpeaking(btn, true);
  const voices = synth.getVoices?.() || [];
  if (voices.length) { start(text, voices); return; }
  const mine = seq;
  // stopSpeak() durante la espera sube seq: al resolver no debe sonar nada
  waitVoices().then((list) => { if (mine === seq) start(text, list); });
}
