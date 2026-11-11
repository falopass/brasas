# Calibración del aviso de aluvión post-incendio (AGUA-04)

Este documento fija el criterio con que BRASA avisa a un lugar guardado de «lluvia intensa sobre zona quemada», y
cómo se eligió. Lo calculó `scripts/calibrar_aluvion.py` el 11-nov-2026. Los resultados completos, con la tabla de
cada combinación de umbrales y el relieve de cada incendio, están en
[`aluvion-calibracion/resultados-2026-11-09.json`](aluvion-calibracion/resultados-2026-11-09.json).

## Criterio

El aviso sale cuando se cumplen las cuatro condiciones a la vez:

| Condición | Umbral | Dato |
|---|---|---|
| Hay suelo quemado cerca | cicatriz a ≤ 5 km en los últimos **365 días** | `scars.cicatriz_cerca` (huella satelital guardada o incendio de CONAF de ≥ 10 ha) |
| El terreno es ladera | pendiente **≥ 8°** a escala de 1 km | grilla 3×3 de Horn con paso de 1 km sobre Copernicus GLO-90 |
| Llueve fuerte | **≥ 10 mm en 3 h** (la peor ventana del pronóstico) | Open-Meteo, pronóstico horario en la celda de 0,1° |
| Llueve en líquido sobre la ladera | isoterma 0 °C **≥ cota máxima** del entorno (sin dato de isoterma, se da por cumplida) | `freezing_level_height` de Open-Meteo |

El aviso es de nivel «aviso», nunca «urgente». Siempre dice que es una estimación de BRASA y remite a SENAPRED.
Se emite una vez por temporal: no se repite en el mismo lugar durante 36 horas.

## Datos usados

