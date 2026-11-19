---
id: PERF-14
repo: brasas
rama: perf/zona-titulo-fijo
modelo: agente-alto
riesgo: A
archivos: web/js/views/zona.js, web/css/app.css, CHANGELOG.md
e2e: si
---

# PERF-14 · El título de «Mi zona» pinta desde el primer instante

## Objetivo

Que el titular de la vista (`h1.view-title`, el elemento LCP de `#/mi-zona`) se pinte al
montar, sin esperar la primera tanda de consultas. Después de PERF-13 la portada pinta
una sola vez, pero ese pintado sigue esperando `me` + `alerts` + resúmenes por lugar:
en Lighthouse móvil el LCP quedó en ~4,0 s con 87 % de render delay.

## Contexto

- Auditoría del BRASA Lead (19-11-2026): `#/mi-zona` rendimiento 0,87; LCP 4 005 ms,
  fase «Render Delay» 3 492 ms (87 %); elemento LCP `h1.view-title` «¿Hay fuego cerca de
  tu casa?». El texto depende de si hay lugares (`places.length`), que llega después del
  montaje (PERF-13 garantiza que llega por el evento `places`, también sin conexión).
- `paint()` armaba el `innerHTML` completo —incluido el `h1`— solo cuando la primera
  tanda resolvía; cada repintado posterior volvía a crear el `h1`.

## Cambio

- `web/js/views/zona.js`: helpers `tituloZona()` (texto según haya lugares),
  `shellZona()` (esqueleto con `#zona-a`, `h1#zona-title` y `#zona-b`) y
  `syncTitulo()` (actualiza el texto solo si cambió). `mount()` pinta el esqueleto de
  inmediato; `paint()` asegura el esqueleto (la vista de emergencia lo reemplaza y el
  siguiente pintado normal lo reconstruye) y repinta solo las dos zonas. El evento
  `places` sincroniza el título apenas llegan los lugares.
- `web/css/app.css`: `#zona-a, #zona-b { display: contents }` para que el contenido se
  comporte como hijo directo de `#view` y no cambie espaciado ni CLS.

## Criterio de listo

- El `h1` existe en el primer pintado (LCP deja de esperar las consultas) y no se
  recrea en los repintados por datos.
- Quien tiene lugares ve «Tus lugares, hoy» desde que llega `places`, sin esperar los
  resúmenes; el modo emergencia y sus botones siguen funcionando.
- CLS de `#/mi-zona` no empeora; accesibilidad y textos cortados (e2e) en verde.
- CI en verde; presupuestos intactos (bloqueante ≤ 175 KB; total ≤ 346 KB gzip, sin
  mover umbrales).
