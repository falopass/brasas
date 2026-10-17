# Hoja de ruta — BRASA Chile

Versión 0.1 | 16 de octubre de 2026

## Propósito y público

BRASA es una plataforma independiente de exploración geoespacial para ciudadanía, investigadores, periodistas, estudiantes y profesionales. Una persona debe poder comparar fuentes, explorar observaciones de calor, investigar superficies afectadas y navegar la historia de un incendio **sin confundir observación, confirmación, perímetro, predicción y alarma oficial**.

## Estado real del MVP entregado

| Capacidad | Estado | Condición |
|---|---|---|
| Explorador 2D/3D CesiumJS con zona Chile | Implementado | Internet para CesiumJS y teselas; relieve real opcional con token ion |
| NASA FIRMS NOAA-20/NOAA-21 (reciente) | Implementado | La clave gratuita FIRMS se configura por el usuario; conectividad y disponibilidad externa |
| NASA FIRMS MODIS_SP (histórico 1–5 días) | Implementado | Depende de archivo disponible en el proveedor y clave FIRMS |
| Línea temporal por día de observación | Implementado | No modela perímetros entre fechas |
| Meteorología modelada actual | Implementado | Open-Meteo; sólo centro de zona |
| Detalles de focos, fechas, coordenadas y FRP | Implementado | La altura de marcador en terrenos altos es provisional |
| Importación manual GeoJSON | Implementado | SHP debe convertirse a WGS84 antes de cargarlo |
| Geometrías CONAF sincronizadas automáticamente | Pendiente | Trabajo de ETL, validación y actualización |
| Límites territoriales de Chile y regiones exactos | Pendiente crítico | Requiere fuente oficial de geometrías y PostGIS |
| Mapas Sentinel-2, análisis dNBR | Pendiente | Pipeline ráster + validación de calidad |
| Alertas oficiales SENAPRED automatizadas | Pendiente de fuente/acuerdo | No prometer API pública no verificada |
| Operaciones de brigadas/drones/cámaras | Fuera de alcance inicial | Requiere acuerdos y permisos |
| Predicción de propagación | Investigación posterior | No apta para emergencias sin validación rigurosa |

## Fase 0 — Prototipo visible (entregado)

- [x] Globo CesiumJS y controles de exploración
- [x] Servidor de consulta NASA; clave secreta fuera del navegador
- [x] Filtro territorial aproximado, cinco días máximo por consulta
- [x] Línea temporal de observaciones
- [x] Capa geoespacial importable y consulta meteorológica
- [x] Mensajes de ausencia de datos, fuentes y limitaciones

**Definición de terminado:** servidor abre en localhost; sin clave no inventa focos; con clave y conectividad puede consultar productos NASA; GeoJSON válida aparece sobre el mapa.

## Fase 1 — Monitoreo robusto (semanas 1–3)

1. Importar límites oficiales comunales, regionales y nacionales en EPSG:4326; indexar con PostGIS. Manejar explícitamente Rapa Nui e islas.
2. Desarrollar colector FIRMS programado con polling conservador (15–30 min), backoff, rate limiting y cache central.
3. Validar/deduplicar observaciones mediante identificación estable, fuente, lat/lon, hora; conservar registro de descarga y versión del producto.
4. Persistir cada detección en PostgreSQL/PostGIS. Consultas por bounding box, región exacta y ventana temporal.
5. Exponer `data_as_of`, última observación de cada fuente, latencia visible y fallos parciales.
6. Crear pruebas end-to-end, seguimiento de salud y registro de errores de ingesta.

**Criterios de aceptación:** la web no llama a NASA por cada visitante; mismos filtros devuelven resultados reproducibles; una caída de NASA no borra datos previamente capturados; cada detección indica fuente y hora de adquisición. Ningún punto fuera de Chile se etiqueta como perteneciente a Chile.

## Fase 2 — Archivo y reconstrucción (semanas 4–6)

