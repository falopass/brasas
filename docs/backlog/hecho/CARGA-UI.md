---
id: CARGA-UI
repo: brasas
rama: carga-ui-sin-esperas
modelo: swe-2-high
riesgo: M
archivos: web/js/app.js, web/js/views/calidad.js, deploy/cloudflare/src/cache.ts, deploy/cloudflare/test/cache.test.mjs, tests/js/calidad-carga.test.mjs, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
estado_desde: 2026-11-09T12:00:00
nota:
---

# CARGA-UI · La app y «Calidad» dejan de esperar en serie

## Objetivo
Que la primera vista no espere `/api/config` para montarse y que «Calidad de los datos»
pinte de inmediato con lo que ya tiene, completando por partes en vez de esperar todas
las consultas.

## Qué se hizo
- `/api/config` con 60 s en `EDGE_CACHE_TTL` (`deploy/cloudflare/src/cache.ts`): la
  respuesta es igual para todos (banderas y claves públicas), sin `set-cookie`, y
  `config.version` no se lee en `web/` — la versión que muestra el diagnóstico sale de
  `status.version`.
- El arranque (`web/js/app.js`) guarda la última configuración buena en `storage`: con
  copia monta la vista al instante y pide la fresca en segundo plano; solo la primera
  visita mantiene la espera con reintentos ante 503 y el texto «Conectando con BRASA…».
- «Calidad» (`web/js/views/calidad.js`): el estado de la vista viaja en un objeto
  `vista` y un solo `repintar()` reemplaza las seis copias de `keepPlace`. Al montar
  pinta con `store.status` (o secciones en carga si no hay) y lanza en paralelo
  `api.status(20)`, los extras, licencias, latencias y concordancia; cada respuesta
  actualiza su parte. El aviso parcial con «Reintentar» (FIX-76) se conserva y la
  pantalla de error con teléfonos (FIX-57) solo aparece si no hay ningún estado que
  mostrar.

## Verificación
- `node --check` sobre los archivos editados: verde.
- CI del PR: ruff, pytest, JS, reglas de diseño y e2e — resultado en el cuerpo del PR.
