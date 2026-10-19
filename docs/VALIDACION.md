# Validación de la detección contra CONAF (QA-03)

`scripts/validar_deteccion.py` responde con números la pregunta central del proyecto:
**¿qué porcentaje de los incendios que informa CONAF detectó BRASA, por tamaño, y con cuántos
minutos de ventaja o atraso?**

```bash
python scripts/validar_deteccion.py --db data/demo/brasa.db [--season 2025-2026] [--km 10] [--hours 6] [--json]
```

La base se copia a un directorio temporal y la copia se abre en solo lectura: el script nunca
escribe en `brasa.db`/`work.db` ni llama a la red.

## Qué mide

- Para cada incendio del reporte público de CONAF (GEPRIF) con hora de detección
  (`f_deteccion`, guardada en `official_fires.detected_at`), busca la primera observación de
  BRASA a `--km` km o menos, dentro de la ventana `[detección − 6 h, detección + --hours h]`.
  Si existe, el incendio cuenta como **detectado**.
- **Ventaja** = primera observación BRASA − detección CONAF, en minutos.
  **Negativo = BRASA llegó antes**; positivo = CONAF informó primero. La tabla muestra la
  mediana (p50) y el p90 por tramo de superficie (`<1 ha`, `1-10`, `10-100`, `>100`,
  `sin superficie`).
- **Candidatos a falso positivo**: incidentes abiertos («posible»/«anomalía») sin ningún
  incendio de CONAF a `--km` km o menos.
- Sin `--season` se evalúan todas las temporadas guardadas y se imprime una línea de resumen
  por cada una. Si no hay incendios con hora de detección, el script lo dice y sale con
  código 2 (no imprime una tabla vacía).

## Qué NO mide

- **Falsos positivos reales.** Un incidente sin CONAF cerca es solo un *candidato*: puede ser
  una quema autorizada, una fuente de calor industrial, un reflejo o un incendio real que CONAF
  aún no informa (o que quedó fuera de su reporte). Separarlos exige revisión caso a caso; el
  número es una cota, no una tasa de error.
- **Incendios que CONAF no informó.** La validación solo cubre lo que está en el CSV oficial;
  BRASA podría estar detectando focos que nunca entran al registro y el script no los contaría
  como aciertos (entran como candidatos).
- **Calidad espacial.** La correspondencia es por distancia al punto del reporte (lat/lon del
  incendio), no al perímetro: un incendio grande detectado en su borde puede quedar fuera del
  radio, y una observación cercana puede venir de otro foco.
- **Todo el espectro temporal.** Si BRASA solo veía el incendio fuera de la ventana
  (−6 h / +6 h por omisión), cuenta como no detectado aunque haya observaciones.

## Por qué solo cubre la temporada en curso

El CSV que CONAF publica en GitHub (`deigeprif/public`, `reporte/incendios.csv`) contiene
únicamente la temporada vigente (julio a junio): cuando empieza una temporada nueva el archivo
se reinicia. `official_fires` conserva lo que la ingesta vio en vivo, así que la validación da
una temporada completa solo después de que BRASA estuvo corriendo toda la temporada. Las
temporadas anteriores no se pueden reconstruir desde esta fuente; para eso están los casos
precalculados de `scripts/replay_case.py` (QA-02), que miden tiempos internos pero no comparan
contra CONAF.

## Cómo leer los números

- Un `%` alto con `p50` negativo es el escenario ideal: BRASA ve casi todo y antes que el parte
  oficial. `f_deteccion` es cuando el foco se reportó a CONAF (un testigo, una brigada, un
  avistamiento), no cuando el fuego empezó: una ventaja negativa grande no es necesariamente
  sospechosa.
- Los tramos chicos (`<1 ha`, `1-10`) se apagan o se reportan rápido y tienen menos píxeles:
  una tasa menor ahí es esperable y no equivale a fallar en incendios peligrosos.
- Si el número de candidatos crece mucho en el norte, revisar DET-08 del backlog
  (`docs/BACKLOG_MAESTRO.md`): desiertos, minería y plantas solares calientan de día.
