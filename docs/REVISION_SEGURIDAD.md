# Revisión de seguridad — SEC-13

Recorrido OWASP de la API (FastAPI), el Worker de Cloudflare y el service worker, antes de la
temporada. Fecha: 2026-10-19. Alcance: `backend/routes/*`, `backend/security.py`,
`backend/reports.py`, `backend/storage.py`, `backend/notify/*`, `deploy/cloudflare/src/*`,
`web/sw.js`, `web/js/*`. Sin cambios de código: solo el informe.

Modelo de amenaza principal: proteger los datos personales (lugares, avisos, reportes con foto),
la disponibilidad del contenedor único y la cuota compartida de NASA FIRMS, que alimenta tanto la
ingesta (`backend/services.py:253`) como las consultas públicas.

## Hallazgos

### 1. `POST /api/cases/{id}/polar` gasta la cuota FIRMS sin límite ni chequeo de caché — media
- **Dónde:** `backend/routes/community.py:326-340`.
- **Qué pasa:** ruta pública que descarga el archivo científico de FIRMS con la clave del servidor.
  El GET sí lee la caché (`community.py:323`), pero el POST vuelve a llamar a `firms.fetch_hotspots`
  aunque el caso ya esté cargado. No tiene `limiter.check` ni tope en el borde (`edgeLimiter` solo
  cubre `/api/reports` y `/api/subscribers`, `deploy/cloudflare/src/index.ts:245-249`).
- **Por qué importa:** la misma `FIRMS_MAP_KEY` alimenta la ingesta principal cada 10 min
  (`backend/services.py:253`). Agotar la cuota diaria de la cuenta deja a BRASA sin detecciones
  de órbita polar: denegación de servicio sobre la fuente, no sobre el servidor.
- **Explotabilidad:** `for i in {1..N}; do curl -X POST .../api/cases/VALPARAISO_2024/polar; done`.
  Cada llamada cuesta una o más consultas a FIRMS por fuente del caso.
- **Arreglo:** devolver lo cacheado si `cache_get(f"case-firms:{id}")` ya existe, y/o
  `limiter.check(request, "case-polar", 10, 3600)`.

### 2. Los límites por IP no cubren las lecturas pesadas ni el resto de los POST — media
- **Dónde:** `deploy/cloudflare/src/index.ts:245-249,284-295` (borde) y
  `backend/routes/common.py:49-81` (app).
- **Qué pasa:** en el borde solo se limitan `POST /api/reports` (10/min) y `POST /api/subscribers`
  (30/min). En la app solo hay topes en `/api/reports`, `/api/subscribers`, `/api/shared`,
  `/api/explore` y `/api/alerts/test`. El resto sale libre: `GET /api/observations?hours=336` con
  `bbox` variable es un barrido de hasta 20.000 filas por llamada (`public.py:126-162`) y su URL
  única siempre falla la caché del borde (`index.ts:222-224`); `/api/nearby-services`
  (`personal.py:260-278`) pega a Overpass; `place_summary` consulta el viento aguas arriba.
- **Por qué importa:** el backend es un solo contenedor (`max_instances: 1`, wrangler.jsonc). Un
  cliente con consultas caras repetidas puede dejar el mapa lento o caído justo en un megaincendio.
- **Explotabilidad:** razonamiento suficiente: no hay barrera entre un bucle de GETs y el
  contenedor. La caché del borde solo absorbe las 5 rutas fijas de `EDGE_CACHE_TTL`
  (`index.ts:147-153`).
- **Arreglo:** un `ratelimits` genérico para `/api/*` en el borde (o `limiter.check` suave por IP
  en un middleware) con holgura para uso real.

