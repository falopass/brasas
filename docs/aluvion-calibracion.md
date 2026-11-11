# Calibración del aviso de aluvión post-incendio (AGUA-04)

Este documento fija el criterio con que BRASA avisa a un lugar guardado de «lluvia intensa sobre zona quemada», y
cómo se eligió. Lo calculó `scripts/calibrar_aluvion.py` el 11-nov-2026. Los resultados completos, con cada
combinación de umbrales, el relieve de cada incendio y las ventanas del evento de control, están en
[`aluvion-calibracion/resultados-2026-11-09.json`](aluvion-calibracion/resultados-2026-11-09.json).

## Criterio

El aviso sale cuando se cumplen las cuatro condiciones a la vez:

| Condición | Umbral | Dato |
|---|---|---|
| Hay suelo quemado cerca | cicatriz a ≤ 5 km en los últimos **365 días** | `scars.cicatriz_cerca` (huella satelital guardada o incendio de CONAF de ≥ 10 ha) |
| El terreno es ladera | pendiente de ladera **≥ 8°** | gradiente de Horn de una grilla 3×3 con paso de 1 km (~2×2 km) sobre Copernicus GLO-90 |
| Llueve fuerte | **≥ 10 mm en 3 h** en la peor ventana del pronóstico | Open-Meteo, pronóstico horario de las próximas 48 h en la celda de 0,1° |
| Llueve en líquido sobre la ladera | isoterma 0 °C **≥ cota máxima** de las 9 muestras (sin dato de isoterma, se da por cumplida) | `freezing_level_height` de Open-Meteo |

El aviso es de nivel «aviso», nunca «urgente». Siempre dice que es una estimación de BRASA y remite a SENAPRED. Un
mismo lugar no recibe dos avisos de aluvión en menos de **36 horas**.

El campo `slope_max_deg` del contrato de `/api/climate/lluvia` conserva ese nombre, pero no es el máximo entre puntos:
es un solo gradiente de Horn de toda la grilla de 2×2 km. `elev_max_m` sí es la mayor de las 9 cotas.

## Datos usados

- **Ventana:** 180 días locales, del 14-may al 9-nov-2026 (todo el invierno y el inicio de la primavera de El Niño 2026).
  Se pide a la fuente un día UTC más, para no cortar las últimas horas del 9-nov en Chile.
