# INV-08 · CR2MET frente a ERA5 para la anomalía de lluvia de RISK-02

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** decisión de fuente de datos para RISK-02; no se integró ni se cambió código. Cada afirmación lleva su fuente con fecha de consulta. Lo que no se pudo verificar se marca **NO VERIFICADO**.

## Resumen ejecutivo

1. **CR2MET sí se actualiza.** Existe un feed operacional en `ftp.cr2.cl`: `v2.5_NRT` (mismo método que la versión operacional, pero con ERA5T casi en tiempo real) con un rezago documentado de **~9 días**, y `v2.5_best`, que copia por mes lo mejor disponible con prioridad v2.5 → R1 → NRT. Verificado el 19-oct-2026: el archivo de octubre cubre hasta el **10 de octubre**.
2. **En calidad, CR2MET es objetivamente mejor para Chile centro-sur**: es un *downscaling* estadístico de ERA5 a 0,05° calibrado contra estaciones nacionales (DGA, DMC, SERVIMET, INIA, FDF); su propio documento técnico reporta «alta covariabilidad» con los registros locales **especialmente en la zona centro-sur**. Como contraste, una evaluación sobre 345 estaciones de la Patagonia midió una sobreestimación mediana de **+59,7 %** de ERA5-Land.
3. **Pero la métrica de BRASA es un cociente contra la normal del mismo dataset.** El sesgo sistemático de ERA5 aparece en el numerador y en el denominador y se cancela en gran parte: la ventaja de CR2MET pesa más en los milímetros absolutos que en la anomalía relativa que publica RISK-02.
4. **En latencia, CR2MET es peor que lo que ya usa BRASA.** ERA5 en Open-Meteo se actualiza a diario con 5 días de retraso y el código ya tapa esa cola con el pronóstico (`past_days`), así que la temporada en curso queda completa. Con CR2MET NRT quedarían ~9 días de cola sin dato, o habría que mezclar fuentes para taparla.
5. **Licencia: CC BY 4.0** (registro Zenodo del dataset). Permite el uso y los derivados con cita — la misma obligación práctica que Open-Meteo. No hay bloqueo ni ventaja decisiva.
6. **Decisión: RISK-02 se queda con ERA5 vía Open-Meteo.** CR2MET queda como referencia de validación y como fuente candidata si BRASA llega a mostrar milímetros absolutos por comuna que deban calzar con las cifras oficiales (la DGA usa CR2MET para el componente meteorológico del Balance Hídrico de Chile).

## 1. Pregunta y método

**Pregunta** (BACKLOG_MAESTRO, INV-08):

- ¿CR2MET se actualiza con poco retraso?
- ¿Es mejor que ERA5 en Chile central y sur?
- ¿Licencia?
- Salida: la fuente de RISK-02.

**Método**

- Fuentes primarias: `readme.pdf` del servidor de datos del CR2 (descargado y extraído), listados del servidor `ftp.cr2.cl` con fechas de publicación por archivo, metadatos JSON por archivo NetCDF, registro del dataset en Zenodo (API), documentación de la API histórica de Open-Meteo.
- Verificación empírica: se descargaron el readme, los JSON de metadatos de octubre y septiembre de 2026 y los primeros bytes del NetCDF para comprobar el formato real (sin autenticación).
- Literatura de validación: comparaciones de productos grillados de precipitación contra estaciones chilenas.
- **No se descargó el dataset completo ni se procesó la grilla**: eso queda como paso de implementación si la decisión cambia.

## 2. Estado actual de RISK-02

- `backend/rain.py` calcula la anomalía por comuna: lluvia del 1 de junio a hoy contra el promedio 1991-2020 **de la misma ventana de días**, y traduce el cociente a un nivel y una frase.
- `backend/providers/weather.py::daily_rain` usa el archivo ERA5 de Open-Meteo (0,25°, diario) para la temporada, y el pronóstico con `past_days=7` para los últimos días que el archivo aún no cubre (`compute_rain_anomaly` los mezcla).
- Las normales se construyen por celda de 0,5° (~55 km) —153 celdas para 345 comunas— con 30 años de ERA5 diario (`build_rain_normals`); el mismo ERA5 alimenta el numerador y el denominador, así que el cociente es internamente consistente.
- Licencia en uso: datos de Open-Meteo bajo CC BY 4.0 y API gratuita para uso no comercial (verificado en la investigación del 30-30-30/FWI, `docs/research/02-30-30-30-y-fwi.md`).

