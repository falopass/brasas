# Cierre técnico — 24 de noviembre de 2026

Evidencia del cierre de la ola de noviembre 2026. Continúa [`cierre-brasa-2026-11-17.md`](cierre-brasa-2026-11-17.md).
Base: `main` en `8d081b7` ([#985](https://github.com/falopass/brasas/pull/985)). Este documento no da por terminado nada que no tenga prueba en el CI de GitHub o en sondas GET contra producción. En local no corrieron pruebas, builds, servidores ni navegadores (`AGENTS.md`).

## 1. Perímetros históricos reales de CONAF (`MAPA-182`) — fusionado y en producción

- **PR:** [#983](https://github.com/falopass/brasas/pull/983) (`513f001`), desplegado en Cloudflare en la corrida [45306208798](https://github.com/falopass/brasas/actions/runs/45306208798).
- **Qué cambió:** `web/data/scars.json` pasó de 11 elipses sintéticas a **9 perímetros reales simplificados de CONAF (IDE Minagri `if_magnitud_*`, 2014–2024)** más **2 aproximaciones declaradas** donde IDE Minagri no publica polígono oficial (`approximate: true`, con trazabilidad de fuente y año por polígono).
- **Verificación:** revisiones especializadas `geo-reviewer` y `ux-reviewer` aprobadas, CI completo en verde y `GET /web/data/scars.json` verificado `200 OK` en producción. `docs/backlog/MAPA-182.md` movido a `docs/backlog/hecho/MAPA-182.md`.

## 2. Capa conmutable de infraestructura crítica (`MAPA-181`) — fusionado y en producción

- **PR:** [#984](https://github.com/falopass/brasas/pull/984) (`c3e0726`), CI 5/5 en verde ([45309802970](https://github.com/falopass/brasas/actions/runs/45309802970) y [45311256676](https://github.com/falopass/brasas/actions/runs/45311256676)) y desplegado en Cloudflare en la corrida [45311256658](https://github.com/falopass/brasas/actions/runs/45311256658).
- **Qué cambió:** nueva capa opcional «Infraestructura crítica» en «Capas → Contexto» (apagada por defecto, visible desde `zoom >= 10`) alimentada por el archivo estático versionado `web/data/infraestructura/chile.json` (generado por `scripts/local/build_infraestructura.py`, sin llamadas externas en tiempo real). Reúne **871** cuarteles de bomberos, **2.425** establecimientos vigentes de salud pública (DEIS · MINSAL en `datos.gob.cl`, CC0 1.0), **10.943** escuelas, **971** subestaciones y **2.009** líneas eléctricas de alta tensión (`>= 110 kV`, OpenStreetMap vía Geofabrik Chile, ODbL).
- **Revisiones y controles:** `brasa-geo-reviewer`, `brasa-ux-reviewer` y `brasa-sec-reviewer` aprobados con 0 hallazgos; paleta Okabe-Ito validada contra daltonismo (`validate_palette.mjs`), leyenda y popups en lenguaje dual y nota orientativa explícita (no reemplaza rutas ni albergues oficiales). `docs/backlog/MAPA-181.md` movido a `docs/backlog/hecho/MAPA-181.md`.
- **Verificación en producción (`2026-11-24T02:30Z`):** `GET /web/data/infraestructura/chile.json` `200 OK` con los 5 conteos íntegros; `/web/sw.js` publicó `brasa-c3e07262`.

## 3. Respuestas oficiales de MMA/SINCA, MINVU y SENAPRED — fusionado y en producción

- **PR:** [#985](https://github.com/falopass/brasas/pull/985) (`8d081b7`), CI 5/5 en verde ([45312867154](https://github.com/falopass/brasas/actions/runs/45312867154)) y desplegado en Cloudflare en la corrida [45314155344](https://github.com/falopass/brasas/actions/runs/45314155344).
- **Qué quedó registrado (sin datos personales en el repositorio público):**
  - **MMA / SINCA (Carta N° 02853/2026, 23-11-2026, folio `AW002T0016097`):** confirma que no hay licencia Creative Commons ni API pública por ahora y que la republicación debe citar la autoría con el **Ministerio del Medio Ambiente de Chile**. Actualizados `backend/providers/sinca.py` (`SOURCE`), `web/js/views/zona.js`, `web/js/views/riesgo.js`, `web/data/licencias.json`, `docs/FUENTES.md`, `docs/backlog/PASOS_DUENO.md`, `docs/backlog/README.md` y `tests/js/sinca-aire.test.mjs`.
  - **MINVU (respuesta definitiva SIAC/DPH, 04-11-2026):** confirma administración del Catastro Nacional de Campamentos por el **Departamento de Asentamientos Precarios (DAP-MINVU)** y exige reconocerlo expresamente como fuente oficial. Actualizados `web/js/exposure.js`, `web/data/campamentos.json` (corrigiendo también la errata «Sentamientos» y serializado compacto para mantener `web/data/` en `3,995 MB < 4,00 MB`), `scripts/local/build_campamentos.py`, `web/data/licencias.json`, `docs/FUENTES.md`, `docs/backlog/PASOS_DUENO.md` y `tests/test_riesgo_3capas_campamentos.py`.
  - **SENAPRED (Oficio N° 2236, 10-11-2026, folio `AB004T0002166`):** confirma inexistencia de API/feed público (ni planes de corto plazo), remite a `senapred.cl/alertas` (24/7) y no recomienda web scraping. Por decisión expresa de la persona dueña (24-11-2026), se mantuvo `backend/providers/senapred.py` intacto (1 consulta compartida en caché cada 10 min al AppSync del portal, sin descargar HTML) y se documentó el oficio y la degradación al enlace directo en `web/data/licencias.json`, `docs/FUENTES.md`, `docs/backlog/PASOS_DUENO.md` y `docs/backlog/README.md`.
- **Revisiones:** `brasa-sec-reviewer` y `brasa-ux-reviewer` aprobados con 0 hallazgos.

## 4. Higiene operativa, Dependabot y workflows

- **Workflows y alertas de fuentes:** PR [#981](https://github.com/falopass/brasas/pull/981) (`2ce170b`) corrigió la sonda de ESA WorldCover (`Salud de las fuentes`) y los falsos positivos en `Enlaces vivos`. Ambas corridas en `main` terminaron en verde ([45301331566](https://github.com/falopass/brasas/actions/runs/45301331566) y [45301335543](https://github.com/falopass/brasas/actions/runs/45301335543)); issues [#898](https://github.com/falopass/brasas/issues/898) y [#980](https://github.com/falopass/brasas/issues/980) cerrados (**0 issues abiertos** al cierre).
- **Dependabot (#966–#971):** resueltos los 6 PRs: [#966](https://github.com/falopass/brasas/pull/966) (`7b662a4`), [#967](https://github.com/falopass/brasas/pull/967) (`628f3ed`), [#971](https://github.com/falopass/brasas/pull/971) (`1e64680`) y [#982](https://github.com/falopass/brasas/pull/982) (`3440d04`, consolidando `fastapi`, `numpy` y `python-multipart` con `requirements.lock` regenerado) fusionados en `main`; [#968](https://github.com/falopass/brasas/pull/968), [#969](https://github.com/falopass/brasas/pull/969) y [#970](https://github.com/falopass/brasas/pull/970) cerrados como reemplazados.
- **Cola de PRs:** **0 PRs abiertos** al cierre.

## 5. Producción al cierre (GET, `2026-11-24T02:44Z`)

- `GET /web/sw.js`: `200 OK`, `VERSION = 'brasa-8d081b75'` (commit de PR [#985](https://github.com/falopass/brasas/pull/985)).
- `GET /api/health`: `200 OK`, `status: "ok"`, `version: "0.9.0"`, `time_utc: "2026-11-24T02:44:42Z"`.
- `GET /api/status`: `200 OK`, última ingesta `2026-11-24T02:41:06Z` (hace 3,6 min), `failed_sources: []`, `backup: true` (`217.088 B`), `work_backup: true` (`7.135.771 B`), `firms_quota: 8/5000`, `senapred_alertas: 416`, `dmc_alerts: 14`, `0` fallos en 24 h en 11 de 12 productos (1 `JSONDecodeError` puntual de `FWI` a las `19:11Z` ya recuperado a las `20:12Z`).
  - **Nota operativa observada:** Open-Meteo cerró el día `2026-11-23` en `9.102/9.000` ubicaciones programadas (con `risk_error: "Sin cupo diario de Open-Meteo para el 30-30-30."` antes de medianoche de Chile; el cupo se reinicia a las `03:00Z` / `00:00 CLST`). `risk_computed_at` vigente del `2026-11-23T19:52:38Z`.
- `GET /web/data/licencias.json`: `200 OK`, `21` filas de terceros + `4` propios (incluye `MAPA-181` y las citas oficiales de SENAPRED, MMA/SINCA y DAP-MINVU).
- `GET /web/data/campamentos.json`: `200 OK`, JSON compacto con atribución exacta al Departamento de Asentamientos Precarios (DAP-MINVU).
- `GET /web/data/infraestructura/chile.json`: `200 OK` (verificado a las `02:30Z` tras `c3e0726`).
- `GET /web/data/scars.json`: `200 OK` (verificado tras `513f001`).

## 6. Estado del backlog y pendientes en manos de la persona dueña

- **Backlog cerrado en esta ola:** todos los encargos P0 y todos los P1 sin clave externa (`SEC-15`, `ALR-45`, `PERF-10`, `OFI-34`, `RISK-24`, `RISK-25`, `DET-46`, `MAPA-180`, `DET-47`, `UX-82`, `MAPA-184`, `DET-48`, `OFI-35`, `MAPA-182`, `MAPA-183`, `MAPA-181`, `RISK-26`, `MAPA-189`, `MAPA-185`, `MAPA-187`, `PROD-01` y `MAPA-191`–`MAPA-198`) están en `docs/backlog/hecho/`.
- **Quedan 13 encargos abiertos** en `docs/backlog/` (P1 con clave externa y horizontes P2/P3): `OFI-37`, `MAPA-186`, `RISK-27`, `DET-49`, `MAPA-188`, `PROD-02`, `PROD-03`, `OFI-38`, `RISK-28`, `MAPA-190`, `ATMOS-01`, `PROD-04` y `DET-50`.
- **En manos de la persona dueña** (detalle en [`docs/backlog/PASOS_DUENO.md`](backlog/PASOS_DUENO.md)):
  - Registro y corte al dominio `.cl` ([`DOMINIO_CL.md`](DOMINIO_CL.md)).
  - Autorización formal de CONAF (CSV de incendios y capas GEPRIF/IDE Minagri; Catastro de Vegetación CIREN si se retoma `MAPA-185`).
  - Claves gratuitas externas para habilitar la siguiente ola (`OFI-37` Agromet INIA, `DET-49` CDSE, `OFI-38` OpenAQ v3).
  - Evaluación de presupuesto para SMS/WhatsApp y vigilancia del cupo diario de Open-Meteo (`9.000` ubicaciones/día).
