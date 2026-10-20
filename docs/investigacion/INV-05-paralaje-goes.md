# INV-05 · Desplazamiento de los píxeles GOES por el relieve en Chile (DET-02)

> Investigación para BRASA Chile. **Fecha:** 20 de octubre de 2026. **Alcance:** solo lectura.
> No cambia las posiciones que ingiere `parse_fdc`, no reescribe la historia y no toca umbrales,
> agrupación ni avisos. La geometría con altura queda disponible y probada; la integración con un
> DEM es el paso siguiente, con una decisión de datos que este documento deja explícita.

## Resumen ejecutivo

1. **El producto FDC no corrige el relieve.** El ReadMe del producto FHS/FDC de GOES-18 (NOAA/STAR,
   17-12-2024), punto 9 de problemas conocidos, lo dice: «L2 product pixel locations are not
   corrected for terrain, so GOES fires will appear offset from other data sources, particularly in
   elevated terrain». La geometría de `scan_to_latlon` es la del elipsoide.
2. **Cuánto:** en Chile central, un foco a 2.000 m se dibuja **1,63 km** al sur de su posición real;
   a 3.000 m, **2,45 km**. En Temuco son 2,00 y 3,00 km; en Punta Arenas, 3,58 y 5,38 km. La
   magnitud crece hacia el sur porque el ángulo de visión desde 75,2° O es mayor.
3. **Hacia dónde:** el píxel aparente queda al **sur y muy ligeramente al este**; la corrección lo
   mueve al **norte y algo al oeste** (rumbo 351,8° en Santiago a 3.000 m). El ítem suponía «más
   abajo y más al oeste»: la componente principal es sur, no oeste.
4. **Contra los perímetros oficiales:** el 50 % de las detecciones GOES cae dentro del perímetro
   final. Las que quedan fuera y a ≤2 km se concentran al sur del perímetro: el rumbo medio desde
   la detección al borde es 358,7° en Viña 2024 y 23,3° en Ñuble 2023. Es una señal consistente en
   dirección, pero **no aísla el paralaje**: el perímetro es un área final, no un punto, y el píxel
   GOES mide 2-4 km.
5. **El caso de alta cordillera falta.** Los perímetros versionados son de valle y precordillera:
   los centroides van de 17 a 602 m (mediana 242 m en Ñuble). No hay un caso versionado de alta
   cordillera con GOES y perímetro, así que la validación empírica a 2.000-3.000 m **queda
   pendiente**. La tabla teórica responde la pregunta de magnitud; el hueco se declara, no se
   rellena con una suposición.
6. **Veredicto:** DET-02 sí aplica. Recomendación: corregir antes de agrupar, con un DEM; aplicar
   la corrección a las detecciones nuevas, no reescribir la historia, y guardar la altura usada y
   la posición original para auditoría. Pedir la elevación a Open-Meteo por píxel no es viable en
   la ingesta (límite por minuto y latencia).

## 1. Fuente y método

- **Producto:** GOES-R ABI L2 FDC (Fire/Hot Spot Characterization), GOES-16/19, 75,2° O. El
  archivo entrega ángulos de escaneo `x`, `y` en la rejilla fija del ABI; la latitud/longitud se
  calcula con la geometría del satélite.
- **Confirmación de la NOAA:** ReadMe del producto FHS/FDC de GOES-18, 17-12-2024, punto 9:
  <https://www.star.nesdis.noaa.gov/atmospheric-composition-training/documents/G18_ABI_FDC_ReadMe.pdf>.
  La frase está citada textualmente en el resumen.
- **Geometría:** la página «GOES Imager Projection (ABI Fixed Grid)» de NOAA/STAR explica que la
  latitud/longitud se obtiene intersectando el rayo con el elipsoide:
  <https://www.star.nesdis.noaa.gov/atmospheric-composition-training/satellite_data_goes_imager_projection.php>.
- **Código:** `backend/providers/goes.py:74` (`scan_to_latlon`) resuelve la intersección con el
  elipsoide y `parse_fdc` la llama sin altura. La función ahora acepta una altura opcional
  (`elevation`, en metros): con 0 reproduce la geometría actual; con la altura del terreno
  intersecta el mismo rayo con el elipsoide desplazado. La aproximación del elipsoide desplazado
  es exacta a menos de 0,02 m a 5.000 m (probado en `tests/test_paralaje_goes.py`).
