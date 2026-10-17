# BRASA Chile — MVP 0.1

**Visor web 2D/3D de detecciones térmicas satelitales para Chile, con modo histórico e importación de polígonos GeoJSON.** Un prototipo técnico funcional, no un sistema de emergencia certificado. No está afiliado a CONAF ni SENAPRED.

## Funciones listas

- Globo interactivo CesiumJS, controles de cámara, cambio 2D/3D y navegación por zonas de Chile.
- Consulta en el servidor de **NASA FIRMS** con `VIIRS_NOAA20_NRT` y `VIIRS_NOAA21_NRT` para observaciones recientes.
- Consulta retrospectiva de `MODIS_SP` por intervalo de **1 a 5 días**.
- Línea temporal **por día de detección**, con reproducción, pausa y navegación. *No es una reconstrucción continua del frente de fuego*.
- Consulta de condiciones meteorológicas **actuales y modeladas** del centro de cada zona con Open-Meteo.
- Importación local de archivos `GeoJSON` en WGS84 de cualquier polígono histórico, incluidos los transformados desde SHP de CONAF.
- Panel de detalle (fecha/hora Chile, coordenadas, sensor, FRP, brillo y confianza).
- Cache de consultas en el servidor; la `FIRMS_MAP_KEY` nunca se revela al navegador.
- Pantallas vacías y errores explícitos, sin hotspots inventados ni falsos registros.

**No incluidos aún:** perimetros oficiales descargados automáticamente, regiones con límites exactos, relieve 3D sin token de Cesium ion, historial satelital con Sentinel-2/dNBR, alertas SENAPRED automatizadas, posiciones de brigadas/drones, mapas térmicos IR ni predicción de propagación.

## Ejecutar en Windows (sin usar terminal)

