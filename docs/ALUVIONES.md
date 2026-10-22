# Siguiente amenaza: de incendio a aluvión

Un suelo quemado absorbe mucho menos agua y pierde la vegetación que lo sujeta. Por eso, el área quemada en verano, sumada a la pendiente y a la lluvia del invierno siguiente, permite anticipar dónde aumenta el riesgo de aluviones y deslizamientos. BRASA ya tendrá los polígonos de área quemada: esta es su continuación natural, y casi nadie la ofrece de forma simple.

## Cómo se calcula hoy la cicatriz

Hoy la cicatriz es la **huella de detecciones satelitales**: la unión de los píxeles calientes confiables que vieron GOES-19 y VIIRS/MODIS durante cada incidente de la temporada (medio píxel de radio por sensor, 1,5 km en el ABI por el píxel efectivo de ~3 km en Chile; el mismo criterio de la ficha del incidente), agrupada por comuna. No es el perímetro oficial de CONAF ni el área quemada medida: con GOES (píxel de 2-3 km) sobreestima la superficie. El dNBR de Sentinel-2 (componente 1) la reemplazará como medición.

Se publica como dato abierto en `/api/opendata/scars.geojson` (parámetro `days`, 90 por defecto) y como capa «Cicatrices de la temporada» en el mapa, apagada por defecto.

La cicatriz incluye también las **anomalías** —detecciones sueltas que no alcanzaron el umbral de «posible»—: mide «zona donde el satélite vio calor», no superficie quemada con evidencia. Cambiar esa regla (por ejemplo, publicar `ha` solo con evidencia y aparte `ha_anomalia`) es una decisión de producto pendiente (SCARS-02) y no se aplica sin aprobación. `incidents_examined` cuenta todos los incidentes examinados, incluidos los que no tienen comuna; `sin_comuna` declara cuántos quedaron fuera de la geometría.

## Componentes

1. **Área quemada y severidad**: dNBR con Sentinel-2 (antes y después de la temporada), validado con los perímetros de CONAF. Severidad alta y moderada → suelo hidrofóbico y sin cobertura.
2. **Pendiente y cuencas**: un modelo de elevación (Copernicus DEM GLO-30) para delimitar microcuencas que drenan hacia zonas pobladas y calcular la pendiente media quemada por cuenca.
3. **Lluvia pronosticada e intensidad**: pronóstico horario (Open-Meteo / DMC). Lo que importa es la intensidad en pocas horas, no solo el acumulado. Implementado el insumo en `backend/lluvia.py` (AGUA-03A); falta la calibración con lluvia real y el cruce con las cicatrices.
4. **Isoterma 0 °C**: cuando llueve con la isoterma muy alta, la cordillera recibe lluvia en lugar de nieve y el agua escurre de inmediato. Es un factor clave en Chile central. Implementado el insumo en `backend/lluvia.py` (AGUA-03A); falta la calibración con lluvia real y el cruce con las cicatrices.
5. **Caudales en tiempo real**: red hidrométrica de la DGA, para confirmar crecidas aguas abajo.
6. **El Niño en el norte**: lluvias de verano en quebradas secas. Casos de referencia: Antofagasta (1991) y Atacama (2015).

## Producto para la ciudadanía

- El mismo modelo de **alerta por lugar**: «tu casa está aguas abajo de una ladera quemada y se pronostican X mm en 3 horas con la isoterma a Y m».
- Un semáforo por microcuenca para los próximos días de lluvia.
- Recomendaciones simples: no ubicarse en el cauce de quebradas, rutas de salida hacia zonas altas y qué hacer si se escucha un ruido fuerte que baja por la quebrada.

## Qué puede decir BRASA hoy, en palabras (AGUA-206)

