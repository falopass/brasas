---
id: PROD-05
repo: brasas
rama: feat/plan-evacuacion-municipal
modelo: agente-alto
riesgo: B
archivos: web/js/municipios.js, web/js/views/zona.js, CHANGELOG.md, tests/
e2e: si
---

# PROD-05 · Plan de evacuación municipal enlazado desde «Mi zona»

## Objetivo

Enlazar desde «Mi zona» el plan de evacuación por sector que publica el municipio, empezando por el
[plan comunal de Quintero](https://www.muniquintero.cl/wp-content/uploads/2026/10/PLAN-COMUNAL-VARIABLE-INCENDIOS-FORESTALES-EDICION-AGOSTO-2026-CON-DECRETO-3.pdf)
(identifica vías para Loncura y otros sectores), siempre presentado como material de preparación:
nunca como ruta segura en tiempo real ni como sustituto de las órdenes de SENAPRED y del SAE.

## Contexto

- Oportunidad 1 del bot de investigación externa (19-11-2026): ya existe una fuente municipal
  específica para incendios en Quintero y no requiere integrar otro servicio; el #188 solo investigó fuentes.
- BRASA ya tiene puntos de OpenStreetMap y plan familiar, pero no un plano municipal por incendio.
- Módulo puro `web/js/municipios.js` con el recurso por código de comuna (piloto: 5107 Quintero) y
  fecha de consulta; la vista `zona.js` muestra una tarjeta con el enlace y la aclaración.

## Criterio de listo

- Quien tenga un lugar guardado en Quintero ve en «Mi zona» el enlace al plan municipal con su
  entidad y la aclaración de que no reemplaza a SENAPRED/SAE; el resto de las comunas no ve nada.
- El enlace abre el PDF en una pestaña nueva (`rel="noopener"`), sin scripts en línea (CSP).
- CI en verde (`web`, `pytest`, revisión de navegador).

## Fuente y licencia

- **Nombre:** Municipalidad de Quintero, «Plan comunal de variable incendios forestales», edición agosto 2026 (con decreto).
- **Enlace:** <https://www.muniquintero.cl/wp-content/uploads/2026/10/PLAN-COMUNAL-VARIABLE-INCENDIOS-FORESTALES-EDICION-AGOSTO-2026-CON-DECRETO-3.pdf> (verificado con GET el 19-11-2026: 200).
- **Licencia:** documento público municipal; se enlaza, no se reproduce.
