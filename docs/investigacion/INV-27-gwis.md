# INV-27 · GWIS como capa de contexto (CC BY 4.0): ¿entra o no entra?

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** decidir si el Global Wildfire Information System (GWIS, JRC/Copernicus) entra en BRASA como capa de **contexto** — nunca como alerta — y dejar escritos los ítems si entra. Ítem de origen: `docs/research/00-sintesis-y-features.md` feature 12 (P2). Todas las sondas fueron GET, anónimas, sin clave.

## Resumen ejecutivo

**Veredicto: integrar, pero solo lo que BRASA no tiene.** El WMS de GWIS está verificado hoy, es global, gratis, sin clave, con CORS abierto y licencia CC BY 4.0. Entra como capa de contexto apagada por defecto: el **FWI ECMWF con su anomalía/ranking climatológico** (~40 años) y el **área quemada NRT** son valor que BRASA no produce; los **focos activos no entran** porque GWIS república NASA FIRMS con ~1 día de rezago — BRASA ya consume FIRMS NRT directo, con menor latencia y filtro propio.

## 1. Qué ofrece GWIS que sirva a BRASA

Catálogo de productos declarado en «Data and services» (<https://gwis.jrc.ec.europa.eu/applications/data-and-services>, consultado 19-oct-2026) y confirmado contra el `GetCapabilities` del WMS (266 nombres de capa, §2):

| Producto | Capas WMS verificadas | ¿Le sirve a BRASA? |
|---|---|---|
| Peligro de incendio (FWI y subíndices FFMC/DMC/DC/ISI/BUI) | `ecmwf.*` (ECMWF ~8 km), `mf025.*` (Météo-France ~10 km), `nasa_geos5.*` (GEOS-5 ~28 km) | **Sí, como contexto**: el FWI de pronóstico ECMWF a 1-9 días, y sobre todo `ecmwf.anomaly` y `ecmwf.ranking` (anomalía en σ y percentil contra ~40 años de historia), que BRASA no calcula |
| MARK-5, KBDI, NFDRS | `ecmwf.mark5.*`, `ecmwf.nfdrs.*` | No: duplican el mismo propósito que el FWI propio |
| Focos activos VIIRS/MODIS (1/7/30 días, temporada) | `viirs.hs`, `modis.hs`, `all.hs`, variantes `.today/.week/.month/.season` y por satélite `.n20/.n21/.suomi`, más `s3.hs` (Sentinel-3) | **No como dato**: es FIRMS republicado con más rezago (§5). Como mucho, `viirs.hs.week` podría pintarse en un modo «contexto global», pero no es prioridad |
| Área quemada NRT (MODIS & VIIRS) | `nrt.ba`, `nrt.ba.poly`, `nrt.ba.point.*`, `nrt.ba.bbox`, con variantes temporales | **Sí**: cicatriz reciente global, útil para combustible (RISK-12) y para la Historia |
| Área quemada mensual/anual/frecuencia (MCD64A1) | `mcd64a1.*` | Posible a futuro; no verifiqué su contenido sobre Chile |
| Emisiones GFAS (CO₂, PM2,5, aerosoles, 7 días) | `gfas.*` | Posible contexto de humo (complementa DET-04/GOES); no prioridad |
| Mapa de combustible, usos de suelo, áreas protegidas, asentamientos | `fuel_map`, `landcover.*`, `wdpa*`, `ghsl` | No como capa en vivo; `fuel_map` podría servir para contexto estático |
| Pronóstico de rayos ECMWF | `ecmwf.extra.lightning` | BRASA ya tiene GLM (GOES); redundante |

## 2. Endpoints verificados hoy (19-oct-2026)

Servicio real: un **MapServer WMS 1.1.1** en `https://maps.effis.emergency.copernicus.eu/gwis` (los enlaces de descarga de la propia página «Data and services» apuntan ahí; no hay GeoServer bajo `gwis.jrc.ec.europa.eu` — `/geoserver/ows` y `/geoserver/wms` responden 404). Sin registro ni clave. `Server: lighttpd/1.4.74`, `Access-Control-Allow-Origin: *`, `Cache-Control: public, max-age=3600`.

| Operación | URL (recortada) | HTTP | Content-Type | Resultado |
|---|---|---|---|---|
| GetCapabilities | `…/gwis?SERVICE=WMS&REQUEST=GetCapabilities` | 200 | `application/vnd.ogc.wms_xml` | 197 173 B en 0,8 s; WMS 1.1.1; operaciones: GetMap, GetFeatureInfo, DescribeLayer, GetLegendGraphic, GetStyles; SRS: EPSG:3034/3035/**3857**/4326/900913 |
| GetMap focos VIIRS, 7 días, Chile | `…/gwis?LAYERS=viirs.hs&SERVICE=wms&VERSION=1.1.1&REQUEST=GetMap&STYLES=&SRS=EPSG:4326&BBOX=-76,-56.5,-65.5,-17&WIDTH=800&HEIGHT=1200&TIME=2026-10-12/2026-10-18&FORMAT=image/png&TRANSPARENT=true` | 200 | `image/png` | 28 887 B en ~1 s; PNG decodificado 800×1200 RGBA con **10 821 píxeles visibles** (focos reales sobre Chile) |
| GetMap focos VIIRS, temporada 2026 | misma, `TIME=2026-02-01/2026-02-10` | 200 | `image/png` | 27 912 B; 11 328 píxeles visibles |
| GetMap focos MODIS, 7 días | `LAYERS=modis.hs`, `TIME=2026-10-12/2026-10-18` | 200 | `image/png` | 8 525 B; 1 471 píxeles visibles (más grueso, esperable: píxel de 1 km y MODIS en retiro) |
| GetMap FWI ECMWF, pronóstico | `LAYERS=ecmwf.fwi`, `TIME=2026-10-20` | 200 | `image/png` | 31 135 B en ~1 s |
| GetMap área quemada NRT 2026 | `LAYERS=nrt.ba`, `TIME=2026-01-01/2026-10-18` | 200 | `image/png` | 31 272 B; 8 439 píxeles visibles |
| GetMap área quemada NRT 2024 | `LAYERS=nrt.ba`, `TIME=2024-01-01/2024-12-31` | 200 | `image/png` | 23 503 B; 5 548 píxeles visibles (temporada del megaincendio de Valparaíso) |
| GetMap en EPSG:3857 (tiles MapLibre) | `LAYERS=viirs.hs&SRS=EPSG:3857&BBOX=-8455000,-7265000,-7280000,-1900000&WIDTH=512&HEIGHT=512` | 200 | `image/png` | 18 766 B en 0,9 s |
| GetFeatureInfo foco | `LAYERS=viirs.hs.query&QUERY_LAYERS=viirs.hs.query&…&X=312&Y=562&INFO_FORMAT=application/vnd.ogc.gml` | 200 | `application/vnd.ogc.gml` | Atributos completos por foco: `lon/lat`, `acq_date`, `frp`, `confidence`, `satellite`, `bright_mir/tir`, `gid_0=CHL`, `name_1=Maule`, `name_2=Talca`. Ejemplo real: foco en Talca 2026-10-15 06:40 UTC, S-NPP/VIIRS, FRP 2,2 MW, confianza High |
| WFS GetCapabilities | `…/gwis?SERVICE=WFS&REQUEST=GetCapabilities` | — | — | **Timeout de lectura en 2 intentos (30 s y 90 s): no hay WFS usable** |
| Sitio: licencia | `https://gwis.jrc.ec.europa.eu/about-gwis/data-license` | 200 | `text/html` | Texto de licencia citado en §3 |
| Sitio: Country Profile | `https://gwis.jrc.ec.europa.eu/apps/country.profile/` | 200 | `text/html` | App carga (SPA); contenido por país no sondeado |

Notas de uso verificadas:

- `TIME` va como rango ISO `desde/hasta` (`2026-10-12/2026-10-18`) o fecha sola para pronósticos. Las capas `*.today/.week/.month/.season` son ventanas rodantes y **no exigen TIME** (no tienen dimensión temporal en las capabilities): simplifican una capa de contexto.
- `STYLES=` (aunque vacío) es obligatorio en GetMap/GetFeatureInfo; sin él el servidor responde `ServiceException MissingParameterValue` (exigencia de MapServer ≥ 8).
- `INFO_FORMAT`: `text/plain` devuelve solo IDs de feature; `application/vnd.ogc.gml` devuelve los atributos; `application/json` es rechazado (`Unsupported INFO_FORMAT`).
- No hay descarga bulk WFS: la «descarga» que ofrece la página es el propio GetMap a tamaño completo (p. ej. 5120×2560 para ECMWF).

## 3. Licencia y atribución

Fuente oficial: <https://gwis.jrc.ec.europa.eu/about-gwis/data-license> (consultado 19-oct-2026). Texto:

> «Unless otherwise indicated (e.g. in individual copyright notices), content owned by the EU on this website is licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0) licence. This means that reuse is allowed, provided appropriate credit is given and changes are indicated.»

