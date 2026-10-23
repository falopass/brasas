---
id: AUTO-14
repo: brasas
rama: feat/diagnostico-con-arreglo
modelo: swe-2-high
riesgo: B
archivos: backend/diagnostics.py, backend/routes/diagnostico.py, backend/main.py, web/admin.html, web/js/admin.js, tests/test_diagnostico_api.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que BRASA diga sola qué está fallando y qué hacer: un `GET /api/diagnostico` con el veredicto por fuente y el arreglo sugerido, y una pestaña «Salud» en `/admin` que lo muestre.

**Ítem del backlog.** OPS-01/OPS-02 (monitoreo y prueba de humo de fuentes) y el foco de auto-mejora de esta ronda. Continúa el trabajo de `backend/diagnostics.py` (`failures_24h`, OPS-14) sin cambiar lo que ya publica `/api/status`.

**Qué pasa hoy.** `/api/status` entrega contadores crudos (corridas, fallos, frescura) y nadie los convierte en una frase accionable. `web/admin.html:33-35` tiene solo tres pestañas (Reportes, Registro, Moderadores) y `web/js/admin.js:39-44` cambia entre ellas: quien modera no tiene ninguna pantalla que le diga «GOES lleva 40 minutos sin barrido, revisa el contenedor» o «la clave de FIRMS está cerca del tope». El dueño se entera por GitHub o mirando el mapa, no por el producto.

**Qué hacer.** (1) En `backend/diagnostics.py`, una función nueva `diagnostico(svc)` que recorra las fuentes que ya están en `ingest_runs` y devuelva, por fuente: `id`, `nombre` legible, `estado` en {`bien`, `tarde`, `fallando`, `sin_dato`}, `ultima_ok`, `minutos_desde_ultima_ok`, `fallos_seguidos`, `que_hacer` (texto fijo por tipo de falla, en español neutro, nombrando el secreto o el panel a revisar) y `enlace`. (2) Una ruta `backend/routes/diagnostico.py` con `GET /api/diagnostico`, protegida con `Depends(admin)` (el token de administración, como el resto de `/api/admin/*`), `include_in_schema=False` y solo lectura. (3) Registrar el router en `backend/main.py`. (4) En `/admin`, una pestaña «Salud» con el resumen (cuántas fuentes en rojo y en ámbar) y la tabla: fuente, estado, hace cuánto fue la última corrida buena y el «qué hacer»; reusar `.status-badge` y `.callout` que ya existen, sin CSS nuevo. (5) Una línea en `CHANGELOG.md`.

**Reglas.** Los estados se derivan solo de datos reales de la base (nada inventado); si no hay ninguna corrida, el estado es `sin_dato` y no «bien». Sin datos personales ni tokens en la respuesta. Sin dependencias nuevas y sin `innerHTML` con texto sin escapar (`html`/`raw` de `util.js`).

**Archivos a tocar.** `backend/diagnostics.py`, `backend/routes/diagnostico.py`, `backend/main.py`, `web/admin.html`, `web/js/admin.js`, `tests/test_diagnostico_api.py`, `CHANGELOG.md`. No toques `backend/routes/public.py` (otro ítem lo ocupa), ni `/api/status`, ni el resto de `/api/admin/*`.

**Criterio de listo.** `python dev.py test -k diagnostico` en verde con cuatro casos: todo bien; una fuente con la última corrida buena de hace 3 h (estado `tarde`, con su `que_hacer`); tres fallos seguidos (`fallando`); fuente sin corridas (`sin_dato`). Sin token, la ruta responde 401/403. `python dev.py check` en «Todo en orden» y la pestaña «Salud» se ve en `/admin` con datos de demostración.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
