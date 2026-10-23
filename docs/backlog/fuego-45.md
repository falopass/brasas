---
id: FUEGO-45
repo: brasas
rama: docs/decision-pendiente-en-el-escenario
modelo: swe-2-high
riesgo: C
archivos: ninguno (decisión), scripts/local/build_pendientes.py, web/data/pendientes-comunas.json, backend/fwi.py, backend/routes/public.py, tests/test_pendientes.py, docs/FUENTES.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
---

# Decisión: cómo entra la pendiente real en el escenario de propagación

**Objetivo.** Que Diego elija cómo se incorpora la pendiente del terreno al escenario estimado, antes de que alguien escriba código que parezca más preciso de lo que es.

**Ítem del backlog / foco de Diego.** Foco 1: «la propagación debe explicar viento, pendiente y humedad en términos que un vecino entienda, siempre rotulada como escenario estimado y nunca como predicción». Se cruza con FUEGO-02, AGUA-02 (pendiente para aluviones) y DET-02 (paralaje).

**Qué pasa hoy.** `backend/fwi.py` ya implementa la pendiente como viento equivalente (FBP, ecs. 39-44): `_slope_factor` (línea 295), `_slope_equivalent_wind` y los parámetros `slope_deg`/`aspect_deg` de `propagation_scenario` (línea 323). Pero nadie les pasa esos valores y el docstring lo dice (línea 331): «sin ella (hoy: BRASA no tiene DEM) el escenario es de terreno plano». La ruta que arma el escenario (`backend/routes/public.py:449`) llama `propagation_scenario(ffmc, wind, dir)` con tres argumentos. O sea: la física está escrita y apagada, y el vecino lee un escenario al que le falta justo el factor que en un cerro del Maule manda más que el viento.

**Opciones (con su costo).**
- **A. Tabla estática por comuna.** Precalcular pendiente y orientación medias por comuna desde un DEM y versionarlas en `web/data/`. Barato en runtime, pero una comuna entera con un solo número es casi una ficción: Talca tiene valle y precordillera.
- **B. DEM por punto del incidente.** Buscar el píxel del DEM en la coordenada del incendio (Copernicus GLO-30 o SRTM) y pasarlo al escenario. Mucho más honesto; exige decidir cómo se consulta (archivo local, servicio, caché) y con qué resolución.
- **C. No hacerlo y decirlo mejor.** Dejar el escenario plano y que la ficha diga explícitamente «no considera la pendiente» hasta tener DEM. Cuesta una línea y no engaña a nadie.

**Riesgo de equivocarse.** Un escenario con pendiente mal puesta puede mover el rumbo decenas de grados y se lee como si supiera más. Cualquier opción debe mantener el rótulo «escenario estimado, no es una predicción» y una lista de supuestos visible.

**Qué necesita de Diego.** Elegir A, B o C; si es B, autorizar la fuente del DEM (y si se puede versionar el recorte de Chile en el repo) y la resolución mínima; si es C, aprobar el texto. Con eso se escribe el brief de implementación y su criterio de término.

Decisiones así las toma Diego, no la fábrica.


DECISION (21-10, Diego delegó): Aprobado: pendiente real desde el DEM en el escenario, con test de caso plano vs pendiente.

## Unificado el 23-10-2026

Este encargo absorbe otros que pedían lo mismo sobre los mismos archivos. Además de lo de arriba, incluye:

- **FUEGO-22** ([original](unificados/fuego-22.md)): Fuente del relieve: Copernicus DEM GLO-30 (verificar licencia y atribución), derivados precalculados con un script en `scripts/local/` y peso del archivo medido.
- **FUEGO-34** ([original](unificados/fuego-34.md)): La pendiente entra con el modelo actual (`_slope_factor` de FBP en `backend/fwi.py`), siempre rotulada «escenario estimado» y revisada por `geo-reviewer`.
