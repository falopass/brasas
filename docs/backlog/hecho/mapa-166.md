---
id: MAPA-166
repo: brasas
rama: feat/mapa-sin-senal
modelo: swe-2-high
riesgo: M
archivos: web/sw.js, web/js/map.js, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
estado: espera decisión (primero confirmar los términos de OpenFreeMap para precarga de teselas)
---

# MAPA-166 · Tu zona sin señal

**Por qué.** En un incendio grande las redes celulares se saturan. Hoy, sin conexión, el mapa muestra solo los límites de las regiones: no hay calles ni nombres.

**Qué haría.** Con Wi-Fi y la pantalla visible, el service worker precarga las teselas vectoriales (zoom 8 a 13) alrededor de cada lugar guardado, dentro de su radio, con un tope de unos 15 MB por lugar. Se puede borrar desde Privacidad.

**Antes de empezar.** Confirmar por escrito que los términos de OpenFreeMap permiten precargar teselas en el dispositivo, y medir cuánto pesa una zona rural y una urbana.
