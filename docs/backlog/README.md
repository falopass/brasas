# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-10-23 (con evidencia en `_estado-2026-10-23.md`).
- El 24-10-2026 se integró todo el plan (`PLAN_INTEGRACION.md`, sección «Resultado»): lo que queda depende de algo externo.
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

**0 encargos abiertos** al 3-11-2026: la Fase 5 completa (MAPA-157 a 167, MZ-06 a 10, UX-80 y UX-81) y ALR-44 ya están en `hecho/` tras las olas del 25 al 30 de octubre. Lo que queda no es código: respuestas externas de licencias y los pasos del dueño en `PASOS_DUENO.md`.

La ola del 4 al 8 de noviembre (PRs #784-#806) llegó sin archivo de encargo: cicatrices históricas, infraestructura a sotavento, sequedad por satélite (NDVI), Landsat en FIRMS, respaldo SINCA, tres capas de riesgo con campamentos, SNASPE, terreno post-incendio, latencias y concordancia en Calidad, tres casos por macrozona y arreglos del mapa. Su conciliación con el estado de `main`, los PRs e issues que siguen abiertos (#803, #807, #798, #802) y lo que falta por tipo quedan en [`../cierre-brasa-2026-11-08.md`](../cierre-brasa-2026-11-08.md).

Antes de la Fase 4 quedaban 0 encargos abiertos. El 24-10 Diego aprobó integrar las tres fuentes de gobierno pendientes (OFI-04 SENAPRED, OFI-10 SINCA, OFI-25 MINVU) con atribución y enlace; quedan en `hecho/`. Al 3-11: SENAPRED quedó decidido (acceso anónimo del portal; Transparencia solo si lo restringe), MINVU confirmó uso público y CONAF se usa con cita — no volver a consultar. Lo único que sigue dependiendo de fuera: la respuesta de licencia del MMA/SINCA por Transparencia y el host `sinca.mma.gob.cl`, que no responde desde Cloudflare (#792 dejó proxy + snapshot). Al llegar, se anota en `docs/FUENTES.md`. Ver [`PASOS_DUENO.md`](PASOS_DUENO.md).
