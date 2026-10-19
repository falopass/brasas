# Sostenibilidad

## Principio

**Las alertas ciudadanas son gratis para siempre.** El proyecto funciona como una fundación sin fines de lucro, al estilo de Watch Duty: la confianza depende de que nadie pague por recibir un aviso a tiempo.

## Fuentes de financiamiento

| Fuente | Qué ofrece BRASA | Nota |
|---|---|---|
| **Versión para empresas** | Forestales, eléctricas, viñas, agrícolas, aseguradoras y municipios: alertas sobre sus propios predios y líneas, informes por temporada y acceso a los datos por API. | Requiere licencias comerciales del mapa base y de Open-Meteo. |
| **Fondos públicos** | CORFO, ANID y fondos regionales: un piloto operando durante un El Niño fuerte es un argumento potente para postular. | Las bases suelen pedir una contraparte institucional. |
| **Filantropía y cooperación** | Google.org, fundaciones de clima y cooperación internacional. | Cofinanciar la red de verificadores. |
| **Convenios de datos** | Acceso a cámaras y torres de vigilancia de forestales y eléctricas, a cambio de integración y reportes. | Mejora la detección temprana sin costo directo. |

## Costos aproximados del piloto (orden de magnitud)

- Servidor pequeño con HTTPS y respaldos: bajo (decenas de dólares al mes).
- Datos: GOES, FIRMS y Open-Meteo (uso no comercial) no tienen costo; el mapa base vectorial se puede autoalojar.
- Lo caro son **las personas**: verificadores en turno durante la temporada, soporte y comunicación. Presupuestar coordinación y turnos antes que infraestructura.

## Límites y cuotas

OPS-13: que no haya sorpresas en enero. Cada cifra lleva su fuente oficial y la fecha en que se consultó; el uso en vivo se mide en `/api/status` (campos `open_meteo` y los de respaldo). El plan de Cloudflare que usa el proyecto es **Workers Paid** (escrito en `docs/DESPLIEGUE_CLOUDFLARE.md`; Containers no existe en el plan gratuito).

| Servicio | Qué se usa en BRASA | Límite del plan | Costo si se supera | Fuente (URL) | Consultado |
|---|---|---|---|---|---|
| Cloudflare Workers (plan Paid, USD 5/mes) | Worker `brasa-chile`: sirve la PWA, enruta `/api/*`, cron cada 10 min (~4.300 invocaciones/mes) más el tráfico de usuarias | 10 M solicitudes/mes y 30 M ms de CPU incluidos; las solicitudes a *static assets* son gratis e ilimitadas | +USD 0,30 por millón de solicitudes; +USD 0,02 por millón de ms de CPU | <https://developers.cloudflare.com/workers/platform/pricing/> | 19-10-2026 |
| Cloudflare Containers (instancia `basic`: ¼ vCPU, 1 GiB, 4 GB de disco) | Backend FastAPI en `deploy/cloudflare` (`max_instances: 1`, `sleepAfter` por configurar) | Incluidos 25 GiB-h de memoria, 375 vCPU-min y 200 GB-h de disco al mes | Memoria +USD 0,0000025/GiB-s; CPU +USD 0,000020/vCPU-s; disco +USD 0,00000007/GB-s. Una `basic` despierta todo el mes usa ~730 GiB-h: algunos dólares extra | <https://developers.cloudflare.com/containers/platform/pricing/> | 19-10-2026 |
| Cloudflare R2 (bucket `brasa-chile-datos`) | Respaldos cifrados de `brasa.db`, `work.db.gz`, copia diaria y fotos de reportes | Gratis: 10 GB-mes, 1 M operaciones clase A (Put/List) y 10 M clase B (Get/Head) al mes; *egress* gratis | Almacenamiento USD 0,015/GB-mes; clase A USD 4,50/millón; clase B USD 0,36/millón | <https://developers.cloudflare.com/r2/pricing/> | 19-10-2026 |
| Open-Meteo (API gratuita no comercial, licencia CC-BY 4.0) | Pronóstico por comuna, FWI histórico, normales de lluvia y clima de casos; uso medido en `/api/status` (RISK-14) | 10.000 llamadas/día, 5.000/hora, 600/minuto y 300.000/mes, por IP y aplicación | No hay cobro: al superar el límite responde HTTP 429 (el backend espera 65 s y reintenta); el uso comercial exige plan de pago | <https://open-meteo.com/en/terms> · <https://creativecommons.org/licenses/by/4.0/> | 19-10-2026 |
| NASA FIRMS (API de áreas, VIIRS NOAA-20/21 NRT) | Ingesta cada 10 min vía cron y exploración histórica con `MAP_KEY` gratuita | 5.000 transacciones por intervalo de 10 minutos por clave; las consultas grandes cuentan como varias | No hay cobro: se agota la cuota hasta el siguiente intervalo; la clave se pide gratis en su página | <https://firms.modaps.eosdis.nasa.gov/api/area/> · clave: <https://firms.modaps.eosdis.nasa.gov/api/map_key/> | 19-10-2026 |
| Respaldo a R2 (`brasa.db` + `work.db.gz`) | Subida tras cada cambio y al final de cada ciclo; restauración al arrancar el contenedor | Por medir: OPS-18 aún no registra el tamaño comprimido en `/api/status` (hoy solo expone `backup`/`work_backup`) | Dentro del nivel gratuito de R2 mientras el total siga bajo 10 GB | <https://developers.cloudflare.com/r2/pricing/> | 19-10-2026 |

### Si una cuota llega al 80 %

Revisar `/api/status` y los gráficos del panel de Cloudflare, y actuar en este orden: bajar la frecuencia de lo que consume (cron más espaciado, `sleepAfter` más corto, menos tramos históricos de Open-Meteo o FIRMS), subir la duración del caché del borde (OPS-03) para absorber picos, y avisar a la persona dueña del proyecto. **Lo que no se hace sin su decisión:** activar planes de pago, subir límites facturables ni pedir aumentos de cuota — cualquier gasto nuevo pasa por NEG-01 (presupuesto anual) primero.

## Gobernanza mínima antes del verano

- Una persona responsable de la operación diaria y otra de la verificación.
- Una política pública de qué se publica, cómo se verifica y cómo se corrigen errores.
- Una política de privacidad breve: no se piden nombres ni teléfonos; los lugares se asocian a un token del dispositivo; las fotos se publican sin metadatos y solo tras la verificación.