`backend/lluvia.py` incorpora `explicacion(lluvia, isoterma, dias_desde_el_incendio)`: una
función pura que traduce la peor ventana de lluvia a un texto para el vecino. **No gatilla
avisos, notificaciones ni cambios en la app**: es el insumo de un bloque informativo que
todavía no se publica. La opción conservadora —la que se implementa aquí— es no emitir nada
automático hasta que la persona dueña elija el umbral y el canal.

La fórmula elegida es la prudente, no la que afirma un aluvión:

| Situación | Lo que dice el texto |
|---|---|
| Lluvia bajo el umbral | «No se espera lluvia intensa sobre el suelo quemado». |
| Lluvia intensa, isoterma baja | «Lluvia intensa sobre suelo quemado… no te ubiques en el cauce de las quebradas». |
| Lluvia intensa, isoterma alta | «…en la cordillera cae lluvia en vez de nieve y el agua baja de inmediato hacia las quebradas. Atento a las quebradas: no te ubiques en su cauce». |
| Sin dato de lluvia | «No hay pronóstico de lluvia para esta zona»; no se afirma nada. |
| Sin dato de isoterma | Avisa igual por la lluvia y dice que falta la isoterma. |

Ningún texto dice «va a haber un aluvión» ni «puede bajar un alud de barro». Todos terminan con
la etiqueta de estimación de BRASA («umbrales provisionales: no es un aviso oficial») y con la
frase que manda a SENAPRED y a la autoridad local. La fecha del incendio agrega contexto («hace
N días»), pero no cambia la señal: no hay calibración de cómo decae el riesgo con los años, así
que no se usa como umbral.

