# Cambios

Formato: lo que nota una persona primero; lo técnico, después. Fechas de despliegue en producción.

## 25 de octubre de 2026

**Para las personas**
- **Panel sin línea fija ni contorno raro:** se fue el enlace permanente a «Tiempos de respuesta oficiales de CONAF» bajo el panel (vuelve al final de la ficha del incendio y del Mapa), y los títulos ya no quedan con un borde rojo al cambiar de vista; con teclado el foco sigue marcándose igual (UX-73, UX-74).
- **Prepárate avisa qué hacer si no carga:** el bloque «Comunas prioritarias» muestra los teléfonos de emergencia y «Reintentar» en vez de desaparecer (UX-77).
- **«Cómo llegar» al punto de encuentro:** en la hoja del plan familiar, el punto de encuentro escrito lleva un enlace que abre la app de mapas del teléfono con ese destino, junto al recordatorio de seguir las rutas que indique la autoridad (UX-78).

## 24 de octubre de 2026

**Para las personas**
- **«Medido en la estación…» en Mi zona:** junto al pronóstico, la lectura real (temperatura, humedad, viento) de la estación automática de la DMC más cercana, con su nombre, distancia y hora. Solo aparece si hay una estación a menos de 25 km con dato de las últimas 3 horas; si no, no se muestra nada. (OFI-33)
- **«Aire medido…» en Mi zona:** el MP2,5 que mide de verdad la estación SINCA más cercana (hasta 60 km, de las últimas 6 horas), con su ICAP y su estado, marcado como dato preliminar del MMA. Al lado del pronóstico de humo, no en su lugar. (OFI-10)
- **«La autoridad informa» en Mi zona:** las alertas oficiales vigentes de SENAPRED que nombran tu comuna o tu región, con su texto exacto, su fecha y su enlace. BRASA no emite alertas: si SENAPRED no te nombra, el bloque no aparece y el enlace oficial queda siempre. (OFI-04)
- **Campamentos por comuna (dato nuevo):** `web/data/campamentos.json` agrega el Catastro Nacional de Campamentos del MINVU — cuántos campamentos y hogares catastrados tiene cada comuna, sin puntos ni nombres— para que la exposición al riesgo cuente también a quienes viven en asentamientos. Aún sin superficie en la interfaz. (OFI-25)

**Técnico**
- `GET /api/climate/station?lat=&lon=` sirve la estación EMA más cercana; la red completa de la DMC se baja una vez y se comparte en caché 10 min. Credenciales del portal (`DMC_USUARIO`/`DMC_TOKEN`) como secretos del Worker, reenviadas al contenedor.
- `GET /api/climate/air?lat=&lon=` sirve el MP2,5 de la estación SINCA más cercana; el listado de la red (JSON público sin clave) se comparte en caché 30 min; la hora se interpreta en hora de Chile. (OFI-10)
- `GET /api/alerts/official?lat=&lon=` sirve las alertas vigentes de SENAPRED que nombran el lugar: consulta `alertasByDate` del AppSync del portal público con las credenciales anónimas del identity pool (firma SigV4), calce por comuna/región en el título oficial, caché de 10 min. (OFI-04)
- `scripts/local/build_campamentos.py` genera el agregado por comuna del MINVU (1.250 campamentos vigentes, 75.966 hogares, 185 comunas); registrado en la caducidad de datos versionados y en la sonda semanal. (OFI-25)

## Integración del backlog — 23 y 24 de octubre de 2026

Cada cambio se desplegó al mergearse; el detalle por tanda está en `docs/backlog/PLAN_INTEGRACION.md` («Resultado»).

**Para las personas**
- **Avisos que dicen qué hacer y no cansan:** cada aviso dice hace cuánto se detectó y cierra con un paso concreto; hay topes por lugar (un urgente que escala siempre sale) y los avisos no urgentes esperan a las 07:00 si llegan de noche (ALR-26, ALR-20, ALR-19).
- **Mi zona explica el día:** por qué es peligroso, qué cambió desde tu última visita, cómo viene la semana, la temporada de tu comuna con cifras de CONAF, qué hacer hoy y la lluvia sobre zonas quemadas (MZ-01, MZ-03, MZ-05, RISK-22, UX-62, UX-64, TEMP-03, AGUA-09).
- **Enlace de familia:** cómo viene la semana en una frase, «Estoy bien» sin texto libre y calendario de días peligrosos (VEC-01, UX-48, ALR-23).
- **Ficha del incendio:** el escenario estimado en palabras, con la pendiente real del terreno, si el viento empuja el fuego hacia tus lugares y si hubo rayos cerca al inicio (FUEGO-14, FUEGO-17, FUEGO-45, DET-23).
- **Mapa:** viento animado y crédito de OpenStreetMap visible (RISK-07, MAPA-105).
- **Páginas nuevas:** lista de focos en texto (`/focos`) y una página por comuna con el riesgo del día (FOCOS-01, SEO-05).
- **Antes de reportar** se ven los reportes y focos que ya hay cerca, sin demorar el envío (REP-01).
- «¿Qué hago si…?», preguntas frecuentes, Prepárate (mantenimiento y parcela, ¿puedo quemar hoy?), versión liviana, datos abiertos y vista Calidad con más contenido y fuentes (UX-57, UX-61, UX-72, FAQ-01, PREP-03, UX-59, QUEMA-01, MAPA-02, UX-70, DAT-05, AUTO-03, AUTO-11).

