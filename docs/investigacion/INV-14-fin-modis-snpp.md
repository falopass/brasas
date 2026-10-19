# INV-14 · Fin de S-NPP y de MODIS: impacto en los casos y en el botón «Sumar VIIRS/MODIS»

> Investigación para BRASA Chile. **Consulta:** 19 de octubre de 2026. **Alcance:** qué pasa con el archivo FIRMS SP de Suomi NPP y MODIS tras los retiros (2-nov-2026, feb-2027, sep-2027), efecto en el botón «Sumar VIIRS/MODIS (FIRMS)» de la Historia y cobertura SP del caso 2026 (CONT-07). Solo lectura y web; **no hubo clave FIRMS_MAP_KEY disponible**, así que la disponibilidad real por fecha queda marcada **NO VERIFICADO**.

## Resumen ejecutivo

1. **El archivo SP no se pierde.** Lo que cesa es la *entrega de datos nuevos*: S-NPP el 2-nov-2026 13:00 UTC (aviso NESDIS), MODIS Terra ~feb-2027 y Aqua ~sep-2027 (nota editorial de NASA Science). Para S-NPP hay declaración explícita (NSIDC) de que el acceso histórico seguirá disponible; para MODIS, la propia NASA planea un **reprocesamiento final v8.0 de toda la colección** (LAADS), lo que es incompatible con un archivo que desaparece. No encontré declaración explícita del equipo FIRMS sobre su herramienta de descarga: **NO VERIFICADO** en ese detalle, pero todas las señales apuntan a que persiste.
2. **El botón sigue funcionando.** `POST /api/cases/{id}/polar` consulta solo productos **SP** (`firms_sources` de cada caso) sobre la ventana histórica del caso. Los 6 casos actuales son 2011-2026: todo su archivo SP ya existe y el retiro no lo toca.
3. **Lo que cambia es para casos *nuevos*.** Un caso posterior al 2-nov-2026 no tendrá detecciones S-NPP; posterior a sep-2027 no tendrá MODIS. Dejar esos productos en `firms_sources` solo gasta cuota de la API. La ingesta en vivo ya está bien: `FIRMS_SOURCES` por defecto usa solo `VIIRS_NOAA20_NRT` y `VIIRS_NOAA21_NRT`, y `.env.example` ya advierte el retiro de S-NPP.
4. **CONT-07 (caso Penco–Lirquén, 17-20 ene 2026):** casi con seguridad el SP ya lo cubre — el archivo estándar va con ~2-3 meses de rezago (FAQ) y la página de descarga acota el reemplazo NRT→SP a ~5 meses; enero-2026 quedó atrás hace ~9 meses. **NO VERIFICADO**: sin `FIRMS_MAP_KEY` no pude consultar `data_availability` ni una fecha real.
5. **Cambios recomendados:** mínimos y opcionales; ninguno es urgente. Ver §4.

## 1. Pregunta 1 · ¿FIRMS mantendrá el archivo SP de S-NPP tras nov-2026 y de MODIS tras sus retiros?

**Fuentes**

- NESDIS/NOAA, «Cessation of Suomi NPP data to users on/after November 2, 2026», emitido 3-ago-2026. <https://www.nesdis.noaa.gov/news/cessation-of-suomi-national-polar-orbiting-partnership-s-npp-data-users-onafter-november-2-2026> (consultado 19-oct-2026).
- NASA Earthdata, «Suomi NPP Data Product Delivery to Cease on November 1, 2026», emitido 7-ago-2026. <https://www.earthdata.nasa.gov/data/alerts-outages/suomi-npp-data-product-delivery-cease-november-1-2026> (consultado 19-oct-2026).
- NSIDC DAAC, «User Notice: S-NPP/VIIRS data sets — Cessation of Data Delivery», 6-oct-2026. <https://nsidc.org/data/user-resources/data-announcements/user-notice-s-nppvisible-infrared-imaging-radiometer-suite-viirs-data-sets-cessation-data-delivery> (consultado 19-oct-2026).
- NASA Science, «Terra: The End of An Era» (nota editorial con las fechas de fin de ciencia). <https://science.nasa.gov/science-research/earth-science/terra-the-end-of-an-era/> (consultado 19-oct-2026).
- NASA LAADS DAAC, «MODIS to VIIRS Transition». <https://ladsweb.modaps.eosdis.nasa.gov/learn/modis-to-viirs-transition> (consultado 19-oct-2026).
- NASA Earthdata, «Transition from MODIS to VIIRS», emitido 2-may-2025. <https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs> (consultado 19-oct-2026).
- NASA FIRMS, «Archive Download». <https://firms.modaps.eosdis.nasa.gov/download/> (consultado 19-oct-2026).
- NASA Earthdata, «FIRMS FAQ». <https://www.earthdata.nasa.gov/data/tools/firms/faq> (consultado 19-oct-2026).

