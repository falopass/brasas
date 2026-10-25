# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).
- El 24-10-2026 se integró todo el plan (`PLAN_INTEGRACION.md`, sección «Resultado»): lo que queda depende de algo externo.
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

**16 encargos abiertos** desde el 25-10 (Fase 5 de `PLAN_INTEGRACION.md`, solo frontend): MAPA-157 a 165, MZ-06 a 10, UX-80 y UX-81, en tres olas en los hosts. **En espera de decisión:** ALR-44 (toca backend y avisos), MAPA-166 y MAPA-167 (licencias por confirmar). La Fase 4 (17 encargos) quedó entera en `hecho/` el 25-10.

Antes de la Fase 4 quedaban 0 encargos abiertos. El 24-10 Diego aprobó integrar las tres fuentes de gobierno pendientes (OFI-04 SENAPRED, OFI-10 SINCA, OFI-25 MINVU) con atribución y enlace; quedan en `hecho/`. Lo que sigue dependiendo de fuera: las respuestas de las consultas de licencia (Transparencia SENAPRED/MMA, correo MINVU) — al llegar, se anotan en `docs/FUENTES.md`. Ver [`PASOS_DUENO.md`](PASOS_DUENO.md).
