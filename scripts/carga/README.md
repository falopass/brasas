# Prueba de carga del mapa (OPS-04)

`mapa.js` simula a una persona que abre el mapa: la carga inicial en paralelo (página, GeoJSON
de comunas y las API públicas) y después los refrescos reales de la app (`/api/status` cada 60 s,
`/api/observations` cada 120 s). La forma de la prueba es la del backlog: **500 usuarios
simultáneos durante 10 minutos**, midiendo **p95 y porcentaje de errores** (umbrales: p95 < 2 s,
errores < 1 %).

## Cómo correrla

1. Instala [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (un solo binario).
2. Levanta una **copia de prueba** — nunca apuntes esto a producción sin avisar:
   - **Local:** `python dev.py run --demo` (o `run` normal) y después
     `k6 run -e BASE_URL=http://127.0.0.1:8000 scripts/carga/mapa.js`
   - **Copia en Cloudflare:** despliega el Worker con otro nombre (`"name": "brasa-chile-prueba"`
     en `wrangler.jsonc` o un segundo `wrangler deploy --name …`) y apunta ahí:
     `k6 run -e BASE_URL=https://brasa-chile-prueba.<subdominio>.workers.dev scripts/carga/mapa.js`
3. Al terminar, el resumen de k6 muestra `http_req_duration` con `p(95)` y `http_req_failed`.
   Si algún umbral falla, k6 termina con código distinto de 0.

## Opciones (variables de entorno)

| Variable | Qué hace |
|---|---|
| `BASE_URL` | Destino (defecto `http://127.0.0.1:8000`). |
| `WITH_PRIVATE=1` | Agrega el alta de suscriptor (`POST /api/subscribers`) y `/api/places` con token. Desde una sola máquina estas rutas chocan con el límite por IP (en la app y en el borde), así que vienen apagadas: sirven para probar que el límite funciona, no para medir el mapa. |

## Cómo leer los resultados

- **En local** no hay borde: todo pega al proceso Python. Es un piso: producción con la caché del
  Worker (OPS-03) debería responder mejor a los GET públicos.
- **Con la caché del borde activa** las respuestas repetidas llegan desde Cloudflare sin tocar el
  contenedor: espera un p95 muy bajo y la cabecera `X-Brasa-Cache: hit|stale|miss`.
- Si los errores son 503 «iniciando», el contenedor estaba dormido: la prueba también mide el
  arranque en frío.
