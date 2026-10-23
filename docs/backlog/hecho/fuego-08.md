---
id: FUEGO-08
repo: brasas
rama: feat/frescura-por-fuente
modelo: swe-2-high
riesgo: C
archivos: backend/freshness.py, backend/routes/public.py, tests/test_freshness.py, web/js/app.js, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# Objetivo (para que lo vea Diego antes de lanzarlo)

Que la aplicación no diga «datos al día» cuando una fuente lleva horas caída. Hoy la frescura se mide con una sola marca —la última corrida de la ingesta— y no con lo que de verdad llegó de cada producto.

# Por qué no se lanza solo

Toca la afirmación más delicada del producto («el dato es de ahora») y la cambia de significado, en `backend/routes/public.py` y `web/js/app.js` (ambos con PRs abiertos). Necesita una decisión de Diego sobre semántica y umbrales por fuente: GOES barre cada 10 minutos, pero los polares (VIIRS/MODIS) pasan 2 a 3 veces al día; un mismo umbral de 30 minutos convertiría el satélite polar en «caído» casi siempre.

# Evidencia

- `backend/freshness.py:28-37` (`status`): `stale` se calcula solo con `last_ingest_at`, que se escribe al final de cada ciclo, aunque el ciclo haya fallado en FIRMS o CONAF.
- `backend/routes/public.py:129-160`: `/api/status` ya publica `history` por producto (con `ok` por corrida), `last_cycle` y `freshness`; los insumos del dato honesto ya están ahí.
- `backend/diagnostics.py` (`error_summary`, `failures_24h`) calcula fallas por producto, pero no las cruza con la frescura.
- `web/js/app.js:231-233`: la píldora toma `status.freshness` y muestra una sola frase para todo.
- Caso concreto: si FIRMS falla 2 horas y GOES sigue bien, `last_ingest_at` se mantiene fresco y la aplicación afirma que el dato está al día — justo la frase que la regla de oro prohíbe.

# Propuesta (a aprobar o ajustar)

1. `backend/freshness.py`: `status(...)` pasa a recibir también `history` (o un dict de última corrida buena por producto) y devuelve `products: {FIRMS: {age_seconds, stale, stale_after_s}, GOES: {...}, CONAF: {...}}` con umbrales por producto en una constante documentada (propuesta: GOES 30 min, FIRMS polar 3 h, CONAF 6 h, Open-Meteo 6 h), más un `stale` global que es el peor de los que importan.
2. `/api/status` publica ese objeto sin cambiar los campos actuales (`age_seconds`, `stale_after_s`, `stale`), para no romper el cliente ni el monitoreo.
3. `web/js/app.js`: la píldora sigue mostrando una frase, pero cuando lo viejo es una fuente concreta dice cuál («Sin datos nuevos de FIRMS hace 2 h»); la página Calidad muestra el detalle por producto.
4. `docs/FUENTES.md`: la tabla de umbrales con su porqué.

# Criterio de listo (si se aprueba)

`tests/test_freshness.py`: un historial con FIRMS caído 2 h y GOES al día da `products.FIRMS.stale == true`, `products.GOES.stale == false` y `stale == true`; un historial vacío no inventa productos ni dice «al día»; el objeto conserva `age_seconds`/`stale_after_s` para el cliente actual. `python dev.py check` y `e2e` en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