## 3. Qué es CR2MET y con qué retraso llega

CR2MET es el producto grillado del Centro de Ciencia del Clima y la Resiliencia (CR2): precipitación y temperaturas extremas **diarias** en una malla de **0,05°** sobre Chile continental, obtenido por *downscaling* estadístico de ERA5 con parámetros topográficos y LST de MODIS, calibrado contra observaciones nacionales con control de calidad.

El `readme.pdf` del servidor de datos (descargado el 19-oct-2026) define cuatro subproductos; el rezago entre paréntesis es lo verificado hoy en los listados:

| Subproducto | Qué es | Periodo | Rezago verificado el 19-oct-2026 |
|---|---|---|---|
| `v2.5` | Versión final: incluye posproceso de ajuste de anomalías mensuales con observaciones; la mejor coherencia con observaciones | 1960 → 2021 | Estático (último año completo 2021) |
| `v2.5_R1` | Salida directa de los modelos de regionalización, sin el ajuste mensual; depende de la disponibilidad de datos de ERA5 | 1960 → P − 3 meses | Último archivo: **jul-2026** (~3 meses, calza) |
| `v2.5_NRT` | Igual que R1 pero con ERA5T (ERA5 casi en tiempo real); el readme fija el rezago en «aproximadamente 9 días» | ~nov-2022 → P − 9 días | El archivo de oct-2026 cubre **1 al 10 de octubre** (~9 días, calza) |
| `v2.5_best` | Copia por mes del mejor subproducto disponible, con prioridad v2.5 → R1 → NRT; incluye derivados (spi, spei, et0, tmean, sf) | 1960 → P − 9 días | Oct-2026: cubre 1 al 10 de octubre |

Formato: un NetCDF por variable y mes, grilla de 800×220 puntos (lat −56,975 → , lon −76,975 → , según el JSON de metadatos), enteros de 16 bits con `scale_factor` 0,01 y `add_offset` 300; `pr` en mm/día; ~20 MB por archivo mensual de precipitación. El *magic number* del archivo es `CDF\x01`: **NetCDF-3 clásico**, no NetCDF-4/HDF5.

## 4. Calidad en Chile central y sur

- **Documento técnico del propio producto:** precipitación y temperatura «muestran, en general, una alta covariabilidad espacial y temporal con registros locales, **especialmente en la zona centro-sur de Chile**»; el desempeño diario «disminuye de manera importante en los extremos norte y sur del país, debido al menor ajuste de ERA5 con las observaciones en estas regiones» (readme de `ftp.cr2.cl`, 19-oct-2026). Para tendencias largas y periodos pre-satelitales recomienda usarlo junto a referencias observacionales.
- **Validación independiente con estaciones:** en la evaluación de productos de precipitación y temperatura contra estaciones chilenas de Boisier et al. (benchmarking WRF-SAAG, preprint en revisión en HESS), «the CR2MET product consistently provided the best performance metrics for extreme precipitation and temperature»; todos los productos rinden peor en el Norte Grande y la Patagonia y mejor en la macrozona sur lluviosa (KGE mediano ≥ 0,65).
- **Patrón regional de los productos grillados:** la evaluación de Zambrano-Bigiarini et al. (2017, HESS) sobre 366 estaciones encontró que los productos rinden mejor en Chile central (32,2–36,4° S) y el sur húmedo (36,4–43,7° S) en cotas bajas y medias, y mejor en otoño-invierno (MAM-JJA) — justo la ventana jun–oct de RISK-02.
- **Sesgo de ERA5 crudo en el sur austral:** una evaluación de seis productos mensuales sobre 345 estaciones de la Patagonia midió en ERA5-Land la mayor sobreestimación sistemática (mediana +59,7 % sobre lo observado) y el peor desempeño general (KGE). La familia ERA5 sin corrección local tiene un sesgo húmedo fuerte donde la red de estaciones es escasa y el terreno complejo.
- **Matiz hidrológico:** Baez-Villanueva et al. (2021, HESS) compararon CR2MET, RF-MEP, ERA5 y MSWEP como forzante de un modelo lluvia-escorrentía en 100 cuencas chilenas: con calibración, todos dieron desempeño similar — el modelo compensa las diferencias entre forzantes. Es evidencia indirecta de que para una **razón dentro del mismo dataset** (como la anomalía de BRASA) las diferencias entre productos se atenúan.
- **Uso oficial:** la actualización del Balance Hídrico de Chile (DGA, SIT N° 524, 2022) se basó en CR2MET para su componente meteorológica; las cifras oficiales de déficit hídrico son directamente comparables con este producto.

