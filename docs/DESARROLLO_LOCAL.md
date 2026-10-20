# Desarrollo local

Guía para trabajar en BRASA Chile en tu equipo, desde que clonas el repositorio hasta que despliegas. Todo funciona sin claves: con internet, GOES-19 y el riesgo 30-30-30 llegan solos. Sin internet, usa el modo demostración.

## 1. Requisitos

| Herramienta | Versión | Para qué | ¿Obligatoria? |
|---|---|---|---|
| Python | 3.12 o superior (CI prueba 3.12 y 3.13) | Backend, pruebas y scripts | Sí |
| Git | cualquiera reciente | Control de versiones | Sí |
| Node.js | 22 o superior (la usa el CI) | Revisar la sintaxis del JavaScript (`web/` son módulos ES sin `package.json`) y las reglas de diseño (`dev.py check`) | Recomendada |
| Chromium vía Playwright | lo instala `dev.py setup --e2e` | Revisión en navegador real (`dev.py e2e`) | Opcional |
| Wrangler / Docker | — | Solo si quieres probar el Worker de Cloudflare en local | Opcional |

No hay paso de compilación del frontend: `web/` son módulos ES que el backend sirve tal cual.

## 2. Primera vez

```bash
git clone https://github.com/falopass/brasas.git
cd brasas
python dev.py setup          # crea .venv, instala requirements-dev.txt y copia .env.example → .env
python dev.py run            # http://127.0.0.1:8000 con recarga automática del backend
```

En Windows usa `py dev.py …` si `python` no está en el PATH. También sigue funcionando el doble clic en `start_windows.bat` (o `./start.sh` en macOS/Linux) para quien solo quiere usar la aplicación.

Para la revisión en navegador:

```bash
python dev.py setup --e2e    # además instala Playwright y descarga Chromium (~150 MB)
```

## 3. Comandos del día a día (`dev.py`)

| Comando | Qué hace |
|---|---|
| `python dev.py run` | Servidor en `127.0.0.1:8000` con recarga al cambiar `backend/`. El frontend no necesita recarga del servidor: basta refrescar el navegador. |
| `python dev.py run --demo` | Igual, pero con **datos de ejemplo** en `data/demo` y **sin ingesta** (no consulta NASA ni NOAA). Activa `/admin` con el token `demo-admin-token-local`. |
| `python dev.py seed` | Rehace los datos de ejemplo: un incidente en Quilpué (14 detecciones), un incendio «(DEMO)» de CONAF unido a él, Botón Rojo en 5 comunas y riesgo (real si hay internet, de ejemplo si no). |
| `python dev.py test` | Pruebas (`pytest -q`). Los argumentos extra pasan a pytest: `python dev.py test -k incidents -x`. |
| `python dev.py check` | Lo que hay que correr **antes de cada commit**: lint de Python (`ruff`, reglas E9 y F), pruebas, sintaxis de todo `web/**/*.js` y reglas de diseño (`design-taste-frontend`). |
| `python dev.py e2e` | Con el servidor corriendo: recorre 8 vistas en 320, 390 y 1280 px, en lectura sencilla y detallada y con letra grande; reporta errores de JS, violaciones de CSP y textos cortados, y guarda capturas en `data/shots/`. |
| `python dev.py clean` | Borra cachés, `data/demo` y `data/shots`. No toca `data/brasa.db` ni `data/work.db`. |

Regresión visual: las capturas de `e2e` se pueden comparar contra una referencia guardada para pillar cambios de diseño no intencionales. Con el servidor corriendo:

```bash
# fijar la referencia (primera vez, o tras un cambio de diseño deliberado)
python scripts/local/browser_checks.py --url http://127.0.0.1:8000 --out data/shots --update-baseline data/shots-base
# comparar contra ella: falla si alguna vista supera el 0,5 % de píxeles distintos
python scripts/local/browser_checks.py --url http://127.0.0.1:8000 --out data/shots --baseline data/shots-base
```

La tolerancia se ajusta con `--tolerancia` (fracción, defecto 0.005). Cuando algo se movió queda `data/shots/<vista>.diff.png` con los píxeles distintos marcados en magenta. Ni `data/shots` ni `data/shots-base` se versionan.

Con VS Code: `.vscode/launch.json` trae «servidor (datos reales)», «servidor (demo)» y «pruebas» listos para depurar. En Windows cambia `python.defaultInterpreterPath` a `.venv\Scripts\python.exe`.

## 4. Configuración (`.env`)

`.env` se crea desde `.env.example` y **nunca** se publica (está en `.gitignore`). Lo mínimo útil:

