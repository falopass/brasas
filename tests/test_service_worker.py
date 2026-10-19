"""FIX-35: el service worker debe cachear la cáscara completa, incluido el modo
liviano (/web/lite.html) y la hoja A4 (/web/lista.html), que son las vistas
pensadas para usarse con señal mala o sin conexión.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

RUTAS_LIGERAS = [
    "/web/lite.html",
    "/web/js/lite.js",
    "/web/lista.html",
    "/web/css/lista.css",
]


def _shell() -> set[str]:
    """Extrae el arreglo SHELL de web/sw.js."""
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    match = re.search(r"const\s+SHELL\s*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, "no se encontró el arreglo SHELL en web/sw.js"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _recursos_locales(html: str) -> set[str]:
    """Rutas locales (src/href absolutas al propio sitio) referenciadas en el HTML."""
    return {
        valor
        for valor in re.findall(r'''(?:src|href)=["']([^"']+)["']''', html)
        if valor.startswith("/")
    }


def test_shell_incluye_modo_liviano_y_lista():
    shell = _shell()
    faltantes = [ruta for ruta in RUTAS_LIGERAS if ruta not in shell]
    assert not faltantes, f"faltan en SHELL de web/sw.js: {faltantes}"


def test_recursos_de_lite_y_lista_cacheables():
    shell = _shell()
    for pagina in ("lite.html", "lista.html"):
        html = (WEB / pagina).read_text(encoding="utf-8")
        for recurso in _recursos_locales(html):
            if recurso.startswith("/api/"):
                continue  # rutas de API: las cubre la caché dinámica CACHEABLE_API
            assert recurso in shell, (
                f"{pagina} referencia {recurso}, que no está en SHELL de web/sw.js "
                "(quedaría sin respuesta offline)"
            )
