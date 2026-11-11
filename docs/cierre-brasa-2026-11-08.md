# Cierre de conciliación — 8 de noviembre de 2026

Reconcilia lo demostrado en `main` con la documentación que quedó atrás. Base verificada:
`e7e2c3f7` (merge de #806, 8-11 21:52); **ampliado al 11-11 con base `5bea710e`** (merge de
#821) — ver «Continuación». Documento de evidencia: no implementa nada ni declara terminado
lo que no tiene prueba. Las tandas del 4-11 se entregaron sin archivo de encargo en
`docs/backlog/` — este informe es su registro.

Esta ampliación se escribió en un worktree de texto. El bloque delegado a SWE-2 de
medición y Playwright se ejecuta por SSH en devin-vm; el notebook solo coordina.

Las primeras ejecuciones de las tandas 2 y 3 fallaron por cuota del proveedor
(`Usage Limit Reached`). Sus tareas se retomaron después y los seis bloques
se fusionaron: el fallo de esos hilos no significa trabajo de código pendiente.

## Tanda 1 — fusionada el 4 y 5 de noviembre

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#788](https://github.com/falopass/brasas/pull/788) | Tiempos CONAF en la ficha, enlaces al meteograma Pyrocast y capa «Áreas protegidas (SNASPE)» en el mapa | `web/js/views/mapa.js`, `web/js/capas.js`, `web/js/popup.js`, `web/data/snaspe.json` (99 áreas), `tests/test_conaf_ops_snaspe.py` |
| [#789](https://github.com/falopass/brasas/pull/789) | Riesgo en 3 capas en la ficha de comuna (1. Condiciones del día · 2. Combustible acumulado · 3. Exposición territorial) y ranking «Peligro × Exposición»; campamentos del catastro MINVU en la exposición; Pyrocast (RISK-03, OFI-25, OFI-20) | `web/js/views/riesgo.js` (`capa1/2/3`, `sortMode`), `web/js/exposure.js` (`exposureFactor`: interfaz + Censo 2024 + campamentos), `tests/test_riesgo_3capas_campamentos.py`. Cierra el ítem 2.3 del plan |
| [#790](https://github.com/falopass/brasas/pull/790) | SNASPE en «Mi zona» (área protegida más cercana o dentro del polígono) y terreno post-incendio en la lluvia: `/api/climate/lluvia` devuelve `terreno` = lluvia × pendiente × huella de calor a ≤ 5 km | `web/js/views/zona.js` (`protectedAreaLine`, `terrenoNota`), `backend/lluvia.py` (`evaluar_terreno`), `backend/routes/climate.py`, `tests/test_zona_snaspe_aluvion.py` |
| [#791](https://github.com/falopass/brasas/pull/791) | «Calidad de los datos» muestra la latencia p50/p95 por ruta de la última hora y la concordancia comuna-día del índice con incendios y Botón Rojo de CONAF (CALIDAD-OBS, RISK-09) | `backend/routes/observability.py`, `web/js/views/calidad.js` (`latenciasRutas`, `concordanciaRiesgo`), `/api/observability/routes` y `/api/observability/concordancia` |

## Tanda 2 — recuperada y fusionada el 4 y 5 de noviembre

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#796](https://github.com/falopass/brasas/pull/796) | Cicatrices históricas 2014-2024 en «Mi zona» y el mapa: inicios CONAF-GEPRIF de ≥ 50 ha; tres con perímetro simplificado real, el resto como superficie orientativa — nunca como perímetro oficial (CONAF-HIST-10Y) | `web/data/scars.json`, `web/js/views/mapa.js`, `web/js/views/zona.js`, `tests/test_scars.py` |
| [#793](https://github.com/falopass/brasas/pull/793) | Infraestructura crítica a sotavento de un incendio (escuelas, salud, energía, agua en 5 km, OSM/Overpass ODbL) en la ficha de incidente (OSM-SOTAVENTO) | `backend/providers/overpass.py` (`build_critical_query`, `CRITICAL_TAGS`), `backend/routes/public.py`, `web/js/views/incendio.js`, `tests/test_infraestructura_sotavento.py` |
| [#795](https://github.com/falopass/brasas/pull/795) | Tres casos nuevos por macrozona (Rocuant y San Roque 2019, Reserva China Muerta 2015, Timaukel 2022) y el comparador «Condiciones de hoy vs. grandes incendios» (CONT-06, CLIMA-COMP) | `web/data/cases.json`, `web/js/views/casos.js` (`comparadorHtml`, `meteoDeHoy`), `tests/test_casos_catalogo.py` |

## Tanda 3 — recuperada y fusionada el 4 y 5 de noviembre

| PR | Qué quedó en `main` | Evidencia |
|---|---|---|
| [#792](https://github.com/falopass/brasas/pull/792) | SINCA: intento por `SINCA_PROXY_URL`, respaldo de borde en el Worker y snapshot local (`SINCA_SNAPSHOT_PATH`, válido ≤ 12 h, `source_mode: snapshot` con su hora real) (OFI-10) | `backend/providers/sinca.py`, `scripts/actualizar_sinca_snapshot.py`, `deploy/cloudflare/src/index.ts`, `tests/test_sinca_respaldo.py`, `.env.example`. El host sigue sin responder desde Cloudflare y la licencia MMA sigue pendiente — ver «Pendientes externos» |
| [#794](https://github.com/falopass/brasas/pull/794) | Landsat 8/9 (OLI, 30 m) sumado a la ingesta FIRMS cuando hay `FIRMS_MAP_KEY`; familia propia en la confirmación multi-sensor (DET-07) | `backend/providers/firms.py` (`LANDSAT_NRT`), `backend/incidents.py` (`satellite_family`), `tests/test_firms_landsat.py` |
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

## Código integrado durante el cierre (8-11, 22:29 de Chile)

- **PR [#803](https://github.com/falopass/brasas/pull/803)** — fusionado en `c3614027`: marcas de calor como anillos isoterma y descarga anticipada del mapa en «Mi zona» (MAPA-visual). El CI del head `0cfdb0c3` pasó pytest, web y revisión en navegador. Se redujeron duplicaciones y comentarios para conservar la holgura de arranque; presupuestos y assertions intactos. Ambos comentarios de Devin Review quedaron corregidos.
- **PR [#807](https://github.com/falopass/brasas/pull/807)** — fusionado en `e87113a3`: reserva pendiente del plan de riesgo, FWI y lluvia (OPS-798), diagnóstico `X-Brasa-Cache` por muestra (OPS-802) y monitoreo de `risk_error` textual. CI completo del head `ffa7c1ab` en verde y revisión geo final aprobada. Evidencia causal en `docs/cierre-operacion-2026-11-08.md`. Los tiempos originales de #802 no prueban por sí solos un miss de caché.

## Continuación — merges del 10 y 11 de noviembre

Auditoría de lo que entró a `main` después de este cierre. «CI» = `pytest`, `web` y
Revisión en navegador del PR (esta última se omite cuando el diff no toca la interfaz);
«producción» = lo que solo se ve con el servicio desplegado. Los merges que tocaron el
backend, la web o el Worker dispararon su despliegue automático; los runs citados abajo
terminaron en verde. El cambio de ruff y los documentos no requieren despliegue.

- **OPS-813 — `/api/status` sin recorrer toda la tabla ni bloquear el servidor.**
  [#815](https://github.com/falopass/brasas/pull/815) mergeado en `75a6345` (10-11 02:22 UTC)
  y su corrección de tipos [#816](https://github.com/falopass/brasas/pull/816) en `51a1c82`
  (02:33 UTC). Poda de `ingest_runs` al final del ciclo (`prune_ingest_runs`, retención de
  7 días conservando la última y la última buena de cada producto), índice
  `work.ingest_runs_started`, armado del estado en `backend/status.py` ejecutado con
  `asyncio.to_thread`, consultas `done` de GOES acotadas a 26 h, tramos SQLite del ciclo
  movidos a hilo y `process: {started_at, startup_ms}` nuevo en la respuesta. Pruebas:
  `tests/test_ingest_runs.py` (poda + ~20.000 corridas con `EXPLAIN QUERY PLAN` sin `SCAN`
  de la tabla). CI verde en ambos PRs. Cierra el issue [#813](https://github.com/falopass/brasas/issues/813)
  (p95 de 3163 ms); la latencia real bajo el umbral quedó confirmada por la sonda posterior
  en producción (abajo).
- **OPS-817 — datos públicos desde una copia en R2 mientras el contenedor despierta.**
  [#817](https://github.com/falopass/brasas/pull/817) mergeado en `a9e7df2` (03:05 UTC) y
  [#819](https://github.com/falopass/brasas/pull/819) en `4cdc4bd` (03:25 UTC). El Worker
  copia a `public/` en R2 las seis respuestas canónicas tras cada `tick` exitoso
  (`deploy/cloudflare/src/copias.ts`, metadata `generada`, tope de 25 min) y `cachedApi`
  las sirve con `X-Brasa-Cache: snapshot` cuando el borde no tiene copia vigente — a lo más
  una consulta R2 por ventana de frescura (`copiaLastTry`). El sello `x-brasa-generada`
  evita que una copia más vieja pise lo que el borde ya guarda, y `serveStatus` corrige la
  edad y el `stale` por familia también en entregas vigentes (#819: una copia recién
  guardada decía «hace 0 min» — medido en producción `age_seconds` 3 a los 55 s de
  generada). Pruebas: `deploy/cloudflare/test/copias.test.mjs` y
  `tests/test_copias_canonicas.py`, que coteja la lista con `api.js`/`data.js`/`store.js`.
  CI verde (navegador omitido: no toca `web/`). **Lo que el CI no prueba:** la existencia
  física de las copias en el bucket de producción no la expone ninguna API pública;
  `X-Brasa-Cache: snapshot` acredita que una respuesta salió de R2, pero no demuestra por
  sí sola que el contenedor estuviera dormido. La evidencia nueva se adjunta aparte.
- **OPS-818 — arranque en frío medido por fases y respaldo compacto.**
  [#818](https://github.com/falopass/brasas/pull/818) mergeado en `aefc818` (03:25 UTC).
  `/api/status` suma `process.startup` por fases (`territory_ms`, `restore_work_ms`,
  `restore_db_ms`, `restore_work_parts`) y `work_db_bytes` (tamaño lógico); `snapshot_work`
  pasa a `VACUUM INTO`, así la copia ya no arrastra las páginas libres que dejó la poda de
  OPS-813; `restore_work` baja a `quick_check` (`work.db` se reconstruye; `brasa.db`
  conserva `integrity_check`); `territory()` corre en hilo en paralelo a `svc.start()` y la
  descompresión del gzip también va a hilo. Pruebas: `test_db_work.py` (`freelist_count = 0`,
  archivo más chico y restaurable, base viva en WAL), `test_storage.py`, `test_backup_size.py`.
  CI verde completo. **Lo que el CI no prueba:** que el objeto del respaldo en R2 sea
  efectivamente más chico ni que el arranque real del contenedor baje con el código nuevo —
  `work_db_bytes` reporta el tamaño lógico de la base, no el del archivo físico ni el del
  `-wal`. La API permite comprobar fases y tamaños declarados por el servicio; no
  expone las filas retenidas ni `freelist_count` de la base viva. No se afirma una
  inspección física de la poda en producción.
- **Dependabot:** [#809](https://github.com/falopass/brasas/pull/809) mergeado en `ef43283`
  (11-11 00:27:46 UTC; grupo menores-y-parches de `deploy/cloudflare`) y
  [#810](https://github.com/falopass/brasas/pull/810) en `7c20e22` (00:28:46 UTC; ruff
  0.17.3 → 0.17.4). CI verde y revisión automática sin hallazgos en ambos.
- **Otros merges del tramo:** [#814](https://github.com/falopass/brasas/pull/814) en
  `8e76f2e` (02:09 UTC) — la app y «Calidad de los datos» pintan sin esperar al servidor
  (CARGA-UI; `/api/config` pasa al caché del borde con 60 s).
  [#811](https://github.com/falopass/brasas/pull/811) en `65feaef` (03:35 UTC) — dependabot
  `python-multipart` ≥ 0.0.33. [#820](https://github.com/falopass/brasas/pull/820) en
  `f650cdd` (03:35 UTC) — la cita del verdor enlaza la ficha MOD13Q1 en NASA Earthdata;
  cierra el issue [#812](https://github.com/falopass/brasas/issues/812) (enlace caído de
  `modis.gsfc.nasa.gov`). [#821](https://github.com/falopass/brasas/pull/821) en `5bea710`
  (11-11 00:32:38 UTC) — checklist OPS-11 del dominio `.cl` en `docs/DOMINIO_CL.md`:
  procedimiento completo para el dueño, **nada ejecutado** — el nombre sigue sin elegir ni
  comprar.

## Verificación de producción

- Despliegue automático [42545820566](https://github.com/falopass/brasas/actions/runs/42545820566): `c3614027`, terminado en verde el 9-11 a las 01:34:09 UTC. Incluye #803 y #807.
- GET `/api/health`: HTTP 200, `status: ok`, versión `0.9.0`, a las 01:36:07 UTC. `/web/sw.js` declara `brasa-c3614027`; `util.js` sirve el anillo y `index.html` la conexión anticipada de teselas.
- GET `/api/status?history=3&cierre=c3614027-20261109T0140`: HTTP 200, respuesta generada a las 01:37:20 UTC. Ingesta 01:31:06 UTC, `failed_sources: []`, `backup: true`. El riesgo seguía fechado el 8-11 a las 18:51:13 UTC; cupo del día de Chile: 8718/9000.
- Sonda posterior al despliegue [42546488299](https://github.com/falopass/brasas/actions/runs/42546488299): finalizó en verde a las 01:37:24 UTC; las 15 rutas respondieron con p95 dentro de 2500 ms, sin cambiar el umbral.
- Las sondas son de solo lectura. No se ejecutaron pruebas, builds, servidores ni navegador en el notebook.

### Después de este cierre (10 y 11-11)

- Despliegue automático en verde tras cada merge del tramo:
  [42740745388](https://github.com/falopass/brasas/actions/runs/42740745388) (`8e76f2e`),
  [42742296828](https://github.com/falopass/brasas/actions/runs/42742296828) (`75a6345`),
  [42743577263](https://github.com/falopass/brasas/actions/runs/42743577263) (`51a1c82`),
  [42747083573](https://github.com/falopass/brasas/actions/runs/42747083573) (`a9e7df2`),
  [42749325729](https://github.com/falopass/brasas/actions/runs/42749325729) (`4cdc4bd`),
  [42749377742](https://github.com/falopass/brasas/actions/runs/42749377742) (`aefc818`),
  [42750421646](https://github.com/falopass/brasas/actions/runs/42750421646) (`65feaef`),
  [42750441014](https://github.com/falopass/brasas/actions/runs/42750441014) (`f650cdd`) y
  [42931538405](https://github.com/falopass/brasas/actions/runs/42931538405) (`ef43283`).
- Sonda de latencia [42895118059](https://github.com/falopass/brasas/actions/runs/42895118059):
  verde el 10-11 a las 20:25 UTC sobre `f650cdd7`, con la poda de OPS-813 ya desplegada.
  Los merges posteriores solo tocan dev-deps y documentación.
- Monitoreo de ingesta [42928337747](https://github.com/falopass/brasas/actions/runs/42928337747):
  verde el 11-11 a las 00:03 UTC sobre el mismo SHA.
- **Medición nueva pendiente de adjuntar:** SWE-2 toma por SSH en devin-vm las fases de
  `process.startup`, los tamaños declarados del respaldo, las 15 rutas y las capturas
  móvil/escritorio. Este documento no anticipa resultados. Por instrucción del dueño,
  Instabox queda excluida; para SSH solo se autorizan `desktop` y `devin-vm`.

## Seguimiento de issues

Verificado al 11-11: **0 issues abiertos**.

- **Issue [#798](https://github.com/falopass/brasas/issues/798)** — cerrado el 10-11 a las
  03:28 UTC con evidencia en producción: `risk_computed_at` = 2026-11-10T00:41:24Z (2,8 h,
  bajo el umbral de 6 h) y `last_cycle.risk_error` vacío en el GET `/api/status` de las
  03:26 UTC. El riesgo se recalculó con el cupo del día nuevo de `America/Santiago`; si
  vuelve a pasar, el monitoreo abre un issue nuevo.
- **Issue [#802](https://github.com/falopass/brasas/issues/802)** — cerrado el 9-11 tras la
  sonda posterior al despliegue: presupuesto de 2500 ms cumplido. El origen de los 3072 ms
  anteriores (n=3, p50 82 ms) no quedó demostrado; #807 agrega cabeceras `X-Brasa-Cache`
  por muestra para diagnosticar una recurrencia. El monitoreo continúa activo.
- **Issue [#813](https://github.com/falopass/brasas/issues/813)** — cerrado el 10-11 con el
  merge de #815 (ver «Continuación»).
- **Issue [#812](https://github.com/falopass/brasas/issues/812)** — cerrado el 10-11 con el
  merge de #820.

## Qué falta, por tipo

**Código (en `main` falta, sin PR a la vista):**
- Aviso de aluvión por lugar guardado: `evaluar_terreno` y la señal de lluvia existen, pero BRASA declara «no emite avisos de aluvión» — los umbrales siguen provisionales por calibrar (`backend/lluvia.py`).
- Descartes por fuente en «Calidad de los datos» (única pieza del ítem 3.2 sin evidencia).
- dNBR de Sentinel-2 / caudales DGA (3.1): ampliaciones del roadmap pendientes de decisión. El viento animado ya se entregó en #700, con grilla de 1° cada 6 h y alternativa estática.
- Canales nuevos (2.6): Telegram quedó **descartado** el 3-11; SMS/WhatsApp esperan presupuesto.

**Operación:**
- Dominio propio (OPS-11): el procedimiento completo ya está escrito en `docs/DOMINIO_CL.md`
  (#821) — registro en NIC Chile, zona en Cloudflare, delegación de nameservers, corte de
  `PUBLIC_BASE_URL` y alta del dominio en Turnstile. **Nada ejecutado:** el nombre no está
  elegido ni comprado; es una compra y cambios en paneles que solo hace el dueño. Conviene
  antes de sumar usuarios, porque push, app instalada y token de lugares quedan atados al
  dominio `workers.dev`.
- CHANGELOG: las entradas de #792 (SINCA respaldo), #793 (sotavento), #796 (cicatrices
  históricas) y #797 (NDVI) quedaron añadidas en #808; no se duplican.

**Externos (no dependen del repo):**
- Licencia MMA/SINCA: consulta por Transparencia enviada; al responder se anota en `docs/FUENTES.md`. Mientras tanto el host `sinca.mma.gob.cl` no responde desde la red de Cloudflare (probable geocerca); el proxy/snapshot de #792 deja lista la vía cuando exista un canal alcanzable.
- Comunas prioritarias CONAF 2026-27 (`web/data/prioritarias.json`): sigue vacía a la espera del documento oficial.
- SENAPRED, CONAF y MINVU: **decididos el 3-11-2026** (acceso anónimo con cita / uso público confirmado) — no volver a consultar.

## Discrepancias resueltas en este cierre

- `README.md`: ya no dice «Fases 2 y 3 pendientes»; distingue fases del roadmap de las tandas entregadas.
- `docs/PLAN_NEXT_LEVEL.md`: 2.3 marcado ✅ (combinación de las 3 capas + ranking en `main`); 3.1 y 3.2 con el detalle actualizado; fecha de sincronización al 8-11-2026.
- `docs/backlog/README.md`: sigue en 0 encargos abiertos y ahora enlaza este informe para la ola del 4-8 de noviembre, que llegó sin archivo de encargo.
- El cruce de aluvión usa huellas de los últimos 180 días, no las cicatrices históricas del catálogo; se corrigió esa ambigüedad de Devin Review. El viento animado ya estaba en #700 y se retiró de los pendientes.
