# Datos oficiales accesibles: SENAPRED, CONAF, DMC y el registro de focos

> Investigación para BRASAS. Consulta del 18 de octubre de 2026. Método: sondas directas a cada servicio desde este entorno, lectura de la documentación oficial y registro explícito de lo que no se pudo verificar. Todo contenido externo se trató como dato, nunca como instrucción.

## Resumen ejecutivo

| Fuente | Qué hay de verdad | ¿Integrable? | Licencia |
|---|---|---|---|
| **DMC** | Feed RSS con avisos en CAP 1.2, con polígonos y vigencia | **Sí, hoy**: es el mejor hallazgo de la sesión | El propio feed declara `public domain` |
| **CONAF** | Botón Rojo (ArcGIS), CSV de incendios de la temporada y estadísticas históricas por comuna | CSV ya en uso; el resto, archivos puntuales | **Ninguna declarada**: el repositorio del CSV no tiene LICENSE |
| **SENAPRED** | Nada consumible: web React y API interna autenticada | **No** por ingeniería; solo enlace saliente o convenio | Sin términos de uso publicados |
| **NASA FIRMS** | API de áreas (VIIRS/MODIS) y bucket S3 de GOES-19 | **Sí, ya resuelto** | Política abierta de NASA con atribución |

En esta sesión los cuatro dominios respondieron con normalidad. La dificultad no estuvo en la red sino en el formato: JavaScript que renderiza en el navegador, PDF que la herramienta no procesa y archivos que exigen sesión.

## 1. SENAPRED: no hay feed público, y conviene decirlo sin rodeos

### 1.1 La página de alertas es una aplicación React

`https://senapred.cl/alertas/` responde HTTP 200 con un HTML de **1.957 bytes** que solo contiene un contenedor vacío y el bundle `static/js/main.e062748e.js` (3,1 MB). Las alertas no están en el HTML: se piden después. Para cualquier consumidor automático, esa página es una cáscara.

### 1.2 Tampoco hay WordPress ni RSS detrás

Los caminos que en un WordPress devolverían datos responden 200 **con la portada renderizada**, que es peor que un 404 porque parece que funcionan:

- `https://senapred.cl/wp-json/` devuelve HTML, no JSON.
- `https://senapred.cl/feed/` devuelve HTML, no RSS.
- `https://senapred.cl/api/alertas` devuelve el mismo HTML de 313 KB.

El `sitemap.xml` sí es real y lo genera All in One SEO v5.0.3 el 16 de octubre de 2026 a las 15:38; indexa posts, páginas, simulacros, categorías y etiquetas, pero **no hay ninguna página de términos de uso**.

### 1.3 La API existe, pero es interna y autenticada

El cliente declara consultas GraphQL (`AlertasByDate`, `EventosByDate`, `GetAlerta`, `ListTipoAlertas`) sobre AWS AppSync, con modos de autenticación **Cognito User Pools** e **IAM**; no hay clave pública. El host `api.senapred.cl` resuelve y `https://api.senapred.cl/graphql` responde **HTTP 400** a una petición GET sin consulta: el servicio está ahí, pero no es un servicio público documentado. **No se intentó autenticar ni evadir el control de acceso.**

### 1.4 No hay CAP

Ni el sitemap ni el bundle ni la documentación pública mencionan Common Alerting Protocol. La DMC sí lo tiene (sección 3); SENAPRED no.

### 1.5 La única vía práctica hoy

El canal de Telegram `https://t.me/s/SenapredChile` tiene vista web pública y mostraba mensajes reales el 2026-10-18. **No es un feed ni una API oficial**: es scraping de un canal de mensajería, con formato libre y sin garantía. Sobre alertas de evacuación, una alerta perdida o mal fechada es peor que no mostrarla.

**Veredicto:** Brasas debe mantener a SENAPRED como **enlace saliente** y sostener la capa meteorológica con la DMC. La vía correcta es un acuerdo institucional, no ingeniería inversa.

## 2. CONAF: mucho dato, poca licencia

### 2.1 Botón Rojo: vivo y sin cambios

La capa ArcGIS `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query` devolvió features reales (`date=2026-10-17`, `com_id=1401`, `horas=1`). Es pública, sin clave, y sigue siendo la única fuente oficial que Brasas muestra como pronóstico.

