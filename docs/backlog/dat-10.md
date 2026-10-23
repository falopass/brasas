---
id: DAT-10
repo: brasas
rama: feat/datos-abiertos-recorte-explicado
modelo: swe-2-high
riesgo: B
archivos: backend/routes/opendata.py, docs/API.md, tests/test_opendata.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# DAT-10 · Los datos abiertos explican qué focos quedan fuera de Chile

## Objetivo

Que quien abra los datos abiertos entienda por qué hay focos sin comuna y por qué el número de BRASA no siempre calza con el de FIRMS. Hoy la colección de observaciones entrega `comuna: null` sin decir si es un punto fuera de Chile, un punto en el mar o un error, y el catálogo no documenta ningún recorte territorial.

## Evidencia de que está pendiente

- `backend/routes/opendata.py:245-290` (`observations_geojson`) arma cada feature con `comuna: comuna.name if comuna else None`. Cuando el punto está fuera del polígono comunal, el consumidor recibe `null` y no hay forma de distinguir «fuera de Chile» de «sin asignar».
- El índice de datos abiertos (`backend/routes/opendata.py:85-170`) describe las colecciones y sus propiedades, y no menciona ni el recorte ni el descarte.
- En el otro endpoint sí existe el concepto: `backend/routes/public.py:424-429` publica `in_chile` y `outside_chile` para la exploración. La idea está, la documentación y la colección geoespacial no la tienen.
- `docs/API.md` tampoco lo dice.

## Qué hacer

1. En `observations_geojson`, agrega a cada feature un booleano `en_chile` (derivado de `comuna_code is not None`) y una `meta` en la colección: `{"recorte": "polígono comunal BCN con tolerancia costera", "fuera_de_chile": <n>, "total": <n>, "explicacion": "…"}`.
2. Mantén el parámetro opcional `chile=1` (o `solo_chile=true`, elige uno y documéntalo) que filtre a los puntos con comuna. **Por defecto no filtres**: no rompas a quien ya consume la colección.
3. Replica la explicación en el índice (`opendata.py:85`), en la entrada de `observations.geojson`: una línea que diga que los puntos fuera del territorio no tienen comuna y por qué se conservan (transparencia: el archivo crudo de la fuente sí los trae).
4. Documenta en `docs/API.md`: parámetro nuevo, campo nuevo, ejemplo de respuesta.

## Archivos

`backend/routes/opendata.py`, `docs/API.md`, `tests/test_opendata.py`, `CHANGELOG.md`.

**No toques nada más.** En particular no toques `backend/routes/public.py` (lo tiene tomado otro encargo), ni `backend/providers/glm.py`, ni `backend/providers/goes.py` (FUEGO-12 y DET-25 van en paralelo), ni `docs/FUENTES.md` (lo lleva DOC-13).

## Caso de prueba concreto

En `tests/test_opendata.py`, con la base sembrada:

- Un punto con `comuna_code` de Talca y otro con `comuna_code` nulo → el GeoJSON trae `en_chile: true` y `false`, y `meta.fuera_de_chile == 1`.
- Con `?chile=1` (o el nombre que elijas) la colección trae solo el punto chileno y `meta.total == 1`, pero **la respuesta sin el parámetro sigue trayendo los dos** (compatibilidad).
- El índice menciona la palabra «fuera» en la entrada de observaciones.

## Criterio de listo

- `./.venv/Scripts/python.exe -m pytest tests/test_opendata.py -q` en verde.
- `python dev.py check` en verde (ver la nota del final).
- `docs/API.md` describe el parámetro y el campo nuevos.
- Sin archivos bajo `web/` en `git diff --stat`.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.

**Estado del repo que debes saber.** `main` está en rojo solo por el presupuesto de arranque (`tests/test_peso_arranque.py`: 252,2 KB contra 252 KB) y el total de `web/` está en 199,9 KB contra 200 KB. Si `python dev.py check` falla únicamente en `test_peso_arranque`, dilo en el PR y sigue; no subas umbrales ni toques `scripts/local/peso_arranque.py` ni `presupuesto_peso.py`. Otro encargo (DIETA-01) está arreglando eso.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
