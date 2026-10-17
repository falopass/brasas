# BRASA Chile · v0.2

**Alertas ciudadanas de incendios forestales por lugar, riesgo meteorológico por comuna y reconstrucción de incendios históricos.**

BRASA responde una pregunta concreta: *«¿mi casa, mi parcela o mi familia están en riesgo hoy, y qué debo hacer?»*. Complementa a SENAPRED y CONAF, nunca compite con ellos: las alertas oficiales (SAE en el celular) siguen siendo la autoridad. BRASA aporta contexto, un aviso temprano cuando un satélite detecta calor cerca y herramientas de prevención.

> Prototipo independiente. No está afiliado a CONAF, SENAPRED ni NASA/NOAA. **No usar para decidir una evacuación**: sigue siempre las instrucciones oficiales.

## Qué hace

| Módulo | Qué entrega | Datos |
|---|---|---|
| **Mi zona** | Guarda tu casa, tu parcela o la casa de tu familia. Cada lugar muestra su estado (*sin focos*, *riesgo alto hoy*, *foco cercano*, *urgente*), los focos más cercanos con distancia y dirección, el viento y el riesgo de los próximos 7 días. | GOES, VIIRS, Open-Meteo |
| **Alertas por lugar** | Aviso cuando aparece un foco confiable dentro de tu radio; pasa a **urgente** si el viento sopla desde el foco hacia tu lugar, si está a ≤ 2 km, o a ≤ 5 km en un día de riesgo alto. Llega por notificación web (PWA) y/o Telegram. | Ingesta cada 10 min |
| **Mapa en vivo** | Focos de las últimas 6 h a 7 días, coloreados por antigüedad; los píxeles GOES se dibujan con su tamaño real (~2–3 km), y la ficha de cada foco incluye sensor, hora, comuna, FRP y confianza. También muestra el estado de cada fuente y permite explorar el archivo FIRMS por fecha. | NASA FIRMS, NOAA GOES |
| **Riesgo 30-30-30** | Semáforo por comuna para 7 días (temperatura > 30 °C, humedad < 30 %, viento > 30 km/h, hora a hora), ranking de comunas y gráficos horarios con los umbrales. | Open-Meteo |
| **Casos históricos** | Reconstrucción hora a hora de **Viña del Mar 2024**, **Ñuble-Biobío-Araucanía 2023** y **Las Máquinas 2017**: reproductor, huella acumulada de calor, gráficos sincronizados (píxeles, huella, viento, temperatura y humedad ERA5), eventos derivados de los datos, vista 2D/3D e importación del perímetro oficial de CONAF. | GOES-16 real (precalculado), FIRMS SP, ERA5 |
| **Prepárate** | Checklist «mi casa preparada» y mochila de emergencia (se guardan en el dispositivo), plan familiar imprimible, qué hacer antes, durante y después, prevención y denuncia. | — |
| **Reportes ciudadanos** | Foto + ubicación + descripción. La foto se re-codifica sin EXIF/GPS. Nada se publica sin verificación humana en `/admin`. | Voluntarios |

Todo lo que aparece en pantalla indica su **fuente, hora y nivel de confianza**. No hay datos simulados: si una fuente no responde, se dice.

## Inicio rápido

### Windows (doble clic)

