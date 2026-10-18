# Cambios

Formato: lo que nota una persona primero; lo técnico, después. Fechas de despliegue en producción.

## Sin desplegar

**Técnico** (ola OPS: picos, límites y despliegue)
- **Caché en el borde** (OPS-03): el Worker guarda `/api/observations`, `/api/incidents`, `/api/official-fires`, `/api/risk` y `/api/status` 30-60 s en la Cache API, y sirve respuestas vencidas hasta 10 min mientras refresca en segundo plano. Un pico de visitas al mapa ya no golpea al contenedor. Cada respuesta lleva `X-Brasa-Cache` (`hit`/`stale`/`miss`) para verificarlo.
- **Límite en el borde y Turnstile** (OPS-05): `POST /api/reports` y `POST /api/subscribers` pasan por límites de solicitudes del Worker (10 y 30 por IP por minuto; 429 con `Retry-After`), antes de los límites propios del backend. El formulario de reportes pide un token Turnstile invisible y el backend lo verifica en `siteverify`; sin claves configuradas todo sigue igual (fail-open, cada reporte pasa por moderación). Diego crea las claves en Cloudflare: pasos en `docs/DESPLIEGUE_CLOUDFLARE.md`.
- **Prueba de carga** (OPS-04): `scripts/carga/mapa.js` (k6) simula 500 personas simultáneas en el mapa por 10 min, con rampa y umbral p95 < 2 s y < 1 % de errores. Cómo correrlo, en `scripts/carga/README.md`.
- **Dependencias fijas** (OPS-08): `requirements.lock` generado con `uv pip compile --generate-hashes`; el Dockerfile instala desde el lock con `--require-hashes`. Dependabot semanal para pip, npm y acciones de GitHub (`.github/dependabot.yml`).
- **Simulacro de restauración** (OPS-10): `scripts/simulacro_restauracion.py` baja `db/brasa.db` y `db/work.db.gz` de R2 y verifica integridad SQLite; workflow mensual (día 3) con los mismos secretos del despliegue.
- **Acciones de GitHub al día** (OPS-09): `checkout`, `setup-python` y `setup-node` a v7 en los cuatro workflows, antes de la migración de `ubuntu-latest` a Ubuntu 26 y del cambio forzado de Node 20 a Node 24.
- **Las copias diarias se borran a las 24 horas:** el cron del Worker barre `db/diario/` cada 10 minutos y elimina las que superen un día desde su escritura, de modo que la política de privacidad puede afirmar que los respaldos se conservan hasta 24 horas.

## 0.8.0 — 18 de octubre de 2026

**Para las personas**
- **Tus avisos, todos en un lugar:** nueva sección **Avisos** con cada alerta que te llegó: hora, lugar, distancia, si fue urgente y **por dónde salió** (notificación del teléfono o Telegram). Se puede filtrar por urgentes y pedir las anteriores.
- **El dato dice su edad:** la píldora de la cabecera muestra cuánto tiempo tienen los datos satelitales y, cuando pasan de 30 minutos, lo dice en palabras («Datos de hace 45 min»). El umbral lo decide el servidor: todas las pantallas dicen lo mismo del mismo dato.
- **El aviso abre la ficha del incendio:** el enlace de cada alerta ya no deja el mapa en un punto para buscar el foco entre todos los de la zona: cuando el aviso sabe de qué incidente habla, abre directamente su ficha con lo que se sabe de él y su estado. Si no hay incidente asociado, sigue llevando al mapa como antes, y si ese incidente luego se fusiona con otro, el enlace viejo abre la ficha vigente en vez de un error. En Telegram la etiqueta dice adónde va el enlace («Ver el incidente» o «Ver en el mapa»).

**Técnico**
- `backend/freshness.py`: una sola regla de frescura (30 minutos) y su contrato en `/api/status.freshness` (`age_seconds`, `stale_after_s`, `stale`), para que el cliente no repita la aritmética ni invente otro umbral.
- `/api/alerts` pagina con `limit` (1–200, 50 por defecto) y `before`, y devuelve `total` y `has_more`; antes cortaba en 100 sin decirlo.
- `web/js/views/alertas.js`: historial agrupado por día, filtro de urgentes y canales de entrega, con entrada en la navegación. Identidad por token de dispositivo, sin cuentas.
- `alerts.incident_url` decide el destino del enlace (`/#/incendio/<id>` o `/#/mapa?…`); `evaluate_official` resuelve el incidente vivo por `official_ref` (si varios lo comparten, gana el más reciente). Los incidentes fusionados quedan como alias en `incident_merges` y `/api/incidents/{id}` los resuelve siguiendo la cadena.
- Investigación de las próximas piezas en `docs/FEATURES_INVESTIGACION.md`: fuentes oficiales (DMC, CONAF, SENAPRED), prácticas contrastadas con enlace y lo que **no** se pudo verificar.

