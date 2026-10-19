# INV-26 · ¿Se puede usar SINCA (MMA) para el humo y la calidad del aire?

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** decidir si el Sistema de Información Nacional de Calidad del Aire (SINCA, Ministerio del Medio Ambiente) sirve como fuente de MP2,5 **medido** para BRASA (OFI-10, INV-07), con qué licencia y por qué vía. Solo lectura y web, sin claves; dos consultas GET reales ejecutadas y reproducibles (§1). Relación: AGUA-05 (humo CAMS vía Open-Meteo) entrega **pronóstico** modelado; SINCA es la única vía encontrada con **medición real en terreno**.

## Resumen ejecutivo

1. **Sí existe acceso público sin clave**, dos vías, ambas verificadas hoy con GET reales: (a) JSON del mapa interactivo `index.php/json/listadomapa2k19/` — inventario completo de estaciones con lat/lon, comuna, red y las últimas ~24 h por contaminante (MP2,5 como media móvil 24 h + ICAP); (b) CGI de descarga horaria `cgi-bin/APUB-MMA/apub.tsindico2.cgi` — serie horaria real por estación y contaminante con columnas de validación (validado / preliminar / no validado), sin autenticación. Es la vía oficial de descarga que el propio sitio ofrece (GHDx documenta descargas CSV/TXT/PDF por estación desde 1992).
2. **Latencia observada:** ~2 h. El JSON del mapa se regenera cada hora (el portal declara actualización cada 1 hora) y el último dato disponible al consultar (17:44–17:58 UTC-04) era la hora 16:00 local.
3. **Cobertura:** 119 estaciones en el inventario del mapa, 92 con MP2,5; en el Maule 6 estaciones públicas en línea (Talca ×3, Curicó, Linares, Cauquenes), todas Red MMA. Las estaciones son urbanas (EMRP, representatividad poblacional): el dato medido existe en ciudades, no en la interfaz rural — para humo de incendio, SINCA **mide el impacto en población, no el humo en el foco**.
4. **Licencia: no hay licencia explícita de reutilización.** El pie de cada página dice «Todos los derechos reservados» y el sitio advierte que los datos son **preliminares** hasta validación operacional. Es la misma situación del CSV de incendios de CONAF (ya listada como decisión pendiente del dueño). Veredicto: **integrar, con puerta de licencia del dueño** (§4).
5. **Encaje:** OFI-10 como proveedor `backend/providers/sinca.py` (CGI horario para MP2,5 real + JSON del mapa para estado/ICAP), complementando el pronóstico CAMS de AGUA-05.

## 1. Acceso público real — consultas GET verificadas

**Fuentes**

- Mapa interactivo SINCA: <https://sinca.mma.gob.cl/mapainteractivo/index.html> (su JS, `mapa.js`, llama internamente `var g = { listado: "//sinca.mma.gob.cl/index.php/json/listadomapa2k19/" }`; documentado en `docs/sinca-internals.md` de py-atmchile, <https://github.com/maigonzalezh/py-atmchile> — consultado 19-oct-2026).
- Portal SINCA (declaración de frecuencia y carácter preliminar): <https://sinca.mma.gob.cl/> (consultado 19-oct-2026).
- GHDx (IHME), ficha del sistema: «data … can be downloaded in PDF, TXT, or CSV file formats», cobertura «01/1992 – present». <https://ghdx.healthdata.org/record/chile-national-air-quality-information-system-monitoring-station-database> (consultado 19-oct-2026).

### 1.1 JSON del mapa (tiempo quasi-real, todo el país en una consulta)

```
GET https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/
```

- Sin autenticación, sin cabeceras especiales. Responde un array JSON (~1,4 MB) con **119 estaciones** (cada una con `realtime` no vacío al momento de la consulta). Por estación: `nombre`, `key` (código numérico, p. ej. `"709"`), `latitud`, `longitud`, `comuna`, `red`, `region`, `regionindex`, `calificacion` (`Pública`/`Privada`/`no definida`), `empresa` (operador).
- `realtime[]` trae una entrada por contaminante (`code`: `PM25`, `PM10`, `0001` SO2, `0003` NO2, `0004` CO, `0008` O3) con `info.rows` = ~24 valores horarios `[hora, valor, color, tooltip]` y un `tableRow` resumen: `{status, statuscode, datetime, parameter, movil, value, unit, icap}`.
- **Ojo con la semántica:** el MP2,5 del JSON es `media móvil 24 h` (vista regulatoria ICAP), **no** el valor horario — amortigua los picos de humo. Para humo de incendio sirve el CGI horario (§1.2). Además, en `info.rows` el `v` numérico lleva un desplazamiento respecto del valor real del tooltip (p. ej. `v:18` → «8 µg/m³»); usar `tableRow.value` o el CGI, no el `v` crudo.
- **Campos verificados con datos reales (estación Curicó, `key:"709"`):** `{"nombre":"Curicó","key":"709","latitud":-34.974925,"longitud":-71.233967,"comuna":"Curicó","red":"Red MMA","region":"Región del Maule","regionindex":9,"calificacion":"Pública","empresa":"Ministerio del Medio Ambiente"}`, y `tableRow`: `{"status":"bueno","statuscode":1,"datetime":"2026-10-19 16:00","parameter":"MP 2,5","movil":"media móvil 24 h","value":8,"unit":"µg/m³","icap":16}`.
- **Latencia observada:** el JSON se generó «2026-10-19 17:44–17:58 hrs. UTC-04» (campo `datetime` por estación) y el último dato era 16:00 → ~2 h de rezago, consistente con la actualización horaria declarada. Las marcas son hora local Chile (UTC-04 en la respuesta, horario de invierno).