- **Herramienta:** `scripts/local/medir_paralaje_goes.py`, solo lectura y sin red. Hace la tabla
  teórica y mide los casos versionados contra sus perímetros. No escribe en la base ni en el
  producto.
- **Constantes:** `lon0 = -75,2°`, `h = 35.786.023 + 6.378.137 m`, `r_eq = 6.378.137 m`,
  `r_pol = 6.356.752,31414 m`, las del `goes_imager_projection` de los archivos FDC.

## 2. Cuánto y hacia dónde

La tabla usa la geometría exacta, no una regla de tres. «Rumbo de corrección» es el rumbo desde el
píxel aparente hacia el punto real; «rumbo aparente» es el opuesto, desde el punto real hacia donde
lo dibuja el producto.

| Lugar | 2.000 m | 3.000 m | Rumbo de corrección (3.000 m) |
|---|---|---|---|
| Arica | 0,83 km | 1,24 km | 345,0° |
| Santiago | 1,63 km | 2,45 km | 351,8° |
| Concepción | 1,85 km | 2,78 km | 356,4° |
| Temuco | 2,00 km | 3,00 km | 355,8° |
| Puerto Montt | 2,22 km | 3,33 km | 356,6° |
| Punta Arenas | 3,58 km | 5,38 km | 354,6° |

A 1.000 m el desplazamiento va de 0,41 km (Arica) a 1,79 km (Punta Arenas); a 4.000 m, de 1,65 a
7,17 km. La relación es lineal con la altura para un punto fijo: `d ≈ h · tan θ`, donde `θ` es el
ángulo cenital del satélite. Por eso la corrección no puede ser una constante: depende de la
latitud, la longitud y la altura.

La dirección merece una corrección al texto del ítem. Para Chile continental (al este de 75,2° O),
el rayo que sale del satélite pasa por el punto elevado y sigue hasta el elipsoide **más lejos del
satélite**: al sur y un poco al este. La corrección, por lo tanto, mueve el píxel al norte y algo
al oeste. En Santiago a 3.000 m la componente norte es 2,41 km y la oeste, 0,35 km; el rumbo de
corrección es 351,8°. En la cordillera, «ladera abajo» no es la dirección del error: el error es
casi norte-sur.

## 3. Contra los perímetros oficiales de CONAF

Se usaron los perímetros históricos versionados en los casos (INV-03): la capa
`PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO` de CONAF-GEPRIF, consultada el 19-10-2026.
La medición está en `scripts/local/medir_paralaje_goes.py`.

| Caso | Detecciones GOES | Polígonos | Dentro | Fuera | Mediana fuera | ≤2 km | Mediana ≤2 km | Rumbo medio ≤2 km |
|---|---|---|---|---|---|---|---|---|
| Viña del Mar 2024 | 2.667 | 4 | 1.404 (52,6 %) | 1.263 | 0,54 km | 95,6 % | 0,54 km | 358,7° |
| Ñuble-Biobío-Araucanía 2023 | 43.398 | 106 | 21.716 (50,0 %) | 21.682 | 0,88 km (muestra 2.000) | 65,7 % | 0,38 km | 23,3° |
| Las Máquinas 2017 | — | 1 | — | — | — | — | — | sin GOES versionado |
| Penco-Lirquén 2026 | 6.957 | — | — | — | — | — | — | sin perímetro versionado |

- **Viña 2024** es un complejo de interfaz, con cuatro perímetros. La mediana de las detecciones
  fuera es 0,54 km; el 95,6 % está a ≤2 km. El rumbo medio al borde es 358,7° (norte), consistente
  con un píxel aparente al sur del área oficial. En alta confianza (1.235 dentro, 1.130 fuera), la
  mediana es 0,54 km y el rumbo medio a ≤2 km, 1,4°.
