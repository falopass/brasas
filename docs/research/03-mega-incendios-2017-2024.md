# Mega incendios en Chile, 2017-2024: cifras oficiales y dato por comuna

> Investigación para BRASAS. Consulta del 18 de octubre de 2026. Cada cifra lleva su organismo, su fecha de corte y su enlace; cuando hay dos cifras oficiales se muestra el rango. Lo que no se pudo verificar se marca **NO VERIFICADO**.

## Resumen

1. **570.197,4 ha (2017) y 429.103,0 ha (2023) son totales de temporada** (1 de julio a 30 de junio), no de un incendio ni de un episodio. Compararlos con la superficie de un incendio concreto es el error más frecuente en la prensa y en las apps.
2. En 2024, el complejo «Las Tablas–Reserva Lago Peñuelas» explica **8.656,5 ha**; la región de Valparaíso quemó **15.219,9 ha** en toda la temporada.
3. **Víctimas:** 11 en 2017 (ONEMI), 26 en 2023 (SENAPRED, con un reporte previo de 24) y 137 → 138 en 2024 (Fiscalía y Juzgado de Garantía).
4. **El dato por comuna existe, con dos formas distintas:** una tabla agregada por temporada (XLSX de CONAF, 1985-86 a 2023-24) y un microdato geoespacial por incendio (SHP de IDE Minagri). La primera necesita limpieza: sus totales no cuadran con el total oficial. El segundo trae `COMUNA` completo en 2022-2024 y **vacío en 2016-2017**.
5. La consecuencia de diseño es clara: la vista Historia debe separar **temporada**, **incendio**, **víctimas** y **viviendas**, cada uno con su fuente y su fecha de corte.

## 1. Tabla por evento

| Evento | Fechas | Regiones y comunas | Superficie | Víctimas | Viviendas | Fuente |
|---|---|---|---|---|---|---|
| **«Tormenta de Fuego»** | Focos desde el 20-01-2017; enero y febrero de 2017 | Maule, O'Higgins y Biobío (además de RM y Valparaíso). Comunas: Cauquenes, Chanco, San Javier, Empedrado, Constitución (Santa Olga, Los Aromos, Nirivilo), San Fabián, Tomé | **570.197,4 ha** en la temporada 2016-2017. Por región: Maule 252.556,1; Biobío 119.409,1; O'Higgins 105.542,9. Mayor incendio: «Las Máquinas», **159.812,6 ha** | **11 fallecidos**, 39 heridos, 14.700 evacuados | **2.571 destruidas** (3.885 afectadas) | ONEMI, *Informe Estadístico Anual 2017*; CONAF, estadísticas de temporada |
| **Incendios de Ñuble, Biobío y Araucanía** | 1 al 28 de febrero de 2023 | Biobío, Araucanía, Ñuble (además de Maule y Los Ríos). Comunas: Nacimiento, Florida, Quillón, Ninhue, Galvarino, Angol | **429.103,0 ha** en la temporada 2022-2023. Por región: Biobío 181.796,1; Araucanía 116.723,7; Ñuble 57.158,4. Mayor incendio: «Santa Ana», **69.080,5 ha** | **26** (Biobío 18, Araucanía 7, Ñuble 1). Un reporte oficial del 07-02-2023 consigna 24 | 1.145 a 1.159 destruidas a comienzos de febrero; consolidado final **NO VERIFICADO** | CONAF; SENAPRED |
| **Megaincendio de Valparaíso** | 2 y 3 de febrero de 2024 | Valparaíso (Placilla), Viña del Mar (Villa Independencia, Jardín Botánico), Quilpué, Villa Alemana | **8.656,5 ha** en el registro «Complejo Las Tablas–Reserva Lago Peñuelas»; **15.219,9 ha** en toda la región en la temporada | **137** (Fiscalía, abril de 2025) y **138** (Juzgado de Garantía, mayo de 2025) | **NO VERIFICADO**: no se halló consolidado oficial | CONAF; Fiscalía vía La Tercera; Juzgado de Garantía vía La Tercera |
| **Otras temporadas** | 2019-2020; 2020-2021; 2021-2022 | Nacional | 102.291,7 ha; 35.622,9 ha; 125.335,1 ha | — | — | CONAF |

Lectura: el megaincendio de 2024 explica poco más de la mitad de la superficie regional de esa temporada; en 2017 y 2023, en cambio, las cifras que circulan son el total de la temporada completa.

## 2. ¿Existe dato oficial por comuna?

### 2.1 Tabla agregada: sí, pero es una hoja de trabajo, no una base de datos

El conjunto «Resumen de ocurrencia y daño por comuna, 1985 - 2024» del Centro Documental de CONAF es un **XLSX de 2.577.710 bytes con 40 hojas**, una por temporada (`84-85 oK`, `1985-1986` … `2023-2024`). Cada hoja mide **A1:U386**, se titula «RESUMEN NACIONAL DE OCURRENCIA POR COMUNAS» y contiene columnas `REGION`, `PROVINCIA`, `COMUNA`, `SUPERFICIE TOTAL` y un desglose de daño por tipo de vegetación (pino insigne por edad, eucalipto, otras especies, arbolado, matorral, pastizal, desechos) hasta `TOTAL SUPERFICIE AFECTADA`.

