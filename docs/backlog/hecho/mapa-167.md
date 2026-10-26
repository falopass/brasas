---
id: MAPA-167
repo: brasas
rama: feat/buscar-localidad
modelo: swe-2-high
riesgo: M
archivos: web/data/localidades.json (nuevo), web/js/buscador.js, web/data/licencias.json, docs/FUENTES.md, CHANGELOG.md
e2e: si
intento: 0
estado: hecho
---

# MAPA-167 · Buscar localidades, no solo comunas

**Por qué.** En las comunas rurales grandes la gente se ubica por su pueblo, su villa o su sector, no por la comuna. Hoy el buscador solo encuentra las 345 comunas.

**Qué haría.** Un índice estático de localidades (nombre, comuna y coordenadas), cargado en diferido solo al buscar. Al elegir una localidad, el mapa vuela a ella; también sirve para el pin de MAPA-161.

**Antes de empezar.** Elegir la fuente y su licencia:
- Un extracto de OpenStreetMap es una base derivada bajo **ODbL**: va con licencia propia en `licencias.json`, distinta de la CC BY 4.0 de los datos de BRASA.
- Para el INE hay que confirmar los términos de reutilización.
