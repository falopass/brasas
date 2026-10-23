---
id: AUTO-01
repo: brasas
rama: feat/salud-5xx-y-lentitud
modelo: swe-2-high
riesgo: B
archivos: backend/main.py, backend/salud.py, backend/routes/salud.py, tests/test_salud.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que BRASA **cuente y publique sus propias fallas de servicio** —respuestas 5xx y respuestas lentas— en un endpoint `/api/salud` que además diga, en palabras simples, qué está fallando y qué se está haciendo al respecto. Es el pedazo de «auto-mejora» que hoy no existe: el producto solo sabe de las fuentes externas, no de sí mismo.

# Ítem del backlog

Prioridad de producto de esta ronda: «que el propio producto detecte y reporte sus fallas (datos viejos, fuentes caídas, páginas lentas, errores 5xx) y proponga el arreglo». Lo de datos viejos y fuentes caídas ya está (`backend/freshness.py`, `backend/diagnostics.py`); los 5xx y la lentitud del propio backend no.

# Evidencia de que está pendiente

- `backend/diagnostics.py:19-36` (`error_summary`) y `:42-66` (`failures_24h`) solo leen la tabla `ingest_runs`: fallas de la ingesta, no del servicio HTTP.
- `backend/main.py:64-83` — el único middleware existente pone cabeceras de seguridad; no mide latencia ni status. Un 500 en `/api/explore` no deja ningún rastro consultable.
- `.github/scripts/monitoreo.py` (sondeo de `/api/status`) alerta de frescura y de respaldo, no de errores 5xx propios.

# Qué hacer

1. **`backend/salud.py`** (nuevo): acumulador en memoria con `collections.deque(maxlen=500)` de eventos `(ruta, metodo, status, ms, instante)`. `registrar(ruta, metodo, status, ms)`; `resumen()` devuelve últimos 60 min: `total`, `errores_5xx`, `lentas` (ms > 2000 aunque el status sea 200), `por_ruta` (top 10 por errores y por lentitud) y `problemas`: lista de dicts `{clave, gravedad, texto, arreglo}` armada con umbrales explícitos (p. ej. ≥1 5xx en la hora → «Respuestas con error en /api/x», arreglo «revisar los registros del contenedor y el issue de monitoreo»; p95 > 2 s → «Respuestas lentas»). Nada de datos personales: **solo** ruta normalizada (sin query string), método, status y ms; nunca IP, headers ni cuerpos.
2. **`backend/routes/salud.py`** (nuevo): `GET /api/salud` que devuelve `ok`, `window_min`, `total_respuestas`, `errores_5xx`, `lentas`, `por_ruta`, `problemas`. Registrar el router en `backend/main.py` junto a los demás (`main.py:51-60`).
3. **Middleware** en `backend/main.py`, aparte del de seguridad (no lo modifiques): medir con `time.perf_counter()`, registrar al volver, y **excluir `/api/salud`** para que la consulta no se cuente a sí misma ni se vuelva inestable. Si algo falla al registrar, el request sigue igual (nunca un 500 por la telemetría).

# Archivos a tocar

`backend/main.py`, `backend/salud.py`, `backend/routes/salud.py`, `tests/test_salud.py`, `CHANGELOG.md`. **No toques nada más** (ni `backend/routes/public.py`, ni `backend/routes/internal.py`, ni `docs/API.md`: están tomados por otros encargos).

# Criterio de listo (verificable)

`tests/test_salud.py` con `TestClient` (patrón de `tests/conftest.py`):

- (a) tres GET a una ruta inexistente (404) no suman a `errores_5xx`;
- (b) una ruta de prueba que lanza una excepción deja `errores_5xx == 1` y aparece en `por_ruta`;
- (c) una respuesta de más de 2 s cuenta en `lentas` (monkeypatch de `time.perf_counter` o `sleep` corto, lo que sea estable en CI);
- (d) `GET /api/salud` no se cuenta a sí misma (dos consultas seguidas dan el mismo `total_respuestas`);
- (e) pedir `/api/observations?bbox=-75,-56,-66,-17` deja la clave `/api/observations` sin query string.

`python dev.py test -k salud` en verde y `python dev.py check` en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
