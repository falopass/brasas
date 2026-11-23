# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `repo`, `rama`, `modelo`, `riesgo`, `archivos`, `e2e`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos o proveedores cuya premisa venció o fueron descartados por licencia/costo (ver [proveedores descartados el 18-11-2026](descartados/proveedores-licencia-costo.md)).
- Estado revisado contra `main` el **18-11-2026**: **36 encargos** derivados de la revisión integral del 18-11-2026 (excluyendo los 8 defectos ya cubiertos por PRs en curso y verificando que ninguno estuviera ya en `main`). Al 19-11-2026 quedan **33 abiertos** en la raíz: [DET-46](hecho/det-46.md) pasó a `hecho/` por estar cubierto en el PR #896 (ver «Cubiertos por PRs abiertos»).
- Las decisiones y credenciales pendientes en manos de la persona dueña están en [`PASOS_DUENO.md`](PASOS_DUENO.md).
- Historial anterior: al 11-11-2026 quedaban 0 encargos abiertos (`PLAN_INTEGRACION.md`, `_estado-2026-10-23.md`).

## Cubiertos por PRs abiertos (19-11-2026)

Reconciliado contra `main` (`4268a0f`, #888) y los PRs abiertos. Ninguno de estos PRs está mergeado: todos esperan la aprobación de Sovran.

| PR | Qué cubre | Efecto en el backlog |
|---|---|---|
| [#896](https://github.com/falopass/brasas/pull/896) `fix(ingesta)` | Filtro DMC «baja», hectáreas CONAF (`_number`), sello `last_ingest_at` cuando fallan FIRMS y GOES, retiro de `LANDSAT_NRT` y alta de `VIIRS_NOAA21_SP` | [DET-46](hecho/det-46.md) cubierto completo → `hecho/`. Resto de caché polar anotado en [OPS-30](hecho/OPS-30.md). `LANDSAT_NRT` anotado en [descartados](descartados/proveedores-licencia-costo.md). |
| [#895](https://github.com/falopass/brasas/pull/895) `fix(incidentes,avisos)` | `official_ref` al fusionar, `evaluate_official` por cada incendio CONAF en radio, `prune` sin invalidar caché de más | [ALR-45](ALR-45.md) **no queda cubierto**: la parte 1 (segundo foco en `evaluate`) se intentó y se revirtió en `ae46bb8`; partes 2 y 3 siguen abiertas. |
| [#894](https://github.com/falopass/brasas/pull/894) `fix(seguridad)` | CSP en toda respuesta HTML (Worker y FastAPI) | No cubre [SEC-15](SEC-15.md) (comodines `https:`), pero comparte archivos: SEC-15 va después de #894. |

## Encargos abiertos (30 · ordenados por valor / esfuerzo)

### Seguridad, alertas, operación y rendimiento (alto valor · esfuerzo S–M)

1. [SEC-15](SEC-15.md) — Restringir `img-src` y `connect-src` de la CSP a una lista explícita de dominios (paridad `backend/security.py` y Worker).
2. ~~[ALR-45](hecho/ALR-45.md) — Segundo foco en `evaluate`, `tag` push por nivel en `sw.js` y supresión completa en `delete_me` (Ley 21.719).~~ En `hecho/`.
4. ~~[PERF-10](hecho/PERF-10.md) — Optimizar descargas y repintados en `map.js`, `mapa.js`, `incendio.js` y `zona.js`.~~ En `hecho/`.

### P0 · Proveedores e inteligencia atmosférica (máximo impacto · esfuerzo S)

5. [OFI-34](OFI-34.md) — GWIS en capas WMS (`ecmwf.ranking`, `ecmwf.fwi`, `nrt.ba` · CC BY 4.0, solo frontend).
6. [RISK-24](RISK-24.md) — Open-Meteo: más variables (`VPD`, humedad de suelo, `CAPE`, `850/700 hPa`), `models=` explícito e Índice de Haines.
7. [RISK-25](RISK-25.md) — Calidad del aire pronosticada con `CO`, `PM10`, `AOD` y polvo (`cams_global` en lotes).
8. ~~[DET-46](hecho/det-46.md) — Archivo histórico FIRMS: incorporar `VIIRS_NOAA21_SP` para casos 2024+.~~ Cubierto por #896 (en `hecho/`).

### P1 · Nuevos datos, cobertura insular/rural, capas CONAF y UX del mapa (esfuerzo S a M)

9. ~~[MAPA-180](hecho/MAPA-180.md) — NASA GIBS WMTS: GOES GeoColor cada 10 min, VIIRS color real diario y aerosol AOD.~~ En `hecho/` (PR #903).
10. ~~[DET-47](hecho/DET-47.md) — GOES-18 `ABI-L2-FDCF` y cobertura GLM para Rapa Nui.~~ En `hecho/`.
11. ~~[UX-82](hecho/UX-82.md) — Usabilidad, legibilidad, accesibilidad y móvil `320 px` en el mapa (`radio` en coropletas, perfiles rápidos, `Escape`/foco, hoja inferior en `peek`).~~ En `hecho/`.
12. [MAPA-184](MAPA-184.md) — Modo sin conexión en el mapa (cambio a mapa guardado, bordes comunales y precaché de capas estáticas en `sw.js`).
13. [DET-48](DET-48.md) — GOES-19 `ABI-L2-AODF` para espesor óptico cuantitativo del humo.
14. ~~[OFI-35](hecho/OFI-35.md) — SINCA horario real + `PM10` y `CO` para picos de humo agudo.~~ En `hecho/`.
15. [MAPA-182](MAPA-182.md) — Perímetros reales de CONAF 2014–2024 en `scars.json` / PMTiles.
16. [MAPA-183](MAPA-183.md) — Capa espacial Interfaz Urbano-Forestal (`riesgo_interfaz_tiled`) y respaldo `incendios_base` de CONAF.
17. [MAPA-181](MAPA-181.md) — Capa conmutable de infraestructura crítica en el mapa (OSM + MINSAL + MINEDUC).
18. [OFI-37](OFI-37.md) — Estaciones rurales Agromet INIA `api/v4` (requiere clave gratuita en [`PASOS_DUENO.md`](PASOS_DUENO.md)).

### P2 · Combustible, terreno 3D, viento fino, basemap propio y funciones de producto (esfuerzo M)

19. ~~[RISK-26](hecho/RISK-26.md) — FWI diario incremental (ahorro de cuota Open-Meteo) y corrección de `obs_hour` por horario de verano/invierno.~~ En `hecho/`.
20. [MAPA-189](MAPA-189.md) — Terreno 3D nativo en MapLibre sobre Mapterhorn GLO-30 y respaldo AWS Terrain Tiles (z13–15).
21. [MAPA-185](MAPA-185.md) — Capas de uso de suelo y combustible: ESA WorldCover 10 m y Catastro CONAF (IDE Minagri).
22. [MAPA-186](MAPA-186.md) — Cicatrices históricas y severidad de quema CR2 (1984–2018).
23. [RISK-27](RISK-27.md) — Respaldo de verdor con VIIRS `VNP13A1` (ORNL) y evaluación de `NDMI`/`dNBR` Sentinel-2.
24. [DET-49](DET-49.md) — Tercera familia satelital polar: Sentinel-3 SLSTR FRP nocturno SWIR 500 m vía CDSE.
25. [MAPA-187](MAPA-187.md) — Grilla de viento de 0,25° (NOAA GFS / Open-Meteo) con ráfagas, selector horario e interpolación bilineal `O(1)`.
26. [MAPA-188](MAPA-188.md) — Mapa base propio Protomaps/PMTiles en R2 vía Worker XYZ, DPA oficial completa (SUBDERE/BCN) y evaluación de VersaTiles.
27. ~~[PROD-01](hecho/PROD-01.md) — «Paquete sin señal» por comuna (límites, servicios cercanos y guía práctica).~~ En `hecho/`.
28. [PROD-02](PROD-02.md) — Aviso de «salida única» (callejones sin salida) y puntos de agua cercanos al incendio (OSM).
29. [PROD-03](PROD-03.md) — Vigías verificados (juntas de vecinos y bomberos) con prioridad en la cola de moderación.

### P3 · Horizonte de sequía, escala independiente, exposición, idiomas y vigilancia (esfuerzo M–L)

30. [OFI-38](OFI-38.md) — Respaldo de calidad del aire con OpenAQ v3 y evaluación de RedMeteo como referencia no oficial.
31. [RISK-28](RISK-28.md) — Sequía satelital (NOAA VHI, Copernicus CLMS SWI, NASA SMAP), pronóstico Ensemble y evaluación SPEI/CR2MET.
32. [MAPA-190](MAPA-190.md) — Exposición poblacional fina (Censo 2024 manzana, WorldPop, GHSL), vialidad MOP/OSM y evaluación SENAPRED GRD / CONAF cortafuegos.
33. [ATMOS-01](ATMOS-01.md) — Rutas atmosféricas independientes de Open-Meteo (ECMWF Open Data, GEFS-Aerosols, CAMS ADS/GFAS, GEOS-CF) y Sentinel Hub SWIR bajo proxy.
34. [PROD-04](PROD-04.md) — Mensajes clave de emergencia en mapudungun y rapa nui con audio pregrabado (requiere validación comunitaria).
35. [DET-50](DET-50.md) — Vigilancia y evaluación de fuentes futuras: INPE Queimadas y FireSat.
36. ~~[MAPA-191](hecho/MAPA-191.md) — Área quemada Copernicus EMSR859 en el caso Penco–Lirquén (producto GRA v2 del 25-ene-2026; no es un frente en vivo).~~ En `hecho/` (PR #909).
37. ~~[MAPA-192](hecho/MAPA-192.md) — Medición de depuración del mapa apagada por defecto (`?debug=1` / `localStorage` «brasa:debug-mapa»).~~ En `hecho/`.
38. ~~[MAPA-193](hecho/MAPA-193.md) — Latido del mapa a ~10 fps en pantallas táctiles (~30 fps con ratón) para bajar el TBT medible en gama media.~~ En `hecho/`.
39. ~~[MAPA-194](hecho/MAPA-194.md) — Lienzo del mapa a pixelRatio 2 en pantallas táctiles para bajar el render residual de MapLibre en gama media.~~ En `hecho/`.
40. ~~[MAPA-195](hecho/MAPA-195.md) — Los tintes de suelo del basemap (landcover/landuse) no se evalúan a escala país (zoom<6) para bajar el repintado del arranque.~~ En `hecho/`.
41. ~~[MAPA-196](hecho/MAPA-196.md) — El globo 3D no sigue pintando cuando está oculto (pausa del bucle de render).~~ En `hecho/` (PR #936).
42. ~~[MAPA-197](hecho/MAPA-197.md) — El globo 3D pinta bajo demanda: quieto no gasta hilo ni batería.~~ En `hecho/`.
43. ~~[MAPA-198](hecho/MAPA-198.md) — El latido de los focos duerme a los 10 s tras el último dato o toque (antes 20 s) para bajar la ráfaga de hilo del sondeo en gama media.~~ En `hecho/`.

---

Al 11-11-2026 no queda ningún encargo abierto: los dos últimos con archivo en la raíz, [ICON-E-01](hecho/ICON-E-01.md) (iconos y OG, PRs #836 y #835) y la [cadencia del verdor satelital](hecho/RISK-11-cadencia.md) (PRs #852 y #857), pasaron a `hecho/` en el barrido de ese día, y [AGUA-04](hecho/agua-04.md) (aviso de aluvión por lugar guardado) quedó registrado con sus PRs #838, #831, #840 y #851.

La ola del 10 y 11 de noviembre cerró, además de los tres anteriores: las cicatrices anuales del cruce de aluvión (AGUA-01, #824), la sequedad por las 288 comunas medibles (RISK-11, #830), la suite e2e de los flujos principales (QA-E2E, #850), los descartes por fuente en Calidad (QA-3.2, #823), la ronda móvil (MOV-01 a MOV-05, VIS-01, VIS-02, MZ-09 y arreglos táctiles e imprimibles) y documentos de operación (checklist del dominio `.cl` en `docs/DOMINIO_CL.md`, #821 y #854, y evidencia de producción, #825, #827 y #837).

Al 3-11-2026 había 0 encargos abiertos: la Fase 5 completa (MAPA-157 a 167, MZ-06 a 10, UX-80 y UX-81) y ALR-44 ya estaban en `hecho/` tras las olas del 25 al 30 de octubre. Los pendientes externos de ese cierre están en `PASOS_DUENO.md`.

La ola del 4 al 8 de noviembre llegó sin archivo de encargo: cicatrices históricas, infraestructura a sotavento, sequedad por satélite (NDVI), Landsat en FIRMS, respaldo SINCA, tres capas de riesgo con campamentos, SNASPE, terreno post-incendio, latencias y concordancia en Calidad, tres casos por macrozona y arreglos del mapa. Las tandas recuperadas, los PR #803 y #807 fusionados y el seguimiento de los issues #798/#802 quedan en [`../cierre-brasa-2026-11-08.md`](../cierre-brasa-2026-11-08.md).

Antes de la Fase 4 quedaban 0 encargos abiertos. El 24-10 Diego aprobó integrar las tres fuentes de gobierno pendientes (OFI-04 SENAPRED, OFI-10 SINCA, OFI-25 MINVU) con atribución y enlace; quedan en `hecho/`. Al 3-11: SENAPRED quedó decidido (acceso anónimo del portal; Transparencia solo si lo restringe), MINVU confirmó uso público y CONAF se usa con cita — no volver a consultar. Lo único que sigue dependiendo de fuera: la respuesta de licencia del MMA/SINCA por Transparencia y el host `sinca.mma.gob.cl`, que no responde desde Cloudflare (#792 dejó proxy + snapshot). Al llegar, se anota en `docs/FUENTES.md`. Ver [`PASOS_DUENO.md`](PASOS_DUENO.md).
