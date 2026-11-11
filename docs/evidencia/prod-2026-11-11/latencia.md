## Latencia de las páginas públicas

| ruta | n | p50 | p95 | máx | borde | estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `/` | 3 | 72 ms | 79 ms | 79 ms | ·,·,· | ok |
| `/web/lite.html` | 3 | 55 ms | 87 ms | 87 ms | ·,·,· | ok |
| `/web/pantalla.html?comuna=5801` | 3 | 58 ms | 70 ms | 70 ms | ·,·,· | ok |
| `/web/lista.html` | 3 | 31 ms | 43 ms | 43 ms | ·,·,· | ok |
| `/web/respuesta.html` | 3 | 27 ms | 66 ms | 66 ms | ·,·,· | ok |
| `/web/plan.html` | 3 | 26 ms | 34 ms | 34 ms | ·,·,· | ok |
| `/web/datos.html` | 3 | 43 ms | 83 ms | 83 ms | ·,·,· | ok |
| `/web/sitemap.xml` | 3 | 31 ms | 71 ms | 71 ms | ·,·,· | ok |
| `/api/health` | 3 | 103 ms | 114 ms | 114 ms | ·,·,· | ok |
| `/api/config` | 3 | 27 ms | 76 ms | 76 ms | hit,hit,hit | ok |
| `/api/status` | 3 | 25 ms | 26 ms | 26 ms | hit,hit,hit | ok |
| `/api/risk/5801` | 3 | 28 ms | 84 ms | 84 ms | hit,hit,hit | ok |
| `/api/incidents` | 3 | 30 ms | 30 ms | 30 ms | hit,hit,hit | ok |
| `/api/observations?bbox=-75,-56,-66,-17` | 3 | 56 ms | 76 ms | 76 ms | hit,hit,hit | ok |
| `/api/panorama` | 3 | 149 ms | 156 ms | 156 ms | ·,·,· | ok |

todas las rutas dentro del presupuesto. Base: https://brasa-chile.ddiegosebastianbb.workers.dev · 3 repetición(es) por ruta · hora UTC 2026-11-11T01:59:26Z.

Si una ruta quedó lenta: revisa primero la caché del borde (miss del Worker),
después el peso de la vista (`python scripts/local/presupuesto_peso.py`) y por
último la consulta que la alimenta. Detalles en docs/LATENCIA.md. Mientras un
issue «[latencia] …» siga abierto, este monitoreo lo actualiza en vez de crear otro.