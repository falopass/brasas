# Despliegue en Cloudflare (Workers + Containers)

## Cómo queda montado

```
Navegador ──HTTPS──► Worker «brasa-chile» (borde de Cloudflare)
                      ├─ /, /web/*, /sw.js, /admin   → PWA estática (Workers Assets): carga al instante
                      ├─ /api/*                      → contenedor Python (FastAPI) · 1 instancia «basic»
                      ├─ /api/internal/*             → bloqueado al público
                      └─ Cron cada 10 min            → /api/internal/tick: GOES + FIRMS → alertas → riesgo
Contenedor ──http://storage.brasa/…──► el Worker lo intercepta ──► R2 «brasa-chile-datos»
                                         db/brasa.db  (lugares, suscripciones, alertas, reportes, claves)
                                         db/diario/AAAA-MM-DD.db (copia diaria)
                                         photos/<id>.jpg (fotos de reportes)
```

- El disco del contenedor es efímero. Los **datos de las personas** viven en una base SQLite pequeña que se sube a R2 unos segundos después de cada cambio, al final de cada ciclo y al apagarse, y que se restaura al arrancar. Las observaciones y el riesgo se reconstruyen solos con la ingesta.
- El contenedor no guarda credenciales de R2: escribe a `http://storage.brasa`, que solo existe para él y que el Worker atiende.
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

### 3. Desplegar

**Actions → Desplegar en Cloudflare → Run workflow.** El flujo:

1. corre las pruebas del backend;
2. crea el bucket R2 `brasa-chile-datos` si no existe;
3. construye la imagen y publica el Worker y el contenedor (`wrangler deploy`);
4. carga los secretos.

Al terminar, el registro muestra la URL, por ejemplo `https://brasa-chile.<tu-subdominio>.workers.dev`. La primera visita por HTTPS le enseña esa dirección al backend (enlaces de las alertas y webhook de Telegram), así que en `workers.dev` no hace falta configurar `PUBLIC_BASE_URL`.

> La primera carga de `/api` puede tardar unos segundos mientras el contenedor arranca; la interfaz se ve de inmediato porque se sirve desde el borde.

### 4. Comprobar

- `https://…/api/health` responde `{"status":"ok"}`.
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

## Restaurar un respaldo anterior

1. En R2, copia `db/diario/AAAA-MM-DD.db` sobre `db/brasa.db`.
2. Reinicia el contenedor (un nuevo despliegue lo hace) para que lo restaure al arrancar.

## Límites conocidos

- **Una sola instancia** (`max_instances: 1`), a propósito: la ingesta y la base son de un solo escritor. Para escalar, separa la ingesta y migra a PostGIS (ver `ARQUITECTURA.md`).
- Durante un despliegue nuevo el contenedor se reinicia: la API puede responder 503 por unos segundos.
- Los mapas base externos (OpenFreeMap, EOX) siguen sus propias condiciones de uso; ver `FUENTES.md`.