Obligaciones prácticas: atribuir a la Unión Europea/GWIS, enlazar <https://creativecommons.org/licenses/by/4.0/> y declarar cambios (en BRASA: «capa remosaiciada por BRASA, sin modificar el dato» o indicar el reescalado). La propia página «Data and services» recuerda: «By using the data provided you acknowledge the following terms of use under this license».

Matiz no resuelto: los focos activos de GWIS **son datos de NASA FIRMS republicados** (lo dice la página técnica, §5). La titularidad última de esos píxeles es de NASA (datos de uso abierto), no de la UE; la licencia CC BY 4.0 de la página cubre el servicio GWIS. **No verificado**: si el aviso de atribución debe nombrar a ambos. Atribución conservadora: «© Unión Europea, GWIS/EFFIS (CC BY 4.0); focos: NASA FIRMS».

## 4. Resolución, latencia y cobertura de Chile

**Puede afirmarse (verificado o citado de fuente):**

- **Cobertura global real, incluido Chile.** `LatLonBoundingBox` de `viirs.hs` y `ecmwf.fwi`: −180…180, −90…90 (`nrt.ba` se recorta a −60…70 lat, suficiente para Chile continental). Los GetMap sobre el bbox de Chile devuelven píxeles de verdad, no vacío (§2).
- **Resolución fuente**: focos VIIRS 375 m y MODIS 1 km; FWI ECMWF ~8 km, Météo-France ~10 km, GEOS-5 ~28 km (<https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/active-fire-detection> y `…/fire-danger-forecast`, consultados 19-oct-2026). El WMS entrega ráster: la resolución efectiva en pantalla la fija el tile pedido.
- **Latencia de focos**: la página técnica declara actualización diaria, «available in GWIS within 1 day the acquisition of the MODIS/VIIRS images» — más lento que el FIRMS NRT (~3 h) que BRASA ya usa.
- **Latencia del FWI ECMWF**: pronóstico de 1 a 9 días (Météo-France ≤3 días, GEOS-5 6 días), con `TIME=fecha` del día del pronóstico.
- **Clases del FWI GWIS** (misma fuente): 6 clases armónicas globales — Low <11,2 · Moderate 11,2–21,3 · High 21,3–38 · Very High 38–50 · Extreme 50–70 · **Very Extreme >70** (clase añadida jun-2021). `ecmwf.anomaly` = desviación estándar contra ~40 años; `ecmwf.ranking` = percentil.
- **Rendimiento observado**: GetMap Chile ~0,6-1,1 s por imagen de 800×1200; tile 512² en EPSG:3857 ~0,9 s; caché HTTP 1 h.

