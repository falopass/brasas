---
id: MAPA-154
repo: brasas
rama: feat/fuego-visible
modelo: swe-2-high
riesgo: B
archivos: web/js/views/mapa.js, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-154 · Cuándo vuelve a mirar el satélite

**Por qué.** «No veo fuego» no significa «no hay fuego»: el satélite mira cada cierto tiempo. Decir cuándo llega la siguiente mirada baja la ansiedad y explica los huecos.

**Qué hacer.**
1. En la vista Mapa, una línea corta: «El satélite GOES vuelve a mirar en ~N min». Se calcula con el último barrido `ok` de `goes_sweeps` en `/api/status` (`backend/routes/public.py:239`) más la cadencia de 10 min del disco completo de GOES-19. Si el último barrido tiene más de 30 min, dice que hay un atraso, igual que el aviso `goes_gap`.
2. Debajo, en la lectura técnica (`dual`), las ventanas aproximadas de los satélites polares VIIRS (S-NPP, NOAA-20, NOAA-21) sobre Chile: madrugada y primera hora de la tarde, hora local, rotuladas «aproximado». No inventes horarios exactos: si no hay una fuente que dé la pasada exacta, solo la ventana con su fuente (NASA FIRMS / NOAA).
3. Sin llamadas nuevas al backend: `/api/status` ya se refresca cada 60 s (`web/js/app.js:354`).

**Archivos.** `web/js/views/mapa.js` y `CHANGELOG.md`.

**Criterio de listo.** La línea aparece en la captura del mapa y no corta texto a 320 px; el CI pasa.
