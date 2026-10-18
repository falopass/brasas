# Detección temprana comunitaria: qué funciona en otros países y qué puede copiar Brasas

> Investigación para BRASAS. Consulta del 18 de octubre de 2026. Cada afirmación lleva su fuente; lo que no se pudo verificar se marca **NO VERIFICADO** y no se usa como argumento. Las citas de páginas oficiales se transcriben en su idioma original.

## Resumen

1. Ningún sistema revisado publica el reporte ciudadano en crudo. El ciudadano aporta la señal; una persona o un umbral decide si se publica.
2. El valor no está en la aplicación sino en el vocabulario de estados, en la trazabilidad de cada dato y en la latencia declarada.
3. Los programas vecinales preparan comunidades; no detectan incendios. Prometer detección con ellos es un error de diseño.
4. Lo replicable con recursos mínimos es la gobernanza (quién publica, con qué fuente, con qué corrección), no la infraestructura de cámaras ni de IA.
5. Para Chile, el equivalente global de EFFIS es GWIS: EFFIS cubre Europa y no sirve como fuente operativa local.

## 1. Comparación

| Sistema | País | Qué hace | Datos abiertos | Antídoto contra falsos positivos | Replicable en Chile |
|---|---|---|---|---|---|
| NSW RFS · Hazards Near Me | Australia (NSW) | App y feed de incidentes del servicio de bomberos rural | Sí: CAP, GeoRSS y GeoJSON, con licencia Creative Commons Attribution (metadatos del catálogo, última modificación 2016-07-20) | Publica incidentes registrados por el RFS; el conjunto no describe un canal de reporte ciudadano | Alto, con la salvedad de que el dominio bloquea el acceso automatizado (HTTP 403) |
| VicEmergency | Australia (VIC) | App, web y línea telefónica con incidentes y alertas | No se encontró conjunto abierto: la búsqueda en data.vic no devolvió resultados | Información de agencias oficiales; sin canal ciudadano visible | Medio |
| CFA · Community Fireguard | Australia (VIC) | Programa de preparación vecinal | No aplica | No gestiona reportes: su función es preparación | Alto y de bajo costo; impacto **NO VERIFICADO** |
| BC Wildfire Service | Canadá (BC) | App, mapa, teléfono de reporte y estados operativos | Parcial: histórico de incidentes con Open Government Licence - British Columbia | Solo publica el estado oficial; el reporte entra por teléfono y lo valida la agencia | Alto |
| EFFIS | Unión Europea | Focos activos y área quemada | Sí: CC BY 4.0, con WMS/WFS | Filtro propio y verificación visual; advierte que «no todos los focos son incendios» | Bajo como fuente local (no cubre Chile); alto como referencia de método |
| GWIS | Global | Peligro de incendio y focos casi en tiempo real | Sí: CC BY 4.0 | Productos satelitales con las mismas advertencias | Alto como contexto |
| Copernicus EMS Rapid Mapping | Unión Europea | Cartografía de emergencia a pedido | Productos gratuitos, pero la activación la piden usuarios autorizados | Validación por analistas | Bajo: es un servicio para Estados |
| Watch Duty | EE. UU. | App sin ánimo de lucro operada por personas | No se verificó un feed abierto | Código de conducta: «no hearsay», fuente identificable, revisión antes de publicar | Medio: se copia la gobernanza, no la app |
| HPWREN | EE. UU. | Red de cámaras y sensores | Archivo con CC BY-NC 4.0; el tiempo real requiere licencia | Cámara más criterio humano | Bajo por costo |
| Pano AI | EE. UU. | Cámaras 360° con IA de humo y analistas | No | Revisión humana de cada detección (según el propio proveedor) | Bajo por costo |

## 2. Patrones que se repiten y funcionan

### 2.1 El ciudadano es sensor, no editor

Watch Duty lo dice en su código de conducta: la información debe venir de «a bonafide source, e.g., radio scanner transmission, a firefighter, a Sheriff, CALFIRE publication, etc.» y «containment percentages and other relevant data must come from official sources». Su descripción rechaza el rumor: «no hearsay, no sensationalization—only verified information». Pano AI aplica la misma regla con máquinas: revisión humana de cada detección.

Para Brasas, el estado `reportado` (reporte verificado por moderación) ya sigue este patrón; el error sería publicar el reporte sin moderar.

### 2.2 Un vocabulario de estados que todos usan

BC Wildfire Service publica cuatro estados operativos: Out of Control, Being Held, Under Control y Out, y una figura aparte, «Wildfire of Note», para el incendio de interés público. El valor no está en el mapa: está en que la prensa, la agencia y la app usan la misma palabra para lo mismo. Brasas tiene su propia escala (`anomalía`, `posible`, `reportado`, `confirmado`, `controlado`); conviene explicarla en la interfaz y no traducirla a la ligera.

