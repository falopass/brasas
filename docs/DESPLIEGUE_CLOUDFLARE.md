# Despliegue en Cloudflare (Workers + Containers)

## Cómo queda montado

```
Navegador ──HTTPS──► Worker «brasa-chile» (borde de Cloudflare)
                      ├─ /, /web/*, /sw.js, /admin   → PWA estática (Workers Assets): carga al instante
                      ├─ /api/*                      → contenedor Python (FastAPI) · 1 instancia «basic»
                      ├─ /api/internal/*             → bloqueado al público
                      └─ Cron cada 10 min            → /api/internal/tick: GOES + FIRMS → alertas → riesgo
Contenedor ──https://<URL pública>/_internal/storage/… + INTERNAL_TOKEN──► Worker ──► R2 «brasa-chile-datos»
                                         db/brasa.db  (lugares, suscripciones, alertas, reportes, claves)
                                         db/diario/AAAA-MM-DD.db (copia diaria, se conserva 24 h)
                                         db/work.db.gz (observaciones e incidentes)
                                         photos/<id>.jpg (fotos de reportes)
                  Las claves db/* reposan cifradas (AES-256-GCM, SEC-06); photos/* va en claro.
```

- El disco del contenedor es efímero. Los **datos de las personas** viven en una base SQLite pequeña que se sube a R2 unos segundos después de cada cambio, al final de cada ciclo y al apagarse, y que se restaura al arrancar. Las observaciones y el riesgo se reconstruyen solos con la ingesta.
- El contenedor no guarda credenciales de R2: escribe a `<PUBLIC_BASE_URL>/_internal/storage/<clave>` con su `INTERNAL_TOKEN`; el Worker valida el token (en tiempo constante, 403 si no coincide) y lee o escribe en R2. Antes se usaba la intercepción de salida hacia `http://storage.brasa`, pero en producción esas solicitudes salían a internet y fallaban con 530, así que cada reinicio perdía los datos.
- Si R2 no respondiera al arrancar, el contenedor **no sobrescribe** el respaldo con una base vacía: reintenta la restauración en cada ciclo.
- Telegram funciona por **webhook**: no hace falta que el contenedor esté siempre despierto para recibir mensajes.

Medido en una prueba local con la misma imagen: un ciclo completo con datos reales de GOES tarda unos 6 segundos y la memoria máxima es de unos 120 MB (la instancia `basic` tiene 1 GiB).

## Requisitos

1. Una cuenta de Cloudflare con el plan **Workers Paid** (Containers no está en el plan gratuito).
2. Este repositorio en GitHub; el despliegue lo hace GitHub Actions, que construye la imagen Docker.

## Paso a paso

### 1. Token de API de Cloudflare

En el panel de Cloudflare: **My Profile → API Tokens → Create Token** → plantilla **«Edit Cloudflare Workers»**. Verifica que incluya, a nivel de cuenta:

- Workers Scripts: Edit
- Workers R2 Storage: Edit
- Containers: Edit (si la plantilla no lo trae, agrégalo)
- Account Settings: Read

Copia también tu **Account ID** (aparece en la portada de *Workers & Pages*).

### 2. Secretos y variables en GitHub

En `github.com/falopass/brasas` → **Settings → Secrets and variables → Actions**:

| Tipo | Nombre | Valor |
|---|---|---|
| Secreto | `CLOUDFLARE_API_TOKEN` | El token del paso 1 |
| Secreto | `CLOUDFLARE_ACCOUNT_ID` | Tu Account ID |
| Secreto (recomendado) | `FIRMS_MAP_KEY` | Clave NASA FIRMS (VIIRS 375 m) |
| Secreto (recomendado) | `ADMIN_TOKEN` | Un texto largo y secreto para `/admin` |
| Secreto (opcional) | `TELEGRAM_BOT_TOKEN` | Token de @BotFather |
| Secreto (opcional) | `CESIUM_ION_PUBLIC_TOKEN` | Relieve 3D |
| Variable (opcional) | `TELEGRAM_BOT_USERNAME` | Usuario del bot, sin @ |
| Variable (opcional) | `PUBLIC_BASE_URL` | Solo si usas un dominio propio, por ejemplo `https://brasa.tudominio.cl` |
| Variable (opcional) | `CLOUDFLARE_DEPLOY` | `true` para desplegar en cada push a `main` |

`INTERNAL_TOKEN` y `TELEGRAM_WEBHOOK_SECRET` se generan solos en el primer despliegue y se conservan.

