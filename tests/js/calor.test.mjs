/* Pruebas de web/js/calor.js (QA-84): el módulo que decide cuándo BRASA muestra
 * consejos de salud junto a un aviso de calor de la DMC (ALR-22). Lo consumen
 * «Riesgo» y «Mi zona», así que un cambio en sus umbrales o en sus fuentes se
 * vería en dos pantallas de emergencia. Documenta lo que ya existe: los textos
 * y los umbrales no se cambian aquí. calor.js es puro (sin DOM) y se importa
 * directo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CONSEJOS_CALOR, CONSULTA_FUENTES, DOMINIOS_OFICIALES, NO_OFICIAL, hayCalor, revisarConsejos } from '../../web/js/calor.js';

/* La lista blanca de dominios oficiales vive en la guarda de Python; se lee de
 * ahí para que agregar un dominio en un solo lugar baste. */
const GUARDA = readFileSync(new URL('../test_fuentes_enlaces.py', import.meta.url), 'utf8');
const BLOQUE = /DOMINIOS_OFICIALES\s*=\s*\(([\s\S]*?)\n\)/.exec(GUARDA);
assert.ok(BLOQUE, 'no se pudo leer DOMINIOS_OFICIALES de tests/test_fuentes_enlaces.py');
const DOMINIOS = [...BLOQUE[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);

describe('hayCalor', () => {
  test('sin avisos no hay calor', () => {
    for (const avisos of [[], undefined, null]) assert.equal(hayCalor(avisos), false);
  });
  test('un aviso de otro tipo no basta', () => {
    assert.equal(hayCalor([{ kind: 'viento' }]), false);
  });
  test('un solo aviso de calor entre varios da true', () => {
    assert.equal(hayCalor([{ kind: 'viento' }, { kind: 'calor' }, { kind: 'lluvia' }]), true);
  });
});

describe('CONSEJOS_CALOR', () => {
  test('cada consejo tiene texto y fuente no vacíos', () => {
    assert.ok(CONSEJOS_CALOR.length > 0, 'debe haber al menos un consejo');
    for (const c of CONSEJOS_CALOR) {
      assert.ok(c.text && c.text.trim(), `consejo sin texto: ${JSON.stringify(c)}`);
      assert.ok(c.source && c.source.trim(), `consejo sin fuente: ${c.text}`);
    }
  });
  test('cada consejo trae una URL https de un dominio oficial', () => {
    for (const c of CONSEJOS_CALOR) {
      assert.match(c.url, /^https:\/\//, `«${c.source}» no es https: ${c.url}`);
      const host = new URL(c.url).hostname;
      assert.ok(DOMINIOS.some((d) => host === d || host.endsWith(`.${d}`)),
        `«${c.source}» apunta a un dominio no registrado en tests/test_fuentes_enlaces.py: ${host}`);
    }
  });
});

describe('NO_OFICIAL', () => {
  test('menciona a SENAPRED y no afirma que BRASA sea oficial', () => {
    assert.match(NO_OFICIAL, /SENAPRED/);
    assert.match(NO_OFICIAL, /no es (una )?fuente oficial/i);
    assert.doesNotMatch(NO_OFICIAL, /BRASA es (una )?fuente oficial/i);
  });
});

describe('CONSULTA_FUENTES', () => {
  test('sigue el formato ISO AAAA-MM-DD y no es futura', () => {
    assert.match(CONSULTA_FUENTES, /^\d{4}-\d{2}-\d{2}$/);
    // Fecha de hoy en Chile (UTC-3/-4), no en UTC: el 19-10 en Chile puede ser 20-10 en UTC.
    const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago' }).format(new Date());
    assert.ok(CONSULTA_FUENTES <= hoy, `CONSULTA_FUENTES (${CONSULTA_FUENTES}) está en el futuro; hoy en Chile es ${hoy}`);
  });
});

/* QA-207: la guarda que hace cumplir «sin fuente oficial verificable no se
 * publica». `hoy` se inyecta para que la prueba no dependa del reloj. */
describe('revisarConsejos', () => {
  const HOY = '2026-12-31';
  const bueno = {
    text: 'Consejo de prueba con el largo suficiente para pasar la guarda.',
    source: 'SENAPRED: prueba',
    url: 'https://senapred.cl/prueba/',
  };

  test('los consejos publicados pasan la guarda', () => {
    const r = revisarConsejos(CONSEJOS_CALOR, HOY);
    assert.deepEqual(r.problemas, []);
    assert.equal(r.ok, true);
  });

  test('rechaza una URL http', () => {
    const r = revisarConsejos([{ ...bueno, url: 'http://www.minsal.cl/x' }], HOY);
    assert.equal(r.ok, false);
    assert.ok(r.problemas.some((p) => /https/.test(p)), `se esperaba un problema que mencione https: ${r.problemas}`);
  });

  test('rechaza un dominio que no es oficial y lo nombra', () => {
    const r = revisarConsejos([{ ...bueno, url: 'https://blog-de-alguien.cl/x' }], HOY);
    assert.equal(r.ok, false);
    assert.ok(r.problemas.some((p) => p.includes('blog-de-alguien.cl')), `se esperaba un problema que nombre el dominio: ${r.problemas}`);
  });

  test('rechaza un consejo sin texto', () => {
    const r = revisarConsejos([{ ...bueno, text: '' }], HOY);
    assert.equal(r.ok, false);
  });

  test('acepta un subdominio de la lista blanca', () => {
    const r = revisarConsejos([{ ...bueno, url: 'https://www.senapred.cl/' }], HOY);
    assert.deepEqual(r.problemas, []);
    assert.equal(r.ok, true);
  });

  test('rechaza URLs repetidas', () => {
    const r = revisarConsejos([bueno, { ...bueno, text: 'Otro consejo distinto, también con el largo suficiente.' }], HOY);
    assert.equal(r.ok, false);
    assert.ok(r.problemas.some((p) => p.includes(bueno.url)));
  });

  test('rechaza una CONSULTA_FUENTES futura respecto de hoy', () => {
    const r = revisarConsejos(CONSEJOS_CALOR, '2020-01-01');
    assert.equal(r.ok, false);
    assert.ok(r.problemas.some((p) => p.includes('CONSULTA_FUENTES')));
  });

  test('la lista blanca sale del módulo, no del test', () => {
    for (const d of ['minsal.cl', 'senapred.cl', 'saludresponde.minsal.cl', 'who.int', 'samu.cl']) {
      assert.ok(DOMINIOS_OFICIALES.includes(d), `falta ${d} en DOMINIOS_OFICIALES`);
    }
  });
});
