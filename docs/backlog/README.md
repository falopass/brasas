# Backlog de encargos

Fuente única del trabajo pendiente de BRASA: un archivo por encargo, con su objetivo, archivos y criterio de listo.
`docs/BACKLOG_MAESTRO.md` queda como roadmap e historia; sus estados ya no se mantienen.

- Al terminar un encargo, en el mismo PR muévelo a `hecho/` (con `git mv`) y nombra su ID en el título del PR.
- Un encargo nuevo es un archivo `<id>.md` con el frontmatter de los demás (`id`, `rama`, `modelo`, `archivos`).
- `unificados/`: encargos absorbidos por otro que pedía lo mismo. `descartados/`: encargos cuya premisa venció.
- Estado revisado contra `main` el 2026-11-11: **0 encargos abiertos** en la raíz (la evidencia anterior está en `_estado-2026-10-23.md`).
- El 24-10-2026 se integró todo el plan (`PLAN_INTEGRACION.md`, sección «Resultado»): lo que queda depende de algo externo.
- Orden de trabajo: [`PLAN_INTEGRACION.md`](PLAN_INTEGRACION.md) (tandas por archivos compartidos).

Al 11-11-2026 no queda ningún encargo abierto: los dos últimos con archivo en la raíz, [ICON-E-01](hecho/ICON-E-01.md) (iconos y OG, PRs #836 y #835) y la [cadencia del verdor satelital](hecho/RISK-11-cadencia.md) (PRs #852 y #857), pasaron a `hecho/` en el barrido de ese día, y [AGUA-04](hecho/agua-04.md) (aviso de aluvión por lugar guardado) quedó registrado con sus PRs #838, #831, #840 y #851.

La ola del 10 y 11 de noviembre cerró, además de los tres anteriores: las cicatrices anuales del cruce de aluvión (AGUA-01, #824), la sequedad por las 288 comunas medibles (RISK-11, #830), la suite e2e de los flujos principales (QA-E2E, #850), los descartes por fuente en Calidad (QA-3.2, #823), la ronda móvil (MOV-01 a MOV-05, VIS-01, VIS-02, MZ-09 y arreglos táctiles e imprimibles) y documentos de operación (checklist del dominio `.cl` en `docs/DOMINIO_CL.md`, #821 y #854, y evidencia de producción, #825, #827 y #837).

Al 3-11-2026 había 0 encargos abiertos: la Fase 5 completa (MAPA-157 a 167, MZ-06 a 10, UX-80 y UX-81) y ALR-44 ya estaban en `hecho/` tras las olas del 25 al 30 de octubre. Los pendientes externos de ese cierre están en `PASOS_DUENO.md`.

La ola del 4 al 8 de noviembre llegó sin archivo de encargo: cicatrices históricas, infraestructura a sotavento, sequedad por satélite (NDVI), Landsat en FIRMS, respaldo SINCA, tres capas de riesgo con campamentos, SNASPE, terreno post-incendio, latencias y concordancia en Calidad, tres casos por macrozona y arreglos del mapa. Las tandas recuperadas, los PR #803 y #807 fusionados y el seguimiento de los issues #798/#802 quedan en [`../cierre-brasa-2026-11-08.md`](../cierre-brasa-2026-11-08.md).

Antes de la Fase 4 quedaban 0 encargos abiertos. El 24-10 Diego aprobó integrar las tres fuentes de gobierno pendientes (OFI-04 SENAPRED, OFI-10 SINCA, OFI-25 MINVU) con atribución y enlace; quedan en `hecho/`. Al 3-11: SENAPRED quedó decidido (acceso anónimo del portal; Transparencia solo si lo restringe), MINVU confirmó uso público y CONAF se usa con cita — no volver a consultar. Lo único que sigue dependiendo de fuera: la respuesta de licencia del MMA/SINCA por Transparencia y el host `sinca.mma.gob.cl`, que no responde desde Cloudflare (#792 dejó proxy + snapshot). Al llegar, se anota en `docs/FUENTES.md`. Ver [`PASOS_DUENO.md`](PASOS_DUENO.md).