- **Ñuble 2023** es el único caso de la temporada 2022-2023 con GOES y perímetro. La mediana de
  las detecciones fuera es 0,88 km, pero el p90 es 14,35 km: la cola larga son detecciones lejanas
  a cualquier perímetro (otros focos o falsos positivos), no el borde del incendio. Mirando solo
  las que están a ≤2 km, la mediana baja a 0,38 km y el rumbo medio al borde es 23,3° (norte-noreste).
  En alta confianza (18.477 dentro, 18.446 fuera), la mediana a ≤2 km es 0,40 km y el rumbo medio,
  29,0°.
- **Las Máquinas 2017** tiene perímetro (192.157 ha, un polígono) pero no tiene GOES versionado. El
  caso es de la geometría de GOES-16 en 2017 (89,5° O), no la de 75,2° O, así que no sirve para
  medir el producto actual.
- **Penco-Lirquén 2026** tiene GOES-19, pero la capa histórica no incluye la temporada 2025-26. La
  capa `Perimetro_final` en vivo sí devolvió un polígono de 52,2 ha («573-PUNTA DE PARRA II») para
  la caja del caso, pero no está versionado en el caso y no se agregó para no convertir esta
  investigación en un cambio de datos. Queda como tercer caso posible para el seguimiento.

### Elevación de los perímetros

Para interpretar la tabla se consultó la elevación del centroide de cada polígono con la API de
elevación de Open-Meteo (Copernicus DEM 2021 GLO-90, 90 m; consulta del 20-10-2026):

| Caso | Centroides (m) | Mediana (m) |
|---|---|---|
| Viña del Mar 2024 | 226-442 | 288 |
| Ñuble-Biobío-Araucanía 2023 | 17-602 | 242 |
| Las Máquinas 2017 | 353 | 353 |

Son incendios de valle y precordillera, no de alta cordillera. A 242-442 m el desplazamiento
esperado es 0,20-0,36 km, del mismo orden que la mediana observada a ≤2 km (0,38-0,54 km); la
diferencia es compatible con el tamaño del píxel y con que el perímetro es un área final. La
comparación **no permite separar** el paralaje del crecimiento del incendio ni del centro del
píxel. A 2.000-3.000 m el desplazamiento esperado es 1,6-3,0 km, mucho mayor que la resolución del
píxel; ahí sí sería una señal clara, pero no hay caso versionado a esa altura.

## 4. Límites

- **El perímetro es un área, no un punto.** Una detección desplazada 2-3 km al sur puede seguir
  cayendo dentro de un polígono grande. La mediana «fuera del perímetro» es una **cota inferior**
  del error, no la magnitud del paralaje.
- **El perímetro es final, no contemporáneo.** El incendio creció después de cada detección; el
  área final puede contener posiciones que en ese momento estaban fuera.
- **El píxel GOES mide 2-4 km en Chile.** El centro del píxel no es el punto del fuego; el algoritmo
  marca un píxel caliente, no un punto.
- **La cola de Ñuble no es paralaje.** El p90 de 14 km y el máximo de 57 km son detecciones lejanas
  a todo perímetro; se reportan para no esconderlos, pero no se usan para la conclusión.
- **La elevación es del centroide.** No es la máxima del polígono ni la del frente de llama. Un DEM
  completo permitiría muestrear el polígono entero; no se hizo porque esta investigación es de solo
  lectura y sin DEM.
- **Sin VIIRS simultáneo ni punto de ignición oficial.** El método ideal de INV-05 (comparar GOES y
  VIIRS en el mismo incendio) no está disponible en los datos versionados: los casos guardan solo
  GOES. El CSV de CONAF trae coordenadas de los incendios en curso, no de los casos históricos.
- **La geometría del elipsoide desplazado** es una aproximación de la superficie a altura `h`; el
  error es <0,02 m a 5.000 m, muy por debajo de la resolución del píxel.

## 5. Decisión y recomendación

**DET-02 sí aplica.** El producto no corrige el relieve y el desplazamiento es material en la
cordillera: 1,6-3,0 km a 2.000-3.000 m en Chile central, y hasta 5,4 km en Punta Arenas a 3.000 m.
La distancia que se anuncia («a 2,4 km de tu casa») y el umbral de urgencia pueden estar
equivocados por esa magnitud.

