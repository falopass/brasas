# Comparación de agrupación de detecciones (DET-19, evidencia de DET-09)

`scripts/comparar_agrupacion.py` reinyecta las detecciones GOES de un caso histórico
(`web/data/cases/<id>.goes.json`) dos veces con `scripts/replay_case.py`: una con la regla
vigente (enlace simple, `backend/incidents.py: single_link`) y otra con un DBSCAN
espacio-tiempo incremental implementado dentro del mismo script (`dbscan_linker`,
min_samples=3, eps=`link_km` por par, ventana de 6 h por miembro). Corre sobre bases
desechables `data/comparar-*.db` (ignoradas por git): **nunca toca `data/brasa.db` ni
`data/work.db`** y no cambia la regla por defecto (`LINKER` sigue siendo enlace simple).
Lo garantiza `tests/test_agrupacion_comparada.py`.

## Cómo correrlo

```bash
python scripts/comparar_agrupacion.py <case-id> [--limit N]
```

`--limit N` procesa solo los primeros N barridos. Sin red. Los casos disponibles son los
`*.goes.json` de `web/data/cases/` (los genera `scripts/build_case_goes.py`).

## Qué mide

Por estrategia y por caso: número de incidentes resultantes, detecciones asignadas, tamaño
del mayor incidente, fusiones entre incidentes, mediana de minutos desde la primera
detección hasta el estado «posible» (y cuántos incidentes lo alcanzaron) y tiempo de reloj
del replay. Las fusiones cuentan cuántas veces una detección nueva tocó dos o más
incidentes y los unió: es la señal del defecto del enlace simple, que puede encadenar
incendios distintos en episodios masivos.

## Resultados

Corridas completas (sin `--limit`) el 19-oct-2026, en Windows, con `.venv` del repo:

### nuble-biobio-araucania-2023 (1007 barridos · 43 398 detecciones)

| estrategia             | incidentes | asignadas | mayor | fusiones | min→posible     | reloj   |
|------------------------|-----------:|----------:|------:|---------:|-----------------|--------:|
| enlace simple          |        394 |    43 398 | 7 733 |       78 | 20 min (287)    |  97.0 s |
| dbscan espacio-tiempo  |        440 |    43 398 | 7 702 |      447 | 40 min (278)    | 105.8 s |

Δ dbscan − enlace simple: incidentes +46 · mayor −31 obs · fusiones +369.

### vina-del-mar-2024 (433 barridos · 2 667 detecciones)

| estrategia             | incidentes | asignadas | mayor | fusiones | min→posible     | reloj   |
|------------------------|-----------:|----------:|------:|---------:|-----------------|--------:|
| enlace simple          |          4 |     2 667 | 2 225 |        4 | 15 min (4)      |  22.8 s |
| dbscan espacio-tiempo  |          4 |     2 667 | 2 225 |       12 | 20 min (4)      |  20.5 s |

Δ dbscan − enlace simple: incidentes +0 · mayor +0 obs · fusiones +8.

## Decisión

**Mantener el enlace simple.** DBSCAN no gana en fusiones (al contrario: +369 en el caso
masivo y +8 en Viña, porque la detección nueva cuenta como vecina al evaluar núcleos) y
además empeora la mediana hasta «posible» (de 20 a 40 min en Ñuble-Biobío-Araucanía; de
15 a 20 min en Viña) a igual tiempo de reloj. Sin ventaja medible, no se toca el `LINKER`.

## Estado de DET-09

En `docs/BACKLOG_MAESTRO.md` DET-09 figura «✅ · hecho: comparación DBSCAN vs enlace simple
sin cambiar la regla (gana la simple), PR #204». Este documento (DET-19) publica los
números que faltaban y confirma esa conclusión sobre casos reales; no abre una propuesta
de cambio de agrupación.
