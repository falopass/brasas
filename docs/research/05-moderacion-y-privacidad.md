# Moderación y privacidad de los reportes ciudadanos

Fecha: 18 de octubre de 2026. Carril de investigación. Lo que implique código va aquí como
**propuesta**, con su ticket para la sesión de backend; este documento no cambia el producto.

> Esto es investigación, **no asesoría legal**. Las fechas y obligaciones se citan con su fuente y
> lo que no se pudo leer en el texto oficial queda marcado al final.

## Resumen ejecutivo

1. **La moderación de reportes ciudadanos es un flujo, no un botón.** Ushahidi —la plataforma de
   referencia en crisis— verifica contra tres cosas (socios en terreno, otros reportes y medios),
   marca cada reporte como *sin verificar / verificado / falso* y deja escrito que **es mejor
   dejarlo en «sin verificar» que publicarlo con duda**. Ese criterio debería ser el de BRASA.
2. **Hay una fecha legal encima**: la Ley 21.719 (nueva ley de datos personales de Chile) empieza a
   regir el **1 de diciembre de 2026**, seis semanas después de este documento. BRASA guarda
   coordenadas, fotos y un identificador de dispositivo de personas: cae de lleno en su ámbito.
3. **El hueco operativo de BRASA no es moderar, es el tiempo**: hoy la cola no caduca, los reportes
   no se podan y el autor nunca sabe qué pasó con su aviso. Las tres cosas están resueltas en el
   backend propuesto en el PR #7 (caducidad a 6 h, lote, `/api/reports/mine`, duplicados).

## 1. Cómo moderan otros

