# INV-04 · Registro público de quemas autorizadas (avisos de quema de CONAF)

**Veredicto: no** — no existe hoy un registro público y consultable de quemas autorizadas o avisadas que BRASA pueda cruzar con sus detecciones de calor. El registro existe (SAQ de CONAF), pero exige login de «usuario del fuego»; lo publicado (SHP y REST/WMS de IDE Minagri, corte 2021) es histórico y **sin fechas**, y el Calendario de Quemas solo dice cuándo se *puede* quemar por comuna, no qué se avisó. Parcialmente útil como contexto estático, nunca como verificación de una quema concreta.

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** responder si existe un registro público y consultable de avisos de quema de CONAF, por comuna y fecha, y decidir OFI-11 («marcar posible quema autorizada»). Cada afirmación lleva su fuente; lo que no se pudo verificar se marca **NO VERIFICADO**. El dataset `aviso_quema_2021` se descargó y se leyó completo; las consultas al servicio REST citadas se ejecutaron en esta sesión, igual que las verificaciones de SENAPRED, DMC, Bomberos, portales municipales y el catálogo ArcGIS de GEPRIF.

## Resumen ejecutivo

1. **El registro existe**: el SAQ (Sistema de Asistencia a Quemas Controladas) de CONAF registra cada aviso de quema con predio, coordenadas, superficie y la fecha y horas autorizadas en el comprobante (DS 276/1980, arts. 4° y 5°). **Pero no es consultable públicamente**: el sitio `saq.conaf.cl` solo abre con usuario y contraseña del «usuario del fuego».
2. **Lo que sí se publica es histórico y sin fechas**: IDE Minagri publica el SHP `aviso_quema_<año>` por temporada, con un punto por predio, comuna y superficie — pero solo hasta 2021 y sin el día de la quema (el campo temporal es `temporada = año`). El mismo corte 2021 se sirve por WMS y por un endpoint REST de ArcGIS que sí es consultable por comuna o por caja geográfica.
3. **La pieza «por comuna y fecha» que falta la cubre parcialmente el Calendario de Quemas**: una resolución anual (N°1148, 30-sep-2026) fija, comuna por comuna, los días y horas permitidos. Es la ventana autorizada, no la lista de quemas avisadas.
4. **Licencia: no declarada** en la página de descarga de IDE Minagri (**NO VERIFICADO** en la fuente primaria). La cosecha del Geo Nodo en el entorno `cert` de datos.gob.cl marca las capas como CC BY, pero los enlaces de descarga de esa cosecha ya no existen.
5. **Decisión para OFI-11: NO** con datos de hoy. No hay forma pública de saber que una quema concreta fue autorizada en una fecha concreta. Sí hay caminos parciales: el calendario vigente por comuna («hoy es día de quema permitido»), el historial predial 2012-2021 como prior de zonas quemadoras, y la etiqueta «posible quema agrícola» basada solo en evidencia local.
6. **Los otros canales institucionales no publican registro**: los municipios actúan como oficinas receptoras del aviso (canal del SAQ, no registro propio); SENAPRED deriva el aviso de quema «a CONAF o a tu municipio» y solo publica recomendaciones y alertas; la DMC publica avisos meteorológicos CAP (ya integrados); Bomberos publica estadística operativa; y el catálogo ArcGIS de GEPRIF (~80 capas públicas) no contiene ninguna capa de quemas.

## 1. Preguntas y método

**Preguntas**

- ¿Existe un registro consultable de avisos de quema de CONAF por comuna y fecha?
- ¿Es público? ¿Con coordenadas o solo comuna? ¿Bajo qué licencia y en qué formato?
- ¿Cada cuánto se actualiza? ¿Alcanza para OFI-11 (marcar «posible quema autorizada»)?

**Método**

- Lectura del DS 276/1980 (texto consolidado), de las páginas oficiales de CONAF («Uso del fuego», FAQ del SAQ, aviso en línea) y del formulario de comprobante.
- Descarga y lectura del SHP `aviso_quema_2021` de IDE Minagri (14.787 registros, campos y valores verificados en esta sesión).
- Consultas de prueba contra el MapServer de ArcGIS `IDEMINAGRI/QUEMAS_CONTROLADAS` (conteo por comuna y por caja geográfica).
- Revisión del Calendario de Quemas 2026-2027 (resolución y PDFs), del xlsx de estadísticas 1991-2023, del xlsx de oficinas receptoras 2026-2027, de datos.gob.cl (producción y `cert`) y de sondas a `saq.conaf.cl` para descartar una consulta pública.

