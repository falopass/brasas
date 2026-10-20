"""Presupuesto de peso del frontend propio (UX-33, segunda parte de UX-15).

Suma los bytes de los archivos propios de web/ (JS, CSS, HTML y el manifiesto;
nada de web/vendor ni otros recursos de terceros) y los compara con un tope.
Corre dentro de `python dev.py check` para que el frontend no engorde sin
que nadie lo note.

    python scripts/local/presupuesto_peso.py            verifica umbrales (falla si se pasan)
    python scripts/local/presupuesto_peso.py --informe  tabla completa, siempre termina en 0
    python scripts/local/presupuesto_peso.py --json     medición en JSON

Umbrales medidos el 2026-10-19 sobre main (tras la carga diferida de MapLibre
del PR #141): total propio ≈ 149 KB gzip y archivo más grande ≈ 13,4 KB gzip
(web/css/app.css). Se fijaron con ~10 % de holgura. Si el crecimiento es
intencional, súbelos aquí y explica por qué en el CHANGELOG.

OFI-08 agrega web/js/exposure.js (~1,1 KB gzip): el total medido pasa de
178,9 KB a 180,0 KB y el presupuesto sube a 185 KB (~2,7 % de holgura).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# OFI-08 deja el total medido en 180,0 KB: presupuesto en 185 KB (~2,7 % de
# holgura); el próximo aumento se revisa con el reporte de peso antes de aprobarse.
PRESUPUESTO_TOTAL_KB = 185
PRESUPUESTO_ARCHIVO_KB = 15  # app.css ≈ 13,4 KB medidos + ~10 % de holgura

GRUPOS = [
    ("js", "js/**/*.js"),
    ("css", "css/*.css"),
    ("html", "*.html"),
    ("manifiesto", "manifest.webmanifest"),
]

PISTA = "Si el crecimiento es intencional, sube el umbral en scripts/local/presupuesto_peso.py y explica por qué en el CHANGELOG."


def medir(web: Path) -> list[dict]:
    """Peso en disco y gzip -9 de cada archivo propio, agrupado por tipo."""
    filas = []
    for tipo, patron in GRUPOS:
        for ruta in sorted(web.glob(patron)):
            if not ruta.is_file():
                continue
            datos = ruta.read_bytes()
            filas.append(
                {
                    "archivo": ruta.relative_to(web.parent).as_posix(),
                    "tipo": tipo,
                    "disco": len(datos),
                    "gzip": len(gzip.compress(datos, compresslevel=9, mtime=0)),
                }
            )
    return filas


def imprimir_tabla(filas: list[dict]) -> None:
    print(f"{'archivo':44s} {'disco':>9s} {'gzip':>9s}")
    tipo = None
    tot_disco = tot_gzip = 0
    for f in filas:
        if f["tipo"] != tipo:
            tipo = f["tipo"]
            print(tipo.upper())
        print(f"  {f['archivo']:42s} {f['disco'] / 1024:8.1f} K {f['gzip'] / 1024:8.1f} K")
        tot_disco += f["disco"]
        tot_gzip += f["gzip"]
    print(f"{'TOTAL':44s} {tot_disco / 1024:8.1f} K {tot_gzip / 1024:8.1f} K")


def excesos(filas: list[dict]) -> list[str]:
    """Lista de incumplimientos: total propio y tope por archivo suelto."""
    total = sum(f["gzip"] for f in filas)
    tope_total = PRESUPUESTO_TOTAL_KB * 1024
    tope_archivo = PRESUPUESTO_ARCHIVO_KB * 1024
    fallas = []
    if total > tope_total:
        fallas.append(
            f"el total gzip ({total / 1024:.1f} KB) supera el presupuesto de "
            f"{PRESUPUESTO_TOTAL_KB} KB por {(total - tope_total) / 1024:.1f} KB"
        )
    for f in filas:
        if f["gzip"] > tope_archivo:
            fallas.append(
                f"{f['archivo']} pesa {f['gzip'] / 1024:.1f} KB gzip y supera el tope por "
                f"archivo de {PRESUPUESTO_ARCHIVO_KB} KB por {(f['gzip'] - tope_archivo) / 1024:.1f} KB"
            )
    return fallas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--informe", action="store_true", help="imprime la tabla completa y termina en 0")
    p.add_argument("--json", action="store_true", help="imprime la medición en JSON")
    p.add_argument("--raiz", type=Path, default=ROOT, help="raíz del proyecto (por defecto, este repo)")
    args = p.parse_args(argv)

    web = args.raiz / "web"
    if not web.is_dir():
        print(f"No existe {web}", file=sys.stderr)
        return 2
    filas = medir(web)

    if args.json:
        print(json.dumps({"archivos": filas, "total_gzip": sum(f["gzip"] for f in filas)}, ensure_ascii=False, indent=2))
        return 0
    if args.informe:
        imprimir_tabla(filas)
        return 0

    total = sum(f["gzip"] for f in filas)
    fallas = excesos(filas)
    if fallas:
        print("Presupuesto de peso excedido:")
        for falla in fallas:
            print(f"  - {falla}")
        print(PISTA)
        return 1
    print(f"Peso del frontend dentro del presupuesto: {total / 1024:.1f} KB gzip de {PRESUPUESTO_TOTAL_KB} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
