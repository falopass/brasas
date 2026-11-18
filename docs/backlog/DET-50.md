---
id: DET-50
repo: brasas
rama: docs/vigilancia-inpe-queimadas-firesat
modelo: agente-alto
riesgo: C
archivos: docs/investigacion/, docs/FUENTES.md, backend/providers/
e2e: no
---

# DET-50 · Vigilancia y evaluación de fuentes futuras: INPE Queimadas y FireSat

## Objetivo

Evaluar formalmente e implementar cuando corresponda (o mantener en vigilancia documentada) dos fuentes complementarias de detección de calor/incendios señaladas en `CONSOLIDADO.md` y `atmosfera.md`: el catálogo abierto **INPE Programa Queimadas** (América del Sur) como posible respaldo regional y cruce histórico, y **FireSat** (Earth Fire Alliance / Muon Space) previsto hacia ~2027.

## Contexto

- **INPE Queimadas** (`terrabrasilis.dpi.inpe.br/queimadas/`): publica focos de Sudamérica incluyendo Chile a partir de NOAA-20/21, S-NPP, Aqua/Terra, MetOp y GOES; sirve como respaldo regional si FIRMS cae, pero su licencia indicada como **CC BY-SA** obliga a revisar compatibilidad *share-alike* con los endpoints abiertos de BRASA antes de mezclarla en `/api/incidents` o `/api/opendata/`.
- **FireSat**: constelación dedicada de alta resolución (~5 m en infrarrojo, pensada para detectar focos nacientes pequeños), sin acceso operativo abierto disponible aún (~2027).

## Archivos

- `docs/investigacion/` (ficha técnica de compatibilidad CC BY-SA para INPE Queimadas y seguimiento de acceso público de FireSat)
- `docs/FUENTES.md` (registro en vigilancia o integrado si se aprueba compatibilidad de INPE)
- `backend/providers/` (solo si la revisión legal/técnica aprueba el respaldo INPE aislado sin contaminar licencias)

## Criterio de listo

- Queda documentada la evaluación de compatibilidad de licencia `CC BY-SA` de INPE Queimadas frente a los endpoints CC BY 4.0 de BRASA antes de ingerir datos en producción.
- FireSat queda con ficha de criterio de activación futura (endpoint abierto, latencia, cobertura sobre Chile y licencia verificada).
- CI en verde.

## Fuente y licencia

- **Nombre:** INPE Programa Queimadas (Brasil / Sudamérica) y FireSat (Earth Fire Alliance).
- **Enlace:** <https://terrabrasilis.dpi.inpe.br/queimadas/> · <https://www.earthfirealliance.org/>.
- **Licencia:** Para INPE Queimadas, **licencia por confirmar** (verificar términos exactos **CC BY-SA** y atribución en <https://terrabrasilis.dpi.inpe.br/queimadas/>); para FireSat, **licencia por confirmar** en <https://www.earthfirealliance.org/> (constelación futura en despliegue).
