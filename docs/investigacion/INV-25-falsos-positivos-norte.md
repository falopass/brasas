# INV-25 · Falsos positivos del norte: medición de «anomalia» por región (DET-08)

> Investigación para BRASA Chile. **Fecha:** 19 de octubre de 2026. **Alcance:** método de medición y límites; **no se cambió ningún umbral** (`backend/incidents.py`, `backend/providers/goes.py` intactos). La medición sobre la temporada real queda pendiente de correr con datos suficientes.
>
> **Actualización (23-10-2026):** con la decisión de DET-45 se implementó la máscara regional por celda —`web/data/mascara-norte.json` (lista vacía) y la regla en `backend/incidents.py`—; ver §8. La calibración sigue pendiente de datos reales.

## Resumen ejecutivo

1. **Qué se mide:** por región, cuántas detecciones de `work.observations` terminaron en un incidente «anomalia» —la evidencia no alcanzó para subir de estado— frente a las que llegaron a un estado con evidencia, y qué fracción es diurna (08:00-19:59 hora de Chile).
2. **Herramienta:** `scripts/local/medir_falsos_positivos.py`, solo lectura y sin red. Imprime una tabla por región y las 5 comunas con más «anomalia».
3. **Advertencia central:** «anomalia» no equivale a falso positivo. Una detección aislada puede ser un incendio real pequeño que nadie reportó, una quema autorizada o calor industrial. La métrica es un candidato a ruido, no una condena.
4. **Decisión que habilita:** si el norte muestra una tasa de «anomalia» diurna claramente más alta que el resto (y nocturna normal), corresponde evaluar un umbral o máscara regional; si la tasa es pareja, el problema no es regional y conviene otra vía (persistencia, fuentes fijas).

## 1. Por qué el norte es sospechoso

GOES-19 (ABI, banda 7 de onda media ~3,9 µm) detecta calor, no fuego. En el desierto de Atacama el suelo desnudo supera los 60 °C en tardes de verano, y la minería a cielo abierto, las fundiciones y las plantas solares de concentración emiten calor permanente. La hipótesis de DET-08 es que ahí el algoritmo produce «anomalias» que nunca fueron incendio.

La escala importa: el píxel de GOES sobre Chile mide del orden de 2-3 km (2 km en el nadir, degradándose con el ángulo). Un punto caliente pequeño —una antorcha, un espejo solar— se diluye en un píxel que también contiene suelo frío, pero el suelo desértico a mediodía puede llenarlo entero.

## 2. Método

Para cada fila de `work.observations` (con filtros opcionales de fecha y sensor):

1. Se resuelve el incidente que la agrupó por `work.incident_observations` → `work.incidents.status`.
2. Se clasifica en dos grupos: **«anomalia»** (el incidente quedó en el estado inicial: una sola detección o solo confianza baja, sin persistencia ni reporte) y **con evidencia** («posible», «reportado», «confirmado», «controlado», «extinguido»). Las detecciones sin incidente enlazado se cuentan aparte.
3. La región sale del `comuna_code` grabado al ingerir (territorio BCN). Las detecciones sin comuna —mar o fuera de la cobertura territorial— se agrupan en «(sin comuna)».
4. «Diurna» se evalúa convirtiendo `observed_at` (UTC) a America/Santiago y contando 08:00 a 19:59 locales. La división importa: el ruido por suelo caliente es exclusivamente diurno; una «anomalia» de noche tiene otra explicación (industria, volcán, borde de nube mal resuelto).

Salida: detecciones, % diurnas, % en «anomalia» (total, de día y de noche) por región, ordenadas de norte a sur, más las 5 comunas con más «anomalia».

## 3. Cómo correrlo contra la temporada real

```bash
# toda la base
python scripts/local/medir_falsos_positivos.py --db data/work.db

# temporada en curso (ejemplo) y solo GOES, que es el sospechoso del norte
python scripts/local/medir_falsos_positivos.py --db data/work.db \
    --from 2025-12-01 --to 2026-02-28 --sensor ABI

# contra la copia en el servidor, bajada por respaldo (sin tocar producción)
python scripts/local/medir_falsos_positivos.py --db respaldo-work.db --json INV-25-resultado.json
```

`--to` con fecha sola incluye el día completo. `--sensor` acepta `ABI` (GOES), `VIIRS` y `MODIS`. Con base vacía o filtros sin datos imprime un mensaje y sale con código 0.

## 4. Cómo leer el resultado

| Patrón | Lectura probable |
|---|---|
| Norte alto de día **y** de noche | Fuentes fijas (minería, antorchas) o umbral global bajo: mirar DET-05/DET-06, no un umbral regional diurno |
| Norte alto solo de día | Suelo caliente / plantas solares: candidato a umbral diurno regional o máscara por celda |
| Tasa pareja en todas las regiones | El ruido no es del norte: no hay caso para umbral regional; revisar persistencia (DET-01) o confianza mínima |
| Pocas detecciones en el norte | La muestra no alcanza: esperar más temporada antes de decidir |

Comunas en el «top 5» concentrado en el norte (p. ej. sobre la minería de Antofagasta o Calama) apuntan a fuentes fijas puntuales; comunas repartidas apuntan a fenómeno regional.

## 5. Límites