| Plataforma | Qué hace | Qué se toma para BRASA |
|---|---|---|
| **Ushahidi / Uchaguzi** ([guía de verificación](https://docs.ushahidi.com/uchaguzi-support/digital-response-teams/verification.md)) | Equipo dedicado; cola de «Unverified Posts»; verifica triangulando con socios, otros reportes y medios; categorías *Unverified / Verified / False*; comprueba duplicados y autenticidad de la foto; deja notas para el equipo; «mejor dejarlo sin verificar que publicarlo con duda». | Categorías explícitas (no un booleano), chequeo de duplicados y nota del moderador visible para el autor. |
| **eBird** ([proceso de revisión](https://ebird.freshdesk.com/es/support/solutions/articles/48000795278/)) | Revisores voluntarios regionales evalúan lo inusual; filtros de calidad automáticos; los casos dudosos quedan marcados, no se borran. | Moderador humano con criterio local + regla automática para lo evidente (duplicado, caducado). |
| **Smoke Sense (EPA)** ([artículo](https://europepmc.org/article/MED/32159029)) | Reportes estructurados de ciudadanos sobre humo; se devuelve contexto y el reporte sirve al propio participante. | El reporte debe devolver algo a quien lo hace (estado), o la gente deja de reportar. |

## 2. Qué obliga la ley chilena y desde cuándo

| Norma | Estado | Qué importa para BRASA |
|---|---|---|
| **Ley 19.628** (1999) | Vigente hoy | Regula el tratamiento de datos personales; base legal y derechos básicos. |
| **Ley 21.719** | Publicada en el Diario Oficial el **13 de diciembre de 2024**; **entra en vigencia el 1 de diciembre de 2026** ([DOE, feb-2026](https://actualidadjuridica.doe.cl/emilio-onate-sobre-ley-de-datos-personales-mas-que-sancionar-el-principal-desafio-de-la-nueva-institucionalidad-sera-promover-una-cultura-de-respeto-a-la-privacidad/)) | Crea la **Agencia de Protección de Datos Personales**, consagra derechos (acceso, rectificación, **supresión**, oposición) y un régimen sancionatorio progresivo ([Academia Judicial](https://academiajudicial.cl/wp-content/uploads/2026/05/El-Nuevo-Sistema-de-Proteccion-de-los-Datos-Personales-1.pdf)). Modelo inspirado en el RGPD. |

Consecuencias concretas para BRASA, sin tecnicismos:

- **Una foto de humo puede contener personas identificables** (una casa, un rostro, una patente). Si
  BRASA la publica, está publicando datos personales de terceros que no dieron su consentimiento.
- **La coordenada exacta de un reporte puede identificar una vivienda.** BRASA ya redondea a ~100 m
  en la API pública; la cola de moderación y el historial del autor sí ven el punto exacto, y eso
  está bien mientras no se publique.
- **El identificador de dispositivo es un dato personal** en la medida en que permita identificar a
  alguien. BRASA no pide nombre ni correo, lo que reduce el riesgo, pero el token sigue siendo
  información vinculada a una persona.
- **Derecho de supresión**: si alguien pide borrar su reporte, hoy no hay mecanismo. Y no hay poda:
  los reportes se guardan para siempre.

## 3. Qué hace BRASA hoy (hechos del repositorio)

| Hecho | Dónde |
|---|---|
| La foto se re-codifica: sin EXIF, sin GPS del archivo, máximo 1600 px y 8 MB. | `backend/reports.py` |
| El reporte nace `no_verificado`; nada se publica sin revisión humana. | `backend/routes/community.py` |
| La foto solo se sirve con `ADMIN_TOKEN` mientras no esté verificada (403 sin token). | `community.py`, `report_photo` |
| La API pública redondea a 3 decimales (~100 m) y no expone al autor. | `_public` |
| La ingesta usa el token de dispositivo; no hay cuentas ni correos. | `backend/routes/common.py` |
| Hay tope de 6 reportes por hora por IP (en memoria del proceso, no se guarda la IP). | `limiter` |
| **No hay caducidad, ni poda de reportes, ni forma de que el autor consulte su reporte.** | — (hueco) |

## 4. Propuestas

### P0 — antes del 1 de diciembre de 2026 (lo que la ley aprieta)

1. **Política de retención de reportes**: podar a 90 días los `descartado` y a 1 año los
   `verificado`, con el plazo escrito en la interfaz. *Ticket backend: `reports` + poda en el ciclo.*
2. **Derecho de supresión mínimo**: `DELETE /api/reports/mine/{id}` para reportes propios en estado
   `no_verificado` (los publicados se despublican y se anonimiza el autor). *Ticket backend.*
3. **No publicar fotos con personas identificables**: regla de moderación escrita en `admin.html`
   («si se ve una persona, una patente o el interior de una casa, se descarta o se recorta»).
   *Ticket web + guía de moderación en docs.*
4. **Aviso de privacidad junto al formulario**: qué se guarda (foto, punto, token), para qué, cuánto
   tiempo y cómo pedir el borrado. *Ticket web (texto) + este documento como base.*

### P1 — que la cola sea ágil (ya propuesto como código)

5. **Caducidad a las 6 h**: un reporte de humo sin revisar deja de servir; pasa a `descartado` con
   el motivo, no se borra. **Implementado en el PR #7**, pendiente de merge.
6. **Moderación en lote** (hasta 200 de una vez): el cuello de botella es humano. **PR #7**.
7. **El autor sabe qué pasó**: `GET /api/reports/mine` con el estado en palabras y la nota del
   moderador. **PR #7**; necesita una línea en el carril de web (`auth: true` al crear el reporte).
8. **Duplicados**: mismo tipo, ≤1,5 km y ≤3 h devuelven el reporte que ya está en revisión. **PR #7**.

### P2 — cuando haya volumen

9. **Corroboración en vez de un solo testigo**: dos reportes independientes del mismo punto en la
   misma ventana suben la confianza; uno solo nunca se publica como verificado (práctica Ushahidi).
10. **Nivel de confianza del autor** (historial de reportes aceptados), no para ocultar reportes
    nuevos, sino para priorizar la cola.
11. **Verificación de imagen** (detección de fotos reutilizadas) antes de publicar. Requiere
    dependencia nueva: decisión de la persona dueña.

## 5. Lo que no hay que hacer

- **Publicar un reporte dudoso para «no perder» información.** Ushahidi lo dice al revés: ante la
  duda, sin verificar. Un falso positivo en un incendio cuesta confianza y puede costar vidas.
- **Contar reportes como incendios.** Un reporte ciudadano es una señal; el estado «confirmado»
  sigue siendo solo de CONAF.
- **Borrar en vez de caducar.** Caducar deja el rastro de que llegó y no se revisó; borrar
  destruye la evidencia de que el sistema falló.
- **Prometer anonimato absoluto.** Se puede decir «no pedimos nombre ni correo»; no «es anónimo»,
  porque el token y la foto pueden identificar.
- **Guardar la IP.** Hoy el limitador es en memoria y no la persiste: mantenerlo así es una ventaja
  de privacidad, no una carencia.

## 6. Fuentes

| Fuente | Qué se tomó |
|---|---|
| [Ushahidi · guía de verificación](https://docs.ushahidi.com/uchaguzi-support/digital-response-teams/verification.md) | Flujo de tres categorías, triangulación, duplicados, autenticidad de foto y el criterio «en duda, sin verificar». |
| [eBird · proceso de revisión](https://ebird.freshdesk.com/es/support/solutions/articles/48000795278/) | Revisores voluntarios regionales, filtros automáticos, lo dudoso se marca y no se borra. |
| [Smoke Sense (EPA), Europe PMC](https://europepmc.org/article/MED/32159029) | Reporte ciudadano estructurado y con retorno para quien reporta. |
| [DOE · entrevista sobre la nueva ley (feb-2026)](https://actualidadjuridica.doe.cl/emilio-onate-sobre-ley-de-datos-personales-mas-que-sancionar-el-principal-desafio-de-la-nueva-institucionalidad-sera-promover-una-cultura-de-respeto-a-la-privacidad/) | Entrada en vigencia el 1 de diciembre de 2026 y foco en cultura de privacidad. |
| [DOE · «cambio copernicano» (jul-2025)](https://actualidadjuridica.doe.cl/un-desafio-de-un-cambio-cultural-la-nueva-ley-de-proteccion-de-datos-personales-marca-un-cambio-copernicano-en-chile/) | Vacancia legal de dos años hasta diciembre de 2026; régimen sancionatorio. |
| [Academia Judicial · El nuevo sistema de protección de datos](https://academiajudicial.cl/wp-content/uploads/2026/05/El-Nuevo-Sistema-de-Proteccion-de-los-Datos-Personales-1.pdf) | Agencia, derechos del titular, modelo RGPD. |
| [Tesis U. de Chile · plataformas de entretención](https://repositorio.uchile.cl/xmlui/bitstream/handle/2250/204965/Normativa-aplicable-al-tratamiento-de-datos-personales-por-plataformas-de-entretencion-en-linea-una-revision-de-los-estandares-de-proteccion.pdf?sequence=1&isAllowed=y) | Fecha de publicación en el Diario Oficial: 13 de diciembre de 2024. |

## 7. Lo que no se pudo verificar

1. **El texto oficial en LeyChile** (`bcn.cl`) no se pudo leer: la página se arma con JavaScript y
   devolvió un documento vacío. La fecha de vigencia (1-dic-2026) y la publicación (13-dic-2024)
   vienen de fuentes secundarias concordantes; **hay que confirmarlas en el texto oficial** antes de
   citarlas en la interfaz o en una política de privacidad.
2. **Si la foto de un reporte constituye dato personal por sí sola** depende del contenido; no se
   encontró una guía de la Agencia (que aún no está operando) sobre imágenes de desastres.
3. **Plazos concretos de conservación** que exija la ley: no se verificaron; la propuesta de 90 días
   / 1 año es de BRASA, no una obligación legal.
4. **Las sanciones** se citan por la prensa jurídica; no se leyeron los montos en el articulado.
