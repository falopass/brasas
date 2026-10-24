---
id: RISK-07
repo: brasas
rama: feat/viento-animado
modelo: fusion-claude-opus-5-5-high-sidekick-swe-2-high
riesgo: B
archivos: backend/windgrid.py, backend/services.py, backend/routes/public.py, web/js/map.js, web/js/views/mapa.js, tests/test_windgrid.py
e2e: si
intento: 0
estado_desde: 2026-10-20T02:40:00
---

# RISK-07 · Viento animado en el mapa (partículas)

**Objetivo (una frase):** capa de viento animado (partículas) en el mapa, alimentada por una grilla de Open-Meteo precalculada en el backend y servida como dato compacto, sin llamadas a Open-Meteo por visita.

**Ítem del backlog:** RISK-07 (P2 · L), docs/BACKLOG_MAESTRO.md:298: «Grilla de 0,25° de Open-Meteo precalculada cada hora en el backend y servida como binario compacto; capa WebGL en MapLibre».

**Evidencia de que falta:**
- `web/js/map.js`: no existe ninguna capa ni fuente de viento (no hay partículas, ni `fill-pattern`, ni source `wind`); `web/js/views/mapa.js` no tiene interruptor «Viento».
- `backend/`: no existe módulo de viento (grep `windgrid` vacío). El viento solo se pide de a un punto (`wind_at`) para los lugares.
- `backend/services.py`: el ciclo no genera ninguna grilla de viento.

**Cómo (y nada más que esto):**
1. `backend/windgrid.py` (nuevo): descarga de Open-Meteo horario (`wind_speed_10m`, `wind_direction_10m`; `temperature_2m` solo si la usas para la densidad de partículas) para una grilla de 0,25° sobre Chile continental (aprox. lat −56° a −17°, lon −77° a −66°). Lotea las ubicaciones en pocas peticiones (reutiliza el patrón del FWI: peticiones espaciadas y con reintentos; si conviene, bucle propio fuera del cron para no pasar el límite de tiempo). Guarda el último resultado como archivo compacto (JSON o binario propio) con su `computed_at`. **Presupuesto:** documenta cuántas peticiones usa por actualización (apunta a un máximo de ~100 al día, batching incluido) y refresca cada 1–3 h.
2. `backend/routes/public.py`: `GET /api/wind/grid` que sirve la última grilla (cacheable; con `computed_at`; si todavía no hay grilla, 404 honesto con un mensaje en palabras).
3. `web/js/map.js`: capa de partículas sobre el mapa usando el endpoint. **Sin dependencias nuevas** (canvas/WebGL propio, como ya se hizo para los patrones del mapa de riesgo): un canvas encima del mapa animado con `requestAnimationFrame`, que se pausa cuando el mapa no está visible o la pestaña está oculta; se enciende/apaga con el interruptor de capas existente (`data-layer`, como las demás) y sobrevive al cambio de estilo/tema igual que las otras capas.
4. `web/js/views/mapa.js`: interruptor «Viento» en el panel de capas + una línea de leyenda («Partículas: viento estimado a 10 m · Open-Meteo»). Nada más.
5. `tests/test_windgrid.py` (nuevo): funciones puras — la grilla del bbox es correcta, el parseo de la respuesta y la caché (`computed_at`) funcionan, y con caché fresca no se hace ninguna petición (cliente HTTP simulado).

**No toques nada más.** Si necesitas una regla mínima de CSS para el canvas, documéntala en el PR; evita `web/css/app.css` si puedes.

**Criterio de listo (verificable):**
- `python dev.py check` en «Todo en orden» y `python dev.py e2e` verde.
- Evidencia en el PR: (1) respuesta de `/api/wind/grid` con `computed_at` y el número de celdas; (2) captura del e2e con la capa encendida; (3) una comprobación de que la capa no llama a Open-Meteo por visita (solo sirve lo precalculado), por ejemplo con el conteo de peticiones del módulo.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.

Rebase: `backend/services.py` viene de tocarse en FIX-25 y `backend/routes/public.py` en varios PRs verdes (fix-17, alr-13, ofi-20…); rebasa sobre `origin/main` cuando estén mergeados.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
