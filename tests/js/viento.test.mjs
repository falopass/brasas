/* Pruebas de web/js/viento.js (MAPA-187): indexación O(1), interpolación bilineal
 * vectorial (u, v), rotación por bearing, prioridad de subgrilla fina 0,25°, pasos
 * horarios +0/+3/+6/+12 h, ráfagas y escala de color por velocidad. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  colorVelocidad,
  esPasoVigente,
  etiquetaBotonPaso,
  etiquetaPasoViento,
  interpolarEnGrilla,
  interpolarViento,
  pasoMasCercano,
  PASOS_HORA,
  prepararGrilla,
  WIND_BANDS,
} from '../../web/js/viento.js';

const cerca = (a, b, tol = 1e-3, msg = '') => {
  assert.ok(Math.abs(a - b) <= tol, `${msg || 'valor'} esperado ${b} (±${tol}), recibido ${a}`);
};

function grillaUniforme({ step, lat0, lon0, rows, cols, speed, dir, gust, bbox }) {
  const n = rows * cols;
  return {
    step,
    lat0,
    lon0,
    rows,
    cols,
    ...(bbox ? { bbox } : {}),
    speed: Array(n).fill(speed),
    dir: Array(n).fill(dir),
    gust: Array(n).fill(gust),
  };
}

describe('interpolación bilineal O(1) en grilla regular', () => {
  const raw = {
    computed_at: '2026-11-23T12:00:00Z',
    step: 1.0,
    lat0: -36.0,
    lon0: -72.0,
    rows: 2,
    cols: 2,
    // Índice r * cols + c: (0,0) (-36,-72), (0,1) (-36,-71), (1,0) (-35,-72), (1,1) (-35,-71)
    speed: [10, 20, 30, 40],
    dir: [180, 180, 180, 180],
    gust: [18, 32, 44, 66],
  };
  const vista = prepararGrilla(raw, 0);

  test('en el centro exacto de una celda reproduce su velocidad, dirección y ráfaga', () => {
    const res = interpolarViento(vista, -71.0, -36.0, 0);
    assert.ok(res);
    cerca(res.u, 0, 1e-4, 'u');
    cerca(res.v, 20, 1e-4, 'v');
    cerca(res.speed, 20, 1e-4, 'speed');
    cerca(res.gust, 32, 1e-4, 'gust');
    cerca(res.vx, 0, 1e-4, 'vx');
    cerca(res.vy, -20 / 30, 1e-4, 'vy');
    assert.equal(res.fuente, 'base');
  });

  test('en el punto medio de 4 celdas promedia los 4 vecinos de forma exacta', () => {
    const res = interpolarViento(vista, -71.5, -35.5, 0);
    assert.ok(res);
    cerca(res.u, 0, 1e-4, 'u');
    cerca(res.v, 25, 1e-4, 'v');
    cerca(res.speed, 25, 1e-4, 'speed');
    cerca(res.gust, 40, 1e-4, 'gust');
  });

  test('omite vecinos sin dato (null) renormalizando los pesos válidos', () => {
    const conHueco = prepararGrilla({
      ...raw,
      speed: [10, 20, 30, null],
      dir: [180, 180, 180, null],
      gust: [18, 32, 44, null],
    }, 0);
    const res = interpolarEnGrilla(conHueco.base, -71.5, -35.5, 0);
    assert.ok(res);
    cerca(res.speed, 20, 1e-4, 'speed sin el cuarto vecino');
    cerca(res.gust, (18 + 32 + 44) / 3, 1e-3, 'gust sin el cuarto vecino');
  });

  test('fuera del dominio devuelve null', () => {
    assert.equal(interpolarViento(vista, -80.0, -35.5, 0), null);
    assert.equal(interpolarViento(vista, -71.5, -20.0, 0), null);
  });
});

describe('interpolación vectorial sin salto de 355° a 5°', () => {
  const vista = prepararGrilla({
    step: 1.0,
    lat0: -35.0,
    lon0: -72.0,
    rows: 1,
    cols: 2,
    speed: [20, 20],
    dir: [355, 5], // ambos vienen casi del norte (0°): deben soplar hacia el sur
    gust: [30, 34],
  }, 0);

  test('el promedio entre 355° y 5° sopla hacia el sur (vy > 0), nunca hacia el norte', () => {
    const res = interpolarViento(vista, -71.5, -35.0, 0);
    assert.ok(res);
    cerca(res.u, 0, 1e-4, 'componente este casi nula');
    assert.ok(res.v < -19, `debe soplar al sur (v < -19), recibido ${res.v}`);
    cerca(res.vx, 0, 1e-4, 'vx');
    assert.ok(res.vy > 0.6, `en pantalla debe bajar (vy > 0), recibido ${res.vy}`);
    cerca(res.gust, 32, 1e-4, 'gust interpolado');
  });
});

describe('rotación por bearing del mapa', () => {
  test('viento desde el sur (dir=180°) rota correctamente en 0°, 90°, 180° y 270°', () => {
    const vista = prepararGrilla(grillaUniforme({
      step: 1.0, lat0: -35.0, lon0: -71.0, rows: 1, cols: 1, speed: 30, dir: 180, gust: 45,
    }), 0);

    const b0 = interpolarViento(vista, -71.0, -35.0, 0);
    cerca(b0.vx, 0, 1e-4, 'bearing 0 vx');
    cerca(b0.vy, -1, 1e-4, 'bearing 0 vy (sube)');

    const b90 = interpolarViento(vista, -71.0, -35.0, 90);
    cerca(b90.vx, -1, 1e-4, 'bearing 90 vx (izquierda)');
    cerca(b90.vy, 0, 1e-4, 'bearing 90 vy');

    const b180 = interpolarViento(vista, -71.0, -35.0, 180);
    cerca(b180.vx, 0, 1e-4, 'bearing 180 vx');
    cerca(b180.vy, 1, 1e-4, 'bearing 180 vy (baja)');

    const b270 = interpolarViento(vista, -71.0, -35.0, 270);
    cerca(b270.vx, 1, 1e-4, 'bearing 270 vx (derecha)');
    cerca(b270.vy, 0, 1e-4, 'bearing 270 vy');
  });

  test('viento desde el oeste (dir=270°) sube con bearing=90°', () => {
    const vista = prepararGrilla(grillaUniforme({
      step: 1.0, lat0: -35.0, lon0: -71.0, rows: 1, cols: 1, speed: 30, dir: 270, gust: 40,
    }), 0);
    const b90 = interpolarViento(vista, -71.0, -35.0, 90);
    cerca(b90.vx, 0, 1e-4, 'bearing 90 vx');
    cerca(b90.vy, -1, 1e-4, 'bearing 90 vy (sube)');
  });
});

describe('subgrilla fina 0,25° y respaldo automático a 1°', () => {
  const fineBbox = [-73.5, -39.5, -70.5, -32.25];
  const payload = {
    computed_at: '2026-11-23T12:00:00Z',
    ...grillaUniforme({
      step: 1.0, lat0: -41.5, lon0: -74.5, rows: 12, cols: 6, speed: 12, dir: 180, gust: 18,
    }),
    fine: grillaUniforme({
      step: 0.25, lat0: -39.5, lon0: -73.5, rows: 30, cols: 13, speed: 42, dir: 270, gust: 64, bbox: fineBbox,
    }),
  };

  test('prioriza la subgrilla fina 0,25° dentro de FINE_BBOX y usa 1° fuera de ella', () => {
    const vista = prepararGrilla(payload, 0);
    const dentro = interpolarViento(vista, -71.65, -35.43, 0);
    assert.ok(dentro);
    assert.equal(dentro.fuente, 'fine');
    cerca(dentro.speed, 42, 1e-3, 'velocidad fina');
    cerca(dentro.gust, 64, 1e-3, 'ráfaga fina');

    const norte = interpolarViento(vista, -71.2, -31.2, 0);
    assert.ok(norte);
    assert.equal(norte.fuente, 'base');
    cerca(norte.speed, 12, 1e-3, 'velocidad base norte');
    cerca(norte.gust, 18, 1e-3, 'ráfaga base norte');

    const sur = interpolarViento(vista, -73.0, -40.8, 0);
    assert.ok(sur);
    assert.equal(sur.fuente, 'base');
    cerca(sur.speed, 12, 1e-3, 'velocidad base sur');
  });

  test('sin subgrilla fina (null) cae de forma transparente a la grilla base 1°', () => {
    const vista = prepararGrilla({ ...payload, fine: null }, 0);
    const res = interpolarViento(vista, -71.65, -35.43, 0);
    assert.ok(res);
    assert.equal(res.fuente, 'base');
    cerca(res.speed, 12, 1e-3);
  });

  test('payload legado sin rows/cols cae al respaldo por points', () => {
    const vista = prepararGrilla({
      computed_at: '2026-11-23T12:00:00Z',
      points: [[-35.5, -71.5]],
      speed: [18],
      dir: [180],
    }, 0);
    const res = interpolarViento(vista, -71.5, -35.5, 0);
    assert.ok(res);
    assert.equal(res.fuente, 'legado');
    cerca(res.speed, 18, 1e-3);
    assert.equal(res.gust, null);
  });
});

describe('pasos horarios +0/+3/+6/+12 h y ráfagas interpoladas', () => {
  const payload = {
    computed_at: '2026-11-23T12:00:00Z',
    step: 1.0,
    lat0: -36.0,
    lon0: -72.0,
    rows: 1,
    cols: 2,
    speed: [10, 20],
    dir: [180, 180],
    gust: [16, 28],
    steps: {
      0: { at: '2026-11-23T12:00:00Z', speed: [10, 20], dir: [180, 180], gust: [16, 28] },
      3: { at: '2026-11-23T15:00:00Z', speed: [20, 30], dir: [270, 270], gust: [34, 46] },
      6: { at: '2026-11-23T18:00:00Z', speed: [35, 45], dir: [270, 270], gust: [52, 68] },
      12: { at: '2026-11-24T00:00:00Z', speed: [8, 12], dir: [90, 90], gust: [14, 22] },
    },
  };

  test('cada paso prepara sus vectores, marca de tiempo y ráfaga máxima', () => {
    assert.deepEqual(PASOS_HORA, [0, 3, 6, 12]);
    const esperados = [
      [0, '2026-11-23T12:00:00Z', 15, 22, 28],
      [3, '2026-11-23T15:00:00Z', 25, 40, 46],
      [6, '2026-11-23T18:00:00Z', 40, 60, 68],
      [12, '2026-11-24T00:00:00Z', 10, 18, 22],
    ];
    for (const [paso, at, spdEsp, gustEsp, maxEsp] of esperados) {
      const v = prepararGrilla(payload, paso);
      assert.equal(v.pasoHora, paso);
      assert.deepEqual(v.pasos, [0, 3, 6, 12]);
      assert.equal(v.at, at);
      assert.equal(v.rafagaMaxKmh, maxEsp);
      const muestra = interpolarViento(v, -71.5, -36.0, 0);
      cerca(muestra.speed, spdEsp, 1e-3, `speed +${paso}h`);
      cerca(muestra.gust, gustEsp, 1e-3, `gust +${paso}h`);
    }
  });

  test('un paso inexistente cae al paso 0 disponible', () => {
    const v = prepararGrilla(payload, 99);
    assert.equal(v.pasoHora, 0);
  });
});

describe('escala de color por velocidad (WIND_BANDS y colorVelocidad)', () => {
  test('clasifica los cuatro tramos (<15, 15–30, 30–50 y >50 km/h)', () => {
    assert.equal(WIND_BANDS.length, 4);
    assert.equal(colorVelocidad(0), '#5aa0d8');
    assert.equal(colorVelocidad(14.9), '#5aa0d8');
    assert.equal(colorVelocidad(NaN), '#5aa0d8');
    assert.equal(colorVelocidad(15), '#2ec4b6');
    assert.equal(colorVelocidad(29.9), '#2ec4b6');
    assert.equal(colorVelocidad(30), '#f59f00');
    assert.equal(colorVelocidad(49.9), '#f59f00');
    assert.equal(colorVelocidad(50), '#e03131');
    assert.equal(colorVelocidad(85), '#e03131');
    // Variante de mayor contraste para mapa claro.
    assert.equal(colorVelocidad(10, true), '#1d4ed8');
    assert.equal(colorVelocidad(60, true), '#b91c1c');
  });
});

describe('frescura del paso horario y cobertura en los extremos de Chile', () => {
  test('con grilla de hace 6 h, elige +6 h como paso vigente y nunca llama «Ahora» al paso 0', () => {
    const payload6h = {
      computed_at: '2026-11-23T12:00:00Z',
      step: 1.0,
      lat0: -36.0,
      lon0: -72.0,
      rows: 1,
      cols: 1,
      speed: [12],
      dir: [180],
      gust: [20],
      steps: {
        0: { at: '2026-11-23T12:00:00Z', speed: [12], dir: [180], gust: [20] },
        3: { at: '2026-11-23T15:00:00Z', speed: [18], dir: [180], gust: [28] },
        6: { at: '2026-11-23T18:00:00Z', speed: [26], dir: [220], gust: [40] },
        12: { at: '2026-11-24T00:00:00Z', speed: [14], dir: [200], gust: [22] },
      },
    };
    const ahoraMs = Date.parse('2026-11-23T18:05:00Z');
    assert.equal(pasoMasCercano(payload6h, ahoraMs), 6);
    assert.equal(esPasoVigente(payload6h.steps[0].at, ahoraMs), false);
    assert.equal(esPasoVigente(payload6h.steps[6].at, ahoraMs), true);
    assert.ok(!etiquetaPasoViento(0, payload6h.steps[0].at, ahoraMs).includes('Ahora'));
    assert.ok(!etiquetaBotonPaso(0, payload6h.steps[0].at, ahoraMs).includes('Ahora'));
    assert.equal(etiquetaBotonPaso(6, payload6h.steps[6].at, ahoraMs), 'Ahora');
    assert.ok(etiquetaPasoViento(6, payload6h.steps[6].at, ahoraMs).startsWith('Ahora ('));
  });

  test('la grilla base 1° real (-55.5, -75.5, 38×10) cubre Visviri (-17.6) y Cabo de Hornos (-55.98)', () => {
    const baseChile = prepararGrilla({
      computed_at: '2026-11-23T12:00:00Z',
      ...grillaUniforme({
        step: 1.0, lat0: -55.5, lon0: -75.5, rows: 38, cols: 10, speed: 22, dir: 210, gust: 35,
      }),
    }, 0);
    const visviri = interpolarViento(baseChile, -69.5, -17.6, 0);
    assert.ok(visviri, 'Visviri (-17.6) debe recibir viento desde la grilla base');
    assert.equal(visviri.fuente, 'base');
    const hornos = interpolarViento(baseChile, -67.27, -55.98, 0);
    assert.ok(hornos, 'Cabo de Hornos (-55.98) debe recibir viento desde la grilla base');
    assert.equal(hornos.fuente, 'base');
  });
});

