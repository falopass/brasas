# Lo que queda en manos de Diego

Lo que es código vive en el backlog (Fase 5 en `PLAN_INTEGRACION.md`). El 24-10 se integraron
las tres fuentes de gobierno (SENAPRED, SINCA, MINVU) con atribución y enlace; de eso solo
queda **esperar las respuestas** de las consultas de licencia/acceso que ya quedaron enviadas
(o por enviar) por los canales oficiales:

- **SENAPRED — decidido el 3-11-2026.** Datos públicos del Estado: se sigue usando el acceso
  anónimo del portal sin pedir feed formal. Si SENAPRED lo cambia o lo restringe, la capa se
  degrada al enlace oficial (OFI-04) y ahí sí convendría la solicitud por Transparencia.
- **MMA / SINCA** — consulta de licencia de reutilización de los datos de SINCA por
  Transparencia en <https://mma.gob.cl/>. Si responden con licencia (o la niegan), se anota
  en `docs/FUENTES.md` junto a la fila de SINCA. Además hay un bloqueo técnico: el host no
  responde desde la red de Cloudflare (probable geocerca), así que hoy la capa entrega
  `air:null` — si la respuesta habilita un canal alcanzable, queda lista.
- **MINVU — respondió el 3-11-2026.** La información del Catastro de Campamentos es de uso
  público; la citación «Ministerio de Vivienda y Urbanismo. (2026). Sentamientos Precarios
  [Servicio de mapas]» ya quedó anotada en `docs/FUENTES.md`. Nada pendiente.
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

- **Dominio propio (OPS-11), antes de sumar usuarios.** Hay tres cosas atadas al dominio actual (`workers.dev`): las suscripciones push, la app instalada y el token del teléfono que da acceso a los lugares guardados. Cada persona que se sume ahí habrá que migrarla después. Pasos: registrar el `.cl`, apuntarlo al Worker y fijar `PUBLIC_BASE_URL`. Al activarlo, agregar el dominio nuevo al widget de Turnstile (hoy solo cubre `*.workers.dev`).
- **Turnstile — hecho el 3-11-2026.** Widget invisible creado en Cloudflare; `TURNSTILE_SITE_KEY` quedó como variable y `TURNSTILE_SECRET` como secreto del repo, propagados en el despliegue.
- **Moderación — resuelta el 3-11-2026.** Diego revisa los reportes en
  `/web/admin.html` con el token `ADMIN_TOKEN` (ya está en los secretos del Worker); la página
  cubre cola por estado, fotos, verificar/descartar, registro, moderadores y salud.
- **Bot de Telegram (ALR-01) — descartado el 3-11-2026** por decisión del dueño.
- **Corrida de carga — hecha el 3-11-2026.** `scripts/carga/mapa.js` (k6 v2.3) contra la copia
  local (`python dev.py run --demo`): 500 personas simultáneas 10 min con el patrón real del
  mapa. Resultado: **11.375 pedidos, 0 % errores, p95 = 26 ms** (máx 552 ms); ambos umbrales
  en verde. Es un piso: en local todo pega a un solo proceso Python, sin la caché del borde
  (OPS-03) que en producción debería responder mejor. Pendiente solo si se quiere medir la
  copia aislada en Cloudflare o el escenario «Mi zona».

Ningún valor de clave se pega en el chat, en issues ni en el repositorio. Si alguna
respuesta dice «no», la capa correspondiente se retira y queda solo el enlace oficial —
la app ya degrada así cuando la fuente falla.
