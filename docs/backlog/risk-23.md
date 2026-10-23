---
id: RISK-23
repo: brasas
rama: feat/comuna-lo-que-se-quemo
modelo: swe-2-high
riesgo: B
archivos: backend/routes/comuna.py, backend/scars.py, tests/test_comuna_api.py, tests/test_scars.py, web/js/exposure.js, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo:** que la ficha de una comuna diga en castellano simple cuánto se ha quemado esta temporada cerca de las casas, usando las cicatrices que BRASA ya calcula, para que un vecino de Talca o San Clemente entienda su riesgo de hoy con un dato de su comuna y no con un mapa.

**Ítem del backlog:** la sección «¿A quién afecta?» (OFI-08, PR #344) y AGUA-01 (cicatrices, PR #340). Hoy `web/js/exposure.js:25` (`exposureSection`) muestra población, viviendas y hectáreas de interfaz leyendo dos JSON estáticos, y no dice nada de lo que se quemó. Las cicatrices existen desde #340, pero solo se publican en `GET /api/opendata/scars.geojson` (`backend/routes/opendata.py:492`) y `backend/scars.py:52` (`season_scars`) calcula **todas** las comunas de la ventana (hasta 300 incidentes, un footprint por incidente), así que pedirlas para una sola comuna desde el navegador es caro. La API institucional `/api/comuna/{code}` (`backend/routes/comuna.py:78`) tiene un bloque por fuente y su caché de 300 s, pero no trae temporada.

**Qué hacer:**
1. En `backend/scars.py`, añade a `season_scars` un parámetro opcional `comuna_code: int | None = None` que filtre en SQL (`AND comuna_code = ?`) antes del `LIMIT`, manteniendo intacto el comportamiento actual cuando no se pasa. Documenta que filtra en la consulta y no después.
2. En `backend/routes/comuna.py`, agrega al payload un bloque `temporada` con `{"source": {...}, "ha": ..., "n_incidentes": ..., "desde": ..., "hasta": ...}` calculado con `season_scars(svc.db, days=90, comuna_code=code)`; sin cicatrices, `ha: 0`, `n_incidentes: 0` y una `note` que diga que no hay huellas de detecciones en la ventana (nunca un cero sin explicación). Mantén la caché y el TTL como están.
3. En `web/js/exposure.js`, agrega una línea al bloque «¿A quién afecta?»: «En los últimos 90 días, los satélites vieron calor en X ha de esta comuna (N focos con ficha)», con la aclaración de que es huella de detecciones y no el perímetro oficial de CONAF. Léela del bloque nuevo de `/api/comuna/{code}` con un `fetch` perezoso, con `catch` que devuelve cadena vacía (la sección nunca debe romper la vista) y sin bloquear el resto del bloque.
4. Tests: en `tests/test_scars.py`, el filtro por comuna devuelve solo esa comuna y con `comuna_code=None` sigue devolviendo todas; en `tests/test_comuna_api.py`, el payload trae `temporada` con fuente y una comuna sin incidentes trae la `note`.

**Archivos a tocar:** `backend/routes/comuna.py`, `backend/scars.py`, `tests/test_comuna_api.py`, `tests/test_scars.py`, `web/js/exposure.js`, `CHANGELOG.md`. No toques nada más: `web/js/views/riesgo.js` está tomado por el PR #357 (solo se usa su llamada existente a `exposureSection`) y `backend/routes/opendata.py` está en curso (FUEGO-05).

**Criterio de listo:** `python dev.py test -k "scars or comuna"` verde; `python dev.py check` verde; y en la demo, la ficha de una comuna con cicatrices muestra la línea de hectáreas y una comuna sin ellas muestra la nota, sin errores de consola.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
