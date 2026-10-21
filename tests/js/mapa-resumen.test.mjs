/* Pruebas de resumenMapa (web/js/map.js): la frase que anuncia un lector de pantalla
 * sobre el lienzo del mapa (accesibilidad MAPA). Lógica pura, sin navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { resumenMapa } from '../../web/js/map.js';

const MIN = 60000;
const HORA = 3600000;
const DIA = 86400000;
const AHORA = 1_700_000_000_000;
const focos = (n) => Array.from({ length: n }, () => ({}));

describe('resumenMapa: el mapa se puede leer sin verlo', () => {
  test('sin focos lo dice en claro', () => {
    const s = resumenMapa({ capas: ['focos'] });
    assert.match(s, /^Mapa: /);
    assert.match(s, /sin focos de calor a la vista/);
  });

  test('un solo foco, en singular', () => {
    assert.match(resumenMapa({ focos: focos(1) }), /Mapa: 1 foco de calor/);
  });

  test('varios focos cuentan puntos agrupados y separan los miles', () => {
    const s = resumenMapa({ focos: focos(1248), agrupados: 210 });
    assert.match(s, /1\.248 focos de calor en 210 puntos agrupados/);
  });

  test('un solo punto agrupado, en singular', () => {
    assert.match(resumenMapa({ focos: focos(14), agrupados: 1 }), /en 1 punto agrupado/);
  });

  test('sin agrupación real no se habla de puntos agrupados', () => {
    const s = resumenMapa({ focos: focos(3), agrupados: 3 });
    assert.match(s, /Mapa: 3 focos de calor/);
    assert.doesNotMatch(s, /agrupados/);
  });

  test('el dato más reciente dice su edad', () => {
    const s = resumenMapa({ focos: focos(2), ahora: AHORA, reciente: AHORA - 20 * MIN });
    assert.match(s, /el más reciente hace 20 minutos/);
  });

  test('edades largas pasan a horas y días; frescas a «recién»', () => {
    assert.match(resumenMapa({ focos: focos(2), ahora: AHORA, reciente: AHORA - 3 * HORA }), /hace 3 horas/);
    assert.match(resumenMapa({ focos: focos(2), ahora: AHORA, reciente: AHORA - 2 * DIA }), /hace 2 días/);
    assert.match(resumenMapa({ focos: focos(2), ahora: AHORA, reciente: AHORA - 5 * 1000 }), /recién/);
  });

  test('incendios de CONAF y avisos de vecinos, en singular y plural', () => {
    assert.match(resumenMapa({ incendios: 1 }), /1 incendio informado por CONAF/);
    assert.match(resumenMapa({ incendios: 3 }), /3 incendios informados por CONAF/);
    assert.match(resumenMapa({ reportes: 1 }), /1 reporte de vecinos/);
    assert.match(resumenMapa({ reportes: 2 }), /2 reportes de vecinos/);
  });

  test('las capas prendidas se nombran; sin capas se dice ninguna', () => {
    assert.match(resumenMapa({ capas: ['focos', 'incendios'] }), /Capas: focos, incendios\./);
    assert.match(resumenMapa({}), /Capas: ninguna\./);
  });

  test('la frase nunca usa jerga técnica', () => {
    const casos = [
      resumenMapa({}),
      resumenMapa({ focos: focos(5000), agrupados: 12, incendios: 4, reportes: 2, capas: ['focos'], ahora: AHORA, reciente: AHORA }),
      resumenMapa({ focos: focos(1), ahora: AHORA, reciente: AHORA - 5 * DIA }),
    ];
    for (const s of casos) {
      for (const jerga of ['FRP', 'decimación', 'píxel']) {
        assert.ok(!s.toLowerCase().includes(jerga.toLowerCase()), `«${jerga}» no debe aparecer en «${s}»`);
      }
    }
  });
});
