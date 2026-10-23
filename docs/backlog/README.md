# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).

81 encargos abiertos.

| ID | Encargo | Estado | Modelo |
|---|---|---|---|
| AGUA-07 | [Avisos de lluvia y tormenta de la DMC cuando hay cicatriz de incendio (decisión)](agua-07.md) | pendiente | swe-2-high |
| AGUA-09 | [La señal de **lluvia intensa + isoterma 0 °C** (AGUA-03A) ya está calculada y probada, pero **no la ve nadi…](agua-09.md) | pendiente | swe-2-high |
| ALR-19 | [Horario de silencio para los avisos que no son urgentes (decisión)](alr-19.md) | pendiente | swe-2-high |
| ALR-20 | [Tope anti-fatiga de avisos por lugar (decisión)](alr-20.md) | pendiente | swe-2-high |
| ALR-23 | [que una familia pueda suscribir el calendario de su lugar y recibir ahí los días en que las condiciones van…](alr-23.md) | pendiente | swe-2-high |
| ALR-24 | [El aviso dice hace cuánto se detectó el foco y cuál es el paso siguiente](alr-24.md) | pendiente | swe-2-high |
| ALR-26 | [El aviso de foco dice qué hacer, no solo dónde está](alr-26.md) | pendiente | swe-2-high |
| ALR-28 | [Que el historial de avisos muestre, arriba de la lista, un resumen **por lugar**: cuántos avisos te llegaro…](alr-28.md) | pendiente | swe-2-high |
| ALR-30 | [`/focos`: el bot dice qué focos hay ahora cerca de tus lugares](alr-30.md) | a medias | swe-2-high |
| AUTO-01 | [Que BRASA **cuente y publique sus propias fallas de servicio** —respuestas 5xx y respuestas lentas— en un e…](auto-01.md) | a medias | swe-2-high |
| AUTO-03 | [Que la vista **Calidad** deje de ser una tabla de puntos rojos y verdes y pase a responder, en una frase, «…](auto-03.md) | pendiente | swe-2-high |
| AUTO-06 | [Que la revisión semanal de fuentes diga **qué tan viejo es el dato** de cada fuente, no solo si el formato…](auto-06.md) | a medias | swe-2-high |
| AUTO-07 | [Que la vista **Calidad** distinga «esta fuente está fallando ahora» de «esta fuente falló y BRASA se recupe…](auto-07.md) | pendiente | swe-2-high |
| AUTO-09 | [El panel de administración suma una pestaña «Salud» con qué está fallando y qué hacer](auto-09.md) | a medias | swe-2-high |
| AUTO-10 | [El producto no sabe qué endpoints van lentos ni cuántos 5xx produce](auto-10.md) | a medias | swe-2-high |
| AUTO-11 | [Un botón «Revisar ahora» en #/calidad que prueba lo que el vecino usa](auto-11.md) | pendiente | swe-2-high |
| AUTO-14 | [Que BRASA diga sola qué está fallando y qué hacer: un `GET /api/diagnostico` con el veredicto por fuente y…](auto-14.md) | a medias | swe-2-high |
| AUTO-16 | [Que BRASA sepa y diga **qué tan viejos son sus propios datos versionados** —los JSON de `web/data/` que el…](auto-16.md) | a medias | swe-2-high |
| CAL-02 | [Que el calendario `.ics` de una comuna incluya también los avisos oficiales de viento y calor extremo de la…](cal-02.md) | pendiente | swe-2-high |
| CONT-17 | [Que la página de preguntas frecuentes (`/web/preguntas.html`) responda las dudas que un vecino del Maule ti…](cont-17.md) | pendiente | swe-2-high |
| DAT-03 | [Datos abiertos: recetas listas para copiar](dat-03.md) | pendiente | swe-2-medium |
| DAT-04 | [Datos abiertos explicados en palabras simples](dat-04.md) | pendiente | swe-2-high |
| DAT-05 | [Que la página de **Datos abiertos** explique cada conjunto en palabras simples y arme su lista de accesos *…](dat-05.md) | pendiente | swe-2-high |
| DAT-06 | [Que cada gráfico de BRASA se pueda descargar como CSV y muestre su fuente cuando el llamador la entrega, pa…](dat-06.md) | pendiente | swe-2-high |
| DAT-08 | [Catálogo legible por máquina de las capas de datos abiertos](dat-08.md) | pendiente | swe-2-high |
| DAT-09 | [Que la página de datos abiertos sirva para usarlos: un solo camino por conjunto y un ejemplo de llamada que…](dat-09.md) | pendiente | swe-2-high |
| DAT-10 | [Los datos abiertos explican qué focos quedan fuera de Chile](dat-10.md) | pendiente | swe-2-high |
| DAT-11 | [Que cada conjunto de datos abiertos de BRASA diga, campo por campo, qué significa y en qué unidad viene, ta…](dat-11.md) | pendiente | swe-2-high |
| DET-06 | [Por qué es delicado (va a decisión de Diego)](det-06.md) | a medias | swe-2-high |
| DET-23 | [Motivo de que sea decisión de Diego](det-23.md) | pendiente | swe-2-high |
| DET-45 | [Decisión: umbral o máscara regional para los falsos positivos del norte](det-45.md) | aprobado, falta implementar | swe-2-high |
| DIETA-01 | [Devolver `main` a verde: el arranque pesa hoy 252,2 KB gzip contra un presupuesto de 252 KB y por eso `pyth…](dieta-01.md) | pendiente | swe-2-high |
| FAQ-01 | [Que las preguntas frecuentes de BRASA sean una página de verdad: enlazada desde la aplicación, con la marca…](faq-01.md) | a medias | swe-2-high |
| FOCOS-01 | [Una lista de focos e incendios activos en texto, sin mapa](focos-01.md) | pendiente | swe-2-high |
| FUEGO-08 | [Que la aplicación no diga «datos al día» cuando una fuente lleva horas caída. Hoy la frescura se mide con u…](fuego-08.md) | pendiente | swe-2-high |
| FUEGO-14 | [Que el bloque «Escenario estimado de avance» de la ficha del incidente explique, en palabras que entienda u…](fuego-14.md) | pendiente | swe-2-high |
| FUEGO-17 | [«¿Viene hacia mi casa?»: el viento del escenario contra mis lugares](fuego-17.md) | pendiente | swe-2-high |
| FUEGO-22 | [La pendiente del terreno en el escenario de propagación (decisión: fuente, licencia y costo)](fuego-22.md) | aprobado, falta implementar | swe-2-high |
| FUEGO-34 | [Decisión para Diego: la pendiente del terreno en el escenario de propagación](fuego-34.md) | aprobado, falta implementar | ninguno |
| FUEGO-45 | [Decisión: cómo entra la pendiente real en el escenario de propagación](fuego-45.md) | aprobado, falta implementar | swe-2-high |
| MAPA-02 | [que el modo liviano (`/web/lite.html`) abra el enlace compartido de un lugar (`/web/lite.html#/v/<token>`)…](mapa-02.md) | pendiente | swe-2-high |
| MAPA-105 | [Decisión para Diego: las capas base del mapa y sus licencias](mapa-105.md) | aprobado, falta implementar | ninguno |
| MOD-03 | [Que quien modera vea, en la misma tarjeta del reporte, a qué distancia está del incendio más cercano conoci…](mod-03.md) | pendiente | swe-2-high |
| MZ-01 | [Que la tarjeta de cada lugar guardado diga en una línea si el pronóstico de su comuna para los próximos día…](mz-01.md) | pendiente | swe-2-high |
| MZ-03 | [Que cada tarjeta de lugar en «Mi zona» diga en una línea **por qué** el día es peligroso (calor, humedad de…](mz-03.md) | pendiente | swe-2-high |
| MZ-05 | [«Desde tu última visita»: qué cambió en Mi zona](mz-05.md) | pendiente | swe-2-high |
| OFI-04 | [Responder en la aplicación «¿qué dijo la autoridad?» con la alerta **oficial** de SENAPRED para la comuna o…](ofi-04.md) | pendiente | swe-2-high |
| OFI-10 | [SINCA (MP2,5 medido): la fuente es pública pero no declara licencia (decisión de Diego)](ofi-10.md) | pendiente | swe-2-high |
| OFI-25 | [OFI-09 · Campamentos del MINVU por comuna (delicado: fuente nueva y licencia por verificar)](ofi-25.md) | pendiente | swe-2-high |
| OFI-33 | [Estación DMC más cercana: hace falta la clave del portal (decisión de Diego)](ofi-33.md) | pendiente | swe-2-high |
| OPS-12 | [Encargo — OPS-12 · Rotar la clave de FIRMS (P0, solo Diego puede)](ops-12.md) | pendiente | swe-2-medium |
| OPS-27 | [Autodiagnóstico de la cara pública: 5xx, páginas lentas y enlaces roto](ops-27.md) | pendiente | swe-2-high |
| OPS-28 | [Que el repositorio se revise solo una vez al día y, cuando `python dev.py check` quede rojo en `main`, abra…](ops-28.md) | pendiente | swe-2-high |
| OPS-29 | [Que el panel de administración tenga una pestaña «Salud» que lea `/api/status` y muestre, en una sola panta…](ops-29.md) | a medias | swe-2-high |
| PERF-07 | [Devolver `main` a verde y dejarle holgura real al presupuesto del arranque: hoy el arranque pesa **252,2 KB…](perf-07.md) | pendiente | swe-2-high |
| PESO-03 | [Sacar del arranque el texto de Prepárate (y devolver `dev.py check` a verde)](peso-03.md) | pendiente | swe-2-high |
| PESO-04 | [Devolver `main` a verde bajando el peso del arranque por debajo de 252 KB **sin tocar el umbral**: sacar de…](peso-04.md) | pendiente | swe-2-high |
| PESO-05 | [El texto legal sale del JavaScript: margen real en el presupuesto de peso](peso-05.md) | pendiente | swe-2-medium |
| PREP-03 | [Mantenimiento de la casa: cuándo se hizo y cuándo toca de nuevo](prep-03.md) | pendiente | swe-2-high |
| QA-72 | [Que ninguna regeneración de los datos que el sitio publica pueda dejar coordenadas fuera de Chile sin que l…](qa-72.md) | pendiente | swe-2-high |
| QUEMA-01 | [«¿Puedo quemar hoy?» (decisión del dueño)](quema-01.md) | pendiente | swe-2-high |
| REP-01 | [Que quien va a reportar humo o fuego vea **antes de enviar** si un vecino ya reportó lo mismo cerca, y enti…](rep-01.md) | a medias | swe-2-high |
| RISK-07 | [Viento animado en el mapa (partículas)](risk-07.md) | pendiente | fusion-claude-opus-5-5-high-sidekick-swe-2-high |
| RISK-22 | [Que en **Mi zona** —la pantalla que un vecino abre todos los días— cada lugar guardado muestre si el pronós…](risk-22.md) | pendiente | swe-2-high |
| RISK-23 | [que la ficha de una comuna diga en castellano simple cuánto se ha quemado esta temporada cerca de las casas…](risk-23.md) | a medias | swe-2-high |
| SAT-01 | [Que el enlace «verlo en el satélite» que BRASA ofrece en los casos históricos abra la **imagen del día y la…](sat-01.md) | pendiente | swe-2-high |
| SEO-05 | [Páginas indexables por comuna (decisión de Diego)](seo-05.md) | pendiente | fusion-claude-opus-5-5-high-sidekick-swe-2-high |
| TEMP-03 | [«Tu comuna esta temporada» en Mi zona](temp-03.md) | pendiente | swe-2-high |
| UX-48 | [«Estoy bien»: que la familia sepa que la persona vio el aviso (decisión)](ux-48.md) | pendiente | swe-2-high |
| UX-55 | [Preguntas frecuentes: cómo leer lo que BRASA muestra (y que se llegue a ellas)](ux-55.md) | a medias | swe-2-high |
| UX-56 | [Modo vecino: «cómo viene la semana», en una frase](ux-56.md) | pendiente | swe-2-high |
| UX-57 | [«¿Qué hago si…?»: humo y personas sensibles](ux-57.md) | pendiente | swe-2-high |
| UX-59 | [Agregar a «Prepárate» una lista de preparación para quien vive en una parcela o en el campo del Maule —leña…](ux-59.md) | pendiente | swe-2-high |
| UX-61 | [Que la pantalla **«¿Qué hago si…?»** —la que un vecino abre en plena emergencia— diga **cuándo se revisó su…](ux-61.md) | a medias | swe-2-high |
| UX-62 | [«Qué hacer hoy»: una acción concreta en la tarjeta del lugar, según el nivel de riesgo](ux-62.md) | pendiente | swe-2-high |
| UX-63 | [El enlace compartido explica el pronóstico de la semana, no solo lo pinta](ux-63.md) | pendiente | swe-2-high |
| UX-64 | [Que «Mi zona» diga, en una línea, cómo va la temporada en la comuna del lugar guardado, con CONAF como fuen…](ux-64.md) | pendiente | swe-2-high |
| UX-70 | [Que en el modo liviano (`/lite`, la página para un celular de gama baja con 2G en el secano del Maule) cada…](ux-70.md) | pendiente | swe-2-high |
| UX-72 | [«¿Qué hago si…?» con enlace propio por situación y botón para reenviarla](ux-72.md) | pendiente | swe-2-high |
| VEC-01 | [El familiar que vigila no sabe si la semana viene peor que la pasada](vec-01.md) | a medias | swe-2-high |
| VEC-02 | [Que en «Mi zona» cada lugar guardado muestre, con su fuente, **cómo le fue a su comuna en la temporada pasa…](vec-02.md) | a medias | swe-2-high |
