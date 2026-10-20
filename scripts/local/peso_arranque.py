"""Peso del arranque de BRASA: lo que el navegador descarga antes de poder
mostrar y usar la aplicación (QA-62).

El presupuesto de `presupuesto_peso.py` mide aparte las páginas que se
descargan solo cuando se piden (DEBT-07). Este script parte de web/index.html,
toma la portada y las referencias que
bloquean el arranque —<link rel="stylesheet">, <link rel="preload" as="font">
y <script type="module" src>— y sigue los imports relativos de esos módulos
de forma transitiva (se ignoran web/vendor y lo externo, igual que en
tests/test_estaticas_guardas.py).

Separa dos conjuntos y no esconde ninguno:
- «bloqueante»: lo alcanzable por imports estáticos (`import … from`,
  `export … from` e `import '…'`). Es lo que el navegador descarga y parsea
  antes del primer pintado; se mide contra PRESUPUESTO_ARRANQUE_KB.
- «diferido»: lo alcanzable solo por `import('…')` desde el arranque. No
  bloquea el primer pintado, pero se informa siempre y suma al total, que
  tiene su propio tope (PRESUPUESTO_TOTAL_KB) para que no crezca sin control.

    python scripts/local/peso_arranque.py            verifica ambos umbrales
    python scripts/local/peso_arranque.py --informe  tabla completa, siempre termina en 0
    python scripts/local/peso_arranque.py --json     medición en JSON

Medido el 2026-10-22 con las vistas en carga diferida: 134,6 KB gzip de
bloqueante y 232,0 KB de total. Presupuestos: 180 KB bloqueante y 300 KB
total. Si el crecimiento es intencional, súbelo aquí y explica por qué en el
CHANGELOG; si no, recorta el arranque o mueve la vista a carga diferida.

Este es el tope del arranque. El de las páginas que no se abren desde
index.html (lite, lista, pantalla, respuesta…) está en
scripts/local/presupuesto_peso.py, para que una página nueva no compita con
lo que bloquea el primer pintado (DEBT-07).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRESUPUESTO_ARRANQUE_KB = 180  # bloqueante: lo que se descarga antes del primer pintado
PRESUPUESTO_TOTAL_KB = 300  # bloqueante + diferido; evita que lo diferido crezca sin control

# Referencias que bloquean el arranque dentro de index.html, en el orden en
# que el navegador las encuentra: cada entrada es (grupo, regex del tag).
_REF_TAGS = [
    ("css", re.compile(r'<link\b[^>]*rel=["\']stylesheet["\'][^>]*>', re.I)),
    ("fuente", re.compile(r'<link\b[^>]*rel=["\']preload["\'][^>]*as=["\']font["\'][^>]*>', re.I)),
    ("js", re.compile(r'<script\b[^>]*type=["\']module["\'][^>]*>', re.I)),
]
_ATTR = re.compile(r'\b(?:src|href)\s*=\s*["\']([^"\']+)["\']')

# Imports que bloquean el arranque: `import … from '…'`, `export … from '…'`
# e `import '…'`. Los `import('…')` dinámicos se miden aparte. Solo se
# siguen las rutas relativas.
_IMPORT_ESTATICO = re.compile(r"\b(?:import|export)\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
# Imports diferidos: `import('…')`, que el navegador pide solo al ejecutarse.
_IMPORT_DINAMICO = re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]")

PISTA = (
    "Si el crecimiento es intencional, sube el umbral en "
    "scripts/local/peso_arranque.py y explica por qué en el CHANGELOG; "
    "si no, recorta el arranque o mueve la vista a carga diferida. Las páginas "
    "que no se abren desde index.html se miden aparte, en "
    "scripts/local/presupuesto_peso.py."
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


def _import_relativos(archivo: Path, patron: re.Pattern[str]) -> list[Path]:
    src = archivo.read_text(encoding="utf-8")
    return [(archivo.parent / ref).resolve() for ref in patron.findall(src) if ref.startswith(("./", "../"))]


def _alcanzables(semillas: list[Path], raiz: Path, patrones: tuple[re.Pattern[str], ...]) -> set[Path]:
    """Módulos alcanzables desde las semillas siguiendo los patrones dados.
    web/vendor y lo que cae fuera del repo quedan fuera."""
    raiz = raiz.resolve()
    modulos: set[Path] = set()
    pendientes = [s.resolve() for s in semillas]
    while pendientes:
        modulo = pendientes.pop()
        if not modulo.is_file() or not modulo.is_relative_to(raiz) or "vendor" in modulo.parts or modulo in modulos:
            continue
        modulos.add(modulo)
        for patron in patrones:
            pendientes.extend(_import_relativos(modulo, patron))
    return modulos


def modulos_arranque(semillas: list[Path], raiz: Path) -> set[Path]:
    """Módulos que bloquean el primer pintado: solo imports estáticos."""
    return _alcanzables(semillas, raiz, (_IMPORT_ESTATICO,))


def modulos_diferidos(semillas: list[Path], raiz: Path) -> set[Path]:
    """Módulos que solo llegan por import() desde el arranque. Si un módulo
    también es alcanzable de forma estática, cuenta como bloqueante."""
    bloqueantes = modulos_arranque(semillas, raiz)
    destinos = [destino for modulo in bloqueantes for destino in _import_relativos(modulo, _IMPORT_DINAMICO)]
    return _alcanzables(destinos, raiz, (_IMPORT_ESTATICO, _IMPORT_DINAMICO)) - bloqueantes


def archivos_arranque(raiz: Path) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """(bloqueantes, diferidos): la portada, sus referencias bloqueantes y los
    módulos transitivos de cada conjunto, sin duplicados."""
    web = raiz / "web"
    refs = referencias_html(web / "index.html", raiz)
    semillas = [ruta for grupo, ruta in refs if grupo == "js"]
    bloqueantes = modulos_arranque(semillas, raiz)
    diferidos = modulos_diferidos(semillas, raiz)
    vistos = {ruta for _, ruta in refs}
    bloqueantes_refs = list(refs)
    for modulo in sorted(bloqueantes - vistos):
        bloqueantes_refs.append(("js", modulo))
    return bloqueantes_refs, [("js", modulo) for modulo in sorted(diferidos)]


def medir(raiz: Path) -> list[dict]:
    """Peso en disco y gzip -9 de cada archivo, con su sección y grupo."""
    filas = []
    bloqueantes, diferidos = archivos_arranque(raiz)
    for seccion, refs in (("bloqueante", bloqueantes), ("diferido", diferidos)):
        for tipo, ruta in refs:
            if not ruta.is_file():
                continue
            datos = ruta.read_bytes()
            filas.append(
                {
                    "archivo": ruta.relative_to(raiz).as_posix(),
                    "tipo": tipo,
                    "seccion": seccion,
                    "disco": len(datos),
                    "gzip": len(gzip.compress(datos, compresslevel=9, mtime=0)),
                }
            )
    return filas


def imprimir_tabla(filas: list[dict]) -> None:
    print(f"{'archivo':44s} {'disco':>9s} {'gzip':>9s}")
    total_disco = total_gzip = 0
    for seccion in ("bloqueante", "diferido"):
        print(seccion.upper())
        sec_disco = sec_gzip = 0
        tipo = None
        sub_disco = sub_gzip = 0
        for f in filas:
            if f["seccion"] != seccion:
                continue
            if f["tipo"] != tipo:
                if tipo is not None:
                    print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
                tipo = f["tipo"]
                sub_disco = sub_gzip = 0
                print(f"  {tipo.upper()}")
            print(f"  {f['archivo']:42s} {f['disco'] / 1024:8.1f} K {f['gzip'] / 1024:8.1f} K")
            sub_disco += f["disco"]
            sub_gzip += f["gzip"]
            sec_disco += f["disco"]
            sec_gzip += f["gzip"]
            total_disco += f["disco"]
            total_gzip += f["gzip"]
        if tipo is not None:
            print(f"  {'subtotal':42s} {sub_disco / 1024:8.1f} K {sub_gzip / 1024:8.1f} K")
        print(f"  {'subtotal ' + seccion:42s} {sec_disco / 1024:8.1f} K {sec_gzip / 1024:8.1f} K")
    print(f"{'TOTAL':44s} {total_disco / 1024:8.1f} K {total_gzip / 1024:8.1f} K")


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
    bloqueante = sum(f["gzip"] for f in filas if f["seccion"] == "bloqueante")
    diferido = sum(f["gzip"] for f in filas if f["seccion"] == "diferido")
    total = bloqueante + diferido

    if args.json:
        print(
            json.dumps(
                {
                    "bloqueante": [f for f in filas if f["seccion"] == "bloqueante"],
                    "diferido": [f for f in filas if f["seccion"] == "diferido"],
                    "bloqueante_gzip": bloqueante,
                    "diferido_gzip": diferido,
                    "total_gzip": total,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.informe:
        imprimir_tabla(filas)
        return 0

    errores = []
    tope_bloqueante = PRESUPUESTO_ARRANQUE_KB * 1024
    if bloqueante > tope_bloqueante:
        pesado = max((f for f in filas if f["seccion"] == "bloqueante"), key=lambda f: f["gzip"])
        errores.append(
            f"Peso del arranque excedido (bloqueante): {bloqueante / 1024:.1f} KB gzip supera el "
            f"presupuesto de {PRESUPUESTO_ARRANQUE_KB} KB por "
            f"{(bloqueante - tope_bloqueante) / 1024:.1f} KB; "
            f"el archivo más pesado es {pesado['archivo']} ({pesado['gzip'] / 1024:.1f} KB)"
        )
    if total > PRESUPUESTO_TOTAL_KB * 1024:
        pesado_total = max(filas, key=lambda f: f["gzip"])
        errores.append(
            f"Peso total excedido: {total / 1024:.1f} KB gzip supera el "
            f"presupuesto de {PRESUPUESTO_TOTAL_KB} KB por "
            f"{(total - PRESUPUESTO_TOTAL_KB * 1024) / 1024:.1f} KB; "
            f"el archivo más pesado es {pesado_total['archivo']} ({pesado_total['gzip'] / 1024:.1f} KB)"
        )
    if errores:
        print("\n".join(errores))
        print(PISTA)
        return 1
    print(
        f"Peso del arranque dentro del presupuesto: bloqueante {bloqueante / 1024:.1f} KB gzip "
        f"de {PRESUPUESTO_ARRANQUE_KB} KB; diferido {diferido / 1024:.1f} KB; "
        f"total {total / 1024:.1f} KB gzip de {PRESUPUESTO_TOTAL_KB} KB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
