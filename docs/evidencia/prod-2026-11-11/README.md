# Evidencia de producción, 2026-11-11

Ventana de sondeo: **2026-11-11 entre 01:59 y 02:01 UTC**, contra
`https://brasa-chile.ddiegosebastianbb.workers.dev`. Todo GET, sin escrituras,
sin `/api/climate/lluvia`, sin invalidar cachés y sin reiniciar el contenedor.
El navegador corrió con service workers bloqueados y abortó todo método que no
fuera GET.

## Versión evidenciada

El pedido era el main `df3c6a82` (después de #828 y #829). Al medir, ese commit
ya no era la punta: encima estaban #831 (`2b69710b`, aviso de aluvión) y #830
(`9520c4b7`, sequedad por comuna).

- **Service worker durante toda la sonda:** `brasa-9520c4b7`.
- **Deploy:** [42942368014](https://github.com/falopass/brasas/actions/runs/42942368014),
  head `9520c4b7`, success a las 01:59:28 UTC. La sonda empezó a las 01:59:12 y
  el sello ya era ese commit.
- **Health:** `/api/health` 200, `status: ok`, versión `0.9.0`, a las 01:59:26
  (`health.json`) y 01:59:45 (`produccion-final.json`).
- **User-Agent:** `BRASA-Chile medir-latencia (+https://github.com/falopass/brasas)`.

## Resultados

| Comprobación | Resultado | Archivo |
| --- | --- | --- |
| `/api/health` | 200, `status ok`, v0.9.0 | `health.json`, `produccion-final.json` |
| 15 rutas p95 < 2500 ms | 45 respuestas, 0 fallos; peor p95 **156 ms** (`/api/panorama`) | `medicion.json`, `latencia.md`, `medicion-contexto.json` |
| OPS-817 (caché) | `/api/status` 200 con `x-brasa-cache: hit` a las 01:59:26 | `operacion.json` |
| OPS-818 (arranque) | Proceso nuevo a las 02:00:53, `startup_ms` 2826. Las fases territorio 299, work.db 2545 y brasa.db 280 suman 3124 porque corren en paralelo y no parten el total. Dentro de work.db: descarga 1000, gzip 210, comprobación 1335. El proceso anterior, leído a las 01:59:26, declaraba 3166 ms | `operacion.json` |
| Respaldo | `backup.work_bytes` 5 792 221, `work_updated_at` 01:43:42, `reason` null. `work_db_bytes` 39 137 280 | `operacion.json` |
| Salud de fuentes | `freshness.stale=false`. CONAF, Open-Meteo, GOES y FIRMS con `stale=false` y `fallos_seguidos=0` a las 02:01 | `operacion.json` |
| Render móvil 390×844 | HTTP 200, `scrollWidth = innerWidth`, 0 errores de página, 161 puntos de calor y nav inferior | `movil.png`, `navegador.json` |
| Render escritorio 1366×768 | HTTP 200, `scrollWidth = innerWidth`, 0 errores de página, mapa y leyenda | `escritorio.png`, `navegador.json` |
| #830 en producción | Quilpué 36 % más verde; Santiago cae a la Región Metropolitana, 15 % más verde. Imagen del 16 de octubre de 2026. Sin errores de página | `operacion.json` |

El cupo FIRMS que devolvió el estado fue 8 de 5000, marcado a las 01:53:11.
`open_meteo.calls` leyó 0 con tope diario 9000 en el proceso que arrancó a las
02:00:53: es el contador de ese proceso, no el uso acumulado del día.
`goes_gap` estaba en false. Incidencias abiertas: 45 anomalía, 2 controlado,
20 posible. `risk_computed_at` del estado: 2026-11-11T01:41:15Z.

## Iconos, manifiesto y tarjeta OG servidos ahora

Esto es lo que responde producción hoy, antes de #835 y #836:

| Ruta | HTTP | Nota |
| --- | --- | --- |
| `/manifest.webmanifest` | 200 | 1833 bytes, `application/manifest+json` |
| `/web/icons/icon.svg` | 200 | 2697 bytes, la marca que ya está en main |
| `/web/icons/og.png` | 200 | 254678 bytes |
| `/favicon.ico` | 404 | |
| `/web/icons/favicon.ico` | 404 | |
| `/web/icons/favicon.svg` | 404 | |
| `/web/icons/apple-touch-icon.png` | 404 | |
| `/web/icons/og-focos.png` | 404 | |

## Incidencias honestas

- **DMC:** 2 corridas fallidas de 24 en 24 h. La última, 01:51:08 UTC, dice
  «La DMC no respondió (ConnectTimeout, tras 3 intentos).» El resto de los
  productos de `failures_24h` tenía 0 fallos.
- **POST `/api/subscribers` abortados:** 2 por vista. El arnés cortó la
  identidad del dispositivo antes de salir. No llegó ninguna escritura.
- **`work_backup` del ciclo leído a las 01:59:** false. El objeto `backup`
  seguía con bytes y fecha. No se afirma que el respaldo horario faltara más
  allá de ese ciclo.
- **Favicon nuevo y `og-focos.png`:** 404 porque #835 y #836 no están en main.

## Método y limitaciones

- Sonda desde `devin-vm` (Azure). No se tomó `/data/workspace/.heavy.lock`.
- Las 15 rutas son las de `scripts/local/medir_latencia.py`. El cliente fue
  Playwright, con el mismo calentamiento y el mismo p95. Las páginas estáticas
  no se precalientan.
- La latencia es en caliente. No mide el primer miss ni el arranque en frío.
  El arranque queda aparte, en `operacion.json`.
- Ningún archivo contiene PII, tokens ni secretos.
