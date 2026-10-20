/* Lectura en voz alta (UX-02), el mismo patrón que web/js/views/zona.js y web/js/lite.js:
 * «Escuchar» solo se crea cuando hay speechSynthesis (exportado como `synth`), un solo
 * «leyendo» a la vez y la etiqueta pasa a «Detener». La vista que lo usa debe llamar
 * stopSpeak() al repintar o desmontar para no dejar una voz huérfana sonando. */
export const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
let speakingBtn = null;

function setSpeaking(btn, on) {
  btn.classList.toggle('speaking', on);
  btn.textContent = on ? 'Detener' : 'Escuchar';
}

export function stopSpeak() {
  if (speakingBtn) { setSpeaking(speakingBtn, false); speakingBtn = null; }
  synth?.cancel();
}

export function speak(text, btn) {
  if (!synth) return;
  if (speakingBtn === btn) { stopSpeak(); return; }
  if (speakingBtn) setSpeaking(speakingBtn, false);
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'es-CL';
  const voices = synth.getVoices?.() || [];
  u.voice = voices.find((v) => v.lang === 'es-CL')
    || voices.find((v) => v.lang === 'es-419')
    || voices.find((v) => (v.lang || '').toLowerCase().startsWith('es'))
    || null;
  speakingBtn = btn;
  setSpeaking(btn, true);
  u.onend = u.onerror = () => {
    if (speakingBtn === btn) { speakingBtn = null; setSpeaking(btn, false); }
  };
  synth.speak(u);
}
