# Siguiente amenaza: de incendio a aluvión

Un suelo quemado absorbe mucho menos agua y pierde la vegetación que lo sujeta. Por eso, el área quemada en verano, sumada a la pendiente y a la lluvia del invierno siguiente, permite anticipar dónde aumenta el riesgo de aluviones y deslizamientos. BRASA ya tendrá los polígonos de área quemada: esta es su continuación natural, y casi nadie la ofrece de forma simple.

## Componentes

1. **Área quemada y severidad**: dNBR con Sentinel-2 (antes y después de la temporada), validado con los perímetros de CONAF. Severidad alta y moderada → suelo hidrofóbico y sin cobertura.
2. **Pendiente y cuencas**: un modelo de elevación (Copernicus DEM GLO-30) para delimitar microcuencas que drenan hacia zonas pobladas y calcular la pendiente media quemada por cuenca.
3. **Lluvia pronosticada e intensidad**: pronóstico horario (Open-Meteo / DMC). Lo que importa es la intensidad en pocas horas, no solo el acumulado.
4. **Isoterma 0 °C**: cuando llueve con la isoterma muy alta, la cordillera recibe lluvia en lugar de nieve y el agua escurre de inmediato. Es un factor clave en Chile central.
5. **Caudales en tiempo real**: red hidrométrica de la DGA, para confirmar crecidas aguas abajo.
6. **El Niño en el norte**: lluvias de verano en quebradas secas. Casos de referencia: Antofagasta (1991) y Atacama (2015).

## Producto para la ciudadanía

- El mismo modelo de **alerta por lugar**: «tu casa está aguas abajo de una ladera quemada y se pronostican X mm en 3 horas con la isoterma a Y m».
- Un semáforo por microcuenca para los próximos días de lluvia.
- Recomendaciones simples: no ubicarse en el cauce de quebradas, rutas de salida hacia zonas altas y qué hacer si se escucha un ruido fuerte que baja por la quebrada.

## Prerrequisitos técnicos

- PostGIS (cuencas, intersecciones con área quemada).
- Un pipeline ráster (Sentinel-2 y DEM a COG) separado del servidor web.
- Validación con especialistas (DGA, Sernageomin, universidades) antes de emitir avisos.