| Variable | Efecto en local |
|---|---|
| `FIRMS_MAP_KEY` | Agrega VIIRS NOAA-20/21 (375 m) en vivo y el botón «Sumar VIIRS/MODIS» en la Historia. Clave gratuita en <https://firms.modaps.eosdis.nasa.gov/api/map_key/>. |
| `ADMIN_TOKEN` | Activa la moderación de reportes en `/admin`. |
| `BRASA_SCHEDULER=0` | Apaga la ingesta automática (útil para trabajar en la interfaz sin tráfico de red). |
| `BRASA_DATA_DIR` | Carpeta de las bases. Vacío = `./data`. |
| `GOES_ENABLED=0` | Sin GOES (por ejemplo, con una red muy lenta). |
| `CONAF_PERIMETRO_ENABLED=1` | Perímetro oficial de CONAF en la ficha del incidente (OFI-17). Apagado hasta la autorización de la capa (OFI-03). |

`BRASA_STORAGE_URL`, `INTERNAL_TOKEN` y `TELEGRAM_WEBHOOK_SECRET` solo tienen sentido en Cloudflare: déjalos vacíos.

**Secretos:** el repositorio es público. Las claves reales (FIRMS, ADMIN_TOKEN, Cloudflare) van en tu `.env` local o en *Settings → Secrets and variables → Actions* de GitHub; nunca en archivos del repositorio ni como entradas de un workflow.

## 5. Dónde están los datos

| Archivo | Contenido | ¿Se puede borrar? |
|---|---|---|
| `data/brasa.db` | Datos de las personas: dispositivos, lugares, avisos, reportes. En producción se respalda en R2 tras cada cambio. | Solo si no te importa perder tus lugares de prueba. |
| `data/work.db` | Observaciones (45 días), incidentes, riesgo, Botón Rojo, incendios de CONAF y caché. En producción se respalda cada hora. | Sí: se reconstruye con la ingesta (los incidentes antiguos se pierden). |
| `data/demo/` | Base de `dev.py run --demo`. | Sí (`dev.py seed` la rehace). |
| `data/uploads/` | Fotos de reportes (sin EXIF). | Con cuidado. |
| `web/data/` | Datos versionados: comunas, regiones, casos históricos, GOES precalculado, volcanes. | No: son parte del código. |

El esquema se crea y migra solo al arrancar (`backend/db.py`: `USER_SCHEMA`, `WORK_SCHEMA` y `_migrate_user`). Si agregas una columna a una tabla de personas, súmala a `USER_COLUMNS` para que los respaldos antiguos la reciban.

## 6. Recorrido por el código

```
backend/
  main.py            aplicación FastAPI, ciclo de vida, cabeceras de seguridad (CSP en security.py), PWA
  services.py        ciclo: FIRMS + GOES → observaciones → incidentes → avisos; CONAF; riesgo; respaldos
  incidents.py       agrupa detecciones en incidentes, estados, fuentes fijas, unión con CONAF
  alerts.py          avisos por lugar (satélite y «CONAF informa»)
  risk.py            índice 30-30-30
  cases.py           reconstrucción hora a hora (huella, eventos) — la usan la Historia y la ficha de incidente
  providers/         firms.py · goes.py · weather.py · overpass.py · conaf.py (Botón Rojo e incendios)
  routes/            public.py (mapa, riesgo, incidentes, CONAF) · personal.py (lugares, avisos) · community.py
  db.py · storage.py · geo.py · settings.py · notify/
web/
  index.html · admin.html · sw.js · css/app.css
  js/app.js          rutas (#/vista/...), navegación, hoja móvil
  js/views/          zona (Mi zona + modo emergencia) · mapa · riesgo · casos · incendio · preparate · vecino
  js/map.js · charts.js · data.js · ui.js · util.js · motion.js
  data/              comunas, cases.json, cases/*.goes.json, persistent_hotspots.json
deploy/cloudflare/   Worker (TypeScript) y wrangler.jsonc
scripts/             build_case_goes.py · build_case_timeline.py · build_territory.py · convert_conaf.py
scripts/local/       seed_demo.py · browser_checks.py (los usa dev.py)
tests/               pytest; HTTP simulado con FakeWeb (tests/conftest.py)
  js/                pruebas del frontend con `node --test`; basta crear `tests/js/<tema>.test.mjs`,
                     el índice las descubre solo
```

Más detalle en [`ARQUITECTURA.md`](ARQUITECTURA.md); fuentes y reglas de interpretación en [`FUENTES.md`](FUENTES.md).

