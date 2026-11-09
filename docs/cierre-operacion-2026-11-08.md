# Cierre de operación — riesgo viejo y latencia de /api/status (8-nov-2026)

Investigación de los issues #798 («[monitoreo] riesgo viejo») y #802
(«[latencia] /api/status con p95 3072 ms»), con el estado de producción medido
por sonda GET a `https://brasa-chile.ddiegosebastianbb.workers.dev/api/status?history=3`
el 2026-11-09T00:56 UTC.

## #798 — «Sin cupo diario de Open-Meteo para el 30-30-30» (bug vigente, corregido)

**Síntoma.** `risk_computed_at` envejece más de 6 h y `last_cycle.risk_error`
repite «Sin cupo diario de Open-Meteo para el 30-30-30.» en cada ciclo.

**Mecanismo.** El cupo propio de Open-Meteo son 9.000 ubicaciones por día de
Chile (`weather.DAILY_LOCATIONS_CAP`, se reinicia a medianoche de
America/Santiago). `compute_risk` solo corre si quedan `345 comunas + 500 de
reserva`; el 8-nov el acumulado `open_meteo.scheduled.total` llegó a **8.338**
(libre: 162) y cada pasada de riesgo posterior falló.

Reparto del día (según `open_meteo.scheduled.tasks`):

| tarea | ubicaciones | ¿presupuestada en `risk_points_per_pass`? |
| --- | ---: | --- |
| `risk` (6 × 550) | 3.300 | sí — el plan son 8 pasadas |
| `fwi` (temporada jun→nov) | 2.416 | sí |
| `windgrid` (3 × 380) | 1.140 | **no** |
| `pendiente` (relieve 3×3, FUEGO-45) | 792 | **no** |
| `rain` (anomalía) | 690 | sí |

**Causa raíz.** Dos consumidores que «ceden cupo» no dejaban nada para las
pasadas de riesgo que faltaban:

1. `windgrid_cycle` llamaba a `cabe_en_cupo(n, cap=9000, gastado)`: podía gastar
   hasta el tope, sin descontar ni la reserva de 500 (que su propio cálculo de
   `libre` sí restaba, pero nunca se usaba en el guarda) ni el plan del 30-30-30.
   El test `test_cupo_al_borde` ya documentaba que el ciclo descuenta la reserva
   «antes de llamar» — el código nunca lo hizo. En producción el refresco de las
   19:21 UTC (380 ubicaciones) se llevó justo el cupo que la pasada de riesgo de
   las 21:51 UTC necesitaba.
2. El relieve de los avisos (`pendiente`, 9 ubicaciones por incidente nuevo)
   solo respetaba la reserva plana de 500, así que en días de mucha actividad
   comía el margen del riesgo.

**Corrección.** `Services._om_plan_pending()` reserva lo pendiente de las tres
tareas presupuestadas: 30-30-30, FWI y lluvia. `open_meteo_daily_costs` comparte
los costos con `risk_points_per_pass`, evitando dos fórmulas diferentes. Las
pasadas se redondean hacia arriba también para intervalos como 200 minutos.
La grilla y el relieve solo piden si `gastado + necesarias +
OPEN_METEO_RESERVE + pendiente_plan ≤ cap`.

La primera revisión independiente detectó que reservar solo el riesgo dejaba
gastar el cupo de FWI y lluvia antes de su primera tanda. Se corrigió antes del
merge y se dejó una regresión para febrero, cuando casi no hay holgura, con
intervalos de 180 y 200 minutos. La reserva es conservadora por día completo:
tras un arranque tardío puede aplazar tareas opcionales hasta medianoche.
No compensa gastos extraordinarios de reintentos ni configuraciones cuyo
mínimo de una ubicación por comuna ya supera el cupo diario.

**Bug secundario corregido.** `.github/scripts/monitoreo.py` verificaba
`last_cycle.risk_error is True`, pero el campo llega como texto de la excepción:
el veredicto «riesgo sin recalcular» era código muerto y solo alertaba la regla
de 6 h. Ahora cualquier `risk_error` no vacío alerta, como dice el docstring.
Efecto: la primera pasada fallida abre el issue en vez de esperar 6 h (los
issues se deduplican por etiqueta, no hay ruido extra).

## #802 — p95 3072 ms en /api/status (causa aún por confirmar)

**Hechos.** n=3, p50 82 ms: una sola muestra de ~3 s rompe el presupuesto.
La ruta tiene caché de borde de 30 s con stale-while-revalidate. La muestra
lenta pudo ser un `miss` que viajó al contenedor durante el ciclo de ingesta
(`docs/LATENCIA.md` anticipa esa contienda), pero la corrida original no
registró cabeceras por muestra. Ese origen es una hipótesis: estos tres
pedidos no permiten confirmar ni descartar una regresión del endpoint.

**Factor externo.** El workflow corre programado a las 13:07 UTC (10:07 en
Chile, lejos del boundary del cron) pero GitHub lo disparó con 5-7 h de atraso
todas las corridas recientes (11-06 19:55, 11-07 17:59, 11-08 18:19 UTC): la
medición cayó en horario de uso real y contienda, que es justo lo que la hora
elegida evitaba. Esto no se puede controlar desde el script.

**Mejora (observabilidad).** `medir_latencia.py` ahora registra el header
`X-Brasa-Cache` de cada muestra y la tabla del issue trae una columna `borde`
(`hit,hit,miss`): el próximo p95 malo dice solo si fue un viaje al contenedor
o latencia real en régimen. Umbrales intactos.

## 500 intermitentes (/api/alerts, /api/priority-comunas)

Ambas rutas son lecturas locales (SQLite / un JSON) sin Open-Meteo. La
contienda del contenedor es una hipótesis, pero sin trazas de esos 500 no
puede atribuirse su causa ni descartarse un fallo de las rutas. No se cambian
estas rutas sin evidencia causal.

## Otros hallazgos descartados como bug

- `open_meteo.scheduled.date` atrasada un día UTC: es el día de Chile
  (America/Santiago), correcto.
- `desfase` marca VIIRS_NOAA20_NRT con ~6 h: puede corresponder a la cadencia
  orbital y a la ausencia de focos nuevos. La ingesta registra corridas exitosas;
  eso no demuestra que el satélite haya observado focos más recientes. Sin
  evidencia para cambiar sus umbrales.
- `open_meteo.calls`/`since` en cero o nulos: el contador en memoria se pierde
  cuando el contenedor se suspende; el que manda es `scheduled`. Documentado.
- Consumidores no protegidos que quedan: llamadas en el camino de la persona
  (`/api/weather`, riesgo puntual, relieve por comuna), pequeñas y con caché;
  salen de la reserva de 500. FWI y lluvia van dentro del plan y no necesitan
  guarda propia mientras gasten lo presupuestado.

## Validación pendiente del cierre

- Cerrar #798 cuando producción muestre `risk_computed_at` fresco y
  `open_meteo.scheduled` completo tras el despliegue.
- Volver a medir #802 conservando el presupuesto de 2500 ms. Un `miss` puede
  explicar el recorrido del pedido, pero no justifica superar el presupuesto.
  Si vuelve a fallar, documentar sus muestras y mantener abierto el seguimiento.
- Si los atrasos de `schedule` de GitHub se vuelven normales, evaluar correr la
  medición dos veces al día o aceptar el ruido en el issue.
