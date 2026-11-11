# Dominio propio `.cl` para BRASA (OPS-11)

Checklist paso a paso para pasar de `brasa-chile.ddiegosebastianbb.workers.dev` a un
dominio `.cl` propio. **Nada de esto está ejecutado**: el nombre no está elegido ni
comprado, y el documento usa el marcador `<dominio.cl>` en todos los ejemplos. Es un
procedimiento para la persona dueña — incluye una compra y cambios en paneles que el
agente no puede autorizar ni tocar.

Por qué conviene hacerlo **antes de sumar usuarios** (`docs/backlog/PASOS_DUENO.md`):
tres cosas quedan atadas al origen `workers.dev` — las suscripciones push, la app
instalada (PWA) y el token del teléfono que abre los lugares guardados. Cada persona
que se sume hoy habrá que migrarla después. El detalle está en la sección 6.

Fuentes oficiales consultadas (nov-2026): NIC Chile (`nic.cl`, `clientes.nic.cl`) y la
documentación de Cloudflare (`developers.cloudflare.com`: *Full setup*, *Update
nameservers*, *Workers Custom Domains*).

## Estado y alcance

- [ ] **Pendiente de decisión del dueño:** el nombre (`<dominio.cl>`) y si la app vive
  en el apex o en un subdominio (por ejemplo `app.<dominio.cl>`). Este documento
  asume el **apex**; donde cambie algo se avisa.
- [ ] **Pendiente de compra:** la inscripción del dominio en NIC Chile.
- [ ] **Pendiente de ejecución:** todos los pasos en paneles (NIC Chile, Cloudflare,
  GitHub) y el PR de corte descrito en la sección 4.
- Nada de lo que sigue toca secretos ni datos: la base `brasa.db` es una sola y la
  comparten ambos orígenes, así que el cambio es de **dirección canónica**, no de datos.

## 1. Registrar el `.cl` en NIC Chile (compra, la hace el dueño)

1. Verificar disponibilidad en el buscador de `nic.cl` o en su WHOIS
   (`nic.cl/whois/`). No asumir que un nombre está libre sin consultarlo.
2. Crear cuenta en `clientes.nic.cl` (o entrar con la existente): pide RUN y correo
   del titular. Usar una cuenta a nombre del dueño, con correo que sí se lee — ahí
   llegan renovaciones y avisos.
3. Inscribir `<dominio.cl>`: completar datos del titular, elegir el plazo y pagar.
   La tarifa vigente está publicada en `nic.cl/dominios/tarifas.html`.
4. Al terminar, el dominio queda delegado a los servidores DNS de NIC por defecto.
   Se reemplazan en la sección 3 — no configurar registros ahí, NIC solo gestiona la
   delegación.
5. Guardar comprobante y credenciales en el gestor de contraseñas. **Nada de esto va
   al repositorio** (repo público).
6. Opcional: activar la renovación automática o anotar la fecha de vencimiento; un
   `.cl` vencido deja el servicio abajo y puede perderse.

## 2. Crear la zona en Cloudflare

Requisito previo ya cumplido: la cuenta de Cloudflare del despliegue (Workers Paid).

1. Panel de Cloudflare → **Domains → Onboard a domain** → escribir el apex
   `<dominio.cl>` → plan **Free** (alcanza; el plan de Workers no depende del plan
   de la zona).
2. Cloudflare escanea registros DNS existentes. En un dominio recién inscrito no hay
   nada útil: **revisar y borrar** cualquier registro importado que no se necesite.
3. Cloudflare asigna **dos nameservers** propios (`<nombre>.ns.cloudflare.com`).
   Aparecen en el flujo de alta y después en **Overview** de la zona. Anotarlos
   exactamente como se muestran.

## 3. Apuntar los nameservers en NIC Chile (delegación)

1. En `clientes.nic.cl` → **Mis Dominios** → `<dominio.cl>` → sección
   **Configuración Técnica**.
