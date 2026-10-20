/* Pruebas del patrón de voz compartido web/js/speak.js (UX-02): un solo «leyendo»
 * a la vez, la etiqueta alterna «Escuchar»/«Detener» y stopSpeak() no deja voz ni
 * botón marcado. adopt() re-vincula el botón de un repintado sin cortar la voz
 * (DEBT-11). La voz se elige en es-CL aunque getVoices() llegue vacío y la lista
 * aparezca después con voiceschanged, como en Chrome y Edge. speak.js toca `window`
 * al cargar, así que se importa con un speechSynthesis falso que registra las llamadas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const calls = { speak: 0, cancel: 0, last: null };
const voices = { list: [], listeners: new Set() };
globalThis.window = {
  addEventListener() {}, // otros módulos (ui.js) registran listeners; el stub debe tolerarlo
  speechSynthesis: {
    speak(u) { calls.speak += 1; calls.last = u; },
    cancel() { calls.cancel += 1; },
    getVoices() { return voices.list; },
    addEventListener(type, fn) { if (type === 'voiceschanged') voices.listeners.add(fn); },
    removeEventListener(type, fn) { voices.listeners.delete(fn); },
  },
};
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) { this.text = text; this.voice = null; this.lang = ''; }
};
const { adopt, pickVoice, speak, stopSpeak, synth } = await import('../../web/js/speak.js');

/* Lo que hace Chrome/Edge cuando termina de cargar las voces: llena la lista y avisa. */
function loadVoices(list) {
  voices.list = list;
  for (const fn of [...voices.listeners]) fn();
}

function btn() {
  const classes = new Set();
  return {
    textContent: 'Escuchar',
    classList: { toggle: (c, on) => { if (on) classes.add(c); else classes.delete(c); } },
    has: (c) => classes.has(c),
  };
}

function reset(list = [{ lang: 'es-CL' }]) {
  stopSpeak();
  voices.list = list;
  calls.speak = 0;
  calls.cancel = 0;
  calls.last = null;
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

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

describe('voz en español de Chile', () => {
  test('entre varias voces elige es-CL y ajusta el idioma a esa voz', () => {
    reset([{ lang: 'en-US' }, { lang: 'es-ES' }, { lang: 'es-CL' }]);
    const b = btn();
    speak('texto', b);
    assert.equal(calls.speak, 1);
    assert.equal(calls.last.voice.lang, 'es-CL');
    assert.equal(calls.last.lang, 'es-CL');
    reset();
  });

  test('pickVoice prefiere es-CL, luego es-419, luego cualquier español y si no hay, null', () => {
    assert.equal(pickVoice([{ lang: 'es_ES' }, { lang: 'es_419' }]).lang, 'es_419');
    assert.equal(pickVoice([{ lang: 'es-ES' }, { lang: 'es-CL' }]).lang, 'es-CL');
    assert.equal(pickVoice([{ lang: 'en-US' }, { lang: 'es-MX' }]).lang, 'es-MX');
    assert.equal(pickVoice([{ lang: 'en-US' }]), null);
    assert.equal(pickVoice([]), null);
  });

  test('solo voces no españolas: habla igual, sin voz, en es-CL', () => {
    reset([{ lang: 'en-US' }]);
    const b = btn();
    speak('texto', b);
    assert.equal(calls.speak, 1);
    assert.equal(calls.last.voice, null);
    assert.equal(calls.last.lang, 'es-CL');
    assert.equal(b.textContent, 'Detener');
    reset();
  });

  test('getVoices() vacío al tocar: espera voiceschanged y elige la es-CL', async () => {
    reset([]);
    const b = btn();
    speak('texto', b);
    assert.equal(calls.speak, 0, 'no habla con la lista vacía');
    assert.equal(b.textContent, 'Detener', 'el toque responde de inmediato');
    loadVoices([{ lang: 'en-US' }, { lang: 'es-ES' }, { lang: 'es-CL' }]);
    await tick();
    assert.equal(calls.speak, 1);
    assert.equal(calls.last.voice.lang, 'es-CL');
    assert.equal(calls.last.lang, 'es-CL');
    reset();
  });

  test('si voiceschanged nunca llega, habla igual en es-CL', async () => {
    reset([]);
    const b = btn();
    speak('texto', b);
    await new Promise((resolve) => setTimeout(resolve, 1100));
    assert.equal(calls.speak, 1, 'el tope de espera no deja el botón colgado');
    assert.equal(calls.last.voice, null);
    assert.equal(calls.last.lang, 'es-CL');
    reset();
  });

  test('stopSpeak durante la espera no habla después ni deja el botón marcado', async () => {
    reset([]);
    const b = btn();
    speak('texto', b);
    stopSpeak();
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
    loadVoices([{ lang: 'es-CL' }]);
    await tick();
    assert.equal(calls.speak, 0);
  });

  test('dos speak() seguidos: un solo speak, el anterior se cancela', async () => {
    reset([]);
    const a = btn();
    const b = btn();
    speak('primero', a);
    speak('segundo', b);
    loadVoices([{ lang: 'es-CL' }]);
    await tick();
    assert.equal(calls.speak, 1);
    assert.equal(calls.last.text, 'segundo');
    assert.equal(a.textContent, 'Escuchar');
    assert.equal(b.textContent, 'Detener');
    reset();
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

  test('la espera de voces también se adopta al repintar', async () => {
    reset([]);
    speak('frase', btn());
    const nuevo = btn();
    assert.equal(adopt('frase', nuevo), true);
    loadVoices([{ lang: 'es-CL' }]);
    await tick();
    assert.equal(calls.speak, 1);
    assert.equal(nuevo.textContent, 'Detener');
    assert.ok(nuevo.has('speaking'));
    reset();
  });
});
