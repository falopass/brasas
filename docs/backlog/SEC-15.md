---
id: SEC-15
repo: brasas
rama: sec/csp-dominios-explicitos
modelo: agente-alto
riesgo: A
archivos: backend/security.py, deploy/cloudflare/src/index.ts, tests/test_security.py, docs/FUENTES.md
e2e: si
---

# SEC-15 · Restringir `img-src` y `connect-src` de la CSP a una lista explícita de dominios

## Objetivo

Eliminar los comodines abiertos `https:` en `img-src` y `connect-src` dentro de la Política de Seguridad de Contenidos (CSP), sustituyéndolos por una lista explícita y mínima de los orígenes externos realmente consumidos por el navegador, manteniendo paridad exacta entre `backend/security.py` y el Worker de Cloudflare (`deploy/cloudflare/src/index.ts`).

## Contexto

- Hoy `backend/security.py:54,56` y `deploy/cloudflare/src/index.ts:150-151` declaran `img-src 'self' data: blob: https:` y `connect-src 'self' https:`, lo que permite exfiltración o carga de imágenes/peticiones hacia cualquier dominio HTTPS arbitrario.
- `tests/test_security.py` exige que ambas políticas (incluidos los hashes de scripts en línea) sean idénticas byte a byte.
- La lista debe cubrir todas las fuentes directas del cliente vigentes al momento de aplicar el cambio (por ejemplo: OpenFreeMap `tiles.openfreemap.org`, EOX `tiles.maps.eox.at`, OpenTopoMap `*.tile.opentopomap.org`, Mapterhorn `tiles.mapterhorn.com`, jsDelivr `cdn.jsdelivr.net`, Cesium ion si aplica `*.cesium.com` / `api.cesium.com` / `assets.ion.cesium.com`, Turnstile `challenges.cloudflare.com`, más los orígenes cliente de capas ya integradas como GWIS `maps.effis.emergency.copernicus.eu` o NASA GIBS `gibs.earthdata.nasa.gov` si están activos en `main`).

## Archivos

- `backend/security.py`
- `deploy/cloudflare/src/index.ts`
- `tests/test_security.py` (verificar paridad y ausencia de `https:` genérico en `img-src`/`connect-src`)

## Criterio de listo

- Ni `img-src` ni `connect-src` contienen `https:` genérico.
- `backend/security.py` y `deploy/cloudflare/src/index.ts` generan exactamente la misma cabecera CSP (confirmado por `tests/test_security.py`).
- `python dev.py e2e` pasa sin errores de CSP en consola en todas las vistas (incluidos mapa 2D, capas activas y vista 3D).

## Fuente y licencia

- **Nombre:** Revisión de seguridad interna (`CONSOLIDADO.md`, `mapa.md`) y especificación W3C Content Security Policy Level 3.
- **Enlace:** <https://www.w3.org/TR/CSP3/> y `backend/security.py` en el repositorio.
- **Licencia:** N/A (configuración propia del proyecto).