2. En **Tipo de servicio** elegir **Servidores DNS**, borrar los que vengan por
   defecto y agregar **los dos nameservers asignados por Cloudflare** (botón
   «Agregar Servidor de Nombre» si falta un campo).
3. Aceptar las condiciones y confirmar con **Actualizar datos de dominio**.
4. Esperar la propagación: NIC avisa que puede tomar horas; Cloudflare marca la
   zona como **Active** cuando detecta la delegación (y suele enviar correo).
   Comprobar con `nslookup -type=NS <dominio.cl>` o en el Overview de la zona.

La zona queda activa sin ningún registro que sirva la app todavía: eso se crea solo
en el paso siguiente.

## 4. Dominio personalizado en el Worker `brasa-chile`

Cloudflare llama a esto **Custom Domain**: apunta todo el host al Worker, crea el
registro DNS y emite el certificado TLS automáticamente, sin tocar DNS a mano.
Requisitos: zona activa (sección 3 terminada) y el Worker existente.

1. Panel → **Workers & Pages → brasa-chile → Settings → Domains & Routes → Add →
   Custom Domain** → escribir `<dominio.cl>` → **Add Custom Domain**.
2. En unos minutos `https://<dominio.cl>` ya sirve la app completa (Worker + assets
   + contenedor), porque es el mismo despliegue.
3. **`workers.dev` queda activo**: el Worker sigue respondiendo en
   `brasa-chile.ddiegosebastianbb.workers.dev`. No desactivarlo — la coexistencia
   es lo que permite migrar sin romper a nadie (sección 6).
4. Si se decide también `www.<dominio.cl>`: agregarlo como segundo Custom Domain y
   evaluar después una redirección `www` → apex (opcional, no necesario para el
   corte).
5. Alternativa equivalente: declarar el Custom Domain en `deploy/cloudflare/wrangler.jsonc`
   (`"routes": [{ "pattern": "<dominio.cl>", "custom_domain": true }]`) en el mismo
   PR de la sección 5. Si se hace por dashboard — lo recomendado, porque el dominio
   se puede probar antes del corte — **no** agregar `routes` al jsonc, para que un
   `wrangler deploy` no discuta la configuración hecha a mano.

## 5. `PUBLIC_BASE_URL`: el flujo real del repositorio

`PUBLIC_BASE_URL` es la dirección canónica que el backend usa para los enlaces de
los avisos, la ruta interna de respaldo `/_internal/storage/…`, el proxy SINCA y el
webhook de Telegram (este último sin uso: ALR-01 descartado). Su flujo real hoy:

- **Valor canónico:** `vars.PUBLIC_BASE_URL` de `deploy/cloudflare/wrangler.jsonc`
  (lo leen `tests/test_sitemap.py` y `tests/test_docs_municipios.py`).
- **Variable del repo** `PUBLIC_BASE_URL` (GitHub → Settings → Secrets and
  variables → Actions → Variables): si existe, el workflow de despliegue la pasa
  como `--var` y **pisa** el valor del jsonc; además fija el `BASE` de la sonda
  `diagnostico-cloudflare.yml`.
- **Respaldo automático:** si llega vacío, el backend «aprende» el host de la
  primera visita HTTPS (`Services.learn_public_url`). Sirve para `workers.dev`;
  con dominio propio se fija explícito para no depender del orden de las visitas.

### PR de corte (una sola rama, todo junto)

- [ ] `deploy/cloudflare/wrangler.jsonc` → `"PUBLIC_BASE_URL": "https://<dominio.cl>"`.
- [ ] `web/robots.txt` → las líneas `Sitemap:` con `https://<dominio.cl>/…`
  (la guarda `test_sitemap.py` exige el mismo host que `wrangler.jsonc`).
- [ ] `web/sitemap.xml` → los `<loc>` con el dominio nuevo.
- [ ] `backend/routes/paginas_comuna.py` → el *fallback* de `PUBLIC_BASE`
  (hoy apunta al `workers.dev`; con la variable en ambiente no se usa, pero debe
  decir lo mismo que el resto).