1. Instala [Python 3.10 o superior](https://www.python.org/downloads/) (marca *Add python.exe to PATH*).
2. Haz doble clic en **`start_windows.bat`**. La primera vez crea un entorno en `.venv` e instala dependencias (requiere internet). Después abre `http://127.0.0.1:8000` cuando el servidor está listo.
3. Opcional: edita `.env` (se crea solo a partir de `.env.example`) y reinicia.

### macOS / Linux

```bash
./start.sh            # o: ./start.sh 8080
```

### Sin configurar nada ya funciona

- **GOES-Este** (NOAA, cada 10 minutos, sin clave) alimenta el mapa y las alertas desde el primer minuto; al arrancar se rellenan las últimas 6 horas.
- Los **casos 2023 y 2024** traen detecciones GOES reales precalculadas.
- El **riesgo 30-30-30** se calcula cada 3 horas si el servidor tiene internet (Open-Meteo, sin clave).

### Configuración recomendada (`.env`)

| Variable | Para qué |
|---|---|
| `FIRMS_MAP_KEY` | VIIRS NOAA-20/21 (375 m) en vivo y el archivo científico de los casos. Clave gratuita: <https://firms.modaps.eosdis.nasa.gov/api/map_key/> |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | Alertas por Telegram. Crea el bot con @BotFather. |
| `ADMIN_TOKEN` | Activa la moderación de reportes en `/admin`. Usa un valor largo y secreto. |
| `PUBLIC_BASE_URL` | Dirección pública, para los enlaces de las alertas. |
| `CESIUM_ION_PUBLIC_TOKEN` | Relieve 3D real en los casos (token público y restringido por dominio). |

Las notificaciones web exigen **HTTPS** (o `localhost`). Para usar BRASA desde un celular, publícala detrás de HTTPS.

### Publicar en Cloudflare (Workers + Containers)

La PWA se sirve desde el borde, el backend Python corre en un Cloudflare Container, la ingesta la dispara un Cron Trigger cada 10 minutos y los datos de las personas se respaldan en R2. El despliegue lo hace GitHub Actions (**Actions → Desplegar en Cloudflare**) en cuanto agregues `CLOUDFLARE_API_TOKEN` y `CLOUDFLARE_ACCOUNT_ID` como secretos. Guía: [`docs/DESPLIEGUE_CLOUDFLARE.md`](docs/DESPLIEGUE_CLOUDFLARE.md). Para un VPS propio, ver [`docs/OPERACION.md`](docs/OPERACION.md).

## Arquitectura en una línea

FastAPI + SQLite (esquema espejo del diseño PostGIS) + tareas asíncronas de ingesta → PWA sin compilación (MapLibre 2D liviano, Cesium 3D bajo demanda, gráficos SVG propios). Detalle en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

```
backend/
  main.py           aplicación, ciclo de vida, cabeceras de seguridad, PWA
  services.py       ingesta FIRMS + GOES → base local → alertas → Telegram/Web Push
  providers/        firms.py · goes.py · weather.py · overpass.py
  geo.py            345 comunas reales (BCN), punto→comuna, distancia, rumbo, barlovento
  risk.py           índice 30-30-30 horario y diario
  alerts.py         reglas de alerta por lugar
  cases.py          reconstrucción de casos: huella, gráficos y eventos
  notify/           telegram.py · webpush.py
  routes/           API pública, personal (lugares, alertas) y comunidad (reportes, casos)
web/
  index.html · sw.js · manifest.webmanifest · admin.html
  js/               app, mapa, gráficos, vistas (mi-zona, mapa, riesgo, casos, prepárate)
  data/             comunas, regiones, catálogo de casos y GOES precalculado
scripts/            build_territory.py · build_case_goes.py · build_case_timeline.py · convert_conaf.py
deploy/cloudflare/  Worker (TypeScript), wrangler.jsonc · Dockerfile en la raíz
```

## API (resumen)

`GET /api/config` · `GET /api/status` · `GET /api/observations?hours=24` · `GET /api/explore?zone=region-7&mode=historical&start=2017-01-24&days=5` · `GET /api/risk?day=AAAA-MM-DD` · `GET /api/risk/{código_comuna}` · `POST /api/subscribers` · `GET|POST|PATCH|DELETE /api/places` (cabecera `X-Brasa-Token`) · `GET /api/places/{id}/summary` · `GET /api/alerts` · `POST /api/push/subscribe` · `POST /api/telegram/link` · `POST /api/reports` · `GET /api/cases/{id}` · documentación interactiva en `/docs`.

## Pruebas

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
# Con un barrido GOES real (por ejemplo, el del 2024-02-02 21:00 UTC):
BRASA_GOES_SAMPLE=ruta/al/archivo.nc python -m pytest -q tests/test_goes.py
```

Las pruebas simulan FIRMS, Open-Meteo y Telegram (no hacen llamadas reales) y cubren parseo, proyección GOES, riesgo, alertas y deduplicación, privacidad de fotos, moderación, aislamiento entre dispositivos y que ningún secreto llegue al navegador.

## Regenerar datos

```bash
python scripts/build_territory.py carpeta_con_1..16.geojson   # comunas BCN (caracena/chile-geojson)
python scripts/build_case_goes.py vina-del-mar-2024          # GOES-16 real desde AWS
python scripts/build_case_timeline.py                         # huella, gráficos y eventos
python scripts/convert_conaf.py perimetros.shp --output perimetro.geojson   # requiere requirements-geo.txt
```

## Límites que hay que conocer

- Un **foco de calor no es un incendio confirmado**: puede ser una quema agrícola, una industria o un falso positivo. Y que no haya focos no garantiza que no haya fuego (nubes, humo, horas sin pasada satelital).
- **GOES** llega con unos 10 a 20 minutos de retraso y tiene píxeles de 2 a 3 km. **VIIRS** tiene una resolución de 375 m, pero pasa pocas veces al día y llega con 1 a 3 horas de retraso.
- El índice 30-30-30 usa un modelo meteorológico de kilómetros de resolución: no ve el viento de una quebrada ni la sequedad de la vegetación.
- La **huella** de los casos es la unión de píxeles calientes: no es el perímetro oficial ni el área quemada.
- La lista de las 90 comunas prioritarias de CONAF se carga solo desde la fuente oficial (`web/data/prioritarias.json`); hoy está vacía a la espera de esa verificación.

## Documentación

- [`docs/ROADMAP.md`](docs/ROADMAP.md): plan por etapas con fechas para el verano 2026-27.
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md): arquitectura actual, modelo de datos y migración a PostGIS.
- [`docs/FUENTES.md`](docs/FUENTES.md): fuentes, licencias y reglas de interpretación.
- [`docs/DESPLIEGUE_CLOUDFLARE.md`](docs/DESPLIEGUE_CLOUDFLARE.md): Workers + Containers + R2, paso a paso.
- [`docs/OPERACION.md`](docs/OPERACION.md): VPS con HTTPS, Telegram, moderación y verificación en vivo.
- [`docs/ALUVIONES.md`](docs/ALUVIONES.md): siguiente amenaza, de incendio a aluvión.
- [`docs/SOSTENIBILIDAD.md`](docs/SOSTENIBILIDAD.md): modelo de fundación y versión para empresas.