Verificación de primera mano (2026-10-18), hoja 2016-2017: **360 filas con nombre de comuna para 346 comunas distintas**, y `COMUNA` completo en todas las filas.

**Pero no se puede ingerir a ciegas.** Al sumar la columna de totales de esa hoja sale **1.613.842,4 ha**, unas 2,8 veces el total oficial de la temporada (570.197,4 ha), y solo 279 filas tienen valor numérico. Hay filas repetidas, subtotales o celdas combinadas. Conclusión: sirve para **consultar una comuna concreta**, no para sumar; cualquier ingesta debe validarse contra el total oficial de temporada.

### 2.2 Microdato geoespacial: el mejor dato por incendio

El IDE Minagri / Geoportal de Chile publica por temporada (2010-2011 a 2024-2025) la «Localización de Incendios Forestales a nivel de Puntos (CONAF)» en SHP y WMS. Campos verificados en el DBF: `REGION`, `PROVINCIA`, `COMUNA`, `NOM_INCEN`, `CAUSA_GENE`, desglose de superficie por tipo (`PINO`, `EUCALIPTO`, `MATORRAL`, `PASTIZAL`…) y `SUPERFICIE`.

Cobertura del campo `COMUNA`, medida sobre los archivos:

- **2022-2023 y 2023-2024: 100 %** (4.972 incendios en 2023-2024).
- **2016-2017: 0 %** (5.234 registros con el campo vacío).

Es decir: para 2017 **no hay comuna en el microdato**, aunque el relato de ONEMI nombre las comunas afectadas. La licencia es un metadato ISO 19115 con `otherRestrictions` y la leyenda «La información es de carácter público. La única restricción es que debe tener citada la fuente»: no es Creative Commons, es atribución obligatoria.

### 2.3 SENAPRED: viviendas y personas, no superficie

Los informes estadísticos anuales de SENAPRED (2023 y 2024) traen tablas comunales de **viviendas y personas** por evento, pero **no de superficie quemada**. Para la ficha de Historia son la fuente correcta para daño humano y habitacional.

### 2.4 Lo que no existe

- **Estadística agregada por comuna en el archivo de hectáreas por región:** ese archivo (1977-2024) está rotulado «POR REGION» y no trae comunas.
- **`snif.conaf.cl`:** el dominio **no resuelve por DNS** (verificado el 2026-10-18).
- **datos.gob.cl:** no hay dataset de CONAF sobre incendios; las búsquedas devuelven resultados de DIPRES o del MMA.
- **INFOR:** no se localizó anuario con desagregación comunal; la ruta de publicaciones devuelve 404. **NO VERIFICADO.**
- **La antigua URL** `conaf.cl/.../estadisticas-historicas/` devuelve **404**: el enlace estable hoy es el Centro Documental.

### 2.5 Veredicto

Para la vista Historia: **SHP por temporada** para los incendios nominados desde 2022-2023 (con comuna fiable), **XLSX por comuna** para la serie larga con validación previa, **SENAPRED** para viviendas y personas, y **relato de ONEMI** para las comunas de 2017, donde el microdato no las trae.

## 3. Discrepancias y cómo declararlas

1. **Temporada contra evento contra comuna.** «570.000 ha» y «429.000 ha» son temporadas; «8.656,5 ha» es un incendio. Mezclarlas produce comparaciones falsas.
2. **Víctimas 2017: 11** (ONEMI, consolidado anual). Circulan 10 en documentos parlamentarios que no se pudieron abrir: no usarlos sin fuente.
3. **Víctimas 2023: 24 y 26**, ambas oficiales en fechas distintas. Mostrar el rango con la fecha de cada corte.
4. **Víctimas 2024: 137 → 138.** La serie no es un error: es una corrección judicial. Mostrar la serie, no solo el último número.
5. **Superficie 2024: 8.656,5 ha** (complejo) frente a **15.219,9 ha** (región y temporada). Las cifras de «30.000 a 43.000 ha» que circularon esos días no se pudieron verificar en fuente oficial.
6. **Viviendas 2023: 1.145 frente a 1.159** según el día del balance. En 2017, 2.571 destruidas es el consolidado anual; los conteos diarios de enero fueron menores.
7. **Regla de estilo:** toda cifra con organismo, fecha de corte y enlace; si hay dos oficiales, rango y ambas fuentes.

## 4. Literatura con DOI

Metadatos verificados en Crossref el 2026-10-18.

