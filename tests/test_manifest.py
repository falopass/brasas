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
    return {k1 or k2 for k1, k2 in re.findall(r"(?:'([^']+)'|([A-Za-z0-9_-]+))\s*:", etiquetas.group(1))}


def _resuelve_archivo(url):
    """Ruta servida -> archivo del repo: /web/x -> web/x; /x -> web/x (el backend sirve web/ en raíz)."""
    rel = url.lstrip("/").split("?")[0].split("#")[0]
    for candidato in (ROOT / rel, ROOT / "web" / rel):
        if candidato.is_file():
            return candidato
    return None


def test_campos_minimos_y_display_valido(manifiesto):
    for campo in ("name", "short_name", "start_url", "scope", "id", "lang"):
        assert manifiesto.get(campo), f"el manifiesto no tiene «{campo}» o está vacío"
    assert manifiesto.get("icons"), "el manifiesto no declara íconos"
    display = manifiesto.get("display")
    assert display in DISPLAY_VALIDOS, f"display «{display}» no es uno de {sorted(DISPLAY_VALIDOS)}"


def test_iconos_existen_en_disco(manifiesto):
    for icono in manifiesto.get("icons", []):
        src = icono.get("src", "")
        if not src.startswith("/"):
            continue
        assert _resuelve_archivo(src), f"el ícono «{src}» no existe en el repositorio"


def test_iconos_any_y_maskable_separados(manifiesto):
    """ICON-E-01: el maskable es un archivo aparte (zona segura), no un `any`
    reciclado: los lanzadores que recortan necesitan el motivo centrado."""
    iconos = manifiesto.get("icons", [])
    maskables = [i for i in iconos if i.get("purpose") == "maskable"]
    otros = [i for i in iconos if i.get("purpose") != "maskable"]
    assert len(maskables) == 1, "debe haber exactamente un ícono maskable"
    for icono in otros:
        assert icono.get("purpose") == "any", f"«{icono.get('src')}» debe declarar purpose «any» explícito"
    for icono in maskables:
        assert "maskable" in icono.get("src", ""), f"el maskable «{icono.get('src')}» no es un archivo propio"
        assert icono["src"] not in {i["src"] for i in otros}, "el maskable no puede compartir archivo con un ícono «any»"


def test_atajos_apuntan_a_algo_real(manifiesto):
    vistas = _vistas_app()
    atajos = manifiesto.get("shortcuts", [])
    # Los lanzadores muestran a lo más cinco atajos; el sexto se corta sin avisar.
    assert len(atajos) <= 5, f"hay {len(atajos)} atajos y los lanzadores muestran hasta 5"
    urls = [a.get("url", "") for a in atajos]
    assert len(urls) == len(set(urls)), "hay atajos con la URL repetida"
    for atajo in atajos:
        url = atajo.get("url", "")
        nombre = atajo.get("name", url)
        # FIX-213: «Pantalla pública» es un tablero de TV sin vuelta a la app,
        # un callejón sin salida en un teléfono; no puede volver a ser atajo.
        assert nombre != "Pantalla pública", "el atajo «Pantalla pública» es un tablero sin vuelta a la app"
        if "#/" in url:
            vista = url.split("#/", 1)[1].split("/")[0].split("?")[0]
            assert vista in vistas, f"el atajo «{nombre}» apunta a la vista «{vista}», que no existe en web/js/app.js"
        else:
            archivo = _resuelve_archivo(url)
            assert archivo, f"el atajo «{nombre}» apunta a «{url}», archivo que no existe"
            # Lista blanca de páginas sueltas admitidas como atajo. «web/pantalla.html»
            # queda fuera a propósito: es un tablero de TV sin barra ni enlace de vuelta,
            # un callejón sin salida en un teléfono (FIX-213).
            permitidas = {ROOT / "web" / "lista.html"}
            assert archivo in permitidas, (
                f"el atajo «{nombre}» lleva a «{url}», una página suelta sin navegación; "
                f"los atajos deben abrir vistas de la app o una página de {sorted(p.name for p in permitidas)}"
            )


def test_atajo_cerca_abre_mi_zona_con_parametro(manifiesto):
    """MOV-03: «¿Hay fuego cerca de mí?» abre la pantalla de cercanía de un toque.
    El parámetro lo lee app.js (MOV-01); mientras no llegue se ignora sin romper nada."""
    atajo = next(a for a in manifiesto["shortcuts"] if a["name"] == "¿Hay fuego cerca de mí?")
    assert atajo["url"] == "/#/mi-zona?cerca=1"


def test_start_url_y_atajos_dentro_del_scope(manifiesto):
    scope = manifiesto.get("scope", "/")
    urls = [("start_url", manifiesto.get("start_url", ""))]
    urls += [(a.get("name", "?"), a.get("url", "")) for a in manifiesto.get("shortcuts", [])]
    for nombre, url in urls:
        path = url.split("#")[0] or "/"
        assert path.startswith(scope), f"«{nombre}» («{url}») queda fuera del scope «{scope}»"