**Respuesta**

- **Fechas de cese confirmadas:** NESDIS anunció (3-ago-2026) que la entrega de *todos* los productos S-NPP —incluido VIIRS— cesa el **2-nov-2026 a las 13:00 UTC** de forma permanente; Earthdata lo emitió como 1-nov-2026 13:00 UTC y NSIDC lo precisó al 2-nov (la tabla del backlog usa 2-nov, correcto). Para MODIS, la nota editorial de NASA Science proyecta el fin de ciencia de **Terra en feb-2027 y Aqua en sep-2027** (coincide con la tabla del backlog); el plan de instrumentos (MODIS Science Team, mar-2026) habla de fin de ciencia de Terra ~1-mar-2027: fechas aún móviles.
- **El retiro es de entrega nueva, no del archivo.** NESDIS solo anuncia fin de «delivery». NSIDC lo dice explícito para S-NPP: *«access to the historical data and documentation will still be available»*. Para MODIS, LAADS anuncia un reprocesamiento **v8.0 final de toda la colección** tras el fin de operaciones — un archivo que se va a borrar no se reprocesa entero.
- **El SP de fuego tiene doble respaldo.** Según el FAQ de FIRMS, el producto estándar **MCD14ML** (lo que BRASA consume como `*_SP`) lo produce el MODIS Fire Team Science Computing Facility de la Universidad de Maryland y también se distribuye directo por UMD; además el archivo completo se reprocesa periódicamente por «colecciones» (C6.1 desde abr-2021). La página de descarga de FIRMS sigue listando cobertura «desde 2000/2012 hasta el presente» sin aviso de retiro de datos históricos.
- **Vacío honesto:** no hay una declaración del equipo FIRMS que diga «el Archive Download seguirá sirviendo S-NPP/MODIS post-retiro». El único aviso del equipo FIRMS (página de outages) repite el cese de S-NPP y recomienda migrar a NOAA-21/20. **NO VERIFICADO** en ese punto específico.

**Confianza:** alta para S-NPP (declaración explícita de archivo persistente) y media-alta para MODIS (inferida del reprocesamiento v8.0 y del patrón EOSDIS; sin declaración explícita de FIRMS).

**Decisión:** asumir que el archivo SP histórico persiste; lo que se planifica es el fin de datos *nuevos* por sensor. Re-verificar en nov-2026 con `data_availability` cuando haya `FIRMS_MAP_KEY`.

## 2. Pregunta 2 · ¿El botón «Sumar VIIRS/MODIS» de la Historia sigue funcionando? ¿Algo deja de funcionar?

**Fuentes (código)**

- Botón y flujo: `web/js/views/casos.js` (botón `#polar`, `loadPolar`, etiqueta «Sumar VIIRS/MODIS (FIRMS)», solo visible en modo técnico `x-tech`); `web/js/api.js` (`loadCasePolar` → `POST /api/cases/{id}/polar`).
- Backend: `backend/routes/community.py` (`load_case_polar` llama `firms.fetch_hotspots` con `case["firms_sources"]` y la ventana del caso; cachea un año en `case-firms:{id}`); `backend/providers/firms.py` (`PRODUCTS`: las fuentes de los casos son todas `kind: "sp"`, `area/csv` por tramos de 5 días).
- Datos: `web/data/cases.json` (`firms_sources` por caso; el más antiguo, Torres del Paine 2011, usa solo `MODIS_SP`; el más nuevo, Penco–Lirquén ene-2026, usa `VIIRS_NOAA20_SP`, `VIIRS_SNPP_SP`, `MODIS_SP`). **Nota:** el encargo mencionaba `web/js/satelite.js`; ese archivo no existe — el código relevante vive en `casos.js`, `api.js` y `util.js`.

**Respuesta**

- **Sí, sigue funcionando para los 6 casos actuales.** Todas sus ventanas (2011-2026) ya están dentro del archivo SP; el retiro de un satélite no borra observaciones pasadas. El botón no usa NRT.
- **Nada deja de funcionar.** No hay dependencia de S-NPP ni de MODIS en la ingesta en vivo: `settings.firms_sources` por defecto es `("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")` y `.env.example` ya documenta el retiro.
- **Efectos reales, todos acotados:**
  - **Casos nuevos posteriores a los retiros:** un caso post-2-nov-2026 no tendrá píxeles S-NPP y uno post-sep-2027 no tendrá MODIS. Si `firms_sources` los conserva, FIRMS devolverá vacío (o la consulta se cuenta igual contra la cuota de transacciones del MAP_KEY).
  - **`/api/explore` histórico:** `public.py` filtra fuentes por `min_date` pero no hay `max_date` en `PRODUCTS`; una ventana histórica totalmente posterior a un retiro seguirá consultando el sensor muerto (consulta vacía, cuota gastada). Menor.
  - **Si alguien edita `FIRMS_SOURCES`:** agregar `VIIRS_SNPP_NRT` o `MODIS_NRT` dejará de traer datos tras las fechas de cese. Ya está advertido en `.env.example` para S-NPP, no para MODIS.