## 0.7.0 — 18 de octubre de 2026

**Para las personas**
- **El nivel del día:** la ficha de cada comuna combina el **30-30-30** con la **sequía acumulada (FWI)** y dice cuál de los dos manda. Si los dos coinciden en condiciones altas, el día sube un paso: son dos medidas distintas que apuntan a lo mismo. Nunca pasa de «extremo», y se siguen viendo por separado.
- **Avisos que se pueden apagar:** quien activó las notificaciones ahora tiene **Desactivar avisos** en la tarjeta de canales del teléfono.
- **Sequía acumulada (FWI):** además de la regla 30-30-30, la ficha de cada comuna muestra el **FWI**, el índice del sistema canadiense. No mira solo el día de hoy: mira cuánto llevan secándose el pasto y la hojarasca en las últimas semanas. Un día no tan caluroso después de un mes seco puede ser más peligroso que un día de 33 °C tras una semana de lluvia. Se muestran los dos índices, no uno en lugar del otro.
- **Avisos de la DMC:** si la Dirección Meteorológica de Chile emitió un aviso oficial de **viento** o de **calor extremo** que toca tu comuna, aparece en Riesgo y en la tarjeta de cada lugar guardado, con su hora de vencimiento y el enlace al aviso original. Los avisos de lluvia, nieve o tormentas no se muestran: en un día de incendio no cambian qué hacer.
- **Lluvia de la temporada:** la ficha de cada comuna dice cuánto ha llovido desde el 1 de junio frente a lo normal de los últimos 30 años. La frase no es un alivio: en la zona central, un invierno más lluvioso **sube** el riesgo del verano siguiente, porque crece más pasto y ese pasto se seca.

**Técnico**
- `backend/fwi.py`: FFMC, DMC, DC, ISI, BUI y FWI de Van Wagner (1987), con las tablas de largo del día y de estación del hemisferio sur. Prueba de referencia: 48 días del ejemplo publicado, contrastados con el paquete `cffdrs`, con tolerancia de 0,02 en cada código.
- Tabla `fwi_daily` en `work.db`; `/api/risk` y `/api/risk/{code}` publican el índice con su fuente y sus componentes. Se calcula con 60 días de archivo de Open-Meteo más el pronóstico, espaciado en lotes y con reintento cuando la API responde 429.
- El cálculo del FWI corre en su propio bucle, no dentro del ciclo del cron: pesa demasiado para los 30 s del Cron Trigger.
- `backend/providers/dmc.py`: lee el RSS oficial y el CAP 1.2 de cada aviso (dominio público). Traduce el polígono de cada zona a comunas reales (`Territory.comunas_in`) y, cuando el CAP no trae polígono, usa el nombre de la zona o de la región (`Territory.comunas_named`) en vez de adivinar. Tabla `dmc_alerts`; `/api/risk`, `/api/risk/{code}` y el resumen de cada lugar publican `dmc_alerts` con su fuente. Ingesta cada hora en su propio bucle.
- Sólo se guardan los avisos de viento y calor: el filtro es explícito (`dmc.KINDS`), no una lista negra de lo que no interesa.
- `backend/rain.py`: anomalía de lluvia de la temporada (1 de junio → hoy) contra la normal 1991-2020 **de la misma ventana de días**, para no confundir «temporada a medio terminar» con «sequía». Tablas `rain_normal` (promedio diario por comuna, calculado una sola vez) y `rain_season`; `/api/risk` y `/api/risk/{code}` publican `rain` con su fuente.
- Las normales se construyen **una vez por celda de 0,5°** (~55 km; 153 celdas en vez de 345 comunas) desde `scripts/local/build_rain_normals.py`, que es reanudable. El ciclo de lluvia avanza `RAIN_NORMALS_PER_RUN` celdas por vuelta (12 por defecto: la serie completa en unos 3 días) y después recalcula la anomalía; si el archivo responde 429 se conserva lo avanzado y la anomalía sale igual con las comunas que ya tengan normal.
- **Riesgo combinado:** `risk.combine` junta 30-30-30 y FWI con una regla explícita (el más alto manda; si los dos llegan a «alto», sube un paso; tope «extremo»). `risk_daily` guarda `level_combined`, `fwi`, `fwi_level` y `reasons`; `/api/risk` y `/api/risk/{code}` los publican.
- **El respaldo de trabajo se migra al restaurar:** `restore_work` copiaba el `work.db` de R2 y ejecutaba el esquema, que solo crea tablas que falten. Un respaldo con el esquema anterior dejaba `risk_daily` sin las columnas nuevas y `/api/risk` respondía 500 mientras `compute_risk` no podía escribir. Ahora se ejecuta también la migración de columnas.
- **Cron del worker:** el Worker llama `/api/internal/tick?wait=1`, así la petición queda abierta hasta que el ciclo termina. Antes respondía 202 y el contenedor se suspendía entre disparos, dejando a medias el riesgo, el FWI y la lluvia. El resumen de cada ciclo se guarda en la base y `/api/status` lo lee de ahí: sobrevive a la suspensión del contenedor.
- **Un 429 del archivo no deja el mapa sin nivel:** el FWI y el 30-30-30 se calculan y guardan por separado; si el archivo falla, se registra y el 30-30-30 se publica igual.
- **Tope de consultas satelitales:** `EXPLORE_DAILY_LIMIT` (200 por IP y día) corta `/api/explore` con 422 y el código `EXPLORE_DAILY_LIMIT`, con el motivo en palabras; el resto de los cupos sigue respondiendo 429.

