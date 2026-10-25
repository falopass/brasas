# Lo que queda en manos de Diego

Lo que es código vive en el backlog (Fase 5 en `PLAN_INTEGRACION.md`). El 24-10 se integraron
las tres fuentes de gobierno (SENAPRED, SINCA, MINVU) con atribución y enlace; de eso solo
queda **esperar las respuestas** de las consultas de licencia/acceso que ya quedaron enviadas
(o por enviar) por los canales oficiales:

- **SENAPRED** — solicitud de feed público de alertas (idealmente CAP) por el formulario de
  Ley de Transparencia de <https://senapred.cl/>. Si responden con un servicio oficial, se
  migra `backend/providers/senapred.py` a él; mientras, se usa el acceso anónimo del portal.
- **MMA / SINCA** — consulta de licencia de reutilización de los datos de SINCA por
  Transparencia en <https://mma.gob.cl/>. Si responden con licencia (o la niegan), se anota
  en `docs/FUENTES.md` junto a la fila de SINCA.
- **MINVU** — consulta de reutilización del Catastro de Campamentos a `ideminvu@minvu.cl`
  (o por Transparencia en minvu.cl). Igual: la respuesta se anota en `docs/FUENTES.md`.

## Antes de un lanzamiento abierto (auditoría del 25-10-2026)

BRASA está lista para un piloto controlado. Para abrirla a todo el público (prensa, municipios, cadenas de WhatsApp) faltan cosas que no son código:

- **Dominio propio (OPS-11), antes de sumar usuarios.** Hay tres cosas atadas al dominio actual (`workers.dev`): las suscripciones push, la app instalada y el token del teléfono que da acceso a los lugares guardados. Cada persona que se sume ahí habrá que migrarla después. Pasos: registrar el `.cl`, apuntarlo al Worker y fijar `PUBLIC_BASE_URL`.
- **Turnstile.** Producción responde `turnstile_site_key` vacío: el formulario de reporte solo tiene límites por IP. Crear el sitio en Cloudflare y cargar `TURNSTILE_SITE_KEY` y `TURNSTILE_SECRET` (pasos en `docs/DESPLIEGUE_CLOUDFLARE.md`).
- **Bot de Telegram (ALR-01).** Hoy `telegram.enabled` es `false` y el único canal es Web Push. En iPhone, Web Push exige instalar la app en la pantalla de inicio; Telegram llega sin instalar nada.
- **Turnos de moderación.** Los avisos de vecinos se publican solo después de revisarlos. Hay que definir quién revisa y en qué horario, incluidos los fines de semana de temporada.
- **Una corrida de carga.** `scripts/carga/mapa.js` (k6) contra una copia, con un escenario de «Mi zona». Todo corre en un solo contenedor `basic` con SQLite.

Ningún valor de clave se pega en el chat, en issues ni en el repositorio. Si alguna
respuesta dice «no», la capa correspondiente se retira y queda solo el enlace oficial —
la app ya degrada así cuando la fuente falla.