## 7. Tareas frecuentes

### Agregar un caso histórico

1. Agrega el caso a `web/data/cases.json`: `id`, fechas UTC, `bbox`, `camera`, `scope` (`fire`, `complex`, `episode` o `season`), `goes` (`{"satellite": "G16"|"G19", "cadence_min": 10}` o `null` con `goes_note`), `firms_sources`, y `figures` con revisiones `{value, source, url, date, note?}`. Cada cifra necesita fuente y enlace (lo verifica `tests/test_api.py`).
2. Precalcula GOES (descarga cada barrido de AWS, sin clave; 72 h ≈ 430 barridos, unos minutos):
   `.venv/bin/python scripts/build_case_goes.py <id> --concurrency 8`
3. Precalcula la línea temporal: `.venv/bin/python scripts/build_case_timeline.py <id>`
4. `python dev.py check` y revisa el caso en `#/casos/<id>`.

### Cambiar la política de seguridad (CSP)

La CSP vive en dos lugares que deben coincidir: `backend/security.py` (servidor local y contenedor) y la constante `CSP` de `deploy/cloudflare/src/index.ts` (borde). `tests/test_security.py` falla si no coinciden o si cambia un script en línea sin actualizar su hash.

### Agregar una fuente de datos

Sigue el patrón de `backend/providers/conaf.py`: función que descarga y normaliza, error propio (`ConafError`) y registro en `ingest_runs` (`start_run` / `finish_run`) para que aparezca en `/api/status`. Documenta la licencia y el enlace en `docs/FUENTES.md` antes de mostrarla. Si el entorno de desarrollo no llega al dominio, explóralo con el workflow **Explorar fuentes oficiales** (`.github/scripts/explorar.py`), que publica lo encontrado como anotaciones.

### Textos de la interfaz

- Español neutro, **sin voseo**.
- Dos niveles de lectura: `dual('frase sencilla', 'detalle técnico')` (en `util.js`). La versión sencilla debe entenderla cualquier persona; la técnica, un experto.
- Nunca decir «incendio» para un punto de calor sin evidencia; «confirmado» solo con CONAF.
- Revisa los textos cortados con `python dev.py e2e`.

## 8. Antes de hacer commit

```bash
python dev.py check                # ruff + pruebas + JS + diseño
python dev.py run --demo &         # en otra terminal
python dev.py e2e                  # si tocaste la interfaz
```

Convenciones de commits y estilo en [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## 9. Desplegar

El despliegue es manual y lo hace GitHub Actions:

1. `git push` a `main` (las pruebas corren solas en **Pruebas**).
2. *Actions → Desplegar en Cloudflare → Run workflow*. El workflow reemplaza la versión del service worker por el SHA del commit, así los usuarios reciben el aviso «Hay una versión nueva».
3. *Actions → Diagnóstico de Cloudflare → Run workflow* (`minutos=11`): espera un ciclo completo del cron y publica `/api/status` y las cabeceras como anotaciones. Revisa que `backup` sea `true`, que no haya `failed_sources` y que lleguen `official_fires` y `boton_rojo`.

Guía completa: [`DESPLIEGUE_CLOUDFLARE.md`](DESPLIEGUE_CLOUDFLARE.md).

Con la CLI de GitHub:

```bash
gh workflow run deploy-cloudflare.yml --ref main
gh workflow run diagnostico-cloudflare.yml --ref main -f minutos=11
```

## 10. Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| «Esperando los primeros datos» por mucho rato | Sin internet o con `BRASA_SCHEDULER=0`. Usa `python dev.py run --demo`. |
| Aviso amarillo de «datos atrasados» en la demo | La demo tiene más de 30 min: `python dev.py seed`. |
| Respuestas 429 al probar mucho | El limitador de solicitudes es por IP: reinicia el servidor. |
| El navegador muestra una versión vieja | El service worker guarda la aplicación. En desarrollo usa una ventana privada o *DevTools → Application → Service workers → Unregister*; `dev.py e2e` ya lo bloquea. |
| La vista 3D no carga | Cesium viene de jsDelivr: necesita internet. El relieve real requiere `CESIUM_ION_PUBLIC_TOKEN`. |
| `dev.py e2e` no encuentra Chromium | `python dev.py setup --e2e`, o apunta a uno existente con `BRASA_CHROMIUM=/ruta/a/chrome`. |
| Error al restaurar en Cloudflare | Mira `last_cycle.restore_error` en `/api/status` (se recorta a 200 caracteres, sin secretos). |