| Trabajo | Medio y año | DOI |
|---|---|---|
| de la Barrera et al., «Megafires in Chile 2017: Monitoring multiscale environmental impacts of burned ecosystems» | Science of The Total Environment, 2018 | [10.1016/j.scitotenv.2018.05.119](https://doi.org/10.1016/j.scitotenv.2018.05.119) |
| «Modeling the Ignition Risk: Analysis before and after Megafire on Maule Region, Chile» | Applied Sciences, 2022 | [10.3390/app12189353](https://doi.org/10.3390/app12189353) |
| «Salud Mental y Apoyo Psicosocial Durante la Emergencia y Desastre: Incendios Forestales de 2024 en la Región de Valparaíso, Chile» | REDER, 2025 | [10.55467/reder.v9i1.174](https://doi.org/10.55467/reder.v9i1.174) |
| «Wildfire Scar Detection in Mediterranean Chile Using Sentinel-1 InSAR Coherence and Machine Learning: The 2017 "Las Máquinas" Megafire» | Remote Sensing, 2026 | [10.3390/rs18183105](https://doi.org/10.3390/rs18183105) |

No se citan resultados de estos trabajos porque no se leyó su texto completo en esta sesión: se usan como puerta de entrada bibliográfica.

## 5. Qué mostrar en la vista Historia

1. **Cuatro campos separados y rotulados:** temporada (ha totales y por región), incendio nominado (comuna y ha), víctimas (organismo y fecha de corte) y viviendas (o «sin cifra oficial consolidada»). Criterio de aceptación: ninguna tarjeta mezcla temporada con evento.
2. **Sello «cifra al DD-MM-AAAA» y enlace primario estable** (Centro Documental de CONAF, BiblioGRD, Geoportal), nunca un titular de prensa.
3. **Serie de correcciones visible:** 137 → 138 en 2024, 24 → 26 en 2023. Criterio: la ficha muestra la serie, no solo el último valor.
4. **Comunas de 2017 desde el relato de ONEMI**, no desde la capa, porque el campo `COMUNA` está vacío en esa temporada.
5. **Nota metodológica visible:** la superficie oficial es de temporada y el dato por comuna solo es completo como microdato desde 2022-2023.

## 6. Fuentes consultadas (18 de octubre de 2026)

- CONAF, «Hectáreas por incendio nacional de incendios forestales por región, 1977-2024»: <https://www.conaf.cl/centro-documental/hectareas-por-incendio-nacional-de-incendios-forestales-por-region-1977-2023/>.
- CONAF, «Resumen de ocurrencia y daño por comuna, 1985-2024»: <https://www.conaf.cl/centro-documental/resumen-de-ocurrencia-y-dano-por-comuna-1985-2023/>.
- CONAF, Centro Documental de estadísticas históricas: <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>.
- IDE Minagri, descarga de capas de desastres: <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>; metadato ISO del conjunto de puntos (revisión del 22-11-2025): <https://geoportal.cl/index.php/geoportal/catalog/xml?identifier=01d06ae3-122e-41fc-9512-1dd2b5067112>.
- ONEMI, *Informe Estadístico Anual 2017*: <https://bibliogrd.senapred.gob.cl/bitstream/handle/2012/1818/InfEstAnualONEMI2017.pdf?sequence=1&isAllowed=y>.
- SENAPRED, reporte del 07-02-2023: <https://www.senapred.cl/2023/02/07/autoridades-entregaron-nuevo-reporte-por-incendios-entre-maule-y-los-lagos/>; *Informe Estadístico Anual 2023*: <https://bibliogrd.senapred.gob.cl/bitstream/handle/1671/6451/Informe_Estad%c3%adstico_2023.pdf?sequence=4&isAllowed=y>; *Informe Estadístico 2024*: <https://bibliogrd.senapred.gob.cl/bitstream/handle/1671/7051/Informe_Estad%c3%adstico_2024.pdf?sequence=4&isAllowed=y>.
- La Tercera, 23-04-2025: <https://www.latercera.com/nacional/noticia/fiscalia-aclara-cifra-de-fallecidos-por-megaincendio-en-valparaiso-y-prepara-reformalizacion-para-siete-presuntos-autores/>; 22-05-2025: <https://www.latercera.com/nacional/noticia/megaincendio-en-valparaiso-fiscalia-confirma-138-fallecidos-y-tribunal-extiende-plazo-de-investigacion/>.
- BCN, Asesoría Técnica Parlamentaria, *Incendios Forestales. Período 2019-2024. Estadísticas*, noviembre de 2025, Nº SUP 151.240: <https://obtienearchivo.bcn.cl/obtienearchivo?id=repositorio/10221/37942/1/Estadistica_Incendios_Forestales.pdf>.
- Crossref, metadatos de los cuatro DOI: <https://api.crossref.org/works/10.1016/j.scitotenv.2018.05.119>.

## 7. Límites de esta investigación

- **NO VERIFICADO:** el consolidado final de viviendas de 2023 y la cifra de viviendas de 2024; el contenido del informe de la Comisión Especial Investigadora de la Cámara (su sitio devuelve 403); y los resultados de los cuatro papers, que no se leyeron completos.
- Las cifras de CONAF se leyeron de sus archivos oficiales, pero **no se reconstruyó la serie completa**: se verificaron las temporadas citadas.
- La estructura interna del XLSX por comuna (filas repetidas y subtotales) se comprobó por suma, no documento a documento. La conclusión operativa —no ingerir sin validación— se sostiene con esa medición.