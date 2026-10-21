"""Rutas por fragmento («#/vista») de la aplicación de una sola página (ENLACES-04).

El router de `web/js/app.js` toma el primer segmento tras `#/` —descartando la
query— y lo busca entre las vistas registradas. Un `#/ruta` que no existe queda
muerto sin que nadie lo note (a diferencia de un `href="/falta.html"`, que ya
vigila `tests/test_enlaces_internos.py`). Esta guarda extrae cada `#/ruta` de
`web/**/*.html` y `web/js/**/*.js` y la compara con los `id:` declarados en
`web/js/views/*.js`, que son los que `app.js` registra en `VIEWS`.

`VISTAS_ESPERADAS` fija la lista de rutas válidas: agregar, renombrar o retirar
una vista obliga a declararlo aquí, para que el cambio sea evidente.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.settings import ROOT

WEB = ROOT / "web"
VIEWS = WEB / "js" / "views"

# Vistas registradas hoy (los `id:` de web/js/views/*.js). La raíz «#/» nunca
# produce hallazgo: el router la resuelve a «mi-zona». «#/v/<token>» es la
# ficha que comparte un vecino y cuenta como la vista «v».
VISTAS_ESPERADAS = {
    "alertas",
    "calidad",
    "casos",
    "incendio",
    "mapa",
    "mi-zona",
    "preparate",
    "privacidad",
    "quehago",
    "riesgo",
    "temporada",
    "v",
}

# «#/ruta»: el primer segmento tras el fragmento. La query («#/mapa?capas=…»)
# queda fuera porque `?` no está en la clase; la raíz «#/» tampoco captura.
_FRAGMENTO = re.compile(r"#/([A-Za-z0-9_-]+)")
_ID_VISTA = re.compile(r"""^\s*id:\s*["']([\w-]+)["']""", re.MULTILINE)


def _fuentes(web: Path) -> list[Path]:
    return sorted(web.rglob("*.html")) + sorted((web / "js").rglob("*.js"))


def _vistas_registradas(views: Path) -> set[str]:
    return {vista for archivo in views.glob("*.js") for vista in _ID_VISTA.findall(archivo.read_text(encoding="utf-8"))}


def _fragmentos_de(archivo: Path) -> list[tuple[int, str]]:
    """(línea, ruta) de cada «#/ruta» del archivo."""
    return [
        (numero, ruta)
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1)
        for ruta in _FRAGMENTO.findall(linea)
    ]


def _hallazgos(archivos: list[Path], validas: set[str]) -> list[str]:
    return [
        f"{archivo}:{numero}: #/{ruta} (no es una vista registrada)"
        for archivo in archivos
        for numero, ruta in _fragmentos_de(archivo)
        if ruta not in validas
    ]


def test_las_vistas_registradas_son_las_esperadas():
    registradas = _vistas_registradas(VIEWS)
    assert registradas == VISTAS_ESPERADAS, (
        f"las vistas cambiaron: faltan {sorted(VISTAS_ESPERADAS - registradas)}, "
        f"sobran {sorted(registradas - VISTAS_ESPERADAS)}; actualiza VISTAS_ESPERADAS"
    )


def test_el_repositorio_no_tiene_enlaces_muertos():
    fallas = _hallazgos(_fuentes(WEB), _vistas_registradas(VIEWS))
    assert not fallas, "Rutas por fragmento sin vista:\n" + "\n".join(fallas)


def test_una_vista_retirada_en_tmp_path_se_acusa_con_linea(tmp_path):
    """«#/calida» fue una vista retirada: un enlace a ella debe romper el check."""
    pagina = tmp_path / "ayuda.html"
    pagina.write_text(
        '<p><a href="#/mapa">Mapa</a></p>\n<p><a href="#/calida">Calidad del aire</a></p>\n',
        encoding="utf-8",
    )
    fallas = _hallazgos([pagina], _vistas_registradas(VIEWS))
    assert fallas == [f"{pagina}:2: #/calida (no es una vista registrada)"]


def test_tambien_se_acusa_en_un_js_de_tmp_path(tmp_path):
    vista = tmp_path / "vista.js"
    vista.write_text("const ir = () => { location.hash = '#/fantasma'; };\n", encoding="utf-8")
    fallas = _hallazgos([vista], _vistas_registradas(VIEWS))
    assert fallas == [f"{vista}:1: #/fantasma (no es una vista registrada)"]


def test_la_raiz_la_query_y_el_token_no_producen_hallazgos(tmp_path):
    pagina = tmp_path / "ok.html"
    pagina.write_text(
        '<a href="#/">Portada</a>\n'
        '<a href="#/mapa?capas=focos,riesgo">Mapa con capas</a>\n'
        '<a href="#/v/token-de-familia">Lugar compartido</a>\n',
        encoding="utf-8",
    )
    assert _hallazgos([pagina], _vistas_registradas(VIEWS)) == []
