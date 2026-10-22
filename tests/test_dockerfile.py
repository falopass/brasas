"""OPS-52: la base del Dockerfile queda clavada a un digest, igual que las dependencias.

`requirements.lock` se instala con `--require-hashes` (OPS-08), pero un `FROM python:3.12-slim`
sin digest es un tag móvil: dos construcciones del mismo commit pueden traer parches distintos
de Debian, OpenSSL o CPython. El validador es una función pura: recibe el texto del Dockerfile
y lanza ValueError nombrando la línea infractora, como en tests/test_datos_publicados.py.
"""

import re
from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"

_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}\b")


def _fail(lineno: int, msg: str):
    raise ValueError(f"Dockerfile línea {lineno}: {msg}")


def validate_dockerfile(text: str):
    """Guardas del Dockerfile de producción: base fija, instalación con hash y usuario no root."""
    froms = 0
    has_require_hashes = False
    has_non_root_user = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keyword = line.split(None, 1)[0].upper()
        if keyword == "FROM":
            froms += 1
            if not _DIGEST_RE.search(line):
                _fail(lineno, f"FROM sin digest @sha256:… (tag móvil): {line}")
        elif keyword == "RUN" and "--require-hashes" in line:
            has_require_hashes = True
        elif keyword == "USER":
            user = line.split(None, 1)[1].strip()
            if user in {"root", "0"}:
                _fail(lineno, "USER root no está permitido")
            has_non_root_user = True
    if not froms:
        _fail(0, "no hay ninguna línea FROM")
    if not has_require_hashes:
        _fail(0, "falta `pip install --require-hashes` (las dependencias van clavadas con hash)")
    if not has_non_root_user:
        _fail(0, "falta un `USER` que no sea root")


def test_dockerfile_de_produccion_cumple_las_guardas():
    validate_dockerfile(DOCKERFILE.read_text(encoding="utf-8"))


def test_todo_from_lleva_digest_de_64_hex():
    text = DOCKERFILE.read_text(encoding="utf-8")
    froms = [line for line in text.splitlines() if line.strip().upper().startswith("FROM")]
    assert froms, "el Dockerfile debe tener al menos un FROM"
    for line in froms:
        assert _DIGEST_RE.search(line), f"FROM sin digest: {line}"


def test_rechaza_from_con_tag_movil(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.12-slim\nRUN pip install --require-hashes -r requirements.lock\nUSER brasa\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="línea 1"):
        validate_dockerfile(dockerfile.read_text(encoding="utf-8"))


def test_rechaza_instalacion_sin_require_hashes(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.12-slim@sha256:" + "a" * 64 + "\nRUN pip install -r requirements.txt\nUSER brasa\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="require-hashes"):
        validate_dockerfile(dockerfile.read_text(encoding="utf-8"))


def test_rechaza_usuario_root(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.12-slim@sha256:" + "b" * 64 + "\nRUN pip install --require-hashes -r requirements.lock\nUSER root\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="root"):
        validate_dockerfile(dockerfile.read_text(encoding="utf-8"))
