---
id: DET-48
repo: brasas
rama: feat/goes19-aodf-humo
modelo: agente-alto
riesgo: B
archivos: backend/providers/smoke.py, backend/services.py, backend/routes/public.py, web/js/views/mapa.js, web/js/views/zona.js, docs/FUENTES.md, tests/
e2e: si
---

# DET-48 · GOES-19 `ABI-L2-AODF` para espesor óptico del humo

## Objetivo

Complementar la máscara binaria de humo `ABI-L2-ADPF` (`Smoke=0/1`) en `backend/providers/smoke.py` con el producto cuantitativo `ABI-L2-AODF` (Espesor Óptico de Aerosoles cada ~10 minutos desde el mismo bucket `noaa-goes19`), para distinguir humo tenue de columnas densas en el mapa y en «Mi zona».

## Contexto

- Hoy `backend/providers/smoke.py` lee únicamente `ABI-L2-ADPF`, por lo que no puede diferenciar una pluma ligera en altura de humo denso sobre una comuna.
- `ABI-L2-AODF` vive en el mismo bucket S3 `https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-AODF/`, usa el mismo formato NetCDF4/HDF5 (`h5py`) y la misma proyección `goes_imager_projection` ya soportada por `smoke.py`, con resolución ~2 km en nadir (~3 km en Chile central) y cobertura diurna.
- Su lectura debe filtrar píxeles de alta/media calidad (`DQF`) y degradar limpiamente a `ABI-L2-ADPF` cuando no haya dato diurno o falle el prefijo `AODF`.

## Archivos

- `backend/providers/smoke.py` (descarga y decodificación de `ABI-L2-AODF` con filtro `DQF` y cuantiles/intensidad por celda)
- `backend/services.py` (persistencia y expiración en el ciclo de humo)
- `backend/routes/public.py` (exposición del atributo de intensidad/AOD en la respuesta de humo sin romper compatibilidad)
- `web/js/views/mapa.js` y `web/js/views/zona.js` (mostrar densidad cualitativa: tenue / denso)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- `smoke.py` lee `ABI-L2-AODF` (diurno) junto a `ABI-L2-ADPF` sin añadir dependencias Python nuevas ni romper el formato existente si `AODF` está vacío o de noche.
- La interfaz muestra en lenguaje dual la diferencia entre humo tenue y columna densa, indicando que es producto diurno satelital GOES-19.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** NOAA GOES-19 `ABI-L2-AODF` (Aerosol Optical Depth Full Disk) vía NOAA Open Data Dissemination.
- **Enlace:** `https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-AODF/` (<https://www.noaa.gov/information-technology/open-data-dissemination>).
- **Licencia:** Dominio público NOAA, gratis y sin clave.
