---
id: OFI-35
repo: brasas
rama: feat/sinca-horario-co-pm10
modelo: agente-alto
riesgo: B
archivos: backend/providers/sinca.py, backend/services.py, backend/routes/personal.py, web/js/views/zona.js, web/js/views/calidad.js, docs/FUENTES.md, tests/
e2e: si
---

# OFI-35 · SINCA horario real + `PM10` y `CO` para picos de humo agudo

## Objetivo

Reemplazar la lectura de media móvil de 24 horas en `backend/providers/sinca.py` por lecturas horarias reales (desde el CGI oficial `apub.tsindico2.cgi` o la serie `info.rows` validada) y extraer también `PM10` y monóxido de carbono (`CO`, código `0004`) ya presentes en el JSON `listadomapa2k19`, de modo que «Mi zona» refleje picos agudos de humo durante incendios y los distinga de polvo en suspensión.

## Contexto

- Hoy `backend/providers/sinca.py:130-156` solo toma `tableRow.value` para `PM25` (media móvil de 24 h) y descarta explícitamente `MP10`/`CO`. Durante un incendio, el MP2,5 horario puede superar 150–300 ug/m3 mientras la media móvil de 24 h apenas sube, ocultando el episodio agudo a las personas usuarias (`INV-26`, `atmosfera.md`).
- Debe mantenerse la compatibilidad con `SINCA_PROXY_URL` y el respaldo por snapshot <=12 h en R2, respetando la hora de Chile continental (`America/Santiago`) y marcando claramente si el dato es preliminar/no validado.
- La respuesta formal de licencia por Transparencia ante el Ministerio del Medio Ambiente sigue pendiente (`PASOS_DUENO.md` / `OFI-10`), por lo que la integración mantiene atribución explícita, enlace y degradación segura.

## Archivos

- `backend/providers/sinca.py` (parseo horario + `PM10` y `CO` `0004`, validando unidad y marca horaria)
- `backend/services.py` y `backend/routes/personal.py` (propagación de `aire_medido` con marca horaria)
- `web/js/views/zona.js` y `web/js/views/calidad.js` (mostrar lectura horaria, aviso de dato preliminar y relación humo/polvo cuando exista `CO`/`PM10`)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- `sinca.py` expone la última hora disponible de `PM25`, `PM10` y `CO` (`0004`) con marca temporal UTC correcta y manejo seguro ante estaciones sin alguno de los sensores.
- «Mi zona» muestra la lectura horaria en lugar de la media móvil de 24 h, con nombre de la estación, hora de Chile continental y enlace a SINCA.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Sistema de Información Nacional de Calidad del Aire (SINCA) — Ministerio del Medio Ambiente de Chile.
- **Enlace:** `https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/` y `https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi` (<https://sinca.mma.gob.cl/>).
- **Licencia:** Licencia por confirmar (consulta por Transparencia ante el MMA en <https://mma.gob.cl/> pendiente según `OFI-10` y [`PASOS_DUENO.md`](PASOS_DUENO.md); se integra bajo criterio provisional con atribución y enlace).
