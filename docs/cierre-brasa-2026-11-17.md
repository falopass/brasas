# Cierre del backlog — 17 de noviembre de 2026

Evidencia del cierre del plan. Continúa [`cierre-brasa-2026-11-08.md`](cierre-brasa-2026-11-08.md).
Base: `main` en `a720f99` (#877). Este documento no implementa nada ni da por terminado lo que no tiene prueba.
Las verificaciones se hicieron por GET contra producción, con el CI de GitHub y con Playwright por SSH en
devin-vm. En el notebook no corrieron pruebas, builds ni servidores.

## 1. Rediseño «Isoterma 2» — PR #888, abierto y en verde, sin fusionar

Los carriles #884 a #887 se fusionaron en la rama de integración `feat/frontend-total`. El PR
[#888](https://github.com/falopass/brasas/pull/888) sigue en **draft** a propósito, para que lo revise la persona
dueña en 390×844. **No se fusiona**: fusionarlo despliega a producción.

| Qué faltaba | Qué se hizo | Evidencia |
|---|---|---|
| `pytest`: el shell del service worker pesaba 2.146.993 B, sobre su techo de 2.142.204 B | Se quitaron comentarios de `web/css/app.css` y `web/css/lista.css`, sin tocar reglas ni el presupuesto: el shell bajó a 2.140.891 B | `51a3a9c` |
| e2e, flujo 4 «compartir con la familia»: falló 4 de 5 veces en el CI | **Causa:** fallaba exactamente en las corridas en que el runner no alcanzaba Open-Meteo (la siembra deja «Sin Open-Meteo» en el log del job). `build_summary` esperaba en serie el viento y el 30-30-30 del punto, con un timeout de 40 s cada uno, y `GET /api/shared/<token>` tardaba hasta ~80 s. **Arreglo en `main`:** [#890](https://github.com/falopass/brasas/pull/890) pide ambos datos en paralelo con un tope de 6 s; si falta un dato, vale `None`. En la rama: si el motor del mapa falla al iniciar, la vista se monta igual (`c1cfbd3`), y el e2e deja el diagnóstico en una sola línea. | `3603293` (#890), `c1cfbd3`, `1c3fafe`; CI verde en `2e0e86f` |
| `geo-reviewer` sobre el carril A (dibujo y encuadre de focos) | Aprobado con 2 hallazgos menores. El primero está corregido: el encuadre inicial ya no se apaga si el primer lote no trae focos confiables. El segundo queda anotado en el PR: con un radio activo, un incidente en estado `anomalia` no dibuja su envolvente | Comentario del geo-reviewer en #888; `b5ce6ab` |
| Comentarios de Devin Review | El PR no tiene comentarios de Devin Review: es un draft y la revisión automática no comentó | `gh api …/pulls/888/comments` vacío |

**Playwright en devin-vm** (demo sembrada, head `b5ce6ab`, `auditar_vistas.py`, 360, 390 y 1280 px, con
`medicion.json` y capturas):

- Ninguna vista se desplaza de lado en 360 ni en 390 px. No hay errores JS en el mapa en ningún ancho.
- CLS de las vistas: 0 a 0,05. El mapa carga en 9,9 s (360 px), 10,1 s (390 px) y 7,2 s (1280 px). Son
  mediciones de la demo en devin-vm, no de producción.
- Cuántos objetivos táctiles miden menos de 44 px, frente a `main` medido igual: lo mismo en todas las vistas,
  salvo **Prepárate**, que pasa de 37 a 52 (360 px) y de 39 a 54 (390 px). Las casillas del tablero ya cumplen,
  pero se suman 20 enlaces sin texto de 24 px de alto y los enlaces de fuentes siguen en 24 px. Queda para la
  revisión de la persona dueña; las reglas de diseño del CI no lo bloquean.

## 2. Aviso de aluvión por lugar guardado — ya estaba en `main`

El encargo pedía calibrar y construir. Las dos cosas ya estaban fusionadas desde el 11-11. Esta vez no se
recalibró nada: no hay evidencia nueva que lo justifique (ver «Límites» en la calibración).

- Calibración con 180 días de lluvia real: 362 cicatrices de CONAF, pronóstico archivado de Open-Meteo,
  relieve Copernicus GLO-90 y Quebrada Honda (8-oct-2026) como evento de control. Está en #838,
  [`docs/aluvion-calibracion.md`](aluvion-calibracion.md) y sus resultados en JSON.
- El aviso para lugares guardados, con la preferencia `aluvion_alerts`, está en #840, #831, #851 y #859.
- **En producción, 17-11, 12:10 UTC:** `GET /api/climate/lluvia?lat=-33.40&lon=-70.50` responde
  `terreno.aviso=false`, `nivel=bajo`, relieve de 5,19° y cicatriz «PLAZA SUR» (CONAF, 897,4 ha a ≤ 5 km,
  hace 322 días). La nota cita el criterio calibrado.
- `docs/ALUVIONES.md` decía «Provisional» en dos umbrales. Ahora dice qué los respalda de verdad:
  `VENTANA_HORAS` (3 h) está **sin calibrar**, porque solo se evaluó esa duración. `CICATRIZ_DIAS` (365) se
  eligió por el evento de control (283 días) y no por una curva de cómo baja el riesgo con el tiempo.

## 3. NDVI — 288/345 comunas; imagen todavía del 16-10

- La cobertura ya se había ampliado de 17 a 288 comunas (#830). La cadencia de 16 días está declarada (#852) y
  la imagen no retrocede a una anterior (#857). Las 57 faltantes están listadas por región en
  [`COBERTURA.md`](COBERTURA.md). Les falta el píxel o el promedio, y no se rellenan.
- **Regeneración intentada el 17-11:** ORNL MODIS Subsets todavía publica como última imagen el compuesto
  `A2026289` (16-10-2026). Se consultó `…/MOD13Q1/dates` en Talca, que devolvió 614 fechas. No se abrió un PR
  con un archivo igual. El compuesto siguiente es el del 1-11 (`A2026305`), todavía sin publicar en ORNL. El
  archivo vence por cadencia el 27-11 (`cobertura_datos.py --check`). Ese día hay que correr
  `scripts/actualizar_sequedad_vegetacion.py`.
- La pantalla muestra la fecha de la imagen, así que no se afirma que el dato sea actual.

## 4. Operación: #798, #882 y #860

- **#798 (riesgo viejo), cerrado el 10-11:** se volvió a verificar. `GET /api/status` el 17-11 a las 12:08 UTC
  dio `risk_computed_at` 10:51 UTC (1,3 h, umbral 6 h), `risk_error` nulo y Open-Meteo sin fallos seguidos.
- **#882 (latencia del sitemap), cerrado:** la sonda relanzada sobre `main`
  ([44080461422](https://github.com/falopass/brasas/actions/runs/44080461422)) terminó en verde y las 15 rutas
  quedaron bajo 2500 ms. Tres GET a `/web/sitemap.xml` respondieron en 0,34 a 0,42 s. El pico de 5,6 s fue 1
  de 3 muestras y coincidió con otras 5 rutas. El sitemap se sirve desde los assets del Worker, sin pasar por
  el contenedor.
- **#860 (DMC_CAP), cerrado:** en las últimas 24 h hubo 21 corridas y 0 fallos (`failures_24h`). La última
  terminó `ok` a las 11:31 UTC.

## 5. Dominio `.cl`

El checklist ya existía en [`DOMINIO_CL.md`](DOMINIO_CL.md) (#821 y #854). Ahora suma el punto de partida
verificado el 17-11 y el orden exacto: registro en NIC, zona, nameservers, Custom Domain, Turnstile y después
el PR de corte con `PUBLIC_BASE_URL`. **No se compró ni se configuró nada.** Turnstile ya está activo en
producción (`/api/config` publica la clave del sitio).

## Producción al cierre (GET, 17-11, 12:08 UTC)

- `/api/health`: `ok`, versión `0.9.0`.
- `/api/status`: ingesta de hace 7 min, `failed_sources: []`, `backup: true` y 0 fallos en 24 h en todas las
  fuentes. El contenedor acababa de despertar: `startup_ms` 2284, restauración de `work.db` en 2009 ms.
- #890 se desplegó solo: el despliegue de `3603293` terminó en verde y `/web/sw.js` declara `brasa-36032936`. A las 13:41 UTC: `/api/health` `ok`; `/api/status` con ingesta a las 13:31 UTC, `failed_sources: []` y sin datos viejos.

## Bloqueado o esperando a la persona dueña

- **Revisar y fusionar #888.** Al fusionarlo se despliega solo.
- Elegir y comprar el `.cl` y hacer los pasos en paneles ([`DOMINIO_CL.md`](DOMINIO_CL.md)).
- Autorización formal de CONAF para el CSV de incendios y acceso oficial a las alertas de SENAPRED. No se
  contactó a nadie.
- SMS y WhatsApp esperan presupuesto. Telegram está descartado.
- PRs de terceros que este cierre no tocó: dependabot #878, #879, #880 y #881, y el documento #883.
