"""Guarda de lenguaje de BRASA (QA-79): el escenario se rotula como estimado,
nunca como una predicción.

Recorre los textos visibles (`web/**/*.html` y `web/js/**/*.js`), los
literales de `backend/**/*.py` y los JSON de `web/data/` (narraciones de
«Historia», fichas de comuna), y busca fórmulas que prometen o anticipan el
fuego. En los JSON se miran solo los valores; las claves no son texto visible.
Deja fuera `docs/investigacion/`, `tests/` y `web/vendor/`.

    python scripts/local/chequeo_lenguaje.py
    python scripts/local/chequeo_lenguaje.py --raiz <directorio>

Sale 0 si no hay hallazgos y 1 si los hay, con `archivo:línea` y el fragmento.
"""

from __future__ import annotations

import argparse
import ast
import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATRONES = ("web/**/*.html", "web/js/**/*.js", "web/data/**/*.json", "backend/**/*.py")
EXCLUIDOS = ("docs/investigacion/", "tests/", "web/vendor/")

# (fórmula, expresión regular). «llegará» y «quemará» cubren también el plural.
FORMULAS = (
    ("llegará", re.compile(r"\bllegarán?\b", re.IGNORECASE)),
    ("va a llegar", re.compile(r"\bvan? a llegar\b", re.IGNORECASE)),
    ("se quemará", re.compile(r"\bse quemarán?\b", re.IGNORECASE)),
    ("quemará", re.compile(r"\bquemarán?\b", re.IGNORECASE)),
    ("se propagará a", re.compile(r"\bse propagarán? a\b", re.IGNORECASE)),
    ("predice", re.compile(r"\bpredice\b", re.IGNORECASE)),
    ("garantizado", re.compile(r"\bgarantizad[oa]s?\b", re.IGNORECASE)),
    ("predicción", re.compile(r"\bpredicci[óo]n\b", re.IGNORECASE)),
)
# «No es una predicción» es la forma correcta de negar la etiqueta: no es un hallazgo.
NEGACION = re.compile(r"\bno es(?: una)?\s*$", re.IGNORECASE)

# En un JSON la clave («"campo":») no es texto que el vecino lee: se quita antes de revisar la línea.
CLAVE_JSON = re.compile(r'"(?:[^"\\]|\\.)*"\s*:')


def _hallazgo(relativa: str, numero: int, linea: str) -> str | None:
    for etiqueta, patron in FORMULAS:
        for match in patron.finditer(linea):
            if etiqueta == "predicción" and NEGACION.search(linea[: match.start()]):
                continue
            desde = max(0, match.start() - 60)
            hasta = min(len(linea), match.end() + 60)
            return f"{relativa}:{numero}: {linea[desde:hasta].strip()}"
    return None


def _lineas_literales_py(texto: str, nombre: str) -> Iterator[tuple[int, str]]:
    """Líneas de cada literal de texto, con su número de línea en el archivo."""
    for nodo in ast.walk(ast.parse(texto, filename=nombre)):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            for desplazamiento, linea in enumerate(nodo.value.splitlines()):
                yield nodo.lineno + desplazamiento, linea


def hallazgos(raiz: Path = ROOT) -> list[str]:
    encontrados: set[tuple[str, int, str]] = set()
    for patron in PATRONES:
        for ruta in raiz.glob(patron):
            relativa = ruta.relative_to(raiz).as_posix()
            if relativa.startswith(EXCLUIDOS):
                continue
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            if ruta.suffix == ".py":
                lineas = _lineas_literales_py(texto, relativa)
            elif ruta.suffix == ".json":
                lineas = ((n, CLAVE_JSON.sub("", l)) for n, l in enumerate(texto.splitlines(), 1))
            else:
                lineas = enumerate(texto.splitlines(), 1)
            for numero, linea in lineas:
                hallazgo = _hallazgo(relativa, numero, linea)
                if hallazgo:
                    encontrados.add((relativa, numero, hallazgo))
    return [hallazgo for _, _, hallazgo in sorted(encontrados)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Busca fórmulas de predicción en los textos visibles de BRASA")
    parser.add_argument("--raiz", type=Path, default=ROOT, help="raíz del proyecto (para pruebas)")
    args = parser.parse_args(argv)
    encontrados = hallazgos(args.raiz)
    if not encontrados:
        print("Sin hallazgos: el lenguaje de escenario está en orden.")
        return 0
    for hallazgo in encontrados:
        print(hallazgo)
    print(f"{len(encontrados)} hallazgo(s): usa «escenario estimado» y no anuncies el fuego.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
