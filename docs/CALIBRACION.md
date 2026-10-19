# Calibración de los niveles de riesgo (RISK-13, QA-20)

`scripts/calibrar_riesgo.py` mide, sobre una copia de `work.db`, cuántos incendios informados por
CONAF (reporte público de GEPRIF, tabla `official_fires`) empezaron en días de cada nivel de riesgo
calculado por BRASA (`risk_daily`): la regla 30-30-30 sola (`level`), la combinada con el FWI
(`level_combined`) y la clase del FWI (`fwi_level`). Los resultados se agrupan por macrozona y se
comparan con la concordancia del Botón Rojo de CONAF (`boton_rojo`, RISK-09).

**No cambia umbrales.** Mide y propone; mover un umbral se decide aparte en el backlog (RISK-13),
con este informe como evidencia.

## Cómo correrlo

Sobre una copia del `work.db` de producción (o del local, si ya acumuló una temporada):

```bash
python scripts/calibrar_riesgo.py --db data/work.db
python scripts/calibrar_riesgo.py --db respaldo/work.db --json calibracion.json
```

El script copia la base a un temporal con la API de respaldo de SQLite y la abre en solo lectura:
nunca escribe en el archivo que le pasas, y sirve aunque el original esté en WAL. Sin red.

## Qué mide

- **Evento comuna-día:** cada incendio se convierte a su comuna (por nombre normalizado, usando el
  territorio BCN de `backend.geo`) y a su día **en hora de Chile** (`started_at` está en UTC).
  Varios incendios el mismo día en la misma comuna cuentan una vez; el informe dice cuántos se
  agruparon.
- **Tasa por nivel:** dentro de cada macrozona, para cada nivel, `días comuna con incendio /
  días comuna con dato`. El **lift** es esa tasa dividida por la tasa base de la macrozona (todos
  los días con dato de esa clase). Un nivel «alto» con lift 5 concentra incendios 5 veces más que
  un día cualquiera de esa macrozona.
- **Concordancia Botón Rojo:** sobre el universo de días comuna con dato de riesgo o de Botón
  Rojo, qué proporción de los días con Botón Rojo tuvo incendio frente a los días sin Botón Rojo.

Macrozonas (por `region_code` del territorio BCN):

| Macrozona | Regiones |
|---|---|
| norte | Arica y Parinacota, Tarapacá, Antofagasta, Atacama, Coquimbo |
| centro | Valparaíso, Metropolitana, O'Higgins, Maule |
| sur | Ñuble, Biobío, La Araucanía, Los Ríos, Los Lagos |
| austral | Aysén, Magallanes |

Si una región no calza con este mapa, sus días se informan en la fila «sin macrozona».

## Qué no mide

- **No es causal ni probabilidad.** El nivel describe condiciones meteorológicas favorables, no la
  probabilidad de que haya un incendio. La mayoría de los incendios los enciende una persona o una
  falla eléctrica: un día «bajo» con incendio no invalida el nivel, y un lift alto solo dice que las
  condiciones acompañan.
- **Superficie preliminar de CONAF:** `official_fires` es el reporte operativo de GEPRIF, no la
  estadística consolidada de fin de temporada; puede faltar o corregirse.
- **Cobertura:** los incendios no informados por CONAF no existen para esta medición; el denominador
  son solo días con `risk_daily` calculado (es decir, desde que la 0.7.0 corre).
- **Un centroide por comuna:** `risk_daily` evalúa el pronóstico en el centro de cada comuna. En
  comunas grandes con cordillera y costa (p. ej. en la Araucanía), el nivel calculado puede no ser el
  del punto donde empezó el incendio.
- **Pocos datos:** una temporada con 30 días de «extremo» en una macrozona da tasas frágiles; mira
  el denominador antes que el lift.

## Cómo leer un resultado que justifique mover un umbral

Síntomas de mala calibración:

- **Incendios concentrados en «bajo» o «moderado»:** si la tasa en «bajo» es comparable a la base
  (lift ≈ 1 o más), el nivel más tranquilo no discrimina; en pastizales de Chile central el FWI
  «bajo» canadiense puede seguir siendo combustible seco → los umbrales del FWI estarían altos.
- **Sin gradiente:** si «alto» y «extremo» tienen tasas parecidas o invertidas, el escalón extra de
  `combine` (dos índices en alto → sube un paso) no está aportando.
- **Botón Rojo con lift < 1:** el pronóstico oficial no estaría separando los días con incendio en
  esa macrozona; conviene revisar la coincidencia día a día antes de culpar al 30-30-30.

Con el informe en mano, el ajuste (mover `T_LIMIT`/`RH_LIMIT`/`WIND_LIMIT`, las clases del FWI o la
regla de `combine`) se propone en el backlog y se evalúa en su propio PR — idealmente re-corriendo
este script antes y después sobre la misma base para comparar.

## Descartes informados

El informe cuenta y lista: incendios sin fecha o sin comuna, comunas de CONAF que no calzan con el
territorio BCN (sección «comuna no reconocida»), eventos en días sin fila de `risk_daily` y días sin
`fwi_level`/`level_combined` (excluidos de la tabla de esa clase).
