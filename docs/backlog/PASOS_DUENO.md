# Lo que queda en manos de Diego

_Revisado contra `main` el 18-11-2026: decisiones y credenciales de la revisión del 18-11 más el estado previo del 11-11-2026._

## Decisiones y credenciales nuevas (revisión 18-11-2026)

### Decisión de producto: aviso de aluvión creado de noche (`compose_aluvion`) — RESUELTO

- **Resolución aplicada:** se adoptaron las opciones 1 y 2. `compose_aluvion` ([`backend/alerts.py`](../../backend/alerts.py)) entrega avisos de aluvión incluso en horario de silencio nocturno (23:00–07:00) sin aplazarlos (`aplazable` devuelve `False` para `kind == "aluvion"`), y `aluvion:` queda exento del tope semanal `CAP_AVISOS_7D = 3` en `caps_exceeded` sin consumir cupo de los avisos de incendio.

### Clave gratuita de Agromet INIA (`OFI-37`)

- **Qué se necesita:** solicitar una clave gratuita (`AGROMET_API_KEY`) en el portal de desarrolladores de **INIA / Red Agrometeorológica Nacional** (<https://www.agromet.cl/>, API `https://agromet.inia.cl/api/v4/`).
- **Para qué sirve:** cubrir zonas rurales, valles y secano donde ni DMC ni SINCA tienen estación cercana (medición cada 15–60 min para «Mi zona», lluvia rural y aluvión).
- **Verificación previa y carga:** al recibir la clave, revisar que los términos de uso autoricen redistribuir lecturas en una aplicación pública ciudadana citando a INIA; si es conforme, cargarla como secreto del Worker / GitHub (nunca en el repositorio).

### Otras gestiones externas asociadas al backlog del 18-11

- **OpenAQ v3 / RedMeteo (`OFI-38`):** API key gratuita de OpenAQ (filtrando por licencia redistribuible en `/v3/licenses`) y eventual solicitud por correo a `redmeteoaficionadachile@gmail.com` si se activa como referencia ciudadana no oficial.
- **Mensajes en mapudungun y rapa nui (`PROD-04`):** requiere validación lingüística comunitaria antes de publicar texto o audio.

---

Lo que es código vive en el backlog (`docs/backlog/README.md`). El 24-10 se integraron
las tres fuentes de gobierno (SENAPRED, SINCA, MINVU) con atribución y enlace; **las tres
respuestas oficiales ya llegaron y quedaron registradas** en `docs/FUENTES.md` y
`web/data/licencias.json`:

- **SENAPRED — Oficio N° 2236 (10-11-2026, folio `AB004T0002166`, Directora Nacional).**
  Confirma que SENAPRED no cuenta con servicios web, API ni feed (JSON, RSS o CAP) ni prevé
  habilitarlos en el corto plazo, remite a <https://senapred.cl/alertas/> (24/7) y no recomienda
  extracción directa automatizada (web scraping) desde su sitio web por estabilidad y continuidad
  del portal. Por decisión del dueño (24-11-2026) se conserva por ahora la lectura compartida en
  caché (`backend/providers/senapred.py`, 1 consulta cada 10 min al AppSync del portal); si
  SENAPRED lo cambia o lo restringe, la capa se degrada automáticamente al enlace oficial (OFI-04).
- **MMA / SINCA — Carta N° 02853/2026 (23-11-2026, folio `AW002T0016097`, Subsecretario del
  Medio Ambiente).** Confirma que los datos de SINCA no se publican bajo licencia Creative
  Commons y que **para republicarlos debe citarse la autoría con el Ministerio del Medio Ambiente
  de Chile**; por el momento tampoco existe una API pública (los históricos se descargan según el
  tutorial oficial en `sinca.mma.gob.cl`). La cita completa quedó aplicada en la interfaz, la API,
  `web/data/licencias.json` y `docs/FUENTES.md`. Persiste solo el bloqueo técnico de red desde
  Cloudflare hacia `sinca.mma.gob.cl` (cubierto por `SINCA_PROXY_URL` + snapshot en #792).
- **MINVU — Respuesta definitiva SIAC/DPH (04-11-2026, complementa correo IDE MINVU del
  03-11-2026).** Confirma que el Catastro Nacional de Campamentos es administrado por el
  **Departamento de Asentamientos Precarios (DAP-MINVU)**, que su licencia y condiciones
  corresponden al MINVU y que al reutilizar los datos **debe reconocerse expresamente al
  Departamento de Asentamientos Precarios (DAP-MINVU) como fuente oficial**. Atribución aplicada
  en la interfaz (`exposure.js`), `web/data/campamentos.json`, `web/data/licencias.json` y
  `docs/FUENTES.md`. Nada pendiente.
- **CONAF — decidido el 3-11-2026.** Datos públicos del Estado: se usan citando a CONAF, sin
  pedir autorización formal; la carta de OFI-03 quedó archivada sin enviar
  (`docs/cartas/2026-10-carta-geprif.md`). Con la decisión se encendió también el perímetro
  oficial (OFI-17, `CONAF_PERIMETRO_ENABLED` en producción).

## Secretos pendientes en GitHub (3-11-2026)

- **DB_ENC_KEY — hecho el 3-11-2026.** El secreto quedó en GitHub Actions y el simulacro de
  restauración pasó por primera vez con descifrado real: `brasa.db` (156 KB, 52 suscriptores) y
  `work.db` (42,5 MB, 3.643 observaciones, 998 incidentes) íntegras — los respaldos cifrados
  `BRASA1` se pueden restaurar. Nada pendiente aquí; si algún día se rota la clave en el Worker,
  hay que repetir el cambio en GitHub (OPERACION.md §rotación).

## Antes de un lanzamiento abierto (auditoría del 25-10-2026)

BRASA está lista para un piloto controlado. Para abrirla a todo el público (prensa, municipios, cadenas de WhatsApp) faltan cosas que no son código:

- **Dominio propio (OPS-11), antes de sumar usuarios.** Hay tres cosas atadas al dominio actual (`workers.dev`): las suscripciones push, la app instalada y el token del teléfono que da acceso a los lugares guardados. Cada persona que se sume ahí habrá que migrarla después. **Estado al 11-11:** el procedimiento completo quedó escrito en `docs/DOMINIO_CL.md` (#821) y el ejemplo inerte del corte en #854 — **nada ejecutado**: registrar el `.cl` es una compra del dueño, y después apuntarlo al Worker, fijar `PUBLIC_BASE_URL` y agregar el dominio nuevo al widget de Turnstile (hoy solo cubre `*.workers.dev`).
- **Turnstile — hecho el 3-11-2026.** Widget invisible creado en Cloudflare; `TURNSTILE_SITE_KEY` quedó como variable y `TURNSTILE_SECRET` como secreto del repo, propagados en el despliegue.
- **Moderación — resuelta el 3-11-2026.** Diego revisa los reportes en
  `/web/admin.html` con el token `ADMIN_TOKEN` (ya está en los secretos del Worker); la página
  cubre cola por estado, fotos, verificar/descartar, registro, moderadores y salud.
- **Bot de Telegram (ALR-01) — descartado el 3-11-2026** por decisión del dueño.
- **SMS y WhatsApp — en espera.** Dependen de presupuesto (proveedor y costo por mensaje); no se construyen mientras tanto.
- **Comunas prioritarias CONAF 2026-27 — en espera.** `web/data/prioritarias.json` sigue con `"comunas": []`: CONAF informó 90 comunas en el COGRID del 10-sep-2026 pero no ha publicado el listado en un documento oficial; se incorpora solo desde ese documento.
- **Corrida de carga — hecha el 3-11-2026.** `scripts/carga/mapa.js` (k6 v2.3) contra la copia
  local (`python dev.py run --demo`): 500 personas simultáneas 10 min con el patrón real del
  mapa. Resultado: **11.375 pedidos, 0 % errores, p95 = 26 ms** (máx 552 ms); ambos umbrales
  en verde. Es un piso: en local todo pega a un solo proceso Python, sin la caché del borde
  (OPS-03) que en producción debería responder mejor. Pendiente solo si se quiere medir la
  copia aislada en Cloudflare o el escenario «Mi zona».

Ningún valor de clave se pega en el chat, en issues ni en el repositorio. Si alguna
respuesta dice «no», la capa correspondiente se retira y queda solo el enlace oficial —
la app ya degrada así cuando la fuente falla.
