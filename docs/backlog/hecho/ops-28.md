---
id: OPS-28
repo: brasas
rama: feat/salud-del-repositorio
modelo: swe-2-high
riesgo: A
archivos: .github/workflows/salud-repo.yml, .github/scripts/salud_repo.py, tests/test_salud_repo.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que el repositorio se revise solo una vez al día y, cuando `python dev.py check` quede rojo en `main`, abra (o actualice) un *issue* con las etapas que fallaron y el primer error de cada una, en vez de que nadie se entere.

**Ítem del backlog.** OPS-01 (monitoreo con aviso a la persona dueña) y OPS-02 (prueba de humo de las fuentes), ambos ya en `main` pero **solo para producción**. Prioridad 3 de esta ronda: que el producto detecte y reporte sus propias fallas y proponga el arreglo.

**Qué pasa hoy y por qué está mal.** `.github/workflows/` tiene 8 archivos: `monitoreo.yml` consulta `/api/status` de producción y abre un *issue* con etiqueta `monitoreo`; `tests.yml` corre en cada push y PR, pero si el push es a `main` y falla, GitHub solo deja la marca roja. El 20 de octubre de 2026 `main` quedó rojo por el presupuesto de peso del arranque (252,2 KB contra un tope de 252,0 en `scripts/local/presupuesto_peso.py`, con 1118 pruebas en verde) y lo descubrió a mano el planificador, no el repo: por eso hay más de cien encargos parados en `bloqueado/`. Nadie vigila la salud del propio repositorio: ni `dev.py check`, ni la sintaxis JS, ni `node --test tests/js`.

**Qué hacer.**
1. Crear `.github/scripts/salud_repo.py` (sin dependencias nuevas, solo biblioteca estándar) que corra **cada etapa por separado** imitando `cmd_check` de `dev.py:126-142`: `ruff check backend tests`, `pytest -q`, `scripts/local/presupuesto_peso.py`, `node --check` de cada `web/**/*.js` y `node --test tests/js`. Cada etapa con su tope de tiempo (por ejemplo 900 s) y sin abortar en la primera: el informe debe decir **todas** las que fallaron.
   - Salida: informe legible en texto con una línea por etapa (`OK` / `FALLÓ` + duración) y, por cada fallo, las últimas 20 líneas relevantes.
   - `--dry-run`: imprime el plan de etapas y sale con 0 sin ejecutar nada.
   - `--issue`: con `gh issue create --label salud-repo` (o `gh issue comment` si ya existe un *issue* abierto con esa etiqueta y el título es el mismo), cuerpo en Markdown con la tabla del informe, el SHA de `main` y el enlace al run. Nunca imprimir secretos ni variables de entorno.
2. Crear `.github/workflows/salud-repo.yml`: `schedule` diario a las 11:00 UTC (08:00 en Chile) más `workflow_dispatch`; permisos `contents: read` e `issues: write`; instalar dependencias como lo hace `tests.yml` (cópialo como referencia, **no lo modifiques**); correr el script con `--issue` y subir el informe como artefacto.
3. El *issue* debe cerrarse solo cuando la corrida siguiente esté en verde: si hay un *issue* abierto con la etiqueta y el informe es todo `OK`, el script lo comenta y lo cierra.

**Pruebas (`tests/test_salud_repo.py`, nuevo).** Unitarias sobre funciones puras, sin red ni subprocess real: parseo del informe → lista de etapas fallidas; armado del cuerpo del *issue* (incluye SHA, etapas y enlaces); decisión crear/comentar/cerrar según (etapas fallidas, *issues* abiertos). Usa `monkeypatch` para `subprocess.run` y `gh`.

**Criterio de listo (verificable).** `python -m pytest tests/test_salud_repo.py -q` en verde; `python .github/scripts/salud_repo.py --dry-run` imprime las cinco etapas y sale con 0; `python dev.py check` en «Todo en orden»; tras el push, el workflow aparece en `gh workflow list` y una corrida manual (`workflow_dispatch`) termina con el informe en artefactos.

**No toques nada más.** No toques `tests.yml` ni `monitoreo.yml` ni `deploy/`; no edites `docs/OPERACION.md` (lo está tocando otro encargo). De `CHANGELOG.md`, solo tu línea.

Verifica con /verificar y entrega con /entregar-pr.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.