### 2.3 Latencia y licencia declaradas

El catálogo de datos de NSW declara licencia Creative Commons Attribution y tres formatos (CAP, GeoRSS, GeoJSON). EFFIS declara que los focos están disponibles «within 2-3 hours of the acquisition of the MODIS/VIIRS images» y publica bajo CC BY 4.0. Declarar la latencia no es un detalle técnico: es lo que permite al usuario decidir si confía en el dato para actuar.

### 2.4 Una capa humana sobre la máquina, también en lo automático

EFFIS advierte que «the satellites also detect other heat sources (not all hotspots are fires)», y por eso filtra por cobertura del suelo, cercanía a zonas urbanas y confianza del foco, además de verificar visualmente el área quemada. Es el mismo problema que Brasas ya enfrenta con las fuentes fijas (volcanes, industria): el filtro no es opcional.

### 2.5 El teléfono sigue vivo

BC Wildfire Service mantiene un número de reporte junto a su app informativa. La app no sustituye el canal de reporte: lo complementa. Para Brasas, el canal telefónico oficial debe seguir visible, sobre todo en modo emergencia.

### 2.6 Los programas vecinales preparan; no detectan

Community Fireguard (CFA, Victoria) es un programa de preparación evaluado por costes y resultados (Gibbs et al. 2015), no un sistema de detección. Firewise USA es un programa de reconocimiento de comunidades preparadas de la NFPA; su contenido no pudo verificarse (texto truncado), así que no se usa como evidencia.

## 3. Lo que no conviene copiar

- **Abrir el reporte ciudadano sin moderación.** Es el error más caro y el más fácil de evitar: produciría rumores con mapa.
- **Mostrar el dato satelital crudo sin filtro de confianza.** EFFIS documenta sus propios falsos positivos; Brasas ya filtra confianza y fuentes fijas.
- **Cámaras e IA como primera inversión.** Requieren estaciones en altura, revisión permanente y triangulación; el costo por hectárea vigilada es desproporcionado para una app pequeña.
- **Licencias que parecen abiertas y no lo son.** HPWREN advierte que sus datos «are not intended to be used as a decision-making tool», y su tiempo real exige licencia.
- **La activación restringida de Copernicus EMS.** Es cartografía para Estados, no un motor de avisos ciudadano.

## 4. El caso «BC FireWatch»: una corrección

No se encontró evidencia de un programa oficial de vigilancia comunitaria o voluntaria llamado «FireWatch» en Columbia Británica ni en Alberta. Lo verificable con ese nombre es **IQ FireWatch**, un sistema comercial alemán de detección automática de humo y calor, sin relación con un programa ciudadano. Lo que sí existe en BC es el modelo descrito: app informativa, estados operativos, teléfono de reporte y datos históricos abiertos. **NO VERIFICADO** como programa comunitario.

## 5. Evidencia académica

Metadatos verificados en Crossref el 2026-10-18.

