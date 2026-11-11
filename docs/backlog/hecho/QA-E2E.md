---
id: QA-E2E
repo: brasas
rama: test/e2e-flujos
modelo: swe-2-high
riesgo: B
archivos: scripts/local/e2e_flujos.py, dev.py, docs/DESARROLLO_LOCAL.md, CHANGELOG.md
e2e: si
intento: 0
---

# QA-E2E · Suite e2e de los flujos principales con Playwright

## Objetivo
Una suite e2e chica y estable que recorra los flujos que importan a una persona. Corre contra el servidor de demostración, igual que `scripts/local/browser_checks.py`, que ya revisa errores, CSP, cortes y táctiles por vista: esta suite no repite esos chequeos, prueba **flujos de punta a punta**.

## Flujos (viewport 390×844 táctil, `service_workers="block"` salvo en el 6; cada uno con su propio contexto y su propio suscriptor, y limpieza al final)
1. **Primera visita → «¿Hay fuego cerca de mí?»** con el GPS concedido en Quilpué (-33.075, -71.405, junto al incidente de la demo). Toca `#cerca-btn`; la respuesta nombra el incendio o el calor cercano y trae «Ver en el mapa». Cuenta toques: ≤ 3.
2. **Guardar un lugar:** formulario → nombre → «Usar mi ubicación» → casilla de aluvión (`#pf-aluvion`) marcada → guardar. Aparece la tarjeta en Mi zona con su estado y `GET /api/places` lo devuelve.
3. **Editar y borrar ese lugar:** cambia el nombre, desmarca la casilla de humo y guarda; después borra y confirma. La tarjeta desaparece y la API ya no lo lista.
4. **Compartir con la familia:** desde la tarjeta crea el enlace y abre `#/v/<token>` en otro contexto sin el token del dueño. Se ve el lugar en modo lectura y no hay botones de edición.
5. **Reportar lo que veo:** formulario de reporte → «Humo» → descripción → enviar sin foto. Aparece la confirmación y el reporte queda pendiente de moderación (`/api/reports/mine` dice `no_verificado` y `/api/reports` no lo publica).
6. **Sin conexión:** con el service worker activo carga `/`, espera a que el SW esté `activated`, pone el contexto `offline` y recarga. La app pinta Mi zona con datos guardados, no aparece `#arranque-fallido`, y `/focos.html` y `/web/lite.html` abren sin conexión.

## Reglas
- Esperas por estado del DOM (`wait_for_selector`, `wait_for_function`); nada de `wait_for_timeout` salvo animaciones, con comentario.
- Cada flujo imprime `✓ <flujo>` o `✗ <flujo>: <motivo>`; el script termina con código 1 si alguno falla. Una captura por flujo en `--out` (`data/shots/flujos`).
- Corre 3 veces seguidas contra un servidor de demo recién sembrado y pasa las 3; si un flujo es intermitente se arregla la espera, no se desactiva.
- No agrega dependencias ni scripts en línea; no toca `web/`, `backend/`, `deploy/`, `.github/` ni `browser_checks.py`.

## Criterio de listo
`python dev.py e2e --flujos` existe, la suite pasa 3 corridas seguidas contra la demo y el resultado queda en el PR.
