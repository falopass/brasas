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

Si usas la imagen de contenedor (`Dockerfile`) fuera de Cloudflare, la variable `FORWARDED_ALLOW_IPS` controla de quién se aceptan las cabeceras `X-Forwarded-*`. Su valor por defecto es `*` porque en Cloudflare solo el Worker puede hablar con el contenedor y sus cabeceras son legítimas. **En un VPS sin proxy delante hay que definirla**: usa `FORWARDED_ALLOW_IPS=127.0.0.1`, o defínela vacía (`FORWARDED_ALLOW_IPS=`) para no confiar en nadie — sin definirla, el valor es `*`. Con `*`, cualquier cliente puede enviar un `X-Forwarded-For` falso y el limitador de solicitudes contaría un cupo nuevo en cada petición, quedando sin efecto. Si hay un proxy propio delante (Caddy, nginx), indica su IP (`127.0.0.1` si corre en el mismo host).

Un único proceso basta para el piloto: SQLite con WAL soporta bien cientos de usuarios. **No ejecutes varias réplicas** con la misma base: cada una lanzaría su propia ingesta. Antes de escalar, separa la ingesta en un worker y pasa a PostGIS (ver `ARQUITECTURA.md`).

Respaldo: copia `data/brasa.db` una vez al día (contiene lugares, suscripciones y reportes). Las claves VAPID viven en la tabla `kv`: si se pierden, los navegadores deberán volver a suscribirse.

## 3. Telegram

1. En Telegram, habla con **@BotFather** → `/newbot` → elige un nombre y un usuario (por ejemplo `BrasaChileBot`).
2. Copia el token en `TELEGRAM_BOT_TOKEN` y el usuario (sin @) en `TELEGRAM_BOT_USERNAME`. Reinicia.
3. En la web: *Mi zona → Activar alertas → Vincular Telegram* abre el bot con un código de un solo uso.
4. En el bot también se puede compartir una ubicación para crear un lugar, o usar `/lugares`, `/riesgo` y `/borrar`.

En un servidor propio el bot usa *long polling* (no requiere URL pública). En Cloudflare usa *webhook* automáticamente (`TELEGRAM_WEBHOOK_SECRET`). Solo un despliegue debe usar el mismo token.

## 4. Red de verificadores (moderación)

- Define `ADMIN_TOKEN` (largo y secreto): es el acceso maestro a `https://…/admin` y el único que gestiona el equipo. **No lo compartas con los voluntarios**: cada uno entra con su propio token.
- Criterio mínimo para **verificar**: al menos una confirmación independiente (otra fuente, una llamada a Bomberos o CONAF, o una detección satelital consistente cerca). Ante la duda, no publicar.
- Los reportes verificados aparecen en el mapa con ubicación redondeada (~100 m) y la marca «verificado por moderación de BRASA, no es información oficial».

### Alta de un moderador

1. Entra a `https://…/admin` con el `ADMIN_TOKEN` y abre la pestaña «Moderadores».
2. Escribe el nombre de la persona y pulsa «Crear y generar token». El token se muestra **una sola vez**: cópialo ahí mismo.
3. Entrégaselo por un canal privado (nunca en un grupo). En la base solo queda su hash (SHA-256): si se pierde no se puede recuperar — revoca el acceso y crea otro.

### Revocación

- Pestaña «Moderadores» → «Revocar acceso» (pide un segundo clic). El token deja de funcionar al instante; las decisiones que la persona ya tomó quedan registradas a su nombre.

### Qué queda registrado

- La pestaña «Registro» (visible para todo el equipo) muestra cada verificación o descarte: quién, cuándo, sobre qué reporte y la nota. Las acciones hechas con el `ADMIN_TOKEN` aparecen como «administración».

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

## 8. Rotación de secretos

Los ejecuta la persona dueña. Reglas de siempre: ningún valor de secreto se imprime, se pega en chats ni se commitea; se genera uno nuevo, se actualiza en **todos** los lugares donde vive y se verifica antes de dar la rotación por cerrada.

