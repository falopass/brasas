/* Pruebas del latido de los focos (PERF-141): `latidoVigente` es pura — recibe visibilidad,
 * frescura de los datos y marcas de tiempo, y dice si el ciclo debe seguir pidiendo frames.
 * Todo corre en Node, sin navegador ni reloj real. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { LATIDO_REPOSO_MS, latidoVigente } from '../../web/js/map.js';

const AHORA = 1_000_000;
const base = { visible: true, focosRecientes: true, ahora: AHORA, ultimoCambio: AHORA, quietoDesde: AHORA };

describe('latidoVigente', () => {
  test('con la capa oculta no late', () => {
    assert.equal(latidoVigente({ ...base, visible: false }), false);
  });

  test('visible pero sin focos de menos de 3 h no late', () => {
    assert.equal(latidoVigente({ ...base, focosRecientes: false }), false);
  });

  test('visible con un foco de 1 h y datos de hace 2 s late', () => {
    assert.equal(latidoVigente({ ...base, ultimoCambio: AHORA - 2_000, quietoDesde: AHORA - 2_000 }), true);
  });

  test('25 s sin datos nuevos ni interacción: el latido duerme', () => {
    const quieto = AHORA - 25_000;
    assert.equal(latidoVigente({ ...base, ultimoCambio: quieto, quietoDesde: quieto }), false);
    assert.equal(latidoVigente({ ...base, ultimoCambio: null, quietoDesde: quieto }), false);
  });

  test('justo dentro de la ventana de reposo sigue latiendo; un paso más allá, no', () => {
    const limite = AHORA - LATIDO_REPOSO_MS;
    assert.equal(latidoVigente({ ...base, ultimoCambio: limite, quietoDesde: limite }), true);
    assert.equal(latidoVigente({ ...base, ultimoCambio: limite - 1, quietoDesde: limite - 1 }), false);
  });

  test('sin datos nuevos pero con interacción reciente (mover o tocar el mapa) late', () => {
    assert.equal(latidoVigente({ ...base, ultimoCambio: AHORA - 60_000, quietoDesde: AHORA - 5_000 }), true);
  });

  test('con prefers-reduced-motion el arranque no empieza nunca', () => {
    assert.equal(latidoVigente({ ...base, movimientoReducido: true }), false);
  });

  test('con el modo ahorro el latido queda apagado aunque todo lo demás lo pida (UX-76)', () => {
    assert.equal(latidoVigente({ ...base, ahorro: true }), false);
    assert.equal(latidoVigente({ ...base, ahorro: false }), true);
  });
});
