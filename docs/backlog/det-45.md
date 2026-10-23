---
id: DET-45
repo: brasas
rama: docs/decision-umbral-norte
modelo: swe-2-high
riesgo: C
archivos: ninguno (decisión)
e2e: no
intento: 0
ronda_review: 0
---

# Decisión: umbral o máscara regional para los falsos positivos del norte

**Objetivo.** Decidir si BRASA aplica un umbral o una máscara regional a las detecciones del norte grande, y con qué regla, antes de tocar la ingesta.

**Ítem del backlog / foco de Diego.** DET-08 y foco 1: «los focos y los incendios deben corresponder a Chile real». Es el último cabo suelto de realismo que no depende de recortar por polígono (eso ya está en varias ramas): acá el problema no es el país, es el desierto.

**Qué se sabe.** El medidor existe: `scripts/local/medir_falsos_positivos.py` cuenta por región y franja horaria cuántas detecciones terminaron en «anomalia» frente a las que llegaron a un estado con evidencia, y advierte en su docstring que «anomalia» no equivale a falso positivo. La investigación está en `docs/investigacion/INV-25-falsos-positivos-norte.md` y `scripts/validar_deteccion.py` resume por región los incidentes abiertos sin un incendio de CONAF cerca. Lo que falta es la decisión: subir el umbral en Arica–Atacama, aplicar una máscara de calor permanente (DET-05/DET-06, que además espera revisión manual), o dejarlo como está y explicarlo mejor en la página de calidad.

**Por qué es delicado.** Un umbral más alto en el norte también esconde el incendio real de pastizal en un valle: sube el silencio justo donde hay menos gente mirando. Una máscara basada en un catálogo incompleto de plantas solares y minería puede tapar un incendio verdadero durante horas. Y lo que se elija tiene que poder explicarse en la ficha y en `#/calidad` sin jerga.

**Qué necesita de Diego.** (1) ¿Se aplica una regla regional o se deja solo la explicación? (2) Si se aplica, ¿umbral por región, máscara de fuentes fijas o las dos? (3) ¿Acepta medir una temporada completa antes de fijar el número, o quiere un valor provisional con su fecha de revisión? (4) ¿Quién firma la nota metodológica?

Con la respuesta se escribe el brief: probablemente `backend/providers/goes.py` + `backend/incidents.py` + la página de calidad, con la medición como criterio de término.

Decisiones así las toma Diego, no la fábrica.


DECISION (21-10, Diego delegó): Aprobado: mascara regional en vez de umbral unico para falsos positivos; se calibra con Fusion.