- **Punto de continuidad positivo:** NOAA-20 y NOAA-21 (y JPSS-3/4 futuros) siguen; la nota de NASA confirma que no habrá sucesor con la órbita matinal de Terra, pero para fuego eso solo reduce pasadas.

**Confianza:** alta (lectura directa del código + fuentes primarias).

**Decisión:** ningún cambio urgente. Los `firms_sources` actuales quedan como están.

## 3. Pregunta 3 · ¿El caso 2026 ya tiene VIIRS/MODIS SP? (CONT-07)

**Fuentes**

- FIRMS FAQ (rezago del producto estándar MCD14ML: «2-3 month lag») y página Archive Download (reemplazo NRT→SP «with approximately a 5 month lag», cobertura «hasta el presente» por producto). URLs en §1 (consultadas 19-oct-2026).
- `web/data/cases.json`: caso `penco-lirquen-2026`, ventana 17-ene-2026 → 20-ene-2026, `firms_sources: [VIIRS_NOAA20_SP, VIIRS_SNPP_SP, MODIS_SP]`.

**Respuesta**

- **Muy probablemente sí.** Enero-2026 + 5 meses (peor caso documentado) = jun-2026, y hoy es 19-oct-2026. Las tres fuentes del caso deberían tener SP para esas fechas; S-NPP operaba con normalidad en enero-2026 (su cese es nov-2026).
- **NO VERIFICADO:** sin `FIRMS_MAP_KEY` no pude llamar a `GET /api/data_availability/csv/{key}/all` (el repo ya tiene el cliente: `firms.data_availability`) ni a `area/csv` para una fecha de enero-2026. Tampoco hay proxy local que lo exponga sin clave.

**Confianza:** media-alta por rezago documentado; verificación pendiente.

**Decisión:** cerrar CONT-07 cuando alguien con clave confirme `data_availability` o cargue el botón del caso una vez (el resultado queda cacheado un año). Si por algún motivo el SP de enero-2026 aún faltara, la opción es esperar — NRT ya no cubre 9 meses atrás.

## 4. Cambios recomendados (mínimos, anotados para el siguiente paso — no implementados aquí)

1. **`firms_sources` de los casos actuales: ninguno hace falta.** El archivo histórico persiste y cada caso pide solo lo que su ventana tiene.
2. **Convención para casos nuevos** (documentar donde se agregan casos): caso que *empiece* después del 2-nov-2026 → quitar `VIIRS_SNPP_SP`; después de sep-2027 → quitar `MODIS_SP` y dejar `VIIRS_NOAA20_SP` (+`VIIRS_NOAA21_SP` cuando el producto exista en `PRODUCTS`). Hoy el endpoint no falla si se dejan, solo gasta cuota.
3. **Opcional — `max_date` en `PRODUCTS`** (`backend/providers/firms.py`): `VIIRS_SNPP_*: 2026-11-02`, `MODIS_*: 2027-09-30` (ajustar cuando NASA fije la fecha). Reutiliza el patrón `min_date` ya usado en `public.py:308` para no consultar sensores muertos en `explore` histórico.
4. **Texto de la interfaz: ninguno hace falta ahora.** Si se quiere transparencia futura, el subtítulo técnico del botón podría decir «archivo científico FIRMS» y `load_case_polar` ya devuelve `notices` para avisar si una fuente quedó vacía — basta mostrar esa nota en el callout de Datos.
5. **`.env.example`:** agregar a la nota existente de S-NPP que `MODIS_NRT` deja de entregarse en 2027 (una línea).
6. **CONT-07 (verificación pendiente):** con `FIRMS_MAP_KEY`, correr `firms.data_availability` (o el propio botón del caso 2026) y registrar `max_date` por producto; si enero-2026 figura, marcar CONT-07 como verificado.
7. **Salud de fuentes (opcional):** `.github/scripts/fuentes_salud.py` ya consulta FIRMS por API; un chequeo de `data_availability` que avise cuando `max_date` de `VIIRS_SNPP_SP`/`MODIS_SP` deje de avanzar detectaría el corte real sin adivinar fechas.