La recomendación de fondo es la de SENAPRED: no ubicarse en quebradas ni en sus desembocaduras,
y alejarse si se escucha un ruido fuerte que baja
([SENAPRED, aluviones](https://www.senapred.cl/aluviones/)). CONAF también incluye el riesgo de
aluvión en suelo quemado en su Manual Comunitario 2022
([CONAF](https://oficinavirtual.conaf.cl/archivos/recursos/insumos_tecnicos/Proteccion%20de%20Incendios%20Forestales/Manual%20comunitario%20%202022.pdf)).

### Umbrales provisionales

| Constante | Valor | Qué decide | Estado |
|---|---|---|---|
| `VENTANA_HORAS` | 3 h | La ventana de lluvia que se evalúa | Provisional |
| `MM_3H_INTENSA` | 10,0 mm en 3 h | Si la lluvia es «intensa» | **Sin calibrar** |
| `ISOTERMA_ALTA_M` | 2 500 m | Si la isoterma se informa alta | **Sin calibrar** |

## Tabla de calibración

Solo se completan las celdas que se pudieron reconstruir con una fuente reproducible. Las que
faltan quedan marcadas: no se rellenan con una cifra estimada.

| Evento | Fecha | Lluvia en 3 h | Isoterma 0 °C | Daño observado | Fuente | Para qué sirve |
|---|---|---|---|---|---|---|
| Viña del Mar, laderas quemadas en febrero de 2024 | 12-13 jun 2024 | 20,9 mm (máximo; ERA5 y pronóstico archivado) | 3 000 m en la hora central | Deslizamientos de tierra menores en la zona cero; 42 viviendas afectadas en la comuna | [Municipio de Viña del Mar, 13-jun-2024](https://www.munivina.cl/noticias/balance-por-sistema-frontal-municipio-de-vina-del-mar-atiende-afectaciones-en-viviendas-y-toma-acciones-preventivas-por-crecida-del-cauce-del-estero-marga-marga/) · [CIGIDEN, 27-may-2024](https://cigiden.cl/vina-del-mar-laderas-intervenidas-en-zona-de-incendios-aumentan-riesgo-de-derrumbes/) | Único evento post-incendio con lluvia, isoterma y daño que se pudo reconstruir en esta revisión. Con 20,9 mm/3 h el daño fue menor; un umbral de 10 mm/3 h habría marcado este evento. La comparación sugiere que 10 mm es laxo, pero un solo evento no lo demuestra. |
| Villa Santa Lucía (Chaitén) | 16 dic 2017 | Más de 120 mm en 24 h; sin serie de 3 h en la fuente | ~1 600 m | 11 fallecidos y 15 desaparecidos | [Sernageomin, citado por Las Últimas Noticias / Fundación Terram, 18-dic-2017](https://www.terram.cl/glaciar-se-desprendio-por-las-intensas-lluvias-y-provoco-el-fatal-aluvion/) | Referencia del mecanismo (lluvia + isoterma alta). **No es suelo quemado**: no calibra el umbral. |
| Cuencas del Mataquito y del Maule | jun 2023 | Sin dato de 3 h en la fuente | ~3 000 m (98,5 % de la cuenca del Mataquito bajo la isoterma) | Inundaciones y deslizamientos; no es un evento post-incendio | [CIGIDEN, 14-oct-2023](https://www.cigiden.cl/presentan-evidencia-cientifica-inedita-en-torno-a-las-lluvias-que-afectaron-el-centro-sur-del-pais-este-invierno/) | Referencia: 3 000 m ya es una isoterma alta para Chile central; apoya el orden de 2 500 m, no lo fija. |
| Santa Olga (Maule) | 26 ene 2017 | — | — | 979 familias sin vivienda; 8 fallecidos | [La Tercera, 26-ene-2018](https://www.latercera.com/noticia/santa-olga-ano-despues-la-catastrofe/) · [03-mega-incendios-2017-2024.md](research/03-mega-incendios-2017-2024.md) | **Corrección**: fue un incendio, no un aluvión. No sirve como evento de calibración de lluvia. |

La lluvia y la isoterma de la primera fila se reconstruyeron con Open-Meteo en el punto
-33,03 / -71,55 (zona quemada de Viña del Mar), ventana 13-jun-2024 02:00-05:00 UTC:
[reanálisis ERA5](https://archive-api.open-meteo.com/v1/archive?latitude=-33.0300&longitude=-71.5500&start_date=2024-06-12&end_date=2024-06-14&hourly=precipitation&timezone=UTC)
y [pronóstico archivado](https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=-33.0300&longitude=-71.5500&start_date=2024-06-12&end_date=2024-06-14&hourly=precipitation,freezing_level_height&timezone=UTC).
Son productos de modelo (~25 km), no la medición de una estación: la serie oficial de DMC está
en [Servicios Climáticos](https://climatologia.meteochile.gob.cl/application/index/menuTematicoPrecipitacion)
y queda pendiente de contrastar. Para la isoterma no hay serie histórica pública equivalente: la
del pronóstico archivado es la mejor reconstrucción disponible y se declara como tal.

### Qué falta antes de cambiar los umbrales

1. **Serie oficial de lluvia en 3 h** de la estación DMC más cercana a cada evento (Viña del Mar
   Ad. 320041 y las estaciones de la cuenca del Maule), y caudales de la DGA.
2. **Catastro de remociones en masa de SERNAGEOMIN** (AGUA-08): eventos, fecha, comuna y daño,
   para no depender de la prensa.
3. **Informes de SENAPRED** de cada emergencia, con el parte oficial y la hora.
4. **Decisión de la persona dueña** sobre el umbral y sobre la forma del producto: bloque
   informativo, aviso push o nada automático. Esta entrega no enciende ninguno de los tres.

Mientras no estén esos cuatro pasos, `MM_3H_INTENSA` y `ISOTERMA_ALTA_M` siguen siendo
provisionales y el texto no afirma que vaya a ocurrir un aluvión.

## Prerrequisitos técnicos

- PostGIS (cuencas, intersecciones con área quemada).
- Un pipeline ráster (Sentinel-2 y DEM a COG) separado del servidor web.
- Validación con especialistas (DGA, Sernageomin, universidades) antes de emitir avisos.
