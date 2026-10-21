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

## Qué tan rápido llega BRASA: tres casos con barrido GOES

Medida de adelanto de la agrupación (QA-02/QA-03), distinta de la calibración del riesgo de arriba:
al reproducir los tres casos GOES versionados —Viña del Mar 2024, Ñuble-Biobío-Araucanía 2023 y
Penco-Lirquén 2026— con la regla de agrupación vigente, de los 408 incidentes resultantes, 298
llegaron a «posible» en una mediana de **20 min** desde su primera detección satelital; el
más lento tardó **500 min**. Medido el 21 de octubre de 2026. La cobertura de la medida
—110 incidentes nunca alcanzaron «posible» y no entran en la mediana ni en el peor caso—
está declarada en `web/data/calibracion.json` (`coverage`), junto al detalle por caso e
incidente y la fecha exacta; es lo que muestra la vista Calidad.

Los datos de los casos (`web/data/cases/*.goes.json`) son detecciones NOAA GOES-16 y GOES-19 FDC
de dominio público (AWS Open Data). Para reproducirlos, sin red y sobre una base desechable:

```bash
python scripts/local/medir_adelanto.py todos              # reescribe web/data/calibracion.json
python scripts/local/medir_adelanto.py vina-del-mar-2024  # un solo caso
python scripts/replay_case.py vina-del-mar-2024           # la tabla completa, sin escribir nada
```

Qué no mide:

- **Son tres casos, no una tasa.** Una mediana sobre 298 incidentes de tres episodios no dice
  cuánto tardará el próximo; el número depende de la cadencia del barrido (~10 min en GOES), de la
  nubosidad y de la evidencia que exija la regla en cada foco.
- **No todo incidente llega a «posible».** De los 408 agrupados, 110 quedaron fuera de la medida
  —casi todos focos chicos del episodio 2023 (la mediana de observaciones de ese grupo es 1)—;
  `coverage.n_sin_posible` existe para que la mediana no esconda ese denominador.
- **«Posible» es criterio de BRASA, no de CONAF.** Mide cuándo la agrupación automática junta
  suficiente evidencia para abrir seguimiento, no cuándo la autoridad confirma el incendio ni
  cuándo alguien recibe un aviso.
- **Es retrospectivo.** La reproducción corre sin la latencia real de la ingesta (el producto FDC
  llega con ~10–20 min de retraso propio): en vivo hay que sumar ese retraso a estos minutos.

---

# Falsas alarmas por región (DET-08)

`scripts/validar_deteccion.py` resume además, por región del territorio BCN, cuántos incidentes
abiertos («anomalía»/«posible») quedaron sin un incendio de CONAF a ≤ 5 km en ±24 h. Es un **proxy**
de falsa alarma: también entran quemas autorizadas, calor industrial (minería, plantas solares) e
incendios que CONAF aún no informa — no es una condena. La región se obtiene ubicando el punto del
incidente en las comunas BCN; lo que cae fuera de toda comuna chilena (mar, altiplano fuera del país)
queda en «sin región».

**No cambia umbrales.** Mide y propone; mover un umbral o una máscara se decide aparte en el backlog
(DET-08, apoyado en la máscara de fuentes persistentes de DET-05), con este informe como evidencia.

## Cómo correrlo

Sobre una copia del `work.db` de producción (respaldo horario en R2) o del local:

```bash
python scripts/validar_deteccion.py --db work.db
python scripts/validar_deteccion.py --db work.db --json validacion.json
```

La tabla «Candidatos por región» sale siempre, en el texto y en el JSON (`candidatos_por_region`).
Sin incidentes abiertos informa «sin datos»: no inventa ceros.

## Medición del 2026-10-19

Como no había respaldo local a mano, esta corrida se hizo sobre un `work.db` reconstruido con dos GET
a la API pública de producción (`/api/incidents?hours=336&include_fixed=1` y
`/api/official-fires?hours=336`, `data_as_of` 2026-10-19T23:10Z) y el mismo comando de arriba.
Limitaciones de esta fuente: cubre solo los últimos **14 días** (el tope de la API), es pretemporada,
y la ancla de CONAF fue `f_inicio` porque la API no expone `f_deteccion`.

| Región | Abiertos | Sin CONAF cerca | % | Comunas con más casos |
|---|---:|---:|---:|---|
| sin región | 75 | 75 | 100% | — |
| Atacama | 15 | 15 | 100% | Copiapó (6), Diego de Almagro (4), Tierra Amarilla (2) |
| Antofagasta | 5 | 5 | 100% | Antofagasta (2), Taltal (2), Calama (1) |
| Aysén | 5 | 5 | 100% | Lago Verde (4), Cochrane (1) |
| Tarapacá | 3 | 3 | 100% | Pozo Almonte (2), Colchane (1) |
| Arica y Parinacota | 1 | 1 | 100% | General Lagos (1) |
| Biobío | 1 | 1 | 100% | Los Angeles (1) |
| Coquimbo | 1 | 1 | 100% | La Higuera (1) |
| Los Lagos | 1 | 1 | 100% | Puerto Varas (1) |
| Magallanes | 1 | 1 | 100% | Porvenir (1) |
| Maule | 1 | 1 | 100% | Teno (1) |
| Metropolitana | 1 | 1 | 100% | La Florida (1) |

Lectura:

- 110 incidentes abiertos y los 110 quedaron sin CONAF cerca: en estos 14 días ninguno de los 40
  incendios informados por CONAF tuvo un incidente a ≤ 5 km en ±24 h (el más próximo quedó a 10,8 km).
  El 100% es en parte estructural: un incidente que sí calza con CONAF pasa a «reportado»/«confirmado»
  y sale del denominador; la tabla dice **dónde** se concentran los que no calzaron, no qué fracción
  de todas las detecciones sobra.
- «sin región» domina con 75 de 110 (68%): 68 de esos 75 están al norte de los 32°S — mar frente al
  desierto y altiplano fuera de Chile que la ingesta recoge dentro del área de GOES.
- De los 35 en comunas chilenas, 25 (71%) están en la macrozona norte (Arica y Parinacota a Coquimbo);
  Atacama sola junta 15, con Copiapó y Diego de Almagro a la cabeza (zona de minería y plantas
  solares). Ninguno de los 110 es fuente fija ya marcada.
- El denominador es chico: fuera del norte, cada región tiene entre 1 y 5 casos.

## Qué no mide

- **No es una condena:** quemas autorizadas, calor industrial y focos que CONAF aún no informa
  también cuentan como candidatos.
- **Ventana de 14 días en pretemporada:** una temporada completa puede dar otra distribución; este
  número hay que re-correrlo con el `work.db` acumulado en plena temporada.
- **El incidente es un punto:** se ubica por su centroide, no por su huella; uno que cruza una frontera
  comunal cuenta solo en la comuna del centroide.

## Recomendación provisional para el norte

Los números apuntan a una **máscara regional**, no a un umbral: el exceso es geográfico (altiplano
fuera del país, mar frente al desierto y la zona minera de Atacama), no de intensidad ni de horario.
El camino razonable es completar la máscara de fuentes persistentes de DET-05 —que ya filtraría
celdas con calor repetido— y evaluar si además conviene recortar el área de ingesta fuera de Chile.
Esto es provisional: la ventana es de 14 días y en pretemporada, así que antes de mover cualquier
cosa hay que re-correr el comando con el `work.db` de plena temporada (idealmente enero-febrero).