1. Descargar/consolidar SHP históricos de CONAF desde IDE Minagri, capturar URL, temporada, CRS y fecha de publicación.
2. Convertir geometrías a EPSG:4326, validar polígonos y almacenar **geometría final** separada de cualquier **perímetro observado por fecha**.
3. Construir catálogo de incidentes con eventos prioritarios (por ejemplo, temporadas 2016–2017 y 2023–2024).
4. Vincular puntos FIRMS e incidentes mediante tiempo/espacio con criterio explícito y revisión humana, sin asignación automática ciega.
5. Añadir selector de eventos y línea temporal con observaciones diarias, fuentes y metadatos.
6. Procesar imágenes Sentinel-2 para antes/después y comenzar dNBR con máscaras de nubes, validación y estimación de incertidumbre.

**Criterio:** un caso histórico puede abrirse con referencias oficiales, su perímetro final y puntos térmicos observados por fecha. Nunca se presenta un perímetro final como expansión paso a paso si no hay registros intermedios.

## Fase 3 — Producto beta usable (semanas 7–9)

- Interfaz responsive, búsqueda por fecha/región/evento, favoritos y URL compartible con filtros persistentes.
- Carga geoespacial por bbox, clustering/tiles vectoriales para miles de puntos, caché y reducción de peso ráster.
- Leyendas exactas, estados de carga y errores, unidades y fuentes, modo de accesibilidad.
- Panel de meteo por coordenada con contexto temporal; distinguir reanálisis histórico de pronóstico.
- Páginas metodológicas y mecanismo de corrección de datos.
- Observabilidad, política de privacidad, costes de proveedor y revisión de licencias.

**Criterios:** vistas regionales razonablemente fluidas en un notebook corriente; no cargar datasets nacionales completos al primer render; todos los datos visibles tienen procedencia y fecha de actualización.

## Fase 4 — Beta pública (semanas 10–12)

- Despliegue de API, base PostGIS, workers, almacenamiento de ráster y frontend en infraestructura independiente.
- Copias de seguridad, rotación de credenciales, rate limiting, auditoría y pruebas de carga.
- Revisión legal de datos abiertos/atribuciones, y acceso al basemap contratado o autoalojado.
- Piloto con usuarios reales (docentes, investigadores, voluntarios y especialistas).
- Evaluación con usuarios para medir si comprenden diferencia entre foco y evento confirmado.

**Criterio:** beta pública con calidad y responsabilidad definidas. No declarar que es un sistema oficial.

## Fase 5 — Funciones avanzadas (tras validación)

- Integración de alertas oficiales sólo mediante fuente utilizable, licencia y confirmación de actualización.
- Polígonos temporales satelitales y evaluación de incertidumbre; no interpolación presentada como verdad.
- Análisis de cobertura vegetal, pendiente, combustibles, distancia a infraestructura y exposición poblacional.
- Simulación de propagación experimental con escenarios y evaluación científica. Prohibir su uso operacional antes de validar con expertos.
- Teledetección óptica/termal e integración autorizada de aeronaves o drones si se obtiene fuente legítima.

## Priorización

**P0 (necesario antes de producción):** límites geográficos reales; ingesta persistente; procedencia/horas; control de costos; política de mapas; advertencias legales.

**P1 (núcleo diferenciador):** catálogo histórico CONAF, Sentinel-2, visualización temporal honesta, meteo contextual y búsqueda de incidentes.

**P2 (posterior):** informes PDF, comparación entre temporadas, alertas de usuario, modelos predictivos experimentales y contenido en tiempo real de terceros.

## Esfuerzo y alcance

Estimación de planificación **orientativa**, no promesa de entrega: 10–12 semanas para una beta por una persona experimentada trabajando unas 15–25 horas semanales, excluyendo convenios de datos, obtención de permisos, validación científica de modelos y revisión jurídica. Con menor dedicación o procesamiento ráster intensivo, el plazo aumenta considerablemente. Para una app estable con análisis satelital sofisticado sería razonable pensar en un proyecto de varios meses.

## Decisiones que no debemos improvisar

- No vender una falsa equivalencia `hotspot = incendio activo`.
- No hacer scraping intensivo de páginas CONAF o SENAPRED sin permisos ni términos claros.
- No usar la plataforma para toma de decisiones de seguridad personal.
- No depender de VIIRS S-NPP para el monitoreo futuro: NOAA anunció cese de entrega en noviembre de 2026. Priorizar NOAA-21/NOAA-20.
- No usar teselas gratuitas comunitarias para tráfico masivo.
- No convertir las posiciones ficticias del video de referencia en posiciones operativas inventadas.
