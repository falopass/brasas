---
id: CONT-14
repo: brasas
rama: feat/historia-buscar-por-comuna
modelo: swe-2-high
riesgo: B
archivos: web/js/views/casos.js, tests/js/casos.test.mjs, tests/js/index.js, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

NOTA DE LA FÁBRICA: Tu PR #367 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #367 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #234 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #234 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: el PR #234 tiene conflicto con main. Antes de nada: `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: el PR #234 tiene conflicto con main. Antes de nada: `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica y sube con `--force-with-lease`.

# CONT-14 · Buscar los incendios nominados por comuna en Historia

**Objetivo.** Que quien entra a Historia pueda escribir el nombre de su comuna y ver los incendios nominados que le tocaron (2002-2024), con cuántas hectáreas suman y en qué temporadas, sin cargar nada nuevo.

**Ítem del backlog.** CONT-06/OFI-19 (historia desde fuentes GEPRIF) y el pedido de la investigación «Tu comuna en 2017» (`docs/research/00-sintesis-y-features.md`, feature 7). Hoy el bloque de nominados ya existe y ya trae el dato por comuna; falta poder buscarlo.

**Evidencia de que está pendiente (verificada contra `main`).**
- `web/js/views/casos.js:73-79`: `paintNominados()` filtra **solo** por temporada (`!season || i.season === season`); no hay búsqueda por comuna.
- `web/js/views/casos.js:82-100`: `openNominados()` carga `web/data/incendios-nominados.json` una vez y solo agrega el `<select>` de temporadas; no hay campo de texto ni resumen de superficie.
- `web/data/incendios-nominados.json` (355 KB) trae por ítem `name`, `comuna`, `season`, `ha`, `lat`, `lon`, así que no hace falta tocar el backend.

**Qué hacer.**
1. Agregar al bloque de nominados un campo de búsqueda por comuna (texto libre, sin tildes, `ñ` = `n`, insensible a mayúsculas) y un botón «Limpiar». El filtro de temporada debe seguir funcionando y combinarse con el de comuna.
2. Mostrar bajo la lista el resumen del filtro actual: cantidad de incendios y suma de hectáreas; si no hay resultados, un vacío explícito («No hay incendios nominados en esa comuna en la temporada elegida»).
3. Extraer la función pura de filtrado/normalización a una función exportada del propio `casos.js` (o a `web/js/nominados.js` nuevo si queda más limpio) para poder probarla.
4. Mantener el tope de 80 filas (`NOM_MAX`) y decir cuántos quedaron fuera del recorte.

**Archivos a tocar.** `web/js/views/casos.js`, `tests/js/casos.test.mjs` (nuevo), `tests/js/index.js` (agregar el import), `CHANGELOG.md`.
**No toques nada más.** Ni el backend, ni `web/data/incendios-nominados.json`, ni otras vistas.

**Criterio de listo (verificable).**
- `node --test tests/js` en verde con pruebas del filtro: comuna exacta, con tilde («Ñuble»/«Nuble»), sin resultados, combinación con temporada, y que el resumen sume bien las hectáreas.
- `python dev.py check` termina en «Todo en orden».
- `python dev.py e2e` sin errores; la búsqueda se puede usar con teclado (Enter/limpiar) y a 390 px no desborda.

**Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.**


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
