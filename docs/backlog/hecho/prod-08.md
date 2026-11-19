---
id: PROD-08
repo: brasas
rama: feat/ayudas-incendio
modelo: agente-alto
riesgo: B
archivos: web/ayudas.html, web/js/views/mas.js, web/sw.js, web/sitemap.xml, deploy/cloudflare/src/rutas.ts, docs/PAGINAS.md, docs/FUENTES.md, CHANGELOG.md, tests/
e2e: si
---

# PROD-08 · Guía de ayudas tras el incendio (FIBE y Bono de Recuperación)

## Objetivo

Publicar una guía estática, «Ayudas después de un incendio», accesible desde la vista «Más», que
informe por evento dónde consultar la FIBE y qué beneficios siguen vigentes —sobre todo el Bono de
Recuperación del Estado— enlazando solo a los sitios oficiales. BRASA nunca pide ni guarda datos de
las personas para trámites: la guía solo informa y enlaza.

## Contexto

- Idea 7 del bot de investigación externa, aprobada por el Lead (19-11-2026): tras un incendio, la
  familia afectada no siempre sabe que existe la FIBE ni cómo se paga el Bono; BRASA ya habla de
  incendios y puede ser el puente hacia la ayuda estatal, sin convertirse en un canal de datos
  personales.
- La página sigue el formato de `web/preguntas.html` (mismo `<head>`, el mismo CSS y la misma CSP,
  sin scripts en línea) y entra al precache del service worker como las demás páginas de consulta.
- Cada bloque de beneficio lleva «verificado el <fecha>» y la ficha oficial; si un beneficio deja de
  aparecer vigente en la fuente, se quita de la página.

## Criterio de listo

- «Más» muestra el acceso «Ayudas tras un incendio» y la página abre con y sin conexión.
- La página explica qué es la FIBE y dónde consultarla (mifibe.gob.cl con ClaveÚnica y la
  municipalidad), qué es el Bono de Recuperación (no postulable, una sola vez, por la CuentaRUT de
  BancoEstado de la jefatura de hogar), los montos por evento con su fecha de verificación y los
  canales oficiales (ChileAtiende, Ventanilla Única Social, municipalidad y 800 104 777).
- Incluye la nota fija: BRASA no recoge datos personales para trámites; todo se hace en los sitios
  oficiales.
- CI en verde (`web`, `pytest`, revisión de navegador).

## Fuente y licencia

- **Nombre:** Ministerio de Desarrollo Social y Familia (MDSF) — FIBE, SISE y Ventanilla Única
  Social; ChileAtiende (fichas ciudadanas).
- **Enlaces:** <https://www.mifibe.gob.cl/>, <https://sise.gob.cl/>,
  <https://www.ventanillaunicasocial.gob.cl/ficha/329/ficha-basica-emergencia>,
  <https://www.chileatiende.gob.cl/fichas/121985-bono-de-recuperacion> y
  <https://www.ventanillaunicasocial.gob.cl/ficha/323/bono-recuperacion>.
- **Licencia:** información pública del Estado; se enlaza, no se reproduce. Verificado el 19-11-2026.
