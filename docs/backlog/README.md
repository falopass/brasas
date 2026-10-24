# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).
- El 24-10-2026 se integró todo el plan (`PLAN_INTEGRACION.md`, sección «Resultado»): lo que queda depende de algo externo.
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

3 encargos abiertos, todos bloqueados por algo externo: OFI-04 lo hace Diego; OFI-10 y OFI-25 esperan verificar la licencia de la fuente. Pasos y borradores para cada uno: [`PASOS_DUENO.md`](PASOS_DUENO.md).

| ID | Encargo | Estado | Modelo |
|---|---|---|---|
| OFI-04 | [Responder en la aplicación «¿qué dijo la autoridad?» con la alerta oficial de SENAPRED para la comuna o el…](ofi-04.md) | pendiente | swe-2-high |
| OFI-10 | [SINCA (MP2,5 medido): la fuente es pública pero no declara licencia (decisión de Diego)](ofi-10.md) | pendiente | swe-2-high |
| OFI-25 | [OFI-09 · Campamentos del MINVU por comuna (delicado: fuente nueva y licencia por verificar)](ofi-25.md) | pendiente | swe-2-high |
