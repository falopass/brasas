/* Estado del historial de avisos (web/js/alertas-estado.js): un fallo no borra
 * lo cargado y deja marcado qué página reintentar. Sin DOM ni navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { conFallo, conPagina, estadoInicial } from '../../web/js/alertas-estado.js';

const aviso = (id) => ({ id, title: `Aviso ${id}` });

describe('alertas-estado: estadoInicial', () => {
  test('parte vacío, sin error ni reintento pendiente', () => {
    assert.deepEqual(estadoInicial(), {
      alerts: [], total: 0, nextBefore: null, loading: false, error: '', retry: null,
    });
  });
});

describe('alertas-estado: conPagina', () => {
  test('more:false reemplaza la lista y actualiza total y nextBefore', () => {
    const prev = { ...estadoInicial(), alerts: [aviso(1)], nextBefore: 'viejo' };
    const next = conPagina(prev, { alerts: [aviso(2), aviso(3)], total: 10, next_before: 'nuevo' }, false);
    assert.deepEqual(next.alerts.map((a) => a.id), [2, 3]);
    assert.equal(next.total, 10);
    assert.equal(next.nextBefore, 'nuevo');
    assert.equal(next.loading, false);
  });

  test('more:true agrega la página a lo ya cargado', () => {
    const prev = { ...estadoInicial(), alerts: [aviso(1)] };
    const next = conPagina(prev, { alerts: [aviso(2)], total: 2 }, true);
    assert.deepEqual(next.alerts.map((a) => a.id), [1, 2]);
    assert.equal(prev.alerts.length, 1); // el estado anterior no se muta
  });

  test('una página nueva limpia el error y el reintento', () => {
    const prev = conFallo({ ...estadoInicial(), alerts: [aviso(1)] }, 'sin conexión', true);
    const next = conPagina(prev, { alerts: [aviso(3)], total: 7, next_before: 'x' }, true);
    assert.equal(next.error, '');
    assert.equal(next.retry, null);
    assert.equal(next.total, 7);
    assert.equal(next.nextBefore, 'x');
    assert.deepEqual(next.alerts.map((a) => a.id), [1, 3]);
  });

  test('aplicar dos veces la misma página deja una sola fila por id', () => {
    let s = conPagina(estadoInicial(), { alerts: [aviso(1), aviso(2)], total: 4, next_before: 'p2' }, false);
    s = conPagina(s, { alerts: [aviso(1), aviso(2)], total: 4, next_before: 'p3' }, true);
    assert.deepEqual(s.alerts.map((a) => a.id), [1, 2]);
  });

  test('una página con repetidos no infla la lista más allá del total del servidor', () => {
    const prev = { ...estadoInicial(), alerts: [aviso(1), aviso(2)], total: 3, nextBefore: 'x' };
    const next = conPagina(prev, { alerts: [aviso(2), aviso(3)], total: 3, next_before: 'y' }, true);
    assert.equal(next.total, 3);
    assert.deepEqual(next.alerts.map((a) => a.id), [1, 2, 3]);
    assert.ok(next.alerts.length <= next.total);
  });

  test('si el aviso repetido cambió, gana la copia que llega última', () => {
    const viejo = { id: 1, title: 'Aviso 1', level: 'aviso', feedback: 'util' };
    const nuevo = { id: 1, title: 'Aviso 1', level: 'urgente', feedback: 'no_util' };
    const prev = { ...estadoInicial(), alerts: [viejo, aviso(2)], nextBefore: 'x' };
    const next = conPagina(prev, { alerts: [nuevo], total: 3, next_before: 'y' }, true);
    assert.deepEqual(next.alerts.map((a) => a.id), [1, 2]);
    assert.equal(next.alerts[0].level, 'urgente');
    assert.equal(next.alerts[0].feedback, 'no_util');
  });

  test('un aviso sin id se conserva tal cual, no se pierde ninguna fila', () => {
    const sinId = { title: 'Aviso sin id' };
    const prev = { ...estadoInicial(), alerts: [aviso(1), sinId], nextBefore: 'x' };
    const next = conPagina(prev, { alerts: [sinId, aviso(2)], total: 4, next_before: 'y' }, true);
    assert.equal(next.alerts.length, 4);
    assert.equal(next.alerts.filter((a) => a.id === undefined).length, 2);
  });

  test('next_before igual al cursor que se pidió deja nextBefore en null', () => {
    const prev = { ...estadoInicial(), alerts: [aviso(1)], nextBefore: 'x' };
    const next = conPagina(prev, { alerts: [aviso(2)], total: 5, next_before: 'x' }, true);
    assert.equal(next.nextBefore, null);
  });
});

describe('alertas-estado: conFallo', () => {
  test('fallo inicial deja alerts vacíos y retry «inicial»', () => {
    const next = conFallo(estadoInicial(), 'sin conexión', false);
    assert.deepEqual(next.alerts, []);
    assert.equal(next.error, 'sin conexión');
    assert.equal(next.retry, 'inicial');
    assert.equal(next.loading, false);
  });

  test('fallo de la página siguiente conserva los avisos y retry «siguiente»', () => {
    const prev = { ...estadoInicial(), alerts: [aviso(1), aviso(2)], total: 5, nextBefore: 'x' };
    const next = conFallo(prev, 'sin conexión', true);
    assert.deepEqual(next.alerts.map((a) => a.id), [1, 2]);
    assert.equal(next.nextBefore, 'x');
    assert.equal(next.retry, 'siguiente');
  });
});