### 3. `ADMIN_TOKEN` único, sin tope de intentos ni revocación por persona — media
- **Dónde:** `backend/routes/common.py:41-46`; rutas `community.py:182,208,243`.
- **Qué pasa:** un solo secreto compartido gobierna toda la moderación. La comparación es de tiempo
  constante (`hmac.compare_digest`, bien), pero no hay `limiter.check` ni tope en el borde para
  `/api/admin/*`: la fuerza bruta en línea es ilimitada. Si el token se filtra, quien lo tenga
  aprueba o borra reportes y ve fotos no verificadas (`community.py:152-158`); al ser compartido,
  no se puede revocar a una sola persona ni saber quién actuó (sin `moderation_log`).
- **Por qué importa:** la cola de moderación es la barrera que decide qué se publica como
  «verificado» a miles de personas.
- **Explotabilidad:** si `ADMIN_TOKEN` es un secreto fuerte aleatorio, la fuerza bruta es
  inviable; el riesgo real es filtración (se guarda en `sessionStorage`, `web/js/admin.js:4,78`) y
  la falta de atribución. Ya cubierto en backlog: SEC-10 (tokens individuales + log), SEC-12
  (rotación).
- **Arreglo:** agregar `limiter.check` por IP en `admin()` como cortafuegos barato; SEC-10 y
  SEC-12 siguen siendo el arreglo de fondo.

### 4. `INTERNAL_TOKEN` solo protege la base completa y las fotos — baja
- **Dónde:** `deploy/cloudflare/src/index.ts:45-66,279-282`; `backend/storage.py:31-42`;
  `backend/routes/internal.py:19-22`.
- **Qué pasa:** `GET /_internal/storage/db/brasa.db` con el token entrega la base entera (tokens de
  dispositivo, lugares, endpoints push, reportes). La validación es correcta: prefijos `db/` y
  `photos/`, rechazo de `..` tras decodificar (`index.ts:46-49`), comparación sin fuga de tiempo
  (`guardas.ts:5-10`, probada en `test/guardas.test.mjs`), `/api/internal/*` cerrada al público
  (`index.ts:278`) y con `compare_digest` en el backend (`internal.py:21`).
- **Por qué importa:** es un punto único de compromiso con impacto total. El respaldo viaja sin
  cifrar a R2 (SEC-06 abierto lo cubre).
- **Explotabilidad:** solo si el secreto se filtra; no hay canal público que lo exponga.
- **Arreglo:** rotación documentada (SEC-12) y SEC-06 (cifrar el respaldo antes de subirlo).

### 5. El limitador confía en `X-Forwarded-For` y su memoria crece sin purga — baja
- **Dónde:** `Dockerfile:20` (`--forwarded-allow-ips "*"`), `backend/routes/common.py:53,64`.
- **Qué pasa:** la clave del limitador es `request.client.host`, que uvicorn toma del
  `X-Forwarded-For`. En Cloudflare está bien: el Worker lo reescribe con `CF-Connecting-IP`
  (`index.ts:253`) y el contenedor no es público. En un despliegue VPS directo cualquiera falsifica
  la cabecera y esquiva los topes (ya registrado como FIX-20). Además `self.hits` solo purga la
  cola de una IP cuando esa IP vuelve a llamar: las entradas viejas se acumulan para siempre.
- **Por qué importa:** evasión de límites fuera de Cloudflare y crecimiento lento de memoria en el
  contenedor (una entrada por IP distinta que haya llamado, para siempre).
- **Arreglo:** purgar `self.hits` de entradas vacías al revisar; FIX-20 documenta la variable de
  proxies confiables.

### 6. Turnstile falla abierto y sin secreto no hay verificación — baja
- **Dónde:** `backend/routes/community.py:27-43`; `wrangler.jsonc` (`TURNSTILE_SITE_KEY` vacía).
- **Qué pasa:** si `siteverify` no responde, el reporte entra igual (`community.py:38-41`,
  decisión deliberada y comentada). Y si `TURNSTILE_SECRET` no está configurado, no se verifica
  nada (`community.py:29-30`): el antibot existe pero puede estar apagado en producción sin que
  nadie lo note. En `vars`, `TURNSTILE_SITE_KEY` está vacía.
