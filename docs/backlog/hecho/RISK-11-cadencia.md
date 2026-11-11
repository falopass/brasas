# RISK-11 · cadencia del verdor satelital

Estado al 11 de noviembre de 2026, leído de `web/data/vegetacion-sequedad.json` en `main`.

## Muestra

- La muestra de septiembre de 2026 cubría 17 comunas. El archivo vigente ya no es esa muestra.
- Generado el 2026-11-11T01:39:57Z. Imagen MOD13Q1 del 2026-10-16.
- 288 comunas continentales con `anomalia_pct`. Sin píxel fiable no hay número: no se guarda un cero.
- Isla de Pascua y Juan Fernández quedan fuera de la grilla del producto.
- El rollup regional tiene 15 filas. Falta O'Higgins. El punto de muestra de esa región es Santa Cruz (6310) y no está en `comunas`. Hay 25 comunas de O'Higgins con dato propio (códigos 63xx, salvo 6310). El promedio de la macrozona Centro usa solo Valparaíso y Metropolitana, que sí tienen fila. No se inventa una fila regional a partir de esas 25.

## Cadencia

- MOD13Q1 es un compuesto de 16 días. El archivo declara `cadencia_dias: 16`.
- No se regenera todos los días. Se vuelve a correr `scripts/actualizar_sequedad_vegetacion.py` cuando ORNL liste un compuesto más nuevo que `imagen_en`.
- Si la fecha no es posterior a la publicada, no recorre las comunas ni reescribe el JSON. Una fecha anterior tampoco reemplaza el archivo.
- La próxima corrida útil es la que traiga una imagen posterior al 2026-10-16. Hasta entonces el archivo publicado sigue vigente.
- No hay cron en producción en este cambio. La corrida sigue siendo manual y usa la caché fuera del repo para no repetir píxeles ya pedidos.

## Qué no hacer

- No promediar las comunas de O'Higgins para fabricar la fila regional.
- No elegir otro punto de muestra sin una corrida real que tenga píxel fiable.
- No publicar una fecha de imagen que esta corrida no haya leído.

## Cierre

Hecho el 11-11-2026. La sequedad por comunas entró en
[#830](https://github.com/falopass/brasas/pull/830) y la cadencia se concilió con
[#852](https://github.com/falopass/brasas/pull/852) (este documento) y
[#857](https://github.com/falopass/brasas/pull/857) (la corrida no retrocede a una
imagen anterior de MOD13Q1). La cadencia de 16 días y las guardas de fecha quedan
declaradas arriba y el script es `scripts/actualizar_sequedad_vegetacion.py`.
