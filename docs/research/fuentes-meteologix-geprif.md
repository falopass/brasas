# ¿Sirven meteologix.com/cl y deigeprif.com para BRASA?

> Investigación del 19 de octubre de 2026 (INV-FUENTES). Se revisaron ambos sitios con la herramienta fetch y las APIs públicas que quedaron a la vista. Conclusión corta: **meteologix.com no aporta nada que BRASA no tenga ya y sus condiciones lo prohíben; deigeprif.com es el hub oficial del Departamento de Estudios e Investigación de GEPRIF-CONAF y abre la puerta a varias fuentes nuevas con licencia declarada de uso público.**

## 1. meteologix.com/cl

### Qué es

El portal en español para Chile de **Meteologix AG (Kachelmann Group)**, empresa privada suizo-alemana. Es un visor de mapas meteorológicos para usuarios finales: mapas de modelos (ECMWF IFS, GFS, ICON, UKMO, ~30 modelos en total), meteogramas por punto, observaciones, satélite, radar y rayos.

### Qué datos ofrece que sirvan a BRASA

Viento, temperatura, humedad relativa, precipitación, índices de incendio y rayos, a nivel de mapa o meteograma puntual, con cobertura mundial (Chile incluido). **Todo eso ya lo cubre BRASA** con Open-Meteo (pronóstico horario 7 días), el FWI propio, la regla 30-30-30, los avisos CAP de la DMC y las capas de pronóstico de CONAF. Lo único que Meteologix tiene y BRASA no es el modelo propio **SuperHD 1×1 km** y su feed de rayos — nichos que no cambian ninguna decisión ciudadana hoy.

### Cómo se obtendría

- **El portal no ofrece feed ni descargas**: es una aplicación web de mapas. La herramienta fetch recibe HTTP 403 (WAF) incluso para `robots.txt`, así que su política de scraping no se pudo verificar de primera mano — **NO VERIFICADO**, pero el patrón del grupo (WAF + API de pago) indica que el portal no está pensado para consumo automático.
- **API comercial**: `api.meteologix.com` / `api.kachelmannwetter.com`, con documentación propia y precios por consumo (no públicos sin cuenta). Requiere contrato.

### Términos de uso

Los términos de la API (actualizados el 17-07-2025, consultados vía `accounts.meteologix.com/static/api-nutzungsbedingungen`) otorgan una licencia «no exclusiva, intransferible y revocable» para usar el servicio **solo para fines internos o personales**. Redistribuir los datos en una aplicación pública como BRASA requeriría un acuerdo comercial específico. Además, gran parte de su valor es ECMWF, cuya licencia restringe la redistribución.

### Qué agrega frente a lo que BRASA ya usa

| Dato | ¿Ya cubierto por BRASA? | Fuente actual |
|---|---|---|
| Pronóstico viento/temp/HR/lluvia | Sí | Open-Meteo (gratuito, no comercial) |
| Índice de peligro de fuego | Sí | FWI propio + 30-30-30 + Botón Rojo CONAF |
| Avisos oficiales | Sí | DMC CAP 1.2 (dominio público) |
| Rayos | No | No existe feed público para Chile |
| Modelo SuperHD 1×1 km | No | Propietario; el detalle extra no cambia avisos por comuna |

### Riesgos

Costo mensual por consumo, licencia que prohíbe redistribución sin contrato, dependencia de un tercero comercial con cláusula revocable, y duplicación funcional casi total con Open-Meteo.

### Veredicto: **no integrar**

Valor marginal nulo frente a lo ya integrado, licencia restrictiva y costo. Si algún día se quisiera su capa de rayos o SuperHD, es una decisión de presupuesto del dueño (contrato B2B), no de código.

---

## 2. deigeprif.com

### Qué es — no es un sitio meteorológico, es el hub público de CONAF GEPRIF

`deigeprif.com` resuelve por CNAME a GitHub Pages (`deigeprif/deigeprif.github.io`) y su portada «Herramientas DEI CONAF» es un iframe a una **ArcGIS Experience** titulada «Herramientas DEIGEPRIF_v2» (ítem `6fd06a884b7e43de800927c153a90e7c`, dueño `deigeprif`, organización `A1ELWse9bRAi2JiV` = `geprif.maps.arcgis.com`, ~26.600 visitas, actualizada el 19-10-2026). Es decir: **es la vitrina oficial del Departamento de Estudios e Investigación de la Gerencia de Protección contra Incendios Forestales de CONAF** — la misma organización que publica el Botón Rojo y el CSV de incendios que BRASA ya usa. Contacto declarado en los ítems: `dei.geprif@conaf.cl`.