- [ ] `docs/MUNICIPIOS.md` → la dirección publicada que cita
  (`test_docs_municipios.py` la exige igual a `PUBLIC_BASE_URL`).
- [ ] Revisar menciones sueltas al host viejo en `docs/` (esta guía,
  `DESPLIEGUE_CLOUDFLARE.md` ejemplos) — sin romper los textos que explican el
  cambio.
- [ ] En GitHub: variable del repo `PUBLIC_BASE_URL` = `https://<dominio.cl>`
  (misma cadena exacta que el jsonc, sin `/` final).
- [ ] Mergear: el despliegue es automático (`CLOUDFLARE_DEPLOY=true`). Al llegar,
  el contenedor escribe sus respaldos por `https://<dominio.cl>/_internal/storage/…`
  sin tocar nada más.

## 6. Turnstile (hacerlo antes de anunciar el dominio)

El widget invisible cubre hoy solo `brasa-chile.ddiegosebastianbb.workers.dev`.

1. Panel → **Turnstile** → sitio «BRASA Chile» → agregar `<dominio.cl>` a la lista
   de **hostnames**. Conservar el `workers.dev`: mientras ese origen siga vivo, el
   formulario debe funcionar en ambos.
2. No requiere despliegue ni claves nuevas: misma *site key* (`TURNSTILE_SITE_KEY`,
   variable) y mismo *secret* (`TURNSTILE_SECRET`, secreto del repo).
3. **Consecuencia de saltarse este paso:** con secreto configurado el backend exige
   token — si el widget no corre en el host nuevo, `POST /api/reports` responde
   403. Es el único punto del corte que bloquea el camino crítico de reportes, así
   que se verifica con la prueba de la sección 7.
4. La CSP ya permite `challenges.cloudflare.com` en `script-src` y `frame-src`
  (idéntica en `backend/security.py` y `deploy/cloudflare/src/index.ts`): no hay
   nada que cambiar.

## 7. Migración de origen: lo que queda atado al dominio viejo

No hay migración automática de personas. La convivencia de orígenes lo absorbe:
`workers.dev` sigue respondiendo, así que **nada se rompe el día del corte**; lo
que cambia es dónde empiezan las cosas nuevas.

- **Token del teléfono → lugares guardados.** El token vive en
  `localStorage['brasa:token']` y viaja en `X-Brasa-Token`. En `<dominio.cl>` ese
  almacenamiento está vacío: la app crea un suscriptor **nuevo y vacío** al primer
  `POST /api/subscribers`. Los lugares guardados quedan en el token viejo. Hoy no
  hay importador en el servidor (`/api/me/export` exporta, pero no hay endpoint de
  importación): cada persona re-crea sus lugares en el dominio nuevo o sigue en
  `workers.dev`, que sigue funcionando igual.
- **Suscripciones push.** El `endpoint` VAPID es del origen: en `<dominio.cl>`
  `pushManager.getSubscription()` da `null` y activar avisos crea una suscripción
  nueva (`POST /api/push/subscribe`). Los endpoints viejos mueren solos: el envío
  responde 404/410 y `webpush.send` los borra de `subscribers`.
- **PWA instalada.** La app instalada pertenece al origen `workers.dev` y sigue
  abriendo y funcionando ahí. Quien quiera el icono «con el dominio nuevo» la
  reinstala desde `<dominio.cl>`. `manifest.webmanifest` usa rutas relativas
  (`start_url: "/#/mi-zona"`, `scope /`), así que no requiere cambios.
- **Enlaces de familia `#/v/<token>`.** Los ya repartidos con `workers.dev` siguen
  válidos mientras ese origen responda. Los nuevos se generan con
  `location.origin`, es decir, salen con `<dominio.cl>` (`web/js/views/vecino.js`).
