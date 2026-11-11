# Evidencia de producción — cierre 2026-11-10 (OPS-813, OPS-817, OPS-818)

Ventana de sondeo: **2026-11-11 entre 00:48 y 01:06 UTC** (10-11 en Chile), contra
`https://brasa-chile.ddiegosebastianbb.workers.dev`. Todo GET, sin escrituras,
sin invalidar cachés y sin reiniciar el contenedor. El navegador corrió con
service workers bloqueados y abortando todo método que no fuera GET.

## Versión evidenciada

- **Primera revisión observada:** `brasa-ef43283e` — `const VERSION = 'brasa-ef43283e'` en
  `/web/sw.js` (ver `root-observacion.json`). Correlaciona con el workflow
  «Desplegar en Cloudflare» run **42931538405** (head `ef43283e`, success
  00:30:27 UTC, merge de #809). #810 (ruff dev) y #821/#822 (docs) no gatillan
  deploy. Las capturas de las 00:56 UTC corresponden a esta revisión.
- **Revisión final:** otra sesión fusionó #823 (descartes por fuente, QA-3.2) en
  `f6b0b2dd`, desplegado por el run [42935574492](https://github.com/falopass/brasas/actions/runs/42935574492)
  terminado a las 01:01:27 UTC. `produccion-final.json` acredita el SW
  `brasa-f6b0b2dd`, health 200 y estado vivo a las 01:06:15 UTC.
- **Fuente:** `main` en `a8a2cf47` al momento del sondeo; el clon remoto que
  generó `operacion-parcial.json` registraba `f650cdd7`.
- **Health:** `/api/health` 200 `status: ok`, versión `0.9.0`, a las 01:03:57 UTC
  (`health.json`) y 01:06:15 (`produccion-final.json`). El 200 anterior de las
  00:49:23 UTC quedó en la salida de la herramienta, no en `root-observacion.json`.
  Un cliente genérico recibió 403 en
  `/api/health`, `/web/sw.js` y `/api/status` — ver `root.json`; por eso todas
  las sondas posteriores usan el UA oficial
  `BRASA-Chile medir-latencia (+https://github.com/falopass/brasas)`.

## Resultados

| Comprobación | Resultado | Archivo |
| --- | --- | --- |
| `/api/health` | 200, `status ok`, v0.9.0; 221 ms en el GET final | `health.json`, `produccion-final.json` |
| 15 rutas p95 < 2500 ms | 45 respuestas, 0 fallos; peor p95 **334,92 ms** (`/web/datos.html`), 01:03:24–01:03:33 UTC | `medicion.json`, `latencia.md`, `medicion-contexto.json` |
| Sonda CI independiente | run [42934427468](https://github.com/falopass/brasas/actions/runs/42934427468) verde sobre `a8a2cf47`, anterior a #823 | Actions |
| OPS-817 (snapshot R2) | `/api/status` 200 en 384 ms con `x-brasa-cache: snapshot`; cuerpo generado 00:51:02, leído 00:56:01. La medición de las 01:03 también registra `snapshot,hit,hit` | `operacion-parcial.json`, `medicion.json` |
| OPS-818 (arranque medido por fases) | `process.startup_ms` 5141 (territory 411, restore_work 4595, restore_db 535; restore_work = download 1843 + gunzip 326 + check_copy 2426), `work_db_bytes` 38 641 664 | `root-observacion.json`, `operacion-parcial.json` |
| Respaldo observable | `backup.work_bytes` 5 666 997, `work_updated_at` 00:41:30, `last_cycle.backup` y `work_backup` true | `root-observacion.json` |
| Salud de fuentes | `freshness.stale=false` en CONAF, Open-Meteo, GOES y FIRMS; `failed_sources=[]`; **0 fallos en 24 h** en los 10 productos; `senapred_alertas` 412 | `root-observacion.json`, `operacion-parcial.json` |
| Render móvil 390×844 | HTTP 200, `scrollWidth = innerWidth` (sin desborde), 0 errores de página, contenido real (161 puntos de calor, nav inferior completa) | `movil.png`, `navegador.json` |
| Render escritorio 1366×768 | HTTP 200, `scrollWidth = innerWidth`, 0 errores de página, mapa y leyenda | `escritorio.png`, `navegador.json` |

El proceso nuevo de `f6b0b2dd` declara **3602 ms** de arranque: territorio 425,
work.db 2963, brasa.db 628; dentro de work.db: descarga 834, gzip 505 y comprobación/
copia 1624 ms. Hay fases en paralelo: no se suman al total. El estado final sigue con
`backup.reason: null`, respaldo de personas vigente y cero corridas fallidas en 24 h.
`last_cycle.work_backup: false` indica que ese ciclo no hizo el respaldo horario;
su última marca de las 00:41:30 y sus 5 666 997 bytes se conservan.

## Incidencias honestas

- **Desfase VIIRS_NOAA21_NRT:** sin foco nuevo hace **6,2 h** (`stale: true`,
  `desfase.estado: atrasada`). Puede ser que la fuente no vea focos o que su
  ingesta esté atrasada — no se afirma causalidad ni caída. A las 01:06 subió a 6,4 h;
  el propio estado
  sugiere revisar el cupo FIRMS. `GOES19_FDCF` 3,5 h y `VIIRS_NOAA20_NRT` 5,3 h
  sin marca de stale.
- **POST `/api/subscribers` bloqueados:** 2 por vista; la app intentó crear la
  identidad del dispositivo (no es `/api/push/subscribe`) y el arnés la abortó antes de salir (`ERR_BLOCKED_BY_CLIENT`
  en consola). Es el comportamiento buscado: cero mutaciones llegaron al
  servidor.
- **Un tile de mapa `.pbf` abortado** en escritorio (`/planet/…/8.pbf`,
  `ERR_ABORTED`, abort de navegación, no del servidor).
- **`operacion-parcial.json` está truncado** a propósito: la corrida propia se
  detuvo al no duplicar el benchmark que el CI ya dejó en verde; su única sonda
  (`/api/status` con `x-brasa-cache: snapshot`) se conserva como evidencia real.

## Método y limitaciones

- Sondas desde `devin-vm` (Azure) tras `flock` en `/data/workspace/.heavy.lock`;
  la tarea ajena `actualizar_sequedad_vegetacion.py` sostuvo el candado ~25 min
  y no se interrumpió.
- Scripts: `medir.py` y `capturas.cjs` (preparados por root), `medir_latencia.py`
  del repo; UA oficial aplicado tras comprobar el 403 del cliente genérico.
- La medición adicional del script oficial se ejecutó para entregar las muestras
  crudas pedidas en `medicion.json`, que el run de CI no conserva. `medicion-contexto.json`
  documenta su intervalo, script y correlación temporal con el despliegue; no existe un
  sello de revisión por cada muestra. El script procede de `f650cdd7` y las rutas
  medidas no cambiaron en #823.
- La latencia publicada es **en caliente** (warmup por ruta, igual que el CI):
  no prueba cold start ni el primer miss; la poda/prune no es verificable sin
  acceso a la base (no expuesta, por diseño).
- Ningún archivo contiene PII, tokens ni secretos: solo datos públicos de
  operación y de la página.
