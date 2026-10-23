---
id: DIETA-01
repo: brasas
rama: fix/arranque-bajo-presupuesto
modelo: swe-2-high
riesgo: B
archivos: web/js/views/calidad.js, web/data/licencias.json, tests/test_data_files.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Devolver `main` a verde: el arranque pesa hoy 252,2 KB gzip contra un presupuesto de 252 KB y por eso `python dev.py check` falla en cualquier rama que salga de `main` (la fábrica lleva más de 70 ítems bloqueados por este solo motivo). El arreglo es una dieta real de bytes, no subir el umbral.

**Ítem del backlog.** QA-62 (presupuesto de peso del arranque) y PESO-01 (la decisión de Diego sobre los umbrales, que este encargo NO toca).

**Qué pasa hoy.** `scripts/local/peso_arranque.py:33` fija `PRESUPUESTO_ARRANQUE_KB = 252` (229 KB medidos el 20-oct + ~10 % de holgura). Medido ahora sobre `main` 3ceae01: 252,2 KB. `tests/test_peso_arranque.py::test_arranque_real_dentro_del_presupuesto` falla por 0,2 KB y con él todo `dev.py check`; el propio script imprime la pista «recorta el arranque o mueve la vista a carga diferida». Además `presupuesto_peso.py` está en 199,5 de 200 KB: no queda margen para ninguna feature nueva.

**Dónde está el peso que sobra.** `web/js/views/calidad.js:27-37` (`THIRD_PARTY`, 10 filas) y `:38-43` (`OWN_WORK`) son una copia literal de las licencias de `docs/FUENTES.md`; medido con gzip -9 pesan 1.334 bytes y entran enteros en el arranque porque `app.js` importa la vista de forma estática. Se pintan en `calidad.js:226-228`. Es el único bloque de la vista que es documentación pura, no lógica.

**Qué hacer.** (1) Crear `web/data/licencias.json` con las dos listas, con la misma estructura (`[[titulo, texto], ...]`) y exactamente los mismos textos y el mismo orden. (2) En `calidad.js`, cargar ese JSON al pintar la vista con `fetch('/web/data/licencias.json')` y conservar el render `block()` sin cambios visuales; si el JSON no llega, mostrar el bloque con una línea de aviso y el enlace a `#/calidad` en vez de reventar. (3) Añadir a `tests/test_data_files.py` una prueba de forma del JSON: dos listas, cada fila con dos textos no vacíos, sin HTML. (4) Una línea en `CHANGELOG.md` con los bytes liberados.

**Archivos a tocar.** `web/js/views/calidad.js`, `web/data/licencias.json`, `tests/test_data_files.py`, `CHANGELOG.md`. No toques nada más: no edites `docs/FUENTES.md`, no cambies `scripts/local/peso_arranque.py` ni `presupuesto_peso.py`, no toques `web/sw.js` (otro ítem lo ocupa), no modifiques `tests/js/` (la vista de mapa lo está usando) y no cambies ningún texto de licencia.

**Criterio de listo.** `python scripts/local/peso_arranque.py` termina en 0 con al menos 1 KB de holgura (≈251 KB o menos) y `python scripts/local/presupuesto_peso.py` termina en 0; `python dev.py check` dice «Todo en orden»; `python dev.py e2e` pasa; `#/calidad` sigue mostrando las mismas filas de licencias que hoy, con los mismos textos, y una prueba lo fija.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

Descartado el 23-10-2026: la premisa venció. El presupuesto de peso ya no está en rojo: el arranque bloqueante pesa 134,3 KB de 180 y las páginas bajo demanda 62,5 KB de 75 (`dev.py check` con DEBT-07, #674).