- **Service worker y cachés.** Cada origen tiene su SW y sus cachés; no hay nada
  que limpiar: el de `<dominio.cl>` se instala solo en la primera visita.
- **Decisión que queda del dueño:** cuándo (o si) comunicar el cambio a las
  personas ya registradas en `workers.dev`, y si algún día se redirige
  `workers.dev` → `<dominio.cl>` (hoy no hay redirección ni está planificada).

## 8. Verificaciones después del corte (todas GET, sin tocar nada)

- [ ] `GET https://<dominio.cl>/api/health` → `version` **idéntica** al `VERSION`
  de `backend/version.py` del commit desplegado (un `ok` solo no basta: puede ser
  un build viejo).
- [ ] `GET https://<dominio.cl>/api/status` → sin `backup_error` (prueba que el
  respaldo por `/_internal/storage` funciona a través del dominio nuevo).
- [ ] `GET https://<dominio.cl>/api/config` → publica `turnstile_site_key` y la
  clave pública de push.
- [ ] `GET https://<dominio.cl>/robots.txt` → las líneas `Sitemap:` ya dicen
  `<dominio.cl>`; `GET https://<dominio.cl>/web/sitemap.xml` y
  `GET https://<dominio.cl>/sitemap-comunas.xml` → `<loc>` con el dominio nuevo.
- [ ] `GET https://<dominio.cl>/comuna/<slug-de-una-comuna>` → el `<link
  rel="canonical">` y el `og:image` usan `<dominio.cl>`.
- [ ] `GET https://brasa-chile.ddiegosebastianbb.workers.dev/api/health` → sigue
  200 (coexistencia confirmada).
- [ ] Camino crítico, una vez: reporte de prueba real desde `<dominio.cl>` (cae en
  la cola de moderación) para confirmar que Turnstile corre en el host nuevo; y
  activar avisos push para generar la suscripción nueva. Descartar el reporte de
  prueba en `/admin` después.
- [ ] Sonda del repo: `gh workflow run diagnostico-cloudflare.yml --ref main -f
  minutos=11` (usa el `PUBLIC_BASE_URL` de las variables del repo).

## 9. Rollback

- **Antes del PR de corte** (solo se hicieron los pasos de panel): quitar el Custom
  Domain en *Domains & Routes* y listo — `workers.dev` quedó intacto todo el
  tiempo. La zona y los nameservers pueden quedarse sin costo para reintentar.
- **Después del merge del PR de corte:** `git revert` del merge en una rama + PR
  (al mergearse se despliega solo) y revertir la variable del repo
  `PUBLIC_BASE_URL`. El Custom Domain puede quedar o quitarse; con el dominio
  apuntando pero `PUBLIC_BASE_URL` viejo, la app sigue sirviendo en ambos orígenes
  con enlaces del viejo.
- **Nunca hace falta tocar NIC Chile para el rollback:** los NS apuntan a
  Cloudflare y no cuestan nada. Solo se vuelve a NIC si se abandona Cloudflare por
  completo.
- **Datos:** ningún rollback toca `brasa.db` ni R2 — los respaldos y las personas
  registradas son del Worker, no del host.

## Lo que queda pendiente (resumen)

1. Elegir el nombre y **comprar** `<dominio.cl>` (decisión y pago del dueño).
2. Ejecutar los pasos de panel: zona, nameservers, Custom Domain, hostname de
   Turnstile.
3. Abrir el PR de corte de la sección 5 y setear la variable del repo.
4. Decidir `www` y, más adelante, la comunicación a personas del origen viejo.
5. **HSTS con `preload`** (pedido original de OPS-11): hoy el Worker envía
   `Strict-Transport-Security: max-age=31536000` sin `includeSubDomains` ni
   `preload` (`deploy/cloudflare/src/guardas.ts`). Entrar a `hstspreload.org`
   exige cambiar esa cabecera (PR aparte) y es irreversible a efectos prácticos:
   evaluarlo solo con el dominio ya estable, nunca antes.
