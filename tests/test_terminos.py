"""TERMINOS-01: los términos prometen cosas que el código tiene que cumplir.

Guarda entre docs/TERMINOS.md y el producto, en una sola dirección a propósito:
lo que la app muestra (teléfonos de web/index.html) debe estar en los términos,
y las promesas de los términos (ruta de privacidad, borrado de datos) deben tener
su contraparte viva en el código. Si los términos publican un número que la app
no muestra (hoy el 134 PDI), el test no falla: se anota y punto.

Todo se lee como texto, sin red. La ruta de borrado se extrae de
backend/routes/personal.py con una expresión explícita: si un refactor la mueve
o la renombra, el test cae y obliga a tocar los términos.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TERMINOS = RAIZ / "docs" / "TERMINOS.md"
INDEX = RAIZ / "web" / "index.html"
APP = RAIZ / "web" / "js" / "app.js"
ZONA = RAIZ / "web" / "js" / "views" / "zona.js"
PERSONAL = RAIZ / "backend" / "routes" / "personal.py"

TEXTO = TERMINOS.read_text(encoding="utf-8")

# Los meses en español de la línea «Última actualización: <día> de <mes> de <año>».
MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def telefonos_de_la_app() -> set[str]:
    """Números del bloque de emergencia de web/index.html (el <noscript> sin JS)."""
    html = INDEX.read_text(encoding="utf-8")
    bloque = re.search(r'<div class="phones">(.*?)</div>', html, re.S)
    assert bloque, "web/index.html ya no tiene el bloque «phones» de teléfonos de emergencia"
    telefonos = set(re.findall(r'href="tel:([^"]+)"', bloque.group(1)))
    assert telefonos, "el bloque «phones» de web/index.html quedó sin teléfonos"
    return telefonos


def vistas_de_la_app() -> set[str]:
    """Ids de la lista VIEWS de web/js/app.js; el de la portada vive en zona.js (zona.id)."""
    app = APP.read_text(encoding="utf-8")
    views = re.search(r"const VIEWS = \[(.*?)\];", app, re.S)
    assert views, "web/js/app.js ya no declara la lista VIEWS"
    ids = set(re.findall(r"id:\s*'([^']+)'", views.group(1)))
    zona = re.search(r"export default \{\s*id:\s*'([^']+)'", ZONA.read_text(encoding="utf-8"))
    assert zona, "web/js/views/zona.js ya no exporta su id de vista"
    ids.add(zona.group(1))
    return ids


def test_telefonos_que_la_app_publica_aparecen_en_los_terminos():
    """Cada número del bloque de emergencia de la app debe estar en los términos."""
    publicados = set(re.findall(r"\d+", TEXTO))
    for tel in sorted(telefonos_de_la_app()):
        assert tel in publicados, (
            f"la app muestra el teléfono de emergencia {tel} (web/index.html) "
            "y docs/TERMINOS.md no lo nombra: actualiza la lista de emergencias de los términos"
        )


def test_toda_ruta_citada_en_los_terminos_existe_como_vista():
    """Un «#/vista» de los términos sin su vista en la app manda al vecino a un callejón sin salida."""
    ids = vistas_de_la_app()
    for ruta in sorted(set(re.findall(r"#/([a-z0-9-]+)", TEXTO))):
        assert ruta in ids, (
            f"los términos mandan a «#/{ruta}» pero ninguna vista de web/js/app.js la tiene: corrige la ruta en docs/TERMINOS.md"
        )


def test_si_los_terminos_prometen_borrar_datos_nombran_la_ruta_real():
    """«Borrar tus datos» promete un DELETE /me; el texto debe nombrar la ruta que existe en el código."""
    if not re.search(r"borrar tus datos", TEXTO, re.I):
        return
    codigo = PERSONAL.read_text(encoding="utf-8")
    prefix = re.search(r'APIRouter\(\s*prefix="([^"]+)"', codigo)
    assert prefix, "backend/routes/personal.py ya no declara el prefix del router"
    delete_me = re.search(r'@router\.delete\(\s*"(/me)"', codigo)
    assert delete_me, (
        "los términos prometen borrar los datos pero backend/routes/personal.py "
        'ya no tiene su @router.delete("/me"): la promesa quedó sin ruta que la cumpla'
    )
    ruta = f"{prefix.group(1)}{delete_me.group(1)}"
    assert ruta in TEXTO, (
        f"los términos prometen «borrar tus datos» pero no nombran la ruta que lo hace ({ruta}): "
        "agrégala en docs/TERMINOS.md junto a la promesa"
    )


def test_terminos_declaran_desde_cuando_rigen():
    """Sin fecha de revisión, nadie sabe si el texto que aceptó sigue vigente."""
    m = re.search(r"Última actualización:\s*(\d{1,2}) de (\w+) de (\d{4})", TEXTO)
    assert m, "docs/TERMINOS.md necesita la línea «Última actualización: <día> de <mes> de <año>»"
    dia, mes, anio = m.groups()
    assert mes.lower() in MESES, f"«{mes}» no es un mes en español: revisa la línea «Última actualización»"
    try:
        date(int(anio), MESES[mes.lower()], int(dia))
    except ValueError as e:
        raise AssertionError(f"la fecha de «Última actualización» no existe: {dia} de {mes} de {anio}") from e