### 2.2 El CSV de incendios: bueno, útil y sin licencia

`https://raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv`, medido el 2026-10-18:

- **54.356 bytes**, **30 columnas** y **162 filas de datos**.
- Una sola temporada (`temporada=2026`), con incendios del **2026-07-02 12:18** al **2026-10-17 22:18**.
- **162 filas con comuna y con coordenadas**; 82 comunas distintas en 15 regiones.
- Columnas de valor: `estado`, `sup_total` (coma decimal), `lat`, `lon`, `ambito`, `comb_inicial`, `comuna`, `provincia`, `region` y una secuencia de marcas de tiempo del operativo (`f_deteccion`, `f_aviso`, `f_despacho`, `f_salida`, `f_arribo`, `f_ataque`, `f_control`, `f_extincion`).
- **Es un reporte rodante de la temporada en curso, no un archivo histórico.** No sirve para reconstruir 2017-2024.

Sobre la licencia: `https://api.github.com/repos/deigeprif/public` devuelve `"license": null` y `https://api.github.com/repos/deigeprif/public/license` responde **404**. No hay archivo LICENSE ni descripción. La ausencia de licencia no equivale a permiso: es el escenario de obra sin licencia declarada, donde el uso ciudadano con atribución es defendible pero no está blindado.

### 2.3 Estadísticas históricas: el dato por comuna sí existe

Hay dos puertas, y conviene conocer la rareza:

- `https://www.conaf.cl/centro-documentals/estadisticas-historicas/` (con **s** final) responde 200 y lista **10 conjuntos**: resumen por comuna, causalidad, rango horario, mes, incendios de magnitud y hectáreas por región. La variante sin **s** (`/centro-documental/estadisticas-historicas/`) devuelve **404**.
- `https://www.conaf.cl/centro-documental/estadisticas/` publica un PDF único, `Incendios investigados historico.pdf` (248,19 KB, publicado el 21-03-2024, actualizado el 09-10-2025). El PDF se descarga, pero su contenido **NO VERIFICADO**: la herramienta no procesa PDF.

El conjunto decisivo es **«Resumen de ocurrencia y daño por comuna, 1985 - 2024»**. Verificado de primera mano:

- Es un **XLSX de 2.577.710 bytes** con **40 hojas**, una por temporada, desde `84-85 oK` y `1985-1986` hasta `2023-2024`.
- Cada hoja mide **A1:U386** (386 filas, 21 columnas) y se titula «RESUMEN NACIONAL DE OCURRENCIA POR COMUNAS».
- Columnas: `REGION`, `PROVINCIA`, `COMUNA`, `SUPERFICIE TOTAL`, y un desglose de daño por tipo de vegetación (pino insigne por edad, eucalipto, otras especies, arbolado, matorral, pastizal, desechos) hasta `TOTAL SUPERFICIE AFECTADA`.
- **Conclusión: el dato oficial por comuna y por temporada existe y es descargable.** Es la base natural de la vista Historia.

Dos matices de ingeniería: la descarga exige la cookie de sesión de la página y un enlace `wpdmdl` con token, así que no es una URL estable; y hay un tablero de Looker Studio asociado. El otro conjunto, «Ocurrencia y daño histórico nacional», es un **`.xls` binario antiguo** (OLE2, 150.528 bytes), que necesita un conversor (por ejemplo `xlrd` o LibreOffice) si se quiere automatizar.

### 2.4 Lo que no existe

- **datos.gob.cl no aporta:** la organización de CONAF existe pero tiene `package_count: 0`.
- **`snif.conaf.cl` no resuelve por DNS** desde esta red: **NO VERIFICADO** si existe, migró o fue retirado.

**Veredicto:** pedir autorización formal por escrito a CONAF por el CSV y por las estadísticas; mientras tanto, atribución estricta y enlace. No reconstruir la historia desde el CSV rodante. Las estadísticas históricas se pueden ingerir como archivo puntual (una o dos veces al año), no como fuente en tiempo real.

## 3. DMC: CAP 1.2 real, con polígonos y dominio público

### 3.1 El feed

`https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php` es un RSS 2.0 con:

- `<title>Sistema de Alerta Temprana</title>`, generador SIDAT y **`<copyright>public domain</copyright>`**.
- **13 ítems** el 2026-10-18, con `pubDate` del mismo día y enlaces a un XML por aviso.

