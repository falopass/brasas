# INV-29 · Fuente de teselas DEM para el relieve sombreado (MAPA-155)

**Fecha:** 2026-10-25. **Encargo que la necesita:** MAPA-155 (capa `hillshade` de MapLibre sobre una fuente `raster-dem`).

## Pregunta

¿Qué fuente de teselas DEM en formato `raster-dem` de MapLibre (Terrarium o Mapbox Terrain-RGB) puede usar BRASA —app ciudadana pública y gratuita— con licencia abierta verificada para mostrar relieve sombreado en Chile? Para cada candidata: URL, formato, zoom máximo, licencia exacta con enlace, atribución exigida, límites de uso o de tráfico y CORS.

## Fuentes consultadas (primarias)

- AWS Registry of Open Data — Terrain Tiles: <https://registry.opendata.aws/terrain-tiles/>
- Tilezen Joerd (el proyecto que genera esas teselas): `docs/attribution.md` y `docs/data-sources.md` en <https://github.com/tilezen/joerd>
- Mapterhorn: <https://mapterhorn.com/data-access/>, <https://mapterhorn.com/attribution/>, TileJSON oficial <https://tiles.mapterhorn.com/tilejson.json> y catálogo de fuentes <https://github.com/mapterhorn/mapterhorn/tree/main/source-catalog>
- Copernicus Data Space — COP-DEM: <https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM> y la licencia GLO-30 en PDF: <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf>

Las URLs de teselas se verificaron en vivo (GET con encabezado `Origin` de producción) el 2026-10-25.

## Candidatas

### 1. Mapterhorn ✅ recomendada

- **URL de teselas:** `https://tiles.mapterhorn.com/{z}/{x}/{y}.webp` (TileJSON: `https://tiles.mapterhorn.com/tilejson.json`; también existen archivos PMTiles descargables en `download.mapterhorn.com` para autoalojar).
- **Formato:** Terrarium (`"encoding":"terrarium"` en el TileJSON), WebP de 512 px —directamente compatible con `type: "raster-dem"` de MapLibre.
- **Zoom máximo en Chile:** z12. La cobertura global z0–z12 usa **Copernicus GLO-30 (~30 m)**; los niveles z13–z17 solo existen en regiones con fuentes de alta resolución (Europa, Nueva Zelanda, etc.), ninguna en Sudamérica. Verificado: z12 responde en Santiago, z13 da 404.
- **Licencia:** los datos de cada tesela provienen de fuentes de datos abiertos (`source-catalog/` en el repo); para Chile la fuente es `glo30`, declarada como «COPERNICUS full, free and open license» con su `LICENSE.pdf` (licencia ESA/CDSE para COP-DEM-GLO-30-F: permite uso, distribución, comunicación al público y modificación, exigiendo el aviso de fuente). El código del proyecto es BSD-3.
- **Atribución exigida:** el TileJSON declara `© Mapterhorn` con enlace a `/attribution`; la licencia GLO-30 exige informar la fuente con el aviso «© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved» (forma corta aceptable: «Copernicus DEM GLO-30») y sugiere citar el DOI `10.5270/ESA-c5d3d65`.
- **Límites de uso/tráfico:** el endpoint de teselas es público y gratuito, servido sobre Cloudflare R2/Workers (Cloudflare es patrocinador de infraestructura). **No publica términos de servicio ni límites de tráfico escritos**: es un proyecto comunitario financiado por donaciones (OpenCollective); no hay SLA. Si BRASA crece, el camino de cortesía/robustez es autoalojar el PMTiles de Chile en R2 (licencia lo permite).
- **CORS:** `Access-Control-Allow-Origin: *` verificado en `tilejson.json` y en teselas.

### 2. AWS Terrain Tiles (Mapzen / Tilezen Joerd, Registry of Open Data) — alternativa