`DB_ENC_KEY` (cifrado del respaldo, SEC-06) lo crea la persona dueña una vez, a mano: `openssl rand -base64 32` y luego `cd deploy/cloudflare && npx wrangler secret put DB_ENC_KEY`. Se conserva entre despliegues. Sin él el Worker **rechaza** las subidas de `db/*` con 500 — la falla se ve en `backup_error` de `/api/status` — en vez de dejar la base en claro.

### 3. Desplegar

**Actions → Desplegar en Cloudflare → Run workflow.** El flujo:

1. corre las pruebas del backend;
2. crea el bucket R2 `brasa-chile-datos` si no existe;
3. construye la imagen y publica el Worker y el contenedor (`wrangler deploy`);
4. carga los secretos.

Al terminar, el registro muestra la URL, por ejemplo `https://brasa-chile.<tu-subdominio>.workers.dev`. La primera visita por HTTPS le enseña esa dirección al backend (enlaces de las alertas y webhook de Telegram), así que en `workers.dev` no hace falta configurar `PUBLIC_BASE_URL`.

> La primera carga de `/api` puede tardar unos segundos mientras el contenedor arranca; la interfaz se ve de inmediato porque se sirve desde el borde.

### 4. Comprobar

- **La versión publicada es la del commit desplegado, no solo que el sitio responde.** `curl -s https://…/api/health | python -c "import json,sys;print(json.load(sys.stdin)['version'])"` debe imprimir exactamente el `VERSION` de `backend/version.py` de ese commit (hoy `0.9.0`). Si no coincide, el despliegue no tomó ese commit: revisa el run de Actions antes de seguir. Importa porque un `{"status":"ok"}` no basta — un build viejo responde ok igual y puede seguir sirviendo datos que el código nuevo ya filtra (caso real: incidentes con centroide fuera de Chile).
- `https://…/api/health` responde `{"status":"ok"}`.
- `/api/status` no trae `backup_error`; si aparece, falta `DB_ENC_KEY` (ver el [paso 2](#2-secretos-y-variables-en-github)).
- A los 10 minutos, en *Mapa → Estado de las fuentes* aparece GOES-19 con una consulta reciente.
- En el panel de R2 aparece `db/brasa.db` después de guardar el primer lugar.
- Logs en vivo: `cd deploy/cloudflare && npx wrangler tail`.

## Despliegue manual (alternativa)

Con Docker Desktop instalado:

```bash
cd deploy/cloudflare
npm ci
npx wrangler login
npx wrangler r2 bucket create brasa-chile-datos
npx wrangler deploy
npx wrangler secret put INTERNAL_TOKEN      # un texto aleatorio largo
npx wrangler secret put FIRMS_MAP_KEY
npx wrangler secret put ADMIN_TOKEN
```

## Costos (orden de magnitud; verifica los precios vigentes)

- Workers Paid: USD 5 al mes, que incluye una cuota de uso de Workers y de Containers.
- El contenedor queda despierto entre ciclos (`sleepAfter = 12m` con el cron de 10 min). Una instancia `basic` encendida todo el mes puede superar la cuota incluida en algunos dólares. Para ahorrar, baja `sleepAfter` a `2m` en `deploy/cloudflare/src/index.ts`: dormirá entre ciclos a cambio de un arranque en frío de algunos segundos en la primera consulta.
- R2: los respaldos pesan kilobytes; el costo es despreciable.

## Protección en el borde

El Worker hace tres cosas antes de tocar el contenedor:

1. **Límite de solicitudes** (OPS-05): los `POST /api/reports` y `POST /api/subscribers` pasan por los `ratelimits` de `wrangler.jsonc` (10 y 30 por IP por minuto; el exceso responde 429). Es la primera defensa: el contenedor y los límites de aplicación del backend (6 reportes/hora y 20 suscripciones/hora por IP) quedan como segunda línea. Ajusta `simple.limit`/`period` en `wrangler.jsonc` si un día hace falta más o menos. Si algún día hay dominio propio (OPS-11), se puede mover a una regla de *Rate Limiting* del dashboard para ver gráficos.
2. **Caché de GET públicos** (OPS-03): `/api/observations`, `/api/incidents`, `/api/official-fires`, `/api/risk` y `/api/status` se guardan 30-60 s en el borde (Cache API). Una respuesta vencida se sigue sirviendo hasta 10 min mientras el borde la refresca en segundo plano, así que un pico no tira abajo el contenedor. Las respuestas llevan `X-Brasa-Cache: hit|stale|miss` para verificarlo en la prueba de carga.
3. **Turnstile invisible** (OPS-05): el formulario de reportes pide un token invisible al borde y el backend lo valida en `siteverify`. Solo activo si hay claves configuradas; sin claves no bloquea nada (todo reporte pasa por moderación de todas formas).

### Configurar Turnstile (lo hace la persona dueña, ~5 min)

1. Panel de Cloudflare → **Turnstile → Add site**: nombre «BRASA Chile», dominio `brasa-chile.<sub>.workers.dev` (y el dominio propio cuando exista), modo **invisible**.
2. Copia la **site key** y el **secret key**.
3. En GitHub → Settings → Secrets and variables → Actions: variable `TURNSTILE_SITE_KEY` con la site key y secreto `TURNSTILE_SECRET` con el secret. El siguiente despliegue los propaga (`--var` y `wrangler secret put`).
4. Alternativa manual: `npx wrangler secret put TURNSTILE_SECRET` y agrega `TURNSTILE_SITE_KEY` a `vars` de `wrangler.jsonc`.

Sin claves (desarrollo local) el widget no se renderiza y el backend acepta el reporte igual: fail-open a propósito, porque cada reporte queda en revisión antes de publicarse.

## Cifrado del respaldo (SEC-06)

Todo lo que el contenedor guarda bajo `db/*` (`brasa.db`, `db/work.db.gz` y las copias diarias) reposa cifrado con AES-256-GCM: el Worker cifra al recibir el PUT y descifra al servir el GET, así que el bucket nunca ve el SQLite en claro. El objeto guardado es `BRASA1` + IV aleatorio + ciphertext. Los objetos escritos antes de este cambio (sin cabecera `BRASA1`) se siguen leyendo tal cual: la transición no rompe la restauración. Las fotos (`photos/*`) no se cifran.

Tras desplegar, comprueba que el respaldo ya no es un SQLite legible:

```bash
cd deploy/cloudflare
npx wrangler r2 object get brasa-chile-datos/db/brasa.db --remote --file /tmp/brasa.enc
head -c 6 /tmp/brasa.enc   # debe decir BRASA1, no «SQLite format 3»
```

Para revisar un respaldo descifrado, con la clave en el entorno (sin pegarla en ningún archivo):

```bash
DB_ENC_KEY=… node -e 'const fs=require("fs"),b=fs.readFileSync("/tmp/brasa.enc");
crypto.subtle.importKey("raw",Buffer.from(process.env.DB_ENC_KEY,"base64"),"AES-GCM",false,["decrypt"])
  .then(k=>crypto.subtle.decrypt({name:"AES-GCM",iv:b.subarray(6,18)},k,b.subarray(18)))
  .then(p=>fs.writeFileSync("/tmp/brasa.db",Buffer.from(p)));'
head -c 16 /tmp/brasa.db   # SQLite format 3
```

## Restaurar un respaldo anterior

1. En R2, copia `db/diario/AAAA-MM-DD.db` sobre `db/brasa.db` (las copias viven 24 h: si ya no está, usa la última disponible o el respaldo en vivo `db/brasa.db`). Ambos objetos están cifrados con la misma clave, así que la copia funciona igual.
2. Reinicia el contenedor (un nuevo despliegue lo hace) para que lo restaure al arrancar.

### Simulacro mensual de restauración (OPS-10)

`scripts/simulacro_restauracion.py` baja `db/brasa.db` y `db/work.db.gz` de R2 con wrangler y verifica la integridad SQLite (cabecera, `integrity_check`, tablas esperadas). El workflow *Simulacro de restauración* lo corre el día 3 de cada mes con los mismos secretos del despliegue; en local:

```bash
export CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=…
python3 scripts/simulacro_restauracion.py
```

> Ojo: desde SEC-06 esos objetos son ciphertext (`BRASA1…`), así que el script reporta «no es una base SQLite» hasta que se adapte para descifrar con `DB_ENC_KEY`. Mientras tanto, el respaldo cifrado se puede verificar a mano con los comandos de la sección anterior.

Si el simulacro falla, el script imprime los pasos para recuperar desde `db/diario/` o el último ciclo.

## Límites conocidos

- **Una sola instancia** (`max_instances: 1`), a propósito: la ingesta y la base son de un solo escritor. Para escalar, separa la ingesta y migra a PostGIS (ver `ARQUITECTURA.md`).
- Durante un despliegue nuevo el contenedor se reinicia: la API puede responder 503 por unos segundos.
- Los mapas base externos (OpenFreeMap, EOX) siguen sus propias condiciones de uso; ver `FUENTES.md`.
