# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).
- El 24-10-2026 se integró todo el plan (`PLAN_INTEGRACION.md`, sección «Resultado»): lo que queda depende de algo externo.
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

0 encargos abiertos. El 24-10 Diego aprobó integrar las tres fuentes de gobierno pendientes (OFI-04 SENAPRED, OFI-10 SINCA, OFI-25 MINVU) con atribución y enlace; quedan en `hecho/`. Lo que sigue dependiendo de fuera: las respuestas de las consultas de licencia (Transparencia SENAPRED/MMA, correo MINVU) — al llegar, se anotan en `docs/FUENTES.md`. Ver [`PASOS_DUENO.md`](PASOS_DUENO.md).
