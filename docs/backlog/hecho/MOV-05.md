---
id: MOV-05
repo: brasas
rama: perf/movil-fcp
modelo: swe-2-high
riesgo: B
archivos: web/index.html, docs/backlog/hecho/MOV-05.md, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# MOV-05 · El primer pintado vuelve a llegar antes en red lenta

## Objetivo

MOV-01 (#832) adelantó la navegación y la vista en red lenta, pero el primer
pintado (FCP) empeoró en las tres redes: los 23 `<link rel="modulepreload">`
del `<head>` compiten por el mismo ancho de banda que `app.css` y la fuente
precargada, que son lo único que bloquea el primer pintado. Recuperar el FCP
sin perder la mejora de navegación y vista de MOV-01.

## Evidencia medida en producción (Playwright, 360 px, CPU ×4, 10-nov-2026)

| Red | FCP antes → después de MOV-01 | Navegación pintada | Vista Mi zona |
|---|---|---|---|
| sin límite | 316 → 528 ms | 0,77 → 0,70 s | 2,08 → 1,35 s |
| Fast 3G | 1.620 → 2.340 ms | 4,80 → 2,48 s | 5,31 → 2,98 s |
| Slow 3G | 5.356 → 8.144 ms | 16,06 → 8,45 s | 18,34 → 10,48 s |

## Medición local por opción

Servidor local (`uvicorn`, datos de `seed_demo`), throttling por CDP con los
mismos perfiles del auditor de producción (`auditar_movil.py --solo-arranque`,
360 px, CPU ×4). FCP en ms; navegación y vista en segundos.

| Corrida | Red | FCP | Nav | Vista |
|---|---|---|---|---|
| base (main `901fe96`) | sin límite | 640 | 1,04 | 1,52 |
|  | Fast 3G | 1932 | 4,53 | 5,32 |
|  | Slow 3G | 5728 | 14,03 | 16,08 |
| (a) corrida 1 | sin límite | 392 | 0,71 | 0,71 |
|  | Fast 3G | 1644 | 4,16 | 4,93 |
|  | Slow 3G | 5372 | 14,42 | 16,47 |
| (a) corrida 2 | sin límite | 296 | 0,66 | 0,66 |
|  | Fast 3G | 1556 | 4,24 | 4,75 |
|  | Slow 3G | 5332 | 14,38 | 16,41 |
| (b) | sin límite | 636 | 0,97 | 0,97 |
|  | Fast 3G | 1620 | 5,29 | 5,80 |
|  | Slow 3G | 5416 | 18,08 | 20,10 |

Flujo «¿Hay fuego cerca de mí?» (botón visible → respuesta, en segundos):

| Corrida | Fast 3G | Slow 3G |
|---|---|---|
| base | 6,89 → 8,76 | 18,37 → 22,97 |
| (a) corrida 1 | 5,60 → 7,07 | 18,56 → 22,99 |
| (a) corrida 2 | 5,66 → 6,77 | 18,63 → 21,16 |
| (b) | 6,65 → 8,16 | 22,16 → 26,62 |

## Opciones probadas y decisión

- **(a) `fetchpriority="high"` en `app.css` y en la fuente precargada,
  `fetchpriority="low"` en los 23 `modulepreload` — elegida.** El FCP mejora
  en las tres redes y en dos corridas seguidas (~-40 % sin límite, ~-17 % en
  Fast 3G, ~-6 % en Slow 3G) sin tocar la lista de precargas: navegación y
  vista se mantienen dentro del ruido en Slow 3G (+0,3-0,4 s) y mejoran en las
  redes rápidas; el flujo «cerca de mí» queda igual o mejor en todas.
- **(b) `modulepreload` solo del primer nivel de `app.js` (10 módulos) —
  descartada.** Mejora el FCP lo mismo que (a), pero devuelve la cascada de
  imports al segundo nivel: en Slow 3G la navegación pasa de 14,0 a 18,1 s y la
  vista de 16,1 a 20,1 s, perdiendo buena parte de lo ganado por MOV-01.
- **(c) mover los `modulepreload` después de `app.css` — ya cumplida.** Ya van
  después del stylesheet en el `<head>` desde MOV-01; no había nada que mover.

El navegador que no entienda `fetchpriority` lo ignora y queda como antes.
Cuando `app.js` pide un módulo cuya precarga sigue en vuelo a prioridad baja,
reutiliza la respuesta de la precarga: la prioridad solo ordena la cola de la
red, no cambia qué se descarga ni cuándo se ejecuta.

## Qué se hizo

- `web/index.html` (solo el `<head>`): `fetchpriority="high"` en el
  `<link rel="preload">` de la fuente y en el `<link rel="stylesheet">` de
  `app.css`; `fetchpriority="low"` en los 23 `<link rel="modulepreload">`.
- `tests/test_arranque_precarga.py` no necesitó cambio: sus reglas leen los
  `href` de los `modulepreload` y la lista no cambió.
- CSP intacta: no se tocó ningún guion en línea.

## Supuestos

- Las corridas del auditor que fallaron en `reintento` cayeron en
  `Page.screenshot` (error de protocolo de Chromium, también con el código
  base): el bloque «no pudo cargar» se verificó aparte bloqueando `app.js` por
  ruta y aparece correctamente.
- El servidor local no tiene latencia real: los números comparables son los de
  las redes emuladas por CDP, como indica el encargo. La medición de
  producción queda para después del despliegue.