**Síntesis honesta:** CR2MET es el mejor producto disponible para lluvia en Chile centro-sur en términos de milímetros absolutos y coherencia con registros nacionales. Sin embargo, RISK-02 no publica milímetros absolutos como titular: publica el **cociente** temporada/normal calculado dentro del mismo producto. El sesgo húmedo de ERA5 aparece en ambos lados del cociente y se cancela en gran parte, así que la ventaja de CR2MET sobre la *anomalía* es real pero más acotada que sobre los valores absolutos. Ninguna fuente evaluó el cociente de anomalía estacional por comuna tal como lo calcula BRASA — esa comparación queda **NO VERIFICADO**.

## 5. Licencia

- El registro del dataset en Zenodo (DOI 10.5281/zenodo.7529682, consultado el 19-oct-2026 vía API) declara `access_right: open` y `license: cc-by-4.0`. La cita pedida es «Boisier, J. P. (2023). CR2MET… (v2.5) [Data set]. Zenodo» y el artículo Boisier et al. (2025, HESS, egusphere-2024-2695).
- El servidor `ftp.cr2.cl` no publica un archivo de licencia propio (se revisó el readme completo y los listados): distribuye el mismo producto con la misma cita exigida. **NO VERIFICADO** que el feed operacional tenga términos distintos al depósito Zenodo; la página del producto en `cr2.cl` pide llenar un formulario de cortesía, pero el servidor de archivos sirve sin autenticación (verificado).
- **Comparación:** Open-Meteo publica los datos bajo CC BY 4.0 y su API es gratuita para uso no comercial (documentado en `docs/research/02-30-30-30-y-fwi.md`). Misma obligación práctica en ambos casos: atribución visible. Para una app pública como BRASA, con la cita en la ficha de fuentes, **ninguno de los dos bloquea**.

## 6. Costo de acceso e integración (si se quisiera cambiar)

- **Descarga:** HTTP abierto, sin clave ni sesión (verificado hoy con el readme, los JSON y bytes del NetCDF). Un archivo `pr` mensual pesa ~20 MB.
- **Volumen para las normales:** 30 años × 12 meses ≈ 360 archivos ≈ 7 GB una sola vez (existe además un `CR2MET_pr_v2.5_mon_stats_1960_2021_005deg.nc` cuyo contenido no se inspeccionó — **NO VERIFICADO** si trae la climatología ya calculada).
- **Formato:** NetCDF-3 clásico (`CDF\x01`). `h5py`, ya instalado para GOES/GLM, **no lo lee**: haría falta `netCDF4` o `scipy.io.netcdf_file`, es decir una dependencia nueva.
- **Operación:** el archivo del mes en curso se regenera con el mes parcial (el de oct-2026 se regeneró el 19-oct cubriendo al 10-oct), así que habría que re-descargarlo en cada ciclo y vigilar el rezago; además, los últimos ~9 días quedarían sin dato o habría que taparlos con otra fuente (mezclar productos dentro de la ventana de la anomalía es posible pero rompe la consistencia interna del cociente). El servidor es de un centro de investigación: **sin SLA**.
- **Esfuerzo estimado:** un proveedor nuevo análogo a `weather.daily_rain` pero en lote mensual + un script de normales sobre `v2.5`/`v2.5_best` + el mapeo comuna → píxel (a 0,05° se puede usar el polígono comunal en vez del centroide, lo que además mejoraría la representatividad de cada comuna). Días de trabajo, no semanas.

## 7. Respuesta a las preguntas del backlog

