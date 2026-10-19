# Operación: despliegue, alertas, moderación y verificación

> En temporada de incendios (15-dic → 28-feb) aplica el [congelamiento de temporada](#7-congelamiento-de-temporada-15-dic--28-feb): solo arreglos, cada uno con diagnóstico y reversión probada.

## 1. Verificación en tu equipo (lo que no se pudo probar en el entorno de desarrollo)

El entorno donde se construyó la v0.2 tenía acceso a NOAA GOES (AWS) pero **no** a FIRMS, Open-Meteo, OpenFreeMap, EOX, Overpass ni Telegram. Esas integraciones están probadas con respuestas simuladas; confírmalas en vivo:

1. `start_windows.bat` (o `./start.sh`) → abre `http://127.0.0.1:8000`. El indicador superior debe decir «Actualizado hace X min».
2. **Mapa base**: en *Mapa* deberían verse calles y nombres (OpenFreeMap). Prueba *Satélite* y *Relieve*.
3. **GOES**: en *Mapa → Estado de las fuentes* aparece «GOES-19 · cada 10 min» con una consulta correcta reciente.
4. **FIRMS**: agrega `FIRMS_MAP_KEY` en `.env`, reinicia y espera un ciclo (10 min). Debe aparecer «VIIRS NOAA-20 + VIIRS NOAA-21». En *Explorar una fecha* consulta Maule el 2017-01-24.
5. **Riesgo**: a los pocos minutos de arrancar, *Riesgo* muestra el semáforo de 7 días. Si dice «Aún no hay pronóstico», revisa la conexión con `api.open-meteo.com`.
6. **Casos**: en *Casos → Viña del Mar 2024*, el clima ERA5 debe cargar (viento, temperatura y humedad). Con clave FIRMS, pulsa «Sumar VIIRS/MODIS».
7. **3D**: en un caso, pulsa 3D (descarga Cesium desde jsDelivr).
8. **Puntos de encuentro**: en *Mi zona*, agrega un lugar urbano y pulsa «Puntos de encuentro» (Overpass).

## 2. Publicar con HTTPS (necesario para notificaciones en celulares)

Web Push solo funciona en `localhost` o con HTTPS. La opción recomendada es **Cloudflare Workers + Containers**, con despliegue automático desde GitHub: ver [`DESPLIEGUE_CLOUDFLARE.md`](DESPLIEGUE_CLOUDFLARE.md). Alternativas:

- **VPS** (cualquier proveedor con Ubuntu): instala Python 3.12+, clona el repositorio, crea el `.env` y ejecuta detrás de **Caddy**, que obtiene el certificado automáticamente:

  ```
  # /etc/caddy/Caddyfile
  brasa.tu-dominio.cl {
      reverse_proxy 127.0.0.1:8000
  }
  ```

  ```bash
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
  ```

  Usa `systemd` para reiniciarlo solo y define `PUBLIC_BASE_URL=https://brasa.tu-dominio.cl`.
- **Túnel temporal** para un piloto (por ejemplo, Cloudflare Tunnel) apuntando a `http://127.0.0.1:8000`.

Un único proceso basta para el piloto: SQLite con WAL soporta bien cientos de usuarios. **No ejecutes varias réplicas** con la misma base: cada una lanzaría su propia ingesta. Antes de escalar, separa la ingesta en un worker y pasa a PostGIS (ver `ARQUITECTURA.md`).

Respaldo: copia `data/brasa.db` una vez al día (contiene lugares, suscripciones y reportes). Las claves VAPID viven en la tabla `kv`: si se pierden, los navegadores deberán volver a suscribirse.

## 3. Telegram

1. En Telegram, habla con **@BotFather** → `/newbot` → elige un nombre y un usuario (por ejemplo `BrasaChileBot`).
2. Copia el token en `TELEGRAM_BOT_TOKEN` y el usuario (sin @) en `TELEGRAM_BOT_USERNAME`. Reinicia.
3. En la web: *Mi zona → Activar alertas → Vincular Telegram* abre el bot con un código de un solo uso.
4. En el bot también se puede compartir una ubicación para crear un lugar, o usar `/lugares`, `/riesgo` y `/borrar`.

En un servidor propio el bot usa *long polling* (no requiere URL pública). En Cloudflare usa *webhook* automáticamente (`TELEGRAM_WEBHOOK_SECRET`). Solo un despliegue debe usar el mismo token.

## 4. Red de verificadores (moderación)

- Define `ADMIN_TOKEN` (largo y secreto) y comparte `https://…/admin` solo con verificadores de confianza.
- Criterio mínimo para **verificar**: al menos una confirmación independiente (otra fuente, una llamada a Bomberos o CONAF, o una detección satelital consistente cerca). Ante la duda, no publicar.
- Los reportes verificados aparecen en el mapa con ubicación redondeada (~100 m) y la marca «verificado por moderación de BRASA, no es información oficial».
- La v0.2 usa un solo token compartido. Para la temporada, la siguiente mejora es tener cuentas por verificador con registro de quién verificó qué.

## 5. Alertas: cómo se deciden

| Condición (detección nueva y confiable dentro del radio) | Nivel |
|---|---|
| Viento ≥ 8 km/h que sopla desde el foco hacia el lugar (±45°) | **urgente** |
| Foco a ≤ 2 km | **urgente** |
| Foco a ≤ 5 km en un día de riesgo 30-30-30 alto o extremo | **urgente** |
| Cualquier otra detección confiable dentro del radio | aviso |

«Confiable»: VIIRS/MODIS nominal o alta; GOES alta o media. Un mismo foco (≤ 3 km, 12 h) no se repite salvo que suba de nivel. Cada alerta incluye la fuente, la hora, la confianza, la distancia, la dirección, el viento y el texto «Esto no es una alerta oficial…» con los números de emergencia.

## 6. Datos que se regeneran

| Archivo | Cómo | Cuándo |
|---|---|---|
| `web/data/comunas.geojson`, `regiones.geojson` | `scripts/build_territory.py` | Si cambian los límites oficiales |
| `web/data/cases/*.goes.json` | `scripts/build_case_goes.py <caso>` | Al agregar un caso |
| `web/data/cases/*.timeline.json` | `scripts/build_case_timeline.py` | Tras cambiar `cases.py` o el GOES de un caso |
| `web/data/prioritarias.json` | A mano, desde el documento de CONAF | Al inicio de cada temporada |

## 7. Congelamiento de temporada (15-dic → 28-feb)

Durante la temporada de incendios la prioridad es que la aplicación **no se rompa**: cada despliegue se hace con diagnóstico previo y con la reversión ya probada (OPS-17). El congelamiento parte una vez cerrada la 0.7.0 en producción (OPS-19: desplegar y correr el diagnóstico); hasta entonces el ritmo normal sigue.

**Qué se congela**

- Funcionalidades nuevas y mejoras (features), aunque estén listas.
- Refactors, reordenamientos y limpiezas de código.
- Actualizaciones de dependencias (Python, npm, imágenes base).

**Qué sí se hace**

- Arreglos de fallos que afectan el servicio: la app caída, alertas que no llegan o llegan mal, datos corruptos, huecos de seguridad.
- Cambios mínimos de configuración urgente (por ejemplo, una clave vencida).

**Qué significa «con diagnóstico»**

Cada arreglo llega a producción con una nota (en el PR) que responde:

1. **Evidencia del problema**: qué se observó (log, captura, respuesta de `/api/status`, reporte de una persona) y desde cuándo.
2. **Por qué el cambio es mínimo**: qué se tocó y por qué no hace falta tocar nada más.
3. **Qué se verificó**: salida de `python dev.py check`, pruebas acotadas (`python dev.py test -k …`) y, si tocó la interfaz, el e2e.

### Lista de verificación antes de cada despliegue de temporada

En este orden; si algo queda en rojo, no se despliega:

1. `python dev.py check` → «Todo en orden».
2. `python dev.py e2e` si el cambio tocó `web/` o el Worker.
3. Diagnóstico de Cloudflare en verde *antes* del despliegue (workflow **Diagnóstico en Cloudflare**, `workflow_dispatch`): `/api/health` y `/api/status` responden 200 y el último ciclo del cron terminó bien. Así sabemos que cualquier fallo posterior lo introdujo este despliegue.
4. La nota de diagnóstico del arreglo está en el PR.
5. Se conoce el commit/versión al que se volvería si algo sale mal (ver Reversión).

### Reversión

El despliegue es un Worker + un contenedor (`deploy/cloudflare/wrangler.jsonc`). Hay dos piezas que revertir.

**Worker (rápido, ~segundos).** Wrangler guarda las últimas 10 versiones del Worker. Verificado con wrangler 4.151 (`npx wrangler rollback --help`, `npx wrangler versions list --help`):

```bash
cd deploy/cloudflare
export CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=…
npx wrangler versions list          # lista las 10 versiones más recientes
npx wrangler rollback <version-id> -y -m "Reversión: <motivo>"
```

Tras el rollback, corre el workflow **Diagnóstico en Cloudflare** y confirma `/api/health` + `/api/status`.

> Verificar antes de usar: `rollback` revierte el código y la configuración del Worker; confirma en el diagnóstico que el contenedor sigue respondiendo. Si la versión anterior ya no aparece en `versions list` o el rollback no alcanza al contenedor, usa la vía del commit anterior.

**Contenedor / reversión completa (la vía probada).** Redesplegar el commit anterior con el mismo workflow de siempre:

1. En `main`, revierte el cambio problemático: `git revert <sha-del-despliegue-malo>` (o vuelve `main` al commit anterior si era un solo commit) y push. Si `CLOUDFLARE_DEPLOY=true` el push despliega solo; si no, corre el workflow **Desplegar en Cloudflare** con `workflow_dispatch`.
2. Alternativa sin tocar `main`: `git checkout <sha-anterior>` en un clone aparte, `cd deploy/cloudflare && npm ci && npx wrangler deploy` con los mismos secretos/variables.
3. Corre el diagnóstico y confirma `/api/health` + `/api/status` y un ciclo del cron.

Ojo: los datos no se revierten con esto. Si el fallo dañó la base, restaura el respaldo de R2 (`DESPLIEGUE_CLOUDFLARE.md → Restaurar un respaldo anterior`) *además* de revertir el código.
