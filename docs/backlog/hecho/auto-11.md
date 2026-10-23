---
id: AUTO-11
repo: brasas
rama: feat/calidad-autochequeo
modelo: swe-2-high
riesgo: B
archivos: web/js/views/calidad.js, web/js/autochequeo.js, tests/js/autochequeo.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# AUTO-11 · Un botón «Revisar ahora» en #/calidad que prueba lo que el vecino usa

## Objetivo
Que la página de calidad no sólo cuente el estado de las fuentes de ingesta, sino que compruebe desde el navegador las páginas y los GET que el vecino realmente abre, diga cuánto tardaron y, si algo falla, diga qué hacer.

## Ítem del backlog
Foco del dueño (3) auto-mejora: «páginas lentas, errores 5xx, enlaces rotos… y que proponga el arreglo».

## Qué pasa hoy (verificado en main 3ceae01)
- `web/js/views/calidad.js:1-5` declara su alcance: estado de las fuentes, barridos de GOES, incidentes por estado, opinión sobre los avisos y licencias. `:83-104` pinta la tabla de corridas de ingesta.
- No hay ninguna comprobación de las nueve páginas de `web/` ni de los GET que alimentan la portada: si `/web/lista.html` devuelve 500 o `/api/incidents` tarda 4 s, la página de calidad sigue mostrando «al día» porque sólo mira la ingesta. La persona dueña se entera por el issue de OPS-01 o no se entera.
- `web/js/views/calidad.js` no está tomado por ningún PR abierto; `web/sw.js` sí: no lo toques.

## Solución pedida
1. `web/js/autochequeo.js` (nuevo, puro, sin DOM): 
   - `TARGETS`: las nueve páginas (`/web/index.html`, `lite.html`, `lista.html`, `plan.html`, `preguntas.html`, `datos.html`, `respuesta.html`, `pantalla.html`, `admin.html`) y seis GET clave (`/api/status`, `/api/incidents`, `/api/observations`, `/api/risk`, `/api/opendata`, `/api/panorama`);
   - `run(fetchImpl, nowFn)` que pide cada objetivo con `AbortSignal.timeout(8000)`, mida ms y devuelva `{target, status, ms, ok, error}`;
   - `summarize(results)` → `{total, ok, lentos, fallidos, peor}` con «lento» = más de 2.500 ms;
   - `advice(res)` → una frase por caso: 5xx «el servidor está fallando en esta ruta», timeout «tu conexión o el servidor no respondieron: prueba el modo liviano», lento «tarda demasiado: revísalo antes de la temporada», ok «responde bien».
2. En `calidad.js`: bloque «Chequeo del producto» con el botón «Revisar ahora», la tabla de resultados (objetivo, ms, estado) y el consejo, con `aria-live="polite"` para anunciar el resumen. Nada de dependencias nuevas ni de `innerHTML` con datos sin escapar (`html`/`raw` de `util.js`).
3. `tests/js/index.js` es un archivo compartido: agrega el `import './autochequeo.test.mjs';` ahí.

## Criterio de listo (verificable)
`tests/js/autochequeo.test.mjs` cubre: `summarize` con todo ok, con un 500 y con un lento; `advice` para 200, 500, timeout y lento; y que `TARGETS` incluya las nueve páginas. `node --test tests/js` en verde y `python dev.py check` en verde. En e2e: entrar a `#/calidad`, pulsar «Revisar ahora» y ver las filas con su estado. Actualiza `CHANGELOG.md`.

No toques nada más: ni `sw.js`, ni `api.js`, ni `app.js`, ni el backend.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
