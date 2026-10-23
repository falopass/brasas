---
id: ALR-26
repo: brasas
rama: feat/aviso-de-foco-con-accion
modelo: swe-2-high
riesgo: B
archivos: backend/alerts.py, tests/test_aviso_accion.py, CHANGELOG.md, tests/test_risk_alerts.py, tests/test_alerts.py
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# ALR-26 · El aviso de foco dice qué hacer, no solo dónde está

## Objetivo

Que un aviso de foco de calor, en especial el urgente, le diga a la persona **qué hacer en los próximos minutos**. Hoy el mensaje entrega distancia, dirección y viento —excelente— pero cierra con «Verifica con fuentes oficiales y prepárate para actuar», que no le dice nada concreto a alguien que acaba de despertarse con la notificación.

## Evidencia de que está pendiente

- `backend/alerts.py:123-141` (`compose`) arma el cuerpo: distancia y dirección (línea 128), viento si viene hacia el lugar (130), la línea del incidente (132), otras detecciones (135) y la fuente (139). La única acción real aparece en `alerts.py:136-138`, y **solo** cuando `place.get("older_adult")` es verdadero.
- El cierre es `alerts.py:141`: «Un foco de calor no confirma un incendio. Verifica con fuentes oficiales y prepárate para actuar.» Es un descargo, no una instrucción.
- El patrón de acción ya existe y está bien hecho en el aviso de calor de la DMC (ALR-22, PR #373 mergeado: una acción de salud con fuentes). Se trata de aplicar la misma idea al aviso de foco.
- Riesgo de redacción: cualquier texto nuevo debe dejar claro que es un **escenario estimado**, nunca una predicción de que el fuego va a llegar. Ese es un requisito explícito del dueño.

## Qué hacer

1. En `backend/alerts.py`, agrega una tabla corta de acciones por nivel (`urgente`, `posible`, `aviso`) y una función que devuelva **una** línea de acción, insertada después de la línea de viento y antes de la fuente.
   - `urgente`: alejar a la familia de pastizales, techos y acopios; tener agua y documentos a mano; cerrar ventanas si llega humo; seguir a SENAPRED y a Bomberos; no esperar a ver el fuego para salir.
   - `posible`: tener el teléfono cargado, la vía de salida clara y el plan familiar a mano.
   - `aviso`: sin acción nueva (no sumar ruido).
2. Si el lugar tiene persona mayor, la acción urgente se antepone a la línea que ya existe en `alerts.py:136-138`, sin repetirla dos veces.
3. Nada de «va a llegar», «se dirige a tu casa» ni «predicción». Usa «escenario estimado» si hace falta describir el avance.
4. Mantén el largo del cuerpo razonable: el aviso se lee en una notificación.

## Archivos

`backend/alerts.py`, `tests/test_aviso_accion.py` (nuevo), `CHANGELOG.md`.

**No toques nada más.** No toques `backend/alerts.py` en la zona de `compose_official` ni `compose_report` (otros tipos de aviso, otro alcance), ni `web/js/views/alertas.js` (lo tiene tomado FIX-40 con un PR abierto), ni `backend/services.py`.

## Caso de prueba concreto

En `tests/test_aviso_accion.py` (nuevo, con las fixtures de `tests/conftest.py`):

- Un aviso `urgente` de un foco a 1,2 km incluye al menos una acción con verbo concreto («aleja», «ten», «cierra», «sigue») y **no** contiene las palabras «predicción» ni «va a llegar».
- Un aviso `posible` no repite la frase del urgente.
- Un aviso `urgente` para un lugar con `older_adult=True` no repite dos veces la instrucción de salir temprano.
- Un aviso `aviso` no gana ninguna línea nueva respecto de hoy.

## Criterio de listo

- `./.venv/Scripts/python.exe -m pytest tests/test_aviso_accion.py tests/test_risk_alerts.py tests/test_avisos_texto.py -q` en verde.
- `python dev.py check` en verde (ver la nota del final).
- El PR muestra el cuerpo completo de un aviso urgente antes y después, en texto plano.
- Sin archivos bajo `web/` en `git diff --stat`.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.

**Estado del repo que debes saber.** `main` está en rojo solo por el presupuesto de arranque (`tests/test_peso_arranque.py`: 252,2 KB contra 252 KB) y el total de `web/` está en 199,9 KB contra 200 KB. Si `python dev.py check` falla únicamente en `test_peso_arranque`, dilo en el PR y sigue; no subas umbrales ni toques `scripts/local/peso_arranque.py` ni `presupuesto_peso.py`. Otro encargo (DIETA-01) está arreglando eso.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

## Unificado el 23-10-2026

Este encargo absorbe otros que pedían lo mismo sobre los mismos archivos. Además de lo de arriba, incluye:

- **ALR-24** ([original](unificados/alr-24.md)): El aviso dice en palabras hace cuánto se detectó el foco (push, Telegram y lista de Avisos).
