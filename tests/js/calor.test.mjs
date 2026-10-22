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
  test('incluye no dejar niños ni mascotas en el auto (MINSAL)', () => {
    const c = CONSEJOS_CALOR.find((x) => /auto estacionado/i.test(x.text));
    assert.ok(c, 'falta el consejo del auto estacionado');
    assert.match(c.source, /MINSAL/);
    assert.equal(new URL(c.url).hostname, 'degreyd.minsal.cl');
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

/* QA-207: la guarda que impide publicar un consejo de salud sin fuente oficial. Cada caso
 * rompe una sola regla para que el mensaje diga cuál. */
const consejo = (over = {}) => ({
  text: 'Bebe agua aunque no tengas sed durante todo el día, sobre todo si estás al sol.',
  source: 'SENAPRED: calor extremo',
  url: 'https://senapred.cl/calor-extremo/',
  ...over,
});

describe('revisarConsejos', () => {
  test('la lista publicada pasa la guarda', () => {
    const { ok, problemas } = revisarConsejos(CONSEJOS_CALOR, '2026-12-31');
    assert.deepEqual(problemas, []);
    assert.equal(ok, true);
  });

  test('una URL http se rechaza y el problema menciona https', () => {
    const { ok, problemas } = revisarConsejos([consejo({ url: 'http://www.minsal.cl/x' })], '2026-12-31');
    assert.equal(ok, false);
    assert.ok(problemas.some((p) => p.includes('https')), problemas.join(' · '));
  });

  test('un dominio que no es oficial se rechaza y el problema lo nombra', () => {
    const { ok, problemas } = revisarConsejos([consejo({ url: 'https://blog-de-alguien.cl/x' })], '2026-12-31');
    assert.equal(ok, false);
    assert.ok(problemas.some((p) => p.includes('blog-de-alguien.cl')), problemas.join(' · '));
  });

  test('un consejo sin texto se rechaza', () => {
    assert.equal(revisarConsejos([consejo({ text: '' })], '2026-12-31').ok, false);
  });

  test('un subdominio www de la lista blanca pasa', () => {
    const { ok } = revisarConsejos([consejo({ url: 'https://www.senapred.cl/' })], '2026-12-31');
    assert.equal(ok, true);
  });

  test('dos consejos con la misma URL se rechazan', () => {
    const { ok, problemas } = revisarConsejos([consejo(), consejo()], '2026-12-31');
    assert.equal(ok, false);
    assert.ok(problemas.some((p) => p.includes('repetida')), problemas.join(' · '));
  });

  test('una fecha de consulta en el futuro se rechaza contra hoy', () => {
    const { ok, problemas } = revisarConsejos(CONSEJOS_CALOR, '2026-01-01');
    assert.equal(ok, false);
    assert.ok(problemas.some((p) => p.includes('futuro')), problemas.join(' · '));
  });

  test('la lista blanca cubre los hosts que usa la app', () => {
    for (const c of CONSEJOS_CALOR) {
      const host = new URL(c.url).hostname;
      assert.ok(DOMINIOS_OFICIALES.some((d) => host === d || host.endsWith(`.${d}`)), `falta ${host} en DOMINIOS_OFICIALES`);
    }
  });
});