| Trabajo | Medio y año | DOI | Qué aporta | Límite |
|---|---|---|---|---|
| Boulton, Shotton y Williams, «Using Social Media to Detect and Locate Wildfires» | ICWSM 10(2):178-186, 2021 (en línea 2016) | [10.1609/icwsm.v10i2.14850](https://doi.org/10.1609/icwsm.v10i2.14850) | Correlación temporal entre actividad en redes y ocurrencia de incendios | La relación varía mucho a escala de estado y condado: sirve como señal agregada, no como localizador fino |
| Puttinaovarat et al., «WildfireGO…» | Applied System Innovation 9(7):136, 2026 | [10.3390/asi9070136](https://doi.org/10.3390/asi9070136) | Sistema que combina crowdsourcing, focos satelitales y aprendizaje profundo | El propio resumen señala «fragmented data sources, false alarms, and delays in field verification» |
| Gibbs et al., «Cost and outcomes associated with participating in the Community Fireguard Program…» | IJDRR 375-380, 2015 | [10.1016/j.ijdrr.2015.07.016](https://doi.org/10.1016/j.ijdrr.2015.07.016) | Costes y resultados del programa vecinal tras los incendios de Black Saturday | Sin resumen disponible en la fuente consultada: no se citan resultados |
| Bogdos y Manolakos, «Crowd-Sourced Wildfire Spread Prediction With Remote Georeferencing Using Smartphones» | IEEE Access 102102-102112, 2019 | [10.1109/ACCESS.2019.2931456](https://doi.org/10.1109/ACCESS.2019.2931456) | Georreferenciación remota con teléfonos para estimar propagación | Verificado por título y metadatos; no se citan resultados |

## 6. Qué puede copiar Brasas

1. **Convertir el reporte ciudadano en señal, no en publicación.** Exigir foto georreferenciada, agrupar reportes por radio y ventana de tiempo, y no mostrar el punto hasta superar un umbral (por ejemplo, dos reportes independientes en 3 km y 30 minutos, o uno con evidencia satelital). Criterio de aceptación: ningún reporte aislado crea un incidente visible.
2. **Adoptar un código de conducta mínimo y publicarlo.** Nada de rumores; fuente identificable; revisión antes de publicar; corrección pública y fechada; «confirmado» solo con CONAF. Criterio: cada incidente muestra su fuente y su hora, y toda corrección queda registrada.
3. **Declarar latencia y licencia por fuente.** En la ficha de incidente y en la página de calidad de datos: qué sensor, qué latencia típica, qué licencia. Criterio: ninguna capa sin fuente, latencia y licencia visibles.
4. **Usar GWIS como contexto global y no EFFIS como fuente local.** GWIS cubre Chile; EFFIS no. Criterio: si se integra, aparece como capa de contexto con crédito y no como alerta.
5. **Mantener el teléfono y la preparación.** El canal oficial de reporte y el contenido de preparación no se sustituyen por la app. Criterio: el modo emergencia sigue mostrando el canal oficial.

## 7. Fuentes consultadas (18 de octubre de 2026)

- Catálogo de datos de NSW, metadatos del conjunto «NSW Rural Fire Service Current Incidents Feed»: <https://data.nsw.gov.au/data/api/3/action/package_show?id=nsw-rural-fire-service-current-incidents-feed> (licencia Creative Commons Attribution; tres recursos CAP, GeoRSS y GeoJSON).
- NSW Government, «Hazards Near Me app»: <https://www.nsw.gov.au/emergency/hazards-near-me-app>.
- Gobierno de Victoria, «Setting up your VicEmergency App»: <https://www.vic.gov.au/help-setting-vicemergency-app>. Búsqueda sin resultados en el catálogo abierto: <https://discover.data.vic.gov.au/api/3/action/package_search?q=vicemergency&rows=2>.
- CFA, «Community Fireguard»: <https://www.cfa.vic.gov.au/fire-safety/programs-and-services/general-fire-safety-programs/community-fireguard>.
- Gobierno de BC, «Wildfire Service»: <https://www2.gov.bc.ca/gov/content/safety/wildfire-status> y «Stages of control»: <https://www2.gov.bc.ca/gov/content/safety/wildfire-status/wildfire-response/management-strategies/stages-of-control> (actualizada el 11-05-2026).
- BC Data Catalogue, metadatos del conjunto histórico de incidentes: <https://catalogue.data.gov.bc.ca/api/3/action/package_search?q=%22incident%20locations%22&rows=1> (Open Government Licence - British Columbia).
- EFFIS, «Active Fire Detection»: <https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/active-fire-detection>; «Data License»: <https://forest-fire.emergency.copernicus.eu/about-effis/data-license>.
- GWIS, portada: <https://gwis.jrc.ec.europa.eu/>; licencia: <https://gwis.jrc.ec.europa.eu/about-gwis/data-license>.
- Copernicus EMS, «About us»: <https://emergency.copernicus.eu/about/>.
- Watch Duty, «Code of Conduct»: <https://www.watchduty.org/how-it-works/code-of-conduct>; «How Watch Duty Works»: <https://www.watchduty.org/how-it-works/overview>.
- HPWREN: <https://www.hpwren.ucsd.edu/>; condiciones de uso: <https://www.hpwren.ucsd.edu/cc.html>.
- Pano AI, «Our Solution»: <https://www.pano.ai/solution>.
- IQ FireWatch: <https://www.iq-firewatch.com/>.
- Crossref, metadatos de los cuatro DOI citados: <https://api.crossref.org/works/10.1609/icwsm.v10i2.14850>.

## 8. Límites de esta investigación

- **No verificados (no se usan como prueba):** rfs.nsw.gov.au (HTTP 403), emv.vic.gov.au (403), mdpi.com (403), nfpa.org (texto truncado), PreventionWeb (403 por control anti-bots), alertwildfire.org (solo devuelve «Loading...», es una aplicación JavaScript) y todos los PDF (la herramienta de consulta no procesa `application/pdf`).
- La página del catálogo de BC respondió HTTP 520 al verificarla; los metadatos se leyeron por la API del catálogo.
- **No se verificó ninguna cifra de usuarios, adopción o impacto** de estos sistemas: no se afirma que «funcionen» en ese sentido. Lo que está documentado es su mecanismo y su gobernanza.
- El caso «FireWatch» de BC queda como **NO VERIFICADO**: no se encontró un programa oficial con ese nombre.