/* Pruebas del patrón de voz compartido web/js/speak.js (UX-02): un solo «leyendo»
 * a la vez, la etiqueta alterna «Escuchar»/«Detener» y stopSpeak() no deja voz ni
 * botón marcado. speak.js toca `window` al cargar, así que se importa con un
 * speechSynthesis falso que registra las llamadas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const calls = { speak: 0, cancel: 0, last: null };
globalThis.window = {
  addEventListener() {}, // otros módulos (ui.js) registran listeners; el stub debe tolerarlo
  speechSynthesis: {
    speak(u) { calls.speak += 1; calls.last = u; },
    cancel() { calls.cancel += 1; },
    getVoices() { return []; },
  },
};
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) { this.text = text; }
};
const { speak, stopSpeak, synth } = await import('../../web/js/speak.js');

function btn() {
  const classes = new Set();
  return {
    textContent: 'Escuchar',
    classList: { toggle: (c, on) => { if (on) classes.add(c); else classes.delete(c); } },
    has: (c) => classes.has(c),
  };
}

function reset() { stopSpeak(); calls.speak = 0; calls.cancel = 0; calls.last = null; }

describe('speak', () => {
  test('está disponible cuando el navegador tiene speechSynthesis', () => {
    assert.ok(synth, 'synth no debería ser null con speechSynthesis en window');
  });

  test('lee el texto en es-CL y el botón pasa a «Detener»', () => {
    reset();
    const b = btn();
    speak('Paso uno. Paso dos.', b);
    assert.equal(calls.speak, 1);
    assert.equal(calls.last.lang, 'es-CL');
    assert.equal(calls.last.text, 'Paso uno. Paso dos.');
    assert.equal(b.textContent, 'Detener');
    assert.ok(b.has('speaking'));
    reset();
  });

  test('tocar el mismo botón detiene la lectura', () => {
    reset();
    const b = btn();
    speak('texto', b);
    speak('texto', b);
    assert.equal(calls.speak, 1, 'no se encola una segunda lectura');
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
  });

  test('un solo «leyendo»: otro botón reemplaza al anterior', () => {
    reset();
    const a = btn();
    const b = btn();
    speak('primero', a);
    speak('segundo', b);
    assert.equal(a.textContent, 'Escuchar');
    assert.ok(!a.has('speaking'));
    assert.equal(b.textContent, 'Detener');
    assert.ok(b.has('speaking'));
    reset();
  });

  test('al terminar la locución el botón se restaura solo', () => {
    reset();
    const b = btn();
    speak('texto', b);
    calls.last.onend();
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
  });

  test('stopSpeak cancela y no deja botón marcado', () => {
    reset();
    const b = btn();
    speak('texto', b);
    const before = calls.cancel;
    stopSpeak();
    assert.equal(calls.cancel, before + 1);
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
  });
});
