---
id: PROD-06
repo: brasas
rama: feat/incendios-hoy-comuna
modelo: agente-alto
riesgo: B
archivos: backend/routes/paginas_comuna.py, tests/test_pagina_comuna.py, CHANGELOG.md
e2e: no
---

# PROD-06 · «¿Hay incendios hoy?» en las páginas por comuna

## Objetivo

Que la página comunal indexable (`/comuna/<slug>`, SEO-05) responda también si hay incendios hoy
en la comuna: los incendios que informa CONAF (con estado y fecha) y, aparte, las señales de
calor que vio el satélite hoy, cada bloque con su hora de actualización. Piloto de búsqueda:
Concepción, Penco y Valparaíso; la implementación es genérica para todas las comunas, con estados
vacíos honestos.

## Contexto

- Oportunidad 4 del bot de investigación externa (19-11-2026): Autocompletar Chile devuelve
  «incendio concepción hoy», «incendio penco hoy» y «mapa incendios forestales chile»; el #702
  hizo indexable el pronóstico por comuna, no un resumen de incidentes activos.
- BRASA ya tiene los datos: `official_fires` (CONAF, con estado oficial) e `incidents`
  (con `comuna_code`, estado y `last_seen_at`).
- La página es pública y la pegan los crawlers: el bloque va con caché de 5 min por comuna.

## Qué se hizo

- `_incendios_comuna`: bloque `conaf` (incendios no extinguidos de los últimos 30 días, filtro
  geográfico por bbox + `territory().locate`, tope 10 en la lista y total real) y bloque
  `satelite` (conteo de incidentes vivos con señal desde las 00:00 de Chile, sin fuentes fijas).
- `_cuerpo_incendios`: sección «Incendios en <comuna>» con la lista de CONAF, la línea satelital
  («calor, no incendio confirmado») y la marca de actualización de cada fuente; el vacío se
  explica («no hay dato»), nunca como «no hay fuego».
- Todo el contenido dinámico escapado; sin scripts en línea (CSP); estilos propios de la página.

## Criterio de listo

- `/comuna/concepcion` muestra el incendio de CONAF sembrado y la señal satelital del día, y una
  comuna sin datos dice honestamente que no hay información.
- Los nombres de incendios se escapan; `tests/test_pagina_comuna.py` cubre los tres casos.
- CI en verde.
