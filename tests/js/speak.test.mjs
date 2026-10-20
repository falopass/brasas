/* Pruebas del patrón de voz compartido web/js/speak.js (UX-02): un solo «leyendo»
 * a la vez, la etiqueta alterna «Escuchar»/«Detener» y stopSpeak() no deja voz ni
 * botón marcado. adopt() re-vincula el botón de un repintado sin cortar la voz
 * (DEBT-11). speak.js toca `window` al cargar, así que se importa con un
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
const { adopt, speak, stopSpeak, synth } = await import('../../web/js/speak.js');

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

describe('adopt', () => {
  test('la misma frase re-vincula el botón nuevo sin cortar la voz', () => {
    reset();
    const viejo = btn();
    speak('la misma frase', viejo);
    const antes = { speak: calls.speak, cancel: calls.cancel };
    const nuevo = btn();
    assert.equal(adopt('la misma frase', nuevo), true);
    assert.equal(calls.speak, antes.speak, 'no encola otra locución');
    assert.equal(calls.cancel, antes.cancel, 'no cancela la que suena');
    assert.equal(nuevo.textContent, 'Detener');
    assert.ok(nuevo.has('speaking'));
    assert.equal(viejo.textContent, 'Escuchar', 'el botón viejo se apaga');
    reset();
  });

  test('otra frase no se adopta y la lectura sigue igual', () => {
    reset();
    const viejo = btn();
    speak('frase vieja', viejo);
    const nuevo = btn();
    assert.equal(adopt('frase nueva', nuevo), false);
    assert.equal(nuevo.textContent, 'Escuchar');
    assert.ok(!nuevo.has('speaking'));
    assert.equal(viejo.textContent, 'Detener');
    assert.equal(calls.speak, 1);
    reset();
  });

  test('sin lectura en curso no hay nada que adoptar', () => {
    reset();
    assert.equal(adopt('texto', btn()), false);
  });

  test('tras adoptar, el fin de la locución apaga el botón nuevo', () => {
    reset();
    speak('frase', btn());
    const nuevo = btn();
    adopt('frase', nuevo);
    calls.last.onend();
    assert.equal(nuevo.textContent, 'Escuchar');
    assert.ok(!nuevo.has('speaking'));
    assert.equal(adopt('frase', nuevo), false, 'ya no queda lectura en curso');
  });

  test('tras adoptar, tocar el botón nuevo detiene la lectura', () => {
    reset();
    speak('frase', btn());
    const nuevo = btn();
    adopt('frase', nuevo);
    speak('frase', nuevo);
    assert.equal(nuevo.textContent, 'Escuchar');
    assert.equal(calls.speak, 1, 'el toque detiene en vez de leer de nuevo');
  });
});