| Pregunta | Respuesta | Confianza |
|---|---|---|
| ¿CR2MET se actualiza con poco retraso? | **Sí existe feed operacional** (`v2.5_NRT` ~9 días; `v2.5_R1` ~3 meses; `v2.5_best` combina). Es **más lento** que la cadena actual de BRASA (ERA5 a 5 días + pronóstico que tapa la cola). | Alta |
| ¿Es mejor que ERA5 en Chile central y sur? | Para milímetros absolutos y coherencia con registros nacionales: **sí**, documentado y validado contra estaciones (y es el producto que usa la DGA). Para el cociente de anomalía de RISK-02: ventaja real pero **acotada**, porque el sesgo de ERA5 se cancela parcialmente al dividir contra su propia normal; ninguna fuente evaluó ese cociente. | Media-alta / Media |
| ¿Licencia? | **CC BY 4.0** (Zenodo); permite uso y derivados con cita. Sin bloqueo para una app pública; misma obligación que Open-Meteo. | Alta (feed operacional: misma política asumida, **NO VERIFICADO** aparte) |
| ¿Costo de integración? | Descarga libre ~20 MB/mes; una dependencia nueva para leer NetCDF-3; rebuild de normales ~7 GB una vez; sin SLA. Costo moderado. | Alta |

## 8. Confianza

- **Alta:** rezagos por subproducto (readme + verificación empírica de archivos y JSON el 19-oct-2026), formato NetCDF-3, licencia CC BY 4.0 del depósito Zenodo, rezago de 5 días de ERA5 en Open-Meteo.
- **Media:** la comparación de calidad aplicada a RISK-02 — las fuentes son sólidas pero evalúan productos, no el cociente anomalía por comuna que publica BRASA; la evidencia hidrológica (Baez-Villanueva 2021) sugiere que las diferencias se atenúan tras normalizar.
- **NO VERIFICADO:** términos específicos del feed `ftp.cr2.cl` (sin licencia propia en el sitio), contenido del archivo `mon_stats` (¿climatología precalculada?), cadencia exacta con que se regenera el archivo del mes en curso (una sola muestra: 19-oct → datos al 10-oct), y una medición directa de cuánto cambiaría el nivel de anomalía por comuna al pasar de ERA5 a CR2MET.

## 9. Decisión

**RISK-02 se queda con ERA5 vía Open-Meteo.** Razones:

1. La anomalía es un cociente dentro del mismo producto: la mayor parte del sesgo de ERA5 se cancela, así que la mejora de CR2MET sobre la cifra publicada es acotada.
2. CR2MET NRT llega con ~9 días de retraso y el archivo del mes se regenera: integrar significa ETL mensual, una dependencia nueva (NetCDF-3) y una cola de ~9 días sin dato o una mezcla de fuentes que rompe la consistencia del cociente.
3. La licencia no favorece a ninguno: ambos piden atribución (CC BY 4.0) y ninguno cobra para el uso de BRASA.

**Qué haría falta para cambiar de fuente (siguiente paso, no implementado):**

1. Medir antes de mover: descargar ~5 años de `v2.5_best` y recomputar la anomalía de las temporadas 2021-2025 para una muestra de comunas del centro-sur; si el nivel cambia de categoría en una fracción relevante de casos, la migración se justifica. Si solo cambian los milímetros absolutos, no.
2. Si se migra: usar `v2.5` (1960-2021) para las normales 1991-2020 y `v2.5_best` para la temporada en curso; mapear comuna → píxeles por polígono; agregar `netCDF4` (o `scipy`) a `requirements.txt`; citar «Boisier (2023), CR2MET v2.5, DOI 10.5281/zenodo.7529682» junto a la fuente en la ficha.
3. Reevaluar si BRASA empieza a mostrar **milímetros absolutos** comparables con cifras oficiales (ahí el sesgo de ERA5 sí se nota, sobre todo en el sur austral, donde ERA5-Land sobreestima ~60 %) o si CONAF/DGA publican anomalías de referencia contra las que BRASA deba calzar.

## 10. Fuentes consultadas (19 de octubre de 2026)