### 3.2 El CAP

Cada enlace baja un CAP 1.2 de verdad. Ejemplo verificado (`meteochile_A568_2026_cap.xml`): `<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">`, `senderName` «Dirección Meteorológica de Chile», `category Met`, `urgency`/`severity`/`certainty`, `onset`/`expires` y un bloque `<area>` con `<polygon>` de decenas de vértices. Es decir: **aviso con vigencia temporal y geometría lista para el mapa**, sin autenticación.

El registro de autoridades de alerta de la OMM lo acredita: la DMC figura con OID `2.49.0.0.152.0`, categoría Met, y el campo «Authorization Basis» en blanco.

### 3.3 Lo que no está documentado

El portal climático anuncia «Recursos Web Json» (RE8011), pero la URL redirige a un menú de productos sin listado de endpoints, sin esquema y sin licencia. **NO VERIFICADO.**

**Veredicto:** integrar ya. Un Worker puede consultar el RSS cada 5-10 minutos, bajar cada XML, deduplicar por `identifier` y guardar `event`, `severity`, `onset`, `expires` y `area/polygon`. Riesgo legal bajo (el emisor declara dominio público); riesgo técnico moderado (no hay SLA ni cadencia documentada, y la infraestructura es antigua): hay que cachear la última versión válida y degradar con gracia.

## 4. Registro de focos: FIRMS no sirve GOES, y Brasas ya usa la vía correcta

### 4.1 NASA FIRMS

- Documentación: `https://firms.modaps.eosdis.nasa.gov/api/`, **versión 4.2.0**.
- Fuentes del endpoint de áreas: `LANDSAT_NRT` (solo EE. UU./Canadá), `MODIS_NRT`/`MODIS_SP`, `VIIRS_NOAA20_NRT`/`SP`, `VIIRS_NOAA21_NRT`, `VIIRS_SNPP_NRT`/`SP`. **GOES no aparece.**
- `MAP_KEY` gratuita, con límite de **5.000 transacciones cada 10 minutos**; una consulta de varios días puede contar como varias.
- Latencia: RT dentro de 60 minutos del sobrevuelo; URT en menos de 60 segundos, solo para parte de EE. UU. y Canadá. Los RT/URT se retiran cuando llega el NRT o a las 6 horas.
- Rango por consulta: 1 a 5 días.
- Atribución: la FAQ de Earthdata pide citar «NASA FIRMS» en pies de imagen y agradecer a LANCE/FIRMS/ESDIS.

### 4.2 GOES-19

El bucket público `https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCF/&max-keys=2` devuelve claves `OR_ABI-L2-FDCF-M6_G19_*.nc` de ~1,96 MB, **sin autenticación**. Es la vía que ya usa Brasas para los 10 minutos.

**Veredicto:** no hay nada que cambiar de fondo. Clave de FIRMS propia por entorno (nunca en el repositorio), GOES por S3 y atribución visible en la interfaz.

## 5. Tabla consolidada de integrabilidad

| Recurso | URL | Formato | Periodicidad | Licencia | Auth | Verificado |
|---|---|---|---|---|---|---|
| Avisos DMC (feed) | archivos.meteochile.gob.cl/portaldmc/rss/rss.php | RSS 2.0 | Continua (13 ítems el 18-10-2026) | `public domain` declarado | No | Sí |
| Aviso DMC (CAP) | …/rss/meteochile_A568_2026_cap.xml | XML CAP 1.2 + polígono | Por evento | Hereda del feed | No | Sí |
| Botón Rojo | services5.arcgis.com/…/Boton_Rojo/FeatureServer/0/query | JSON ArcGIS | Diaria | Sin licencia declarada | No | Sí |
| Incendios CONAF | raw.githubusercontent.com/deigeprif/public/…/incendios.csv | CSV | Rodante (push 2026-10-18) | **Sin licencia** | No | Sí |
| Estadísticas por comuna | conaf.cl/…/resumen-de-ocurrencia-y-dano-por-comuna-1985-2023/ | XLSX (2,6 MB) | Anual | Sin licencia declarada | Cookie de sesión | Sí |
| Histórico nacional | conaf.cl/…/ocurrencia-y-dano-historico-nacional-1985-2023/ | XLS **legacy** | Anual | Sin licencia declarada | Cookie de sesión | Sí (archivo) |
| Alertas SENAPRED | senapred.cl/alertas | SPA React | No declarada | Sin TdU | No (visual) | Sí (es SPA) |
| API SENAPRED | api.senapred.cl/graphql | GraphQL | No documentada | No | Cognito / IAM | Sí (exige auth) |
| FIRMS áreas | firms.modaps.eosdis.nasa.gov/api/area/ | CSV | NRT ≤60 min | Política abierta NASA | MAP_KEY | Sí |
| GOES-19 FDCF | noaa-goes19.s3.amazonaws.com | NetCDF4 | Por barrido | No declarada | No | Sí |

