---
id: OFI-37
repo: brasas
rama: feat/agromet-inia-estaciones
modelo: agente-alto
riesgo: B
archivos: backend/providers/agromet.py, backend/services.py, backend/config.py, backend/routes/personal.py, web/js/views/zona.js, web/js/views/calidad.js, docs/FUENTES.md, tests/
e2e: no
---

# OFI-37 · Estaciones rurales Agromet INIA (`api/v4`)

## Objetivo

Integrar la Red Agrometeorológica Nacional (Agromet INIA) mediante `backend/providers/agromet.py` como fuente de observaciones en terreno (temperatura, humedad relativa, viento, precipitación y radiación/$ET_0$) para cubrir las zonas rurales, valles y secano agrícola/forestal donde ni DMC (~134 estaciones) ni SINCA tienen cobertura cercana.

## Contexto

- El mayor vacío observacional de BRASA hoy es rural (O'Higgins, Maule, Ñuble, Biobío, Araucanía). Agromet INIA opera cientos de estaciones automáticas con actualización cada 15–60 minutos.
- **Dependencia externa:** requiere una clave gratuita (`AGROMET_API_KEY`) que debe solicitar y cargar la persona dueña en los secretos del Worker / GitHub (registrado en [`PASOS_DUENO.md`](PASOS_DUENO.md)). Si la clave no está configurada o los términos no permiten redistribución pública, el proveedor permanece deshabilitado sin afectar el ciclo.
- Debe seguir el patrón de `dmc_stations.py`: caché compartida de 15–30 minutos, nunca consultar por visita individual, y prioridad de estación más cercana en «Mi zona» (o respaldo cuando DMC quede a >25 km).

## Archivos

- `backend/providers/agromet.py` (cliente `api/v4` con timeout, caché y normalización a UTC y unidades métricas)
- `backend/config.py` (lectura opcional de `AGROMET_API_KEY` desde entorno)
- `backend/services.py` y `backend/routes/personal.py` (selección entre DMC y Agromet según cercanía y frescura)
- `web/js/views/zona.js` y `web/js/views/calidad.js` (atribución «estación Agromet INIA a X km» con enlace)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Sin `AGROMET_API_KEY` el sistema opera exactamente igual que hoy, sin errores en `/api/status`.
- Con la clave configurada, las lecturas rurales alimentan «Mi zona» y el cruce de lluvia medida con atribución explícita a INIA, enlace oficial y marca horaria.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** Instituto de Investigaciones Agropecuarias (INIA) — Red Agrometeorológica Nacional (Agromet).
- **Enlace:** `https://agromet.inia.cl/api/v4/` (<https://www.agromet.cl/> y <https://agrometeorologia.cl/>).
- **Licencia:** Licencia por confirmar al solicitar la API key gratuita en <https://www.agromet.cl/> (exige atribución a INIA y prohíbe reventa directa; verificar términos de redistribución en aplicación web pública antes de activar en producción).
