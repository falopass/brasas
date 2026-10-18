# INV-16 · Industria y antorchas que el satélite ve como calor permanente

> Investigación para BRASA Chile. **Consulta:** 18 de octubre de 2026. **Alcance:** metodología para DET-05/DET-06 y primeros candidatos verificables. **No se procesó FIRMS en esta sesión**: los candidatos son hipótesis de fuente, no celdas confirmadas. Ninguna coordenada se publica sin fuente. Las afirmaciones sobre sensores y productos llevan su fuente.

## Resumen ejecutivo

1. **Método propuesto:** FIRMS SP 2019-2025 (MODIS 1 km + VIIRS 375 m), celdas de 0,01°, conteo de días distintos por celda y año, fracción nocturna, días fuera de la temporada de quemas, exclusión de incendios de CONAF y de volcanes, y revisión manual contra permisos ambientales y empresas.
2. **Dos niveles:** una máscara amplia para FIX-03 (DET-05) y una lista curada para DET-06. La máscara no debe silenciar un incendio real: solo se publica una celda como «fija» cuando hay persistencia fuerte **y** una fuente oficial que explique el calor.
3. **Primeros candidatos:** 12 instalaciones con fuente oficial (refinerías, fundiciones, celulosas, cemento, plantas de gas, relleno sanitario y una acería cerrada). Ninguna está confirmada aún en FIRMS; cada una tiene un paso de verificación y una pista de dónde buscar la coordenada.
4. **Caso Huachipato:** la acería cerró en 2024 y está en proceso de reactivación. Si FIRMS la vio durante años, una máscara estática la seguiría marcando como industria y podría silenciar un incendio futuro. La lista necesita `valid_from` y `valid_to`.
5. **Regla de oro:** sin `coordinate_source` no hay punto publicado; sin fuente oficial no hay nivel A; sin revisión humana no hay máscara.

## 1. Preguntas y método

**Preguntas**

- ¿Qué metodología permite identificar, con FIRMS SP 2019-2025, celdas de calor persistente que no sean incendios?
- ¿Cómo se cruzan esas celdas con fuentes públicas (permisos ambientales, empresas, registros de emisiones) para producir una lista curada?
- ¿Cuáles son los primeros candidatos verificables para DET-06, sin inventar coordenadas?

**Qué se hizo**

- Revisión de la documentación oficial de FIRMS sobre productos, cobertura y latencia.
- Diseño de un algoritmo reproducible de celdas persistentes y reglas de exclusión.
- Revisión de fuentes públicas de 12 instalaciones candidatas (ENAP, Codelco, Glencore/Altonorte, Arauco, CMPC, Melón, KDM y CAP).
- Revisión del caso Huachipato para ilustrar el problema de la validez temporal.
- **No se descargó ni procesó FIRMS**: eso queda como paso de implementación. Los candidatos no están confirmados como celdas persistentes.

## 2. Datos FIRMS SP

### 2.1 Productos y cobertura