**Técnico**
- `/api/diagnostico`, `/api/datos-versionados`, frescura por fuente en `/api/status`, `/api/wind/grid`, `/api/opendata/catalog`, `/api/climate/lluvia`, `/api/climate/quema/{code}`, `/calendar/lugar/{code}.ics`, `/comuna/{slug}` y `/sitemap-comunas.xml` (AUTO-10, AUTO-16, FUEGO-08, RISK-07, DAT-08, AGUA-09, QUEMA-01, ALR-23, SEO-05).
- Workflows de autodiagnóstico de la cara pública y salud diaria del repo; edad del dato en la revisión de fuentes (OPS-27, OPS-28, AUTO-06).
- Máscara regional del norte por celda, vacía hasta calibrarla; guarda de territorio de los datos; `/focos` del bot con incidentes (DET-45, QA-72, ALR-30).

## Sin desplegar

**Para las personas**
- **Número sobre el ícono de la app:** los avisos urgentes que llegan con BRASA cerrada suman un contador sobre el ícono (donde el navegador lo permite); se borra solo al abrir Avisos o al tocar la notificación. (UX-75)
- **Modo ahorro de batería (en Ajustes):** menos animaciones —el viento del mapa queda en flechas fijas— y datos que se actualizan con menos frecuencia; sugiere el tema oscuro sin imponerlo. Con menos del 20 % de batería y sin cargar, BRASA lo sugiere una vez por sesión; nunca se activa solo. Los avisos llegan igual. (UX-76)
- **Las páginas por comuna (`/comuna/…`) ya se ven como BRASA:** antes eran HTML sin estilo; ahora llevan la misma cara oscura de la app — el nivel de riesgo en grande con su color, los datos del día como instrumentos (máxima, humedad, viento, FWI), los enlaces como tarjetas y los teléfonos de emergencia como botones `tel:` grandes que llaman al tocarlos. Siguen sin JS, indexables y livianas (~8 KB).
- **En el celular la leyenda del mapa se repliega en un chip «Leyenda»:** el mapa queda libre al abrir la vista (ya no queda tapado por la tarjeta de colores, que crece con cada capa activa); al tocar el chip se despliega debajo y otro toque la cierra.
- **En el celular, el modo emergencia abre la hoja completa:** cuando un lugar queda «urgente», el panel con qué hacer ocupa casi toda la pantalla; al pulsar «Ver todo» vuelve a la mitad.
- **El mapa solo dibuja focos de Chile:** el satélite GOES observa un rectángulo que incluye Argentina, Bolivia, Perú y mar abierto; desde ahora cada detección se descarta al leerla si no cae en territorio chileno (margen costero de ~2 km, el tamaño de su píxel —el de FIRMS era ~18 km—). Lo mismo ya se hacía con FIRMS. (FUEGO-15)