- **Ventana:** 180 días, del 14-may al 9-nov-2026 (todo el invierno y el inicio de la primavera de El Niño 2026).
- **Cicatrices:** 362 incendios de ≥ 10 ha de la temporada 2025-26, del
  [reporte público de CONAF (GEPRIF)](https://github.com/deigeprif/public) (`incendios_totales_25_26.csv`), en
  243 celdas de 0,1°. Se usaron los incendios de CONAF porque la huella satelital de BRASA solo se guardaba 45 días
  hasta el PR #824. Ese PR la deja en 400 días y suma estos mismos incendios de CONAF como cicatriz.
- **Lluvia e isoterma:** el archivo del pronóstico horario de Open-Meteo
  ([historical-forecast-api](https://open-meteo.com/en/docs/historical-forecast-api)). Es el mismo tipo de producto que
  BRASA lee en vivo, no una estación. Son 64.935 incendio-días evaluados.
- **Relieve:** Copernicus DEM GLO-90 vía la [API de elevación de Open-Meteo](https://open-meteo.com/en/docs/elevation-api).

## El evento de control: Quebrada Honda, 8-oct-2026

Es el único aluvión post-incendio documentado dentro de la ventana. La fuente es el análisis del CR2
([«El aluvión de San Carlos de Apoquindo del 8 de octubre de 2026»](https://www.cr2.cl/el-aluvion-de-san-carlos-de-apoquindo-del-8-de-octubre-de-2026-el-ultimo-eslabon-en-una-larga-cadena/)):
la cuenca de quebrada Honda (10,6 km², 929-2355 m) se quemó casi por completo el 29-dic-2025.

| Dato | Medido (CR2 / DGA) | Lo que habría visto BRASA |
|---|---|---|
| Incendio | 29-dic-2025 | «Plaza Sur», CONAF, 907,69 ha, 283 días antes |
| Lluvia | 31,6 mm entre 15:00 y 19:00 en la estación DGA Río Molina (a ~7 km), máximo de 10,9 mm en 30 min | 12,6 mm en 3 h (pronóstico de la celda) |
| Isoterma 0 °C | ~2.800 m (observatorio Cerro Tres Puntas) | 2.610 m |
| Relieve | la cuenca sube de 929 a 2.355 m | 9,7° de ladera a 1 km y cota máxima de 1.375 m en el entorno del punto de CONAF (6,6° en el punto mismo, que está en el borde urbano) |

Tres lecciones de este evento cambiaron el diseño:

1. **La ventana de 180 días no alcanza.** El aluvión llegó 283 días después del incendio, así que la cicatriz cuenta
   durante 365 días.
2. **La pendiente del punto engaña.** El punto de inicio del incendio y las casas quedan al pie de la ladera. Por eso
   la pendiente se mide a escala de ladera (1 km), no en el punto.
3. **El modelo subestima los núcleos convectivos.** Se midieron 31,6 mm en 4 h y el pronóstico daba 12,6 mm en 3 h.
   Un umbral sobre ~12 mm habría perdido el único aluvión real.

## Combinaciones evaluadas (180 días, 362 cicatrices)

«Temporales» cuenta los días seguidos con aviso como uno solo. La mediana y el máximo son por cicatriz con aviso.

| Lluvia en 3 h | Ladera a 1 km | Isoterma sobre la cota | Cicatrices con aviso | Temporales | Mediana | Máximo | Marca Quebrada Honda |
|---|---|---|---|---|---|---|---|
| ≥ 10 mm | — | no | 358 | 3.349 | 9 | 19 | sí |
| ≥ 10 mm | ≥ 8° | no | 23 | 238 | 11 | 18 | sí |
| **≥ 10 mm** | **≥ 8°** | **sí** | **23** | **205** | **9** | **17** | **sí** |
| ≥ 10 mm | ≥ 12° | sí | 10 | 103 | 11 | 16 | no |
| ≥ 12 mm | ≥ 8° | sí | 23 | 158 | 7 | 12 | sí (por 0,6 mm) |
| ≥ 15 mm | ≥ 8° | sí | 23 | 110 | 4 | 11 | no |
| ≥ 15 mm | — | sí | 356 | 1.358 | 3 | 11 | no |

Lectura:

- **Sin la condición de ladera**, casi todas las cicatrices (358 de 362) habrían avisado, en un invierno récord de
  lluvia. La ladera es el filtro que más discrimina: solo 25 de 362 cicatrices tienen ≥ 8° a escala de 1 km (la
  mediana es de 1,2°), y la mayoría de los incendios de CONAF ocurren en terreno plano u ondulado.
- **La isoterma** quita un 14 % de los temporales (de 238 a 205): son los casos en que en la ladera nieva en vez de llover.
- **Se eligen 10 mm y no 12 mm**, aunque 12 mm avisa menos (mediana de 7 temporales contra 9), porque 12 mm deja al
  único aluvión real a 0,6 mm del borde, y el pronóstico ya subestimó ese evento a menos de la mitad de lo medido. En
  un aviso de riesgo para la vida se prefiere avisar de más.

## Límites

- **Un solo positivo.** Con un aluvión documentado se puede comprobar que el criterio lo habría marcado (sensibilidad
  en ese caso), pero no se puede medir la tasa de falsas alarmas: no hay un catastro de qué cicatrices *no* tuvieron
  aluvión. Los 205 temporales se cuentan como avisos, no como errores. El catastro de SERNAGEOMIN (AGUA-08) es el paso
  que falta para medir la precisión.
- **Invierno atípico.** El Niño 2026 dejó lluvias récord (CR2): en un año normal el número de avisos debería ser menor.
- **Pronóstico archivado.** El archivo de Open-Meteo se acerca al pronóstico de pocas horas. Un aviso con más
  anticipación usa un pronóstico menos preciso.
- **Disco equivalente.** Un incendio de CONAF es un punto (el inicio) y una superficie. BRASA lo modela como un disco
  de área equivalente, no como el perímetro real.
- **Isoterma contra cota del entorno.** Se compara con la cota máxima de 9 muestras en ~2×2 km, no con la cota de
  toda la cuenca.

## Reproducir

```bash
python scripts/calibrar_aluvion.py --fin 2026-11-09 --out out/calib.json
```

Usa unas 250 llamadas al archivo de Open-Meteo y unas 40 a la API de elevación. Guarda caché en `out/cache` y
reanuda si se corta. El cupo horario de Open-Meteo es por IP: córrelo en una máquina remota.
