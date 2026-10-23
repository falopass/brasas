---
id: AUTO-10
repo: brasas
rama: feat/diagnostico-de-latencias
modelo: swe-2-high
riesgo: B
archivos: backend/main.py, backend/diagnostics.py, backend/routes/diagnostico.py, tests/test_diagnostico_api.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# AUTO-10 · El producto no sabe qué endpoints van lentos ni cuántos 5xx produce

## Objetivo
Que BRASA mida su propio rendimiento y sus errores por ruta y los publique en un GET pequeño, para que la persona dueña detecte una página lenta o un 500 sin depender de los registros del contenedor (que el proxy no deja descargar).

## Ítem del backlog
Foco del dueño (3) auto-mejora: «que el propio producto detecte y reporte sus fallas (datos viejos, fuentes caídas, páginas lentas, errores 5xx…)».

## Qué pasa hoy (verificado en main 3ceae01)
- `backend/main.py:64-79` ya envuelve **cada** request con un middleware (`security_headers`): es el lugar natural para cronometrar, sin añadir otro salto.
- `backend/diagnostics.py:19-66` sólo resume la ingesta (`ingest_runs`): no hay una sola cifra sobre las peticiones HTTP que atiende la API. Una vista que tarda 4 s o una ruta que devuelve 500 tres veces por hora hoy es invisible.
- `backend/routes/public.py` (`/api/status`) está tomado por PRs abiertos (OFI-18, OFI-17, RISK-07): **no lo toques**. La publicación va en una ruta nueva.

## Solución pedida
1. `backend/diagnostics.py`: un acumulador en memoria con ventana deslizante de 15 minutos por ruta: `n`, `errores_5xx`, `p50_ms`, `p95_ms`, `max_ms`, `ultimo_error_at` y `ultimo_codigo`. Usa la ruta plantilla (`request.scope.get("route").path`), nunca la URL: los ids de incidente y los tokens no pueden quedar guardados. Nada de IP, User-Agent ni query string. Limpia la ventana al responder (o con un tope de muestras) para que no crezca sin límite.
2. `backend/main.py`: en el mismo middleware, medir duración y código; excluir `/api/diagnostico` para que no se cuente a sí mismo.
3. `backend/routes/diagnostico.py` (nuevo): `GET /api/diagnostico` → `{"window_min": 15, "routes": [...ordenado por p95 descendente...], "errors_5xx": n, "slowest": "...", "advice": "..."}`. `advice` es una frase de reglas: si hay 5xx, «el servidor está devolviendo errores: revisa las rutas marcadas»; si el p95 más alto pasa de 800 ms, «esta ruta tarda demasiado: revisa su consulta»; si todo está bien, «sin problemas de rendimiento en la ventana». Regístralo en `backend/main.py` junto a los demás routers.

## Criterio de listo (verificable)
Nuevo `tests/test_diagnostico_api.py`:
- la agregación con muestras sintéticas da p50/p95 esperados y cuenta los 5xx (prueba pura del acumulador);
- con `TestClient`, tres GET a `/api/incidents` y un GET a `/api/diagnostico`: la ruta aparece con `n >= 3` y trae las claves prometidas;
- el payload no contiene query strings ni el token del dispositivo;
- `/api/diagnostico` no aparece en su propia tabla.
Más: `.venv/Scripts/python.exe -m pytest tests/test_diagnostico_api.py tests/test_api.py -q` en verde y `python dev.py check` en verde. Actualiza `CHANGELOG.md`.

No toques nada más: ni `routes/public.py`, ni las vistas, ni el Worker de `deploy/`.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