**No puede afirmarse (no verificado):**

- SLA, uptime o política de rate-limit: no hay términos de servicio visibles; es un servicio público «tal cual».
- Frecuencia exacta de refresco de `nrt.ba` ni de `ecmwf.*` en producción (la página dice «diario» para focos; para peligro solo el rango de pronóstico).
- Atributos de `nrt.ba` vía GetFeatureInfo (probada solo `viirs.hs.query`).
- Cuánto de los píxeles `nrt.ba` sobre Chile corresponde a cicatrices validadas vs. falsos positivos NRT.

## 5. Encaje en BRASA

Cómo se vería si entra (patrón de las capas actuales de `web/js/views/mapa.js`, que ya son opcionales con switch + leyenda, y de DET-04 «capa opcional»):

- **Capa ráster WMS apagada por defecto**, activable en el menú de capas del mapa. MapLibre puede consumir el WMS directo desde el navegador (CORS `*`, EPSG:3857, tiles de 512 px): no exige proxy ni backend. Source `type: 'raster'` en `web/js/map.js` con `attribution` propia; switch + leyenda + fecha del dato (`TIME`) en `web/js/views/mapa.js`.
- **Mutuamente excluyente con «Peligro de incendio hoy»**: la capa FWI-GWIS pisa visualmente el relleno por comuna del riesgo propio; el switch debe apagar `risk`/`rain` al encenderse (el código ya hace eso entre `risk` y `rain`).
- **Atribución y fecha visibles**: el mapa ya muestra `customAttribution` (`web/js/map.js:228`); agregar «Contexto: GWIS/EFFIS © UE, CC BY 4.0» mientras la capa esté encendida, y la leyenda debe decir la fecha del `TIME` consultado.
- **Nunca como alerta ni como «el FWI de BRASA»**: la app etiqueta sus niveles como «aproximación BRASA» calculada con Open-Meteo/DMC. La capa GWIS se rotula como **contexto externo** («peligro según GWIS/ECMWF»), no se mezcla en el nivel por comuna ni dispara avisos. Si discrepa del nivel propio, la respuesta es la calibración (RISK-13), no ocultar una de las dos.
- **Los focos GWIS no entran**: son FIRMS republicado con más rezago y sin el filtro de confianza/fuentes fijas que BRASA ya aplica (INV-16). Duplicar el mismo píxel con otro color confunde; la única excepción razonable sería un toggle «contexto global» para mirar fuera de Chile, no prioridad.

