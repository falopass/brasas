---
id: PREP-03
repo: brasas
rama: feat/preparate-mantenimiento
modelo: swe-2-high
riesgo: B
archivos: web/js/mantenimiento.js, web/js/views/preparate.js, tests/js/preparate.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# PREP-03 · Mantenimiento de la casa: cuándo se hizo y cuándo toca de nuevo

## Objetivo
Que la casa preparada deje de ser una lista de una sola vez y muestre la fecha en que se hizo cada tarea y cuándo toca repetirla, para que un vecino del Maule no crea que está al día con tareas que hizo hace tres temporadas.

## Qué pasa hoy (verificado en `main`)
- `web/js/views/preparate.js:48-63` (`checklist()` y `bindChecklist()`) guardan el avance como un mapa `{clave: true}` en `localStorage` (`brasa:check:<id>`): una casilla marcada queda marcada **para siempre** y no se guarda ninguna fecha. El comentario de UX-18 lo dice: «Puntaje = % de ítems marcados sobre el total».
- Las tareas de la casa que importan se repiten cada temporada: despejar 10 m alrededor de la casa, limpiar canaletas y techo, revisar la bomba y la manguera, cortar el pasto seco, revisar el medidor de gas. Hoy un vecino que hizo todo en 2024 ve «100/100» y no tiene ningún recordatorio de que eso caduca.
- La única caducidad que existe es la del plan familiar (`preparate.js:143-152`, seis meses), y es solo un aviso, no una fecha por tarea. Nadie guarda «esto lo hice el 12 de octubre».
- Efecto: el puntaje miente por omisión y la vista no ayuda a planificar el fin de semana antes de la temporada de incendios.

## Qué hacer
1. **Módulo puro nuevo `web/js/mantenimiento.js`** (sin DOM): `MANTENIMIENTO` (5 tareas con `clave`, `texto`, `meses` de caducidad y una `fuente` de las que ya están citadas en `preparate.js`: SENAPRED, CONAF) y funciones `diasDesde(fecha, hoy)`, `vence(fechaISO, meses, hoy)` y `estadoTarea(fechaISO, meses, hoy)` → `'sin-registrar' | 'al-dia' | 'toca'`. Sin fechas válidas devuelve `'sin-registrar'`; `null` nunca revienta.
2. **`web/js/views/preparate.js`**: bloque nuevo «Mantenimiento de la casa» debajo de la casa preparada, con las tareas y su casilla; al marcar, guarda `new Date().toISOString()` en `localStorage` bajo `brasa:check:casa:fechas` (clave → ISO); al desmarcar, borra la fecha. Cada fila muestra «hecho el 12 de octubre (hace 8 días)» con `fmtDateTime`/`ago` de `util.js`, o «sin registrar»; las vencidas llevan una etiqueta suave «toca de nuevo» y un `aria-live` que lo anuncie. Reusar las clases que ya existen (`.checklist`, `.progress`, `.tag`) sin CSS nuevo.
3. **No tocar el puntaje existente**: la mochila (`check:mochila`) y el puntaje de la casa siguen igual; este bloque es informativo y no suma al marcador. Nada de dependencias nuevas ni de `fetch`.
4. **`tests/js/preparate.test.mjs`**: hoy prueba la vista como texto (regex sobre el fuente). Agregar casos que importen `../../web/js/mantenimiento.js`: sin fecha → `'sin-registrar'`; fecha de hace 100 días con caducidad de 6 meses → `'al-dia'`; 200 días → `'toca'`; `vence` con `meses = 12` y 364 días → `al-dia`; fecha basura (`'2026-13-45'`) → `'sin-registrar'`; y que la vista pinte la etiqueta «toca de nuevo».

## Criterio de listo (verificable)
- `node --test tests/js` en verde con los casos nuevos.
- `python dev.py check` en «Todo en orden» (si falla **solo** por «Peso del arranque excedido» o «Presupuesto de peso excedido», es el estado de `main` que arregla PERF-06: no subas umbrales, anótalo en el PR).
- Con `python dev.py run --demo`: marcar una tarea de mantenimiento, recargar y ver la fecha guardada; desmarcarla y ver que vuelve a «sin registrar»; `python dev.py e2e` sin errores nuevos.
- El peso nuevo del módulo es menor a 2 KB gzip (decirlo en el PR).

## Archivos a tocar
`web/js/mantenimiento.js` (nuevo), `web/js/views/preparate.js`, `tests/js/preparate.test.mjs`, `CHANGELOG.md`. **No toques nada más**: no edites `web/js/util.js` (en curso), ni `web/js/plan.js`, ni `web/plan.html`, ni `web/css/app.css`, ni `tests/js/index.js`.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