- **Por qué importa:** bots pueden inundar la cola de moderación, que es trabajo humano.
- **Arreglo:** si se activa Turnstile, registrar en `/api/status` que la verificación está encendida;
  considerar rechazar (no admitir) cuando el secreto existe pero siteverify falla repetidamente.

### 7. El service worker guarda datos personales y `DELETE /api/me` no los invalida — baja
- **Dónde:** `web/sw.js:16,36-44,47-61`; `backend/routes/common.py:31`.
- **Qué pasa:** `/api/places`, `/api/alerts`, `/api/reports/mine` y `/api/shared` se guardan en el
  dispositivo para funcionar sin señal (decisión deliberada, comentada en `sw.js:15`). La
  separación entre usuarios depende de que el Cache API honre `Vary: X-Brasa-Token`
  (`common.py:31`). Además, al borrar la cuenta (`DELETE /api/me`) solo se invalida la caché de
  `/api/places` (`sw.js:36-41`): avisos y «mis reportes» quedan guardados.
- **Por qué importa:** en un dispositivo compartido, datos de la sesión anterior pueden quedar
  servibles sin conexión tras el borrado.
- **Explotabilidad:** baja — mismo dispositivo, mismo navegador; pero el borrado legal (SEC-02)
  promete «todo fuera» y la copia local queda.
- **Arreglo:** al recibir `DELETE /api/me` (o un 401), vaciar `API_CACHE` completa en el SW.

### 8. `/docs` y `/openapi.json` públicos en producción — baja
- **Dónde:** `deploy/cloudflare/src/index.ts:296`; `backend/main.py:41`.
- **Qué pasa:** el esquema completo de la API (rutas, parámetros, modelos de moderación) es público.
- **Por qué importa:** facilita el reconocimiento a un atacante; no expone datos.
- **Arreglo:** bloquear ambas rutas en el Worker o `openapi_url=None` en producción.

### 9. Suscripción push a un endpoint arbitrario: POST firmado VAPID a cualquier URL — baja
- **Dónde:** `backend/routes/personal.py:281-287`; `backend/notify/webpush.py:47-56`.
- **Qué pasa:** basta `https://` para registrar un endpoint; el servidor le hará POST ciegos
  (VAPID + payload cifrado, sin devolver la respuesta). Un suscriptor puede apuntarlo a un host
  interno (`https://169.254.169.254/…`, `https://localhost:…`).
- **Por qué importa:** SSRF ciego de solo escritura. En el contenedor de Cloudflare no hay
  metadatos de instancia ni red interna alcanzable, así que el impacto hoy es nulo; en otro
  despliegue podría pegarle a servicios internos.
- **Arreglo:** opcional — lista de dominios de push conocidos (mozilla, google, apple) o nota en
  OPERACION.

### 10. Cabos sueltos menores — baja
- **Telegram sin validar ni tope:** `handle_update` (`backend/notify/telegram.py`, bloque
  `location`) inserta lugares sin `MAX_PLACES` ni el `PlaceIn` de coordenadas/kind de la API web;
  los `link_code` de vinculación no caducan (`personal.py:301`). Vía webhook exige el secreto
  (`internal.py:46-48`), así que el spam real requiere un chat de Telegram, no falsificación.
- **`notificationclick` abre la URL del payload:** `web/sw.js:89-96` resuelve
  `event.notification.data.url` contra el origen pero admite absolutas externas. Solo el servidor
  puede emitir pushes (VAPID), así que exige servidor comprometido; endurecer abriendo solo rutas
  relativas.
- **Webhook de Telegram con tope de cuerpo (cerrado):** `internal.py:50-67` — ruta
  pública; el secreto en cabecera se valida primero (403), `Content-Length` sobre 1 MiB
  (`TELEGRAM_MAX_BODY`) responde 413 sin leer el cuerpo, sin la cabecera se lee con tope
  y un JSON inválido o no-objeto responde 400. Cubierto por
  `tests/test_telegram_webhook_limite.py`.