## 6. Riesgos y coste

- **Dependencia externa sin SLA**: si `maps.effis.emergency.copernicus.eu` cae, la capa queda en blanco; mitigación: la capa es opt-in y el switch debe tolerar tiles fallidos (MapLibre ya lo hace mostrando el fondo; el patrón `basemapOffline` del repo es el precedente).
- **Endpoint opaco**: no hay documentación formal del API WMS fuera del propio GetCapabilities; las URLs de capas se descubrieron inspeccionando la página oficial. Un cambio de mapfile del JRC puede renombrar capas: mitigación con un chequeo de salud semanal (ítem abajo).
- **Sin clave ni registro hoy**; no se encontró paywall ni rate-limit documentado.
- **Coste**: PR pequeño (~1-2 días, coincide con la estimación del backlog): un source ráster + un switch + leyenda + atribución, sin backend ni datos nuevos que ingerir. Segunda capa (área quemada) repite el patrón: S.
- **Lo que no hay que construir**: ingesta, almacenamiento, ni jobs: el WMS se consulta en vivo desde el navegador y su caché de 1 h amortigua el tráfico.

## 7. Próximos ítems (si el dueño aprueba el veredicto)

| ID sugerido | Qué | Archivos a tocar | Criterio de listo |
|---|---|---|---|
| OFI-17 | **Capa de contexto «Peligro GWIS (ECMWF)»**: source ráster WMS `ecmwf.fwi` (o `ecmwf.ranking`, mejor aún para «¿es raro este día?») en tiles EPSG:3857, apagada por defecto, excluyente con `risk`/`rain`, con atribución CC BY 4.0 + enlace a la licencia + fecha del `TIME` en la leyenda | `web/js/map.js`, `web/js/views/mapa.js` | En el mapa se puede encender, se ven las clases de peligro sobre Chile, la leyenda declara fuente/fecha/licencia, y no modifica el nivel de riesgo propio |
| OFI-18 | **Capa «Área quemada reciente (GWIS NRT)»**: `nrt.ba` o `nrt.ba.poly.month` (ventana rodante, sin TIME), misma mecánica de switch y atribución; aporta a RISK-12 (combustible quemado) | `web/js/map.js`, `web/js/views/mapa.js` | Capa opcional con cicatrices visibles sobre Chile y fecha de consulta declarada |
| OFI-19 | **Salud del endpoint GWIS**: chequeo semanal en `.github/scripts/fuentes_salud.py` que haga GetCapabilities y confirme que `ecmwf.fwi`/`nrt.ba` siguen listadas (el servicio puede renombrar capas sin aviso) | `.github/scripts/fuentes_salud.py` | El chequeo corre en CI programado y falla con mensaje claro si la capa desaparece |
| (opcional) OFI-20 | **Popup «qué es este punto» con GetFeatureInfo** sobre `viirs.hs.query` (GML) solo cuando una capa GWIS esté encendida — muestra fecha, FRP, confianza, satélite | `web/js/map.js`, `web/js/views/mapa.js`, `web/js/api.js` si se prefiere via backend | Click sobre un foco GWIS muestra sus atributos con fuente citada |

