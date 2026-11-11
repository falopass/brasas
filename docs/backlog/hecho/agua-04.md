---
id: AGUA-04
repo: brasas
rama: feat/aviso-aluvion
modelo: swe-2-high
riesgo: C
archivos: backend/lluvia.py, backend/alerts.py, backend/services.py, backend/routes/personal.py, backend/routes/climate.py, web/js/views/zona.js, scripts/calibrar_aluvion.py, docs/aluvion-calibracion.md, docs/ALUVIONES.md, tests/
e2e: si
---

# AGUA-04 · Aviso «riesgo de aluvión» por lugar guardado

## Qué se pidió

Con la misma infraestructura de avisos y otra amenaza: cuando el lugar guardado queda
aguas abajo de una cicatriz reciente y se cumple el umbral de lluvia intensa sobre
ladera, avisar a la persona con un texto prudente («aléjate de las quebradas») que
remite a SENAPRED y nunca afirma que un aluvión va a ocurrir.

## Cierre (11-11-2026)

Entregado en cuatro PRs fusionados: [#838](https://github.com/falopass/brasas/pull/838)
(calibración: `docs/aluvion-calibracion.md` y `scripts/calibrar_aluvion.py`),
[#831](https://github.com/falopass/brasas/pull/831) (preferencia `aluvion_alerts` del
lugar, Mi zona y la lista de avisos), [#840](https://github.com/falopass/brasas/pull/840)
(`alerts.evaluate_aluvion`, pasada horaria `services.aluvion_pass` y el cruce
`lluvia.criterio_aviso`) y [#851](https://github.com/falopass/brasas/pull/851) (ida y
vuelta de `aluvion_alerts` por `/api/places`). Después se sumó
[#859](https://github.com/falopass/brasas/pull/859): la pasada horaria carga las
cicatrices de CONAF si aún faltan en `work.db`, para que el aviso no dependa del
orden del ciclo.

La condición «aguas abajo» del pedido se aproxima por cercanía más ladera (cicatriz a
≤ 5 km y pendiente ≥ 8° a escala de cuenca chica): **no hay análisis de cuenca
hidrográfica**, y eso queda como límite declarado del aviso.

El criterio —cicatriz a ≤ 5 km en 365 días, ladera ≥ 8°, ≥ 10 mm en 3 h e isoterma
sobre la cota— salió de la calibración con 180 días de lluvia real y **un solo evento
de control** (Quebrada Honda, 8-oct-2026): está en
[`docs/aluvion-calibracion.md`](../../aluvion-calibracion.md). Límites declarados
allí mismo: un solo aluvión documentado, el aviso es de nivel «aviso» (nunca
«urgente»), un lugar no repite el aviso en 36 h y todo texto lleva la etiqueta de
estimación de BRASA.