### 1.2 CGI de descarga horaria (histórico + reciente, valor horario real)

```
GET https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi?outtype=xcl&macro=./RVII/709/Cal/PM25//PM25.horario.horario.ic&from=261001&to=261003&path=/usr/airviro/data/CONAMA/&lang=esp&rsrc=&macropath=
```

- Sin autenticación. Es el endpoint de descarga que usa el propio portal (documentado por py-atmchile y AtmChile/R, U. de Chile–FONDECYT 1200674); coincide con la descarga CSV/TXT que GHDx describe como función pública del sitio.
- **Respuesta verificada:** CSV delimitado por `;` con columnas `FECHA (YYMMDD);HORA (HHMM);Registros validados;Registros preliminares;Registros no validados;`. Datos reales de Curicó (`RVII/709`), MP2,5, 1–3 oct 2026: 72 filas horarias, casi todas en `Registros validados` (p. ej. `261001;0100;9;;;` … `261002;0000;27;;;`), una en `preliminares` (`261002;0900;;1;;` — validación con rezago corto, no instantánea). Valores horarios reales en µg/m³N.
- Ruta `macro`: `./{REGIÓN}/{KEY}/Cal/{PARAM}//{PARAM}.horario.horario.ic&` con fechas `from`/`to` en `YYMMDD`. `REGIÓN` = prefijo romano (`RVII` para Maule), `KEY` = el `key` numérico del JSON (709 → `RVII/709`). Códigos de parámetro: `PM25`, `PM10`, `0001`, `0003`, `0004`, `0008`, `0NOX`; meteorología bajo `/Met/` (`TEMP`, `RHUM`, `WSPD`, `WDIR`). Fuente del mapeo: `docs/sinca-internals.md` de py-atmchile (consultado 19-oct-2026).
- **Advertencia:** endpoint **no documentado oficialmente** (descubierto por inspección); puede cambiar sin aviso. Misma clase de riesgo que la API interna de SENAPRED ya anotada como decisión pendiente en `CLAUDE.md`.

### 1.3 Otras vías descartadas o no verificadas

- `index.php/estacion/index/id/{id}` (p. ej. Curicó = id 269 en la página regional): ficha HTML de estación; **los `id` de ficha no coinciden con el `key` del JSON** (269 vs 709).
- `index.php/region/index/id/VII`: lista 9 estaciones del Maule incluidas las sin datos en línea (El Boldo/Curicó, Teno Cementos Bío Bío, Teno ENLASA — privadas u offline).
- `datos.mma.gob.cl`: **no resuelve** (GET falló); no existe un portal CKAN del MMA para SINCA. **NO VERIFICADO** si hay otro catálogo de datos abiertos del MMA.
- API REST documentada: **no existe** («SINCA has no publicly documented API», py-atmchile; igual lo asume AtmChile). **NO VERIFICADO** si el MMA entrega acceso formal a pedido.

## 2. Licencia y condiciones