**Si en cambio se decidiera «no integrar»**: la razón sería que el valor diferencial real (anomalía/ranking climatológico del FWI) se puede calcular en casa contra ERA5 (ya usado para lluvia, RISK-02) sin depender de otro servicio. Lo que cambiaría el veredicto hacia «integrar»: un pedido explícito de contexto global o de contraste visual del FWI propio contra el europeo.

## Fuentes

- GWIS, «Data License»: <https://gwis.jrc.ec.europa.eu/about-gwis/data-license> (consultado 19-oct-2026, HTTP 200) — CC BY 4.0, atribución + declarar cambios.
- GWIS, «Data and services»: <https://gwis.jrc.ec.europa.eu/applications/data-and-services> (consultado 19-oct-2026, HTTP 200) — catálogo de productos y enlaces de descarga WMS.
- WMS GWIS/EFFIS (MapServer): `https://maps.effis.emergency.copernicus.eu/gwis` — GetCapabilities y GetMap/GetFeatureInfo verificados el 19-oct-2026 (tabla §2).
- GWIS, «Active Fire Detection»: <https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/active-fire-detection> (consultado 19-oct-2026) — focos = NASA FIRMS; VIIRS 375 m / MODIS 1 km; «within 1 day»; «not all hotspots are fires».
- GWIS, «Fire Danger Forecast»: <https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/fire-danger-forecast> (consultado 19-oct-2026) — ECMWF ~8 km (1-9 días), Météo-France ~10 km (≤3), GEOS-5 ~28 km (6); clases FWI y clase Very Extreme >70; anomalía/ranking contra ~40 años.
- CC BY 4.0, texto de la licencia: <https://creativecommons.org/licenses/by/4.0/> (consultado 19-oct-2026).
- En el repo: `docs/research/04-deteccion-temprana-comunitaria.md` §6.4 («GWIS como contexto global, no EFFIS como fuente local»); `docs/investigacion/INV-16-industria-antorchas.md` (falsos positivos y filtro propio); `web/js/map.js`, `web/js/views/mapa.js` (patrón de capas opcionales y atribución).
