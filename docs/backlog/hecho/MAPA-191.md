---
id: MAPA-191
repo: brasas
rama: feat/copernicus-emsr859-area-afectada
modelo: agente-alto
riesgo: B
archivos: web/data/cases.json, web/data/cases/penco-lirquen-2026.affected.json, web/js/map.js, web/js/views/casos.js, web/data/licencias.json, docs/FUENTES.md, tests/, CHANGELOG.md
e2e: si
---

# MAPA-191 · Copernicus EMSR859: área quemada cartografiada en el caso Penco–Lirquén 2026

## Objetivo

Agregar al caso histórico `penco-lirquen-2026` la capa de **área quemada según el producto de grading (GRA v2) de la activación Copernicus EMS EMSR859**, cartografiada sobre imagen Spot-6/7 del **25 de enero de 2026** (área afectada 12.780,9 ha según el propio producto), como capa apagada por defecto y claramente separada de la huella térmica satelital (`case-footprint`) y del perímetro oficial CONAF (`case-perimeter`).

## Contexto

- La activación EMSR859 («Wildfires in the Biobio and Nuble Regions, Chile», 21-ene-2026, cerrada) produjo 35 mapas; el producto GRA de la AOI04 Concepción se entregó el 29-ene-2026 (versión 2) con la capa vectorial `observedEventA_v2` (Burnt area) en EPSG:4326.
- Datos descargados una vez desde `https://rapidmapping.emergency.copernicus.eu/backend/EMSR859/AOI04/GRA_PRODUCT/EMSR859_AOI04_GRA_PRODUCT_v2.zip` (paquete público del portal Copernicus EMS Mapping), simplificados (~100 m) a `web/data/cases/penco-lirquen-2026.affected.json` con metadatos del producto (sensor, fecha de adquisición UTC, entrega y superficie).
- Reglas de la casa: nunca presentarlo como frente en vivo ni como perímetro oficial; la fecha del producto y la fuente van visibles; datos oficiales con nombre y enlace.
- Licencia: datos Copernicus abiertos con atribución (© European Union, Copernicus Emergency Management Service).

## Archivos

- `web/data/cases/penco-lirquen-2026.affected.json` (nuevo, capa `affected-area`)
- `web/data/cases.json` (bandera del caso + referencia EMSR859)
- `web/js/map.js` (fuente `case-affected` y capas fill/line)
- `web/js/views/casos.js` (interruptor con fecha y fuente, leyenda, limpieza)
- `web/data/licencias.json`, `docs/FUENTES.md`, `tests/`, `CHANGELOG.md`

## Criterio de listo

En la ficha del caso Penco–Lirquén se puede encender el área quemada de Copernicus EMSR859 con su fecha (25-ene-2026) y fuente visibles, distinta en color de la huella térmica y del perímetro CONAF; el resto de los casos no cambia; CI en verde (pytest, revisión JS y e2e). Revisión `geo-reviewer` antes del merge.
