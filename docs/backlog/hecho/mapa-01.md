---
id: MAPA-01
repo: brasas
rama: feat/mapa-capas-y-leyenda
modelo: swe-2-high
riesgo: B
archivos: web/js/mapa.js, web/css/, tests/js/
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:06:59
nota: PR #354 ya abierto; el ítem quedó pegado en curso con la sesión terminada.
---

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

NOTA DE LA FÁBRICA: Tu PR #354 tiene conflicto con main. Haz `git fetch origin && git rebase origin/main`, resuelve los conflictos, verifica completo y sube con `--force-with-lease`.

# MAPA-01 · el mapa: capas, leyenda y rendimiento

El mapa es la pantalla principal y hoy carga todo junto. Hazlo más legible y más liviano sin cambiar datos.

## Qué hacer

1. **Capas conmutables** (focos, incendios activos, riesgo, aire): un control compacto que prenda y apague
   cada capa, con el estado en la URL (`?capas=focos,riesgo`) para poder compartir la vista.
2. **Leyenda** clara de colores y tamaños, con la fuente y la hora de cada capa.
3. **Rendimiento**: agrupa focos por celda cuando el zoom está lejos (clusters o decimación), y no redibuja
   en cada evento de pan; usa `requestAnimationFrame` o `moveend`. Mide antes/después con el número de
   features dibujadas y el tiempo de render en consola.
4. **Accesibilidad**: el control de capas debe ser operable con teclado y anunciar el estado con ARIA;
   contraste AA en la leyenda.
5. **Tests**: los de `tests/js` que ya cubren el mapa deben seguir verdes; agrega uno para el toggle de capas
   y otro para que la URL refleje las capas activas.

## Criterio de listo

- `python dev.py check` verde y `npm run test` (js) verde.
- Sin cambios en las APIs: todo es cliente.
- Captura o nota en el PR con el antes/después del conteo de features.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
