---
id: QA-COB
repo: brasas
rama: test/cobertura-criticos
modelo: swe-2-high
riesgo: B
archivos: tests/test_alertas_bordes.py, tests/test_incidentes_estados.py, tests/test_cicatriz_bordes.py, tests/test_lugares_cobertura.py, tests/js/cerca.test.mjs, tests/js/alertas-resumen.test.mjs, tests/js/capas.test.mjs, docs/backlog/hecho/QA-COB.md, CHANGELOG.md
e2e: no
---

# QA-COB: cobertura de los módulos críticos de avisos, lugares y aluvión

Solo pruebas: ningún archivo de producción cambió. La prioridad fue por riesgo
(un error aquí avisa mal a una persona o declara fuego lo que no es), no por
porcentaje — la línea base ya estaba alta en estos módulos.

## Qué se agregó

- `tests/test_alertas_bordes.py` — `alerts.py`: silencio 23:00–07:00 en hora de
  Chile con el cambio de reloj (los bordes en UTC-3 y en UTC-4), `aplazable`,
  `vencida`, componedores (`compose_dmc`, `compose_report`, `compose_follow_estado`,
  `compose_aluvion`), `evaluate_status_change` con el lugar borrado a medio
  camino, `evaluate_smoke` con su deduplicación por día, `caps_exceeded_follow`
  con `AVISO_TOPES=0` y la fusión de seguimientos duplicados.
- `tests/test_incidentes_estados.py` — `incidents.py`: la escala
  `anomalia → posible → reportado`, que `confirmado` y `controlado` solo entran
  por `link_official`, `expire` con incidentes satelitales, oficiales y
  extranjeros, `resolve_merge`, `refresh_near`, las máscaras de fuentes fijas y
  la fusión cuando la detección que une no está en `observations`.
- `tests/test_cicatriz_bordes.py` — `scars.py` y `lluvia.py`: la cicatriz que
  cumple 365 días clavados (cuenta) y la de 366 (no), el disco CONAF que toca el
  borde de los 5 km, geometrías y fechas corruptas, la huella que se recalcula
  cuando su sello no calza, y `senal`/`ventana` con `None`, una sola hora y el
  cambio de día UTC.
- `tests/test_lugares_cobertura.py` — `routes/personal.py`: crear, editar y
  borrar lugares; IDOR (el token ajeno recibe 404 en resumen, historial, edición,
  borrado y compartir); el enlace de familia con su revocación; `build_summary`
  en los cuatro estados (tranquilo, riesgo, aviso, urgente — satélite y CONAF);
  push, telegram, inbox con cursor roto, export con seguimientos descifrados y
  el tope de 20 incendios seguidos con la carrera del INSERT idempotente.
- `tests/js/cerca.test.mjs`, `tests/js/alertas-resumen.test.mjs`,
  `tests/js/capas.test.mjs` — bordes de `cercaDe` (24 h clavadas fuera, `ahora`
  como `Date`/ISO/ilegible, coordenadas no finitas, foco de incidente fuera del
  radio o no listado, fuente fija que no cuenta ni como dudosa, `confirmado` y
  `controlado` que nunca se degradan aunque `n_reliable` sea 0), `summaryByPlace`
  con `level` desconocido y `enlaceCompartir` con tipo desconocido y sin origen.

## Cobertura antes y después

Python (`pytest --cov=backend`, suite completa con el candado):

| Módulo | Antes (líneas) | Después (líneas) |
|---|---|---|
| `backend/alerts.py` | 95 % (41 sin cubrir) | **100 %** |
| `backend/incidents.py` | 95 % (26 sin cubrir) | **100 %** |
| `backend/lluvia.py` | 99 % (1 sin cubrir) | **100 %** |
| `backend/routes/personal.py` | 91 % (42 sin cubrir) | 99 % (4 sin cubrir: 303, 769, 869-870) |
| `backend/scars.py` | 93 % (13 sin cubrir) | 99 % (1 sin cubrir: 274) |
| Total `backend/` | 94 % (632 sin cubrir) | **95 % (514 sin cubrir)** |

JavaScript (`node --test --experimental-test-coverage tests/js/`):

| Módulo | Antes (líneas / ramas / funciones) | Después |
|---|---|---|
| `web/js/cerca.js` | 49,07 % / 78,13 % / 21,43 % | 49,07 % / 100,00 % / 21,43 % |
| `web/js/capas.js` | 99,27 % / 86,21 % / 100 % | 100 % / 89,83 % / 100 % |
| `web/js/alertas-resumen.js` | 100 % / 93,75 % / 100 % | 100 % / 94,12 % / 100 % |

En `cerca.js` lo que sigue sin cubrir es la parte de la pantalla que toca el DOM
(`abrirLista`, `permisoDenegado`, `verEnElMapa`…): con `node:test` no hay DOM,
pero todas las ramas de `cercaDe` —la lógica que decide qué se anuncia— quedaron
en 100 %.

## Bugs encontrados

- **`backend/alerts.py` — `vencida` no tolera `expires` no-texto.** Con
  `{"expires": 123}` revienta con `AttributeError: 'int' object has no attribute
  'replace'`: el `except (TypeError, ValueError)` nunca lo alcanza porque
  `_parse` llama `.replace` antes. Entrada: `vencida({"expires": 123}, now)`;
  esperado: `False` (fecha ilegible = no vencida); obtenido: excepción. Marcado
  `pytest.mark.xfail(strict=True)` en `test_alertas_bordes.py`; no se arregla en
  este PR (solo pruebas).

## Hallazgos fuera de alcance

- La fusión de incidentes decide el superviviente por orden de candidatos; con
  `first_seen_at` empatado el ganador puede cambiar entre corridas del mismo
  lote (el alias queda en `incident_merges` igual — el comportamiento visible es
  el mismo, pero el id que sobrevive no es determinista a igualdad de hora).