| Fuente | URL | Fecha | Qué sostiene |
|---|---|---|---|
| CR2, `readme.pdf` del servidor de datos | <https://ftp.cr2.cl/download/cr2met/readme.pdf> | Consultado 19-oct-2026 | Descripción del producto, calibración con estaciones nacionales, tabla de versiones y rezagos (R1 3 meses, NRT ~9 días), formato NetCDF, cita y validación resumida |
| CR2, listado `v2.5_NRT` | <https://ftp.cr2.cl/browse/cr2met/v2.5_NRT/pr/v2.5_NRT_day/> | Consultado 19-oct-2026 | Archivos mensuales nov-2022 → oct-2026; el de octubre se generó hoy |
| CR2, metadatos JSON oct/sep-2026 | <https://ftp.cr2.cl/download/cr2met/v2.5_NRT/pr/v2.5_NRT_day/CR2MET_pr_v2.5_NRT_day_2026_10_005deg.json> | Consultado 19-oct-2026 | Octubre cubre 01→10 de octubre; grilla 800×220; pr mm/día; empaquetado int16 |
| CR2, listado `v2.5_R1` y `v2.5_best` | <https://ftp.cr2.cl/browse/cr2met/v2.5_R1/pr/v2.5_R1_day/> · <https://ftp.cr2.cl/browse/cr2met/v2.5_best/pr/v2.5_best_day/> | Consultado 19-oct-2026 | R1 termina en jul-2026 (~3 meses); best llega al 10-oct-2026 |
| Zenodo, registro CR2MET v2.5 | <https://zenodo.org/records/7529682> (API) | Consultado 19-oct-2026 | `license: cc-by-4.0`, acceso abierto, periodo 1960-2021, grilla 0,05°, archivos zip de pr y txn |
| CR2, página de productos grillados | <https://www.cr2.cl/datos-productos-grillados/> | Consultado 19-oct-2026 | Descripción del dataset, método (ERA5 + topo + MODIS calibrado con observaciones), cita oficial y formulario de descarga |
| Open-Meteo, Historical Weather API | <https://open-meteo.com/en/docs/historical-weather-api> | Consultado 19-oct-2026 | ERA5 0,25° horario desde 1940, «daily with 5 days delay»; ECMWF IFS 9 km sin retraso desde 2017 |
| Boisier et al., benchmarking WRF-SAAG (preprint HESS) | <https://doi.org/10.5194/egusphere-2025-3061> | 2025 | CR2MET con las mejores métricas de precipitación extrema y temperatura contra estaciones; todos los productos peor en Norte Grande y Patagonia |
| Zambrano-Bigiarini et al. 2017, HESS | <https://hess.copernicus.org/articles/21/1295/2017/> | 2017 | Productos grillados rinden mejor en Chile central y sur húmedo y en otoño-invierno; peor en norte árido y sur austral |
| Baez-Villanueva et al. 2021, HESS | <https://doi.org/10.5194/hess-25-5805-2021> | 2021 | CR2MET, ERA5, MSWEP y RF-MEP rinden parecido como forzante hidrológica tras calibrar; la calibración compensa diferencias entre productos |
| Evaluación de productos en Patagonia (DataCiencia ANID) | <https://dataciencia.anid.gob.cl/article/445241> | Consultado 19-oct-2026 | ERA5-Land: mediana +59,7 % de sobreestimación y peor desempeño (KGE) frente a 345 estaciones |
| DGA, SIT N° 524 (citado en el readme CR2MET) | — | 2022 | Balance Hídrico de Chile usa CR2MET como componente meteorológica |

## 11. Límites de esta investigación

- **No se midió la anomalía con ambos productos.** La decisión se basa en la estructura del indicador (cociente interno) y en la literatura de validación, no en una comparación número a número por comuna — ese es el primer paso si se reabre.
- **La latencia observada es una muestra de un día.** El 19-oct-2026 el archivo NRT de octubre cubría hasta el 10-oct y R1 hasta jul-2026, consistente con el readme; la cadencia exacta de regeneración del mes en curso no se verificó.
- **El feed operacional no tiene SLA ni licencia propia publicada.** Se asume la política del dataset (CC BY 4.0 + cita); el formulario de la página de cr2.cl podría ser requisito de cortesía — **NO VERIFICADO** si es obligatorio.
- **CR2MET hereda los errores de ERA5 donde no hay estaciones** (extremo norte y sur del país, según su propio readme); no es «verdad terreno», es la mejor aproximación calibrada disponible.
- **No se revisó la resolución temporal horaria ni otras variables** (tmean, et0, spi/spei, nieve): el encargo era solo la lluvia diaria para RISK-02.