- **Cicatrices:** 362 incendios de ≥ 10 ha de la temporada 2025-26, del
  [reporte público de CONAF (GEPRIF)](https://github.com/deigeprif/public) (`incendios_totales_25_26.csv`), en
  243 celdas de 0,1°. Cada cicatriz cuenta solo durante los 365 días posteriores al inicio del incendio, como en
  producción. Se usaron los incendios de CONAF porque la huella satelital de BRASA solo se guardaba 45 días hasta
  el PR #824. Ese PR la deja en 400 días y suma estos mismos incendios de CONAF como cicatriz.
- **Lluvia e isoterma:** el archivo del pronóstico horario de Open-Meteo
  ([Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api)), el mismo tipo de producto que BRASA
  lee en vivo, no una estación. Para el evento de control se suman los pronósticos emitidos 1 y 2 días antes
  ([Previous Runs](https://open-meteo.com/en/docs/previous-runs-api)).
- **Relieve:** Copernicus DEM GLO-90 vía la [API de elevación de Open-Meteo](https://open-meteo.com/en/docs/elevation-api).
- **Avisos simulados:** se recorren en orden las ventanas de 3 h que cumplen cada combinación (32.130 ventanas de
  ≥ 8 mm dentro de la vida de alguna cicatriz) y se cuenta un aviso por ventana, salvo que el mismo lugar haya recibido
  otro en las 36 h anteriores. Es la misma pausa que usa producción.

## El evento de control: Quebrada Honda, 8-oct-2026

Es el único aluvión post-incendio documentado dentro de la ventana. La fuente es el análisis del CR2
([«El aluvión de San Carlos de Apoquindo del 8 de octubre de 2026»](https://www.cr2.cl/el-aluvion-de-san-carlos-de-apoquindo-del-8-de-octubre-de-2026-el-ultimo-eslabon-en-una-larga-cadena/)):
la cuenca de quebrada Honda (10,6 km², 929-2355 m) se quemó casi por completo el 29-dic-2025. La lluvia intensa cayó
entre las 15:00 y las 19:00, y el aluvión bajó cerca de las 17:00 (hora de Chile).

| Dato | Medido (CR2 / DGA) | Lo que habría visto BRASA |
|---|---|---|
| Incendio | 29-dic-2025 | «Plaza Sur», CONAF, 907,69 ha, 283 días antes |
| Lluvia | 31,6 mm entre 15:00 y 19:00 en la estación DGA Río Molina (a ~7 km), máximo de 10,9 mm en 30 min | Pronóstico emitido **1 día antes**: 12,1 mm en 3 h desde las 18:00 del 8-oct. Emitido 2 días antes: menos de 8 mm |
| Isoterma 0 °C | ~2.800 m (observatorio Cerro Tres Puntas) | Sin dato en el pronóstico del día anterior. En el archivo, 2.540-2.840 m durante la tormenta |
| Relieve | la cuenca sube de 929 a 2.355 m | 9,7° de ladera a 1 km y cota máxima de 1.375 m en el entorno del punto de CONAF (6,6° en el punto mismo, que está en el borde urbano) |

**El aviso habría llegado a tiempo, pero con poco margen.** BRASA lee las próximas 48 h de pronóstico. El pronóstico
emitido el 7-oct ya ponía 12,1 mm en 3 h para la tarde del 8-oct, sobre la ladera con cicatriz. Con el criterio de
10 mm, el aviso habría salido el día 7, antes del aluvión. Con 48 h de anticipación, el pronóstico todavía no lo veía.

**El modelo puso el pico tarde.** En el archivo del pronóstico, las ventanas que terminan antes de las 17:00 suman
como máximo 9,2 mm. El pico del modelo (12,6 mm) empieza a las 19:00, cuando en la estación la lluvia ya terminaba.
Por eso el acierto no se puede leer en la lluvia «del día»: se lee en el pronóstico previo.

Tres lecciones de este evento cambiaron el diseño:

1. **La ventana de 180 días no alcanza.** El aluvión llegó 283 días después del incendio, así que la cicatriz cuenta
   durante 365 días.
2. **La pendiente del punto engaña.** El punto de inicio del incendio y las casas quedan al pie de la ladera. Por eso
   la pendiente se mide a escala de ladera (1 km), no en el punto.
3. **El modelo subestima los núcleos convectivos y los atrasa.** Se midieron 31,6 mm en 4 h. El pronóstico previo
   daba 12,1 mm en 3 h y unas horas más tarde. Un umbral de 12 mm habría pasado por 0,1 mm; uno más alto habría perdido
   el único aluvión real.

## Combinaciones evaluadas (180 días, 362 cicatrices, pausa de 36 h)

La mediana y el máximo son de avisos por cicatriz con aviso. «Día del evento» indica si alguna ventana del 8-oct en
el archivo cumplía la combinación; la oportunidad real del aviso se mide con el pronóstico previo (sección anterior).

| Lluvia en 3 h | Ladera a 1 km | Isoterma sobre la cota | Cicatrices con aviso | Avisos | Mediana | Máximo | Día del evento |
|---|---|---|---|---|---|---|---|
| ≥ 10 mm | — | sí | 358 | 3.747 | 10 | 24 | sí |
| ≥ 10 mm | ≥ 8° | no | 23 | 286 | 14 | 22 | sí |
| **≥ 10 mm** | **≥ 8°** | **sí** | **23** | **252** | **10** | **21** | **sí** |
| ≥ 10 mm | ≥ 12° | sí | 10 | 129 | 15 | 20 | no |
| ≥ 12 mm | ≥ 8° | sí | 23 | 184 | 7 | 14 | sí |
| ≥ 15 mm | ≥ 8° | sí | 23 | 122 | 4 | 13 | no |
| ≥ 15 mm | — | sí | 356 | 1.463 | 4 | 14 | no |
| ≥ 20 mm | ≥ 8° | sí | 15 | 41 | 3 | 6 | no |

Lectura:

- **Sin la condición de ladera**, casi todas las cicatrices (358 de 362) habrían avisado, en un invierno récord de
  lluvia. La ladera es el filtro que más discrimina: solo 25 de 362 cicatrices tienen ≥ 8° a escala de 1 km (la
  mediana es de 1,2°), porque la mayoría de los incendios de CONAF ocurren en terreno plano u ondulado.
- **La isoterma** quita un 12 % de los avisos (de 286 a 252): son los casos en que en la ladera nieva en vez de llover.
- **Se eligen 10 mm y no 12 mm**, aunque 12 mm avisa menos (mediana de 7 avisos contra 10), porque con 12 mm el
  pronóstico previo del único aluvión real habría pasado por 0,1 mm, y ese pronóstico ya subestimaba lo medido a
  menos de la mitad. En un aviso de riesgo para la vida se prefiere avisar de más.
- **El costo es real.** Una cicatriz en ladera recibe una mediana de 10 avisos en 180 días de El Niño y hasta 21.
  Es la carga a revisar cuando exista un catastro de eventos (abajo).

## Límites

- **Un solo positivo.** Con un aluvión documentado se puede comprobar que el criterio lo habría marcado a tiempo,
  pero no se puede medir la tasa de falsas alarmas: no hay un catastro de qué cicatrices *no* tuvieron aluvión. Los
  252 avisos se cuentan como avisos, no como errores. El catastro de SERNAGEOMIN (AGUA-08) es el paso que falta para
  medir la precisión y, quizás, subir el umbral.
- **Invierno atípico.** El Niño 2026 dejó lluvias récord (CR2): en un año normal debería haber menos avisos.
- **Archivo frente a pronóstico en vivo.** La tabla usa el pronóstico archivado, que se acerca al de pocas horas. Solo
  el evento de control se contrastó con los pronósticos emitidos 1 y 2 días antes.
- **Avisos simulados.** La simulación cuenta un aviso por la hora de inicio de la ventana. Producción evalúa cada hora
  la peor ventana de las próximas 48 h, así que puede avisar antes que la ventana misma.
- **Disco equivalente.** Un incendio de CONAF es un punto (el inicio) y una superficie. BRASA lo modela como un disco
  de área equivalente, no como el perímetro real.
- **Isoterma contra cota del entorno.** Se compara con la cota máxima de 9 muestras en ~2×2 km, no con la cota de
  toda la cuenca.

## Reproducir

```bash
python scripts/calibrar_aluvion.py --fin 2026-11-09 --out out/calib.json
```

Usa unas 300 llamadas al archivo de Open-Meteo, una a Previous Runs y unas 40 a la API de elevación. Guarda caché en
`out/cache` y reanuda si se corta. El cupo horario de Open-Meteo es por IP: córrelo en una máquina remota.
