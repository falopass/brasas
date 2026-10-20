"""Guarda del manifiesto de la PWA (QA-45): que instalar BRASA no se rompa en silencio.

Lee web/manifest.webmanifest directo del disco (sin servidor) y comprueba que tenga
los campos mínimos de instalabilidad, que cada ícono declarado exista en el repo y
que cada atajo apunte a una vista real (/#/<vista>) o a un archivo servido.
"""
import json
import re

import pytest

from backend.settings import ROOT

MANIFEST = ROOT / "web" / "manifest.webmanifest"
APP_JS = ROOT / "web" / "js" / "app.js"
DISPLAY_VALIDOS = {"standalone", "fullscreen", "minimal-ui", "browser"}


@pytest.fixture(scope="module")
def manifiesto():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _vistas_app():
    """Ids de vista declarados en web/js/app.js (claves de LABELS)."""
    fuente = APP_JS.read_text(encoding="utf-8")
    etiquetas = re.search(r"LABELS\s*=\s*\{([^}]*)\}", fuente)
    assert etiquetas, "no se encontró el mapa LABELS en web/js/app.js"
    return {
        k1 or k2
        for k1, k2 in re.findall(r"(?:'([^']+)'|([A-Za-z0-9_-]+))\s*:", etiquetas.group(1))
    }


def _resuelve_archivo(url):
    """Ruta servida -> archivo del repo: /web/x -> web/x; /x -> web/x (el backend sirve web/ en raíz)."""
    rel = url.lstrip("/").split("?")[0].split("#")[0]
    for candidato in (ROOT / rel, ROOT / "web" / rel):
        if candidato.is_file():
            return candidato
    return None


def test_campos_minimos(manifiesto):
    for campo in ("name", "short_name", "start_url", "scope", "display", "id", "lang"):
        assert manifiesto.get(campo), f"el manifiesto no tiene «{campo}» o está vacío"
    assert manifiesto.get("icons"), "el manifiesto no declara íconos"


def test_display_valido(manifiesto):
    display = manifiesto.get("display")
    assert display in DISPLAY_VALIDOS, f"display «{display}» no es uno de {sorted(DISPLAY_VALIDOS)}"


def test_iconos_existen_en_disco(manifiesto):
    for icono in manifiesto.get("icons", []):
        src = icono.get("src", "")
        if not src.startswith("/"):
            continue
        assert _resuelve_archivo(src), f"el ícono «{src}» no existe en el repositorio"


def test_atajos_apuntan_a_algo_real(manifiesto):
    vistas = _vistas_app()
    for atajo in manifiesto.get("shortcuts", []):
        url = atajo.get("url", "")
        nombre = atajo.get("name", url)
        if "#/" in url:
            vista = url.split("#/", 1)[1].split("/")[0]
            assert vista in vistas, f"el atajo «{nombre}» apunta a la vista «{vista}», que no existe en web/js/app.js"
        else:
            assert _resuelve_archivo(url), f"el atajo «{nombre}» apunta a «{url}», archivo que no existe"


def test_start_url_y_atajos_dentro_del_scope(manifiesto):
    scope = manifiesto.get("scope", "/")
    urls = [("start_url", manifiesto.get("start_url", ""))]
    urls += [(a.get("name", "?"), a.get("url", "")) for a in manifiesto.get("shortcuts", [])]
    for nombre, url in urls:
        path = url.split("#")[0] or "/"
        assert path.startswith(scope), f"«{nombre}» («{url}») queda fuera del scope «{scope}»"