| Secreto | Para qué sirve | Dónde se define | Cuándo rotar | Qué se rompe si queda descoordinado |
|---|---|---|---|---|
| `ADMIN_TOKEN` | Acceso a `/admin` (moderación de reportes, §4) | Secreto de GitHub Actions y secreto del Worker (`DESPLIEGUE_CLOUDFLARE.md` → «Secretos y variables en GitHub», líneas 53 y 96) | Anual, al cambiar de moderadores o ante sospecha de filtración | Si difiere entre GitHub y el Worker, el siguiente despliegue lo deja con el valor de GitHub; si alguien queda con el viejo, no puede entrar a `/admin` |
| `INTERNAL_TOKEN` | Autoriza las subidas del contenedor a R2 (`_internal/storage`) y el cron `/api/internal/tick` | Solo en el Worker: lo genera el workflow en el primer despliegue (línea 60) y se conserva; a mano es `wrangler secret put INTERNAL_TOKEN` (línea 94) | Anual o ante sospecha de exposición | Si el Worker y el contenedor no comparten el valor: los respaldos a R2 fallan (`backup_error` en `/api/status`) y el cron no corre (sin ingesta ni alertas) |
| `FIRMS_MAP_KEY` | Clave de NASA FIRMS para la ingesta VIIRS (detecciones de 375 m) | Secreto de GitHub Actions y secreto del Worker (líneas 52 y 95); en local/VPS va en `.env` | Tras una exposición (OPS-12: la primera rotación es esta) o anual | Ingesta VIIRS detenida: se ve en *Mapa → Estado de las fuentes* y en `/api/status`; GOES sigue funcionando |

### Procedimiento (el mismo para los tres)

1. Genera el valor nuevo en tu equipo, sin mostrarlo: `openssl rand -hex 32` o `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Actualiza **todos** los lugares que correspondan:
   - GitHub → **Settings → Secrets and variables → Actions**: edita el secreto con el valor nuevo.
   - Cloudflare directo (sin esperar un despliegue): `cd deploy/cloudflare && npx wrangler secret put <NOMBRE>`.
   - Si aplica, el `.env` del VPS o entorno local.
3. Vuelve a desplegar cuando el secreto llegue al contenedor por el workflow (los tres casos de la tabla: el Worker se los pasa al contenedor como variables): **Actions → Desplegar en Cloudflare → Run workflow**. Si solo pusiste el secreto con `wrangler secret put`, el despliegue sigue siendo necesario para que el contenedor reciba el valor nuevo — el paso de «Secretos del Worker» no sobreescribe lo que ya existe.
4. Verifica según el secreto:
   - `ADMIN_TOKEN`: entra a `https://…/admin` con el token nuevo.
   - `INTERNAL_TOKEN`: en `/api/status` un ciclo de respaldo termina sin `backup_error` (espera al ciclo de 10 min o reinicia el contenedor con un despliegue).
   - `FIRMS_MAP_KEY`: en `/api/status` (o *Mapa → Estado de las fuentes*) aparecen detecciones VIIRS recientes tras un ciclo.
5. Descarta el valor viejo: si salió en un chat o captura, bórralo ahí también y considera el incidente cerrado solo después del paso 4.

Notas:

- Las claves VAPID **no** se rotan sin asumir que cada navegador tendrá que volver a suscribirse (viven en la tabla `kv` de la base, §2). Rotarlas es una decisión aparte, no parte de este calendario.
- `DB_ENC_KEY` (cifrado del respaldo, SEC-06) no se rota con este procedimiento: cambiarla invalida los respaldos cifrados existentes en R2. Si se expone, el plan es: respaldo descifrado fuera de R2, clave nueva, reescritura de los objetos.

## 9. Prueba de humo semanal de las fuentes (OPS-02)

El workflow **Salud de las fuentes** corre `.github/scripts/fuentes_salud.py` cada lunes 12:00 UTC (y con `workflow_dispatch`): sondeos GET acotados que avisan en el run si una fuente deja de responder o cambia de formato. Desde el 19 de octubre de 2026 cubre nueve fuentes; las incorporadas en esa fecha son:

- CONAF · Botón Rojo — `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query`.
- Repositorio público de GEPRIF — `raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv`.
- Rayos GLM de GOES-19 — `GLM-L2-LCFA` en `noaa-goes19.s3.amazonaws.com` (`/api/opendata/lightning.geojson`).
- Humo ABI-L2-ADPF de GOES-19 — `ABI-L2-ADPF` en `noaa-goes19.s3.amazonaws.com` (`/api/opendata/smoke.geojson`).