El hub enlaza (todo verificado público y sin clave):

| Herramienta | Recurso | Qué muestra |
|---|---|---|
| Pronóstico de Riesgo | Dashboard `06a31e138f5c40efbd577c1993154ce5` (~982 mil visitas) | 5 mapas: probabilidad de ignición, humedad de combustible fino muerto, velocidad del viento, humedad relativa y temperatura |
| Botón Rojo | Dashboard `41ee3c691359437aa9df2a09d7f6124e` | Ya integrado en BRASA |
| Reporte temporada | Dashboard `262a55fd17ae4f828501be2289ae4d35` (~657 mil visitas) | «Reporte Incendios Forestales Temporada 2025-2026», alimenta el CSV |
| Zonas Interfaz | Dashboard `09532374973a495bb185fcbe55711cd3` (~450 mil visitas) | Zonas de interfaz urbano-forestal por territorio |
| FIRMS | Dashboard `b8fc5f97527345d0aa8e958df28ac581` | Detecciones FIRMS/GOES con comuna y hora local |
| GOES (tableros) | `goes_las_tablas`, `goes_santa_ana` | Monitoreo GOES de incendios específicos |
| Pyrocast | `meteograma.deigeprif.com` (Deno Deploy) | Meteograma por punto con GFS + ECMWF, índice HDWI, reconstrucción histórica (hindcast) y capa FIRMS. Libre y público |
| Varios | 2 reportes Looker Studio y 1 Power BI embebidos, secciones EVI, «daño evitado» y recursos aéreos | Estadística y operación |

### Licencia — la novedad importante

Los ítems «Zonas Interfaz» y «FIRMS» declaran: *«Los elementos y la información desplegada en este elemento son propiedad de CONAF y elaborados por el Departamento de Desarrollo e Investigación de la Gerencia de Protección contra Incendios Forestales. Si bien los datos son de uso público, en su utilización deberá citarse a CONAF como fuente de estos»*. **Es una licencia de uso público con atribución**, más explícita que el silencio del repositorio GitHub. Sigue pendiente la autorización formal (OFI-03), pero la base legal para usar las capas ArcGIS de esta organización es más firme de lo que se creía.

### El catálogo ArcGIS (el hallazgo)

`services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services` lista **~80 FeatureServers públicos** con consulta anónima habilitada y exportación a GeoJSON/CSV/KML. Verificados el 19-10-2026:

| Recurso | Endpoint / formato | Frecuencia | Campos útiles | Valor para BRASA |
|---|---|---|---|---|
| **PI — Probabilidad de ignición** | `…/PI/FeatureServer/{0..4}/query` — polígonos en grilla ~2 km, JSON/GeoJSON | Diaria; capas `d0_20261018_PI` a `d4_20261022_PI` (5 días) | `date`, `var=PI`, `label` (clase/%) | Capa oficial de «probabilidad de ignición» por día: es la candidata natural de la capa de condiciones de RISK-03, más autoritativa que el cálculo propio |
| **HC, VV, HR, TP** | mismo patrón (`…/VV/FeatureServer`, etc.), 5 capas diarias | Diaria | `date`, `var`, `label` | Viento, humedad del combustible, HR y temperatura oficiales de CONAF; complementan el 30-30-30 |
| **Perimetro_final** | `…/Perimetro_final/FeatureServer/0/query` — polígonos | Por evento (última edición ~2026-03) | `ID_IF` («558-SAN RAMON»), `REGION`, `Superficie_hectareas`, patrón de propagación, columnas de comportamiento | **Perímetro oficial de incendios**: permite mostrar «huella oficial CONAF» en la ficha de incidente — regla de interpretación n.º 4 ya prevista |
| **PERÍMETROS_HISTORICOS_2014_2024** | `…/PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO/FeatureServer/0` — estático | Histórico | Compilado operativo 2014-2024/25 | Historia: cicatrices reales por comuna, alternativa al SHP de IDE Minagri |
| **PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA** | `…/PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA/FeatureServer/0/query` — puntos | Histórico | `Temporada`, `Comuna`, `Nombre`, `Lat/Lon`, `Superficie`, `Inicio`, `Duración_` | Incendios nominados 2002-2024 ≥50 ha — la base de «Tu comuna en 2017» sin depender del XLSX con cookie de sesión |
| **incendios_base** | `…/incendios_base/FeatureServer/0` — puntos (164 registros) | Temporada en curso | Equivalente al CSV | Respaldo/redundancia del CSV de incendios |
| **firms** | `…/firms/FeatureServer/0` — puntos | Continua | FIRMS + GOES (G18/G19/G19FRP/MODIS) con `com`, `prov`, `reg`, `localtime` | Detecciones ya georreferenciadas por comuna; redundancia, no reemplazo del S3 de NOAA |
| **Areas_SNASPE / SNASPE** | FeatureServer de áreas protegidas | Estática | Polígonos SNASPE | Contexto «área protegida afectada» en fichas |

