"""Presupuesto de peso de las páginas bajo demanda (DEBT-07, segunda parte de UX-15).

El arranque —lo que el navegador descarga antes del primer pintado: index.html,
app.css, app.js y sus imports estáticos, más las fuentes y el CSS de vendor que
referencia la portada— tiene su propio presupuesto en
scripts/local/peso_arranque.py. Este script mide los archivos propios de web/
(JS, CSS, HTML y el manifiesto; nada de web/vendor) y suma solo los que NO
viajan en el arranque: las demás páginas (lite, lista, pantalla, respuesta,
admin, datos, preguntas, plan), sus CSS y sus JS. Así una página nueva compite
con las otras páginas y no con el arranque, que es el número que sufre una
conexión rural.

    python scripts/local/presupuesto_peso.py            verifica umbrales (falla si se pasan)
    python scripts/local/presupuesto_peso.py --informe  tabla completa, siempre termina en 0
    python scripts/local/presupuesto_peso.py --json     medición en JSON

Medido el 2026-10-22 sobre main: 57,9 KB gzip bajo demanda (el arranque propio
son 195,9 KB y se miden aparte, en scripts/local/peso_arranque.py). El tope
queda en 60 KB: el margen es corto, así que la próxima página nueva
probablemente lo cruce y toque recortar o subirlo aquí. El tope por archivo
suelto (15 KB) sigue cubriendo todo lo propio, también lo del arranque.

Si el crecimiento es intencional, sube el tope aquí y explica por qué en el
CHANGELOG.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import peso_arranque

ROOT = Path(__file__).resolve().parents[2]

# 57,9 KB medidos el 2026-10-22; el tope de 60 KB deja poco margen.
PRESUPUESTO_PAGINAS_KB = 60
PRESUPUESTO_ARCHIVO_KB = 15  # app.css ≈ 13,8 KB medidos + ~8 % de holgura

GRUPOS = [
    ("js", "js/**/*.js"),
    ("css", "css/*.css"),
    ("html", "*.html"),
    ("manifiesto", "manifest.webmanifest"),
]

PISTA = (
    "Si el crecimiento es intencional, sube el tope en scripts/local/presupuesto_peso.py "
    "y explica por qué en el CHANGELOG; si no, recorta la página. El arranque tiene su "
    "propio tope en scripts/local/peso_arranque.py."
)


def medir(raiz: Path) -> list[dict]:
    """Peso en disco y gzip -9 de cada archivo propio, con su presupuesto
    («arranque» o «bajo demanda»)."""
    web = raiz / "web"
    # El arranque son las dos secciones de peso_arranque: lo bloqueante y lo
    # que solo llega por import() desde la portada. Ninguna de las dos se mide
    # aquí (DEBT-07).
    bloqueantes, diferidos = peso_arranque.archivos_arranque(raiz)
    arranque = {ruta.resolve() for _, ruta in [*bloqueantes, *diferidos]}
    filas = []
    for tipo, patron in GRUPOS:
        for ruta in sorted(web.glob(patron)):
            if not ruta.is_file():
                continue
            datos = ruta.read_bytes()
            filas.append(
                {
                    "archivo": ruta.relative_to(raiz).as_posix(),
                    "tipo": tipo,
                    "presupuesto": "arranque" if ruta.resolve() in arranque else "bajo demanda",
                    "disco": len(datos),
                    "gzip": len(gzip.compress(datos, compresslevel=9, mtime=0)),
                }
            )
    return filas


def imprimir_tabla(filas: list[dict]) -> None:
    """Tabla de los archivos bajo demanda, agrupados por tipo. El arranque se
    muestra aparte en peso_arranque.py --informe."""
    bajo = [f for f in filas if f["presupuesto"] == "bajo demanda"]
    print(f"{'archivo':44s} {'disco':>9s} {'gzip':>9s}")
    tipo = None
    tot_disco = tot_gzip = 0
    for f in bajo:
        if f["tipo"] != tipo:
            tipo = f["tipo"]
            print(tipo.upper())
        print(f"  {f['archivo']:42s} {f['disco'] / 1024:8.1f} K {f['gzip'] / 1024:8.1f} K")
        tot_disco += f["disco"]
        tot_gzip += f["gzip"]
    print(f"{'TOTAL BAJO DEMANDA':44s} {tot_disco / 1024:8.1f} K {tot_gzip / 1024:8.1f} K")
    arranque = sum(f["gzip"] for f in filas if f["presupuesto"] == "arranque")
    print(f"\nArranque propio (aparte): {arranque / 1024:.1f} KB gzip; lo mide scripts/local/peso_arranque.py.")


def excesos(filas: list[dict]) -> list[str]:
    """Lista de incumplimientos: total bajo demanda y tope por archivo suelto."""
    bajo = [f for f in filas if f["presupuesto"] == "bajo demanda"]
    total = sum(f["gzip"] for f in bajo)
    tope = PRESUPUESTO_PAGINAS_KB * 1024
    fallas = []
    if total > tope:
        pesado = max(bajo, key=lambda f: f["gzip"]) if bajo else None
        detalle = f"; el archivo más pesado es {pesado['archivo']} ({pesado['gzip'] / 1024:.1f} KB)" if pesado else ""
        fallas.append(
            f"las páginas bajo demanda suman {total / 1024:.1f} KB gzip y superan el tope de "
            f"{PRESUPUESTO_PAGINAS_KB} KB por {(total - tope) / 1024:.1f} KB{detalle}"
        )
    tope_archivo = PRESUPUESTO_ARCHIVO_KB * 1024
    for f in filas:
        if f["gzip"] > tope_archivo:
            fallas.append(
                f"[{f['presupuesto']}] {f['archivo']} pesa {f['gzip'] / 1024:.1f} KB gzip y supera el "
                f"tope por archivo de {PRESUPUESTO_ARCHIVO_KB} KB por {(f['gzip'] - tope_archivo) / 1024:.1f} KB"
            )
    return fallas


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
    total = sum(f["gzip"] for f in filas if f["presupuesto"] == "bajo demanda")
    arranque = sum(f["gzip"] for f in filas if f["presupuesto"] == "arranque")

    if args.json:
        print(json.dumps({"archivos": filas, "total_gzip": total, "arranque_gzip": arranque}, ensure_ascii=False, indent=2))
        return 0
    if args.informe:
        imprimir_tabla(filas)
        return 0

    fallas = excesos(filas)
    if fallas:
        print("Presupuesto de peso excedido:")
        for falla in fallas:
            print(f"  - {falla}")
        print(PISTA)
        return 1
    print(f"Páginas bajo demanda dentro del presupuesto: {total / 1024:.1f} KB gzip de {PRESUPUESTO_PAGINAS_KB} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