Si la prueba o el monitoreo ya reportan una caída, el paso siguiente es el [§12](#12-incidente-en-producción-los-primeros-10-minutos).

## 10. Sonda de producción (OPS-01 · QA-08)

En un comando revisa lo que ve un vecino en producción, sin abrir cuatro páginas a mano:

```bash
python scripts/local/smoke_produccion.py
python scripts/local/smoke_produccion.py --url http://127.0.0.1:8000   # otro origen
python scripts/local/smoke_produccion.py --json                        # salida para máquinas
```

Solo hace peticiones **GET** y no escribe nada. En menos de 20 s comprueba:

- `/`, `/web/js/app.js` y `/manifest.webmanifest`: 200, tipo de contenido razonable y cuerpo no vacío.
- `/api/status`: datos frescos (`freshness.stale` falso y `age_seconds` < 1800) y `failures_24h` vacío o solo de productos sin impacto.
- `/api/observations?bbox=-75,-56,-66,-17`: 200 con detecciones (`points` no vacío).
- `/api/incidents` y `/api/panorama`: 200 con JSON válido.
- `/web/sitemap.xml` (la URL a la que apunta `robots.txt`): 200.

Cada línea trae el estado (`OK`, `LENTA` si tardó más de 2 s, `ERROR` si respondió distinto de 200 o no respondió), los milisegundos y el detalle. Si algo falla, debajo aparece el problema en palabras y el **arreglo sugerido**; la última línea es `RESULTADO: ...`. Sale con código 0 solo si todo está en verde, así que sirve en un `if` o en un cron.

Un 404 en una ruta que sí existe en `main` (por ejemplo `/api/panorama`) apunta a un despliegue pendiente: revisa OPS-19. Con `--json` la salida es un objeto con `ok`, `sondas`, `problemas` y `resultado`, sin la línea final.

## 11. Salud por fuente (AUTO-15)

Cuando la aplicación se ve vacía o una fuente lleva rato sin entregar, este informe dice cuál es, desde cuándo y qué hacer, sin abrir `/api/status` a mano:

```bash
python scripts/local/salud_fuentes.py                 # tabla para personas
python scripts/local/salud_fuentes.py --json          # objeto para máquinas
python scripts/local/salud_fuentes.py --db data/brasa.db   # otra base (por ejemplo, un respaldo)
```

Lee la base local (`ingest_runs`, `observations` y las marcas `kv` de la ingesta), no hace red ni cambia datos. Por fuente (`NASA FIRMS`, `NOAA GOES`, `CONAF`, `DMC`, `Open-Meteo`, `GLM`, `humo ADPF`) muestra el último dato, la última corrida y su resultado, el error más reciente, los minutos de atraso y una columna **Arreglo** con la acción concreta.

| Veredicto | Qué significa |
|---|---|
| `al día` | La última corrida terminó bien y está dentro de la cadencia de la fuente. |
| `atrasada` | Hay un éxito reciente, pero la última corrida falló o la fuente se pasó de su cadencia. |
| `caída` | La última corrida falló y no hay un éxito dentro de la cadencia. |
| `nunca corrió` | No hay corridas ni datos de esa fuente en la base. |

**Cuándo usarlo.** Antes de desplegar (junto a la lista de verificación de la §7) y cuando la aplicación se ve vacía: distingue «no hay incendios» de «la ingesta dejó de traer datos». El último dato solo aparece en FIRMS y GOES, las fuentes que escriben en `observations`; en CONAF, DMC, Open-Meteo, GLM y humo va `—` porque su dato vive en otras tablas (o se sirve a pedido) y la corrida es la señal de salud.

Sale con código 1 si alguna fuente programada no está al día y 0 si todas lo están, así que sirve en un `if` o en un cron. GLM y humo ADPF se sirven a pedido y no dejan corridas en la base: se informan como `nunca corrió`, pero no deciden el código de salida porque no tienen cadencia que cumplir; para ellas el chequeo es el workflow semanal de la §9.
## 12. Incidente en producción: los primeros 10 minutos

> Se lee de arriba abajo **según lo que ve la persona**, no según lo que creemos que falló. Ningún paso de aquí modifica nada: GET a producción y consultas a GitHub. Para arreglar, después, mandan la §7 (diagnóstico previo y reversión) y la §8 (secretos).

**Primer comando: la sonda de la §10.** En menos de 20 s recorre lo que ve un vecino y sugiere el arreglo de lo que falle:

```bash
python scripts/local/smoke_produccion.py
```

Si todo sale en verde y la persona igual ve el mapa vacío, el problema es de una fuente concreta o de interfaz: sigue en la §12.1. Si falla la página o la API, salta a la §12.4. Para separar «la app está viva» de «los datos no llegan» sin el script, el GET más barato (no consulta ninguna fuente externa):

```bash
curl -s https://brasa-chile.ddiegosebastianbb.workers.dev/api/health
```

Si responde `{"status": "ok", …}`, el Worker y el contenedor están vivos y el problema es de datos o de una fuente.

**El estado completo**, con tres corridas por producto (lo mismo que consulta el monitoreo cada 15 minutos):

```bash
curl -s "https://brasa-chile.ddiegosebastianbb.workers.dev/api/status?history=3"
```

El borde guarda una copia de `/api/status` por 30 s y puede servirla vencida hasta 10 min (cabecera `X-Brasa-Cache`); por eso el que prueba que el contenedor responde es `/api/health`, no `/api/status`.

**El mismo veredicto que usa el monitoreo**, sin esperar a que abra el issue. Imprime las condiciones o `sano`, y si hay alerta deja `alerta.md` en el directorio actual:

```bash
python .github/scripts/monitoreo.py
```

### 12.1 El mapa está vacío o la píldora dice «Datos de hace X min»

La píldora de la cabecera usa la misma regla que el servidor: 30 minutos (`stale_after_s` = 1800 en `/api/status`, `backend/freshness.py`). En este orden, los tres veredictos que abren el issue, más el caso en que no hay veredicto, y qué se mira en cada uno:

1. **Datos estancados** (`freshness.stale: true`): los datos llevan más de 30 min, o no hay marca (`last_ingest_at` en `null`). Mira `freshness.age_seconds` contra `stale_after_s`, después `last_ingest_at` y `last_cycle.finished_at`: si el ciclo termina pero la marca no avanza, el ciclo corre y las dos fuentes satelitales fallan a la vez. Ojo, la marca solo se actualiza si fallan **menos de dos** fuentes (`backend/services.py`), así que con una sola caída `stale` puede seguir en `false`. `newest_observation` da la edad real del mapa por fuente: una consulta correcta (`runs[].ok`) no significa datos nuevos.
2. **Un producto con tres fallos seguidos** (`history`): el veredicto exige al menos tres registros y sus tres últimas corridas con `ok: false`. Dice qué fuente está caída; `runs` muestra su último `message` (el error de la propia ingesta) y `last_ok_at`, y `failures_24h` resume la ventana con `runs`, `failed`, `last_failed_at` y `last_error` (recortado a 160 caracteres). Un fallo suelto es ruido: la pasada siguiente suele funcionar.
3. **Respaldo fallido** (`last_cycle.backup: false`): `brasa.db` no se respaldó a R2. Los datos siguen fluyendo y el mapa no se degrada; lo que está en riesgo son los datos de las personas (lugares y avisos), no las detecciones. `work_backup: false` no es señal: `work.db` es reconstruible.
4. **La sonda no respondió** (red, HTTP distinto de 200 o JSON inválido): el script sale con error y el run queda en rojo. No hay veredicto: es «no sabemos», no «todo bien». Se repite el primer comando a mano; si tampoco responde, se sigue en la §12.4.

Los campos que no son veredicto pero explican un hueco: `goes_missing` y `goes_gap` (faltan barridos de GOES en la última hora; se esperan 6 y el aviso se enciende con más de 2), `firms_configured` (si es `false` no hay clave de FIRMS y VIIRS no se ingiere **sin dejar corrida fallida**: es una caída silenciosa que se arregla en los secretos, §8) e `incidents_open` (conteo por estado).

Si el mapa está vacío pero el estado está fresco, separa dato de interfaz con dos GET:

```bash
curl -s "https://brasa-chile.ddiegosebastianbb.workers.dev/api/observations?hours=48"
```

```bash
curl -s "https://brasa-chile.ddiegosebastianbb.workers.dev/api/incidents?hours=48"
```

`points` vacío mientras `runs[].ok` es `true` y `n_records` es mayor que cero significa que la fuente responde pero no hay calor en Chile (posible, raro en enero) o que todo se deduplicó. `points` con datos y el mapa vacío es interfaz (capa apagada, zoom, copia del navegador), no un incidente de producción: no se despliega nada por eso. Y si `/api/status` dice fresco mientras la persona ve «Datos de hace 40 min», la píldora está mostrando la copia guardada por el service worker (`X-Brasa-Cached-At`) o la copia vencida del borde (`X-Brasa-Cache: stale`): tampoco es una caída.

### 12.2 Una fuente está caída

Los productos son los que aparecen en `runs` y `history` de `/api/status` (los de producción en octubre de 2026).

| Fuente | Producto en `/api/status` | Qué se degrada | Qué sigue funcionando |
|---|---|---|---|
| NASA FIRMS (VIIRS NOAA-20 y NOAA-21) | `VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT` | El detalle de 375 m; cada satélite pasa unas 2 veces al día y las detecciones llegan con 1–3 h de retraso | GOES-19 cada 10 min; el mapa, los incidentes y los avisos siguen |
| NOAA GOES-19 | `GOES19_FDCF` (y `ABI-L2-FDCF` cuando falla el listado S3) | El barrido completo cada 10 min; se ve en `goes_missing` y `goes_gap` | FIRMS sigue, pero con pasadas escasas: el mapa queda casi congelado hasta la próxima |
| CONAF · Botón Rojo | `BOTON_ROJO` | La capa de riesgo oficial del día | El 30-30-30 propio y los avisos satelitales |
| CONAF · incendios (GEPRIF) | `CONAF_INCENDIOS` | Los incendios oficiales y su asociación con incidentes; sin CONAF nada pasa a «confirmado» | Las detecciones y sus estados satelitales (`anomalia`, `posible`, `reportado`) |
| Open-Meteo | No tiene producto propio: se ve en `risk_computed_at`, `last_cycle.risk_error` y `open_meteo` | Pronóstico, FWI, lluvia y el viento de los avisos. Sin viento no se dispara la regla «el viento sopla desde el foco hacia el lugar»; las de distancia (≤ 2 km, y ≤ 5 km con riesgo alto o extremo) siguen, con el riesgo del último cálculo guardado. La vista de Riesgo puede decir «Aún no hay pronóstico» | El resto de los avisos y el mapa |
| DMC | `DMC_CAP` | Los avisos de viento y calor que se suman al riesgo | Todo lo demás |

**La regla de oro: «no vemos calor» no es «no hay fuego».** Con una fuente satelital caída el mapa se vacía porque estamos ciegos, no porque no haya fuego; la interfaz ya lo dice cuando falta GOES. Vale para el aviso a la gente, para el issue y para cualquier respuesta pública.

El informe de la §11 da el mismo veredicto por fuente (`al día`, `atrasada`, `caída`) sobre una base local o un respaldo, sin red. Para sondear las fuentes en vivo, la prueba de la §9 (solo lectura: no toca datos ni despliega):

```bash
gh workflow run fuentes-salud.yml --ref main
```

```bash
gh run list --workflow fuentes-salud.yml --limit 5
```

```bash
gh run view <id> --log
```

### 12.3 Errores 5xx o lentitud

1. Separa app de fuente: `/api/health` no consulta nada externo; `/api/status` lee la base y las corridas de ingesta.
2. Un `503` con `{"detail": "El servidor de BRASA está iniciando. Intenta en unos segundos."}` y `Retry-After: 5` significa que el contenedor está despertando o reiniciando (se suspende a los 12 min sin uso). La app reintenta sola (hasta siete veces, 2,5 s entre intentos) y muestra «Conectando…». Espera uno o dos minutos antes de concluir nada.
3. Lento pero 200: mira `X-Brasa-Cache`. `hit` o `miss` es la copia del borde funcionando (45 s en `/api/observations` y `/api/incidents`, 60 s en `/api/official-fires` y `/api/risk`, 30 s en `/api/status`). `stale` significa que el contenedor no respondió y el borde sirve la última copia, que vive hasta 10 min. Si `stale` se mantiene pasados esos 10 min, el contenedor está caído: §12.4 y §7.
4. Un 5xx en una sola ruta: `failures_24h[producto].last_error` y las banderas `*_error` de `last_cycle` (por ejemplo `risk_error`, `fwi_error`, `official_error`, `boton_rojo_error`, `dmc_error`, `rain_error`, `snapshot_error`, `daily_brief_error`) dicen qué paso del ciclo falló. Son `true` cuando falló; `restore_error` y `backup_error` traen el texto.
5. Sin acceso a los registros del contenedor, el diagnóstico del repo es el que se lee: workflow **Diagnóstico en Cloudflare**, de solo lectura (consulta `/api/health`, `/api/status` y las cabeceras de seguridad) y publica el resultado como anotaciones.

```bash
gh run list --workflow diagnostico-cloudflare.yml --limit 5
```

```bash
gh run view <id> --log
```

```bash
gh api repos/falopass/brasas/check-runs/<job_id>/annotations
```

6. **Qué no tocar**: no redesplegar «para ver si se arregla», no revertir por reflejo (la §7 pide diagnóstico previo y reversión ya probada), no reiniciar el contenedor a mano, no tocar `main`, no cambiar secretos y no tocar la base. Si el problema empezó justo después de un despliegue, el sospechoso es ese despliegue: anota el commit anterior antes de mover nada y sigue la §7.

### 12.4 El sitio no carga

Hay tres piezas distintas: el Worker (sirve la página), el contenedor (responde la API) y el service worker del navegador. Dos GET separan las dos primeras:

```bash
curl -sI https://brasa-chile.ddiegosebastianbb.workers.dev/
```

```bash
curl -s https://brasa-chile.ddiegosebastianbb.workers.dev/api/health
```

- **La página responde y `/api/health` no**: el Worker está bien y el contenedor no. La app muestra «Conectando…» y reintenta; es el caso de la §12.3.
- **Ninguna responde**: el Worker o Cloudflare. Antes de tocar nada, mira el estado de Cloudflare y los últimos despliegues; si uno está en vuelo o falló, no se lanza otro encima.
- **La página y la API responden, pero la persona ve una versión vieja**: es el service worker (`web/sw.js`). Sirve la interfaz con caché primero y la API con red primero; el despliegue reemplaza `const VERSION = 'brasa-dev'` por el hash del commit y, al activarse, borra las cachés anteriores. Se actualiza solo: basta cerrar todas las pestañas y volver a entrar. No es un incidente y no se despliega para «refrescarlo».
- **La copia del borde cubre solo cinco rutas de la API** (`/api/observations`, `/api/incidents`, `/api/official-fires`, `/api/risk` y `/api/status`): si lo que no carga es el HTML o `/sw.js`, la caché del borde no es la causa.

Los últimos despliegues, sin lanzar ninguno:

```bash
gh run list --workflow deploy-cloudflare.yml --limit 5
```

### Qué decirle a la gente

Tres frases listas, sin prometer frescura que no hay. Se usan tal cual, en el aviso, en el issue o en el chat:

1. «Estamos revisando los datos. Mientras tanto, la aplicación puede mostrar información de hace un rato; para decisiones, usa CONAF y SENAPRED.»
2. «Ahora no vemos calor porque una de nuestras fuentes está caída. Eso no significa que no haya fuego: si ves humo o llamas, avisa.»
3. «Si ves humo o llamas, llama al 130 (CONAF) o al 132 (Bomberos) y sigue las instrucciones de SENAPRED.»

### Qué no hacer

- **No inventar datos** ni completar a mano lo que falta, ni en la base, ni en el mapa, ni en el issue: un hueco se declara y se explica.
- **No desplegar en caliente** ni revertir por reflejo: la §7 pide diagnóstico previo y reversión conocida, y en temporada rige el congelamiento de la §7.
- **No tocar `main`**: ni commits directos, ni force, ni merge sin autorización. Rama y PR.
- **No pedir a nadie que se registre**: BRASA no tiene cuentas; el dispositivo se crea solo. Si hay que avisar, se comparte el enlace del lugar.
- **No sondear producción con POST ni borrar nada**: contra producción, solo GET.