## 0.6.0 — 18 de octubre de 2026

**Para las personas**
- **Incidentes:** las detecciones cercanas se agrupan en un incidente con estado (señal de calor, posible incendio, visto por vecinos, confirmado por CONAF, controlado, sin calor nuevo). Los volcanes y los puntos que arden muchos días seguidos (industria) no generan avisos.
- **Ficha de incidente** (`#/incendio/<id>`): qué vio cada satélite y cuándo, y cómo fue cambiando hora a hora.
- **CONAF en BRASA:** el pronóstico oficial **Botón Rojo** en Riesgo y en los días de cada lugar, y los **incendios informados por CONAF** en el mapa. Si CONAF informa un incendio nuevo cerca de un lugar guardado, llega un aviso «CONAF informa».
- **Modo emergencia:** si un lugar está en urgente, Mi zona muestra solo lo esencial: a qué distancia está, qué dijo la autoridad, botones grandes para llamar y 4 pasos.
- **Prepárate:** 2 L de agua por persona al día; evacuar a pie si así se indica; no dejar animales amarrados; avisar por mensaje en vez de llamar; no regresar aunque ya no se vean llamas; qué hacer en un parque.
- **Historia:** seis casos (nuevos: Penco–Lirquén 2026 con GOES-19, Valparaíso 2014, Torres del Paine 2011-12). Cada cifra muestra su fuente, su fecha y cómo cambió. Valparaíso 2024 corregido: 138 fallecidos (Fiscalía).
- Textos más exactos: «urgente» ya no afirma que el viento va hacia el lugar cuando la causa es la cercanía; las distancias menores a 3 km se muestran con un decimal.

**Técnico**
- `backend/incidents.py`; tablas `incidents`, `incident_observations`, `boton_rojo` y `official_fires` en `work.db`.
- `work.db` comprimida en R2 cada hora (`db/work.db.gz`) y restaurada al arrancar.
- `backend/providers/conaf.py`; API `/api/incidents`, `/api/incidents/{id}` y `/api/official-fires`; `boton_rojo` en `/api/risk`; `incident_id` en `/api/observations`.
- Exploración de fuentes oficiales desde GitHub Actions (`explorar-fuentes.yml`); hallazgos en `docs/FUENTES.md`.
- Entorno local: `dev.py` (setup, run, seed, test, check, e2e, clean), datos de demostración, revisión en navegador, configuración de VS Code, `docs/DESARROLLO_LOCAL.md`, `CONTRIBUTING.md` y `CLAUDE.md`.

## 0.5.x — octubre de 2026

- Modo vecino (`#/v/<token>`) con aviso anticipado cuando vive una persona mayor en el lugar.
- Identidad «Isoterma», lectura sencilla o detallada y letra grande.
- Ciclo del cron en segundo plano, respaldo en R2 por una ruta protegida del Worker, CSP y HSTS.
