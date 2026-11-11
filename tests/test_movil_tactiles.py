"""MOV-02: guardas de los objetivos táctiles de 44 px en teléfono.

Relee ``web/css/app.css`` y exige que ``.btn``, ``.btn-sm`` y ``.row-btn``
declaren ``min-height`` de al menos 44 px dentro de ``@media (max-width:
899px)`` — o globalmente, si la regla se vuelve base. La medición de
producción (10-nov-2026) los encontró en 40/34/18–37 px; si alguien baja
el objetivo, esta prueba lo rompe antes del merge.
"""
from __future__ import annotations

import re

from backend.settings import ROOT


def _css_sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _trozos_media_899(css: str) -> tuple[str, str]:
    """Separa el interior de `@media (max-width: 899px)` del resto.

    Las llaves se cuentan balanceadas: un `}` interior no cierra el bloque.
    """
    limpio = _css_sin_comentarios(css)
    marca = "@media (max-width: 899px)"
    dentro: list[str] = []
    fuera: list[str] = []
    i = 0
    n = len(limpio)
    while i < n:
        j = limpio.find(marca, i)
        if j < 0:
            fuera.append(limpio[i:])
            break
        fuera.append(limpio[i:j])
        k = limpio.find("{", j)
        assert k != -1, "app.css: @media (max-width: 899px) sin llave de apertura"
        depth = 0
        p = k
        while p < n:
            if limpio[p] == "{":
                depth += 1
            elif limpio[p] == "}":
                depth -= 1
                if depth == 0:
                    dentro.append(limpio[k + 1:p])
                    i = p + 1
                    break
            p += 1
        else:
            raise AssertionError("app.css: bloque @media (max-width: 899px) sin cerrar")
    return "".join(dentro), "".join(fuera)


def _reglas(bloque: str) -> list[tuple[str, str]]:
    """Pares (selector, cuerpo) de cada regla del trozo de CSS."""
    return [(m.group(1), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", bloque)]


def _selector_apunta_a(selector: str, clase: str, solo_exacto: bool) -> bool:
    """True si alguna parte del selector (separada por comas) termina en `.clase`.

    Con `solo_exacto` la parte entera debe ser `.clase` (admite pseudos), así
    `.pick-hint .btn` no cuenta como regla global de `.btn`.
    """
    limite = rf"\.{re.escape(clase)}(?![\w-])(?:\s*[:.\[][^:]*)?$"
    for parte in selector.split(","):
        parte = parte.strip()
        if solo_exacto:
            if re.fullmatch(limite, parte):
                return True
        elif re.search(limite, parte):
            return True
    return False


def _min_height_px(bloque: str, clase: str, solo_exacto: bool) -> list[float]:
    """`min-height` en px de las reglas que apuntan a `.clase` (raíz: 15 px por rem)."""
    altos: list[float] = []
    for selector, cuerpo in _reglas(bloque):
        if not _selector_apunta_a(selector, clase, solo_exacto):
            continue
        for valor, unidad in re.findall(r"min-height\s*:\s*([0-9.]+)\s*(px|rem)\b", cuerpo):
            altos.append(float(valor) * (15.0 if unidad == "rem" else 1.0))
    return altos


def test_objetivos_tactiles_minimos_movil():
    """`.btn`, `.btn-sm` y `.row-btn` ofrecen ≥44 px al dedo en el teléfono.

    Vale la última declaración aplicable (a igual especificidad la última
    gana): una regla posterior que baje el alto rompe la prueba aunque una
    anterior diga 44 px."""
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    dentro, fuera = _trozos_media_899(css)
    for clase in ("btn", "btn-sm", "row-btn"):
        movil = _min_height_px(dentro, clase, solo_exacto=False)
        global_ = _min_height_px(fuera, clase, solo_exacto=True)
        if movil:
            assert movil[-1] >= 44, f"app.css: `.{clase}` baja de 44 px en @media (max-width: 899px)"
        else:
            assert global_ and global_[-1] >= 44, (
                f"app.css: `.{clase}` no tiene min-height ≥44 px en móvil ni globalmente"
            )