**Advertencia de seguridad:** varios servicios operativos (`MANIOBRAS`, `OPERACIONES`, `Perimetro_final`, entre otros) tienen habilitada la **edición anónima** (`allowAnonymousToUpdate: true`). Es una mala configuración del lado de CONAF; BRASA solo debe consultar (`Query`), nunca escribir, y conviene avisarlo en el correo de OFI-03.

### El repositorio `deigeprif/public` tiene más que el CSV

Además de `reporte/incendios.csv` (ya integrado), publica en `raw.githubusercontent.com/deigeprif/public/main/reporte/`:

| Archivo | Contenido verificado |
|---|---|
| `incendios_totales_25_26.csv` (1,8 MB) | **Toda la temporada 2025-26** con las marcas operativas (`f_deteccion` → `f_ataque`) y `sha2_ultimo_poligono` (vínculo con el perímetro oficial) — la materia prima del «radar de respuesta oficial» y de la Historia |
| `incendios_coords.csv` (29 KB) | Puntos de la temporada anterior con comuna y superficie |
| `firms.csv` (34 KB) | Detecciones GOES-18/19, G19FRP y MODIS del 17-18-10-2026 ya cruzadas con comuna/provincia/región y hora local |
| `incendios_totales.csv` | Réplica de `incendios.csv` (mismo sha) |

### Pyrocast (meteograma.deigeprif.com)

Visor público de meteogramas por punto para cualquier lugar del mundo: GFS + ECMWF IFS, HDWI (índice calor-sequedad-viento), hindcast y FIRMS. El equivalente funcional ya lo hace BRASA con Open-Meteo (que además es la fuente que replica el plugin UTN inspirado en Pyrocast). **Sin API documentada** — la herramienta devuelve una SPA vacía a fetch. Su valor para BRASA: **enlace saliente** «ver meteograma detallado en Pyrocast (CONAF)» en la ficha de riesgo, e inspiración para el meteograma propio si se construye.

### Riesgos

- Depende de la buena voluntad de un equipo técnico de CONAF (GEPRIF-DEI): los servicios cambian de nombre cada temporada (`IPO_23112025`, `Mapa_15112025`) y no hay SLA. Mitigación: cachear última versión válida y degradar con gracia (patrón ya usado con Botón Rojo).
- La licencia «uso público con cita» está en los ítems, no en un documento legal formal; el correo de OFI-03 sigue siendo necesario.
- GitHub Pages como hosting de datos es inusual y frágil (límites blandos, sin garantías).
- Capas operativas internas (`MANIOBRAS`, `OPERACIONES`, recursos aéreos, tracks) son de uso táctico: **no integrarlas**, no son para consumo ciudadano y exponerlas podría ser sensible.

### Veredicto: **integrar** (en dos tiempos)

1. **Ya**: enlazar a `deigeprif.com` y `meteograma.deigeprif.com` como referencias oficiales en la ficha de riesgo; documentar el catálogo ArcGIS en `FUENTES.md`.
2. **Backlog**: capas PI/HC/VV/HR/TP para condiciones (OFI-02 ya existe), `Perimetro_final` para la ficha de incidente, y los históricos (perímetros 2014-2024, puntos de inicio 2002-2024, `incendios_totales_25_26.csv`) para la vista Historia — todo con atribución «CONAF GEPRIF» y enlace.

---

## 3. Ítems de backlog propuestos (sin implementar)

Convención del repo: los códigos de fuentes nuevas son de la familia **OFI** (no existe «DAT»); se continúa la numeración.

