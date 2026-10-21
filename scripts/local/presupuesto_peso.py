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

Remedido el 2026-10-20: main ya andaba en ≈ 164,9 KB gzip y el módulo nuevo
web/js/calor.js (AGUA-06, ≈ 0,8 KB gzip) cruzó el tope de 165 KB; el total
queda en ≈ 165,7 KB y el umbral sube a 180 KB para mantener ~8 % de holgura.
El mismo día el total subió a 200 KB: con ese crecimiento de main y las
pestañas Registro y Moderadores del panel /admin (SEC-10) el total medido
es ≈ 184 KB gzip y se mantiene una holgura del ~8 %.
OFI-08 agrega web/js/exposure.js (≈ 1,1 KB gzip): el total medido queda en
≈ 194,6 KB y sigue bajo el presupuesto de 200 KB.
FIX-56 agrega web/js/foto.js y la reducción de la foto en web/js/ui.js
(≈ 1,7 KB gzip): main ya andaba en ≈ 199,1 KB, el total medido queda en
≈ 200,8 KB y el umbral sube a 204 KB (~1,6 % de holgura).
El rebase de MAPA-01 sobre main (2026-10-20) suma web/js/capas.js y el control
de capas en web/js/views/mapa.js y web/js/map.js: el total medido queda en
≈ 207,9 KB y el umbral sube a 210 KB (~1,0 % de holgura).
El rebase de UX-45 sobre main (2026-10-20) suma web/js/pantalla-rotacion.js y
el comparador semana a semana en web/js/pantalla.js: el total medido queda en
≈ 210,1 KB y el umbral sube a 212 KB (~0,9 % de holgura).
CONT-18 reescribe web/preguntas.html con once preguntas (≈ 2,9 KB gzip): el
total medido queda en ≈ 213,1 KB y el umbral sube a 215 KB (~0,9 % de holgura).
PERF-05 (2026-10-20): main mide ≈ 212,8 KB gzip y el umbral de 215 KB queda a
2,2 KB, así que cualquier vista nueva lo cruza; se sube a 225 KB para dejar
margen a la fábrica nocturna. El recorte de fondo se decide aparte.
SEO-01 (2026-10-21): el ld+json FAQPage de web/preguntas.html suma ≈ 0,4 KB
gzip; main ya andaba en ≈ 226 KB sobre el tope de 225 KB, el total medido
queda en ≈ 226,4 KB y el umbral sube a 230 KB (~1,6 % de holgura). El margen
de la fábrica se agota: el recorte de fondo sigue pendiente.
CALIDAD-02 (2026-10-21): el cupo de Open-Meteo y los errores de la última
ronda suman ≈ 1,4 KB gzip en web/js/views/calidad.js: cabe en el tope de
230 KB ya vigente, sin subirlo.
PORTADA-02 (2026-10-21): la portada de emergencia para arranque fallido suma
≈ 0,6 KB gzip en web/index.html; main ya andaba en ≈ 232,3 KB (sobre el tope
de 230 KB) y el total medido queda en ≈ 232,9 KB: el umbral sube a 235 KB
(~0,9 % de holgura). El recorte de fondo sigue pendiente.
MOD-EVIDENCIA (2026-10-21): el chip de evidencia satelital en la tarjeta de
moderación (web/js/admin.js, ≈ 1,2 KB gzip) deja el total medido en ≈ 235,9 KB;
el umbral sube a 238 KB (~0,9 % de holgura). El recorte de fondo sigue pendiente.
GPACK-09 + PERF-141 (2026-10-21): el puntaje de «Mi casa preparada»
(web/js/lista-score.js y el bloque en web/lista.html) y el latido dormido en
web/js/map.js sumaron ≈ 5,5 KB sin subir el tope: el total medido queda en
≈ 241,4 KB y el umbral sube a 245 KB (~1,5 % de holgura). El recorte de fondo
sigue pendiente.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 241,4 KB medidos el 2026-10-21; el margen se agota, el recorte de fondo
# sigue pendiente. GPACK-09 (lista-score.js + lista.html) y PERF-141 (map.js)
# sumaron ≈ 5,5 KB sin subir el tope de 238 KB.
PRESUPUESTO_TOTAL_KB = 245  # 241,4 KB medidos el 2026-10-21 (GPACK-09 + PERF-141; main ya andaba 3,4 KB sobre el tope)
PRESUPUESTO_ARCHIVO_KB = 15  # app.css ≈ 13,8 KB medidos + ~8 % de holgura

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
