# Evidencia de producción — cierre 2026-11-10 (OPS-813, OPS-817, OPS-818)

Ventana de sondeo: **2026-11-11 entre 00:48 y 00:59 UTC**, contra
`https://brasa-chile.ddiegosebastianbb.workers.dev`. Todo GET, sin escrituras,
sin invalidar cachés y sin reiniciar el contenedor. El navegador corrió con
service workers bloqueados y abortando todo método que no fuera GET.

## Versión evidenciada

- **Desplegado:** `brasa-ef43283e` — `const VERSION = 'brasa-ef43283e'` en
  `/web/sw.js` (ver `root-observacion.json`). Correlaciona con el workflow
  «Desplegar en Cloudflare» run **42931538405** (head `ef43283e`, success
  00:30:27 UTC, merge de #809). #810 (ruff dev) y #821/#822 (docs) no gatillan
  deploy.
- **Fuente:** `main` en `a8a2cf47` al momento del sondeo; el clon remoto que
  generó `operacion-parcial.json` registraba `f650cdd7`.
- **Health:** `/api/health` 200 `{"status":"ok","version":"0.9.0"}` (00:49:23
  UTC, sonda con User-Agent oficial). Ojo: un cliente genérico recibió 403 en
  `/api/health`, `/web/sw.js` y `/api/status` — ver `root.json`; por eso todas
  las sondas de esta carpeta usan el UA oficial
  `BRASA-Chile medir-latencia (+https://github.com/falopass/brasas)`.

## Resultados

| Comprobación | Resultado | Archivo |
| --- | --- | --- |
| `/api/health` | 200, `status ok`, v0.9.0 | `root-observacion.json` (health citado en root) |
| 15 rutas p95 ≤ 2500 ms | CI «Latencia de las páginas públicas» run **42934427468** success (00:50:22 UTC, head `a8a2cf47`) — no duplicada aquí | externo (Actions) |
| OPS-817 (snapshot R2) | `/api/status` 200 en 384 ms con `x-brasa-cache: snapshot`: el borde sirvió la copia R2 generada 00:51:02 mientras el proceso llevaba ~7 min arriba | `operacion-parcial.json` |
| OPS-818 (arranque medido por fases) | `process.startup_ms` 5141 (territory 411, restore_work 4595, restore_db 535; restore_work = download 1843 + gunzip 326 + check_copy 2426), `work_db_bytes` 38 641 664 | `root-observacion.json`, `operacion-parcial.json` |
| Respaldo observable | `backup.work_bytes` 5 666 997, `work_updated_at` 00:41:30, `last_cycle.backup` y `work_backup` true | `root-observacion.json` |
| Salud de fuentes | `freshness.stale=false` en CONAF, Open-Meteo, GOES y FIRMS; `failed_sources=[]`; **0 fallos en 24 h** en los 10 productos; `senapred_alertas` 412 | `root-observacion.json`, `operacion-parcial.json` |
| Render móvil 390×844 | HTTP 200, `scrollWidth = innerWidth` (sin desborde), 0 errores de página, contenido real (161 puntos de calor, nav inferior completa) | `movil.png`, `navegador.json` |
| Render escritorio 1366×768 | HTTP 200, `scrollWidth = innerWidth`, 0 errores de página, mapa con clusters y leyenda | `escritorio.png`, `navegador.json` |

## Incidencias honestas

- **Desfase VIIRS_NOAA21_NRT:** sin foco nuevo hace **6,2 h** (`stale: true`,
  `desfase.estado: atrasada`). Puede ser que la fuente no vea focos o que su
  ingesta esté atrasada — no se afirma causalidad ni caída; el propio estado
  sugiere revisar el cupo FIRMS. `GOES19_FDCF` 3,5 h y `VIIRS_NOAA20_NRT` 5,3 h
  sin marca de stale.
- **POST `/api/subscribers` bloqueados:** 2 por vista; la app intentó la
  suscripción push y el arnés la abortó antes de salir (`ERR_BLOCKED_BY_CLIENT`
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
- La latencia publicada es **en caliente** (warmup por ruta, igual que el CI):
  no prueba cold start ni el primer miss; la poda/prune no es verificable sin
  acceso a la base (no expuesta, por diseño).
- Ningún archivo contiene PII, tokens ni secretos: solo datos públicos de
  operación y de la página.
