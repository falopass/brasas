## Latencia de las páginas públicas

| ruta | n | p50 | p95 | máx | borde | estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `/` | 3 | 121 ms | 150 ms | 150 ms | ·,·,· | ok |
| `/web/lite.html` | 3 | 111 ms | 171 ms | 171 ms | ·,·,· | ok |
| `/web/pantalla.html?comuna=5801` | 3 | 139 ms | 225 ms | 225 ms | ·,·,· | ok |
| `/web/lista.html` | 3 | 115 ms | 161 ms | 161 ms | ·,·,· | ok |
| `/web/respuesta.html` | 3 | 161 ms | 273 ms | 273 ms | ·,·,· | ok |
| `/web/plan.html` | 3 | 120 ms | 190 ms | 190 ms | ·,·,· | ok |
| `/web/datos.html` | 3 | 135 ms | 335 ms | 335 ms | ·,·,· | ok |
| `/web/sitemap.xml` | 3 | 133 ms | 234 ms | 234 ms | ·,·,· | ok |
| `/api/health` | 3 | 203 ms | 215 ms | 215 ms | ·,·,· | ok |
| `/api/config` | 3 | 123 ms | 165 ms | 165 ms | hit,hit,hit | ok |
| `/api/status` | 3 | 121 ms | 220 ms | 220 ms | snapshot,hit,hit | ok |
| `/api/risk/5801` | 3 | 137 ms | 208 ms | 208 ms | hit,hit,hit | ok |
| `/api/incidents` | 3 | 122 ms | 124 ms | 124 ms | hit,hit,hit | ok |
| `/api/observations?bbox=-75,-56,-66,-17` | 3 | 171 ms | 186 ms | 186 ms | hit,hit,hit | ok |
| `/api/panorama` | 3 | 192 ms | 206 ms | 206 ms | ·,·,· | ok |

todas las rutas dentro del presupuesto. Base: https://brasa-chile.ddiegosebastianbb.workers.dev · 3 repetición(es) por ruta · hora UTC 2026-11-11T01:03:33Z.

Si una ruta quedó lenta: revisa primero la caché del borde (miss del Worker),
después el peso de la vista (`python scripts/local/presupuesto_peso.py`) y por
último la consulta que la alimenta. Detalles en docs/LATENCIA.md. Mientras un
issue «[latencia] …» siga abierto, este monitoreo lo actualiza en vez de crear otro.