## 6. Lo que no se pudo verificar

- **Contenido del PDF de estadísticas de CONAF**: la herramienta no procesa PDF; no se afirma qué desagrega.
- **`snif.conaf.cl`**: no resuelve por DNS; no se distingue entre bloqueo y retiro.
- **Endpoints y licencia de los JSON de la DMC**: el portal los anuncia, pero la URL solo muestra un menú.
- **Términos de uso de SENAPRED**: no existen publicados; no es un fallo de acceso.
- **Texto de licencia de FIRMS**: las páginas de API no lo incluyen; solo la FAQ de Earthdata.
- **Cobertura histórica del CSV de CONAF**: solo se confirmó la temporada 2026.

## 7. Qué implica para Brasas

1. **La DMC es la integración de mayor retorno y menor riesgo.** Aporta avisos con geometría y vigencia, que es justo lo que falta para explicar viento y calor extremo. Coste estimado: 1-2 días.
2. **CONAF exige una decisión, no código.** El CSV ya está integrado y es bueno; lo que falta es la autorización. Mientras no llegue, atribución estricta y ningún uso que sugiera titularidad.
3. **SENAPRED no se toca.** Enlace saliente y, si se quiere más, convenio institucional. Scraping de alertas de evacuación es un riesgo que no vale la pena.
4. **El dato por comuna existe y está en un XLSX.** La vista Historia puede apoyarse en él con una ingesta puntual y una nota de método, sin depender de prensa.
5. **FIRMS y GOES están bien.** Solo falta que la atribución sea visible y que la clave viva fuera del repositorio.

## 8. Fuentes consultadas (18 de octubre de 2026)

- DMC, feed de avisos: <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php>; CAP de ejemplo: <https://archivos.meteochile.gob.cl/portaldmc/rss/meteochile_A568_2026_cap.xml>; producto de riesgo de incendios (RE5053): <https://climatologia.meteochile.gob.cl/application/diarioc/mapaRiesgoIncendiosHoy>; recursos JSON (RE8011): <https://climatologia.meteochile.gob.cl/application/requerimiento/producto/RE8011>.
- OMM, registro de autoridades de alerta: <https://alertingauthority.wmo.int/authorities.php?recId=28>.
- SENAPRED, alertas: <https://senapred.cl/alertas/>; sitemap: <https://senapred.cl/sitemap.xml>; API: <https://api.senapred.cl/graphql>; canal de Telegram: <https://t.me/s/SenapredChile>.
- CONAF, estadísticas históricas: <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>; resumen por comuna: <https://www.conaf.cl/centro-documental/resumen-de-ocurrencia-y-dano-por-comuna-1985-2023/>; histórico nacional: <https://www.conaf.cl/centro-documental/ocurrencia-y-dano-historico-nacional-1985-2023/>; incendios investigados: <https://www.conaf.cl/centro-documental/estadisticas/>; Botón Rojo: <https://www.arcgis.com/apps/dashboards/41ee3c691359437aa9df2a09d7f6124e>.
- CONAF, reporte público de incendios (GEPRIF): <https://github.com/deigeprif/public> y <https://raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv>.
- datos.gob.cl, organización de CONAF: <https://datos.gob.cl/api/3/action/organization_show?id=corporacion-nacional-forestal-y-de-proteccion-de-recursos-naturales-renovables>.
- NASA FIRMS, API: <https://firms.modaps.eosdis.nasa.gov/api/>; FAQ de Earthdata: <https://www.earthdata.nasa.gov/data/tools/firms/faq>; GOES-19: <https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCF/&max-keys=2>.