| Producto | Sensor | Resolución | Cobertura | Uso en este método |
|---|---|---|---|---|
| MODIS C6.1 (`MODIS_SP`) | Terra y Aqua | 1 km | 1-nov-2000 a hoy | Serie larga; menos sensible a antorchas pequeñas |
| VIIRS 375 m (`VIIRS_SNPP_SP`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_SP`) | Suomi NPP, NOAA-20, NOAA-21 | 375 m | S-NPP desde 20-ene-2012; NOAA-20 desde 1-abr-2018; NOAA-21 desde 17-ene-2024 | Mejor resolución; clave para antorchas y calderas |
| Landsat 30 m | Landsat 8/9 | 30 m | Desde 20-jun-2022 | No es serie principal; apoyo visual |

Fuente: [NASA FIRMS, Archive Download](https://firms.modaps.eosdis.nasa.gov/download/), consultado el 18-oct-2026. La misma página advierte que los datos NRT se reemplazan por datos de calidad científica estándar «with approximately a 5 month lag». Para un análisis retrospectivo 2019-2025 se usa **SP**, no NRT.

**Acceso.** El Archive Download pide Earthdata o un código por correo; se puede solicitar por sensor y rango de fechas, o descargar los archivos diarios. Antes de procesar, conviene verificar con el endpoint de disponibilidad de FIRMS (`/api/data_availability/...`) que cada sensor tiene SP para el periodo; si falta un año, el análisis de persistencia queda sesgado.

**Resolución y significado del píxel.** En MODIS, cada punto representa el centro de un píxel de 1 km; en VIIRS, de 375 m. Fuente: [NASA Earthdata, FIRMS](https://www.earthdata.nasa.gov/data/tools/firms); [GWIS, Active Fire Detection](https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/active-fire-detection). Un píxel caliente no es un incendio: puede ser una antorcha, una caldera, una fundición, un volcán, una quema agrícola o un suelo muy caliente.

**Fin de Suomi NPP.** NASA dejará de entregar observaciones nuevas de Suomi NPP el 2 de noviembre de 2026; el archivo histórico 2019-2025 no se pierde por eso, pero hay que confirmar la disponibilidad del archivo SP (INV-14). Fuente: [NASA Earthdata, Suomi NPP](https://www.earthdata.nasa.gov/data/alerts-outages/suomi-npp-observations-cease-november-2-2026).

### 2.2 Campos que se usan

| Campo | Para qué | Cuidado |
|---|---|---|
| `latitude`, `longitude` | Asignar a celda | Error de geolocalización de hasta ~1 km; no usar el punto como verdad exacta |
| `acq_date`, `acq_time` | Días distintos, estacionalidad | `acq_time` está en UTC; para «nocturno» usar `daynight` |
| `satellite`, `instrument` | Separar sensores | No sumar MODIS y VIIRS sin deduplicar |
| `confidence` | Filtrar detecciones débiles | MODIS usa 0-100; VIIRS usa `l`, `n`, `h`; no son escalas equivalentes |
| `frp` | Ponderar intensidad | No usar FRP como prueba de persistencia: varía con el sensor y la atmósfera |
| `daynight` | Fracción nocturna | Una antorcha suele verse de noche; una planta solar, no |
| `type` (MODIS) | Pista de tipo de fuente | 0 = vegetación, 1 = volcán, 2 = otra fuente, 3 = fuente costa afuera; no excluir solo por `type` |

La documentación de cada producto define los campos y la confianza; para la implementación hay que usar la versión y la guía del producto, no una lista copiada de otro año. Fuente: [NASA FIRMS, FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq).

## 3. Algoritmo de celdas persistentes

### 3.1 Universo de análisis

- **Territorio:** Chile continental, latitud -56,0 a -17,0; longitud -76,0 a -66,0. Excluir Isla de Pascua y Juan Fernández (no están en el rectángulo).
- **Periodo:** 1-ene-2019 a 31-dic-2025.
- **Sensores:** MODIS C6.1 y VIIRS 375 m (S-NPP, NOAA-20 y NOAA-21 cuando exista).
- **Producto:** SP.
- **Filtro de calidad inicial:** MODIS `confidence` ≥ 80; VIIRS `confidence` `h` o `n`; excluir `l`. Hacer un análisis de sensibilidad con umbrales más bajos para no perder antorchas pequeñas.
- **Tierra:** excluir celdas de océano con una máscara de costa; una antorcha costa afuera es posible, pero se revisa aparte.

### 3.2 Cuadrícula y métricas

- **Celda:** 0,01° (~1,1 km en Chile central). Es la misma unidad de DET-05.
- **Sensibilidad:** repetir con 0,005° para VIIRS y comparar; si el resultado cambia mucho, la celda de 0,01° está mezclando fuentes.
- **Métricas por celda y año:**
  - días distintos con al menos una detección;
  - número de detecciones;
  - fracción de detecciones nocturnas;
  - días distintos en abril a noviembre (fuera de la temporada alta de quemas);
  - FRP percentil 90;
  - primera y última fecha;
  - sensor(es) que la detectan.
- **Deduplicación:** una detección por sensor, fecha, hora y ubicación; si MODIS y VIIRS ven el mismo píxel, se cuentan como dos sensores, no como dos días.

### 3.3 Reglas de persistencia

| Nivel | Regla propuesta | Para qué | Confianza |
|---|---|---|---|
| **Máscara DET-05** | ≥ 15 días fuera de diciembre-marzo en 2019-2025; ≥ 3 años con al menos 3 días fuera de temporada; fracción nocturna ≥ 0,15; sin incendio de CONAF a ≤ 5 km en la ventana de ±30 días; fuera de 10 km de un volcán RNVV | Alta sensibilidad para no silenciar incendios; se usa solo con revisión | Media |
| **Lista DET-06** | ≥ 30 días totales; ≥ 4 años con al menos 5 días; ≥ 8 días fuera de temporada; fracción nocturna ≥ 0,20; fuente oficial que explique el proceso | Alta precisión para mostrar «industria» al usuario | Media |
| **Caso dudoso** | Cumple una regla pero no la otra, o no tiene fuente | Se marca `C` y no se publica | Baja |

**Estas cifras son una propuesta de partida, no un estándar publicado.** Se eligen para separar el calor industrial del fuego de vegetación en Chile, donde la temporada de quemas se concentra en diciembre-marzo. Hay que hacer análisis de sensibilidad: si al mover los umbrales ±20 % aparecen o desaparecen muchas celdas, la regla es frágil y hay que revisar a mano. Para instalaciones que abrieron después de 2019, contar solo los años en operación; si son menos de tres, no alcanza para el nivel A.

### 3.4 Exclusiones

1. **Incendios de CONAF.** Para cada celda y año, buscar un incendio oficial a ≤ 5 km y ± 30 días de las detecciones. Si lo hay, excluir ese año. Si todos los años tienen un incendio cerca, la celda es un **área recurrente de incendios**, no una industria. Fuente de los datos: el CSV oficial de incendios que ya usa BRASA (ver [`docs/FUENTES.md`](https://github.com/falopass/brasas/blob/main/docs/FUENTES.md)).
2. **Volcanes.** Excluir celdas a ≤ 10 km de un volcán de la Red Nacional de Vigilancia Volcánica (RNVV). Los volcanes ya son fuentes fijas en BRASA; DET-06 es industria. Fuente: [SERNAGEOMIN, RNVV](https://www.sernageomin.cl/rnvv/).
3. **Plantas solares.** Si la fracción nocturna es < 0,05 y las detecciones son solo diurnas, clasificar como «superficie caliente / solar» y no como industria. Una planta solar no arde de noche.
4. **Quemas agrícolas.** Si la celda solo aparece en diciembre-marzo y cerca de zonas agrícolas, es quema, no industria. La regla de días fuera de temporada la excluye.
5. **Incendios de larga duración.** Un incendio de turberas o de plantación puede durar semanas y parecer persistente. La exclusión de CONAF y la revisión manual lo detectan; si no hay CONAF cerca, revisar la imagen y la estacionalidad.

### 3.5 Agrupación

- Unir celdas vecinas (8 vecinos) en «complejos» para no partir una misma instalación en varias celdas.
- Si un complejo supera 25 celdas (≈ 25 km²), revisar: puede ser un incendio grande, una zona industrial extensa o un artefacto de geolocalización.
- Centroide ponderado por FRP; caja envolvente; área; año de primera y última detección.
- No publicar el centroide como coordenada de la instalación: la coordenada sale de la fuente oficial.

### 3.6 Revisión y clasificación

| Confianza | Qué exige | Se publica |
|---|---|---|
| **A** | Fuente oficial que confirma el proceso (RCA, DIA, SNIFA, RETC o empresa) + coordenada con fuente + persistencia FIRMS + imagen | Sí, con `source_url` y `coordinate_source` |
| **B** | Fuente oficial que confirma la instalación y el proceso, pero falta la coordenada oficial o la imagen | Sí, marcado como «verificado con reserva»; no se usa para silenciar avisos |
| **C** | Solo FIRMS, sin fuente oficial | No; queda como candidato interno |

**Regla de FIX-03:** una celda solo puede silenciar un aviso si tiene confianza A y no hay un incendio de CONAF a ≤ 5 km en la ventana. Si hay duda, no se silencia: se muestra como «posible fuente fija» y se pide moderación.

## 4. Cruzamiento con fuentes públicas

| Fuente | Qué aporta | Cómo se usa | Cuidado |
|---|---|---|---|
| **SEA / e-Seia** | RCA, DIA, declaraciones de impacto, coordenadas UTM, procesos (antorcha, caldera, horno) | Buscar por empresa y comuna; descargar la RCA; extraer la coordenada y el proceso | El permiso puede ser antiguo; verificar si la instalación sigue operando |
| **RETC (MMA)** | Emisiones y transferencias por establecimiento; combustibles y fuentes | Confirmar que hay combustión o antorcha; cruzar el nombre del establecimiento | No todos los procesos declaran; la ausencia no prueba nada |
| **SNIFA (SMA)** | Expedientes de fiscalización, sanciones, descripciones de antorchas | Confirmar antorcha y número de línea (p. ej. L-1360, L-1390) | Un expediente puede ser antiguo; verificar la fecha y el estado |
| **Empresa** | Página oficial, memoria, reporte de sostenibilidad, dirección | Confirmar que la planta existe y qué produce | La empresa puede no publicar coordenadas; no inventarlas |
| **OSM / IDE Chile** | Primera georreferencia | Solo como pista; reemplazar por la coordenada de la RCA | OSM no es una fuente oficial de permisos |
| **CONAF** | Incendios oficiales | Excluir celdas con incendios cercanos | El CSV puede tener atrasos; usar `f_deteccion` y `f_aviso` |
| **SERNAGEOMIN (RNVV)** | Volcanes activos | Excluir volcanes de la lista industrial | Los volcanes ya están en las fuentes fijas de BRASA |

**Cómo se documenta un punto:**

- `name`: nombre de la instalación.
- `kind`: refinería, fundición, celulosa, cemento, relleno, acería, etc.
- `lat`, `lon`: solo si hay `coordinate_source`.
- `coordinate_source`: URL y página del documento oficial (RCA, DIA, SNIFA), no «Google Maps».
- `source_url`: la fuente que confirma el proceso.
- `confidence`: A, B o C.
- `valid_from`, `valid_to`: periodo en que la fuente y FIRMS respaldan la persistencia.
- `firms`: días totales, años presentes, fracción nocturna, días fuera de temporada.
- `last_verified`: fecha de la revisión.

## 5. Primeros candidatos verificables

**No se incluye ninguna coordenada en esta tabla.** En esta sesión no se extrajo una coordenada de una fuente oficial para cada punto. Publicar un punto sin `coordinate_source` violaría la regla de DET-06. La columna «dónde verificar» indica el documento que debe contenerla. Hasta entonces, el candidato no pasa a `persistent_hotspots.json`.

| # | Candidato | Comuna / región | Proceso | Por qué es candidato | Fuente oficial | Estado | Dónde verificar la coordenada |
|---|---|---|---|---|---|---|---|
| 1 | **ENAP Refinería Aconcagua** | Concón, Valparaíso | Refinería de petróleo; antorcha L-1360 | Antorcha documentada en expediente de la SMA; planta en operación | [ENAP, Refinería Aconcagua](https://www.enap.cl/nuestras-operaciones/refinacion-comercializacio/enap-refineria-aconcagua); [SNIFA D-042-2022](https://snifa.sma.gob.cl/General/Descargar/2061200094562) | Antorcha confirmada por SNIFA; **falta celda FIRMS** | RCA 065/2004 y expediente SNIFA |
| 2 | **ENAP Refinería Biobío** | Hualpén, Biobío | Refinería; antorchas L-1320, L-1360 y L-1390 | Antorchas documentadas por ENAP y en la DIA 236546; dirección Camino Lenga 2001 | [ENAP, declaración pública](https://www.enap.cl/sala-de-prensa/declaracion-publica-ii); [SEA, DIA 236546](https://seia.sea.gob.cl/archivos/2016/02/16/01/DIA_236546_DOC_2131185187.pdf); [SNIFA, expediente Biobío](https://snifa.sma.gob.cl/General/Descargar/2062600060122) | Antorcha confirmada; **falta celda FIRMS** | DIA 236546 / RCA de la refinería |
| 3 | **Methanex Cabo Negro** | Punta Arenas, Magallanes | Planta de metanol; antorcha por verificar | Complejo industrial con corrientes gaseosas y operación continua; candidato a calor nocturno | [SEA, expediente 4880](https://www.e-seia.cl/expediente/ficha/fichaPrincipal.php?modo=ficha&id_expediente=4880); [Lenergy, operación a plena capacidad](https://www.lenergygroup.com/por-el-gas-de-vaca-muerta-methanex-busca-operar-su-planta-en-punta-arenas-a-plena-capacidad-de-forma-continua/) | Planta confirmada; **antorcha por verificar** | Expediente SEA 4880 / RCA |
| 4 | **ENAP Planta Posesión** | Punta Arenas, Magallanes | Planta de gas natural; antorcha por verificar | Planta en operación continua desde febrero de 2026; el gas se acondiciona y comprime | [ENAP, reportaje de Magallanes](https://www.enap.cl/files/get/2879); [El Magallánico, 20-mar-2026](https://elmagallanico.com/2026/03/20/enap-reitero-funcionamiento-y-suministro-de-planta-posesion/) | Planta operando; **antorcha por verificar** | RCA / expediente SEA de la planta |
| 5 | **Codelco Fundición Chuquicamata** | Calama, Antofagasta | Fundición de cobre | Fundición y refinería a 15 km al norte de Calama; calor de proceso intermitente | [Codelco, memoria 2023, propiedades](https://www.codelco.com/memoria2023/site/docs/20240522/20240522195731/4__propiedades__instalaciones_y_recursos.pdf) | Fundición confirmada; **calor intermitente, no antorcha** | RCA / SEA de la fundición |
| 6 | **Codelco Fundición Caletones** | Machalí, O'Higgins | Fundición de cobre | Fundición histórica de El Teniente, en la cordillera; calor de proceso | [Codelco, División El Teniente](https://www.codelco.com/operaciones/el-teniente/nosotros/division-el-teniente); [Codelco, 104 años de Caletones](https://www.codelco.com/fundicion-caletones-celebra-104-anos-con-especial-foco-en-la-seguridad-y) | Fundición confirmada; **calor intermitente** | RCA / SEA de Caletones |
| 7 | **Altonorte** | La Negra, Antofagasta | Fundición de cobre | Complejo metalúrgico de Glencore a 25 km de Antofagasta; fundición desde 1993 | [Glencore, Altonorte](https://www.glencore.cl/operaciones-y-empresas-conjuntas/complejo-metalurgico-altonorte) | Fundición confirmada; **calor intermitente** | RCA / SEA de Altonorte |
| 8 | **Arauco, Planta Arauco** | Arauco, Biobío | Celulosa; caldera de recuperación | Planta kraft con calderas y procesos térmicos continuos; dirección Los Horcones S/N | [SNIFA, informe de seguimiento](https://snifa.sma.gob.cl/General/DescargarInformeSeguimiento/258158) | Planta confirmada; **calor de caldera, no antorcha** | RCA / SEA de Planta Arauco |
| 9 | **CMPC, Planta Laja** | Laja, Biobío | Celulosa y papel; calderas | Primera planta kraft de Chile, en la confluencia de los ríos Laja y Biobío | [CMPC Celulosa, Planta Laja](https://www.cmpccelulosa.cl/CMPCCELULOSA/interior.aspx?cid=526) | Planta confirmada; **calor de caldera** | RCA / SEA de Planta Laja |
| 10 | **Melón, Planta La Calera** | La Calera, Valparaíso | Cemento; horno | Planta cementera histórica (1908), con horno de cemento | [Melón, historia](https://www.melon.cl/nosotros/historia/); [Melón, plantas](https://www.melon.cl/productos/cementos/servicios/programacion-y-entrega/) | Planta confirmada; **calor de horno** | RCA / SEA de la planta |
| 11 | **Relleno Sanitario Loma Los Colorados** | Tiltil, Región Metropolitana | Relleno sanitario; antorchas de biogás | Relleno con captura y quema de biogás; se agregaron antorchas para controlar la succión y el abatimiento del biogás; km 63,5 Ruta 5 Norte | [SMA, multa a KDM](https://portal.sma.gob.cl/index.php/sma-aplica-multa-a-kdm-por-infraccion-grave-relativa-al-tratamiento-de-liquidos-percolados-del-relleno-lomas-los-colorados/); [Induambiente, «Poder eléctrico»](https://www.induambiente.com/especial/residuos/poder-electrico) | Antorcha confirmada; **falta celda FIRMS** | RCA del relleno / expediente SEA |
| 12 | **CAP Acero Huachipato** | Talcahuano, Biobío | Acería; coquería y alto horno | Caso de transición: cerró en 2024 y se anunció su reactivación en 2026; no usar como fuente actual | [Cooperativa, 5-jun-2026](https://www.cooperativa.cl/noticias/pais/region-del-biobio/revive-la-siderurgica-huachipato-aza-compro-cap-en-us-130-millones/2026-06-05/114834.html); [Ex-Ante, 4-jun-2026](https://www.ex-ante.cl/negocios/huachipato-como-sera-el-retorno-de-la-planta-siderurgica-que-cerro-hace-21-meses-y-los-detalles-del-acuerdo-del-grupo-cap-y-aza/) | Cerrada en 2024; **en reactivación** | RCA / SEA de Huachipato y fecha de cierre |

**Cómo se verifica cada candidato (3 pasos):**

1. **Celda FIRMS:** comprobar que la celda de 0,01° tiene días suficientes, fracción nocturna y años repartidos; si no, el candidato no entra.
2. **Coordenada oficial:** abrir la RCA, DIA o expediente, ubicar la coordenada UTM o geográfica y registrarla con URL y página; si no está, dejar el punto como «sin coordenada» y no publicarlo.
3. **Imagen:** revisar Sentinel-2/Landsat o Google Earth para confirmar que en el punto hay una instalación, no un incendio ni un campo.

## 6. El caso Huachipato: por qué la máscara necesita fecha

Huachipato es una acería histórica en Talcahuano. En 2024, CAP informó el cese de operaciones de su filial; en junio de 2026 se anunció la compra por Aceros AZA y un plan de reactivación. Fuentes: [Cooperativa, 5-jun-2026](https://www.cooperativa.cl/noticias/pais/region-del-biobio/revive-la-siderurgica-huachipato-aza-compro-cap-en-us-130-millones/2026-06-05/114834.html); [Ex-Ante, 4-jun-2026](https://www.ex-ante.cl/negocios/huachipato-como-sera-el-retorno-de-la-planta-siderurgica-que-cerro-hace-21-meses-y-los-detalles-del-acuerdo-del-grupo-cap-y-aza/).

**Qué implica para la máscara:**

- Si Huachipato aparece en FIRMS 2019-2024, una lista estática la marcaría como industria para siempre.
- Si la planta se reactiva y ocurre un incendio en el mismo predio, la máscara podría silenciarlo. Es exactamente el falso negativo que FIX-03 quiere evitar.
- La solución es `valid_to`: la celda deja de ser «fija» cuando la planta cierra; si se reactiva, se vuelve a evaluar con datos nuevos, no con la persistencia histórica.

**Regla:** toda entrada de DET-06 debe tener `valid_from` y `valid_to` (o `null` si sigue operando). La máscara se recalcula cada año y se revisa cuando una instalación abre, cierra o cambia de proceso.

## 7. Salida para DET-06

### 7.1 Campos del archivo curado

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `id` | texto | Sí | `CL-FIX-001`, estable |
| `name` | texto | Sí | Nombre de la instalación |
| `kind` | enum | Sí | `refineria`, `fundicion`, `celulosa`, `cemento`, `relleno`, `aceria`, `planta_gas`, `otro` |
| `lat`, `lon` | número | Solo con fuente | Si falta `coordinate_source`, no se publica |
| `coordinate_source` | URL + página | Sí para A/B | RCA, DIA, SNIFA; no OSM ni Google Maps |
| `municipality`, `region` | texto | Sí | División administrativa |
| `source_url` | URL | Sí | Fuente que confirma el proceso |
| `confidence` | A/B/C | Sí | Solo A y B se publican |
| `valid_from`, `valid_to` | fecha / null | Sí | Cierre o reactivación |
| `firms` | objeto | Sí | Días, años, fracción nocturna, días fuera de temporada |
| `last_verified` | fecha | Sí | Última revisión |
| `notes` | texto | No | Proceso, antorcha, número de línea |

### 7.2 Flujo de revisión

1. **Candidato:** aparece en FIRMS o en una fuente oficial.
2. **Triaje:** ¿cumple persistencia? ¿Tiene fuente? ¿Tiene coordenada?
3. **Revisión de escritorio:** RCA/SEA, RETC, SNIFA, empresa, imagen.
4. **Clasificación:** A, B o C.
5. **Publicación:** solo A y B; el JSON se versiona con fecha.
6. **Revisión anual:** cierres, aperturas, cambios de proceso; comparar con incendios de CONAF.
7. **Retiro inmediato:** si un incendio real ocurre en una celda marcada como fija, retirar la celda y revisar la regla.

### 7.3 Relación con DET-05 y FIX-03

- **DET-05** produce la máscara (`persistent_hotspots.json`) para que FIX-03 no dependa solo de la regla dinámica.
- **DET-06** produce la lista curada con fuente por punto, para mostrar «industria» en la ficha y explicar por qué no se avisa.
- **FIX-03** usa la máscara solo si la celda es A y no hay un incendio de CONAF cerca; la regla dinámica queda como respaldo.
- **Nunca** usar la lista para ocultar un incendio: la lista explica el calor, no lo justifica.

## 8. Fuentes consultadas (18 de octubre de 2026)

| Fuente | URL | Fecha | Qué sostiene |
|---|---|---|---|
| NASA FIRMS, Archive Download | <https://firms.modaps.eosdis.nasa.gov/download/> | Consultado 18-oct-2026 | Productos, cobertura, latencia SP ~5 meses |
| NASA Earthdata, FIRMS | <https://www.earthdata.nasa.gov/data/tools/firms> | Consultado 18-oct-2026 | Píxel MODIS 1 km y VIIRS 375 m |
| NASA Earthdata, FAQ | <https://www.earthdata.nasa.gov/data/tools/firms/faq> | Consultado 18-oct-2026 | Documentación de productos y confianza |
| NASA Earthdata, fin de Suomi NPP | <https://www.earthdata.nasa.gov/data/alerts-outages/suomi-npp-observations-cease-november-2-2026> | Consultado 18-oct-2026 | Fin de observaciones nuevas el 2-nov-2026 |
| GWIS, Active Fire Detection | <https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/active-fire-detection> | Consultado 18-oct-2026 | Resolución MODIS 1 km / VIIRS 375 m |
| ENAP, Refinería Aconcagua | <https://www.enap.cl/nuestras-operaciones/refinacion-comercializacio/enap-refineria-aconcagua> | Consultado 18-oct-2026 | Planta en Concón |
| SNIFA, D-042-2022 | <https://snifa.sma.gob.cl/General/Descargar/2061200094562> | Consultado 18-oct-2026 | Antorcha L-1360 y RCA 065/2004 |
| ENAP, declaración pública | <https://www.enap.cl/sala-de-prensa/declaracion-publica-ii> | Consultado 18-oct-2026 | Antorchas de Refinería Biobío |
| SEA, DIA 236546 | <https://seia.sea.gob.cl/archivos/2016/02/16/01/DIA_236546_DOC_2131185187.pdf> | Consultado 18-oct-2026 | Antorcha L-1360, dirección Camino Lenga 2001 |
| SNIFA, expediente Biobío | <https://snifa.sma.gob.cl/General/Descargar/2062600060122> | Consultado 18-oct-2026 | Antorcha L-1390 con llama activa |
| SEA, Methanex Cabo Negro | <https://www.e-seia.cl/expediente/ficha/fichaPrincipal.php?modo=ficha&id_expediente=4880> | Consultado 18-oct-2026 | Complejo de metanol en Punta Arenas |
| Lenergy, Methanex | <https://www.lenergygroup.com/por-el-gas-de-vaca-muerta-methanex-busca-operar-su-planta-en-punta-arenas-a-plena-capacidad-de-forma-continua/> | Consultado 18-oct-2026 | Operación de dos trenes |
| ENAP, reportaje Magallanes | <https://www.enap.cl/files/get/2879> | Consultado 18-oct-2026 | Planta Posesión |
| El Magallánico, Posesión | <https://elmagallanico.com/2026/03/20/enap-reitero-funcionamiento-y-suministro-de-planta-posesion/> | 20-mar-2026 | Operación continua desde el 18-feb-2026 |
| Codelco, memoria 2023 | <https://www.codelco.com/memoria2023/site/docs/20240522/20240522195731/4__propiedades__instalaciones_y_recursos.pdf> | Consultado 18-oct-2026 | Chuquicamata a 15 km de Calama |
| Codelco, El Teniente | <https://www.codelco.com/operaciones/el-teniente/nosotros/division-el-teniente> | Consultado 18-oct-2026 | Ubicación de Caletones |
| Codelco, 104 años de Caletones | <https://www.codelco.com/fundicion-caletones-celebra-104-anos-con-especial-foco-en-la-seguridad-y> | Consultado 18-oct-2026 | Fundición Caletones |
| Glencore, Altonorte | <https://www.glencore.cl/operaciones-y-empresas-conjuntas/complejo-metalurgico-altonorte> | Consultado 18-oct-2026 | Fundición en La Negra |
| SNIFA, Planta Arauco | <https://snifa.sma.gob.cl/General/DescargarInformeSeguimiento/258158> | Consultado 18-oct-2026 | Dirección Los Horcones S/N |
| CMPC, Planta Laja | <https://www.cmpccelulosa.cl/CMPCCELULOSA/interior.aspx?cid=526> | Consultado 18-oct-2026 | Planta kraft en Laja |
| Melón, historia | <https://www.melon.cl/nosotros/historia/> | Consultado 18-oct-2026 | Planta La Calera desde 1908 |
| Melón, plantas | <https://www.melon.cl/productos/cementos/servicios/programacion-y-entrega/> | Consultado 18-oct-2026 | Lista de plantas |
| SMA, Loma Los Colorados | <https://portal.sma.gob.cl/index.php/sma-aplica-multa-a-kdm-por-infraccion-grave-relativa-al-tratamiento-de-liquidos-percolados-del-relleno-lomas-los-colorados/> | 4-jul-2022 | Ubicación en Tiltil |
| Induambiente, «Poder eléctrico» | <https://www.induambiente.com/especial/residuos/poder-electrico> | Consultado 18-oct-2026 | Antorchas para controlar la succión y el abatimiento del biogás en Loma Los Colorados |
| Cooperativa, Huachipato | <https://www.cooperativa.cl/noticias/pais/region-del-biobio/revive-la-siderurgica-huachipato-aza-compro-cap-en-us-130-millones/2026-06-05/114834.html> | 5-jun-2026 | Cierre 2024 y compra por AZA |
| Ex-Ante, Huachipato | <https://www.ex-ante.cl/negocios/huachipato-como-sera-el-retorno-de-la-planta-siderurgica-que-cerro-hace-21-meses-y-los-detalles-del-acuerdo-del-grupo-cap-y-aza/> | 4-jun-2026 | Reactivación y plazos |
| SERNAGEOMIN, RNVV | <https://www.sernageomin.cl/rnvv/> | Consultado 18-oct-2026 | Volcanes activos |

## 9. Límites de esta investigación

- **No se procesó FIRMS.** Los 12 candidatos son hipótesis de fuente; ninguno está confirmado como celda persistente. El paso siguiente es implementar el algoritmo y revisar los resultados.
- **No hay coordenadas.** No se extrajo una coordenada oficial para cada punto; publicarlas sin `coordinate_source` violaría la regla de DET-06.
- **Los umbrales son una propuesta.** No provienen de un estándar publicado; se basan en la separación entre temporada de quemas y actividad industrial en Chile. Hay que hacer sensibilidad y revisión manual.
- **MODIS de 1 km puede no ver una antorcha pequeña.** VIIRS de 375 m es mejor, pero también tiene límites; una antorcha puede quedar subpixel.
- **La nubosidad del sur de Chile** reduce el número de detecciones; la persistencia es un límite inferior, no un censo.
- **El periodo 2019-2025 incluye la pandemia.** La actividad industrial cayó en 2020; por eso se exige persistencia en varios años, no en años consecutivos.
- **Las fuentes oficiales pueden estar desactualizadas.** Un permiso de 2004 no prueba que la antorcha siga encendida; hay que cruzar con la operación actual y con FIRMS.
- **La lista no es una verdad jurídica.** Que una instalación tenga RCA no significa que el calor observado sea suyo; la coincidencia espacial y temporal es una hipótesis, no una prueba.
- **No se usó VIIRS Nightfire** ni imágenes nocturnas de alta resolución; sería una validación independiente recomendable para una segunda fase.
