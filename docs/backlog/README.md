# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

63 encargos abiertos.

| ID | Encargo | Estado | Modelo |
|---|---|---|---|
| AGUA-07 | [Avisos de lluvia y tormenta de la DMC cuando hay cicatriz de incendio (decisión)](agua-07.md) | pendiente | swe-2-high |
| AGUA-09 | [La señal de lluvia intensa + isoterma 0 °C (AGUA-03A) ya está calculada y probada, pero no la ve nadie: nin…](agua-09.md) | pendiente | swe-2-high |
| ALR-19 | [Horario de silencio para los avisos que no son urgentes (decisión)](alr-19.md) | pendiente | swe-2-high |
| ALR-20 | [Tope anti-fatiga de avisos por lugar (decisión)](alr-20.md) | pendiente | swe-2-high |
| ALR-23 | [que una familia pueda suscribir el calendario de su lugar y recibir ahí los días en que las condiciones van…](alr-23.md) | pendiente | swe-2-high |
| ALR-26 | [El aviso de foco dice qué hacer, no solo dónde está](alr-26.md) (unificado: ALR-24) | pendiente | swe-2-high |
| ALR-28 | [Que el historial de avisos muestre, arriba de la lista, un resumen por lugar: cuántos avisos te llegaron, c…](alr-28.md) | pendiente | swe-2-high |
| ALR-30 | [`/focos`: el bot dice qué focos hay ahora cerca de tus lugares](alr-30.md) | a medias | swe-2-high |
| AUTO-03 | [Que la vista Calidad deje de ser una tabla de puntos rojos y verdes y pase a responder, en una frase, «qué…](auto-03.md) (unificado: AUTO-07) | pendiente | swe-2-high |
| AUTO-06 | [Que la revisión semanal de fuentes diga qué tan viejo es el dato de cada fuente, no solo si el formato sigu…](auto-06.md) | a medias | swe-2-high |
| AUTO-10 | [El producto no sabe qué endpoints van lentos ni cuántos 5xx produce](auto-10.md) (unificado: AUTO-01, AUTO-14) | a medias | swe-2-high |
| AUTO-11 | [Un botón «Revisar ahora» en #/calidad que prueba lo que el vecino usa](auto-11.md) | pendiente | swe-2-high |
| AUTO-16 | [Que BRASA sepa y diga qué tan viejos son sus propios datos versionados —los JSON de `web/data/` que el veci…](auto-16.md) | a medias | swe-2-high |
| CAL-02 | [Que el calendario `.ics` de una comuna incluya también los avisos oficiales de viento y calor extremo de la…](cal-02.md) | pendiente | swe-2-high |
| DAT-05 | [Que la página de Datos abiertos explique cada conjunto en palabras simples y arme su lista de accesos desde…](dat-05.md) (unificado: DAT-04, DAT-09, DAT-03) | pendiente | swe-2-high |
| DAT-06 | [Que cada gráfico de BRASA se pueda descargar como CSV y muestre su fuente cuando el llamador la entrega, pa…](dat-06.md) | pendiente | swe-2-high |
| DAT-08 | [Catálogo legible por máquina de las capas de datos abiertos](dat-08.md) | pendiente | swe-2-high |
| DAT-10 | [Los datos abiertos explican qué focos quedan fuera de Chile](dat-10.md) | pendiente | swe-2-high |
| DAT-11 | [Que cada conjunto de datos abiertos de BRASA diga, campo por campo, qué significa y en qué unidad viene, ta…](dat-11.md) | pendiente | swe-2-high |
| DET-06 | [Por qué es delicado (va a decisión de Diego)](det-06.md) | a medias | swe-2-high |
| DET-23 | [Motivo de que sea decisión de Diego](det-23.md) | pendiente | swe-2-high |
| DET-45 | [Decisión: umbral o máscara regional para los falsos positivos del norte](det-45.md) | aprobado, falta implementar | swe-2-high |
| FAQ-01 | [Unificado el 23-10-2026](faq-01.md) (unificado: CONT-17, UX-55) | a medias | swe-2-high |
| FOCOS-01 | [Una lista de focos e incendios activos en texto, sin mapa](focos-01.md) | pendiente | swe-2-high |
| FUEGO-08 | [Que la aplicación no diga «datos al día» cuando una fuente lleva horas caída. Hoy la frescura se mide con u…](fuego-08.md) | pendiente | swe-2-high |
| FUEGO-14 | [Que el bloque «Escenario estimado de avance» de la ficha del incidente explique, en palabras que entienda u…](fuego-14.md) | pendiente | swe-2-high |
| FUEGO-17 | [«¿Viene hacia mi casa?»: el viento del escenario contra mis lugares](fuego-17.md) | pendiente | swe-2-high |
| FUEGO-45 | [Decisión: cómo entra la pendiente real en el escenario de propagación](fuego-45.md) (unificado: FUEGO-22, FUEGO-34) | aprobado, falta implementar | swe-2-high |
| MAPA-02 | [que el modo liviano (`/web/lite.html`) abra el enlace compartido de un lugar (`/web/lite.html#/v/<token>`)…](mapa-02.md) | pendiente | swe-2-high |
| MAPA-105 | [Decisión para Diego: las capas base del mapa y sus licencias](mapa-105.md) | aprobado, falta implementar | ninguno |
| MOD-03 | [Que quien modera vea, en la misma tarjeta del reporte, a qué distancia está del incendio más cercano conoci…](mod-03.md) | pendiente | swe-2-high |
| MZ-01 | [Que la tarjeta de cada lugar guardado diga en una línea si el pronóstico de su comuna para los próximos día…](mz-01.md) | pendiente | swe-2-high |
| MZ-03 | [Que cada tarjeta de lugar en «Mi zona» diga en una línea por qué el día es peligroso (calor, humedad del ai…](mz-03.md) | pendiente | swe-2-high |
| MZ-05 | [«Desde tu última visita»: qué cambió en Mi zona](mz-05.md) | pendiente | swe-2-high |
| OFI-04 | [Responder en la aplicación «¿qué dijo la autoridad?» con la alerta oficial de SENAPRED para la comuna o el…](ofi-04.md) | pendiente | swe-2-high |
| OFI-10 | [SINCA (MP2,5 medido): la fuente es pública pero no declara licencia (decisión de Diego)](ofi-10.md) | pendiente | swe-2-high |
| OFI-25 | [OFI-09 · Campamentos del MINVU por comuna (delicado: fuente nueva y licencia por verificar)](ofi-25.md) | pendiente | swe-2-high |
| OFI-33 | [Estación DMC más cercana: hace falta la clave del portal (decisión de Diego)](ofi-33.md) | pendiente | swe-2-high |
| OPS-12 | [Encargo — OPS-12 · Rotar la clave de FIRMS (P0, solo Diego puede)](ops-12.md) | pendiente | swe-2-medium |
| OPS-27 | [Autodiagnóstico de la cara pública: 5xx, páginas lentas y enlaces roto](ops-27.md) | pendiente | swe-2-high |
| OPS-28 | [Que el repositorio se revise solo una vez al día y, cuando `python dev.py check` quede rojo en `main`, abra…](ops-28.md) | pendiente | swe-2-high |
| OPS-29 | [Unificado el 23-10-2026](ops-29.md) (unificado: AUTO-09) | a medias | swe-2-high |
| PESO-05 | [El texto legal sale del JavaScript: margen real en el presupuesto de peso](peso-05.md) (unificado: PERF-07) | pendiente | swe-2-medium |
| PREP-03 | [Mantenimiento de la casa: cuándo se hizo y cuándo toca de nuevo](prep-03.md) | pendiente | swe-2-high |
| QA-72 | [Que ninguna regeneración de los datos que el sitio publica pueda dejar coordenadas fuera de Chile sin que l…](qa-72.md) | pendiente | swe-2-high |
| QUEMA-01 | [«¿Puedo quemar hoy?» (decisión del dueño)](quema-01.md) | pendiente | swe-2-high |
| REP-01 | [Que quien va a reportar humo o fuego vea antes de enviar si un vecino ya reportó lo mismo cerca, y entienda…](rep-01.md) | a medias | swe-2-high |
| RISK-07 | [Viento animado en el mapa (partículas)](risk-07.md) | pendiente | fusion-claude-opus-5-5-high-sidekick-swe-2-high |
| RISK-22 | [Que en Mi zona —la pantalla que un vecino abre todos los días— cada lugar guardado muestre si el pronóstico…](risk-22.md) | pendiente | swe-2-high |
| RISK-23 | [que la ficha de una comuna diga en castellano simple cuánto se ha quemado esta temporada cerca de las casas…](risk-23.md) | a medias | swe-2-high |
| SAT-01 | [Que el enlace «verlo en el satélite» que BRASA ofrece en los casos históricos abra la imagen del día y la h…](sat-01.md) | pendiente | swe-2-high |
| SEO-05 | [Páginas indexables por comuna (decisión de Diego)](seo-05.md) | pendiente | fusion-claude-opus-5-5-high-sidekick-swe-2-high |
| TEMP-03 | [«Tu comuna esta temporada» en Mi zona](temp-03.md) | pendiente | swe-2-high |
| UX-48 | [«Estoy bien»: que la familia sepa que la persona vio el aviso (decisión)](ux-48.md) | pendiente | swe-2-high |
| UX-57 | [«¿Qué hago si…?»: humo y personas sensibles](ux-57.md) | pendiente | swe-2-high |
| UX-59 | [Agregar a «Prepárate» una lista de preparación para quien vive en una parcela o en el campo del Maule —leña…](ux-59.md) | pendiente | swe-2-high |
| UX-61 | [Que la pantalla «¿Qué hago si…?» —la que un vecino abre en plena emergencia— diga cuándo se revisó su conte…](ux-61.md) | a medias | swe-2-high |
| UX-62 | [«Qué hacer hoy»: una acción concreta en la tarjeta del lugar, según el nivel de riesgo](ux-62.md) | pendiente | swe-2-high |
| UX-64 | [Que «Mi zona» diga, en una línea, cómo va la temporada en la comuna del lugar guardado, con CONAF como fuen…](ux-64.md) | pendiente | swe-2-high |
| UX-70 | [Que en el modo liviano (`/lite`, la página para un celular de gama baja con 2G en el secano del Maule) cada…](ux-70.md) | pendiente | swe-2-high |
| UX-72 | [«¿Qué hago si…?» con enlace propio por situación y botón para reenviarla](ux-72.md) | pendiente | swe-2-high |
| VEC-01 | [El familiar que vigila no sabe si la semana viene peor que la pasada](vec-01.md) (unificado: UX-56, UX-63) | a medias | swe-2-high |
| VEC-02 | [Que en «Mi zona» cada lugar guardado muestre, con su fuente, cómo le fue a su comuna en la temporada pasada…](vec-02.md) | a medias | swe-2-high |
