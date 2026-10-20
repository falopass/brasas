/* Lectura en voz alta (UX-02), el mismo patrón que web/js/views/zona.js y web/js/lite.js:
 * «Escuchar» solo se crea cuando hay speechSynthesis (exportado como `synth`), un solo
 * «leyendo» a la vez y la etiqueta pasa a «Detener». La vista que lo usa debe llamar
 * stopSpeak() al repintar o desmontar para no dejar una voz huérfana sonando; si el
 * repintado repite la misma frase, adopt() re-vincula el botón nuevo sin cortarla. */
export const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
let speakingBtn = null;
let spokenText = null; // la frase que suena: adopt() la compara con la del repintado
let seq = 0; // generación de la lectura: el onend de una frase vieja no pisa la nueva

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

export function speak(text, btn) {
  if (!synth) return;
  if (speakingBtn === btn) { stopSpeak(); return; }
  stopSpeak();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'es-CL';
  const voices = synth.getVoices?.() || [];
  u.voice = voices.find((v) => v.lang === 'es-CL')
    || voices.find((v) => v.lang === 'es-419')
    || voices.find((v) => (v.lang || '').toLowerCase().startsWith('es'))
    || null;
  speakingBtn = btn;
  spokenText = text;
  setSpeaking(btn, true);
  const mine = seq;
  u.onend = u.onerror = () => {
    if (mine !== seq) return;
    spokenText = null;
    if (speakingBtn) { setSpeaking(speakingBtn, false); speakingBtn = null; }
  };
  synth.speak(u);
}
