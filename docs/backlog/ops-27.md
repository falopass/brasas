---
id: OPS-27
repo: brasas
rama: feat/autodiagnostico-cara-publica
modelo: swe-2-high
riesgo: A
archivos: .github/scripts/autodiagnostico.py, .github/workflows/autodiagnostico.yml, tests/test_autodiagnostico.py, docs/OPERACION.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# OPS-27 · Autodiagnóstico de la cara pública: 5xx, páginas lentas y enlaces roto

**Objetivo.** Que el propio proyecto revise cada pocas horas sus páginas y endpoints públicos, detecte errores 5xx, respuestas lentas y enlaces internos roto, y abra un issue con el hallazgo y con qué revisar —sin depender de que alguien mire.

**Ítem.** Hoy el monitoreo cubre solo la ingesta. `.github/scripts/monitoreo.py` (líneas 6-20 de su docstring) hace una única sonda a `/api/status?history=3`; `fuentes-salud.yml` revisa fuentes de terceros. **Ningún workflow pide las páginas del producto**: si `/web/datos.html` empieza a devolver 500 o `/#/mapa` tarda 8 segundos, nadie se entera hasta que lo cuenta un usuario. Es la mitad que falta del pedido de auto-mejora.

**Evidencia.**
- `.github/workflows/monitoreo.yml`: la sonda es `python .github/scripts/monitoreo.py`, que solo consulta `/api/status`.
- `web/js/views/calidad.js` (encabezado y `summary`) informa el estado de las **fuentes**, no el del propio sitio: no mide latencia ni códigos de las páginas.
- `web/sitemap.xml` lista 4 URLs públicas; nadie comprueba que respondan 200 ni que sus enlaces internos existan.

**Archivos a tocar.** `.github/scripts/autodiagnostico.py` (nuevo), `.github/workflows/autodiagnostico.yml` (nuevo), `tests/test_autodiagnostico.py` (nuevo), `docs/OPERACION.md`, `CHANGELOG.md`. **No toques nada más**: no toques `.github/scripts/monitoreo.py`, `.github/scripts/fuentes_salud.py`, los otros workflows, `deploy/` ni `web/sw.js`.

**Cómo hacerlo.**
1. Script con la forma de `monitoreo.py`: `--base-url` (por defecto producción), `--payload <json>` para correr sin red con respuestas grabadas, y salida 0/1. Revisa: `/`, `/web/datos.html`, `/web/preguntas.html`, `/web/respuesta.html`, `/web/lista.html`, `/web/plan.html`, `/api/status`, `/api/opendata`, `/api/observations?hours=1` y cada `<loc>` del sitemap. Para cada uno: código HTTP, tiempo total y tamaño. **Umbrales explícitos**: falla con 5xx o con más de 3,0 s en una página y más de 1,5 s en un endpoint JSON. Además, extrae los `href` internos de las páginas estáticas (`/`, `/web/…`, `/#/…`) y reporta los que den 404.
2. Con hallazgos, escribe `alerta.md` con una tabla (URL, qué falló, segundos) y una sección «qué revisar» que apunte a la sección correspondiente de `docs/OPERACION.md`; deja `alerta=true` y `titulo` en `GITHUB_OUTPUT` como hace `monitoreo.py`.
3. Workflow `autodiagnostico.yml`: `schedule` cada 6 horas (`cron: "17 */6 * * *"`), `workflow_dispatch`, `concurrency` con grupo propio, `permissions: contents: read` e `issues: write`, y apertura de issue con etiqueta `autodiagnostico` reutilizando el patrón de `monitoreo.yml` (si ya hay uno abierto, no crea otro; comenta el nuevo).
4. En `docs/OPERACION.md` agrega una sección corta al final (después de la §9) que explique qué mide, los umbrales y cómo se corre a mano.

**Caso de prueba.** `tests/test_autodiagnostico.py` carga el script con `importlib` (mismo patrón que `tests/test_fuentes_salud.py`) y **sin red**: un payload con una página 500 produce veredicto; una página de 4,1 s produce «lenta»; un `href` que responde 404 aparece listado; todo en 200 y bajo el umbral no produce alerta. Además, comprueba que el workflow contiene el cron, el nombre del script y los permisos de issues.

**Criterio de listo (medible).**
1. `python dev.py test -k autodiagnostico` en verde.
2. `python dev.py check` termina en «Todo en orden».
3. El script corre con `--payload` y sale 1 cuando hay un 500 simulado, 0 cuando todo está bien.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