- **CSP amplia en datos:** `connect-src https:` e `img-src https:` (`backend/security.py:37-39`,
  replicada en `index.ts:119`) permitirían exfiltración si apareciera un XSS; `script-src` sigue
  fuerte (sin `unsafe-inline`, con hashes y `'unsafe-eval'` solo por Cesium, justificado en el
  docstring). Endurecimiento opcional, no un agujero.

## Verificado sin hallazgo (anexo)

- **Autorización por recurso:** todas las rutas personales filtran por `subscriber_id`
  (`personal.py:110-150,306-349`); `/api/reports/mine` por `sub["id"]` (`community.py:277`); foto de
  reporte no verificado exige admin (`community.py:157-158`); `/api/shared/{token}` expone solo
  `SHARE_FIELDS` (`personal.py:224,255`).
- **Tokens:** `secrets.token_urlsafe(24)` ≈ 192 bits (`personal.py:58`); share 18 bytes
  (`personal.py:233`). Longitud mínima 20 rechaza tokens cortos (`common.py:33`).
- **Tiempo constante:** admin, interno, Telegram y Worker (`common.py:45`, `internal.py:21,47`,
  `guardas.ts:9`, con prueba).
- **Fotos:** re-codificación JPEG sin EXIF, ≤8 MB, ≤1600 px, nombre `uuid.jpg` del servidor
  (`reports.py:51-67`, `community.py:72-86`). Listado público solo `verificado`, coordenadas
  redondeadas a ~100 m (`community.py:134-149`).
- **SQL:** todo parametrizado; los únicos `f"…"` llevan marcadores `?` generados
  (`community.py:220-227`, `opendata.py:118-123`).
- **Errores:** mensajes fijos; FIRMS evita la URL porque contiene la clave
  (`backend/providers/firms.py:111-113`); 500 genérico de FastAPI.
- **Caché del borde:** solo las 5 GET públicas de `EDGE_CACHE_TTL`, clave = URL sin cabeceras, no
  guarda respuestas con `set-cookie` ni errores (`index.ts:168-179,222-239`).
- **Cabeceras:** CSP idéntica en Worker y backend con prueba (`tests/test_security.py`); HSTS,
  `frame-ancestors`, `nosniff` en el Worker (`guardas.ts:13-26`); CORS ausente (mismo origen).

## Por verificar

- **Entropía real de `ADMIN_TOKEN`/`INTERNAL_TOKEN`/`TELEGRAM_WEBHOOK_SECRET`** en producción
  (largo y aleatoriedad). Solo se sabe que existen como secretos; si son cortos o escritos a mano,
  el hallazgo 3 sube a alta.
- **Que `request.client.host` en el contenedor sea la IP real** (CF-Connecting-IP vía el Worker) y
  no una IP interna compartida: probar con una ráfaga desde una IP conocida o revisar logs.
- **Que el Cache API respete `Vary: X-Brasa-Token`** en los navegadores objetivo (WebKit antiguo,
  modo privado): dos tokens en el mismo perfil deben ver solo sus datos.
- **Versiones de `python-multipart` y Pillow** frente a CVEs (el formulario multipart es entrada
  pública); cubierto por la auditoría semanal SEC-09, confirmar que corre.
- **Tamaños máximos de respuesta de terceros:** S3 (GOES/GLM/humo), FIRMS CSV y CONAF se leen
  enteros en memoria sin tope (`goes.py:196-200`, `glm.py:44-48`, `smoke.py:57-61`,
  `firms.py:101-115`, `conaf.py:174-182`). Un proveedor comprometido o un error upstream podría
  inflar la memoria del contenedor; bajo porque las URLs son fijas y oficiales.
- **Parseo XML de la DMC** (`backend/providers/dmc.py:77-96`): `ElementTree` sobre XML externo;
  depende del `pyexpat` del sistema para límites de expansión de entidades.
