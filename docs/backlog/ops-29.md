---
id: OPS-29
repo: brasas
rama: feat/admin-panel-salud
modelo: swe-2-high
riesgo: B
archivos: web/admin.html, web/js/admin.js, tests/test_admin_salud.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que el panel de administración tenga una pestaña «Salud» que lea `/api/status` y muestre, en una sola pantalla y con un «qué revisar» por problema, el estado de las fuentes, la frescura del dato, los huecos de GOES, el cupo de FIRMS y los respaldos — sin tener que leer un JSON a mano.

**Ítem del backlog.** OPS-14 (resumen de errores de la ingesta en `/api/status`, ya en `main`) y OPS-01 (monitoreo con aviso, ya en `main`). Prioridad 3 de esta ronda: que el propio producto detecte y reporte sus fallas y proponga el arreglo.

**Qué ve hoy el operador y por qué está mal.** `web/admin.html:33-35` solo ofrece tres pestañas —Reportes, Registro y Moderadores— y `web/js/admin.js:58` únicamente consulta `/api/admin/reports`. Todo lo demás que el backend ya publica (`freshness`, `runs`, `failures_24h`, `goes_sweeps`, `firms_quota`, `backup`, `last_cycle`) se consulta a mano con un GET a `/api/status` o se descubre cuando el workflow de monitoreo abre un *issue*. En la práctica, la única persona que mira esto es el dueño, y hoy no tiene una vista: cuando una fuente falla o el respaldo de `work.db` no subió, se entera tarde.

**Qué hacer.**
1. En `web/admin.html`, agregar una pestaña `data-tab="salud"` (mismo patrón `aria-pressed` que las existentes) y una `<section id="salud" hidden>` con: un encabezado, un botón «Actualizar» (`data-refresh`), un párrafo de «última consulta» y contenedores para (a) frescura, (b) fuentes/productos, (c) fallos de 24 h, (d) GOES, (e) cupo FIRMS, (f) respaldos.
2. En `web/js/admin.js`, cargar `/api/status` **sin** `X-Admin-Token` (es un GET público: no lo mezcles con `call()`), renderizar con `textContent` (nada de `innerHTML` con datos del servidor) y marcar cada bloque en rojo/ámbar/verde según: `freshness.stale`, `run.ok === false`, `failures_24h` con `failed > 0`, `goes_gap > 0`, `firms_quota` cerca del tope y `backup.bytes` nulo o con `updated_at` viejo. Cada bloque en problema lleva una línea «Qué revisar» con el enlace a `docs/OPERACION.md` (no edites ese documento) y una acción concreta («revisar el *issue* de monitoreo», «correr la ingesta a mano»).
3. Nada de secretos ni de datos personales en pantalla: solo lo que ya publica `/api/status`. Sin auto-recarga agresiva: un botón y, como máximo, un intervalo de 60 s que se pueda pausar.

**Pruebas (`tests/test_admin_salud.py`, nuevo, `html.parser` de la biblioteca estándar).** Asserts: `web/admin.html` tiene un botón con `data-tab="salud"` y una sección con `id="salud"`; el botón tiene nombre accesible; `web/js/admin.js` menciona `'/api/status'` y no envuelve esa llamada en `call(`; el HTML de la pestaña no contiene `innerHTML` ni `<script>` inline nuevo. Sigue el estilo de `tests/test_accesibilidad_estatica.py`.

**Criterio de listo (verificable).** `python -m pytest tests/test_admin_salud.py -q` en verde; `python dev.py check` en «Todo en orden»; con `python dev.py run --demo`, abrir `/web/admin.html`, entrar con el token de demo y ver la pestaña «Salud» con los datos del demo (frescura, productos y respaldos), y el botón «Actualizar» refrescando la marca de hora.

**Nota de peso (importante).** Hoy `python scripts/local/presupuesto_peso.py` mide **199,8 KB gzip de 200,0**: el margen es de 0,2 KB y ese paso corre dentro de `dev.py check`. No subas el umbral. El margen real lo libera PESO-03 (`perf/preparate-fuera-del-arranque`, en curso). Si tu rama sale de un `main` sin ese merge, entrega el PR igual y anota en el PR la medición exacta: una falla **solo** del presupuesto de peso es previa y tiene dueño, no tuya. Si aun con ese margen no cabe, recorta tus frases y no dupliques literales que ya existen en `web/js/views/*.js`.

**No toques nada más.** No toques `backend/` (todo lo necesario ya está en `/api/status`), ni `docs/OPERACION.md` (lo está tocando otro encargo), ni `web/js/views/calidad.js`. De `CHANGELOG.md`, solo tu línea.

Verifica con /verificar y entrega con /entregar-pr.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
