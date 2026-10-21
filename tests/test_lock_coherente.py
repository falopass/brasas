"""CALIDAD-04: el lock que instala producción debe seguir satisfaciendo requirements.txt.

CI instala requirements.txt y la imagen de producción instala requirements.lock
con --require-hashes. Si un PR cambia el txt sin regenerar el lock, CI queda
verde pero producción corre otra versión. Esta prueba compara ambos archivos,
sin red, para que el desfase falle aquí y no meses después en producción.
"""

from __future__ import annotations

import re

from backend.settings import ROOT

try:
    from packaging.version import Version
except ImportError:  # packaging viene con pip; si falta, compara tuplas de enteros
    Version = None

TXT = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock"

PAQUETE_LOCK = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\]+)")
ESPECIFICADOR = re.compile(r"(===|~=|!=|==|>=|<=|>|<)\s*([^,\s]+)")
COMANDO_LOCK = "uv pip compile requirements.txt -o requirements.lock --python-version 3.12 --generate-hashes"


def _canonico(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def _version(texto: str):
    if Version is not None:
        return Version(texto)
    return tuple(int(x) for x in re.findall(r"\d+", texto)) or (0,)


def _compara(a, b) -> int:
    if isinstance(a, tuple):  # fallback sin packaging: empareja largo con ceros
        n = max(len(a), len(b))
        a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _partes(texto: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", texto)]


def _cumple(version: str, operador: str, pedida: str) -> bool:
    if pedida.endswith(".*") and operador in ("==", "!="):  # rango [X.Y, X.Y+1)
        base, arriba = _partes(pedida[:-2]), _partes(pedida[:-2])
        arriba[-1] += 1
        dentro = _compara(_version(version), _version(".".join(map(str, base)))) >= 0 and (
            _compara(_version(version), _version(".".join(map(str, arriba)))) < 0
        )
        return dentro if operador == "==" else not dentro
    if operador == "~=":  # ~=X.Y.Z equivale a >=X.Y.Z,<X.(Y+1)
        base = _partes(pedida)
        arriba = base[:-1]
        arriba[-1] += 1
        return _compara(_version(version), _version(pedida)) >= 0 and _compara(_version(version), _version(".".join(map(str, arriba)))) < 0
    cmp = _compara(_version(version), _version(pedida))
    return {
        "==": cmp == 0,
        "===": cmp == 0,
        "!=": cmp != 0,
        ">=": cmp >= 0,
        ">": cmp > 0,
        "<=": cmp <= 0,
        "<": cmp < 0,
    }[operador]


def _requisitos(texto_txt: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(nombre_canonico, [(operador, versión), ...])] desde requirements.txt."""
    requisitos = []
    for linea in texto_txt.splitlines():
        linea = linea.split("#", 1)[0].split(";", 1)[0].strip()
        if not linea or linea.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*(.*)$", linea)
        if not m:
            continue
        requisitos.append((_canonico(m.group(1)), ESPECIFICADOR.findall(m.group(2))))
    return requisitos


def _lock(texto_lock: str) -> dict[str, tuple[str, bool]]:
    """{nombre_canonico: (versión, tiene_hash_sha256)} desde requirements.lock."""
    paquetes = {}
    lineas = texto_lock.splitlines()
    i = 0
    while i < len(lineas):
        m = PAQUETE_LOCK.match(lineas[i])
        if not m:
            i += 1
            continue
        bloque = [lineas[i]]
        while bloque[-1].rstrip().endswith("\\") and i + 1 < len(lineas):
            i += 1
            bloque.append(lineas[i])
        paquetes[_canonico(m.group(1))] = (
            m.group(2),
            any("--hash=sha256:" in l for l in bloque),
        )
        i += 1
    return paquetes


def _incoherencias(texto_txt: str, texto_lock: str) -> list[str]:
    paquetes = _lock(texto_lock)
    errores = []
    for nombre, especificadores in _requisitos(texto_txt):
        if nombre not in paquetes:
            errores.append(f"{nombre}: esta en requirements.txt pero falta en requirements.lock -- regenera con: {COMANDO_LOCK}")
            continue
        version, _ = paquetes[nombre]
        for operador, pedida in especificadores:
            if not _cumple(version, operador, pedida):
                errores.append(
                    f"{nombre}: el lock fija {version} pero requirements.txt pide {operador}{pedida} -- regenera con: {COMANDO_LOCK}"
                )
    return errores


def _sin_hash(texto_lock: str) -> list[str]:
    return [
        f"{nombre}=={version}: no trae --hash=sha256: y el Dockerfile instala con --require-hashes -- regenera con: {COMANDO_LOCK}"
        for nombre, (version, tiene) in _lock(texto_lock).items()
        if not tiene
    ]


def test_lock_satisface_requirements_txt():
    errores = _incoherencias(TXT.read_text(encoding="utf-8"), LOCK.read_text(encoding="utf-8"))
    assert not errores, "\n".join(errores)


def test_cada_paquete_del_lock_trae_hash_sha256():
    faltantes = _sin_hash(LOCK.read_text(encoding="utf-8"))
    assert not faltantes, "\n".join(faltantes)


def test_detecta_version_que_no_cumple_el_especificador():
    errores = _incoherencias(
        "paquete-falso>=2.0\n",
        "paquete-falso==1.9.9 --hash=sha256:abc123\n",
    )
    assert len(errores) == 1
    assert "paquete-falso" in errores[0]
    assert "1.9.9" in errores[0]
    assert ">=2.0" in errores[0]


def test_detecta_paquete_que_falta_en_el_lock():
    errores = _incoherencias("paquete-nuevo==1.0\n", "paquete-falso==1.9.9 --hash=sha256:abc123\n")
    assert len(errores) == 1
    assert "paquete-nuevo" in errores[0]


def test_detecta_paquete_del_lock_sin_hash():
    assert _sin_hash("paquete-falso==1.9.9\n")
    assert not _sin_hash("paquete-falso==1.9.9 --hash=sha256:abc123\n")


def test_un_par_coherente_no_reporta_errores():
    errores = _incoherencias(
        "paquete-falso>=1.0,<2\notro==1.0.*\n",
        "paquete-falso==1.9.9 --hash=sha256:abc\notro==1.0.5 --hash=sha256:def\n",
    )
    assert not errores
