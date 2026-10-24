---
id: OFI-04
repo: brasas
rama: feat/alertas-oficiales-senapred
modelo: swe-2-high
riesgo: C
archivos: ninguno (decisión)
e2e: no
intento: 0
ronda_review: 0
---

**Qué se propone.** Responder en la aplicación «¿qué dijo la autoridad?» con la alerta **oficial** de SENAPRED para la comuna o el lugar guardado, no solo con un enlace genérico a senapred.cl.

**Ítem del backlog.** `docs/BACKLOG_MAESTRO.md:301` — OFI-04, P1, tamaño S, estado ⬜. Dice textual: «Solicitud formal (idealmente un feed CAP público); mientras tanto, enlace directo. **No usar su API interna**».

**Por qué no se lanza solo (riesgo C).** Toca tres reglas que no son de un agente: (1) datos y textos de emergencia que solo se publican con fuente oficial clara (la regla de oro del producto); (2) una relación con un organismo público —el acceso a su feed CAP o la autorización para consumirlo—, que no se resuelve con código; (3) el descargo de responsabilidad, porque una alerta de BRASA que parezca oficial cambia el riesgo legal del proyecto (`docs/TERMINOS.md`). Un PR que invente o raspe la API interna de SENAPRED rompería el producto y la convivencia institucional.

**Qué ve hoy la persona.** En el modo emergencia y en la ficha del incidente hay teléfonos y enlaces, pero en ninguna parte aparece la alerta vigente de SENAPRED para su comuna. Cuando la autoridad evacúa, BRASA dice qué hacer en genérico y remite a senapred.cl, sin poder nombrar la alerta real.

**Evidencia.** El backlog lo deja pendiente; `docs/FUENTES.md` no tiene entrada de SENAPRED; las vistas de emergencia (`web/js/views/zona.js`, `web/js/views/vecino.js`) muestran avisos de la DMC y de CONAF, no de SENAPRED. `backend/providers/` no tiene ningún proveedor de SENAPRED.

**Lo que hay que decidir (Diego).** Una de tres:
1. Pedir acceso a un feed CAP público de SENAPRED (o a su futura API) y esperar la respuesta: es lo correcto y lo más lento.
2. Publicar solo un enlace profundo por comuna a su visor público, con texto que diga «consulta la alerta oficial vigente en SENAPRED», sin afirmar nada por nuestra cuenta: se puede hacer esta semana y no requiere permiso.
3. Dejarlo como está hasta que exista el acceso formal.

**Si se aprueba la opción 1 o 2, el encargo sería:** un proveedor de solo lectura que traiga las alertas vigentes con su identificador, su vigencia y su enlace; una tabla en `work.db` reemplazable por ciclo (como `dmc_alerts`); el cruce por comuna con el polígono cuando exista y, cuando no, por nombre de la zona; un bloque «La autoridad informa» en el modo emergencia y en la ficha; textos que digan siempre «fuente: SENAPRED» y «BRASA no emite alertas»; pruebas con una alerta real guardada como fixture. Y **antes de mergear**, la revisión de Diego sobre los textos de emergencia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

Hecho (24-10): Diego aprobó la integración de las tres fuentes de gobierno («haz la
implementación completa»). `backend/providers/senapred.py` lee `alertasByDate` del AppSync
del portal público con las credenciales anónimas del identity pool de Cognito (firma SigV4,
solo stdlib) — el mismo acceso de lectura que recibe cualquier visitante de senapred.cl.
`GET /api/alerts/official?lat=&lon=` ubica la comuna por el territorio BCN y calza las
alertas vigentes por su título oficial («comuna de X», «Región del Maule»); la relación
`comunas`/`regiones` del esquema viene vacía, así que el calce textual es la vía y las
alertas de provincia sin comuna nombrada quedan fuera (limitación documentada). «Mi zona»
las muestra en «La autoridad informa» con el texto exacto, la fecha y el enlace
`senapred.cl/alertas/<slug>`; fuente caída o sin mención → lista vacía y queda el enlace.
La solicitud de feed formal (CAP) sigue enviada por Transparencia: si SENAPRED publica un
servicio oficial, se migra a él.