## 2. El registro existe y se llama SAQ

El DS 276/1980 (Reglamento sobre Roce a Fuego, modificado por el DS 34/2016) obliga a avisar antes de quemar. Texto del artículo 4°, tal como está consolidado:

> «el propietario o poseedor del predio deberá manifestar ante la Corporación Nacional Forestal, a lo menos con un día de anticipación, su voluntad de usar el fuego en forma de Quema Controlada. Para tal fin, los interesados deberán avisar … a la Oficina Regional, Provincial o de Área … como en las Municipalidades que ésta determine **o a través del Sistema de Asistencia de Quemas** que la Corporación habilite para tales fines en su página web.»

Fuente: [BCN, Decreto 276, texto consolidado, art. 4°](https://www.bcn.cl/leychile/navegar?idNorma=147733); PDF del texto en [oficinavirtual.conaf.cl](https://oficinavirtual.conaf.cl/archivos/recursos/normativas_instructivos/Incendios/DTO-276-1980-MOD%20DTO%2034-%202016.pdf).

El artículo 5° dice que el comprobante fija «la fecha y horas» de la quema, y el 6° obliga a CONAF a comunicar la ejecución a Carabineros. Es decir, **el SAQ sí contiene aviso + fecha + horario + predio georreferenciado**. El formulario de comprobante confirma los campos (RUT, rol, predio, comuna, superficie, rango de fechas y horas, número de personas): [comprobante 2014 en saq.conaf.cl](https://saq.conaf.cl/documentos/b0a_Comprobante_de_aviso_de_quema_controlada__2014.pdf).

**Quién administra.** La página «Uso del fuego» dice que CONAF administra el uso del fuego «desde Arica y Parinacota hasta Magallanes»; el FAQ del SAQ (texto más antiguo) dice «entre las regiones de Coquimbo y Magallanes» y que en Atacama administra Carabineros. Los datos publicados cubren las 16 regiones (ver §3), así que en la práctica el SAQ es nacional. Fuentes: [CONAF, Uso del fuego](https://www.conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego/); [SAQ, FAQ](https://saq.conaf.cl/faq/listado.php).

**SAG y municipios.** El SAG no lleva un registro propio: es fiscalizador del DS 276 junto a Carabineros (FAQ del SAQ). Las municipalidades actúan como oficinas receptoras (p. ej., Pozo Almonte, Pica, Alto del Carmen, Huasco, Paihuano en el listado 2026-2027), pero el aviso converge al SAQ: el art. 4° habla de «las Municipalidades que ésta determine» como canal, no como registro aparte. No se encontró ningún registro público municipal de quemas: en Viña del Mar el municipio *fiscaliza* quemas ilegales (inspección comunal y drones) pero no publica permisos; en la Región de Valparaíso el listado oficial de oficinas receptoras solo muestra dependencias de CONAF; y en San Clemente el portal de procedimientos municipales no incluye un trámite ni una lista de quemas. Fuentes: [SAQ, FAQ](https://saq.conaf.cl/faq/listado.php); [CONAF, Oficinas receptoras 2026-2027 (xlsx)](https://www.conaf.cl/centro-documental/oficinas-receptoras/); [Prevención CONAF, Región de Valparaíso](https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-de-valparaiso/); [munivina.cl, «Municipio y Carabineros detienen riesgosa quema ilegal», 4-jul-2024](https://www.munivina.cl/noticias/municipio-y-carabineros-detienen-riesgosa-quema-ilegal-en-sector-alto-de-vina-del-mar/); [cpat.sanclemente.cl](https://cpat.sanclemente.cl/) — consultados el 19-oct-2026.

**Tres cosas que se confunden.** *Aviso de quema* es el trámite ante CONAF (o una municipalidad receptora) que termina en el comprobante del art. 5° — es lo que alimenta el SAQ. *Quema controlada* es la ejecución del protocolo (ventana autorizada + condiciones de seguridad); no hay registro público de ejecuciones, solo de avisos. *Permiso municipal* no existe como tal para quemas agrícolas/forestales: lo municipal es el rol de oficina receptora y la fiscalización; otra cosa son las quemas en zonas urbanas, que no entran al SAQ y se rigen por el DS 144 Minsal (quema de residuos en sitios no autorizados, prohibida). Los municipios además aplican restricciones propias de vigencia general — Valparaíso, Quilpué, Viña del Mar y Villa Alemana no pueden usar fuego entre noviembre y abril—, pero son prohibiciones, no permisos individuales publicados. Fuentes: [DS 276, arts. 4°-5°](https://www.bcn.cl/leychile/navegar?idNorma=147733); [SAQ, FAQ](https://saq.conaf.cl/faq/listado.php) (urbano = DS 144 Minsal); [Prevención CONAF, Región de Valparaíso](https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-de-valparaiso/).

**Acceso al SAQ.** `saq.conaf.cl` y `avisoenlinea.conaf.cl` abren a un formulario de RUT + contraseña. El aviso en línea exige predio inscrito, buena conducta del usuario del fuego, riesgo «Bajo» del predio para el mes y un tope de superficie. Las rutas `/consulta/`, `/mapa/`, `/visor/` y `/api/` responden 404: **no hay consulta pública** de avisos. Fuentes: [saq.conaf.cl](https://saq.conaf.cl/); [avisoenlinea.conaf.cl](https://avisoenlinea.conaf.cl/login/index.php) — ambos consultados el 19-oct-2026.

## 3. Qué se publica hoy y con qué detalle

| Canal | Qué contiene | Precisión | Temporal | Formato | Estado al 19-oct-2026 |
|---|---|---|---|---|---|
| **SAQ web** (`saq.conaf.cl`, `avisoenlinea.conaf.cl`) | Avisos reales con fecha y horas | Predio georreferenciado | El comprobante asigna fecha y horas (art. 5°) | Web | Solo con login de usuario del fuego |
| **IDE Minagri, QUEMAS PROGRAMADAS** | SHP `aviso_quema_2012` … `aviso_quema_2021` | Punto por predio, UTM 19S WGS84, escala 1:50.000 | `temporada` = año; **sin fecha** | SHP en `.rar` | Descarga directa verificada; 2022-2026 → 404 |
| **ArcGIS REST / WMS** (`esri.ciren.cl`) | Capa «SISTEMA DE ASISTENCIA DE QUEMAS 2021» | Misma capa 2021 (14.787 puntos) | Solo `temporada='2021'` | JSON (query), WMS | Vivo; consultas `where comuna=` y por bbox funcionan |
| **Calendario de Quemas 2026-2027** | Comunas/sectores con días y horas permitidos | Comuna (o sector de ella) | Días y horas; vigente | PDF escaneado (9 pág., sin capa de texto) | Resolución N°1148, 30-sep-2026; publicado 14-oct-2026 |
| **Páginas regionales** (`conafprevencionincendios.cl`) | Ventanas por región/provincia y criterios de suspensión | Provincia/comuna | Periodos del año | HTML | Ejemplos verificados: Araucanía, Los Ríos, RM |
| **Estadísticas Quemas 1991-2023** | N° de avisos y superficie tratada | Región | Por temporada | xlsx | Hasta 2023 (publicado mar-2024) |
| **datos.gob.cl** | Sin datasets de quemas CONAF en producción | — | — | — | Búsqueda `quema` y `quema controlada` → 0 datasets de CONAF (solo emisiones MMA); en `cert` hay fichas 2008/2015/2016 con enlaces muertos |

### 3.1 El SHP `aviso_quema_2021`, verificado en esta sesión

Descargado desde `ide.minagri.gob.cl/…/aviso_quema_2021.rar`. Shapefile de puntos, 14.787 registros, `temporada='2021'` en todos. Campos: `ID, REGION, PROVINCIA, COMUNA, NUM_AVISO, PREDIO, ROL_PREDIO, UBICACION, X, Y, SUPERFICIE, TIPO_Q, CLASE_Q, OBJ_Q, TEMPORADA`. Ejemplos reales: «LA FABRICA LAS ANIMAS», Arica, 0,1 ha, «QUEMAS AGRICOLAS»; «MOLINO», Camarones, 0,245 ha. Distribución por región (las mayores): La Araucanía 2.981, Ñuble 2.394, O'Higgins 1.316, Biobío 1.306, Maule 1.104.

**No hay fecha.** Ni día, ni mes, ni ventana autorizada: solo el año. Tampoco hay estado de ejecución: es un registro de *avisos* (intención declarada), no de quemas ejecutadas. El punto es del predio —el FAQ del SAQ dice que el sistema valida coordenadas UTM huso 19S (Coquimbo-Maule) u 18S (Biobío-Magallanes), WGS84—; el publicador advierte que eliminó «los registros inconsistentes en su georreferenciación». Fuentes: [IDE Minagri, Medio ambiente](https://ide.minagri.gob.cl/descarga-de-capas-shp/medio-ambiente/); [SAQ, FAQ, Datos espaciales](https://saq.conaf.cl/faq/listado.php).

### 3.2 El servicio REST sí es consultable — pero solo del corte 2021

`https://esri.ciren.cl/server/rest/services/IDEMINAGRI/QUEMAS_CONTROLADAS/MapServer` expone la capa 0 con capacidades `Map,Query,Data`. Consultas ejecutadas el 19-oct-2026:

- `…/0/query?where=comuna='MULCHEN'&returnCountOnly=true` → **190 avisos** (temporada 2021).
- `…/0/query?geometry=-72.6,-37.7,-72.5,-37.6&inSR=4326&returnCountOnly=true` → **18 avisos**.

Es decir, **la infraestructura para «consultable por comuna» existe y funciona**; el problema es el dato: cinco temporadas de atraso y sin fechas. El mismo servicio se ofrece como WMS desde el directorio de IDE Minagri. Fuentes: [IDE Minagri, Directorio de servicios](https://ide.minagri.gob.cl/directorio-de-servicios/); [MapServer QUEMAS_CONTROLADAS](https://esri.ciren.cl/server/rest/services/IDEMINAGRI/QUEMAS_CONTROLADAS/MapServer).

### 3.3 El Calendario de Quemas: lo más cercano a «comuna y fecha»

El art. 7° del DS 276 obliga a CONAF a dictar cada octubre una resolución «que contendrá el listado de comunas o sectores de ellas y los días y horas en los cuales se podrá usar el fuego». La de 2026-2027 es la **Resolución N°1148, del 30-sep-2026**, publicada en *Las Últimas Noticias* el 14-oct-2026, con PDFs por zona (norte/sur) — descargado y verificado: es un librillo escaneado sin capa de texto, no legible por máquina. Fuentes: [CONAF, Uso del fuego](https://www.conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego/); [conafprevencionincendios.cl, Calendario de Quemas](https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/); [centro documental, zona sur](https://www.conaf.cl/centro-documental/calendario-de-quemas-controladas-zona-sur/) y [zona norte](https://www.conaf.cl/centro-documental/calendario-de-quemas-controladas-zona-norte/).

**Ojo con lo que el calendario NO es**: es la *ventana permitida*, no el aviso. Para quemar hace falta además el comprobante del art. 5°, y aun con comprobante la quema se suspende por Botón Rojo, alertas, viento, clima, fines de semana y festivos o planes de descontaminación (DS 100 en RM y Cachapoal; PDA locales; criterios regionales). Ejemplos verificados: [Araucanía](https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-de-la-araucania/) (prohibición fines de semana; Temuco y Padre Las Casas abril-septiembre), [Los Ríos](https://www.conaf.cl/conaf-reitera-calendario-de-quemas-controladas-para-la-region-de-los-rios-en-la-temporada-2025-2026/) (ventanas por provincia; Valdivia sin fuego 1-may a 30-sep-2026 por PDA).

### 3.4 Licencia

- En la página de descarga de IDE Minagri **no aparece licencia** para las capas: **NO VERIFICADO** en la fuente primaria.
- La cosecha del Geo Nodo en `cert.datos.gob.cl` marca «Sistema Nacional de Quemas 2015», «Avisos de Asistencia de Quemas 2016» y «Base de datos Uso del Fuego 2008» con `license_id: cc-by`, pero es un entorno de certificación y sus enlaces de descarga a `geoportal.cl` responden 404 al 19-oct-2026.
- La Recomendación Técnica de IDE Chile sugiere CC BY 4.0 u ODbL para datos geoespaciales del Estado; es una guía, no una licencia aplicada ([IDE Chile](https://www.ide.cl/documentos/recomendacion-licencias-datos-geoespaciales.pdf)).
- En `datos.gob.cl` de producción no hay datasets de quemas de CONAF (`package_search?q=quema` devuelve solo dos datasets de emisiones del MMA; `q=quema+controlada` devuelve 0). **Conclusión: la licencia hay que confirmarla por escrito a CONAF/CIREN** — encaja con INV-02/ALI-01 (licencias de fuentes CONAF), que sigue abierto en el backlog.

### 3.5 Instituciones revisadas que **no** publican un registro consultable

| Institución | Qué publica | URL exacta | Formato | Frecuencia | Licencia/condiciones | Verificado |
|---|---|---|---|---|---|---|
| SENAPRED | Recomendaciones de prevención y alertas tempranas; deriva el aviso de quema «a CONAF o a tu municipio» | <https://www.senapred.cl/incendios-forestales/> | HTML | Continua | Sitio institucional público | 19-oct-2026: sin registro ni listado de quemas |
| DMC (Dirección Meteorológica) | Avisos y alertas meteorológicos en CAP 1.2 | <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php> | RSS + CAP XML | Continua | El propio RSS se declara «public domain» | 19-oct-2026: solo avisos meteo (viento, tormentas, lluvia); ya integrado en `backend/providers/dmc.py` |
| Bomberos de Chile (JNB) | Estadística operativa (SIB, SGAS) y noticias de respuesta | <https://www.bomberos.cl/> | HTML | Continua | Sitio público | 19-oct-2026: sin registro de quemas autorizadas; su rol es respuesta |
| Municipios (muestra) | Fiscalización de quemas ilegales; oficinas receptoras donde CONAF las habilita | <https://transparencia.munivina.cl/>, <https://cpat.sanclemente.cl/> | HTML / portales de transparencia | — | Sitios públicos | 19-oct-2026: Viña del Mar, Quilpué, Talca y San Clemente no publican avisos ni permisos de quema |
| Catálogo ArcGIS GEPRIF-CONAF | ~80 FeatureServers operativos (incendios, PI, perímetros, FIRMS) | <https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services> | REST JSON | Continua | «Uso público con cita a CONAF» declarado en algunos ítems (ver `docs/research/fuentes-meteologix-geprif.md` §2) | 19-oct-2026: 80 servicios listados; ninguna capa de quemas ni de avisos SAQ |

## 4. Respuesta a las preguntas

- **¿Existe el registro?** Sí: el SAQ registra cada aviso con predio georreferenciado y la fecha/horas asignadas en el comprobante.
- **¿Es público?** No en vivo. Público hay: cortes anuales SHP (2012-2021), el mismo corte por REST/WMS, el calendario anual por comuna y estadísticas regionales 1991-2023.
- **¿Consultable por comuna?** Sí (campo `comuna` en SHP y `where` en REST). **¿Por fecha?** **No**: lo publicado no tiene día; solo `temporada` anual. La fecha existe dentro del SAQ.
- **¿Coordenadas o solo comuna?** Punto por predio (UTM 19S WGS84, 1:50.000). Es la ubicación declarada del predio, no el perímetro ni el foco de la quema.
- **¿Licencia?** No declarada en la fuente (NO VERIFICADO); cosecha secundaria la marca CC BY.
- **¿Formato?** SHP en `.rar`, REST JSON/WMS (Esri), xlsx, PDF escaneado.
- **¿Cada cuánto se actualiza?** Corte anual por temporada; el último año predial publicado es 2021 — **cinco temporadas de atraso**. El calendario se renueva cada octubre; las estadísticas llegaron a 2023.

## 5. Decisión (OFI-11): **NO** con los datos públicos de hoy

No hay forma pública y consultable de saber que una quema concreta fue autorizada en una fecha concreta. Marcar una señal de calor como «posible quema autorizada» con una base oficial en vivo **no es posible hoy** — el dato existe pero está detrás del login del SAQ.

**Camino alternativo más cercano (recomendado):** explicar «posible quema» solo con evidencia local y contexto estático, sin afirmar autorización:

1. **Contexto estático por comuna** (curado a mano, anual): transcribir del calendario vigente los días permitidos por comuna → «hoy es día de quema permitido en la comuna X». El PDF es imagen y las restricciones regionales se publican dispersas en `conafprevencionincendios.cl`: la tabla sería editorial, no automática, y debe citar la resolución y la fecha de vigencia. Sirve como contexto, no como verificación de un aviso específico.
2. **Prior territorial** (opcional): los SHP 2012-2021 permiten mapear predios con avisos recurrentes. Útil como «zona con historial de quemas», nunca como «quema de hoy» — es historia, no permiso.
3. **Evidencia local** (la que ya tiene BRASA): patrón diurno, duración corta, temporada alta de quemas (dic-mar, cuando el calendario lo permite), uso de suelo agrícola, y la regla dinámica de `incidents.py` como respaldo. Etiqueta honesta: «posible quema agrícola», con la nota de que no se puede confirmar si tenía aviso.
4. **Nunca decir «quema autorizada» sin el dato.** Y aun con el dato: el aviso autoriza una ventana y no prueba la ejecución; una detección dentro de un predio avisado es una hipótesis, no una confirmación (mismo cuidado que INV-16 con las fuentes fijas).

**Qué haría falta para implementar OFI-11 bien:**

- **Dato:** una exportación periódica del SAQ con `num_aviso`, `comuna`, `x/y` (o polígono), fecha/ventana autorizada y estado (suspendida/ejecutada). Pedirla a CONAF por la vía institucional o por Ley de Transparencia (existe el canal «Solicitud de Información Ley de Transparencia» en conaf.cl); el contacto IDE Minagri/CIREN es el encargado CONAF de la mesa técnica (página «Nosotros» de IDE Minagri).
- **Licencia:** confirmación escrita de reutilización (hoy no declarada).
- **Integración si existiera la fuente:** ingesta diaria de la exportación (o consulta REST si CONAF abriera la capa vigente) → tabla `quemas_avisadas` con `num_aviso`, geometría, comuna, `desde`, `hasta`, `estado` → al evaluar una señal de calor, marca «posible quema autorizada» si hay aviso vigente a ≤ ~1-2 km (el umbral sale del error del píxel VIIRS/MODIS, no del dato SAQ); si no hay aviso vigente, «posible quema» sin el adjetivo.
- **Realidad operativa:** las quemas se concentran de día y en días permitidos; un Botón Rojo o fin de semana las suspende — el contexto del calendario ayuda a ponderar, no a confirmar.

### 5.1 Riesgos (regla no negociable: la marca anota, nunca silencia)

- **Registro desactualizado → incendio etiquetado como quema.** El riesgo central: un aviso vencido, suspendido o una base con días de atraso podría «explicar» un incendio real. Mitigación de diseño: la marca **anota, nunca silencia** — no baja el nivel del incidente, no suprime ni demora un aviso y no cambia el estado; solo añade contexto («hay un aviso de quema registrado cerca»). Y con datos como los de hoy (sin fechas, con cinco temporadas de atraso) la etiqueta «autorizada» simplemente no se usa.
- **Aviso ≠ ejecución.** El comprobante autoriza una ventana; no prueba que la quema ocurrió. La detección dentro de un predio avisado es una hipótesis (mismo cuidado que INV-16 con las fuentes fijas).
- **Calendario como verdad.** Los días permitidos se suspenden por Botón Rojo, alertas, viento, clima, fines de semana/festivos y PDA; usar «hoy es día permitido» como si fuera un aviso sería una afirmación falsa.
- **Licencia sin declarar.** Redistribuir cortes IDE Minagri sin confirmación escrita es el mismo riesgo que OFI-03 con el CSV de incendios.

## 6. Confianza

| Afirmación | Confianza | Por qué |
|---|---|---|
| No hay consulta pública de avisos vigentes | **Alta** | El SAQ abre solo con login; las rutas públicas razonables responden 404; no se halló otro canal oficial |
| Lo publicado no tiene fecha, solo año | **Alta** | Verificado en el .dbf de 2021 (15 campos) y en el esquema de la capa REST |
| Precisión predial con coordenadas | **Alta** | Punto UTM por predio verificado; el publicador filtró inconsistencias |
| Último corte publicado: 2021 | **Alta** | La lista llega a 2021; 2022-2026 → 404; el servicio REST solo tiene la capa 2021 |
| Licencia | **Media-baja** | No declarada en la fuente; el «CC BY» viene de una cosecha de certificación con enlaces muertos |
| Que no exista ningún otro canal público (p. ej., regional o municipal) | **Media** | No se puede probar la ausencia; se revisó el portal nacional, IDE Minagri, datos.gob.cl, páginas regionales de prevención, SENAPRED, la DMC, Bomberos, el catálogo GEPRIF y una muestra de portales municipales |

## 7. Fuentes consultadas (19 de octubre de 2026)

| Fuente | URL | Fecha | Qué sostiene |
|---|---|---|---|
| BCN, Decreto 276 (consolidado) | <https://www.bcn.cl/leychile/navegar?idNorma=147733> | Consultado 19-oct-2026 | Arts. 4° (aviso ≥1 día, SAQ), 5° (fecha/horas), 6° (aviso a Carabineros), 7°-8° (calendario por comuna) |
| CONAF, texto DS 276 (PDF) | <https://oficinavirtual.conaf.cl/archivos/recursos/normativas_instructivos/Incendios/DTO-276-1980-MOD%20DTO%2034-%202016.pdf> | Consultado 19-oct-2026 | Texto literal de los artículos citados |
| CONAF, Uso del fuego | <https://www.conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego/> | Consultado 19-oct-2026 | Qué es quema controlada; aviso ≥1 día; calendario; alcance nacional |
| SAQ, portada | <https://saq.conaf.cl/> | Consultado 19-oct-2026 | Sistema con login; documentos públicos; teléfonos regionales |
| SAQ, aviso en línea | <https://avisoenlinea.conaf.cl/login/index.php> | Consultado 19-oct-2026 | Requisitos del aviso en línea (predio inscrito, riesgo bajo, tope de superficie) |
| SAQ, FAQ | <https://saq.conaf.cl/faq/listado.php> | Consultado 19-oct-2026 | CONAF administra; SAG/Carabineros fiscalizan; Atacama por Carabineros; UTM por región; comprobante con días/horas; urbano = DS 144 Minsal |
| Formulario de comprobante | <https://saq.conaf.cl/documentos/b0a_Comprobante_de_aviso_de_quema_controlada__2014.pdf> | 2014 | Campos del aviso: fechas, horas, superficie, predio, rol |
| Minagri, aviso de quema controlada | <https://minagri.gob.cl/servicios/aviso-de-quema-controlada/> | Consultado 19-oct-2026 | El trámite y el comprobante «indica la hora y el día permitido» |
| Minagri, inscripción de predios | <https://minagri.gob.cl/servicios/inscripcion-de-predios-en-el-registro-de-quemas-controladas/> | Consultado 19-oct-2026 | Existencia del registro de usuarios del fuego |
| IDE Minagri, QUEMAS PROGRAMADAS | <https://ide.minagri.gob.cl/descarga-de-capas-shp/medio-ambiente/> | Consultado 19-oct-2026 | SHP `aviso_quema_2012`-`2021`, nivel predial, EPSG:32719 |
| SHP `aviso_quema_2021` | <https://ide.minagri.gob.cl/wp-content/uploads/DESCARGAS/CAPAS/MEDIO_AMBIENTE/QUEMAS_PROGRAMDAS_CONAF/aviso_quema_2021.rar> | Descargado 19-oct-2026 | 14.787 avisos; campos verificados; sin fecha |
| IDE Minagri, directorio de servicios | <https://ide.minagri.gob.cl/directorio-de-servicios/> | Consultado 19-oct-2026 | WMS «Quemas Controladas» = avisos del SAQ |
| ArcGIS REST QUEMAS_CONTROLADAS | <https://esri.ciren.cl/server/rest/services/IDEMINAGRI/QUEMAS_CONTROLADAS/MapServer> | Consultado 19-oct-2026 | Capa 2021 queryable (comuna=190 MULCHEN; bbox=18) |
| CONAF, Calendario zona sur | <https://www.conaf.cl/centro-documental/calendario-de-quemas-controladas-zona-sur/> | Consultado 19-oct-2026 | PDF 2026-2027 (escaneado, 9 páginas) |
| CONAF, Calendario zona norte | <https://www.conaf.cl/centro-documental/calendario-de-quemas-controladas-zona-norte/> | Consultado 19-oct-2026 | PDF 2026-2027 |
| Prevención CONAF, Calendario | <https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/> | Consultado 19-oct-2026 | Resolución N°1148 (30-sep-2026), publicado 14-oct-2026; suspensión posible |
| Prevención CONAF, Araucanía | <https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-de-la-araucania/> | Consultado 19-oct-2026 | Criterios de suspensión; veto fines de semana; PDA Temuco/Padre Las Casas |
| CONAF Los Ríos, calendario 2025-2026 | <https://www.conaf.cl/conaf-reitera-calendario-de-quemas-controladas-para-la-region-de-los-rios-en-la-temporada-2025-2026/> | 24-nov-2025 | Ventanas por provincia; PDA Valdivia |
| CONAF, Oficinas receptoras 2026-2027 | <https://www.conaf.cl/centro-documental/oficinas-receptoras/> | Consultado 19-oct-2026 | Oficinas CONAF y municipales por comuna |
| CONAF, Estadísticas Quemas 1991-2023 | <https://www.conaf.cl/centro-documental/estadisticas-quemas-1991-2023/> | Publicado 28-mar-2024 | xlsx con avisos y superficie por región/temporada (hasta 2023) |
| cert.datos.gob.cl (CKAN API) | <https://cert.datos.gob.cl/api/3/action/package_show?id=avisos-de-asistencia-de-quemas-2016-fd770f75> | Consultado 19-oct-2026 | Fichas 2008/2015/2016 marcadas cc-by; enlaces de descarga muertos |
| datos.gob.cl (CKAN API, producción) | <https://datos.gob.cl/api/3/action/package_search?q=quema> | Consultado 19-oct-2026 | Sin datasets de quemas CONAF |
| IDE Chile, recomendación de licencias | <https://www.ide.cl/documentos/recomendacion-licencias-datos-geoespaciales.pdf> | Consultado 19-oct-2026 | Guía que sugiere CC BY 4.0/ODbL; no es licencia aplicada |
| API IDE Minagri (CIREN) | <https://ideminagriapi.ciren.cl/> | Consultado 19-oct-2026 | Solo valida coordenadas/roles; no sirve datos de quemas |
| SENAPRED, incendios forestales | <https://www.senapred.cl/incendios-forestales/> | Consultado 19-oct-2026 | Deriva el aviso «a CONAF o a tu municipio»; sin registro propio |
| DMC, RSS de avisos (CAP 1.2) | <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php> | Consultado 19-oct-2026 | Solo avisos meteorológicos; RSS se declara «public domain»; ya integrado en `backend/providers/dmc.py` |
| Bomberos de Chile (JNB) | <https://www.bomberos.cl/> | Consultado 19-oct-2026 | Estadística operativa (SIB/SGAS); sin registro de quemas autorizadas |
| Prevención CONAF, Región de Valparaíso | <https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-de-valparaiso/> | Consultado 19-oct-2026 | Oficinas receptoras solo CONAF; veto nov-abr en Valparaíso, Quilpué, Viña del Mar y Villa Alemana; veto total en Puchuncaví (Res. 602/2011 Minsal) |
| Municipalidad de Viña del Mar | <https://www.munivina.cl/noticias/municipio-y-carabineros-detienen-riesgosa-quema-ilegal-en-sector-alto-de-vina-del-mar/> y <https://transparencia.munivina.cl/> | Noticia 4-jul-2024; portal consultado 19-oct-2026 | El municipio fiscaliza quemas ilegales; no publica permisos ni avisos |
| Municipalidad de San Clemente | <https://cpat.sanclemente.cl/> | Consultado 19-oct-2026 | Portal de procedimientos sin trámite ni lista de quemas |
| Catálogo ArcGIS GEPRIF-CONAF | <https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services> | Consultado 19-oct-2026 | 80 FeatureServers públicos listados; ninguno de quemas ni avisos SAQ |

## 8. Límites de esta investigación

- **No se probó que no exista un visor público**: se descartaron las rutas evidentes del SAQ, los portales nacionales, la muestra municipal y el catálogo GEPRIF, pero una oficina regional o un municipio podría publicar avisos por su cuenta (no se encontró ninguno).
- **«Visor Chile Preparado» de SENAPRED no se exploró capa por capa**: la página institucional no lista un registro de quemas, pero el visor pudo tener una capa no detectada desde el sitio (**NO VERIFICADO**).
- **No se vio el interior del SAQ**: sin credenciales no se sabe si el sistema tiene un export público o un modo de consulta ciudadana.
- **El calendario se citó desde las páginas oficiales y el PDF**, pero el PDF es imagen escaneada: no se leyó el listado comuna a comuna de la Resolución 1148. Transcribirlo a tabla es un paso de implementación, no de esta nota.
- **Los SHP anteriores a 2021 no se descargaron**: se asume el mismo esquema que 2021 por la descripción de la página; podría variar por año.
- **No se pidió información por Ley de Transparencia**: queda como acción si OFI-11 se prioriza.
- **«Aviso» no es «quema ejecutada»**: aun si el SAQ se abriera, la marca siempre sería probabilística.
