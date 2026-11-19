---
id: PERF-11
repo: brasas
rama: perf/arranque-incidente-ligero
modelo: agente-alto
riesgo: A
archivos: web/js/incidente.js, web/js/views/incendio.js, web/js/popup.js, web/js/views/zona.js, web/index.html, web/sw.js, scripts/local/peso_arranque.py, tests/, CHANGELOG.md
e2e: si
---

# PERF-11 · Sacar la ficha de incendio del arranque y bajar el presupuesto de arranque

## Objetivo

Que la vista de incendio (`web/js/views/incendio.js`, ~14,7 KB gzip) deje de viajar en la carga
inicial: la portada («Mi zona») y las tarjetas solo necesitan sus etiquetas y el botón «Seguir»,
no el mapa, los gráficos ni el KML. Con eso el arranque bloqueante baja de 183,2 a 161,6 KB gzip y
`PRESUPUESTO_ARRANQUE_KB` baja de 194 a 175 KB, devolviendo holgura a las próximas vistas en vez
de subir el tope con cada feature.

## Contexto

- Pedido del BRASA Lead (19-11-2026): «hoy el presupuesto de arranque subió dos veces; mira si
  puedes devolverlo a la baja en vez de seguir subiéndolo, y que las próximas features no lo suban
  de nuevo».
- `views/incendio.js` entraba al grafo bloqueante solo porque `popup.js` y `views/zona.js` (ambos
  del arranque) importaban estáticamente `INCIDENT`, `incidentInfo` y `enlazarSeguimiento` de ahí;
  el router ya la cargaba con `import()` como al resto de las vistas.
- `api.js` importa `util.js`, así que el módulo compartido no puede vivir en `util.js` (ciclo):
  va en `web/js/incidente.js`, que importa de ambos.

## Qué se hizo

- `web/js/incidente.js` (nuevo, ~4 KB): `INCIDENT`, `FIXED`, `incidentInfo` y
  `enlazarSeguimiento`, con sus dependencias (`api.js`, `util.js`).
- `views/incendio.js` los re-exporta, así que `views/mapa.js`, `views/calidad.js`, `cerca.js` y
  `tests/js/incendio.test.mjs` siguen igual; el resto de la vista (mapa, gráficos, KML, PARALLAX)
  queda en carga diferida.
- `popup.js` y `views/zona.js` importan desde `incidente.js`.
- `index.html`: `modulepreload` suma `incidente.js` y retira `views/incendio.js` más los módulos
  que solo ella usaba en el arranque (`charts.js`, `errores.js`, `escenario.js`, `spreadtext.js`).
- `web/sw.js`: `incidente.js` entra al `SHELL` (sin él, la app no arranca sin conexión tras
  actualizarse); `SHELL_ENTRADAS_HOY` 86 → 87.
- `scripts/local/peso_arranque.py`: `PRESUPUESTO_ARRANQUE_KB` 194 → 175 (tope con holgura
  165 KB; medido 161,6 KB). El presupuesto total no cambia.
- `tests/test_peso_arranque.py`: la vista de incendio pasa a la sección diferida (la prueba
  documentaba el comportamiento anterior).

## Criterio de listo

- `tests/test_peso_arranque.py`, `tests/test_service_worker.py`, `tests/test_presupuestos_peso.py`,
  `tests/test_estaticas_guardas.py`, `tests/test_arranque_precarga.py` y `tests/js/incendio.test.mjs`
  en verde; CI del PR en verde con revisión de navegador (toca `web/sw.js`).
- La portada, las tarjetas y la ficha de incendio se comportan igual (etiquetas, «Seguir»,
  estados); la ficha carga su vista completa solo al abrirla.
