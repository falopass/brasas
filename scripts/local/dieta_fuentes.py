"""Dieta de las tipografías de BRASA (PESO-02): recorta las fuentes variables a
los ejes y glifos que la interfaz realmente usa.

Las dos familias venían como variables completas (Anybody 56,9 KB con wght
100–900 y wdth 50–150 %; Public Sans 26,8 KB con wght 100–900): ~84 KB por
persona en cada visita sin caché. La interfaz solo usa wght 600–800 en los
títulos, wdth 62–125 % y wght 400–800 en el texto; además las fuentes latin
traían glifos que ningún texto del sitio muestra.

El script instancia los ejes a los rangos en uso (con margen) y recorta los
glifos a los caracteres presentes en los archivos propios de web/ más el
latín-1 completo, para que un texto nuevo en español nunca quede sin letra.
Los rangos quedan declarados en los @font-face de web/css/app.css: si se
amplía el uso tipográfico, hay que tocar los tres lugares a la vez.

    python scripts/local/dieta_fuentes.py           reescribe los .woff2 en su sitio
    python scripts/local/dieta_fuentes.py --check   falla si lo commiteado no coincide

Requiere fontTools[woff] (requirements-dev.txt). Medido el 2026-10-21:
Anybody 56.888 → ~46 KB; Public Sans 26.832 → ~23 KB (~15 KB menos por visita).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUENTES_DIR = ROOT / "web" / "vendor" / "fonts"

# (archivo, ejes: {tag: (mínimo, máximo) a conservar}). Los rangos cubren lo que
# web/css/*.css pide hoy con margen para el próximo ajuste de diseño.
FUENTES = {
    "anybody-latin-standard-normal.woff2": {"wght": (600, 900), "wdth": (60, 130)},
    "public-sans-latin-wght-normal.woff2": {"wght": (300, 900)},
}

# El latín-1 siempre queda entero (el español lo usa casi todo); los demás
# glifos se conservan solo si algún archivo propio de web/ los muestra.
BASE_LATIN1 = range(0x0020, 0x0100)

# Puntuación fuera del latín-1 que traían las fuentes originales: la receta se
# compromete a cubrirla si la interfaz la usa. Lo demás (→, ≤, ↗…) ya caía a la
# fuente del sistema antes de la dieta, así que no es una regresión.
EXTRAS = {0x2013, 0x2014, 0x2026, 0x2039, 0x203A, 0x2212}

# Cobertura que --check exige: imprimibles de latín-1 (los códigos de control no
# llevan glifo) más la puntuación de EXTRAS.
EXIGIBLES = set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | EXTRAS


def caracteres_usados(raiz: Path) -> set[int]:
    """Puntos de código que aparecen en los textos propios de web/ (JS, HTML, CSS)."""
    usados: set[int] = set(BASE_LATIN1)
    for ruta in (raiz / "web").rglob("*"):
        if ruta.suffix in {".js", ".html", ".css"} and "vendor" not in ruta.parts:
            usados.update(ord(ch) for ch in ruta.read_text(encoding="utf-8"))
    return usados


def generar(origen: Path, ejes: dict[str, tuple[float, float]], unicodes: set[int]) -> bytes:
    """Fuente instanciada y recortada, lista para guardar como .woff2."""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    fuente = instancer.instantiateVariableFont(TTFont(origen), ejes)
    recortador = subset.Subsetter(subset.Options(flavor="woff2"))
    recortador.populate(unicodes=unicodes)
    recortador.subset(fuente)
    salida = io.BytesIO()
    fuente.flavor = "woff2"
    fuente.save(salida)
    return salida.getvalue()


def verificar(ruta: Path, ejes: dict[str, tuple[float, float]], unicodes: set[int]) -> list[str]:
    """Fallas del .woff2 commiteado frente a la receta: ejes fuera de rango o
    glifos que la interfaz muestra y la fuente no trae."""
    from fontTools.ttLib import TTFont

    fuente = TTFont(ruta)
    errores = []
    fvar = {a.axisTag: (a.minValue, a.maxValue) for a in fuente["fvar"].axes} if "fvar" in fuente else {}
    for tag, (minimo, maximo) in ejes.items():
        if fvar.get(tag) != (minimo, maximo):
            errores.append(f"{ruta.name}: eje {tag} es {fvar.get(tag)}, la receta pide {(minimo, maximo)}")
    for tag in set(fvar) - set(ejes):
        errores.append(f"{ruta.name}: eje {tag} no está en la receta")
    cmap = set(fuente.getBestCmap())
    faltan = sorted(c for c in unicodes if c not in cmap and c in EXIGIBLES)
    if faltan:
        errores.append(
            f"{ruta.name}: sin glifo para {len(faltan)} caracteres usados en web/ ({' '.join(f'U+{c:04X}' for c in faltan[:8])}…)"
        )
    return errores


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="verifica que los .woff2 respetan la receta, sin escribir")
    args = p.parse_args(argv)

    try:
        import fontTools  # noqa: F401
    except ImportError:
        print("Falta fontTools[woff]: instala requirements-dev.txt", file=sys.stderr)
        return 2

    unicodes = caracteres_usados(ROOT)
    errores = []
    for nombre, ejes in FUENTES.items():
        ruta = FUENTES_DIR / nombre
        if not ruta.is_file():
            print(f"No existe {ruta}", file=sys.stderr)
            return 2
        if args.check:
            errores.extend(verificar(ruta, ejes, unicodes))
            continue
        antes = ruta.stat().st_size
        ruta.write_bytes(generar(ruta, ejes, unicodes))
        print(f"{nombre}: {antes / 1024:.1f} KB → {ruta.stat().st_size / 1024:.1f} KB")
    if errores:
        print("\n".join(errores))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
