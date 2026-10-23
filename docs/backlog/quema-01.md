---
id: QUEMA-01
repo: brasas
rama: feat/puedo-quemar-hoy
modelo: swe-2-high
riesgo: C
archivos: web/js/views/preparate.js, backend/routes/climate.py, tests/test_quemas.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# QUEMA-01 · «¿Puedo quemar hoy?» (decisión del dueño)

## Qué propone

Un bloque en `#/preparate` que responda la pregunta más frecuente de un vecino rural del Maule en octubre: si hoy es día de quemar rastrojos o no. Con **dos estados y ninguno más**: «Hoy no quemes» cuando el riesgo 30-30-30 de la comuna es alto/extremo o CONAF pronosticó Botón Rojo, y «No hay condiciones seguras conocidas; la autorización la da CONAF o el municipio» en el resto. Nunca un «sí, puedes quemar».

## Por qué es decisión y no se lanza

1. **Responsabilidad**: la autorización de una quema es de CONAF/municipio y depende de la resolución de quemas; si la app dijera «puedes quemar» y el fuego se sale, BRASA queda expuesta. El texto tiene que ser inequívoco y el dueño debe aprobarlo.
2. **Dato oficial incompleto**: el listado de quemas autorizadas no está como dato abierto (INV-04 es solo documentación) y el aviso de CONAF no tiene autorización de uso (OFI-03). Sin esa fuente, la app solo puede **desaconsejar**, no habilitar.
3. **Texto de emergencia**: es exactamente el caso que el foco manda a `decision/` («textos de emergencia sin una fuente oficial clara»).

## Si Diego lo aprueba, qué se haría

`web/js/views/preparate.js` (bloque nuevo, con las fuentes ya citadas en `SRC`), un dato de solo lectura en `backend/routes/climate.py` (el nivel y el Botón Rojo del día por comuna, que ya existen en `risk_daily`/`boton_rojo`), `tests/test_quemas.py` con los dos estados y un caso que compruebe que **nunca** aparece «puedes quemar» ni «autorizado», y `CHANGELOG.md`.

## Criterio de listo (si se aprueba)

`python dev.py test -k quemas` verde con: riesgo alto → «Hoy no quemes» + enlace a CONAF; riesgo bajo → «No hay condiciones seguras conocidas…»; una prueba que recorra todas las cadenas del bloque y falle si contiene «puedes quemar», «está permitido» o «autorizado». E2E en navegador por ser vista.

## Decisión pedida

¿Se implementa con esos dos estados, se deja solo como párrafo informativo enlazado a CONAF, o no se hace?


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
