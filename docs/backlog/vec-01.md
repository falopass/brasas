---
id: VEC-01
repo: brasas
rama: feat/enlace-compartido-comparador
modelo: swe-2-high
riesgo: B
archivos: backend/routes/personal.py, web/js/views/vecino.js, tests/test_shared_trend.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# VEC-01 · El familiar que vigila no sabe si la semana viene peor que la pasada

## Objetivo
Que el enlace compartido de un lugar diga, en una frase y en lenguaje de vecino, si el pronóstico de esta semana viene más alto o más bajo que el que BRASA publicaba hace siete días, aclarando que es un pronóstico y no un incendio.

## Ítem del backlog
Foco del dueño (4) features: «comparación con la semana pasada» para entender el riesgo de hoy. El comparador existe en el backend (`backend/trend.py`, `risk_snapshot`), pero no llega a la vista que usan los hijos que vigilan la casa de sus padres.

## Qué pasa hoy (verificado en main 3ceae01)
- `backend/routes/public.py:568-576` ya arma el comparador con `trend_mod.row()` y `trend_mod.summarize()` sobre `work.risk_snapshot`, pero sólo para `GET /api/trend`.
- `backend/routes/personal.py:233-278` (`build_summary`, que alimenta `/api/shared/{token}`) devuelve `risk_days` con los siete días y el Botón Rojo, y nada sobre cómo cambió la expectativa.
- `web/js/views/vecino.js:130` pinta `dayStrip(data.risk_days)` sin decir si la semana empeoró; `speechFor()` (`:82-86`) tampoco lo dice. El vecino ve «alto» hoy sin saber si es normal o si viene subiendo.

## Solución pedida
1. `personal.py`: en `build_summary`, agregar `trend` para la comuna del lugar con la misma consulta de `public.py:568-571` (últimos tres `snapshot_date`) y `trend_mod.row/summarize`. Si el lugar no tiene comuna o no hay foto de hace siete días, `trend` va con `summary.sin_anterior = 7` y `rows` vacío: la vista no puede inventar una comparación. No cambies `SHARE_FIELDS` ni lo que hoy se publica del lugar.
2. `vecino.js`: bajo la tarjeta, una línea «El pronóstico de esta semana viene más alto/bajo/igual que el de la semana pasada (N de 7 días)» con `change_label`, y cuando no hay con qué comparar, la frase «Todavía no hay pronóstico de la semana pasada para comparar». Añadir la misma idea a `speechFor` sin romper `keepSpeaking` (la frase hablada se compara entre repintados).
3. Nada de textos que sugieran un incendio: el comparador mide dos pronósticos del mismo día, no lo que pasó en el cerro (dilo en el comentario del código).

## Criterio de listo (verificable)
Nuevo `tests/test_shared_trend.py` sobre la base de demostración:
- sin `risk_snapshot` de hace siete días → `trend.summary.sin_anterior == 7` y la respuesta no afirma subida ni bajada;
- con una foto de hace siete días más alta que el pronóstico de hoy → el `change` de ese día es `baja` y aparece `change_label`;
- el resto de la respuesta de `/api/shared/{token}` no cambia (mismas claves de antes, más `trend`).
Más: `.venv/Scripts/python.exe -m pytest tests/test_shared_trend.py tests/test_features.py -q` en verde, `python dev.py check` en verde y e2e de la vista del enlace compartido. Actualiza `CHANGELOG.md`.

No toques nada más: ni `routes/public.py`, ni `trend.py`, ni `zona.js`, ni `views/riesgo.js`.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
