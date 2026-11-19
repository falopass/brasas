---
id: PROD-07
repo: brasas
rama: feat/quemas-biobio-comuna
modelo: agente-alto
riesgo: B
archivos: backend/routes/paginas_comuna.py, tests/test_pagina_comuna.py, CHANGELOG.md
e2e: no
---

# PROD-07 · Restricciones de quema por comuna en el piloto Biobío

## Objetivo

En las páginas públicas por comuna del piloto Biobío, mostrar el estado del mes en curso del
Calendario de Quemas 2026-2027 de CONAF, siempre con enlace para consultar el calendario y dar el
aviso previo. Fuera del piloto la página no cambia.

## Contexto

- Idea 5 del bot de investigación, aprobada por el Lead (19-11-2026): «restricciones de quema por
  comuna» pilotear en Biobío.
- Fuente oficial: CONAF, «Calendario de Quemas», Región del Bío Bío, resolución N° 1148 del
  30-09-2026, publicado en Las Últimas Noticias el 14-10-2026; PDF verificado el 19-11-2026.
- Reglas duras: el calendario nunca atribuye un foco satelital a una quema autorizada; la
  autorización siempre es de CONAF o del municipio; CONAF puede suspender el uso del fuego.

## Qué se hizo

- `_QUEMAS_GRUPOS`/`_QUEMAS_PILOTO`: las 33 comunas del piloto Biobío por código (Arauco,
  Concepción metropolitano, Florida-Santa Juana, Provincia de Biobío y Los Ángeles), con la matriz
  mensual oct-2026 a sep-2027 y los textos legales de las celdas rojas.
- `_quema_estado` y `_cuerpo_quemas`: sección «Uso del fuego y quemas» en `/comuna/<slug>` con el
  estado del mes (amarillo=restringido, rojo=prohibido, verde=sin restricción adicional), el matiz
  de abril en Los Ángeles (1-14 amarillo, 15-30 rojo, D.S. 4/2019), el aviso de suspensión de
  CONAF, la aclaración de autorización y los enlaces a la página regional, el PDF y «uso del
  fuego» (mismo destino que QUEMA-01). Después de sep-2027 avisa que el calendario venció y manda
  a CONAF sin inventar datos.
- `tests/test_pagina_comuna.py`: estados A/R/V con fecha fija, no piloto sin sección, matiz de
  Los Ángeles, vencimiento y enlaces/redacción que nunca afirma permiso.

## Criterio de listo

- Solo las comunas piloto muestran la sección; el resto queda igual.
- El texto informa el calendario, nunca autoriza ni atribuye focos; incluye suspensión de CONAF,
  autorización CONAF/municipio y enlaces oficiales.
- `pytest tests/test_pagina_comuna.py` y `ruff` en verde; CI del PR en verde.

## Fuente y licencia

- **Nombre:** CONAF, «Calendario de Quemas 2026-2027», Región del Bío Bío (resolución N° 1148, 30-09-2026).
- **Enlaces:** <https://www.conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas/region-del-bio-bio/>
  y <https://www.conafprevencionincendios.cl/wp-content/uploads/Biobio.pdf> (verificados el 19-11-2026).
- **Licencia:** documento público CONAF; se enlaza y se resume el estado, no se reproduce el calendario completo.
