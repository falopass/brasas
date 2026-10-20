# BRASA Chile — Backlog maestro

**Versión del producto:** 0.9.0 en producción (verificado el 19-oct-2026: `/api/status` publica `freshness` y `/api/me/export` responde) · la ola OPS en `main`, sin desplegar · **Fecha:** 20 de octubre de 2026 · **Rama:** `main`

**Estados sincronizados con `main` el 20 de octubre de 2026** (✅ mergeado, 🟨 con PR abierto; verificado contra `origin/main` 311efb6 y `gh pr list` hasta el PR #338).

> Hay más de una sesión trabajando sobre el repositorio. Antes de tomar un ítem: `git pull --rebase origin main` y revisa `CHANGELOG.md`, por si ya se hizo.

Este documento reúne todo lo que falta, lo que conviene arreglar, lo que hay que investigar y las ideas para BRASA Chile, con lo necesario para avanzar sin depender de nadie. Complementa a [`PLAN_NEXT_LEVEL.md`](PLAN_NEXT_LEVEL.md) (el plan aprobado y su avance), [`DESARROLLO_LOCAL.md`](DESARROLLO_LOCAL.md) (cómo trabajar) y [`FUENTES.md`](FUENTES.md) (fuentes y licencias).

---

## Índice

0. [Cómo usar este documento](#0-cómo-usar-este-documento)
1. [Fechas que no se mueven](#1-fechas-que-no-se-mueven)
2. [Estado actual en una página](#2-estado-actual-en-una-página)
3. [Arreglos verificados en el código (FIX)](#3-arreglos-verificados-en-el-código-fix)
4. [Detección y datos satelitales (DET)](#4-detección-y-datos-satelitales-det)
5. [Fuentes oficiales e integraciones (OFI)](#5-fuentes-oficiales-e-integraciones-ofi)
6. [Riesgo explicado (RISK)](#6-riesgo-explicado-risk)
7. [Avisos y canales (ALR)](#7-avisos-y-canales-alr)
8. [Experiencia, accesibilidad e inclusión (UX)](#8-experiencia-accesibilidad-e-inclusión-ux)
9. [Multiamenaza: aluviones, calor y humo (AGUA)](#9-multiamenaza-aluviones-calor-y-humo-agua)
10. [Plataforma, infraestructura y operación (OPS)](#10-plataforma-infraestructura-y-operación-ops)
11. [Seguridad, privacidad y cumplimiento legal (SEC)](#11-seguridad-privacidad-y-cumplimiento-legal-sec)
12. [Calidad, pruebas y validación científica (QA)](#12-calidad-pruebas-y-validación-científica-qa)
13. [Contenido: Historia y Prepárate (CONT)](#13-contenido-historia-y-prepárate-cont)
14. [Alianzas, comunidad e institucionalidad (ALI)](#14-alianzas-comunidad-e-institucionalidad-ali)
15. [Sostenibilidad y financiamiento (NEG)](#15-sostenibilidad-y-financiamiento-neg)
16. [Ideas exploratorias (IDEA)](#16-ideas-exploratorias-idea)
17. [Investigaciones necesarias (INV)](#17-investigaciones-necesarias-inv)
18. [Decisiones que solo puede tomar la persona dueña](#18-decisiones-que-solo-puede-tomar-la-persona-dueña)
19. [Riesgos del proyecto y cómo mitigarlos](#19-riesgos-del-proyecto-y-cómo-mitigarlos)
20. [Ruta sugerida semana a semana](#20-ruta-sugerida-semana-a-semana)
21. [Fuentes consultadas para este documento](#21-fuentes-consultadas-para-este-documento)
22. [Cómo mantener este archivo](#22-cómo-mantener-este-archivo)

---

## 0. Cómo usar este documento

**Identificadores.** Cada ítem tiene un código (`FIX-03`, `RISK-01`…). Úsalo en ramas, commits y *issues*: `git switch -c fix-03-goes-barridos`, «Procesa todos los barridos GOES pendientes (FIX-03)».

**Prioridad**

| Código | Significado |
|---|---|
| **P0** | Antes del **1 de diciembre de 2026**: la ley de datos personales entra en vigencia y empieza la temporada alta. |
| **P1** | Antes o durante la **temporada alta** (diciembre a febrero). |
| **P2** | Durante el verano, si hay tiempo, o justo después. |
| **P3** | Después de marzo de 2027, o cuando exista la alianza o el dato necesario. |

**Tamaño:** **S** = medio día o menos · **M** = 1 a 3 días · **L** = 1 a 2 semanas · **XL** = más de 2 semanas.

**Estado:** ⬜ pendiente · 🟨 en curso · ✅ listo · ⏸ bloqueado (anota por qué). Actualiza la columna o el título al avanzar.

**Definición de «listo» (para cualquier ítem)**
1. `python dev.py check` termina en «Todo en orden».
2. Si toca la interfaz: `python dev.py run --demo` y `python dev.py e2e` sin problemas.
3. Pruebas nuevas para cada regla nueva (umbral, estado, fuente).
4. Si cambia algo visible: una línea en `CHANGELOG.md`. Si agrega una fuente: su acceso y licencia en `docs/FUENTES.md`.
5. Si es parte del plan: su fila en `PLAN_NEXT_LEVEL.md` actualizada.
6. Si se despliega: workflow **Diagnóstico de Cloudflare** revisado (`backup: true`, sin `failed_sources`).

**Trabajar con un agente (Claude Code).** `CLAUDE.md` le da el contexto. Una instrucción que funciona bien: *«Lee docs/BACKLOG_MAESTRO.md, toma el siguiente ítem P0 pendiente, impleméntalo con pruebas, corre dev.py check y márcalo como listo»*. Revisa siempre el diff antes de desplegar.

**Regla de oro (no se negocia):** nunca inventar datos, siempre mostrar la fuente, un punto de calor no es un incendio y «confirmado» solo con CONAF.

---

## 1. Fechas que no se mueven

| Fecha | Qué pasa | Qué implica para BRASA | Ítems |
|---|---|---|---|
| **19-oct-2026** | En GitHub Actions, `ubuntu-latest` empieza a migrar a Ubuntu 26. Además, las acciones basadas en Node 20 ya corren forzadas en Node 24. | Revisar que los 4 workflows sigan pasando; actualizar versiones de acciones. | OPS-09 |
| **2-nov-2026** | NOAA deja de entregar datos de VIIRS en **Suomi NPP**. | Ya no se ingiere en vivo. El archivo científico `VIIRS_SNPP_SP` de los casos históricos debería seguir disponible: verificarlo. | INV-14 |
| **1-dic-2026** | Entra en vigencia la **Ley 21.719** de protección de datos personales. Hay un proyecto para postergarla al 1-dic-2027 (boletín 18.623-07) que, a octubre de 2026, seguía en primer trámite. | Política de privacidad, borrado total, retención, consentimiento para el dato «persona mayor». Asumir la fecha de 2026. | SEC-01 a SEC-07 |
| **Dic-2026 a feb-2027** | Temporada alta de incendios. La investigación apunta a un riesgo elevado entre Valparaíso y Los Lagos (lluvia de invierno → más pasto seco). | Congelar cambios riesgosos desde el 15 de diciembre; prioridad a la estabilidad, el monitoreo y la calibración de avisos. | OPS-01, ALR-09 |
| **Feb-2027** | NASA deja de recolectar datos científicos de **MODIS en Terra**. | Los casos 2011 y 2014 usan `MODIS_SP` (archivo: no se pierde). En vivo no se usa MODIS. | INV-14 |
| **Mar a may-2027** | Otoño: primeras lluvias intensas sobre suelos quemados. | Fase 3: riesgo de aluvión. | AGUA-01 a AGUA-06 |
| **May-2027 (estimado)** | **SERNAFOR** (Ley 21.744, sucesor legal de CONAF) empezaría a operar. | Las URL, cuentas de ArcGIS y GitHub de CONAF podrían cambiar de dueño o de nombre. Tener alertas de formato y un plan de reemplazo. | OFI-12 |
| **Sep-2027** | NASA deja de recolectar datos de **MODIS en Aqua**. | Igual que Terra. | INV-14 |

---

## 2. Estado actual en una página

**Lo que funciona en producción (v0.9.0)**
- Ingesta cada 10 min: GOES-19 (FDCF, sin clave), VIIRS NOAA-20/21 (FIRMS), incendios informados por CONAF (CSV de GEPRIF) y, cada 3 h, el riesgo 30-30-30 de Open-Meteo y el Botón Rojo de CONAF.
- Incidentes: agrupación, estados (señal → posible → visto por vecinos → confirmado/controlado por CONAF → sin calor nuevo) y fuentes fijas (3 volcanes y una regla de persistencia).
- Avisos por lugar (Web Push; Telegram listo pero sin bot creado), modo emergencia, modo vecino o familia (`#/v/<token>`), persona mayor con aviso anticipado.
- Mapa, Riesgo (30-30-30 y Botón Rojo), Historia (6 casos con cifras con fuente), Prepárate y reportes ciudadanos con moderación.
- Cloudflare: Worker, Container y R2. Respaldo de `brasa.db` tras cada cambio y de `work.db` cada hora.
- Revisión de diseño, revisión en navegador (`dev.py e2e`) y CSP estricta.

**Lo que se sumó en 0.7.0 a 0.9.0 (ya desplegado) y lo que queda en `main` sin desplegar (la ola OPS)**
- **FWI propio** (Van Wagner, tablas del hemisferio sur, prueba contra `cffdrs`), combinado con el 30-30-30: manda el más alto y, si ambos llegan a alto, sube un paso.
- **Avisos DMC** de viento y calor extremo por comuna (CAP 1.2), en Riesgo y en cada lugar.
- **Lluvia de la temporada** frente a la normal 1991-2020 por comuna. Las normales se completan solas, por tandas, para no agotar el cupo de Open-Meteo.
- Tope diario por IP para la exploración del archivo FIRMS; opción para desactivar las notificaciones push desde la aplicación.
- **0.8.0:** historial de avisos (`#/alertas`), edad del dato en la cabecera (`freshness` en `/api/status`) y los avisos enlazan a la ficha del incidente.
- **0.9.0:** política de privacidad (`#/privacidad`), exportar y borrar los datos del dispositivo, retención con plazos, términos de uso y EIPD.
- **Ola OPS:** caché en el borde (OPS-03), límites y Turnstile (OPS-05), prueba de carga (OPS-04), dependencias fijas (OPS-08), acciones al día (OPS-09), simulacro de restauración (OPS-10) y monitoreo con *issue* automático (OPS-01). Detalles en `CHANGELOG.md`, «Sin desplegar».

**Lo que no existe todavía (resumen)**
- Riesgo en 3 capas y viento animado (resto de la Fase 2; la capa de lluvia ya está en `main`, PR #142, y el panel El Niño también, PR #132).
- Aluviones (Fase 3). La página «Calidad de los datos» ya existe (`#/calidad`, PR #112). La API pública de solo lectura ya existe (`backend/routes/opendata.py`) y está documentada en `docs/API.md`, con `tests/test_api_doc.py` como contrato (PRs #99 y #123).
- Licencia del repositorio: ya elegida — AGPL-3.0 para el código y CC BY 4.0 para los datos propios (SEC-14, PR #143; `LICENSE` en `main`).
- Validación científica contra CONAF (QA-03): el script `scripts/validar_deteccion.py` ya está en `main`, extendido sobre `work.db` (PRs #74 y #139); la medida de adelanto ya está publicada en `#/calidad` (PR #290); el banco de reproducción QA-02 ya está (PR #53).

---

## 3. Arreglos verificados en el código (FIX)

Todos se comprobaron leyendo el código el 18-oct-2026. Están ordenados por impacto.

### FIX-01 · FIRMS pierde detecciones al cambiar el día UTC — ✅ P0 · S
- **Hecho:** `days=2` en `backend/services.py:252` (PR #11).
- **Dónde:** `backend/services.py`, `ingest_firms` → `firms.fetch_hotspots(..., days=1)`.
- **Problema:** con `days=1`, FIRMS devuelve solo las detecciones con fecha de adquisición del **día UTC actual**. Una pasada que se adquiere a las 22:30 UTC y se publica a la 01:30 UTC del día siguiente (latencia NRT de 1 a 3 h) ya no aparece en ninguna consulta. Producción mostró `n_records: 0` a las 02:11 UTC.
- **Solución:** usar `days=2`. `INSERT OR IGNORE` ya deduplica por `id`. Opcional: `days=2` solo entre las 00:00 y las 06:00 UTC para ahorrar transacciones.
- **Listo cuando:** una prueba simula una detección «de ayer» publicada «hoy» y la ingesta la guarda; en producción, después de las 00:00 UTC siguen llegando detecciones del día anterior.

### FIX-02 · GOES procesa solo el último barrido de cada ciclo — ✅ P0 · M
- **Hecho:** `_ingest_goes` cubre la ventana de 40 min (`GOES_WINDOW_MIN` en `backend/services.py:38`, con tope por ciclo), PR #11.
- **Dónde:** `backend/services.py`, `ingest_goes` usa `goes.latest_scan`.
- **Problema:** GOES-19 entrega un barrido de disco completo cada 10 min y el cron también corre cada 10 min. Si un ciclo se atrasa, falla o el contenedor se reinicia, los barridos intermedios se pierden para siempre (el relleno solo corre al arrancar).
- **Solución:** listar los barridos de los últimos 40 min (`list_keys` de la hora actual y la anterior), descartar los ya registrados en `ingest_runs` con `ok = 1` y procesarlos en orden, con un tope de 4 por ciclo para no pasar el límite de tiempo.
- **Listo cuando:** una prueba con 3 claves pendientes procesa las 3 en orden; `/api/status` muestra barridos consecutivos sin huecos durante una hora.

### FIX-03 · La regla de «fuente fija» puede silenciar un incendio real largo — ✅ P0 · M
- **Hecho:** pasos 1, 2 y 4 en `backend/incidents.py` (`FIXED_KM`, `FIXED_WEEKS`, `fixed_reason`), PR #13. El paso 3 sigue como DET-05 (PR #80 ya en `main`; falta publicar la máscara).
- **Dónde:** `backend/incidents.py`, `is_fixed_source` (≥ 8 días distintos con calor en una celda de ~2 km en los últimos 30 días).
- **Problema:** un incendio que arde o rebrota en el mismo lugar durante más de una semana (Torres del Paine 2011-12, turberas, incendios de Patagonia, rescoldos en plantaciones) puede quedar clasificado como «industria». Desde ahí no genera avisos ni pone lugares en urgente. Es el peor tipo de error: un falso negativo silencioso.
- **Solución (combinar):**
  1. Nunca marcar como fija una celda con un incendio informado por CONAF a ≤ 5 km en la ventana.
  2. Exigir que los días estén repartidos: por ejemplo, ≥ 8 días en ≥ 3 semanas distintas, o con presencia fuera de la temporada (abril a noviembre).
  3. Reemplazar la regla dinámica por una máscara precalculada con FIRMS SP 2019-2025 (DET-05) y dejar la dinámica solo como respaldo, con una lista de exclusiones.
  4. Mostrar siempre en la ficha *por qué* se marcó como fija, con un botón de moderación para revertirlo.
- **Listo cuando:** hay pruebas para «incendio de 10 días en el mismo lugar con CONAF cerca → no es fijo» y «antorcha todo el año → fija».

### FIX-04 · El enlace de los avisos lleva al mapa y no al incidente — ✅ P1 · S
- **Hecho:** `alerts.incident_url` lleva a `/#/incendio/<id>` cuando hay incidente (`backend/alerts.py:118`), PR #15.
- **Dónde:** `backend/alerts.py` (`"url": "/#/mapa?lat=…"` en `compose` y `compose_official`).
- **Solución:** si el aviso tiene `incident.id`, usar `/#/incendio/<id>`. Para los avisos de CONAF, el incidente unido si existe; si no, el mapa centrado.
- **Listo cuando:** la prueba de avisos verifica la URL y el mensaje de Telegram lleva a la ficha.

### FIX-05 · La ficha de incidente salta al inicio cada 3 minutos — ✅ P1 · S
- **Hecho:** `keepPlace` en `web/js/views/incendio.js:153`, PR #39.
- **Dónde:** `web/js/views/incendio.js`: `setInterval` → `load` → `render`, que reemplaza `innerHTML`.
- **Problema:** quien lee la lista de evidencia vuelve arriba cada 3 min, y también se pierde el foco del teclado.
- **Solución:** envolver la actualización con `keepPlace(container, …)` de `util.js` (como en `mapa.js`). Mejor aún: actualizar solo las cifras y la lista, sin reconstruir el reproductor.
- **Listo cuando:** en `e2e`, después de una actualización forzada, la posición de scroll se mantiene.

### FIX-06 · El modo vecino no muestra los incendios de CONAF — ✅ P1 · S
- **Hecho:** `officialBlock` reutilizado en `web/js/views/vecino.js:39`, PR #51.
- **Dónde:** `web/js/views/vecino.js`. `/api/shared/{token}` ya usa `build_summary`, que trae `official`.
- **Solución:** reutilizar el bloque «¿Qué dijo la autoridad?» del modo emergencia (extraerlo a una función en `zona.js`) y mostrarlo en el modo vecino cuando haya un incendio oficial dentro del radio.

### FIX-07 · El texto «urgente» habla del satélite aunque la causa sea CONAF — ✅ P1 · S
- **Hecho:** el texto «urgente» dice la causa verdadera (satélite, CONAF o persona mayor), PR #76.
- **Dónde:** `web/js/views/zona.js` (`STATUS.urgente.text`) y el héroe de `vecino.js`.
- **Problema:** cuando la urgencia viene solo de un incendio informado por CONAF, el texto dice «Un satélite vio calor…».
- **Solución:** que `build_summary` devuelva `cause` (`satelite`, `conaf`, `ambos`, `persona_mayor`) y elegir el texto según la causa.

### FIX-08 · La persona mayor dispara urgencia con cualquier quema en 10 km — ✅ P1 · M
- **Hecho:** la persona mayor ya no dispara urgencia con cualquier calor en el radio, PR #227.
- **Dónde:** `backend/alerts.py` (`classify`) y `backend/routes/personal.py` (`build_summary`).
- **Problema:** con `older_adult`, cualquier detección confiable dentro del radio es «urgente» y abre el modo emergencia. En temporada de quemas agrícolas, eso genera fatiga de avisos: la familia deja de mirarlos.
- **Solución propuesta (validar con usuarios, ver INV-09):** urgente solo si el incidente está en «posible» o más, o si está a ≤ 5 km, o con viento hacia el lugar. Las demás detecciones generan un «aviso» con el texto reforzado para la persona mayor.

### FIX-09 · Un reporte verificado no actualiza el incidente cercano — ✅ P1 · S
- **Hecho:** `incidents.refresh_near` al verificar un reporte (`backend/routes/community.py:225` y `:253`), PR #13.
- **Dónde:** `backend/incidents.py` (`_status` solo corre en `_refresh`, al llegar una detección nueva) y `backend/routes/community.py` (moderación).
- **Solución:** al marcar un reporte como `verificado`, refrescar los incidentes abiertos a ≤ 3 km (`incidents.refresh_near(db, lat, lon)`).
- **Listo cuando:** una prueba verifica un reporte y el incidente pasa a «reportado» sin detecciones nuevas.

### FIX-10 · Los incendios de CONAF no avisan si se pierde `work.db` — ✅ P2 · S
- **Hecho:** con la tabla vacía se avisa igual por los incendios de las últimas 2 h (`backend/services.py:698-701`), PR #58.
- **Dónde:** `backend/services.py`, `ingest_official_fires`: con la tabla vacía (`known` vacío) no se avisa, para evitar avisos masivos.
- **Problema:** si la restauración de `work.db` falla en un despliegue, los incendios que aparecieron en ese intervalo nunca generan aviso.
- **Solución:** con la tabla vacía, avisar igual por los incendios que empezaron hace menos de 2 h y no están extinguidos.

### FIX-11 · El Botón Rojo reintenta cada 10 minutos si la capa falla — ✅ P2 · S
- **Hecho:** `boton_rojo_try_at` con espera exponencial hasta 3 h (`backend/services.py:627` y `:725`), PR #64.
- **Dónde:** `backend/services.py`: `boton_rojo_due` mira `boton_rojo_at`, que solo se escribe si la descarga sale bien.
- **Solución:** guardar también `boton_rojo_try_at` y esperar 30 min tras un fallo (espera exponencial con un máximo de 3 h).

### FIX-12 · El CSV de CONAF se descarga entero cada ciclo — ✅ P2 · S
- **Hecho:** `If-None-Match` con el ETag guardado y manejo del 304 (`backend/providers/conaf.py:165-182`), PR #14.
- **Dónde:** `backend/providers/conaf.py`, `fetch_fires`.
- **Solución:** solicitudes condicionales (`If-None-Match` con el `ETag` guardado en `kv`). Si responde 304, no hay nada que hacer. Ahorra ancho de banda y evita límites de `raw.githubusercontent.com`.

### FIX-13 · La superficie de CONAF asume coma decimal — ✅ P2 · S
- **Hecho:** `_number` decide el formato por fila, con el aviso de `area_ha > 500.000` (`backend/providers/conaf.py:101`, `backend/services.py` registra el caso), PR #14.
- **Dónde:** `backend/providers/conaf.py`, `_number`, que borra los puntos de miles y convierte la coma.
- **Riesgo:** si CONAF pasa a publicar «1234.5», BRASA leería 12.345 ha.
- **Solución:** detectar el formato por fila (si hay un solo separador y le siguen 1 o 2 dígitos, es decimal). Agregar pruebas con «0,20», «1.234,50» y «1234.5». Alertar si `area_ha > 500.000`.

### FIX-14 · Se descartan columnas valiosas del CSV de CONAF — ✅ P1 · S
- **Hecho:** `detected_at`, `alerted_at`, `dispatched_at` y `season` se guardan en `official_fires` (`backend/providers/conaf.py:148-149`), PR #14.
- **Dónde:** `parse_fires` ignora `f_deteccion`, `f_aviso`, `f_despacho`, `f_arribo`, `f_ataque`, `temporada`, `provincia` y `sha2_ultimo_poligono`.
- **Por qué importa:** con `f_deteccion` y `f_aviso` se puede medir cuántos minutos antes (o después) que CONAF detecta BRASA un incendio. Es la métrica más fuerte para validar el proyecto ante instituciones (QA-03). `sha2_ultimo_poligono` indica que CONAF tiene perímetros: investigar si se publican (INV-03).
- **Solución:** agregar las columnas a `official_fires` (migración en `WORK_SCHEMA`) y guardarlas.

### FIX-15 · `incidents.update` escala mal en episodios grandes — ✅ P1 · M
- **Dónde:** `backend/incidents.py`: por cada detección nueva, `_candidates` y, por cada candidato, `_members` (consulta y conexión nueva) y el recorrido completo de sus detecciones.
- **Problema:** en un episodio como febrero de 2023 (cientos de incendios y miles de píxeles), el costo crece con detecciones × miembros. Puede pasar el límite de tiempo del ciclo.
- **Hecho:** agrupador escalado a episodios grandes con resultados idénticos, PR #159.
- **Solución:**
  1. Comparar solo contra los miembros de las últimas `ACTIVE_HOURS` (`WHERE observed_at >= ?`).
  2. Un índice espacial simple: cuadrícula de 0,05° en memoria durante el ciclo.
  3. Una sola conexión por ciclo (FIX-16).
  4. Medir con el banco de pruebas de QA-02 (reproducir `nuble-biobio-araucania-2023.goes.json`).
- **Listo cuando:** reproducir el caso 2023 completo tarda menos de 20 s.

### FIX-16 · Una conexión SQLite nueva (con `ATTACH`) por cada consulta — ✅ P2 · M
- **Hecho:** conexión por hilo con `threading.local` y el `ATTACH` hecho una vez (`backend/db.py:360`), PR #56.
- **Dónde:** `backend/db.py`, `Database.connect`.
- **Solución:** conexión por hilo (`threading.local`) o un pequeño grupo reutilizable con `ATTACH` hecho una vez; `executemany` en las rutas calientes. Medir antes y después.

### FIX-17 · El mapa recorta en silencio a 20.000 detecciones — ✅ P2 · S
- **Hecho:** `truncated` y aviso en el mapa, PR #102.
- **Dónde:** `backend/routes/public.py`, `/api/observations` (`LIMIT 20000`).
- **Solución:** devolver `truncated: true` y mostrar un aviso en el mapa («se muestran las 20.000 más recientes»). A mediano plazo, OPS-06.

### FIX-18 · En el celular, el modo emergencia queda a media pantalla — ✅ P1 · S
- **Hecho:** el evento `brasa:sheet` abre la hoja en `full` (`web/js/views/zona.js:216`), PR #38.
- **Dónde:** `web/js/app.js` (`setSheet` no se exporta) y `web/js/views/zona.js`.
- **Solución:** exportar `setSheet` o emitir `brasa:sheet` (ya existe ese evento en las pruebas de desborde) y abrir la hoja en `full` al entrar en modo emergencia.

### FIX-19 · `shapely.ops.transform` está obsoleto — ✅ P2 · S
- **Hecho:** `shapely.transform` con función vectorizada N×2 (`backend/cases.py:16` y `:90`), PR #48.
- **Dónde:** `backend/cases.py:165` (aviso `DeprecationWarning` en las pruebas).
- **Solución:** reemplazarlo por `shapely.transform(geom, fn)` con una función vectorizada (recibe un arreglo N×2).

### FIX-20 · El limitador de solicitudes confía en cualquier `X-Forwarded-For` — ✅ P2 · S
- **Hecho:** `FORWARDED_ALLOW_IPS` configurable en el contenedor, PR #135.
- **Dónde:** `Dockerfile` (`--forwarded-allow-ips "*"`) y `backend/routes/common.py` (`RateLimiter`, en memoria).
- **Problema:** en Cloudflare está bien (el contenedor no es público). En un VPS sin proxy (`docs/OPERACION.md`), cualquiera puede falsificar la IP y saltarse el límite.
- **Solución:** variable `TRUSTED_PROXIES` (por defecto vacía en VPS), documentada. A futuro, el límite en el borde (OPS-05).

### FIX-21 · No hay retención para los avisos ni los reportes — ✅ P0 · S
- **Dónde:** solo existe `RETENTION_DAYS = 45` para observaciones (`services.py`).
- **Solución:** borrar avisos de más de 12 meses, reportes descartados de más de 90 días con su foto y reportes verificados de más de 2 años (o anonimizar su ubicación). Documentarlo en la política de privacidad (SEC-01).
- **Hecho en 0.9.0:** `Services.purge_user_data` corre al final de cada ciclo de ingesta. Los reportes **sin verificar** (no solo descartados) también caducan a los 90 días: guardan coordenadas y foto sin publicarse. La foto remota se sobrescribe con cero bytes (R2 no admite DELETE). Plazos documentados en `#/privacidad`.

### FIX-22 · No existe el borrado total de los datos de un dispositivo — ✅ P0 · S
- **Dónde:** `backend/routes/personal.py` tiene `DELETE /api/places/{id}`, pero no `DELETE /api/me`.
- **Solución:** `DELETE /api/me` borra el suscriptor y, en cascada, sus lugares, avisos y suscripción push. Agregar el botón «Borrar todos mis datos» en Ajustes, con confirmación. Es requisito de la Ley 21.719 (SEC-02).
- **Hecho en 0.9.0:** `DELETE /api/me` borra avisos→lugares→suscriptor en una sola transacción (los borrados hijo→padre son explícitos por respaldos antiguos sin `ON DELETE CASCADE`) y marca el respaldo. Botón en Ajustes con confirmación; la pestaña se reinicia con el localStorage limpio.

### FIX-23 · El Botón Rojo usa una sigla que la mayoría no entiende — ✅ P2 · S
- **Hecho:** marca legible del Botón Rojo en las tiras de Mi zona, PR #125.
- **Dónde:** `.br-mark` («BR») en las tiras de días de `zona.js` y `riesgo.js`.
- **Solución:** un ícono reconocible (botón rojo) con el texto «CONAF» en lectura sencilla, y la sigla solo en la detallada. Confirmar en pruebas con usuarios (INV-09).

### FIX-24 · Las respuestas guardadas sin conexión no dicen su antigüedad — ✅ P2 · M
- **Hecho:** `X-Brasa-Cached-At` y la edad del dato en la píldora, PR #52.
- **Dónde:** `web/sw.js` (caché de `/api/*`) y las vistas.
- **Solución:** que el service worker agregue la cabecera `X-Brasa-Cached-At` al responder desde la caché, y que la interfaz muestre «Sin conexión · datos de hace 2 h» en vez del aviso genérico.

### FIX-25 · Las normales de lluvia 1991-2020 se recalculan si se pierde `work.db` — ✅ P2 · S
- **Hecho:** `web/data/rain_normals.json` versionado que se repone si se pierde `work.db`, PR #88.
- **Dónde:** tabla `rain_normal` en `work.db`, que se completa sola por tandas (`RAIN_NORMALS_PER_RUN`).
- **Problema:** son datos fijos (el período 1991-2020 no cambia). Si se pierde `work.db`, se vuelven a pedir 30 años de archivo por celda, compitiendo con el FWI por el cupo de Open-Meteo, y la lluvia de la temporada queda incompleta durante horas o días.
- **Solución:** exportar las normales completas a `web/data/rain_normals.json` (versionado, con su fuente y la fecha de cálculo) y cargarlas al arrancar si la tabla está vacía. El cálculo automático queda como respaldo.
- **Listo cuando:** con `work.db` vacía, la lluvia de la temporada está completa en el primer ciclo sin pedir el archivo.

---

## 4. Detección y datos satelitales (DET)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| DET-01 | **Persistencia GOES:** pedir 2 barridos seguidos para pasar a «posible» cuando solo hay GOES | Menos falsos positivos (reflejos, bordes de nube) sin perder rapidez | Ya existe «2 momentos distintos»; agregar «en ≤ 30 min» y medir con QA-02 | P1 | S | ✅ · hecho: `GOES_PAIR_MINUTES` en `backend/incidents.py:38`, PR #47 |
| DET-02 | **Corrección de paralaje por relieve** en píxeles GOES | En los Andes, la altura del terreno desplaza la posición aparente (posiblemente 1 a 3 km en Chile central: verificar) | Investigar (INV-05); si aplica, corregir con el DEM y el ángulo de visión del satélite antes de agrupar | P2 | M | ⬜ |
| DET-03 | **Rayos GLM** de GOES-19 (`GLM-L2-LCFA`, mismo bucket S3) | Las igniciones por rayo son frecuentes en el sur y la Patagonia: un rayo sobre pasto seco es una alerta temprana | Ingerir los rayos de la última hora sobre Chile; capa «rayos 24 h»; marca en el incidente si hubo un rayo a ≤ 5 km antes de la primera detección. Complemento: `backend/providers/dmc.py` ya lee los avisos de tormenta eléctrica, aunque hoy no se muestran | P2 | M | 🟨 · hecho en parte: `backend/providers/glm.py` y `/api/opendata/lightning.geojson` (PR #79); falta la capa y la marca en el incidente; PR #197 abierto (capa de rayos GLM) |
| DET-04 | **Humo GOES:** producto de aerosoles `ABI-L2-ADPF` (máscara de humo) | Mostrar hacia dónde va el humo: lo pregunta la gente y ayuda a las personas con asma | Polígonos de humo cada 10-30 min, simplificados; capa opcional | P2 | M | 🟨 · hecho en parte: conjunto abierto `/api/opendata/smoke.geojson` (PRs #87 y #123); falta la capa en el mapa; PR #225 abierto (capa de humo GOES-19) |
| DET-05 | **Máscara de fuentes fijas** con FIRMS SP 2019-2025 (`scripts/build_persistent_mask.py`) | Base para FIX-03; reemplaza la regla dinámica | Celdas de 0,01° con calor en > 15 días distintos fuera de diciembre a marzo; revisar a mano y publicar en `persistent_hotspots.json` con su fuente | P1 | M | 🟨 · script `scripts/build_persistent_mask.py` en `main` (PR #80); falta revisar a mano y publicar la máscara |
| DET-06 | **Lista curada de fuentes fijas** (con fuente por punto) | Hoy solo hay 3 volcanes | Candidatos a verificar con FIRMS SP: volcanes activos de la red de SERNAGEOMIN, refinerías, fundiciones, celulosas con calderas de biomasa y antorchas de gas en Magallanes. **No poner coordenadas sin verificar** | P1 | M | 🟨 · hecho en parte: fuentes fijas con todos los volcanes con ficha GVP (PR #325); faltan los otros candidatos |
| DET-07 | **Sentinel-3 SLSTR FRP** (Copernicus) como tercer sensor polar | Más pasadas al día sobre Chile tras el fin de MODIS | Investigar acceso NRT y latencia (INV-06); adaptador si es útil | P3 | L | ⬜ |
| DET-08 | **Falsos positivos del norte** (desierto caliente, minería, plantas solares) | GOES ve superficies muy calientes de día en Atacama | Medir la tasa por región con QA-03; umbral o máscara regional si hace falta | P2 | M | 🟨 · investigación en `docs/investigacion/INV-25-falsos-positivos-norte.md`; PR #273 abierto (candidatos a falsa alarma por región) |
| DET-09 | **Agrupación más robusta** (DBSCAN espacio-tiempo en vez de enlace simple) | El enlace simple puede encadenar incendios distintos en episodios masivos | Comparar con QA-02 usando el caso 2023; mantener la regla simple si gana | P3 | M | ✅ · hecho: comparación DBSCAN vs enlace simple sin cambiar la regla (gana la simple), PR #204 |
| DET-10 | **Contorno de evidencia por incidente** en el mapa principal (capa `incident-hulls`) | Hoy la huella solo se ve en la ficha | Endpoint con `concave_hull` o `buffer` + `union` simplificado; etiqueta con el estado | P2 | M | 🟨 · PR #272 abierto (huellas de calor por incidente como capa opcional) |
| DET-11 | **Velocidad de avance estimada** (km/h de la huella entre horas) | Dato útil para expertos; base para un futuro escenario de propagación | Calcularla en `build_timeline`; solo en lectura detallada y rotulada como estimación | P3 | S | 🟨 · PR #235 abierto (expansión en km) |
| DET-12 | **FRP acumulada** (energía radiativa, MJ) por incidente | Indicador de intensidad mejor que el FRP instantáneo | Integrar el FRP de GOES en el tiempo; documentar sus límites | P3 | S | 🟨 · PR #235 abierto (energía radiativa acumulada) |
| DET-13 | **Avisos de calidad de GOES** (barridos con errores, huecos) | Que «no vemos fuego» no se lea como «no hay fuego» | Si faltan más de 2 barridos en la última hora, aviso en el mapa | P1 | S | ✅ · hecho: `goes_gap` en `/api/status` (`backend/routes/public.py:118`) y aviso en `web/js/views/mapa.js:165`, PR #44 |
| DET-14 | **FIRMS: verificar transacciones** de la clave (límite por cada 10 min) | Con `days=2` (FIX-01) y la exploración de casos, podría acercarse al límite | Endpoint `mapserver/mapkey_status` de FIRMS en `/api/status` | P2 | S | ✅ · hecho: `firms_quota` en `/api/status` (`backend/routes/public.py:64` y `:157`), PR #161 |

---

## 5. Fuentes oficiales e integraciones (OFI)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| OFI-01 | **Avisos de la DMC (CAP 1.2)** | Calor extremo y viento fuerte oficiales por zona. El RSS se declara de dominio público | Hecho en `backend/providers/dmc.py` (0.7.0). Pendiente: verificarlo en producción (OPS-19) y sumar un aviso push cuando un aviso DMC nuevo toque un lugar guardado (ALR-14) | P1 | M | ✅ |
| OFI-02 | **Capas de pronóstico de CONAF** (PI, HC, VV, HR, TP) | «Condiciones» oficiales para el riesgo en 3 capas (RISK-03) | Misma organización que el Botón Rojo; inspeccionar campos y fechas, resumir por comuna | P2 | M | 🟨 · PR #311 abierto (condiciones oficiales de CONAF por comuna) |
| OFI-03 | **Autorización formal de CONAF** para el CSV de incendios y el Botón Rojo | El repositorio de GEPRIF no declara licencia | Carta o correo a GEPRIF (ver ALI-01): pedir permiso, avisos de cambio de formato y un contacto técnico | P0 | S | 🟨 · PR #250 mergeado (borrador de carta a GEPRIF-CONAF); falta enviarla |
| OFI-04 | **Acceso oficial a las alertas de SENAPRED** | Responder «¿qué dijo la autoridad?» con la alerta real por comuna | Solicitud formal (idealmente un feed CAP público); mientras tanto, enlace directo. **No usar su API interna** | P1 | S | ⬜ |
| OFI-05 | **Comunas prioritarias de CONAF 2026-27** | La lista está vacía (`web/data/prioritarias.json`) | Buscar el documento oficial (resolución, presentación o informe) y cargarlo con su fuente | P1 | S | ⬜ · la lista sigue vacía; el PR #81 agregó solo la guarda estructural; PR #277 mergeado (constancia de la búsqueda del listado oficial) |
| OFI-06 | **Estadística histórica** `if_temporadas_2010_2024` (IDE Minagri) | Densidad histórica de igniciones por comuna para el riesgo y la Historia | La capa respondió sin campos: investigar la capa correcta o la descarga SHP; agregar por comuna y temporada | P2 | M | ⬜ |
| OFI-07 | **Censo 2024 (INE)** por comuna y manzana | Exposición: personas y viviendas en riesgo (RISK-03) | Descargar los datos oficiales, agregarlos por comuna y guardarlos en `web/data/` con su fuente | P2 | M | ✅ · hecho: `web/data/censo_2024.json` y `scripts/local/build_censo.py`, PR #121 |
| OFI-08 | **Interfaz urbano-forestal** | Exposición; la capa encontrada (`Riesgo_IF_Interfaz_Nacional`) la publica una cuenta personal | Verificar su origen (¿CONAF?) antes de usarla; buscar la versión oficial | P2 | S | ✅ · hecho: versión oficial `riesgo_dissolve_point` del catálogo GEPRIF (la del tablero «Zonas Interfaz»); `web/data/interfaz.json` vía `scripts/local/build_interfaz.py`, mostrada con el Censo en la ficha de Riesgo |
| OFI-09 | **Campamentos (MINVU)** | Las personas en campamentos fueron de las más afectadas en 2024; alta vulnerabilidad | Se vio una capa de `campamentos_minvu` en ArcGIS: verificar que sea oficial y pública; usarla solo agregada por comuna | P2 | S | ⬜ |
| OFI-10 | **Calidad del aire (SINCA, MMA)** | Humo: MP2,5 real medido en estaciones | Investigar el acceso en tiempo real (INV-07); combinar con el pronóstico de CAMS (AGUA-05) | P2 | M | ⬜ |
| OFI-11 | **Quemas autorizadas** (avisos de quema de CONAF) | Una quema autorizada explicaría muchas «señales de calor» y bajaría las falsas alarmas | Investigar si existe un registro consultable (INV-04); si existe, marcar «posible quema autorizada» | P1 | S | ✅ · resuelto por INV-04 (PR #137): no existe registro público consultable; caminos parciales en `docs/investigacion/INV-04-quemas-autorizadas.md` |
| OFI-12 | **Plan de continuidad ante SERNAFOR** | Las cuentas y URL de CONAF pueden cambiar en 2027 | Alertas automáticas de formato (ya existen para el CSV), pruebas de humo semanales de cada fuente (OPS-02) y contacto con GEPRIF | P2 | S | 🟨 · PR #289 mergeado (la prueba de humo semanal cubre Botón Rojo, GEPRIF, GLM y ADPF); el contacto con GEPRIF sigue pendiente (OFI-03) |
| OFI-13 | **SIDCO** (incendios en combate en tiempo real) | Es la fuente operativa de CONAF | Solo con autorización (la clave KML encontrada la publicó un tercero) | P3 | S | ⏸ autorización |
| OFI-14 | **Volcanes (SERNAGEOMIN)** | Alimentar DET-06 y, a futuro, una amenaza volcánica | Ranking de volcanes activos y reportes de actividad, con fuente | P3 | S | 🟨 · hecho en parte: todos los volcanes con ficha GVP en las fuentes fijas (PR #325); faltan los reportes de actividad |
| OFI-15 | **Rutas de evacuación y puntos de encuentro municipales** | Hoy se usan solo los de OpenStreetMap | Investigar qué municipios publican sus planes (Viña, Quilpué, Valparaíso, Penco, Tomé) y en qué formato | P2 | M | ⬜ · ver `docs/investigacion/INV-24-evacuacion-y-albergues.md` (los planos de SENAPRED son solo tsunami/volcánica y van con solicitud de copia; ningún municipio revisado publica puntos de encuentro por incendio) |
| OFI-16 | **Albergues activos** durante una emergencia | «¿Adónde voy?» es la segunda pregunta en una evacuación | Investigar si SENAPRED o los municipios los publican en línea; si no, coordinarlo como alianza (ALI-03) | P2 | S | ⬜ · ver `docs/investigacion/INV-24-evacuacion-y-albergues.md` (no hay registro en línea; en emergencias sale por RRSS de SENAPRED/Junaeb; los PCE traen el resumen de albergues como tabla en PDF) |
| OFI-18 | **Condiciones oficiales de CONAF (PI/HC/VV/HR/TP) por comuna** | La capa «oficial CONAF» del riesgo, junto al 30-30-30 y el FWI propios | Ingesta diaria por tandas (firma de capas en `kv`), resumen por comuna con la peor clase del día y bloque «Condiciones oficiales de CONAF» en `riesgo.js`. Extiende OFI-02 con los endpoints verificados en INV-FUENTES §2 | P1 | M | 🟨 · implementado, pendiente de la decisión del dueño: licencia por capa (puerta OFI-03) y rotulación oficial/propia |

---

## 6. Riesgo explicado (RISK)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| RISK-01 | **FWI canadiense propio** (`backend/fwi.py`) | Estándar internacional (EFFIS y GWIS lo usan), comparable y explicable | Hecho en 0.7.0: tablas del hemisferio sur, factor estacional del DC, prueba contra `cffdrs`; combinado con el 30-30-30. Pendiente: calibrarlo para Chile (RISK-13) | P1 | L | ✅ |
| RISK-02 | **Anomalía de lluvia** de junio a octubre de 2026 por comuna («hay más pasto que se secará») | La paradoja hidro-pirológica explica por qué esta temporada puede ser peor | Hecho en 0.7.0 la frase y la ficha por comuna (ERA5 vía Open-Meteo, misma ventana de días). Pendiente: la capa en el mapa, versionar las normales (FIX-25) y comparar con CR2MET (INV-08) | P1 | M | ✅ · hecho: capa de lluvia en el mapa (PR #142), normales versionadas (FIX-25, PR #88) y comparación con CR2MET (INV-08, PR #105) |
| RISK-03 | **Riesgo en 3 capas:** condiciones, combustible y exposición | Separar «puede empezar», «puede crecer» y «a quién afecta» | Condiciones: FWI, 30-30-30, Botón Rojo y DMC. Combustible: anomalía de lluvia y cicatrices. Exposición: Censo e interfaz. Prioridad = probabilidad × exposición, rotulada «aproximación BRASA» | P2 | L | ⬜ |
| RISK-04 | **Riesgo con varios puntos por comuna** | Hoy se usa el centro de la comuna: comunas extensas (Aysén, Natales, Antofagasta) quedan mal representadas | 3 a 9 puntos por comuna (zonas pobladas y la interfaz) y reportar el máximo o el percentil 90; el lote de Open-Meteo ya admite varias ubicaciones | P2 | M | 🟨 · PR #264 abierto (varios puntos por comuna; la comuna queda con el peor caso) |
| RISK-05 | **Riesgo en el lugar exacto** guardado | La gente pregunta por su casa, no por la comuna | Pronóstico puntual por lugar (en caché por celda de 0,1°) para el 30-30-30 y el FWI | P2 | M | ✅ · hecho: 30-30-30 del punto exacto en el resumen del lugar, PR #220 |
| RISK-06 | **Panel El Niño en palabras** | Explicar la temporada sin la regla «El Niño = más incendios» | Índice ONI y Niño 3.4 semanal del NOAA CPC; frase explicativa revisada por un climatólogo (ALI-07) | P2 | M | ✅ · hecho: panel «El Pacífico y esta temporada», PR #132 |
| RISK-07 | **Viento animado** (partículas) | Ver de dónde viene el viento a escala regional; muy pedido en emergencias | Grilla de 0,25° de Open-Meteo precalculada cada hora en el backend y servida como binario compacto; capa WebGL en MapLibre | P2 | L | ⬜ |
| RISK-08 | **«¿Por qué este nivel?»** en cada día | Confianza: el número sin explicación no convence | Una frase generada por reglas («calor 33 °C, aire seco 18 %, viento 35 km/h a las 16 h»), sin modelos de lenguaje | P1 | S | ✅ · hecho: `reasons` en `backend/risk.py:72-81`, publicado en `/api/risk` (`backend/routes/public.py:382`), PR #46 |
| RISK-09 | **Calibrar el 30-30-30 de BRASA contra el Botón Rojo** | Si discrepan mucho, hay que explicar por qué o ajustar | Durante el verano, comparar día y comuna; publicar la tabla de concordancia | P2 | M | ⬜ |
| RISK-10 | **KITRAL** (sistema chileno de comportamiento del fuego y modelos de combustible) | Es el estándar nacional; da credibilidad ante CONAF | Investigar documentación y disponibilidad (INV-11) antes de cualquier modelo propio | P3 | M | ⬜ |
| RISK-11 | **Sequedad de la vegetación** (NDMI de Sentinel-2 o humedad de combustible vivo) | El combustible es la mitad del riesgo | STAC de Copernicus; compuestos de 10 días por comuna; investigar el costo de procesamiento (INV-12) | P3 | L | ⬜ |
| RISK-12 | **Cicatrices de incendios previos** (FIRMS, VNP64A1, dNBR) | Combustible (las zonas recién quemadas arden menos) y aluviones (AGUA-01) | Huellas de los incidentes de BRASA y productos de área quemada | P2 | M | 🟨 · PR #247 abierto (cicatrices de la temporada por comuna, como dato abierto) |
| RISK-13 | **Calibrar los niveles del FWI y la regla combinada para Chile** | Las clases del FWI vienen de bosques boreales canadienses y de Europa; los pastizales de Chile central pueden arder con valores «bajos». La regla «si ambos llegan a alto, sube un paso» no está validada | Con QA-03: frecuencia de incendios de CONAF por clase de FWI, de 30-30-30 y combinada, por región. Ajustar los umbrales por macrozona y documentar el cambio | P1 | M | ✅ · hecho: calibración de niveles contra incendios CONAF, PR #138 |
| RISK-14 | **Cupo de Open-Meteo** compartido por el pronóstico, el FWI (60 días de archivo), las normales de lluvia y el clima de los casos | Un 429 en temporada deja el riesgo viejo | Medir las llamadas por día en `/api/status`; prioridad fija (pronóstico > FWI > normales > casos); evaluar el plan con clave de Open-Meteo (también por la licencia no comercial) | P1 | S | ✅ · hecho: cupo medido y publicado en `/api/status`, PR #126 |

---

## 7. Avisos y canales (ALR)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| ALR-01 | **Crear el bot de Telegram** y activar el webhook | El código está listo; falta el bot | La persona dueña lo crea con @BotFather; se cargan `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` y `TELEGRAM_WEBHOOK_SECRET` como secretos | P0 | S | ⏸ decisión |
| ALR-02 | **Aviso de cambio de estado de CONAF** («El incendio X ya está controlado») | Cierra el ciclo y baja la ansiedad | En `ingest_official_fires`, detectar el cambio de `status` en los incendios que ya generaron un aviso a ese lugar | P1 | S | ✅ · hecho: `evaluate_status_change` en `backend/alerts.py:364`, PR #42 |
| ALR-03 | **Aviso de reporte verificado cercano** | Los vecinos ven antes que los satélites (humo de día, fuego pequeño) | Al verificar un reporte, avisar a los lugares a ≤ 5 km con el texto «Un vecino informó… (revisado por BRASA)» | P1 | S | ✅ · hecho: aviso vecinal en `backend/alerts.py` (`REPORT_RADIUS_KM = 5.0`), PR #59 |
| ALR-04 | **Aviso preventivo diario** («Hoy hay Botón Rojo en tu comuna») a las 8:00 | La prevención evita igniciones: la mayoría son humanas | Opcional por lugar; una vez al día; solo en días de Botón Rojo o 30-30-30 alto; texto con 2 acciones concretas | P1 | M | ✅ · hecho: `evaluate_daily` en `backend/alerts.py:584`, PR #214 |
| ALR-05 | **«¿Te sirvió este aviso?»** (sí / no / era una quema) | Medir la calidad real y la fatiga | Botones en el aviso y en la bandeja; guardar `feedback` en `alerts`; métricas en la página de calidad (QA-05) | P1 | S | ✅ · hecho: «¿Te sirvió este aviso?» por aviso en el historial, PR #119 |
| ALR-06 | **WhatsApp** | Es el canal que usa casi todo Chile | Investigar la API de WhatsApp Business: costo por conversación, plantillas aprobadas y requisitos de verificación (INV-10). Requiere presupuesto | P2 | L | ⏸ decisión |
| ALR-07 | **SMS** para quien no tiene teléfono inteligente (personas mayores en zonas rurales) | Inclusión real | Proveedor local o internacional; costo por SMS; registro con doble confirmación; límite diario | P2 | L | ⏸ decisión |
| ALR-08 | **Avisos a la familia del lugar compartido** | Hoy la familia puede «recibir avisos» copiando el lugar; es indirecto | Al compartir, ofrecer «avisarme también a mí» con un clic, ligado al lugar original (no una copia), revocable por el dueño | P2 | M | ✅ · hecho: seguir un enlace compartido con un toque, PR #243 |
| ALR-09 | **Calibrar los avisos durante el verano** | Fatiga = la gente apaga los avisos | Revisar cada semana: avisos por lugar, «no me sirvió» y quemas confundidas; ajustar umbrales (FIX-08) con un registro de cambios | P1 | S | ⬜ |
| ALR-10 | **Escalamiento** (urgente sin abrir en 10 min → reenviar) | En emergencias, un aviso no leído es un aviso perdido | Push con `requireInteraction`; si hay Telegram, un segundo mensaje; nunca más de 2 | P2 | S | ✅ · hecho: reenvío único de un aviso urgente vigente, PR #202 |
| ALR-11 | **Avisos en otros idiomas** (inglés y criollo haitiano) | Turistas en la Patagonia y la comunidad haitiana en Chile | Plantillas por idioma con revisión humana; el idioma se elige en Ajustes (UX-10) | P3 | M | ⬜ |
| ALR-12 | **Resumen semanal por correo o Telegram** para municipios y juntas de vecinos | Uso institucional sin abrir la aplicación | Incidentes, días de Botón Rojo y avisos agregados (sin datos personales) | P3 | M | ⬜ |
| ALR-13 | **Prueba de aviso guiada** al guardar un lugar | Mucha gente no sabe si los avisos le llegan (sobre todo en iPhone) | Ya existe `/api/alerts/test`: integrarlo al final del formulario con una explicación por sistema operativo | P1 | S | ✅ · hecho: paso guiado tras guardar un lugar, PR #90 |
| ALR-14 | **Aviso push de un aviso DMC nuevo** (viento o calor extremo) que toca un lugar guardado | Hoy el aviso DMC se ve al abrir la aplicación, pero no llega como notificación | Al ingerir `dmc_alerts`, avisar una vez por aviso y lugar (deduplicar por identificador CAP); nivel «aviso», nunca «urgente» | P1 | S | ✅ · hecho: aviso push cuando un aviso DMC toca la comuna de un lugar, PR #149 |

---

## 8. Experiencia, accesibilidad e inclusión (UX)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| UX-01 | **Pruebas con usuarios reales:** 5 personas mayores, 5 adultos y 3 expertos | La meta es «la abuela y el amigo experto». Hoy no hay evidencia de que se logre | Guion de 5 tareas (guardar la casa, entender un aviso, qué hacer, compartir con la familia, leer el riesgo); escala SUS; grabación con consentimiento; registrar hallazgos en `docs/USUARIOS.md` | P0 | M | ⬜ |
| UX-02 | **Lectura en voz alta** del modo emergencia | Personas con baja visión o que no leen bien | Web Speech API (`speechSynthesis`) con voz es-CL si existe; botón «Escuchar» | P1 | S | ✅ · hecho: «Escuchar» en el modo liviano (PR #72) y en «Mi zona» (PR #122) |
| UX-03 | **Modo liviano** `/lite` sin mapa | Celulares de gama baja y señal 2G rural | HTML mínimo con el estado de los lugares, los avisos y los teléfonos; menos de 50 KB; sin WebGL | P1 | M | ✅ · hecho: `web/lite.html` y `web/js/lite.js`, PR #57 |
| UX-04 | **Auditoría de accesibilidad** con axe-core y lectores de pantalla (TalkBack, VoiceOver, NVDA) | Cumplir WCAG 2.2 AA de verdad | Integrar axe en `browser_checks.py`; probar a mano los flujos clave; arreglar anuncios `aria-live` de avisos nuevos | P1 | M | ✅ · hecho: axe-core en la revisión e2e, PR #63 |
| UX-05 | **Imagen para compartir por incidente** (vista previa en WhatsApp) | Lo que se comparte en una emergencia es una imagen | Imagen Open Graph dinámica con Pillow (mapa simplificado + estado + hora + «no es fuente oficial»), en caché | P2 | M | ✅ · hecho: `backend/og.py` con `tests/test_og.py` y las rutas `/i/<id>` y `/og/incident/<id>.png`, PR #170 |
| UX-06 | **Compartir un incidente o el riesgo del día** | Difusión responsable desde la fuente | Botón de compartir con un texto prearmado que siempre incluye «Sigue a SENAPRED» | P2 | S | ✅ · hecho: botón «Compartir» en la ficha (`web/js/views/incendio.js:93`), PR #50 |
| UX-07 | **Afiche con QR** para juntas de vecinos | Llegar a quien no busca aplicaciones | PDF imprimible por comuna: qué es BRASA, QR, teléfonos y 3 pasos | P2 | S | ✅ · hecho: hoja A4 imprimible de emergencia, PR #98 |
| UX-08 | **Modo pantalla pública** (municipios, cuarteles de Bomberos, colegios) | Visibilidad en la comunidad | `#/pantalla?comuna=…`: riesgo de hoy, Botón Rojo e incidentes cercanos, sin datos personales, a pantalla completa | P3 | M | ✅ · hecho: pantalla pública por comuna, PR #73 |
| UX-09 | **Guía para instalar la aplicación** según el sistema | En iPhone, las notificaciones exigen agregar BRASA a la pantalla de inicio | Detectar el sistema y mostrar los pasos con imágenes; volver a ofrecerlo tras guardar el primer lugar | P1 | S | ✅ · hecho: guía por sistema en `web/js/ui.js`, PR #45 |
| UX-10 | **Idiomas:** inglés, criollo haitiano y, con respeto y revisión comunitaria, mapudungun para lo esencial | Inclusión | Extraer los textos a diccionarios; empezar por el modo emergencia y los avisos | P3 | L | ⬜ |
| UX-11 | **Decisión guiada «¿Qué hago si…?»** (veo humo / me ordenan evacuar / no puedo salir / tengo animales) | En pánico, las listas largas no sirven | Árbol de 2 o 3 preguntas con respuestas cortas; contenido con fuente oficial (CONT-05) | P1 | M | 🟨 · PR #269 mergeado (ramas «animales» y «humo sin fuego»); PR #207 abierto (botón Escuchar por rama) |
| UX-12 | **Animales de granja y mascotas** | En el mundo rural, los animales son una razón para no evacuar | Sección en Prepárate con fuente (SAG, SENAPRED) | P2 | S | ✅ · hecho: sección de mascotas y animales de parcela con fuentes SENAPRED/SAG, PR #120 |
| UX-13 | **Modo alto contraste y daltonismo** | Los estados se distinguen por color y texto, pero los mapas no | Paleta alternativa validada (por ejemplo, con `validate_palette.js`) y patrones en el mapa de riesgo | P2 | M | ✅ · hecho: paleta apta para daltonismo en `web/js/map.js:44`, validada por `scripts/local/validate_palette.mjs`, PR #66 |
| UX-14 | **Descarga técnica** del incidente (GeoJSON y KML) para brigadistas y expertos | Uso profesional y en Google Earth | Botón en lectura detallada; mismos datos que la ficha | P2 | S | ✅ · hecho: descarga GeoJSON y KML en lectura detallada, PR #89 |
| UX-15 | **Presupuesto de rendimiento** | En gama baja, cada segundo cuenta | Lighthouse en CI con metas (LCP < 2,5 s en 4G); carga diferida de MapLibre fuera de Mapa | P2 | M | 🟨 · carga diferida de maplibre-gl.js (PR #141) y presupuesto de peso del arranque en la revisión (PRs #271 y #320); falta Lighthouse en CI |
| UX-16 | **Estados vacíos y errores con siguiente paso** en todas las vistas | Nunca dejar a alguien sin saber qué hacer | Revisar cada `catch` de las vistas: siempre los teléfonos y un «Reintentar» | P1 | S | 🟨 · PR #307 abierto («Reintentar» y teléfonos en Calidad cuando falla la consulta) |
| UX-17 | **Historial del lugar** («últimos 30 días cerca de tu casa») | Contexto y aprendizaje: «aquí se quema cada enero» | Lista de incidentes pasados dentro del radio | P3 | S | ✅ · hecho: historial del lugar, últimos 30 días cerca (PR #165); contrato fijado en pruebas (PR #285) |
| UX-18 | **Autoevaluación «Mi casa preparada»** con puntaje y fotos de ejemplo | Convertir la lista en acción | Puntaje 0-100 con los pesos de la guía oficial (CONT-05); se guarda en el dispositivo | P3 | M | ⬜ |

---

## 9. Multiamenaza: aluviones, calor y humo (AGUA)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| AGUA-01 | **Cicatrices de incendios** de la temporada 2026-27 | Sin suelo quemado no hay riesgo de aluvión post-incendio | Unión de huellas de incidentes + FIRMS + (opcional) dNBR de Sentinel-2; guardar por comuna y quebrada | P2 | M | 🟨 · PR #247 abierto (cicatrices de la temporada por comuna, como dato abierto) |
| AGUA-02 | **Pendiente** desde el DEM Copernicus GLO-30 | Aluvión = lluvia + pendiente + suelo quemado | Precalcular la pendiente media por cicatriz y cuenca pequeña con `scripts/` (offline) | P2 | M | ⬜ |
| AGUA-03 | **Lluvia horaria e isoterma 0 °C** (`freezing_level_height` de Open-Meteo) | La isoterma alta convierte nieve en lluvia sobre la cordillera | Pronóstico horario en los lugares y cicatrices; umbral inicial: lluvia diaria > P95 local e isoterma > P90 (documentado en `docs/ALUVIONES.md`) | P2 | M | 🟨 · hecho en parte: `backend/lluvia.py` (lluvia horaria e isoterma 0 °C con su señal, AGUA-03A, PR #186); faltan los umbrales por cicatriz |
| AGUA-04 | **Aviso «riesgo de aluvión»** por lugar guardado | Misma infraestructura de avisos, otra amenaza | Solo si el lugar está aguas abajo de una cicatriz (cuenca) y se cumple el umbral; texto con la acción («aléjate de quebradas») | P3 | L | ⬜ |
| AGUA-05 | **Humo y calidad del aire** (pronóstico CAMS vía Open-Meteo Air Quality + SINCA) | Las personas con asma, mayores y niños lo necesitan aunque el fuego esté lejos | MP2,5 pronosticado en el lugar; aviso opcional «el humo llegará mañana» | P2 | M | 🟨 · hecho en parte: MP2,5 de CAMS en la ficha de comuna (PR #257); PR #310 abierto (pronóstico de humo de 24 h en las tarjetas); falta el aviso opcional |
| AGUA-06 | **Calor extremo** (avisos DMC + pronóstico) | Calor = riesgo de incendio y de salud | Los avisos DMC de calor ya se muestran (0.7.0). Pendiente: recomendaciones de salud con fuente MINSAL, sobre todo para personas mayores | P2 | S | 🟨 · PR #263 abierto (consejos de salud junto al aviso de calor de la DMC) |
| AGUA-07 | **Caudales de la DGA** en tiempo real | Validación de crecidas | Investigar el acceso a sus estaciones satelitales (INV-13) | P3 | M | ⬜ |
| AGUA-08 | **Remoción en masa histórica** (SERNAGEOMIN) | Calibración del riesgo de aluvión | Catastros públicos de eventos | P3 | M | ⬜ |

---

## 10. Plataforma, infraestructura y operación (OPS)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| OPS-01 | **Monitoreo con aviso a la persona dueña** | Hoy, si la ingesta se cae, nadie se entera salvo quien mira la aplicación | Workflow programado de GitHub Actions cada 15 min: consulta `/api/status`; si `last_ingest_at` tiene más de 30 min, si una fuente falla 3 veces seguidas o si `backup` es `false`, abre un *issue* o manda un Telegram a la persona dueña. Sin costo | P0 | S | ✅ · hecho: `.github/workflows/monitoreo.yml` y `.github/scripts/monitoreo.py` (abre *issue* con etiqueta `monitoreo`), PRs #12 y #37 |
| OPS-02 | **Prueba de humo semanal de cada fuente** (FIRMS, GOES, CONAF, Open-Meteo y, a futuro, DMC) | Detectar cambios de formato antes de la emergencia | Ampliar `explorar-fuentes.yml` o crear `fuentes-salud.yml`: valida encabezados y campos esperados | P1 | S | ✅ · hecho: `.github/workflows/fuentes-salud.yml` y `.github/scripts/fuentes_salud.py`, PR #41 |
| OPS-03 | **Caché en el borde para picos de tráfico** | En un megaincendio (como Viña 2024), miles de personas abren la aplicación a la vez; un solo contenedor no aguanta | En el Worker, Cache API para los GET públicos (`/api/observations`, `/api/incidents`, `/api/official-fires`, `/api/risk`, `/api/status`) con 30 a 60 s; `stale-while-revalidate` si el contenedor está lento. Prueba de carga (OPS-04) | P0 | M | ✅ · hecho: `cachedApi` en `deploy/cloudflare/src/index.ts` con `X-Brasa-Cache`, PR #19 |
| OPS-04 | **Prueba de carga** | Saber cuánto aguanta antes de que haga falta | k6 o Locust contra una copia de prueba: 500 usuarios simultáneos en el mapa durante 10 min; medir p95 y errores | P1 | M | ✅ · hecho: `scripts/carga/mapa.js` (k6) y `scripts/carga/README.md`, PR #19 |
| OPS-05 | **Límite de solicitudes en el borde y Turnstile en los reportes** | Spam y abuso sin depender del limitador en memoria | Reglas de *rate limiting* de Cloudflare para `/api/reports` y `/api/subscribers`; Turnstile invisible en el formulario de reportes | P1 | S | ✅ · hecho: límites del Worker (429 con `Retry-After`) y Turnstile con `siteverify` en el backend, PR #19 |
| OPS-06 | **Teselas vectoriales o agrupación en el servidor** para el mapa | FIX-17; menos datos para celulares | Agregación por zoom (celdas H3 o cuadrícula) en `/api/observations?z=…`, o PMTiles generados cada ciclo | P2 | L | ⬜ |
| OPS-07 | **Evaluar Cloudflare D1** para `brasa.db` | Eliminaría el baile de respaldo y restauración, y permitiría más de un contenedor | Prototipo con el esquema actual (D1 es SQLite); medir latencia desde el contenedor; plan de migración con exportación | P3 | L | ⬜ |
| OPS-08 | **Dependencias con versiones fijas** (lock) y Dependabot | Construcciones reproducibles; avisos de seguridad | `uv pip compile` o `pip-tools` → `requirements.lock`; el Dockerfile instala desde el lock; `.github/dependabot.yml` para pip, npm y actions | P1 | S | ✅ · hecho: `requirements.lock` con `--require-hashes` en el Dockerfile y `.github/dependabot.yml`, PR #19 |
| OPS-09 | **Actualizar las acciones de GitHub** (checkout, setup-python, setup-node) | Advertencia de Node 20 y migración a Ubuntu 26 | Subir a la versión mayor vigente; correr los 4 workflows | P0 | S | ✅ · hecho: `checkout`, `setup-python` y `setup-node` a v7 en los workflows, PR #19 |
| OPS-10 | **Simulacro de restauración** desde R2 | Un respaldo que nunca se restauró no es un respaldo | Script que baja `db/brasa.db` y `db/work.db.gz` a un entorno local y verifica su integridad; mensual; versionado o retención en el bucket R2 | P1 | S | ✅ · hecho: `scripts/simulacro_restauracion.py` y `.github/workflows/simulacro-restauracion.yml` (mensual), PR #19 |
| OPS-11 | **Dominio propio** (por ejemplo, un `.cl`) | Confianza: `workers.dev` parece de prueba | Registrar el dominio; HSTS con `preload`; actualizar `PUBLIC_BASE_URL` y los enlaces de los avisos | P1 | S | ⏸ decisión |
| OPS-12 | **Rotar la clave de FIRMS** | La clave se pegó en una conversación de chat: hay que tratarla como expuesta | Pedir una clave nueva en FIRMS, cargarla como secreto y desactivar la anterior | P0 | S | ⬜ |
| OPS-13 | **Costos y cuotas** (Containers, R2, Workers) | Que no haya sorpresas en enero | Tabla mensual en `docs/SOSTENIBILIDAD.md`; alerta de facturación en Cloudflare | P1 | S | 🟨 · hecho en parte: tabla de límites y cuotas por servicio con fuente oficial en `docs/SOSTENIBILIDAD.md` (PR #173); falta la alerta de facturación (cuenta de la persona dueña) |
| OPS-14 | **Registros estructurados** y errores con contexto | Diagnosticar sin acceso a los registros del contenedor (el proxy bloquea su descarga) | Contador de errores por tipo en `/api/status` (sin datos personales); *Workers Logs* o *Logpush* si el plan lo permite | P2 | M | ✅ · hecho: resumen de errores de la ingesta en `/api/status`, PR #183 |
| OPS-15 | **Pruebas en Python 3.13** y en el Worker (TypeScript) | La matriz de CI hoy prueba 3.10 y 3.12; el Worker no tiene pruebas | Agregar 3.13; `tsc --noEmit` y pruebas unitarias del Worker (`tokenMatches`, mapeo a 503, CSP) | P2 | S | ✅ · hecho: 3.13 en la matriz (PR #77), `tsc --noEmit` en el workflow de despliegue y pruebas del Worker en `deploy/cloudflare/test/` (PR #106) |
| OPS-16 | **Gancho previo al commit** | Que `dev.py check` no se olvide | `.git/hooks/pre-commit` instalado por `dev.py setup` (opcional) | P2 | S | ✅ · hecho: `install_pre_commit_hook` en `dev.py:69`, PR #49 |
| OPS-17 | **Congelamiento de temporada** | Evitar romper la aplicación en pleno incendio | Del 15 de diciembre al 28 de febrero, solo arreglos; cada despliegue con diagnóstico y reversión probada (desplegar el commit anterior) | P1 | S | ✅ · hecho: runbook del congelamiento en `docs/OPERACION.md`, PR #86 |
| OPS-18 | **Tamaño del respaldo de `work.db`** | 45 días de observaciones pueden crecer mucho en temporada | Registrar el tamaño comprimido en `/api/status`; si supera 50 MB, respaldar solo incidentes y fuentes oficiales | P2 | S | ✅ · hecho: tamaño del respaldo visible en `/api/status`, PR #191 |
| OPS-19 | **Desplegar lo que hay en `main` (la ola OPS) y verificarlo en producción** | 0.7.0 a 0.9.0 ya están en producción; la ola OPS (caché en el borde, límites, simulacro, monitoreo) está en `main` pero no en Cloudflare | Desplegar y correr el diagnóstico; confirmar que `fwi_daily` tiene las 345 comunas, que llegan `dmc_alerts`, cuántas normales de lluvia hay completas y que no hay 429 de Open-Meteo. Ampliar el diagnóstico para publicar esos conteos | P0 | S | ⬜ |

---

## 11. Seguridad, privacidad y cumplimiento legal (SEC)

La **Ley 21.719** rige desde el **1 de diciembre de 2026**, salvo que se publique antes la postergación a 2027. BRASA guarda ubicaciones de casas, la marca «persona mayor o alguien que necesita ayuda para salir» (posible dato sensible) y fotos. Esto es prioridad P0.

| ID | Qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|
| SEC-01 | **Política de privacidad** clara y corta (versión sencilla y completa) | Qué se guarda (token del dispositivo, lugares, avisos, reportes), para qué, cuánto tiempo (FIX-21), dónde (Cloudflare y R2: transferencia internacional), derechos y contacto. Página `#/privacidad` enlazada desde Ajustes y desde el formulario de lugar. Hecha en 0.9.0 (`web/js/views/privacidad.js`, enlaces en Ajustes y en el formulario de lugar) | P0 | M | ✅ |
| SEC-02 | **Derechos de las personas:** acceso, rectificación, supresión y portabilidad | `GET /api/me/export` (JSON con todo lo del dispositivo) y `DELETE /api/me` (FIX-22); botones en Ajustes. Hecho en 0.9.0; la rectificación ya existía (editar cada lugar) | P0 | S | ✅ |
| SEC-03 | **Consentimiento informado para «persona mayor»** | Texto que explica por qué se pide, que es opcional y que solo cambia el umbral de aviso; consentimiento explícito; nunca se comparte en el modo vecino sin aviso a quien comparte. Hecho en 0.9.0: el formulario explica el para qué y el modal de compartir avisa que la marca también se ve | P0 | S | ✅ |
| SEC-04 | **Minimización** | Revisar cada campo: ¿hace falta? Redondear la ubicación de los reportes públicos (ya ~100 m); no registrar IP en la base; no guardar el `User-Agent`. Verificado en 0.9.0: la IP vive solo en memoria del limitador y el User-Agent no se persiste; documentado en `#/privacidad` y en la EIPD | P0 | S | ✅ |
| SEC-05 | **Evaluación de impacto** (EIPD) breve | Documento `docs/PRIVACIDAD_EIPD.md`: riesgos (por ejemplo, el mapa de casas con personas mayores sería valioso para un delincuente), medidas, responsable. Hecho en 0.9.0 | P0 | M | ✅ |
| SEC-06 | **Cifrado del respaldo** en R2 | Cifrar `brasa.db` antes de subirlo (AES-GCM con una clave en un secreto del Worker) | P1 | M | ✅ · hecho: respaldo cifrado AES-256-GCM en R2, PR #146 |
| SEC-07 | **Asesoría legal** (una vez) | Revisar la política, los términos, el descargo de responsabilidad, el rol de «no oficial» y el uso de datos de CONAF. Buscar apoyo *pro bono* (clínicas jurídicas universitarias) | P0 | S | ⏸ decisión |
| SEC-08 | **Términos de uso y descargo** | «No es un sistema oficial de alerta; sigue a SENAPRED»: hoy está en la interfaz, falta un documento. Hecho en 0.9.0: `docs/TERMINOS.md`, enlazado desde `#/privacidad` | P0 | S | ✅ |
| SEC-09 | **Auditoría de dependencias** | `pip-audit` y `npm audit` (Worker) en CI | P1 | S | ✅ · hecho: `.github/workflows/seguridad.yml` semanal, PR #54 |
| SEC-10 | **Moderadores con tokens individuales y registro de acciones** | Hoy hay un solo `ADMIN_TOKEN` compartido; tabla `moderators` y `moderation_log` (quién, qué, cuándo) | P1 | M | 🟨 · PR #218 abierto (tokens individuales y registro de acciones) |
| SEC-11 | **Política de contenido de los reportes** | Qué hacer con fotos de personas, heridos o contenido abusivo; plazo de revisión; botón «reportar» | P1 | S | ✅ · hecho: política de contenido de los reportes, PR #144 |
| SEC-12 | **Rotación de secretos** | Calendario para `ADMIN_TOKEN`, `INTERNAL_TOKEN` y la clave de FIRMS (OPS-12); documentar el procedimiento en `docs/OPERACION.md` | P1 | S | ✅ · hecho: procedimiento de rotación documentado, PR #162 |
| SEC-13 | **Revisión de seguridad completa** antes de la temporada | Recorrido OWASP de la API, el Worker y el service worker (por ejemplo, con `/security-review` de Claude Code) | P1 | M | ✅ · hecho: revisión de seguridad documentada, PR #133 |
| SEC-14 | **Licencia del repositorio** | El repositorio es público y no tiene archivo `LICENSE`, así que legalmente todos los derechos están reservados y nadie puede contribuir con claridad. Elegir licencia de código (por ejemplo, AGPL-3.0 o MIT) y de datos propios (por ejemplo, CC BY 4.0), respetando las de terceros | P0 | S | ✅ · hecho: AGPL-3.0 para el código y CC BY 4.0 para datos propios (`LICENSE` en `main`), PR #143 |

---

## 12. Calidad, pruebas y validación científica (QA)

| ID | Qué | Por qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|---|
| QA-01 | **e2e en CI** con la base de demostración | Que nadie rompa la interfaz sin enterarse | Job con `setup --e2e`, `seed`, servidor en segundo plano y `dev.py e2e`; capturas como artefacto | P1 | S | ✅ · hecho: job e2e en `.github/workflows/tests.yml`, PR #43 |
| QA-02 | **Banco de reproducción** de los casos: pasar los GOES precalculados por `incidents.update` en orden temporal | Medir rendimiento (FIX-15) y comportamiento: ¿cuántos minutos después de la primera detección el incidente pasa a «posible»? | `scripts/replay_case.py <id>` → tabla de tiempos, cantidad de incidentes y fusiones; prueba lenta opcional | P1 | M | ✅ · hecho: `scripts/replay_case.py`, PR #53 |
| QA-03 | **Validación contra CONAF** (el corazón científico del proyecto) | Responder con datos: ¿qué porcentaje de los incendios de CONAF detecta BRASA, por tamaño?, ¿con cuántos minutos de adelanto o atraso respecto de `f_deteccion` y `f_aviso`?, ¿cuántos «posibles» no tienen un incendio de CONAF cerca? | Con FIX-14 y la temporada en curso: tasa de detección por tamaño (< 1 ha, 1-10, 10-100, > 100 ha), falsas alarmas fuera de quemas y ventaja de tiempo. Publicarlo en la página de calidad (QA-05) | P1 | L | 🟨 · script `scripts/validar_deteccion.py` en `main`, extendido sobre `work.db` (PRs #74 y #139); PR #290 mergeado (medida de adelanto del caso Viña 2024 publicada en `#/calidad`) |
| QA-04 | **Pruebas del frontend** sin navegador | Funciones puras (`dual`, `fmt*`, `fireIncidents`, `emKey`, decisiones de estado) | `node --test` con módulos ES; sin dependencias nuevas | P2 | M | ✅ · hecho: `tests/js/*.test.mjs` con `node --test`, PR #55 |
| QA-05 | **Página «Calidad de los datos»** (`#/calidad`) | Transparencia: confianza ganada con números | Latencias p50/p90 por fuente, ingestas fallidas, frescura, incidentes, descartes, avisos y «me sirvió» (ALR-05), validación (QA-03) | P2 | M | ✅ · hecho: `web/js/views/calidad.js`, ruta `#/calidad`, PR #112 |
| QA-06 | **Regresión visual** | Detectar cambios de diseño no intencionales | Comparar las capturas de `e2e` contra una referencia con tolerancia | P3 | M | ✅ · hecho: regresión visual con referencia y tolerancia en e2e, PR #185 |
| QA-07 | **Pruebas de propiedades** de la agrupación | Casos borde (fusiones en cadena, detecciones desordenadas, empates) | Hypothesis: invariantes (cada detección en un solo incidente, la caja contiene a sus miembros, la fusión conserva el más antiguo) | P3 | M | ✅ · hecho: `tests/test_incidents_props.py` (con `random.Random` y semillas fijas, sin dependencias nuevas), PR #92 |
| QA-08 | **Prueba en terreno** con señal rural | La teoría no reemplaza a una parcela en Hualañé con una línea de señal | Probar en 3 comunas rurales: tiempos de carga, avisos y modo liviano (UX-03) | P1 | M | ⬜ |

---

## 13. Contenido: Historia y Prepárate (CONT)

| ID | Qué | Cómo (resumen) | P | T | Estado |
|---|---|---|---|---|---|
| CONT-01 | **Cifra final oficial de Torres del Paine 2011-12** | Hoy solo hay cifras «mientras avanzaba»: buscar el informe de CONAF o Onemi y agregarlo como revisión | P2 | S | ✅ · hecho: cifra final oficial de Torres del Paine 2011-12, PR #177 |
| CONT-02 | **Cifra final de CONAF de Valparaíso 2024** (por complejo y total) | Buscar el informe oficial de CONAF (o la cartografía de IDE Minagri) y agregarlo como revisión «oficial directa» | P1 | S | ✅ · hecho: cifra oficial agregada en `web/data/cases.json`, PR #78 |
| CONT-03 | **Cifras de la temporada 2022-23 y de Santa Juana** | El caso 2023 no tiene cifras: buscar el balance oficial | P2 | S | ✅ · hecho: cifras de la temporada 2022-23 agregadas al caso de febrero de 2023, PR #91 |
| CONT-04 | **Distinguir «oficial directo» de «oficial citado por prensa»** en las revisiones | Campo `kind` en cada revisión; etiqueta visible | P2 | S | ✅ · hecho: campo `kind` en `web/data/cases.json`, PR #60 |
| CONT-05 | **Cada recomendación de Prepárate con su fuente oficial** | Enlazar la guía de SENAPRED (plan familiar, kit de emergencia) y la de CONAF (comunidad preparada) por recomendación; **verificar los 2 L de agua por persona al día** en la fuente | P0 | M | ✅ · hecho: cada recomendación con su fuente oficial, PR #145 |
| CONT-06 | **Más casos** (candidatos a investigar) | Navidad 2019 en Valparaíso (Rocuant y San Roque), el resto de los focos de la temporada 2025-26, un incendio de la Araucanía o Los Ríos y un caso de la Patagonia reciente. Requisito: datos GOES o FIRMS y cifras con fuente | P3 | L | ⬜ |
| CONT-07 | **VIIRS/MODIS para el caso 2026** | Verificar si el archivo FIRMS SP ya cubre enero de 2026; si no, intentar NRT o esperar | P2 | S | ⬜ |
| CONT-08 | **Perímetros oficiales** en los casos (IDE Minagri) | Convertirlos con `scripts/convert_conaf.py` y cargarlos como estado final | P2 | M | ✅ · hecho: perímetro oficial de CONAF como capa apagable en Historia, PR #292 |
| CONT-09 | **Lecciones aprendidas por caso** desde informes técnicos (CIGIDEN, CR2, CEDIM, WildFireX) | Un párrafo por caso con fuente: qué falló y qué se puede hacer distinto | P2 | M | ✅ · hecho: lecciones aprendidas por caso con fuente, PR #192 |
| CONT-10 | **Módulo para colegios** | Una clase de 45 min con la reconstrucción de un caso, preguntas y una guía docente | P3 | L | ⬜ |
| CONT-11 | **Datos GOES-13 para Valparaíso 2014** | Investigar el archivo WFABBA de GOES-13 (INV-15) para reconstruir el caso con datos geoestacionarios | P3 | M | ⬜ |
| CONT-12 | **Plan para personas con discapacidad** | Prepárate: necesidades de movilidad, medicamentos, dispositivos y redes de apoyo, con fuente oficial | P1 | S | ✅ · hecho: sección «Si necesitas ayuda para salir» en Prepárate, PR #65 |

---

## 14. Alianzas, comunidad e institucionalidad (ALI)

| ID | Con quién | Qué proponer | P | Estado |
|---|---|---|---|---|
| ALI-01 | **CONAF, GEPRIF** (Depto. de Desarrollo e Investigación) | Ya publica datos abiertos en GitHub y ArcGIS. Pedir autorización de uso (OFI-03), un contacto técnico y avisos de cambios. Ofrecer a cambio la validación QA-03 (cuánto adelanta el satélite a su detección) | P0 | 🟨 · PR #250 mergeado (borrador de carta a GEPRIF-CONAF); falta enviarla |
| ALI-02 | **SENAPRED** | Acceso oficial a alertas (OFI-04), revisión del contenido de Prepárate y del modo emergencia, y un protocolo de convivencia con el SAE | P1 | ⬜ |
| ALI-03 | **Municipios piloto** (Quilpué, Viña del Mar, Penco, Tomé y una comuna del Maule) | Piloto con juntas de vecinos; rutas, puntos de encuentro y albergues (OFI-15, OFI-16); afiches (UX-07) | P1 | ⬜ |
| ALI-04 | **Bomberos** (compañías de zonas de interfaz) | Red de verificadores de reportes; difusión | P1 | ⬜ |
| ALI-05 | **Red de moderadores voluntarios** | Turnos, capacitación de 1 h, guía de verificación y canal de coordinación. Sin moderación, el estado «visto por vecinos» no existe | P1 | ⬜ |
| ALI-06 | **Universidades:** U. de Chile (equipo de Cell2Fire), CR2, CIGIDEN, UdeC y UACh | Validación científica, FWI, KITRAL, escenarios de propagación (IDEA-01) y tesis de pregrado o magíster sobre los datos de BRASA | P2 | ⬜ |
| ALI-07 | **Climatólogos** (CR2 o DMC) | Revisar los textos del panel El Niño y de la anomalía de lluvia | P2 | ⬜ |
| ALI-08 | **Empresas forestales y eléctricas** con cámaras y torres | Acceso a detecciones de cámaras (con acuerdo), sin depender de ellas ni perder la independencia; política de conflicto de interés | P3 | ⬜ |
| ALI-09 | **Radios comunitarias** | Boletín diario de riesgo generado automáticamente (IDEA-05) | P2 | 🟨 · boletín de 60 s por región ya en `main` (PR #100) con su prueba de contrato (PR #221); falta acercarse a las radios |
| ALI-10 | **Protocolo de comunicación en emergencias** | Qué publica BRASA, qué no, cómo se corrige un error público y quién habla con la prensa. Documento `docs/COMUNICACION.md` | P1 | ✅ · hecho: `docs/COMUNICACION.md`, PR #96 |
| ALI-11 | **Comunidad de código abierto** | Licencia (SEC-14), etiquetas «buena primera tarea» y una guía de contribución (ya existe `CONTRIBUTING.md`) | P2 | ⬜ |

---

## 15. Sostenibilidad y financiamiento (NEG)

| ID | Qué | Notas | P | Estado |
|---|---|---|---|---|
| NEG-01 | **Presupuesto mínimo anual** | Cloudflare (Containers, R2, Workers), dominio, SMS o WhatsApp (si se aprueban) y tiempo de moderación. Documentarlo en `docs/SOSTENIBILIDAD.md` | P1 | 🟨 · hecho en parte: `docs/SOSTENIBILIDAD.md` con fuentes de financiamiento, costos y cuotas (PR #173); falta el presupuesto anual cerrado |
| NEG-02 | **Programas de apoyo tecnológico** a investigar | Cloudflare Project Galileo (organizaciones de interés público), créditos de nube para ONG y programas de respuesta a desastres de proveedores de nube (verificar requisitos de cada uno) | P1 | ⬜ |
| NEG-03 | **Fondos públicos y concursos** a investigar | ANID, CORFO, fondos regionales de innovación (FIC), Laboratorio de Gobierno y concursos municipales | P2 | ⬜ |
| NEG-04 | **Fundaciones internacionales** a investigar | Fondos de impacto en clima y desastres de empresas tecnológicas y fundaciones filantrópicas | P2 | ⬜ |
| NEG-05 | **Versión institucional** (municipios, condominios, forestales, aseguradoras) | Panel de varios lugares, informes y soporte, **sin que la versión ciudadana pierda funciones**. Revisar las licencias no comerciales de Open-Meteo y Sentinel-2 cloudless antes de cobrar | P3 | ⬜ |
| NEG-06 | **Figura legal** (fundación o corporación sin fines de lucro) | Necesaria para convenios, fondos y responsabilidad legal | P2 | ⏸ decisión |
| NEG-07 | **Métricas de impacto** para postular a fondos | Lugares guardados por comuna, avisos enviados, validación QA-03 y resultados de pruebas con usuarios | P1 | ⬜ |

---

## 16. Ideas exploratorias (IDEA)

Ideas con potencial que necesitan investigación o una alianza antes de comprometerse. Ninguna debe mostrarse como dato real sin validación.

| ID | Idea | Condición para avanzar |
|---|---|---|
| IDEA-01 | **Escenarios de propagación** con Cell2Fire (desarrollado en Chile) y combustibles KITRAL, mostrados como «escenario estimado», nunca como predicción | Backtesting con 2017, 2023, 2024 y 2026 y la colaboración de ALI-06 |
| IDEA-02 | **Enlace a imágenes satelitales del momento** (NASA Worldview, con la hora y el área del incidente, y visores GOES como SLIDER) para «ver el humo» | Verificar los parámetros de URL de cada visor; cero costo de procesamiento. **Hecho:** enlaces a Worldview y SLIDER desde el caso abierto, PR #82 |
| IDEA-03 | **Detección de humo por cámaras con IA** al estilo de ALERTCalifornia | Acuerdo con dueños de cámaras (ALI-08) y validación humana obligatoria |
| IDEA-04 | **Informe mensual automático** «Así fue el mes en incendios» (por región, con fuentes) | QA-03 y QA-05 listos. **Hecho:** informe mensual por región para radios y municipios, PR #278 |
| IDEA-05 | **Boletín diario para radios** (texto de 60 segundos por región con el riesgo, el Botón Rojo y los incidentes) | Plantillas por reglas; revisión de ALI-09. **Hecho:** boletín radial de 60 s por región, PR #100; prueba de contrato contra la API pública, PR #221 |
| IDEA-06 | **«Vecino de confianza»:** una persona mayor designa a un vecino que recibe sus avisos urgentes | Diseño de consentimiento (SEC-03) y pruebas con usuarios |
| IDEA-07 | **Mapa de 10 años de calor por comuna** (FIRMS SP 2015-2025): «dónde se quema siempre» | DET-05 reutiliza el mismo procesamiento |
| IDEA-08 | **Cierres de rutas** en el mapa durante una evacuación | Fuente oficial (Vialidad, Carabineros o municipios) o una alianza de datos de tráfico; investigar |
| IDEA-09 | **API abierta para investigación** (incidentes y observaciones en GeoJSON con licencia clara) | Fase 3.3; licencia SEC-14 y respeto de las licencias de terceros |
| IDEA-10 | **Asistente de lenguaje para resumir un incidente** a periodistas o radios | Solo con texto 100 % trazable a datos; revisión humana; nunca en avisos de emergencia |
| IDEA-11 | **Exportación CAP de BRASA** para que otros sistemas la consuman | Cuidado: BRASA no es autoridad. Solo como «información ciudadana», sin entrar a canales de alertas oficiales |
| IDEA-12 | **Juego de prevención para niños** («limpia tu patio antes del verano») | CONT-10; diseño con docentes |
| IDEA-13 | **Integración con calendarios** (agregar el «día de Botón Rojo» al calendario familiar) | Bajo esfuerzo con un archivo `.ics` por comuna |
| IDEA-14 | **Dron o aeronave en el mapa** | Prohibido sin una fuente oficial autorizada. Se anota solo para recordar que **no** se hace |

---

## 17. Investigaciones necesarias (INV)

Cada investigación termina en una nota en `docs/investigacion/INV-xx.md` con la pregunta, las fuentes, la respuesta, la confianza y la decisión.

### INV-01 · Requisitos concretos de la Ley 21.719 para BRASA — P0
- **Estado:** ✅ hecho (`docs/investigacion/INV-01-ley-21719.md`, PR #16).
- **Preguntas:** ¿«persona mayor o alguien que necesita ayuda para salir» es un dato sensible (salud o discapacidad)? ¿Hace falta un encargado de protección de datos? ¿Cómo se trata la transferencia internacional (Cloudflare y R2)? ¿Qué plazos de respuesta tienen los derechos? ¿Qué pasa con el proyecto de postergación (boletín 18.623-07)?
- **Fuentes:** texto de la ley en la BCN, guías de la Agencia de Protección de Datos Personales (cuando existan), análisis de estudios jurídicos y clínicas universitarias.
- **Salida:** lista de verificación para SEC-01 a SEC-08.

### INV-02 · Licencia y permiso de las fuentes de CONAF — P0
- **Preguntas:** ¿bajo qué condiciones se puede redistribuir el CSV de GEPRIF y las capas de ArcGIS (Botón Rojo, PI, HC…)? ¿Quién autoriza? ¿Cambiará con SERNAFOR?
- **Salida:** carta de solicitud (ALI-01) y la respuesta archivada.

### INV-03 · ¿CONAF publica perímetros de los incendios? — P2
- **Pista:** la columna `sha2_ultimo_poligono` del CSV sugiere polígonos versionados. Buscar en el mismo repositorio y en la organización de ArcGIS `geprif.conaf`.
- **Salida:** si existen, mostrar el perímetro oficial en la ficha del incidente.

### INV-04 · Registro de quemas autorizadas — P1
- **Estado:** ✅ hecho (`docs/investigacion/INV-04-quemas-autorizadas.md`, PRs #75 y #137). Veredicto: **no** existe un registro público consultable; OFI-11 queda resuelto en negativo, con caminos parciales documentados.
- **Preguntas:** ¿existe un registro consultable de avisos de quema de CONAF por comuna y fecha? ¿Con qué precisión de ubicación? ¿Es público?
- **Salida:** OFI-11 sí o no.

### INV-05 · Desplazamiento de los píxeles GOES por el relieve en Chile — P2
- **Preguntas:** ¿el producto FDC corrige el paralaje por altura del terreno? ¿Cuánto se desplaza un foco a 2.000 o 3.000 m en la cordillera, visto desde 75,2° O? ¿Hacia dónde?
- **Método:** comparar detecciones GOES y VIIRS simultáneas en incendios de montaña de los casos 2023, 2024 y 2026.
- **Salida:** DET-02 sí o no, con la magnitud medida.

### INV-06 · Otros sensores para después de MODIS — P3
- **Preguntas:** latencia y acceso de Sentinel-3 SLSTR FRP sobre Chile; cobertura de Landsat; planes de JPSS-3 y JPSS-4.
- **Salida:** DET-07.

### INV-07 · Calidad del aire en tiempo real (SINCA) — P2
- **Preguntas:** ¿hay una API o archivos actualizados cada hora? ¿Licencia? ¿Cobertura en zonas de interfaz?
- **Salida:** OFI-10 y AGUA-05.

### INV-08 · CR2MET frente a ERA5 para la anomalía de lluvia — P1
- **Estado:** ✅ hecho (PR #105).
- **Preguntas:** ¿CR2MET se actualiza con poco retraso? ¿Es mejor que ERA5 en Chile central y sur? ¿Licencia?
- **Salida:** la fuente de RISK-02.

### INV-09 · Comprensión de los avisos y fatiga — P0
- **Estado:** ✅ hecho (`docs/investigacion/INV-09-avisos-fatiga.md`, PR #16); las pruebas con personas (UX-01) siguen pendientes.
- **Preguntas:** ¿una persona mayor entiende «posible incendio», «señal de calor» y «Botón Rojo»? ¿Cuántos avisos por semana tolera antes de ignorarlos? ¿Qué umbral para la persona mayor (FIX-08)?
- **Método:** UX-01, más datos de ALR-05 durante diciembre.
- **Salida:** textos y umbrales ajustados con su evidencia.

### INV-10 · Costos y requisitos de WhatsApp Business y SMS — P2
- **Preguntas:** costo por mensaje o conversación en Chile, aprobación de plantillas, verificación de la organización, límites de envío y alternativas locales de SMS.
- **Salida:** propuesta con presupuesto para la decisión de ALR-06 y ALR-07.

### INV-11 · KITRAL y modelos chilenos de comportamiento del fuego — P3
- **Preguntas:** documentación pública, mapas de combustibles disponibles y su resolución, y si Cell2Fire los integra.
- **Salida:** RISK-10 e IDEA-01.

### INV-12 · Sequedad de la vegetación con Sentinel-2 a bajo costo — P3
- **Preguntas:** ¿se puede calcular el NDMI por comuna cada 10 días sin servidores propios (por ejemplo, con *openEO* de Copernicus o con Actions)? ¿Cuánto tarda?
- **Salida:** RISK-11.

### INV-13 · Acceso a caudales de la DGA — P3
- **Salida:** AGUA-07.

### INV-14 · Fin de S-NPP y de MODIS: impacto en los casos — P1
- **Estado:** ✅ hecho (PR #103).
- **Preguntas:** ¿FIRMS mantendrá el archivo SP de S-NPP y MODIS después de noviembre de 2026 y de 2027? ¿Qué pasa con el botón «Sumar VIIRS/MODIS» de la Historia?
- **Salida:** ajustar `firms_sources` de los casos y el texto de la interfaz.

### INV-15 · Archivo GOES-13 (WFABBA) para casos anteriores a 2017 — P3
- **Preguntas:** ¿dónde está el archivo de detecciones de fuego de GOES-13 (programa WFABBA, CIMSS)? ¿Cubre Chile? ¿Formato?
- **Salida:** CONT-11.

### INV-16 · Industria y antorchas que el satélite ve como calor permanente — P1
- **Estado:** ✅ hecho (`docs/investigacion/INV-16-industria-antorchas.md`, PR #16).
- **Método:** FIRMS SP 2019-2025, celdas persistentes, cruzadas con imágenes y fuentes públicas (permisos ambientales y empresas).
- **Salida:** la lista curada de DET-06 con una fuente por punto.

### INV-17 · Formato de los avisos CAP de la DMC — P1
- **Estado:** ✅ hecho en la práctica: `backend/providers/dmc.py` ya lee el RSS y el CAP (polígono → comunas, o nombre de zona/región) desde la 0.7.0.
- **Preguntas:** ¿el área viene como texto, polígono o código de zona? ¿Cómo mapearla a comunas? ¿Con qué frecuencia se actualiza el RSS?
- **Salida:** OFI-01.

### INV-18 · Uso real y preferencias de canal en Chile — P2
- **Preguntas:** ¿cuántas personas mayores usan WhatsApp frente a SMS? ¿Qué canal abren primero en una emergencia? Buscar encuestas de la Subtel o de universidades.
- **Salida:** prioridades de ALR.

### INV-19 · Instituciones después de SERNAFOR — P2
- **Preguntas:** ¿qué pasa con GEPRIF, sus cuentas y sus datos? ¿Hay una ley de incendios forestales y rurales en trámite? ¿Cambian las competencias de SENAPRED?
- **Salida:** OFI-12 actualizado.

---

## 18. Decisiones que solo puede tomar la persona dueña

| Decisión | Opciones | Recomendación | Bloquea |
|---|---|---|---|
| **Licencia del repositorio** | AGPL-3.0 (las mejoras quedan abiertas) · MIT (máxima adopción) · otra | AGPL-3.0 para el código y CC BY 4.0 para los datos propios | SEC-14, ALI-11, IDEA-09 |
| **Bot de Telegram** | Crearlo ahora · esperar | Crearlo ahora: el código está listo y no tiene costo | ALR-01 |
| **Dominio propio** | `.cl` · seguir en `workers.dev` | Un `.cl` corto antes de diciembre | OPS-11 |
| **WhatsApp y SMS** | Presupuesto mensual · no por ahora | Esperar INV-10; empezar con SMS solo para personas mayores registradas por su familia | ALR-06, ALR-07 |
| **Figura legal** | Fundación · corporación · alero de una universidad | Alero universitario mientras se crea la fundación | NEG-06, convenios |
| **Asesoría legal** | Pagada · *pro bono* | Clínica jurídica universitaria (privacidad y responsabilidad) | SEC-07 |
| **Rotar la clave de FIRMS** | Ahora · después | Ahora | OPS-12 |
| **Congelamiento de temporada** | 15-dic a 28-feb · otro | 15-dic a 28-feb | OPS-17 |
| **Cartas a CONAF y SENAPRED** | Enviar · esperar | Enviar en octubre: las respuestas institucionales tardan | OFI-03, OFI-04 |

---

## 19. Riesgos del proyecto y cómo mitigarlos

| Riesgo | Probabilidad | Impacto | Mitigación | Ítems |
|---|---|---|---|---|
| **Falso negativo:** BRASA no avisa de un incendio real cercano | Media | Muy alto | FIX-01, FIX-02, FIX-03, DET-13; mensaje permanente «no esperes a BRASA: si ves fuego, llama» | FIX-01 a FIX-03 |
| **Fatiga de avisos:** la gente apaga BRASA | Alta | Alto | FIX-08, ALR-05, ALR-09, INV-09 | ALR |
| **Caída en el peor momento** (pico de tráfico) | Media | Muy alto | OPS-03, OPS-04, modo liviano (UX-03) | OPS |
| **La fuente de CONAF cambia o desaparece** | Media (SERNAFOR) | Alto | OFI-12, OPS-02, ALI-01 | OFI |
| **Problema legal de datos personales** | Media | Alto | SEC-01 a SEC-08 antes del 1-dic | SEC |
| **Confusión con alertas oficiales** | Baja | Muy alto | Lenguaje «no oficial», nunca imitar el SAE, ALI-02, ALI-10 | ALI |
| **Mal uso de los datos** (mapa de casas de personas mayores) | Baja | Muy alto | Nada personal es público; cifrado del respaldo (SEC-06); EIPD (SEC-05) | SEC |
| **Proyecto de una sola persona** | Alta | Alto | Documentación (hecha), licencia abierta, comunidad (ALI-11) y figura legal | NEG, ALI |
| **Costos inesperados** | Baja | Medio | OPS-13, NEG-02 | OPS |
| **Error público de BRASA en una emergencia** | Media | Alto | Protocolo de corrección (ALI-10), transparencia (QA-05) | ALI |

---

## 20. Ruta sugerida semana a semana

Hoy es lunes 19 de octubre de 2026. La ruta prioriza lo que sirve antes del 1 de diciembre y deja el verano para operar. (Estados sincronizados el 19-oct-2026: ✅ hecho en `main`, 🟨 con PR abierto.)

| Semana | Foco | Ítems |
|---|---|---|
| **19 al 25 de oct** | Que no se pierdan datos y que alguien se entere si algo falla | OPS-19 (desplegar lo que hay en `main`), FIX-01 ✅, FIX-02 ✅, OPS-01 ✅, OPS-09 ✅, OPS-12; enviar las cartas a CONAF y SENAPRED (OFI-03 🟨 · PR #250 mergeado, falta enviarla; OFI-04); la licencia ya está elegida (SEC-14 ✅ · PR #143) |
| **26 oct al 1 de nov** | Que no se silencie un incendio real; avisos más útiles | FIX-03 ✅ (PR #13), FIX-04 ✅ (PR #15), FIX-09 ✅ (PR #13), FIX-12 ✅, FIX-13 ✅ y FIX-14 ✅ (PR #14), DET-05 🟨 (script en `main`, PR #80; falta la máscara), ALR-01 (si se crea el bot), ALR-02 ✅ (PR #42) |
| **2 al 8 de nov** | Privacidad y ley de datos | INV-01 ✅, SEC-01 a SEC-05 ✅, SEC-08 ✅, FIX-21 ✅, FIX-22 ✅, CONT-05 ✅ (PR #145) |
| **9 al 15 de nov** | Aguantar picos de tráfico | OPS-03 ✅, OPS-04 ✅, OPS-05 ✅, OPS-08 ✅, OPS-10 ✅ (PR #19); UX-03 ✅ (PR #57) |
| **16 al 22 de nov** | Personas reales | UX-01 (pruebas con usuarios), INV-09 ✅, FIX-08 ✅ (PR #227), FIX-05 ✅, FIX-06 ✅, FIX-07 ✅ (PR #76), FIX-18 ✅, UX-09 ✅, ALR-13 ✅ (PR #90) |
| **23 al 29 de nov** | Riesgo explicado y avisos preventivos | RISK-08 ✅ (PR #46), RISK-14 ✅ (PR #126), ALR-04 ✅ (PR #214), ALR-14 ✅ (PR #149), FIX-25 ✅ (PR #88), RISK-02 ✅ (capa de lluvia en el mapa, PR #142) |
| **30 nov al 14 de dic** | Validación y cierre antes de la temporada | QA-01 ✅, QA-02 ✅, DET-13 ✅, SEC-13 ✅ (PR #133), OFI-05 ⬜ (PR #277 mergeado; la lista sigue vacía); despliegue estable + diagnóstico |
| **15 dic a 28 feb** | **Operar** (congelamiento) | ALR-09 semanal, QA-03 🟨 (script en `main`, PRs #74 y #139; PR #290 mergeado publica la medida; validación con la temporada en curso), RISK-13 ✅ (PR #138), solo arreglos; registrar todo lo aprendido |
| **Mar a may 2027** | Fase 2 restante y Fase 3 | RISK-03 a RISK-07 (RISK-06 ✅ · PR #132; RISK-04 🟨 · PR #264; RISK-05 ✅ · PR #220), AGUA-01 a AGUA-06 (AGUA-03 🟨 · PR #186; AGUA-05 🟨 · PRs #257 y #310), OFI-12 🟨 (PR #289 mergeado; QA-05 ya está ✅, PR #112) |

---

## 21. Fuentes consultadas para este documento

**Ley de datos personales**
- [Diario Constitucional: la Ley 21.719 entra en vigor el 1 de diciembre](https://www.diarioconstitucional.cl/2026/06/12/la-ley-21-719-entra-en-vigor-el-1-de-diciembre-y-expone-vacios-en-regulacion-de-pequenas-empresas/)
- [Academia Judicial: Ley 21.719](https://academiajudicial.cl/recursos/actualizaciones-normativas/ley-21-719-que-regula-la-proteccion-y-el-tratamiento-de-los-datos-personales-y-crea-la-agencia-de-proteccion-de-datos-personales/)
- [IAPP: puntos pendientes antes de la entrada en vigor](https://iapp.org/news/a/protecci-n-de-datos-personales-puntos-pendientes-antes-de-la-entrada-en-vigor-de-la-reforma-en-chile)
- [Garrigues: el Ejecutivo concede un año adicional de adaptación](https://www.garrigues.com/es_ES/noticia/chile-ejecutivo-refuerza-futura-agencia-proteccion-datos-concede-ano-adicional-adaptacion.md)
- [Minsegpres: primer informe de la Comisión de Implementación](https://www.minsegpres.gob.cl/wp-content/uploads/2025/08/Primer-informe-Comision-de-Implementacion-para-la-ley-de-proteccion-de-datos-personales-.pdf)

**Institucionalidad forestal**
- [Ley 21.744 que crea el Servicio Nacional Forestal](https://www.jdf.cl/en/ley-21-744-crea-el-servicio-nacional-forestal-y-modifica-la-ley-general-de-urbanismo-y-construcciones)
- [Radio Agricultura: CONAF presenta su modernización hacia SERNAFOR (agosto de 2026)](https://www.radioagricultura.cl/noticias/nacional/conaf-presenta-modernizacion-hacia-sernafor-en-reunion-forestal-de-apec-2026_20260811/)
- [Terram: Balance Ambiental 2025, forestal](https://www.terram.cl/descargar/Balance-Ambiental-2025-Forestal.pdf)

**Satélites**
- [NASA LAADS: transición de MODIS a VIIRS](https://ladsweb.modaps.eosdis.nasa.gov/learn/modis-to-viirs-transition/)
- [NASA Earthdata: aviso de transición de MODIS a VIIRS](https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs)
- [Copernicus CAMS: MODIS a la deriva y el sistema global de asimilación de incendios](https://atmosphere.copernicus.eu/drifting-away-modis-cams-global-fire-assimilation-system)

**Fuentes de datos ya documentadas** en [`FUENTES.md`](FUENTES.md): CONAF Botón Rojo e incendios (GEPRIF), DMC CAP, NOAA GOES, NASA FIRMS, Open-Meteo y las exploraciones de octubre de 2026.

**Hallazgos de código:** revisión directa de `backend/services.py`, `backend/incidents.py`, `backend/alerts.py`, `backend/providers/conaf.py`, `backend/routes/*.py`, `backend/cases.py`, `backend/db.py`, `Dockerfile`, `deploy/cloudflare/src/index.ts` y `web/js/views/*.js` el 18 de octubre de 2026.

---

## 22. Cómo mantener este archivo

- **La regla:** quien implementa un ítem marca su estado **en el mismo PR** — ✅ con la referencia (`PR #n` o `archivo:línea`), 🟨 si quedó a medias o hay un PR abierto que lo continúa, ⏸ si depende de una decisión de la persona dueña. Este archivo se desactualizó porque los estados se marcaban «después», y ese después nunca llegaba.
- Nunca marcar ✅ sin una referencia verificable. Si no se encuentra evidencia en `CHANGELOG.md`, `git log` ni `gh pr list`, la fila queda ⬜.
- Antes de tomar un ítem, verificar igual en `CHANGELOG.md` y `gh pr list -R falopass/brasas`: el estado puede haber cambiado desde la última sincronización.
- Si un ítem aparece duplicado o contradictorio, anotarlo en el PR que lo descubre; no borrarlo.
