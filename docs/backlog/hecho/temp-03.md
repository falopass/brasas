---
id: TEMP-03
repo: brasas
rama: feat/tu-comuna-temporada
modelo: swe-2-high
riesgo: B
archivos: backend/routes/panorama.py, web/js/api.js, web/js/views/zona.js, tests/test_panorama.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# TEMP-03 · «Tu comuna esta temporada» en Mi zona

## Objetivo
Que una persona de Talca o San Clemente abra 「Mi zona」 y vea, sin buscar nada, cuántos incendios informó CONAF este año en **su** comuna, cuánta superficie suman y cómo se compara con la temporada anterior, además de los días con Botón Rojo de esa comuna.

## Ítem del backlog
TEMP-01/TEMP-02 (panorama de la temporada) y foco del dueño (4): «lo que acerque a un vecino a entender su riesgo hoy… comparación… datos oficiales bien explicados». El panorama existe, pero solo se ve en `#/temporada` y **por comuna solo muestra el top 12**.

## Qué pasa hoy (verificado en `main` 3ceae01)
- `backend/routes/panorama.py:42`: `def panorama(season: str | None = Query(None, …))` — **no acepta filtrar por comuna**.
- `backend/routes/panorama.py:114-123`: `by_comuna` se ordena por hectáreas y se corta con `[:12]`; una comuna chica del Maule nunca aparece en la respuesta.
- `backend/routes/panorama.py:84-87`: `boton_rojo_days` es `COUNT(DISTINCT date)` **global** de la temporada, sin `comuna_code`, aunque la tabla sí lo tiene (`backend/db.py:121-129`).
- `web/js/views/zona.js:391-401`: Mi zona pinta los lugares y salta directo a «Avisos»; no hay ningún bloque de temporada. `place.comuna.code` ya está disponible (se usa en `zona.js:232` para el calendario .ics).
- `tests/test_panorama.py` ya existe con `_fire`, `_br` y `make_client`: el caso de prueba se arma ahí mismo.

## Solución pedida
1. `GET /api/panorama?season=2025-2026&comuna=<code>`: parámetro opcional `comuna: int | None = Query(None, ge=1)`. Si viene y no existe en `territory().by_code`, **422** con mensaje claro.
2. La respuesta sigue siendo la de hoy (aditiva, no cambies nombres ni tipos) y suma `comuna_detail`:
   - `comuna`: `{code, name, region}`;
   - `current`: `{n, ha, en_combate}` de esa comuna en la temporada pedida (filtra las filas ya agregadas comparando el `code_for(comuna, region)` que el endpoint ya calcula);
   - `boton_rojo_days`: `COUNT(DISTINCT date) FROM boton_rojo WHERE comuna_code = ? AND date BETWEEN ?` con la ventana `_season_window(season)`;
   - `previous`: `{season, n, ha}` de la temporada anterior (`2025-2026` → `2024-2025`), con ceros si no hay filas.
   Sin `comuna`, `comuna_detail` es `null` y el resto de la respuesta queda **idéntico** a hoy (hay pruebas que lo fijan).
3. `web/js/api.js`: método `panorama(comunaCode, season)` que llame a esa ruta.
4. `web/js/views/zona.js`: bloque «Tu comuna esta temporada» entre los lugares (`:391`) y «Avisos» (`:401`). Una tarjeta por comuna distinta de los lugares guardados (máximo 2), con: «CONAF informó N incendios en <comuna> esta temporada (X ha). La temporada anterior: M (Y ha). Días con Botón Rojo: D.» + enlace a `#/temporada` + la nota «No es una alerta oficial: sigue a SENAPRED». Si no hay filas: «CONAF todavía no informa incendios en tu comuna esta temporada». Si la petición falla, la tarjeta **no se muestra** (nunca un error en medio de Mi zona).
5. Cuidado con el peso: `zona.js` y `api.js` están en el arranque. Mantén el cambio bajo (~1 KB gzip) y no toques `app.js`.

## Criterio de listo (verificable)
En `tests/test_panorama.py`, tres pruebas nuevas: (a) con dos comunas sembradas, `?comuna=<code>` devuelve solo la pedida y `current.n/ha/en_combate` correctos; (b) `previous` cuenta la temporada anterior y da ceros si no existe; (c) `boton_rojo_days` de la comuna cuenta solo sus fechas (siembra dos comunas con días distintos). Y una cuarta: sin `comuna`, `comuna_detail` es `null` y la respuesta conserva todas sus claves actuales. `python dev.py check` en verde. En e2e: guardar un lugar en Talca, abrir Mi zona y ver la tarjeta con números; con un lugar sin comuna, la tarjeta no aparece. `CHANGELOG.md` actualizado.

No toques nada más: ni `views/temporada.js`, ni `views/mapa.js`, ni `map.js`, ni el backend de ingesta.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
