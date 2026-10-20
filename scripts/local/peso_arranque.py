"""Peso del arranque de BRASA: lo que el navegador descarga antes de poder
mostrar y usar la aplicación (QA-62).

El presupuesto de `presupuesto_peso.py` suma todo web/ junto y no distingue
lo que bloquea el primer pintado de lo que se descarga solo cuando se pide.
Este script parte de web/index.html, toma la portada y las referencias que
bloquean el arranque —<link rel="stylesheet">, <link rel="preload" as="font">
y <script type="module" src>— y sigue los imports relativos de esos módulos
de forma transitiva (se ignoran web/vendor y lo externo, igual que en
tests/test_estaticas_guardas.py).

    python scripts/local/peso_arranque.py            verifica el umbral (falla si se pasa)
    python scripts/local/peso_arranque.py --informe  tabla completa, siempre termina en 0
    python scripts/local/peso_arranque.py --json     medición en JSON

Umbral medido el 2026-10-20 sobre main: 229,0 KB gzip en total (los dos
tercios son las fuentes precargadas y las once vistas que app.js importa
de forma estática). Se fijó con ~10 % de holgura. Si el crecimiento es
intencional, súbelo aquí y explica por qué en el CHANGELOG.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRESUPUESTO_ARRANQUE_KB = 252  # 229,0 KB medidos el 2026-10-20 + ~10 % de holgura

# Referencias que bloquean el arranque dentro de index.html, en el orden en
# que el navegador las encuentra: cada entrada es (grupo, regex del tag).
_REF_TAGS = [
    ("css", re.compile(r'<link\b[^>]*rel=["\']stylesheet["\'][^>]*>', re.I)),
    ("fuente", re.compile(r'<link\b[^>]*rel=["\']preload["\'][^>]*as=["\']font["\'][^>]*>', re.I)),
    ("js", re.compile(r'<script\b[^>]*type=["\']module["\'][^>]*>', re.I)),
]
_ATTR = re.compile(r'\b(?:src|href)\s*=\s*["\']([^"\']+)["\']')

# Imports que carga el navegador: `import ... from '…'`, `export ... from '…'`,
# `import '…'` y `import('…')`. Solo se siguen las rutas relativas.
_IMPORT_ESTATICO = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]")
_IMPORT_DIRECTO = re.compile(r"\bimport\s*(?:\(\s*)?['\"]([^'\"]+)['\"]")

PISTA = (
    "Si el crecimiento es intencional, sube el umbral en "
    "scripts/local/peso_arranque.py y explica por qué en el CHANGELOG; "
    "si no, recorta el arranque o mueve la vista a carga diferida."
)


def _resolver(raiz: Path, ref: str, base: Path) -> Path | None:
    """Convierte una referencia del HTML en un archivo local, o None si es
    externa (https://…, //cdn…) o apunta fuera del repo."""
    if re.match(r"(?:https?:)?//", ref):
        return None
    ruta = (raiz / ref.lstrip("/")).resolve() if ref.startswith("/") else (base / ref).resolve()
    return ruta if ruta.is_relative_to(raiz.resolve()) else None


def referencias_html(index: Path, raiz: Path) -> list[tuple[str, Path]]:
    """(grupo, archivo) de la portada y de cada referencia que bloquea el
    arranque en index.html."""
    html = index.read_text(encoding="utf-8")
    refs: list[tuple[str, Path]] = [("html", index)]
    for grupo, patron in _REF_TAGS:
        for tag in patron.findall(html):
            attr = _ATTR.search(tag)
            if not attr:
                continue
            ruta = _resolver(raiz, attr.group(1), index.parent)
            if ruta is not None:
                refs.append((grupo, ruta))
    return refs


def _import_relativos(archivo: Path) -> list[Path]:
    src = archivo.read_text(encoding="utf-8")
    return [
        (archivo.parent / ref).resolve()
        for ref in _IMPORT_ESTATICO.findall(src) + _IMPORT_DIRECTO.findall(src)
        if ref.startswith(("./", "../"))
    ]


def modulos_arranque(semillas: list[Path], raiz: Path) -> set[Path]:
    """Módulos alcanzables desde los <script type="module"> por imports
    relativos. web/vendor y lo que cae fuera del repo quedan fuera."""
    raiz = raiz.resolve()
    modulos: set[Path] = set()
    pendientes = [s.resolve() for s in semillas]
    while pendientes:
        modulo = pendientes.pop()
        if not modulo.is_file() or not modulo.is_relative_to(raiz) or "vendor" in modulo.parts or modulo in modulos:
            continue
        modulos.add(modulo)
        pendientes.extend(_import_relativos(modulo))
    return modulos


def archivos_arranque(raiz: Path) -> list[tuple[str, Path]]:
    """La portada, sus referencias bloqueantes y los módulos transitivos,
    sin duplicados."""
    web = raiz / "web"
    refs = referencias_html(web / "index.html", raiz)
    modulos = modulos_arranque([ruta for grupo, ruta in refs if grupo == "js"], raiz)
    vistos = {ruta for _, ruta in refs}
    for modulo in sorted(modulos - vistos):
        refs.append(("js", modulo))
    return refs


def medir(raiz: Path) -> list[dict]:
    """Peso en disco y gzip -9 de cada archivo del arranque, por grupo."""
    filas = []
    for tipo, ruta in archivos_arranque(raiz):
        if not ruta.is_file():
            continue
        datos = ruta.read_bytes()
        filas.append(
            {
                "archivo": ruta.relative_to(raiz).as_posix(),
                "tipo": tipo,
                "disco": len(datos),
                "gzip": len(gzip.compress(datos, compresslevel=9, mtime=0)),
            }
        )
    return filas


def imprimir_tabla(filas: list[dict]) -> None:
    print(f"{'archivo':44s} {'disco':>9s} {'gzip':>9s}")
    tipo = None
    sub_disco = sub_gzip = tot_disco = tot_gzip = 0
    for f in filas:
        if f["tipo"] != tipo:
            if tipo is not None:
                print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
            tipo = f["tipo"]
            sub_disco = sub_gzip = 0
            print(tipo.upper())
        print(f"  {f['archivo']:42s} {f['disco'] / 1024:8.1f} K {f['gzip'] / 1024:8.1f} K")
        sub_disco += f["disco"]
        sub_gzip += f["gzip"]
        tot_disco += f["disco"]
        tot_gzip += f["gzip"]
    if tipo is not None:
        print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
    print(f"{'TOTAL':44s} {tot_disco / 1024:8.1f} K {tot_gzip / 1024:8.1f} K")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--informe", action="store_true", help="imprime la tabla completa y termina en 0")
    p.add_argument("--json", action="store_true", help="imprime la medición en JSON")
    p.add_argument("--raiz", type=Path, default=ROOT, help="raíz del proyecto (por defecto, este repo)")
    args = p.parse_args(argv)

    if not (args.raiz / "web" / "index.html").is_file():
        print(f"No existe {args.raiz / 'web' / 'index.html'}", file=sys.stderr)
        return 2
    filas = medir(args.raiz)
    total = sum(f["gzip"] for f in filas)

    if args.json:
        print(json.dumps({"archivos": filas, "total_gzip": total}, ensure_ascii=False, indent=2))
        return 0
    if args.informe:
        imprimir_tabla(filas)
        return 0

    tope = PRESUPUESTO_ARRANQUE_KB * 1024
    if total > tope:
        print(
            f"Peso del arranque excedido: {total / 1024:.1f} KB gzip supera el "
            f"presupuesto de {PRESUPUESTO_ARRANQUE_KB} KB por {(total - tope) / 1024:.1f} KB"
        )
        print(PISTA)
        return 1
    print(f"Peso del arranque dentro del presupuesto: {total / 1024:.1f} KB gzip de {PRESUPUESTO_ARRANQUE_KB} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
