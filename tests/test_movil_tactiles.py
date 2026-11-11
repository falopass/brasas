"""MOV-02 y MOV-04: guardas de los objetivos táctiles de 44 px en teléfono.

Relee ``web/css/app.css`` y exige que ``.btn``, ``.btn-sm`` y ``.row-btn``
declaren ``min-height`` de al menos 44 px dentro de ``@media (max-width:
899px)`` — o globalmente, si la regla se vuelve base. La medición de
producción (10-nov-2026) los encontró en 40/34/18–37 px; si alguien baja
el objetivo, esta prueba lo rompe antes del merge.

MOV-04 suma el área *tocable* (hit-testing, no la caja dibujada): el asa de
la hoja medía 33–37 px porque ``.panel`` recorta con ``overflow:hidden`` lo
que su ``::before`` salía por arriba, los ``tel:`` 130/132 eran enlaces en
línea de 15–20 px y los de ``lista.html`` se pisaban entre vecinos por los
márgenes negativos. Las guardas de abajo piden 44 px reales y prohíben
volver a los enlaces en línea.
"""
from __future__ import annotations

import re

from backend.settings import ROOT


def _css_sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _trozos_media(css: str, marca: str) -> tuple[str, str]:
    """Separa el interior de cada bloque `@media <marca>` del resto.

    Las llaves se cuentan balanceadas: un `}` interior no cierra el bloque.
    """
    limpio = _css_sin_comentarios(css)
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
        assert k != -1, f"@media {marca} sin llave de apertura"
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
            raise AssertionError(f"bloque @media {marca} sin cerrar")
    return "".join(dentro), "".join(fuera)


def _trozos_media_899(css: str) -> tuple[str, str]:
    """El interior de `@media (max-width: 899px)` de app.css contra el resto."""
    return _trozos_media(css, "@media (max-width: 899px)")


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


def _height_px(bloque: str, clase: str) -> list[float]:
    """`height`/`min-height` en px de las reglas `.clase` exactas (raíz: 15 px por rem)."""
    altos: list[float] = []
    for selector, cuerpo in _reglas(bloque):
        if not _selector_apunta_a(selector, clase, solo_exacto=True):
            continue
        for valor, unidad in re.findall(r"(?:min-)?height\s*:\s*([0-9.]+)\s*(px|rem)\b", cuerpo):
            altos.append(float(valor) * (15.0 if unidad == "rem" else 1.0))
    return altos


def test_asa_hoja_tocable_44px():
    """MOV-04: el propio tirador mide ≥44 px de alto en el teléfono.

    El `::before` de MOV-02 no podía contar: `.panel` tiene `overflow:hidden` y
    recortaba los 7 px que salían por arriba (quedaban 33–37 px tocables)."""
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    dentro, _ = _trozos_media_899(css)
    altos = _height_px(dentro, "sheet-handle")
    assert altos and altos[-1] >= 44, (
        "app.css: `.sheet-handle` debe medir ≥44 px de alto en móvil; "
        "un ::before no sirve porque .panel lo recorta con overflow:hidden"
    )


def test_telefonos_emergencia_son_botones_no_enlaces():
    """MOV-04: los `tel:` 130/132 son botones `.phone`, no enlaces en línea.

    En `#/alertas` (alertas.js) y en `lite.html` todo ancla `tel:` lleva la
    clase `.phone`; en `focos.html` y `lista.html` vive dentro de un
    `<ul class="phones">`; en `lite.js` se construye solo dentro del par de
    botones (`llamadas()`), nunca interpolado en una frase."""
    alertas = (ROOT / "web" / "js" / "views" / "alertas.js").read_text(encoding="utf-8")
    for tag in re.findall(r"<a\b[^>]*>", alertas):
        if 'href="tel:' in tag:
            assert 'class="phone' in tag, f"alertas.js: tel: en línea fuera de .phone: {tag}"
    for ruta in ("web/focos.html", "web/lista.html"):
        txt = (ROOT / ruta).read_text(encoding="utf-8")
        resto = re.sub(r'<ul class="phones">.*?</ul>', "", txt, flags=re.S)
        assert 'href="tel:' not in resto, f"{ruta}: tel: fuera de <ul class=\"phones\">"
    lite = (ROOT / "web" / "lite.html").read_text(encoding="utf-8")
    for tag in re.findall(r"<a\b[^>]*>", lite):
        if 'href="tel:' in tag:
            assert 'class="phone' in tag, f"lite.html: tel: en línea fuera de .phone: {tag}"
    lite_js = (ROOT / "web" / "js" / "lite.js").read_text(encoding="utf-8")
    assert re.search(r"el\('a',\s*'phone", lite_js), "lite.js: los tel: deben construirse como botones .phone"
    sin_constructores = re.sub(r"const (?:tel|llamadas)\s*=.*?return [ad];\s*};", "", lite_js, flags=re.S)
    assert not re.search(r"\btel\(", sin_constructores), "lite.js: queda un tel() en línea dentro de un texto"