| ID propuesto | Qué | P | T | Fundamento |
|---|---|---|---|---|
| OFI-17 | **Perímetros oficiales en la ficha de incidente**: consultar `Perimetro_final` por `ID_IF`/proximidad al confirmar con CONAF y dibujar la huella oficial (regla 4: como estado final, nunca como avance hora a hora) | P1 | M | Este documento, §2 |
| OFI-18 | **Capa de condiciones CONAF (PI + HC + VV + HR + TP)**: resume por comuna el máximo de cada día hábil en grilla 2 km; alimenta RISK-03 y «¿por qué este nivel?» (RISK-08). Extiende OFI-02 con los endpoints ya verificados | P1 | M | §2, tabla catálogo |
| OFI-19 | **Historia desde fuentes GEPRIF**: perímetros 2014-2024 + puntos de inicio 2002-2024 (≥50 ha) + `incendios_totales_25_26.csv` para «tu comuna en 2017» e incendios nominados, sin depender del XLSX con cookie | P2 | M | §2; cubre el ítem 8 de la síntesis de research |
| OFI-20 | **Enlaces oficiales en la interfaz**: `deigeprif.com` (herramientas CONAF) y `meteograma.deigeprif.com` (Pyrocast) en las fichas de riesgo/incendio, junto a SENAPRED | P1 | S | §2 Pyrocast |
| OFI-21 | **Actualizar `docs/FUENTES.md`**: registrar el hub DEI, la licencia «uso público con cita a CONAF» encontrada en los ítems ArcGIS y el catálogo `services5/A1ELWse9bRAi2JiV`; anotar la advertencia de edición anónima | P1 | S | §2 licencia y advertencia |
| OFI-22 | **Meteologix**: no integrar; si en el futuro se necesita su feed de rayos o SuperHD, requiere contrato B2B (decisión del dueño, no técnica) | P3 | S | §1 |

Pendiente institucional (sin código): sumar al correo de OFI-03 la confirmación del alcance de «uso público» sobre las capas ArcGIS (no solo los dashboards) y el aviso de edición anónima habilitada en sus servicios operativos.

## 4. Fuentes consultadas (19 de octubre de 2026)

- meteologix.com: portal <https://meteologix.com/cl> (HTTP 403 a la herramienta; igual `robots.txt` — política de scraping **no verificada**); API comercial <https://www.business.meteologix.com/en/api> y <https://api.meteologix.com/> (401, exige cuenta); términos de la API <https://accounts.meteologix.com/static/api-nutzungsbedingungen> (resumen de la cláusula de licencia obtenido por búsqueda web; la página directa responde 403).
- deigeprif.com: <https://deigeprif.com/> y <https://deigeprif.github.io/> (landing «Herramientas DEI CONAF»); repositorios <https://github.com/deigeprif> (`deigeprif.github.io`, `public`); CNAMEs verificados (`public.deigeprif.com` → `deigeprif/public`).
- ArcGIS Experience del hub: <https://www.arcgis.com/sharing/rest/content/items/6fd06a884b7e43de800927c153a90e7c?f=json> y su `/data` (páginas BOTON_ROJO, PRONOSTICO, REPORTE, FIRMS_NASA, PYROCAST, GOES, REC_AEREOS…).
- Ítems ArcGIS consultados (metadatos y licencia): dashboards `06a31e13…` (Pronóstico de Riesgo), `09532374…` (Zonas Interfaz, con texto de licencia), `262a55fd…` (Reporte 2025-2026), `b8fc5f97…` (FIRMS), `23ae05f0…`, `c35b12e0…` y `41ee3c69…` (Botón Rojo).
- Catálogo de servicios: <https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services?f=json> (~80 servicios); metadatos y consultas de muestra sobre `PI` (capas `d0_20261018_PI`–`d4_20261022_PI`, campos `date/var/label`), `VV`, `Perimetro_final`, `PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO`, `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA`, `incendios_base` (164 registros) y `firms`.
- Repo de datos: <https://api.github.com/repos/deigeprif/public/contents/reporte> (`incendios.csv`, `incendios_totales.csv`, `incendios_totales_25_26.csv`, `incendios_coords.csv`, `firms.csv`, todos bajados y leídos parcialmente).
- Pyrocast: <https://meteograma.deigeprif.com/> (SPA sin SSR; sin API documentada — NO VERIFICADO su backend); descripción externa en la «Transatlantic Fire Resource Guide» (firesciencenorthatlantic.org) y Observatorio Forestal UTN.
