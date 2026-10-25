---
id: MAPA-156
repo: brasas
rama: feat/avance-por-hora
modelo: swe-2-high
riesgo: B
archivos: web/js/views/incendio.js, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-156 · Avance por hora en la ficha del incendio

**Por qué.** La ficha ya trae «Cómo ha ido cambiando · Reproducción hora a hora», pero hay que darle play para entender hacia dónde avanzó. Una sola imagen estática con las horas apiladas lo dice de inmediato.

**Qué hacer.**
1. En el mapa de la ficha, bandas de la huella por hora: la huella acumulada de cada `frame` de la línea de tiempo (`build_timeline` en `backend/cases.py:152`, que ya entrega huellas acumuladas por hora), de la más antigua (tenue) a la más reciente (intensa), con una leyenda corta «más intenso = más reciente».
2. Una flecha con la dirección en que se desplazó la huella entre la primera y la última hora con dato (centroide a centroide), rotulada «dirección observada, estimación». Si el desplazamiento es menor que el tamaño de un píxel GOES (~2 km), no se dibuja la flecha.
3. Las bandas se pueden apagar y no reemplazan la reproducción que ya existe.
4. No cambies el backend: es trabajo de frontend con los datos que ya llegan. Si falta un dato, la banda o la flecha simplemente no aparece.

**Archivos.** Solo `web/js/views/incendio.js` y `CHANGELOG.md`. Usa clases CSS que ya existan; `web/css/app.css` lo tiene otro PR en esta ola.

**Criterio de listo.** En la captura `incendio_*-390.png` del CI se ven las bandas y la flecha (si el demo se desplaza lo suficiente); el CI pasa.