**Técnico** (ola OPS: picos, límites y despliegue)
- **El monitoreo deja de abrir falsas alarmas de work.db:** `work.db` se respalda una vez por hora, así que `last_cycle.work_backup=false` sin error solo significa que aún no tocaba (los issues #433, #671 y #673 fueron eso). Ahora alerta si ese `false` trae un error «work:» o si `backup.work_updated_at` tiene más de 2,5 h.
- **Frontend sin código muerto:** se quitan cinco funciones exportadas que nadie importaba (`globeOpen`, `isPicking`, `expandSheet`, `debounce`, `isExpert`) y ocho reglas de CSS sin uso (`.px-brasa`, `.px-off`, `.iso-rule`, `.theme-glyph`, `hr.rule`, `.hero-number`, `.icon-btn`, `.place-meta`). Sin cambios de comportamiento.
- **Caché en el borde** (OPS-03): el Worker guarda `/api/observations`, `/api/incidents`, `/api/official-fires`, `/api/risk` y `/api/status` 30-60 s en la Cache API, y sirve respuestas vencidas hasta 10 min mientras refresca en segundo plano. Un pico de visitas al mapa ya no golpea al contenedor. Cada respuesta lleva `X-Brasa-Cache` (`hit`/`stale`/`miss`) para verificarlo.
- **Límite en el borde y Turnstile** (OPS-05): `POST /api/reports` y `POST /api/subscribers` pasan por límites de solicitudes del Worker (10 y 30 por IP por minuto; 429 con `Retry-After`), antes de los límites propios del backend. El formulario de reportes pide un token Turnstile invisible y el backend lo verifica en `siteverify`; sin claves configuradas todo sigue igual (fail-open, cada reporte pasa por moderación). Diego crea las claves en Cloudflare: pasos en `docs/DESPLIEGUE_CLOUDFLARE.md`.
- **Prueba de carga** (OPS-04): `scripts/carga/mapa.js` (k6) simula 500 personas simultáneas en el mapa por 10 min, con rampa y umbral p95 < 2 s y < 1 % de errores. Cómo correrlo, en `scripts/carga/README.md`.
- **Dependencias fijas** (OPS-08): `requirements.lock` generado con `uv pip compile --generate-hashes`; el Dockerfile instala desde el lock con `--require-hashes`. Dependabot semanal para pip, npm y acciones de GitHub (`.github/dependabot.yml`).
- **Simulacro de restauración** (OPS-10): `scripts/simulacro_restauracion.py` baja `db/brasa.db` y `db/work.db.gz` de R2 y verifica integridad SQLite; workflow mensual (día 3) con los mismos secretos del despliegue.
- **Acciones de GitHub al día** (OPS-09): `checkout`, `setup-python` y `setup-node` a v7 en los cuatro workflows, antes de la migración de `ubuntu-latest` a Ubuntu 26 y del cambio forzado de Node 20 a Node 24.
- **Las copias diarias se borran a las 24 horas:** el cron del Worker barre `db/diario/` cada 10 minutos y elimina las que superen un día desde su escritura, de modo que la política de privacidad puede afirmar que los respaldos se conservan hasta 24 horas.
- **Monitoreo de la ingesta** (OPS-01): workflow `monitoreo.yml` cada 15 minutos; sonda GET a `/api/status?history=3` y abre un issue con etiqueta `monitoreo` (sin duplicar mientras haya uno abierto) si `freshness.stale`, si un producto acumula 3 fallos seguidos o si `last_cycle.backup` es `false`. Lógica y veredictos en `.github/scripts/monitoreo.py`.
- **La ficha del incendio ya no salta al inicio** (FIX-05): la actualización automática cada 3 minutos conserva la posición de lectura y el foco, con el mismo `keepPlace` que usa el mapa.
- **La temporada 2025-26 en un dato versionado** (OFI-30): `web/data/temporada-2526.json` resume el CSV oficial de GEPRIF-CONAF en totales por comuna y por región —5 166 incendios, ~79 mil hectáreas— con el mes de mayor superficie y la comuna más afectada. Se regenera con `python scripts/local/build_temporada_2526.py` y es el insumo de la comparación «temporada pasada vs. ahora».

## 0.9.0 — 18 de octubre de 2026

**Para las personas**
- **Privacidad y tus datos:** nueva página **#/privacidad** con la política en dos niveles: qué se guarda (el identificador del dispositivo, lugares, avisos y reportes), para qué, cuánto tiempo, dónde queda todo (Cloudflare y R2: transferencia internacional) y cómo ejercer tus derechos. Se enlaza desde Ajustes y desde el formulario de lugar.
- **Descargar y borrar:** en Ajustes, «Descargar mis datos» baja un JSON con todo lo que BRASA guarda de este dispositivo, y «Borrar todos mis datos» lo elimina todo para siempre —lugares, avisos y suscripciones— tras confirmar.
- **La marca «persona mayor» explica su consentimiento:** el formulario dice que es opcional, que solo adelanta el aviso a «urgente» y que, si compartes el enlace familiar, quien lo abra también la verá; el modal de compartir lo recuerda antes de enviar.
- **Nada queda para siempre:** los avisos se borran a los 12 meses, los reportes sin publicar o descartados a los 90 días y los verificados a los 2 años, con sus fotos.
- **Términos de uso:** `docs/TERMINOS.md` recoge el descargo —BRASA no es una alerta oficial, la autoridad es SENAPRED— y se enlaza desde la página de privacidad.

**Técnico**
- `GET /api/me/export` (acceso y portabilidad) y `DELETE /api/me` (supresión): borra avisos→lugares→suscriptor en una transacción y marca el respaldo; los borrados hijo→padre son explícitos por respaldos antiguos sin `ON DELETE CASCADE`. Ley 21.719 (SEC-02, FIX-22).
- `Services.purge_user_data` (FIX-21) al final del ciclo de ingesta: avisos > 365 días, reportes no verificados o descartados > 90 días y verificados > 730 días. Las fotos se borran del disco y se sobrescriben con cero bytes en R2 (el Worker solo admite GET/PUT). Un fallo se registra y no corta el ciclo.
- Minimización verificada (SEC-04): ni IP ni `User-Agent` llegan a la base; la IP solo vive en el limitador en memoria. Reportes públicos ya redondeaban a ~100 m.
- `docs/PRIVACIDAD_EIPD.md` (SEC-05): datos tratados, riesgos (el «mapa de casas de personas mayores»), medidas, riesgos residuales y responsable.
- Ajustes (SEC-03): sección «Tus datos y privacidad» con exportación a JSON descargable, borrado con confirmación y limpieza de las claves `brasa:*` de `localStorage`.
- `tests/conftest.py` limpia el limitador por IP por cliente: es global al proceso y la suite agotaba el cupo de `/api/subscribers` según el orden.
- `scripts/local/browser_checks.py` recorre también `#/privacidad`.

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