1. Descomprime la carpeta. Instala [Python 3.10+](https://www.python.org/downloads/) si no lo tienes; durante la instalación selecciona el lanzador `py`.
2. Copia `.env.example` como `.env` (si no lo haces, el iniciador crea el archivo automáticamente). Para ver **detecciones reales**, consigue gratis una **MAP_KEY de NASA FIRMS** en <https://firms.modaps.eosdis.nasa.gov/api/map_key/> y agrega:

   ```dotenv
   FIRMS_MAP_KEY=TU_CLAVE_DE_NASA
   ```

3. **Opcional:** para relieve real (montañas), crea un token **público restringido** en <https://ion.cesium.com/tokens>, habilita el acceso permitido y configura:

   ```dotenv
   CESIUM_ION_PUBLIC_TOKEN=TU_TOKEN_PUBLICO
   ```

   Sin token, verás el globo 3D con relieve elipsoidal (sin montañas reales). El mapa de OpenStreetMap y CesiumJS se descargan de internet.

4. Haz doble clic en **`start_windows.bat`**. La primera ejecución instala dependencias Python (requiere internet) e intenta abrir `http://127.0.0.1:8000`. Si el navegador se abre antes de que el servidor arranque, actualiza la página. Mantén la ventana del iniciador abierta.

Si cambias `.env`, cierra el iniciador y ábrelo nuevamente. No publiques ese archivo.

## Ejecutar en macOS/Linux o manualmente

```bash
python -m pip install -r requirements.txt
cp .env.example .env
# Edita .env si quieres datos de FIRMS o terreno 3D
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Abre <http://127.0.0.1:8000>. API autodocumentada: <http://127.0.0.1:8000/docs>.

## Verificación rápida del MVP

1. Abre el mapa, cambia entre Maule y Biobío, centra la cámara y prueba 2D/3D.
2. Sin `FIRMS_MAP_KEY`, verás un mensaje explícito; con la clave configurada, consulta la ventana reciente de 3 días.
3. En «Histórico», selecciona una fecha y pulsa «Consultar satélites». Los resultados dependen de la disponibilidad de NASA FIRMS.
4. Mueve la línea temporal y selecciona un punto: el panel muestra observación y fuente, no estado operacional.
5. Descarga un SHP histórico oficial de [IDE Minagri](https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/), conviértelo a GeoJSON WGS84 con el script de abajo e impórtalo.

## Conversión de cartografía CONAF

CONAF publica shapefiles en sistemas de coordenadas proyectados como `EPSG:32719`. **No cargues SHP UTM directamente** como si sus coordenadas fueran longitud/latitud.

```bash
python -m pip install -r requirements-geo.txt
python scripts/convert_conaf.py ruta/al_archivo.shp --output perimetros.geojson
# Si el archivo no informa CRS, utiliza el EPSG documentado para esa capa:
python scripts/convert_conaf.py ruta/al_archivo.shp --epsg EPSG:32719 --output perimetros.geojson
```

Si la fuente no incluye metadatos CRS y está en Isla de Pascua, verifica el EPSG particular de esa capa: **no supongas 32719**. El script requiere archivos `.shp/.shx/.dbf` juntos (o el ZIP compatible).

## API

| Endpoint | Descripción |
|---|---|
| `GET /api/health` | Estado de servicio |
| `GET /api/config` | Zonas y token público de Cesium, no muestra clave FIRMS |
| `GET /api/hotspots?mode=recent&region=maule&days=3` | NOAA-20 y NOAA-21, observaciones recientes |
| `GET /api/hotspots?mode=historical&region=maule&days=3&start=2017-01-24` | Consulta MODIS retrospectiva |
| `GET /api/weather?lat=-35.4&lon=-71.7` | Condiciones actuales modeladas Open-Meteo |

El API de áreas de FIRMS permite tramos de **1 a 5 días**. Las cajas geográficas del MVP son aproximadas y *pueden incluir detecciones del otro lado de una frontera*. Para producción, usar límites regionales reales y consulta espacial PostGIS. NASA FIRMS exige una clave gratuita y está sujeto a disponibilidad y límites.

## Seguridad y advertencias

- **No usar para evacuación, despacho de recursos ni decisiones operacionales.** Las detecciones satelitales tienen latencia, omisiones y falsos positivos.
- La API no sustituye las alertas oficiales SENAPRED o CONAF, y una detección no demuestra un incendio activo.
- La fecha y hora de cada observación se conserva en UTC; en la ficha se transforma a `America/Santiago`.
- Los datos de meteorología son del centro de la zona, *no* necesariamente del punto seleccionado o del día histórico.
- Las cajas geográficas incluyen zonas vecinas y la colección nacional del prototipo excluye Rapa Nui, que tiene un filtro separado. La capa precisa del límite de Chile es prioritaria antes de publicar.
- No se suma FRP a lo largo de un día como si equivaliera a energía total o hectáreas quemadas.
- El mapa base de `tile.openstreetmap.org` es exclusivamente para un prototipo de bajo tráfico: consulta [sus políticas de uso](https://operations.osmfoundation.org/policies/tiles/). Sustituye por un proveedor con licencia/SLA antes de escalar.
- Open-Meteo ofrece acceso gratuito en condiciones no comerciales; confirma sus condiciones para monetización o uso intensivo.
- El token de Cesium ion es **público en el navegador**: usa uno específico para este proyecto con mínimos permisos y restricción de dominio.
- En producción añade autenticación de ingesta, ratelimits, logs, revisión de proveedores, actualización programada, políticas de datos y validación operativa.

## Documentación

- [`docs/ROADMAP.md`](docs/ROADMAP.md): fases, criterios de aceptación, alcance y entregables.
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md): evolución técnica, modelo PostGIS, contratos de API, ingesta y calidad.
- [`docs/FUENTES.md`](docs/FUENTES.md): fuentes oficiales, licencias y dependencias.

## Notas de arquitectura

El MVP usa **FastAPI + CesiumJS sin compilación frontend**, deliberadamente: apertura rápida y prueba de concepto sin instalar Node/npm. **La arquitectura de producción recomendada es Next.js/React + CesiumJS + FastAPI/Python + PostgreSQL/PostGIS + almacenamiento raster, colas y workers.** La API ya separa consumidores de proveedores externos; el frontend se puede migrar a React sin cambiar el esquema de detecciones.

## Pruebas

```bash
python -m pip install pytest
python -m pytest -q
```

Las pruebas locales **no realizan llamadas reales a NASA**. Solo se validan parsing CSV y límites básicos. Una prueba end-to-end satelital requiere clave y conexión.
