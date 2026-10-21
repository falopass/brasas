"""`docs/DESPLIEGUE_CLOUDFLARE.md`: «responde ok» no puede bastar para dar por bueno un despliegue.

La lección del 21-oct: `/api/health` respondía `{"status":"ok"}` mientras producción corría
un build viejo (`version` 0.8.0 contra el `VERSION` del repo), sirviendo incidentes con
centroide fuera de Chile que `main` ya filtraba. La guarda exige que el paso «N. Comprobar»
del manual compare la `version` publicada con el `VERSION` de `backend/version.py` y que
siga mirando `backup_error` en `/api/status`, y que cualquier versión citada de ejemplo en
el documento sea la viva del módulo.
"""

from __future__ import annotations

import re

from backend import settings

DOC = settings.ROOT / "docs" / "DESPLIEGUE_CLOUDFLARE.md"
VERSION_FILE = settings.ROOT / "backend" / "version.py"
TITLE = re.compile(r"^#+ \d+\. Comprobar\s*$", re.M)
HEADING = re.compile(r"^#{1,6} ", re.M)
SEMVER = re.compile(r"\b\d+\.\d+\.\d+\b")


def _version() -> str:
    match = re.search(r'VERSION = "([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
    assert match, "backend/version.py no declara VERSION"
    return match.group(1)


def _section(text: str) -> str:
    """Texto del paso «N. Comprobar», hasta el próximo encabezado o el final."""
    start = TITLE.search(text)
    assert start, "docs/DESPLIEGUE_CLOUDFLARE.md no tiene el paso «N. Comprobar»"
    rest = text[start.end() :]
    end = HEADING.search(rest)
    return rest if end is None else rest[: end.start()]


def _problems(text: str) -> list[str]:
    """Lo que le falta al paso «Comprobar» para distinguir ok de la versión desplegada."""
    problems = []
    section = _section(text)
    if "/api/health" not in section:
        problems.append("no pide consultar /api/health")
    if "version" not in section or "VERSION" not in section:
        problems.append("no compara la version publicada con el VERSION de backend/version.py")
    if "backup_error" not in section:
        problems.append("no comprueba backup_error en /api/status")
    return problems


def test_paso_comprobar_verifica_la_version_desplegada() -> None:
    problems = _problems(DOC.read_text(encoding="utf-8"))
    assert not problems, "El paso «Comprobar» del manual de despliegue: " + "; ".join(problems)


def test_fragmento_sin_chequeo_de_version_falla() -> None:
    """La guarda no acepta el manual anterior: «responde ok» solo no basta."""
    incomplete = '## 4. Comprobar\n\n- `https://…/api/health` responde `{"status":"ok"}`.\n'
    assert _problems(incomplete), "Un paso «Comprobar» sin chequeo de versión debe fallar"


def test_version_citada_es_la_del_modulo() -> None:
    cited = set(SEMVER.findall(DOC.read_text(encoding="utf-8"))) - {_version()}
    assert not cited, (
        f"El manual cita versiones de ejemplo que no son la viva (VERSION={_version()}): "
        f"{sorted(cited)}. Actualiza el ejemplo o quita la cita."
    )
