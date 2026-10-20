# INV-03 · Perímetros oficiales de CONAF en los casos de Historia (CONT-08)

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** cubre la capa histórica usada por los casos; el perímetro del incendio en curso (ficha de incidente) es OFI-17 y usa otra capa (`Perimetro_final`). Cada afirmación lleva su fuente o el resultado de la consulta ejecutada.

## Resumen ejecutivo

1. La vía oficial es la capa **`PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO`** («COMPILADO OPERATIVO 2014-2025») del FeatureServer público de CONAF-GEPRIF: consulta anónima, `f=geojson`, `outSR=4326`, con simplificación en el servidor (`maxAllowableOffset`).
2. **Licencia:** los ítems de GEPRIF declaran los datos «de uso público» con la obligación de citar a CONAF (`docs/research/fuentes-meteologix-geprif.md`, §2). Cada archivo publicado lleva `source` y `license`, y la vista muestra la atribución «CONAF — GEPRIF».
3. **Quedaron con perímetro 3 de 6 casos:** `las-maquinas-2017` (1 polígono, 192.158 ha), `vina-del-mar-2024` (4 polígonos, 10.484 ha) y `nuble-biobio-araucania-2023` (106 polígonos, 270.421 ha).
4. **Sin perímetro (no se inventa ni se aproxima):** `torres-del-paine-2011` (anterior a la capa), `valparaiso-2014` (no está en el compilado) y `penco-lirquen-2026` (temporada 2025-26 aún no incorporada).
5. `web/js/views/casos.js` muestra la capa «Perímetro oficial CONAF» **apagada por defecto**, con entrada en la leyenda y carga diferida: el GeoJSON se descarga solo al encenderla.

## 1. Fuente y consulta

| Qué | Valor |
|---|---|
| Endpoint | `https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO/FeatureServer/0/query` |
| Geometría | Polígono/MultiPolígono, nativo UTM 19S (EPSG:32719); se pide `outSR=4326` |
| Campos usados | `FID`, `Nombre` («320 - LAS MAQUINAS»), `Región`, `inicio` (fecha, sin hora), `SEMANA`, `Temporada` («2016-2017»), `HA`, `TIPOLOGÍA` |
| Filtro | `Temporada=<del caso>` + envolvente del `bbox` del caso (`esriSpatialRelIntersects`) |
| Simplificación | `maxAllowableOffset` según el alcance: 0,0005° en incendio único, 0,001° en complejo, 0,002° en episodio y 0,004° en temporada (≈50–430 m; el episodio junta decenas de polígonos y a máximo detalle pesaba 8,4 MB) |
| Fecha de consulta | 19-10-2026 (cada archivo registra su `fetched_at`) |
| Licencia | «Uso público» con cita a CONAF (declaración de los ítems de GEPRIF; la confirmación formal sigue siendo OFI-03) |

`scripts/local/build_perimetros_casos.py` corre la consulta por caso, guarda el crudo en `data/cache/geprif_perimetros/` (no versionado, `--refresh` re-descarga) y escribe `web/data/cases/<id>.perimeter.json` solo cuando hay polígonos que calzan.

## 2. Regla de empareje

Un polígono pertenece al caso si cumple **todas** estas condiciones:

1. `Temporada` igual a la del caso. La temporada de ocurrencia de CONAF corre de julio a junio: un incendio de febrero de 2023 es «2022-2023».
2. `inicio` dentro de `start_utc − 5 días` a `end_utc + 5 días` del caso. Tolerancia explícita: el inicio oficial puede ser unos días antes o después del primer dato satelital (Las Máquinas: caso 18-ene, oficial 20-ene).
3. Solo en `scope: fire`, el nombre oficial (sin el correlativo «320 - ») debe compartir una palabra significativa (≥4 letras, sin genéricas como «incendio») con el título del caso. Sin esto, la envolvente de Las Máquinas arrastraría los incendios vecinos de enero de 2017 (Santa Cruz, La Palmilla…). En `complex`, `episode` y `season` no se filtra por nombre: cada polígono es un foco distinto que se unió al caso, y se publican **todos** los que calzan.

Los campos del empareje quedan registrados en cada archivo (`match`: temporada, ventana de inicio, si hubo filtro por nombre y la simplificación aplicada).

## 3. Resultado por caso

| Caso | Polígonos | Ha oficial | Observación |
|---|---|---|---|
| `las-maquinas-2017` | 1 | 192.158 | «320 - LAS MAQUINAS», inicio oficial 20-ene-2017 |
| `vina-del-mar-2024` | 4 | 10.484 | «COMPLEJO LAS TABLAS- RESERVA LAGO PEÑUELAS» (8.807 ha) + «LO MOSCOSO», «SAN PEDRO» y «TRANQUE LA LUZ 3», todos con inicio 02-feb-2024 |
| `nuble-biobio-araucania-2023` | 106 | 270.421 | Todos los focos de la temporada 2022-2023 con inicio entre el 27-ene y el 20-feb-2023 dentro de la envolvente del episodio |
| `valparaiso-2014` | — | — | Abril de 2014 pertenece a la temporada 2013-2014, que la capa no registra: el compilado parte en 2014-2015 (consulta `Temporada='2013-2014'` → 0 polígonos) |
| `torres-del-paine-2011` | — | — | La capa parte en la temporada 2014-2015; diciembre de 2011 queda fuera de su cobertura |
| `penco-lirquen-2026` | — | — | Temporada 2025-26, posterior al compilado (última edición de datos: marzo de 2026). La vía para perímetros de la temporada en curso es `Perimetro_final` (OFI-17) |

## 4. Límites conocidos

- Las superficies de la capa son las del perímetro oficial medido por CONAF y pueden diferir de las cifras de prensa citadas en `figures` del caso (por ejemplo, el megaincendio 2024 suele citarse como «≈9.800 ha» y la capa suma 10.484 ha en los cuatro focos).
- La envolvente del episodio 2023 cubre solo Ñuble, Biobío y La Araucanía: focos del mismo megaincendio fuera de esa zona (por ejemplo, al sur) no entran, por diseño.
- La simplificación del episodio (~170 m) basta para ver el conjunto a escala regional; para detalle fino el archivo original se puede re-descargar sin `maxAllowableOffset`.
- La capa es operativa y se reedita: un `--refresh` futuro puede cambiar cantidades o superficies. El caché crudo permite auditar qué respondió el servicio en cada corrida.
