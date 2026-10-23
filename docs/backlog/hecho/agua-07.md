---
id: AGUA-07
repo: brasas
rama: feat/avisos-lluvia-post-incendio
modelo: swe-2-high
riesgo: C
archivos: ninguno
e2e: si
intento: 0
---

# AGUA-07 · Avisos de lluvia y tormenta de la DMC cuando hay cicatriz de incendio (decisión)

## Objetivo
Que, cuando BRASA ya avise de aluvión (Fase 3, `AGUA-01`/`AGUA-05`), los avisos de **lluvia intensa y tormenta** de la DMC también lleguen al lugar afectado.

## Ítem del backlog
`docs/BACKLOG_MAESTRO.md` §9 (AGUA, Fase 3 febrero-abril) y `docs/ALUVIONES.md`: la lluvia sobre suelo quemado es la amenaza; hoy el proveedor la descarta.

## Evidencia
- `backend/providers/dmc.py:6-9` lo dice explícitamente: «Los avisos de lluvia, nieve o tormentas se descartan a propósito: en un día de incendio no cambian qué hacer». `KINDS` (`:29-33`) solo tiene `viento` y `calor`.
- `backend/alerts.py` construye los avisos de la DMC desde esos tipos (`compose_dmc`, `:486` y siguientes); sin tipo nuevo no hay aviso.
- Con la Fase 3 (`backend/scars.py` en curso, `docs/ALUVIONES.md`) la lluvia intensa sobre una cicatriz **sí** cambia qué hacer (alud, deslizamiento), pero solo en los lugares con cicatriz cerca.

## Por qué está acá y no en la cola
Es una decisión de producto y de **textos de emergencia**: hay que elegir el umbral, la redacción y la fuente exacta (DMC/SENAPRED) antes de escribir código, y una recomendación sin fuente oficial clara contradice la regla de oro del proyecto. Además toca el filtro de una fuente oficial (ruido si se muestra de más).

## Qué hay que decidir
1. ¿Se muestran solo en lugares con cicatriz de incendio cerca (recomendado: sí) o en toda la comuna?
2. Umbral y tipo: solo `lluvia` cuando la DMC emita aviso/alerta, o también `tormenta eléctrica` (rayos = nueva ignición)?
3. Texto: ¿qué frase y qué fuente (DMC, SENAPRED, ambos)? Debe decir «no es una alerta oficial de evacuación».
4. ¿Reemplaza o convive con el aviso propio de aluvión de AGUA-01? (Recomendado: conviven; el de BRASA explica, el de la DMC informa.)

## Criterio de listo (cuando se decida)
- `dmc.KINDS` incluye el tipo aprobado y `tests/test_dmc.py` cubre el filtro y el descarte del resto.
- La tarjeta del lugar muestra el aviso solo bajo la condición aprobada, con su fuente y vencimiento.
- `python dev.py check` en verde y `python dev.py e2e` sin errores.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
