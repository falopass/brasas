---
id: DET-06
repo: brasas
rama: docs/fuentes-fijas-curadas
modelo: swe-2-high
riesgo: C
archivos: docs/investigacion/INV-16-industria-antorchas.md, CHANGELOG.md
e2e: no
intento: 0
---

## Por qué es delicado (va a decisión de Diego)

`web/data/persistent_hotspots.json` **silencia avisos**: si toda la evidencia de un incidente cae dentro del radio de un punto de la lista, BRASA no envía aviso automático (el punto se sigue mostrando). Un punto mal puesto —o con radio de más— **tapa un incendio real**. Por eso este encargo **no publica coordenadas**: investiga y propone; Diego aprueba punto por punto antes de tocar el JSON de producción.

## Objetivo

Cerrar la investigación DET-06 / INV-16 con una **lista corta y verificada de candidatos** a fuentes fijas de calor (volcanes activos de la red SERNAGEOMIN, refinerías, fundiciones, celulosas con calderas de biomasa y antorchas de gas en Magallanes), cada uno con su coordenada, su radio propuesto, su fuente y su vigencia.

## Ítem

DET-06 (P1, «Lista curada de fuentes fijas, con fuente por punto»): hoy `web/data/persistent_hotspots.json` tiene **solo tres volcanes** (Villarrica, Láscar, Copahue). INV-16 existe como documento; DET-05 aporta la máscara dinámica. La lista curada es lo que falta.

## Evidencia de que está pendiente

- `web/data/persistent_hotspots.json`: `sources` tiene tres entradas, todas `kind: "volcan"` con fuente Smithsonian GVP.
- La nota del mismo archivo fija la regla: «sin `coordinate_source` no se publica un punto», y remite a `docs/investigacion/INV-16-industria-antorchas.md`.
- `docs/investigacion/INV-16-industria-antorchas.md` ya existe; este encargo lo completa con la tabla de candidatos, no lo reescribe.
- `backend/incidents.py:65` lee ese archivo para decidir el silenciamiento.

## Qué hacer (solo investigación y documento)

1. Revisar `docs/investigacion/INV-16-industria-antorchas.md` y agregar una tabla de candidatos con: nombre, tipo (`volcan` / `refineria` / `fundicion` / `celulosa` / `antorcha`), coordenada a 3 decimales, radio propuesto en km y **de dónde sale cada coordenada** (URL de SERNAGEOMIN, del catálogo oficial de la empresa, de OpenStreetMap con su nodo, o de FIRMS SP con la celda y las fechas en que se repite).
2. Para cada candidato, la evidencia de que efectivamente se ve como calor desde el satélite: consulta FIRMS SP o el archivo de persistentes y anota la celda y los días (no basta con que exista la planta).
3. Ordenar por prioridad y marcar explícitamente los que **no** se pudieron verificar (con el motivo). Un candidato sin fuente no entra a la tabla.
4. Al final, una sección «Para aprobar» con la lista mínima que Diego debería autorizar, y el radio más pequeño que cubra la evidencia (el radio grande es el que tapa incendios).
5. **No edites `web/data/persistent_hotspots.json`.** Tampoco `backend/incidents.py`.

## Archivos a tocar, y no toques nada más

`docs/investigacion/INV-16-industria-antorchas.md`, `CHANGELOG.md`.

**No toques** `web/data/persistent_hotspots.json` (decisión de Diego), ni `backend/incidents.py`, ni `tests/test_data_files.py`, ni `web/data/*.json`.

## Criterio de listo (verificable)

- La tabla tiene al menos 8 candidatos, cada uno con coordenada, radio y fuente enlazada; los no verificados están en una sección aparte con el motivo.
- Ningún candidato aparece sin `coordenada` y `fuente` a la vez (la regla del archivo).
- Cada fila que se propone para publicar tiene, además, la evidencia satelital (celda y fechas) o la nota de que no se pudo comprobar.
- `python dev.py check` verde (son documentos: no debe cambiar nada del código).
- `CHANGELOG.md`: una línea en «Sin desplegar → Técnico» que diga que la investigación quedó documentada y que la publicación queda a la espera de aprobación.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
