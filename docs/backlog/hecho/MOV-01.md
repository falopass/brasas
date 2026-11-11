---
id: MOV-01
repo: brasas
rama: feat/movil-arranque
modelo: swe-2-high
riesgo: M
archivos: web/index.html, web/js/app.js, web/css/app.css, deploy/cloudflare/src/index.ts, tests/test_arranque_precarga.py, tests/test_portada_arranque.py, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
estado_desde: 2026-11-10T12:00:00
nota:
---

# MOV-01 · Arranque móvil en red lenta sin pantalla de fallo

## Objetivo

Que en Slow 3G la portada nunca muestre «BRASA no pudo cargar en este teléfono»
mientras la app sí está cargando, y que la navegación y «Mi zona» pinten antes
que hoy.

## Evidencia medida en producción (Playwright, 360 px, CPU ×4, 10-nov-2026)

| Red | Primer pintado (FCP) | Navegación pintada | Vista Mi zona | Botón «¿Hay fuego cerca de mí?» |
|---|---|---|---|---|
| sin límite | 0,3 s | 0,8 s | 2,1 s | 4,2 s |
| Fast 3G | 1,6 s | 4,8 s | 5,3 s | 5,9 s |
| Slow 3G | 5,4 s | **16,1 s** | 18,3 s | 20,5 s |

El vigilante PORTADA-02 mostraba la pantalla de fallo a los 15 s: en Slow 3G la
navegación pintaba a los 16 s, con 1-3 s de margen. Un teléfono algo más lento
veía «BRASA no pudo cargar» aunque la app sí estaba cargando.

Causas medidas: (1) cascada de módulos ES (4-5 niveles × ~2 s de latencia);
(2) `maplibre-gl.js` (~1 MB) competía por el ancho de banda del primer pintado;
(3) `maplibre-gl.css` bloqueaba el render en el `<head>` sin que Mi zona lo
necesitara.

## Qué se hizo

- `web/index.html`: un `<link rel="modulepreload">` por cada módulo del grafo
  estático de `app.js` (la lista la vigila `tests/test_arranque_precarga.py`):
  los 23 módulos se descubren en paralelo en vez de en cascada.
- `web/js/app.js`: en `mi-zona` el motor del mapa se pide cuando el navegador
  queda libre tras el primer pintado (`ensureMapTrasPintar`, sin esperar a que
  `mount()` resuelva sus consultas); con ahorro de datos o red `slow-2g`/`2g`/`3g`
  espera además a que la persona toque el mapa o a que pasen ~8 s. Las vistas de
  mapa (`MAP_VIEWS`) lo piden al entrar, como antes, y el manejador de
  `#pf-map`/`[data-act="ver"]`/`[data-alert-lat]` no cambió.
- `maplibre-gl.css` salió del `<head>`: lo inyecta `ensureMap()` junto al motor.
- Vigilante honesto: falla real (error del `<script type="module">` en captura,
  o `window.onerror` antes de pintar) muestra la salida de emergencia de
  inmediato; solo lento muestra a los 15 s el aviso discreto «Tu conexión está
  lenta. BRASA sigue cargando…» (`#arranque-lento`, reglas `/* MOV-01 */` en
  `app.css`), que se oculta solo al pintar; «no pudo cargar» queda para falla
  real o para los 45 s. «Reintentar» borra las cachés `brasa-*` de versión
  (conserva `brasa-push-pending`, `brasa-badge`, `brasa-share`, `brasa-tiles`
  y las `*-api` con los datos de respaldo) y recarga; el registro del worker
  —y con él la suscripción de avisos— se mantiene.
- Atajo `?cerca=1` (lo usará MOV-03 desde el `manifest`): entrar por
  `#/mi-zona?cerca=1` abre «¿Hay fuego cerca de ti?» tras montar la vista, una
  sola vez; el parámetro se limpia con `history.replaceState`.
- CSP: hash del guion en línea recalculado en `deploy/cloudflare/src/index.ts`
  (`CSP` y `CSP_EVAL`).

## Supuestos

- La verdad de «pintó» sigue siendo `#view` o `#nav` con hijos (misma prueba
  que usaba PORTADA-02).
- `navigator.connection` no existe en Firefox/Safari: ahí `ensureMapTrasPintar`
  cae al comportamiento anterior (`requestIdleCallback`), que es lo correcto.
- Un `window.onerror` antes del primer pintado se trata como falla real aunque
  no sea fatal: en 45 s el bloque habría salido igual.
