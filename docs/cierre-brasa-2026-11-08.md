# Cierre de conciliación — 8 de noviembre de 2026

Reconcilia lo demostrado en `main` con la documentación que quedó atrás. Base verificada:
`e7e2c3f7` (merge de #806, 8-11 21:52). Documento de evidencia: no implementa nada ni
declara terminado lo que no tiene prueba. Las tandas del 4-11 se entregaron sin archivo
de encargo en `docs/backlog/` — este informe es su registro.

## Tanda 1 — mergeada el 4-11

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#788](https://github.com/falopass/brasas/pull/788) | Tiempos CONAF en la ficha, enlaces al meteograma Pyrocast y capa «Áreas protegidas (SNASPE)» en el mapa | `web/js/views/mapa.js`, `web/js/capas.js`, `web/js/popup.js`, `web/data/snaspe.json` (99 áreas), `tests/test_conaf_ops_snaspe.py` |
| [#789](https://github.com/falopass/brasas/pull/789) | Riesgo en 3 capas en la ficha de comuna (1. Condiciones del día · 2. Combustible acumulado · 3. Exposición territorial) y ranking «Peligro × Exposición»; campamentos del catastro MINVU en la exposición; Pyrocast (RISK-03, OFI-25, OFI-20) | `web/js/views/riesgo.js` (`capa1/2/3`, `sortMode`), `web/js/exposure.js` (`exposureFactor`: interfaz + Censo 2024 + campamentos), `tests/test_riesgo_3capas_campamentos.py`. Cierra el ítem 2.3 del plan |
| [#790](https://github.com/falopass/brasas/pull/790) | SNASPE en «Mi zona» (área protegida más cercana o dentro del polígono) y terreno post-incendio en la lluvia: `/api/climate/lluvia` devuelve `terreno` = lluvia × pendiente × huella de calor a ≤ 5 km | `web/js/views/zona.js` (`protectedAreaLine`, `terrenoNota`), `backend/lluvia.py` (`evaluar_terreno`), `backend/routes/climate.py`, `tests/test_zona_snaspe_aluvion.py` |
| [#791](https://github.com/falopass/brasas/pull/791) | «Calidad de los datos» muestra la latencia p50/p95 por ruta de la última hora y la concordancia comuna-día del índice con incendios y Botón Rojo de CONAF (CALIDAD-OBS, RISK-09) | `backend/routes/observability.py`, `web/js/views/calidad.js` (`latenciasRutas`, `concordanciaRiesgo`), `/api/observability/routes` y `/api/observability/concordancia` |

## Tanda 2 — mergeada el 4-11

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#792](https://github.com/falopass/brasas/pull/792) | SINCA: intento por `SINCA_PROXY_URL`, respaldo de borde en el Worker y snapshot local (`SINCA_SNAPSHOT_PATH`, válido ≤ 12 h, `source_mode: snapshot` con su hora real) (OFI-10) | `backend/providers/sinca.py`, `scripts/actualizar_sinca_snapshot.py`, `deploy/cloudflare/src/index.ts`, `tests/test_sinca_respaldo.py`, `.env.example`. El host sigue sin responder desde Cloudflare y la licencia MMA sigue pendiente — ver «Pendientes externos» |
| [#793](https://github.com/falopass/brasas/pull/793) | Infraestructura crítica a sotavento de un incendio (escuelas, salud, energía, agua en 5 km, OSM/Overpass ODbL) en la ficha de incidente (OSM-SOTAVENTO) | `backend/providers/overpass.py` (`build_critical_query`, `CRITICAL_TAGS`), `backend/routes/public.py`, `web/js/views/incendio.js`, `tests/test_infraestructura_sotavento.py` |
| [#795](https://github.com/falopass/brasas/pull/795) | Tres casos nuevos por macrozona (Rocuant y San Roque 2019, Reserva China Muerta 2015, Timaukel 2022) y el comparador «Condiciones de hoy vs. grandes incendios» (CONT-06, CLIMA-COMP) | `web/data/cases.json`, `web/js/views/casos.js` (`comparadorHtml`, `meteoDeHoy`), `tests/test_casos_catalogo.py` |

## Tanda 3 — mergeada el 4-11

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#794](https://github.com/falopass/brasas/pull/794) | Landsat 8/9 (OLI, 30 m) sumado a la ingesta FIRMS cuando hay `FIRMS_MAP_KEY`; familia propia en la confirmación multi-sensor (DET-07) | `backend/providers/firms.py` (`LANDSAT_NRT`), `backend/incidents.py` (`satellite_family`), `tests/test_firms_landsat.py` |
| [#796](https://github.com/falopass/brasas/pull/796) | Cicatrices históricas 2014-2024 en «Mi zona» y el mapa: inicios CONAF-GEPRIF de ≥ 50 ha; tres con perímetro simplificado real, el resto como superficie orientativa — nunca como perímetro oficial (CONAF-HIST-10Y) | `web/data/scars.json`, `web/js/views/mapa.js`, `web/js/views/zona.js`, `tests/test_scars.py` |
| [#797](https://github.com/falopass/brasas/pull/797) | Sequedad de la vegetación viva por satélite (NDVI MOD13Q1, 250 m) en la ficha de riesgo: anomalía de verdor frente al promedio de la misma fecha (RISK-11) | `web/data/vegetacion-sequedad.json`, `web/js/views/riesgo.js` (`htmlSequedad`), `scripts/actualizar_sequedad_vegetacion.py`, `tests/test_sequedad_vegetacion.py` |

**Antigüedad del NDVI, verificada:** la tarjeta muestra «Imagen del 14 de septiembre de
2026» (`imagen_en`, impresa por `fechaSequedad` en `riesgo.js:408-412`) — la fecha de la
imagen sí es visible para el vecino. El archivo cubre una **muestra** (17 comunas, 13
regiones, 4 macrozonas; `docs/COBERTURA.md`: 17/345, «sin cadencia» de regeneración
declarada) y fue generado el 4-11-2026. No se afirma actualidad: el dato visible es de
septiembre y la pantalla lo dice.

## Otros merges de la semana

- [#784](https://github.com/falopass/brasas/pull/784): perímetro oficial de CONAF encendido en producción (`CONAF_PERIMETRO_ENABLED`, OFI-03/OFI-17).
- [#799](https://github.com/falopass/brasas/pull/799), [#800](https://github.com/falopass/brasas/pull/800), [#801](https://github.com/falopass/brasas/pull/801): manchas de calor orgánicas, esqueletos de arranque + descarga del mapa en paralelo, huella que se atenúa con el zoom.
- [#804](https://github.com/falopass/brasas/pull/804), [#805](https://github.com/falopass/brasas/pull/805), [#806](https://github.com/falopass/brasas/pull/806): «Mi ubicación» abre incendios cercanos, un toque lleva al incendio y la hoja se restaura, ficha sin id ya no se rompe (MAPA-168/169).

## En tránsito al cierre de este documento (8-11, ~22:00)

- **PR [#803](https://github.com/falopass/brasas/pull/803)** — marcas de calor como anillos isoterma + descarga anticipada del mapa en «Mi zona» (MAPA-visual). Abierto, auto-merge por squash activado. En la última corrida el check `pytest` falló en el presupuesto de arranque (174,5 KB medidos vs. 174 KB de tope con holgura); el cuerpo del PR indica que el merge con `main` lo resuelve (el tope ya subió allí). «Revisión en navegador» seguía en curso.
- **PR [#807](https://github.com/falopass/brasas/pull/807)** — reservar el plan meteorológico (OPS-798) y diagnosticar latencia (OPS-802). Abierto, sin auto-merge, con comentarios de revisión del robot y del dueño. Reserva el cupo diario de Open-Meteo entre riesgo, FWI y lluvia, y registra `X-Brasa-Cache` por muestra en la sonda. Trae su propia evidencia en `docs/cierre-operacion-2026-11-08.md`. La causa original del p95 de 3072 ms sigue como hipótesis (posible miss de caché del borde) hasta que la sonda nueva capture las cabeceras.

## Issues abiertos (no se cierran aquí)

- **Issue [#798](https://github.com/falopass/brasas/issues/798)** — «riesgo viejo»: `risk_error` = «Sin cupo diario de Open-Meteo para el 30-30-30»; `risk_computed_at` superó el umbral de 6 h. Queda abierto hasta que el deploy de #807 (o la recuperación del cupo) se vea en la sonda.
- **Issue [#802](https://github.com/falopass/brasas/issues/802)** — `/api/status` con p95 3072 ms sobre el presupuesto de 2500 ms (n=3, p50 82 ms). Causa no comprobada; #807 agrega el diagnóstico que la aclarará.

## Qué falta, por tipo

**Código (en `main` falta, sin PR a la vista):**
- Aviso de aluvión por lugar guardado: `evaluar_terreno` y la señal de lluvia existen, pero BRASA declara «no emite avisos de aluvión» — los umbrales siguen provisionales por calibrar (`backend/lluvia.py`).
- Descartes por fuente en «Calidad de los datos» (única pieza del ítem 3.2 sin evidencia).
- Viento animado por partículas (RISK-07, 2.5) y dNBR de Sentinel-2 / caudales DGA (3.1): pendientes de decisión del dueño.
- Canales nuevos (2.6): Telegram quedó **descartado** el 3-11; SMS/WhatsApp esperan presupuesto.

**Operación:**
- Dominio propio (OPS-11): registrar el `.cl`, apuntarlo al Worker, fijar `PUBLIC_BASE_URL` y agregar el dominio al widget de Turnstile. Requiere una compra fuera de la autorización del agente; antes de sumar usuarios, porque push, app instalada y token de lugares quedan atados al dominio `workers.dev`.
- CHANGELOG: los PR #792 (SINCA respaldo), #793 (sotavento), #796 (cicatrices históricas) y #797 (NDVI) no agregaron entrada propia — queda anotado para el registro del release.

**Externos (no dependen del repo):**
- Licencia MMA/SINCA: consulta por Transparencia enviada; al responder se anota en `docs/FUENTES.md`. Mientras tanto el host `sinca.mma.gob.cl` no responde desde la red de Cloudflare (probable geocerca); el proxy/snapshot de #792 deja lista la vía cuando exista un canal alcanzable.
- Comunas prioritarias CONAF 2026-27 (`web/data/prioritarias.json`): sigue vacía a la espera del documento oficial.
- SENAPRED, CONAF y MINVU: **decididos el 3-11-2026** (acceso anónimo con cita / uso público confirmado) — no volver a consultar.

## Discrepancias resueltas en este cierre

- `README.md`: ya no dice «Fases 2 y 3 pendientes»; distingue fases del roadmap de las tandas entregadas.
- `docs/PLAN_NEXT_LEVEL.md`: 2.3 marcado ✅ (combinación de las 3 capas + ranking en `main`); 3.1 y 3.2 con el detalle actualizado; fecha de sincronización al 8-11-2026.
- `docs/backlog/README.md`: sigue en 0 encargos abiertos y ahora enlaza este informe para la ola del 4-8 de noviembre, que llegó sin archivo de encargo.