def test_lista_telefonos_sin_margenes_negativos():
    """MOV-04: `.phones li a` gana su área con padding y `min-height`, sin los
    márgenes negativos que se pisaban entre vecinos (35 px reales medidos)."""
    css = (ROOT / "web" / "css" / "lista.css").read_text(encoding="utf-8")
    dentro, _ = _trozos_media(css, "@media screen {")
    reglas = [cuerpo for selector, cuerpo in _reglas(dentro) if ".phones li a" in selector]
    assert reglas, "lista.css: falta la regla `.phones li a` en @media screen"
    for cuerpo in reglas:
        assert not re.search(r"margin[^:]*:\s*-", cuerpo), "lista.css: `.phones li a` volvió al margen negativo"
        altos = [float(v) * (15.0 if u == "rem" else 1.0)
                 for v, u in re.findall(r"min-height\s*:\s*([0-9.]+)\s*(px|rem)\b", cuerpo)]
        assert altos and altos[-1] >= 44, "lista.css: `.phones li a` necesita min-height ≥44 px"


PANTALLA_CSS = ROOT / "web" / "css" / "pantalla.css"
COLEGIOS_CSS = ROOT / "web" / "css" / "colegios.css"


def _font_size_px(cuerpo: str) -> float | None:
    """`font-size` de una regla CSS llevado a px (rem = 16 px, pt = 4/3 px)."""
    m = re.search(r"font-size\s*:\s*([0-9.]+)\s*(px|rem|pt)\b", cuerpo)
    if not m:
        return None
    return float(m.group(1)) * {"px": 1.0, "rem": 16.0, "pt": 4.0 / 3.0}[m.group(2)]


def test_pantalla_enlace_senapred_24px():
    """MOV-06: «SENAPRED (senapred.cl)» va dentro de una frase del pie fijo de
    la pantalla pública: enlace en línea, mínimo 24 px de alto tocable
    (medía 18 px)."""
    css = PANTALLA_CSS.read_text(encoding="utf-8")
    regla = re.search(r"\.official-bar a\s*\{([^}]*)\}", css)
    assert regla, "pantalla.css: falta la regla .official-bar a"
    altos = [float(v) for v in re.findall(r"min-height\s*:\s*([0-9.]+)px", regla.group(1))]
    assert altos and altos[-1] >= 24, "pantalla.css: .official-bar a bajo 24 px de alto"


def test_colegios_tiny_minimo_12px_en_pantalla():
    """MOV-06: el .tiny de colegios.html medía 11,33 px en pantalla (8.5 pt);
    en @media screen no baja de 12 px y la hoja impresa no cambia."""
    css = COLEGIOS_CSS.read_text(encoding="utf-8")
    dentro, fuera = _trozos_media(css, "@media screen {")
    regla = re.search(r"\.tiny\s*\{([^}]*)\}", dentro)
    assert regla, "colegios.css: .tiny sin regla propia dentro de @media screen"
    px = _font_size_px(regla.group(1))
    assert px is not None and px >= 12, f"colegios.css: .tiny en pantalla mide {px} px"
    base = re.search(r"\.tiny\s*\{([^}]*)\}", fuera)
    assert base and re.search(r"font-size\s*:\s*8\.5pt", base.group(1)), (
        "colegios.css: el .tiny impreso debe seguir en 8.5 pt"
    )