**Cuándo corregir.** Antes de agrupar, sobre las detecciones nuevas. No reescribir la historia: los
incidentes guardados conservan sus posiciones y su distancia original. Guardar en la observación
la altura usada y, si se quiere auditar, la posición original; un campo `parallax_corrected` o una
versión de la geometría permite distinguir las detecciones viejas de las nuevas.

**Con qué DEM.** Las opciones, en orden de recomendación:

1. **Grilla gruesa derivada de un DEM global.** Generar una vez, para Chile, una grilla de
   elevación de 0,02°-0,05° a partir de GLO-30 o GLO-90, guardarla como binario compacto con su
   fuente y licencia, y consultarla por interpolación bilineal. No agrega una dependencia de
   raster en tiempo de ejecución y el error de altura (cientos de metros) es menor que el píxel
   GOES de 2-4 km. La resolución exacta es la decisión pendiente.
2. **Leer teselas GLO-30 en tiempo de ejecución** con `rasterio`/GDAL. Es más preciso, pero suma
   una dependencia pesada y lectura de teselas por barrido; para un píxel de 2-4 km no se justifica.
3. **Open-Meteo por píxel.** No es viable en la ingesta: una llamada por punto, límite por minuto y
   dependencia de un tercero para una corrección geométrica. Sí sirve para generar la grilla del
   punto 1 fuera de línea.

**Prueba de regresión.** `tests/test_paralaje_goes.py` fija la geometría (ida y vuelta a 0, 1.000,
3.000 y 5.000 m), la tabla de Santiago a 3.000 m (2,45 km, rumbo 351,8°), un caso sintético de
dentro/fuera y el caso real de Viña 2024 (2.667 detecciones, 1.404 dentro). Cuando se integre el
DEM, la prueba debe agregar el proveedor de altura y un caso de alta cordillera con perímetro
oficial o VIIRS simultáneo.

## 6. Qué se hizo en este PR

- `backend/providers/goes.py`: `latlon_to_scan` y `scan_to_latlon` aceptan una altura opcional.
  `parse_fdc` sigue llamándolas sin altura, así que **las posiciones que se guardan no cambian**.
- `scripts/local/medir_paralaje_goes.py`: medición de solo lectura, con tabla teórica y casos.
- `tests/test_paralaje_goes.py`: geometría, tabla, caso sintético, caso real y guarda del informe.
- Este documento y la actualización de DET-02/INV-05 en `docs/BACKLOG_MAESTRO.md`.

No se tocaron la agrupación, los avisos, la distancia a los lugares guardados ni los datos de los
casos.

## 7. Lo que queda

1. Elegir el DEM y la resolución de la grilla (punto 5.1).
2. Integrar el proveedor de altura en `parse_fdc` y aplicar la corrección antes de agrupar.
3. Guardar la altura y la posición original; decidir si se marca la observación como corregida.
4. Validar con 3-4 incendios de alta cordillera con perímetro oficial (o VIIRS de una pasada
   cercana al nadir) cuando existan; hoy no están en los datos versionados.
5. Recalcular la distancia y el umbral de urgencia con la posición corregida y medir el cambio en
   los avisos antes de desplegar.

## 8. Fuentes

- NOAA/STAR. *GOES-18 ABI L2+ Fire and Hot Spot Characterization (FHS) Full Data Quality Read-Me
  for Data Users*, 17-12-2024, punto 9.
  <https://www.star.nesdis.noaa.gov/atmospheric-composition-training/documents/G18_ABI_FDC_ReadMe.pdf>
- NOAA/STAR. *GOES Imager Projection (ABI Fixed Grid)*.
  <https://www.star.nesdis.noaa.gov/atmospheric-composition-training/satellite_data_goes_imager_projection.php>
- CONAF-GEPRIF. Capa `PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO`; método y licencia en
  `docs/investigacion/INV-03-perimetros.md`.
- Open-Meteo. *Elevation API* (Copernicus DEM 2021 GLO-90, 90 m). Consulta del 20-10-2026.
  <https://open-meteo.com/en/docs/elevation-api>
- Copernicus DEM. DOI de cita: <https://doi.org/10.5270/ESA-c5d3d65>
- Código y datos: `backend/providers/goes.py`, `scripts/local/medir_paralaje_goes.py`,
  `web/data/cases/*.goes.json`, `web/data/cases/*.perimeter.json`.