- **No hay licencia explícita de reutilización en SINCA.** Pie de todas las páginas: «Copyright © 2009-2015 Ministerio de Medio Ambiente | Desarrollado por R9 Ingeniería | **Todos los derechos reservados**». <https://sinca.mma.gob.cl/> (consultado 19-oct-2026).
- Descargo del propio portal (texto de portada, cita textual): «La información presentada no corresponde a datos validados operacionalmente y puede estar afecta a cambios, por lo tanto deben tomarse como **datos Preliminares** para todos los efectos que corresponda.» <https://sinca.mma.gob.cl/> (consultado 19-oct-2026).
- Única «condición de uso» encontrada en el ecosistema MMA (portal IDE, sobre capas cartográficas): «La información cartográfica dispuesta en este portal web es de carácter referencial … El Ministerio del Medio Ambiente **no se hace responsable de los resultados, decisiones y/o acciones que puedan derivar del uso de esta información** …». <https://ide.mma.gob.cl/condiciones-de-uso> (consultado 19-oct-2026). Es un descargo, no una licencia.
- Precedente interno favorable pero no aplicable: la API abierta del RAACC del propio MMA («se publican como dato abierto, para que otros sistemas y personas las reutilicen sin intervención manual», <https://adaptacion.mma.gob.cl/datos-abiertos>) muestra que el MMA sí publica datos para reutilización cuando lo decide — SINCA no tiene esa declaración.
- Contexto legal: los datos son de acceso público por la Ley 20.285 (transparencia) y el portal los entrega sin registro ni clave; pero **acceso público ≠ licencia de reutilización**. Terceros lo tratan igual: chile-hub anota «datos públicos MMA sin licencia explícita; citar fuente oficial» (<https://tooltician.com/chile-hub/reference/datasets/calidad_aire/>, consultado 19-oct-2026).
- **Decisión del dueño:** integrar SINCA exige aceptar «uso razonable de dato público sin licencia, citando fuente» — idéntica a la ya pendiente del CSV de CONAF (`CLAUDE.md`, «Decisiones pendientes»).

## 3. Cobertura y frescura

- **Inventario (JSON 19-oct-2026):** 119 estaciones con `realtime` no vacío; MP2,5 en 92, MP10 en 82; `calificacion`: 62 pública, 50 privada, 7 no definida. La biblioteca py-atmchile cifra el universo en ~118 estaciones / 22 redes (CSV de estaciones, consultado 19-oct-2026).
- **Maule (regionindex 9):** 6 estaciones en línea, todas `Red MMA` / `Pública` / `Ministerio del Medio Ambiente`: La Florida (703) y U.C. Maule (710) y Universidad de Talca (711) en Talca; Curicó (709); Linares (713); Cauquenes Sivica (714). La página regional lista 9 incluidas El Boldo y dos de Teno privadas sin datos en línea.
- **Granulado:** horario real por el CGI (§1.2); el JSON solo da media móvil 24 h. Históricos: sí, por estación y rango (GHDx: desde 1992; validación en 3 columnas).
- **Frescura:** actualización horaria declarada; último dato ~2 h atrás al consultar (§1.1).
- **Sesgo de cobertura (clave para BRASA):** las estaciones son urbanas por diseño (EMRP). En el Maule cubren Talca/Curicó/Linares/Cauquenes; la interfaz rural (precordillera, comunas sin estación) queda sin medición — como advierte chile-hub: «ausencia de una comuna NO significa aire limpio, sino sin medición». Redes privadas forestales/industriales (CMPC, Colbún, ENAP en Biobío) agregan puntos en zonas productivas.

## 4. Veredicto y próxima acción

**Veredicto: integrar — con puerta de licencia.** SINCA aporta exactamente el dato **medido** que a CAMS/Open-Meteo (AGUA-05) le falta: MP2,5 horario real en terreno, sin clave, con históricos y validación explícita. Técnicamente es un GET simple; el riesgo es jurídico-operativo (sin licencia declarada, datos preliminares, endpoints no documentados), no técnico. La decisión de licencia es del dueño, no del agente: **NO VERIFICADO** si el MMA concede reutilización formal — alternativa honesta y sin costo es «solo enlazar» (mostrar estado ICAP con link a SINCA) mientras no haya autorización.

**Propuesta de encaje en el backlog (para el dueño, no implementada aquí):**

1. **OFI-10 (P2):** proveedor `backend/providers/sinca.py` con dos funciones: inventario/estado actual vía `listadomapa2k19` (cachear 1 h; ~1,4 MB por consulta, toda Chile en un solo GET) y serie horaria MP2,5 vía CGI (`from`/`to`, coalesce validado→preliminar→no validado). Mostrar como «medido en estación X a N km», nunca interpolado a comunas sin estación.
2. **AGUA-05:** SINCA queda como capa «ahora medido» junto al pronóstico CAMS; además permite validar el pronóstico a posteriori (comparar CAMS vs medido por estación).
3. **INV-07:** cerrar como **resuelto por esta investigación**: el acceso en tiempo real existe (§1), resta solo la decisión de licencia.
4. **Decisión previa requerida (dueño):** aceptar integración sin licencia explícita (como CONAF) o pedir autorización al MMA por OIRS/transparencia antes de integrar; mientras tanto, «solo enlazar» no requiere decisión.

**Riesgos a anotar en el ítem:** endpoint no documentado sujeto a cambios; dato preliminar que puede variar tras validación; medias móviles 24 h inadecuadas para detección rápida de humo (usar serie horaria); cobertura urbana — no afirmar «aire limpio» donde no hay estación; cortes de estación (la página de portada anuncia mantenciones programadas por región).
