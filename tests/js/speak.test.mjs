/* Pruebas del patrón de voz compartido web/js/speak.js (UX-02): un solo «leyendo»
 * a la vez, la etiqueta alterna «Escuchar»/«Detener» y stopSpeak() no deja voz ni
 * botón marcado. adopt() re-vincula el botón de un repintado sin cortar la voz
 * (DEBT-11). La voz se elige en es-CL aunque getVoices() llegue vacío y la lista
 * aparezca después con voiceschanged, como en Chrome y Edge. speak.js toca `window`
 * al cargar, así que se importa con un speechSynthesis falso que registra las llamadas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const calls = { speak: 0, cancel: 0, last: null, all: [] };
const voices = { list: [], listeners: new Set() };
globalThis.window = {
  addEventListener() {}, // otros módulos (ui.js) registran listeners; el stub debe tolerarlo
  speechSynthesis: {
    speak(u) { calls.speak += 1; calls.last = u; calls.all.push(u); },
    cancel() { calls.cancel += 1; },
    getVoices() { return voices.list; },
    addEventListener(type, fn) { if (type === 'voiceschanged') voices.listeners.add(fn); },
    removeEventListener(type, fn) { voices.listeners.delete(fn); },
  },
};
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) { this.text = text; this.voice = null; this.lang = ''; }
};
const { adopt, partirEnFrases, pickVoice, speak, stopSpeak, synth } = await import('../../web/js/speak.js');

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
  calls.all = [];
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

/* UX-02/UX-11: Chrome y Edge cortan solas una locución larga a los ~15 s, así que
 * speak.js reparte el texto en frases (partirEnFrases) y encola una locución por
 * trozo. El botón vuelve a «Escuchar» solo al terminar el último; si un trozo
 * falla, la cola se cancela y la etiqueta se restaura en vez de quedar pegada. */
const EMERGENCIA = 'Hay humo sobre el cerro y el viento lo empuja hacia tu casa. '
  + 'Si la autoridad ordena evacuar, sal de inmediato por la ruta que indiquen; no esperes a ver las llamas. '
  + 'Lleva solo lo esencial: documentos, remedios y agua. '
  + 'Cierra el gas y la electricidad si tienes tiempo, ayuda a quienes se mueven lento y avisa a los vecinos. '
  + 'No uses la escalera si hay humo en el pasillo y mantén paños húmedos en las puertas de la salida. '
  + 'Si ves brasas caer cerca, moja el techo y las esquinas solo si puedes hacerlo sin riesgo. '
  + 'Cuando estés a salvo, avisa a tu familia con un mensaje corto y sigue la información oficial.';
const norm = (s) => s.replace(/\s+/g, ' ').trim();

describe('partirEnFrases', () => {
  test('un párrafo largo sale en varios trozos acotados', () => {
    const trozos = partirEnFrases(EMERGENCIA);
    assert.ok(EMERGENCIA.length > 600, 'el caso de prueba debe ser un párrafo largo');
    assert.ok(trozos.length >= 4, `esperaba al menos 4 trozos, llegaron ${trozos.length}`);
    for (const t of trozos) assert.ok(t.length <= 200, `trozo de ${t.length} caracteres: ${t}`);
  });

  test('un texto corto queda en un solo trozo', () => {
    const corto = 'Revisa el estado y sigue a la autoridad del lugar.';
    assert.deepEqual(partirEnFrases(corto), [corto]);
  });

  test('texto vacío o solo espacios devuelve una lista vacía', () => {
    assert.deepEqual(partirEnFrases(''), []);
    assert.deepEqual(partirEnFrases('   \n\t  '), []);
  });

  test('una oración larga sin puntuación se corta por palabra', () => {
    const largo = 'palabras seguidas sin punto ni coma para llegar lejos '.repeat(8).trim();
    const trozos = partirEnFrases(largo);
    assert.ok(trozos.length >= 2);
    for (const t of trozos) assert.ok(t.length <= 200);
    assert.equal(trozos.join(' '), largo);
  });

  test('los trozos conservan el texto palabra por palabra', () => {
    const raro = '  Primera frase.\n\nSegunda;   tercera!\tCuarta?  Quinta,sin espacio.\nÚltima  ';
    assert.equal(partirEnFrases(raro).join(' '), norm(raro));
    assert.equal(partirEnFrases(EMERGENCIA).join(' '), norm(EMERGENCIA));
  });
});

describe('lectura en trozos', () => {
  test('un texto largo encola una locución por trozo', () => {
    reset();
    const b = btn();
    speak(EMERGENCIA, b);
    const trozos = partirEnFrases(EMERGENCIA);
    assert.ok(trozos.length > 1);
    assert.equal(calls.speak, trozos.length);
    assert.deepEqual(calls.all.map((u) => u.text), trozos);
    assert.equal(b.textContent, 'Detener');
    reset();
  });

  test('el botón se restaura solo cuando termina el último trozo', () => {
    reset();
    const b = btn();
    speak(EMERGENCIA, b);
    for (const u of calls.all.slice(0, -1)) u.onend();
    assert.equal(b.textContent, 'Detener', 'los trozos intermedios no apagan el botón');
    calls.all.at(-1).onend();
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
  });

  test('un error en un trozo cancela la cola y no deja el botón pegado', () => {
    reset();
    const b = btn();
    speak(EMERGENCIA, b);
    const antes = calls.cancel;
    calls.all[0].onerror();
    assert.equal(calls.cancel, antes + 1);
    assert.equal(b.textContent, 'Escuchar');
    assert.ok(!b.has('speaking'));
    calls.all.at(-1).onend(); // un fin atrasado no rompe nada
    assert.equal(b.textContent, 'Escuchar');
  });

  test('stopSpeak corta la cola completa de una lectura troceada', () => {
    reset();
    const b = btn();
    speak(EMERGENCIA, b);
    assert.ok(calls.speak > 1);
    const antes = calls.cancel;
    stopSpeak();
    assert.equal(calls.cancel, antes + 1);
    assert.equal(b.textContent, 'Escuchar');
    calls.all.at(-1).onend(); // la lectura muerta no toca el botón
    assert.equal(b.textContent, 'Escuchar');
  });

  test('adopt re-vincula el botón nuevo de una lectura troceada', () => {
    reset();
    speak(EMERGENCIA, btn());
    const n = calls.speak;
    const nuevo = btn();
    assert.equal(adopt(EMERGENCIA, nuevo), true);
    assert.equal(calls.speak, n, 'no encola una segunda lectura');
    calls.all.at(-1).onend();
    assert.equal(nuevo.textContent, 'Escuchar');
    reset();
  });
});
