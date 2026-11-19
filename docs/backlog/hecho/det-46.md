---
id: DET-46
repo: brasas
rama: feat/firms-noaa21-sp
modelo: agente-alto
riesgo: B
archivos: backend/providers/firms.py, web/data/cases.json, docs/FUENTES.md, tests/
e2e: no
cubierto_por: "#896"
---

> **Estado al 19-11-2026: cubierto por el PR [#896](https://github.com/falopass/brasas/pull/896)** (`fix(ingesta)`, abierto, CI en verde, pendiente de aprobación de Sovran). #896 agrega `PRODUCTS["VIIRS_NOAA21_SP"]` con `min_date: 2024-01-17`, lo suma a `/api/explore`, a los casos `penco-lirquen-2026` y `vina-del-mar-2024` de `web/data/cases.json` y a `docs/FUENTES.md`, con pruebas en `tests/test_firms.py`. Si #896 se cierra sin mergear, este encargo vuelve a la raíz.
>
> Resto pendiente (anotado en [OPS-30](../OPS-30.md)): la caché polar `case-firms:{case_id}` no incluye las fuentes en la clave, así que los casos que ya tenían detecciones cargadas no muestran NOAA-21 hasta vencer la caché (comentario de Devin Review en #896).

# DET-46 · Archivo histórico FIRMS: incorporar `VIIRS_NOAA21_SP` para casos 2024+

## Objetivo

Agregar el producto de archivo científico `VIIRS_NOAA21_SP` en `backend/providers/firms.py` y en los casos históricos recientes de `web/data/cases.json` (como respaldo y continuidad tras el retiro de Suomi NPP `VIIRS_SNPP_SP` el 2 de noviembre de 2026).

## Contexto

- `PRODUCTS` en `backend/providers/firms.py` ya tiene `VIIRS_NOAA21_NRT` en vivo y `VIIRS_SNPP_SP` con `max_date = "2026-11-02"`, pero aún no registra `VIIRS_NOAA21_SP` para el archivo científico (`SP`).
- Para casos históricos recientes o posteriores al retiro de S-NPP, contar con `VIIRS_NOAA21_SP` asegura dos satélites VIIRS en archivo científico junto a `VIIRS_NOAA20_SP`.
- Nota de alcance: el retiro de `LANDSAT_NRT` del ciclo en vivo lo resuelve otro PR en curso; este encargo no modifica `LANDSAT_NRT`.

## Archivos

- `backend/providers/firms.py` (entrada `VIIRS_NOAA21_SP` en `PRODUCTS` con `min_date` verificada contra `data_availability`)
- `web/data/cases.json` (sumar `VIIRS_NOAA21_SP` en los casos cuyo rango de fechas esté cubierto)
- `docs/FUENTES.md`
- `tests/` (verificar `sources_for` con `VIIRS_NOAA21_SP`)

## Criterio de listo

- `PRODUCTS["VIIRS_NOAA21_SP"]` está registrado con sensor `VIIRS`, satélite `NOAA-21`, resolución `375` m y `min_date` verificada en FIRMS.
- `sources_for` incluye `VIIRS_NOAA21_SP` cuando la ventana del caso entra en su rango.
- `tests/test_data_files.py` y las pruebas de FIRMS pasan en CI.

## Fuente y licencia

- **Nombre:** NASA FIRMS (Fire Information for Resource Management System) — archivo científico VIIRS NOAA-21.
- **Enlace:** `https://firms.modaps.eosdis.nasa.gov/api/` (<https://www.earthdata.nasa.gov/data/tools/firms>).
- **Licencia:** Datos abiertos / dominio público NASA EOSDIS con atribución (<https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy>).