- **«anomalia» ≠ falso positivo.** Puede ser un incendio real pequeño que se apagó solo o que nadie reportó. En el norte hay poca población: los incendios chicos nadie los ve. El cruce fino contra CONAF lo hace `scripts/validar_deteccion.py` (QA-03).
- **El estado es del incidente, no de la detección.** Una detección dentro de un incidente «confirmado» no era ruido aunque en sí misma fuera débil; el criterio «estado final del incidente» es el más honesto disponible sin revisar pixel a pixel.
- **GOES mezcla píxeles.** Con 2-3 km de resolución, una misma celda puede contener una planta solar (ruido) junto a un foco real. Subir el umbral regional arriesga perder incendios tempranos justo donde más importa detectarlos rápido.
- **`comuna_code` faltante.** Detecciones antiguas o en el mar van a «(sin comuna)»; no se reasignan por distancia para no contaminar el conteo.
- **Diurna = banda fija 08-19 h locales**, no salida/puesta real del sol. En verano el día útil del desierto empieza antes y termina después; la banda es un compromiso simple.

## 6. Decisión que habilita

Con la tabla sobre la temporada real se decide entre:

- **Nada:** la tasa del norte no destaca → DET-08 se cierra sin tocar umbrales.
- **Umbral diurno regional:** solo el norte, solo de día, solo para «anomalia» → cambio chico en `backend/incidents.py`, con la tabla como evidencia en el PR.
- **Máscara por celda:** el ruido se concentra en pocas comunas/celdas → alimenta DET-05 (`scripts/build_persistent_mask.py`) con datos reales del propio sistema.

En cualquiera de los casos, el cambio se documenta contra esta medición y se vuelve a correr el script después para verificar que la tasa bajó sin desaparecer detecciones del resto del país.

## 7. Hecho en este PR

- `scripts/local/medir_falsos_positivos.py` (script nuevo, solo lectura).
- `tests/test_falsos_positivos.py` (base sintética: conteos exactos, filtros, base vacía).
- Este documento. **Ningún umbral ni archivo de backend fue modificado.**

## 8. Máscara regional (DET-45): mecanismo implementado y cómo se agrega una celda

**Decisión (21-10, Diego):** máscara regional por celda en vez de umbral único; se calibra con datos reales de la temporada (Fusion).

**Qué se implementó** (sin datos de la temporada en la sesión, ninguna celda se inventó):

- `web/data/mascara-norte.json`: archivo versionado en el mismo lugar y formato que `persistent_hotspots.json`, con `source`, `fetched_at`, `metodo` y `cells` **vacía**. Nada se enmascara hasta que la medición proponga celdas.
- `backend/incidents.py`: una detección de **GOES** (sensor `ABI`) dentro del `radio_km` de una celda vigente y en su `franja` recorre el mismo camino que una fuente fija: si **toda** la evidencia del incidente cae enmascarada, el incidente queda `fixed_source = 1` con `fixed_reason` «máscara del norte: \<motivo\>» — deja de generar aviso automático pero el punto se sigue mostrando y la ficha dice el motivo. VIIRS y MODIS **no** se enmascaran (mejor resolución), así que una detección de ellos en el incidente basta para que avise normal. La invalidación por incendio de CONAF a ≤ 5 km (FIX-03) también aplica a la máscara.
- `franja` de la celda: «dia» = 08:00 a 19:59 hora de Chile (`America/Santiago`, el mismo corte del medidor) para ruido de suelo caliente; «siempre» para calor permanente. Se evalúa sobre el `observed_at` de cada detección, no sobre la hora del ciclo.
- `revisar_el` (ISO AAAA-MM-DD) es la fecha de revisión comprometida y opera como el `valid_to` de las fuentes curadas: **vencida o ilegible, la celda deja de silenciar** hasta re-medirla. Una celda mal puesta o vieja no puede tapar un incendio real para siempre.

### Cómo se agrega una celda

1. Corre la medición sobre la temporada real, por ejemplo `python scripts/local/medir_falsos_positivos.py --db data/work.db --sensor ABI --from <inicio-temporada>` (§3), y busca comunas/puntos con «anomalia» **diurna** concentrada (§4).
2. Criterio de aceptación: la «anomalia» diurna se concentra en un punto acotado con una explicación física que se pueda escribir en `motivo` (planta solar, faena, suelo desnudo). Si el ruido está repartido en toda una comuna no es una celda — es otra discusión (§6). Recuerda: «anomalia» no equivale a falso positivo (§5).
3. Escribe la celda con `lat`, `lon`, `radio_km` (ajustado a la dispersión de las detecciones anómalas del punto, no al píxel teórico), `franja`, `motivo`, `evidencia` (`fecha` y `conteo` de la medición que la propone) y `revisar_el` (a lo sumo la temporada siguiente).
4. Quién revisa: la celda la aprueba el dueño punto por punto, como los puntos de `persistent_hotspots.json` (DET-06). `tests/test_mascara_norte.py` exige el esquema completo y que toda celda caiga en una comuna de Arica y Parinacota, Tarapacá, Antofagasta o Atacama.
5. Después de publicar, vuelve a correr el medidor: la «anomalia» diurna de esa zona debe bajar sin desaparecer detecciones nocturnas ni del resto del país.

**Pendiente:** la calibración con datos de la temporada real; hasta entonces `cells` va vacía y el comportamiento es idéntico al de siempre.