- **URL de teselas:** `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` (bucket `elevation-tiles-prod`, us-east-1; réplica `elevation-tiles-prod-eu`, eu-central-1). Sin clave.
- **Formato:** Terrarium, PNG de 256 px.
- **Zoom máximo:** z15 (verificado: z15 responde en Santiago, z16 da 404).
- **Licencia:** **no hay una licencia única**. El registro apunta a `docs/attribution.md` de joerd, que exige atribución por fuente y declara «you are responsible for researching each project to follow their license terms». Para Chile las fuentes son **SRTM** y **GMTED2010**, ambas de dominio público (USGS, que pide crédito). Es usable, pero la «licencia» es un documento de atribución multi-fuente, no una licencia abierta única.
- **Atribución exigida:** texto por fuente; la plantilla completa lista 11 proveedores. Para una app solo-Chile basta crédito a SRTM/GMTED2010 USGS + Mapzen Terrain Tiles, pero el documento oficial no autoriza esa forma corta explícitamente.
- **Límites:** S3 público patrocinado por el Open Data Program de AWS; sin límites publicados ni SLA. El proyecto joerd está archivado: las teselas siguen sirviendo pero no se regeneran.
- **CORS:** `Access-Control-Allow-Origin: *` verificado.

### 3. Copernicus DEM directo (GLO-30/GLO-90) — solo para autoalojar

- La descarga oficial es GeoTIFF vía Copernicus Data Space (S3/OData con credenciales temporales gratuitas); **no existe un endpoint oficial gratuito de teselas `raster-dem`**. La licencia GLO-30 («Full, Free & Open», PDF enlazado arriba) permite redistribuir, así que servir teselas propias es legal — pero exige construirlas y alojarlas (o extraer un recorte de los PMTiles de Mapterhorn, que es el mismo dato). GLO-90 (~90 m) tiene licencia equivalente.
- Útil como **plan B**: autoalojar un PMTiles de Chile en R2 con datos GLO-30, si Mapterhorn deja de servir o el tráfico lo amerita.

### 4. Mapbox Terrain-RGB — descartada

Requiere token de cuenta y se rige por los términos comerciales de Mapbox (capa gratuita limitada, servicio propietario). No es licencia abierta; el formato es el mismo (`encoding: "mapbox"`) pero la fuente no califica para BRASA.

## Respuesta

Sí existe una fuente con licencia abierta verificable: **Mapterhorn**, cuyas teselas sobre Chile son Copernicus DEM GLO-30 bajo la licencia «Full, Free & Open» de ESA/Copernicus, que permite uso gratuito, redistribución y comunicación al público con aviso de fuente. El endpoint es público, sin clave, con CORS `*` y TileJSON oficial.

## Confianza

- **Alta** en licencia, formato, URL, zoom y CORS de Mapterhorn y de AWS Terrain Tiles (verificados en fuente primaria y con requests en vivo el 2026-10-25).
- **Media** en disponibilidad a largo plazo: ninguna de las dos publica SLA ni límites de tráfico escritos; Mapterhorn vive de patrocinio (Cloudflare + donaciones) y AWS Terrain Tiles es un bucket congelado (proyecto archivado). El plan B de autoalojar PMTiles en R2 mitiga ese riesgo.

## Decisión recomendada

Usar **Mapterhorn** como fuente `raster-dem` para la capa de relieve de MAPA-155:

```json
"hillshade-dem": {
  "type": "raster-dem",
  "tiles": ["https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"],
  "encoding": "terrarium",
  "tileSize": 512,
  "maxzoom": 12,
  "attribution": "© Mapterhorn · Copernicus DEM GLO-30"
}
```

- `maxzoom: 12` en la fuente (sobre z12 MapLibre puede sobredimensionar la tesela z12 para el sombreado, sin pedir teselas inexistentes).
- Resolución efectiva ~30 m: suficiente para leer laderas y quebradas a escala comunal.
- Atribución a registrar en `docs/FUENTES.md` y `web/data/licencias.json`: «© Mapterhorn · © DLR e.V. 2010-2014 / © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA» con enlace a <https://mapterhorn.com/attribution> y al DOI `10.5270/ESA-c5d3d65`.
- **Plan B documentado:** AWS Terrain Tiles (z15, SRTM/GMTED2010 dominio público USGS) con la plantilla de atribución de joerd; o autoalojar PMTiles de Chile en R2 si el tráfico lo justifica (la misma regla que FUENTES.md ya anota para las teselas vectoriales).

## Límites de esta investigación

- No se midió la calidad visual del sombreado (queda para el PR de MAPA-155).
- Mapterhorn podría incorporar fuentes de alta resolución para Sudamérica en el futuro; hoy Chile es solo GLO-30 (z0–z12).
- No se encontraron términos de servicio del endpoint `tiles.mapterhorn.com`; la lectura es «público hasta que el patrocinador diga lo contrario», como con todo servicio comunitario.
