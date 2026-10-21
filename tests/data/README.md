# Fixtures de ingesta

Los dos archivos documentados aquí son datos reales, recortados y sin secretos, para probar el
parseo sin red. Capturados el **2026-10-21**. Los demás archivos del directorio
(`fwi_reference.csv`, `glm_lcfa_sample.nc`, `enlaces_simulados.json`) tienen su propio origen y
no son capturas de esta fecha.

## `firms_viirs_sample.csv`

- **Origen:** NASA FIRMS, archivo público de VIIRS Suomi NPP de los últimos 7 días para Sudamérica:
  `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_7d.csv`
- **Producto:** `VIIRS_SNPP_NRT` (VIIRS, Suomi NPP, 375 m).
- **Recorte:** 25 filas de las que caen dentro del territorio chileno (filtro de comunas de BRASA),
  elegidas para cubrir 14 regiones. Se conserva el encabezado y todas las columnas del archivo NRT
  tal como llegan. Incluye una detección real en la comuna de Talca (`-35.42191, -71.63636`,
  2026-10-17 18:24 UTC). La captura es del 2026-10-21; la ventana del archivo 7d del servicio trae
  detecciones del 2026-10-13 al 2026-10-20, aunque la muestra solo conserva hasta el 2026-10-17.
- **Columnas:** el NRT de Suomi NPP trae 13 columnas y no incluye `instrument`; esa columna aparece
  en otros productos FIRMS (por ejemplo, los SP). El fixture no la agrega.
- **Sin clave:** el archivo público no usa `MAP_KEY`; no hay credenciales en el fixture.
- **Frescura:** las fechas son las de adquisición del satélite (`acq_date` + `acq_time`, UTC), no las
  de la captura del archivo.

## `conaf_reportes_sample.json`

- **Origen:** reporte público de incendios de CONAF (GEPRIF):
  `https://raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv`
- **Recorte:** 5 incendios reales; se conservan `id`, temporada, nombre, estado, fecha de inicio,
  superficie, coordenadas, comuna y región. Son datos públicos de incendios, no de personas.
- **Unidades:** `sup_total` llega como texto con coma decimal (`"0,01"`, `"2,00"`, `"2,40"`, `"23,90"`).
  El reporte `893419859` (TICNAMAR) tiene 1 ha y se guarda como entero `1` para fijar el contrato de
  valores enteros; el CSV de origen lo publica como `"1,00"` (mismo valor).
- **Temporada:** se conserva tal como llega del CSV (para estos incendios, `"2026"`); no se normaliza
  al formato `2026-2027` que usan otras filas del reporte.
- **Nota de formato:** el feed vivo de CONAF es CSV, no JSON. Este archivo es una transcripción fiel de
  esas filas para las pruebas de unidades, no un formato que BRASA consuma en producción.
