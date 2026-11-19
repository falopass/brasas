---
id: MAPA-196
titulo: El globo 3D no sigue pintando cuando está oculto (pausa del bucle de render)
estado: en curso
riesgo: A
archivos: web/js/globe.js, web/js/views/casos.js, tests/js/globe.test.mjs, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# El globo 3D no sigue pintando cuando está oculto

## Encargo
Auditoría del globo 3D en teléfonos de gama media (pedido del Lead, ronda del mapa):
tiempo hasta el primer globo, memoria, FPS al rotar y liberación al volver al mapa 2D.
Si hay mejora medible, PR con antes y después.

## Qué se midió (prod, Playwright 390×844 dpr 3, CPU 4×, 2026-11-19 ~19:20)
- Primer lienzo del globo a los ~2,8 s; asentado con 178 teselas EOx a los ~14,5 s.
- Con el globo abierto y quieto: 99,8 % del hilo principal ocupado (7 fps, cuadros de ~150 ms).
- Al rotar: 6,3 fps, p95 217 ms por cuadro.
- Al volver a 2D (`#v2d`) y al salir a `#/mapa`: quedaban ~9,5–11 % del hilo principal
  robados por el visor de Cesium, que seguía repintando un lienzo oculto en cada cuadro
  (`useDefaultRenderLoop` nunca se apagaba fuera de la pestaña oculta).

## Qué se hizo
`setGlobeRendering(on)` en `web/js/globe.js`: pausa el bucle de render de Cesium cuando el
globo no está a la vista y lo reanuda pidiendo un cuadro (se ve al instante). `casos.js` lo
llama al volver a 2D (`show2D`), al reabrir el 3D (`toggle3D`) y al desmontar la vista
(`unmount`). El manejador de visibilidad de pestaña respeta la pausa para no reencenderlo.

## Verificación
- `node --test tests/js/globe.test.mjs`: 22/22 (3 nuevas: pausa/reanuda, visibilidad de
  pestaña con pausa, sin visor).
- Antes/después medido en prod con `/tmp/globo_cpu.py` (TaskDuration vía CDP):
  antes `tras_v2d` 9,5 % y `en_mapa_tras_globo` 11,1 % de hilo principal ocupado;
  el después se completa tras el deploy con la misma corrida.
- El globo abierto y quieto sigue al ~100 % (bucle por defecto de Cesium): es inherente al
  visor; una versión bajo demanda (requestRender) queda como ronda futura porque exige
  probar vuelos de cámara e interacción.

## Riesgo
A: solo cambia cuándo Cesium pinta; el contenido del globo no cambia. Al reabrir se pide
un cuadro explícito para que no quede en blanco.
