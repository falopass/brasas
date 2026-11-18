---
id: PROD-04
repo: brasas
rama: feat/mensajes-emergencia-mapudungun-rapanui
modelo: agente-alto
riesgo: C
archivos: web/js/views/preparate.js, web/data/, web/sw.js, docs/backlog/PASOS_DUENO.md, tests/
e2e: si
---

# PROD-04 · Mensajes clave de emergencia en mapudungun y rapa nui con audio pregrabado

## Objetivo

Incorporar en la guía de emergencia (`preparate.js`, y eventualmente en paquetes offline `PROD-01`) un conjunto acotado de mensajes clave de prevención y evacuación ante incendios forestales en **mapudungun** y **rapa nui** con audio pregrabado en formato ligero, sujetos obligatoriamente a revisión y validación lingüística de comunidades/hablantes locales antes de publicarse.

## Contexto

- Propuesta de inclusión territorial levantada en `CONSOLIDADO.md` §4 para zonas con alta presencia mapuche (La Araucanía, Biobío, Los Ríos, Los Lagos) y Rapa Nui (en coordinación con cobertura `DET-47`).
- **Bloqueante editorial y comunitario:** bajo ninguna circunstancia deben publicarse traducciones automáticas ni voces sintéticas sin validación explícita de hablantes nativos/organizaciones comunitarias y aprobación de la persona dueña.
- Los audios deben ser cortos, descargables bajo demanda (sin inflar `peso_arranque.py`) y opcionalmente cacheables en `PROD-01`.

## Archivos

- `docs/backlog/PASOS_DUENO.md` (registro de validación comunitaria previa si la persona dueña decide avanzar)
- `web/data/` (metadatos de mensajes validados y créditos de hablantes/colaboradores)
- `web/js/views/preparate.js` (selector de idioma + reproductor accesible con transcripción en español y lengua originaria)
- `web/sw.js` y `tests/`

## Criterio de listo

- Ningún texto ni audio en mapudungun o rapa nui entra en producción sin ficha de validación comunitaria adjunta.
- El reproductor funciona accesible con teclado/lector de pantalla y muestra texto y audio bajo demanda sin aumentar el peso del arranque inicial.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Propuesta de producto de la revisión interna (`CONSOLIDADO.md` §4).
- **Enlace:** `web/js/views/preparate.js` en el repositorio.
- **Licencia:** Licencia por confirmar para los registros de audio y traducciones al momento de acordar la colaboración con las comunidades hablantes (recomendado CC BY 4.0 con atribución acordada).
