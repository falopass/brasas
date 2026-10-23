"""UX-59 / CONT-05: lista de preparación para quien vive en una parcela o en el campo.

La prueba lee web/js/views/preparate.js como texto (sin ejecutar JavaScript) y
fija el contrato del arreglo RURAL_CHECKLIST: las ocho claves del encargo, una
fuente oficial por ítem (claves ya declaradas en el diccionario SRC de la
vista), el enganche con checklist() y bindChecklist() bajo la clave «parcela»,
el título de la sección y que ningún ítem use la palabra «predicción» ni
prometa que no habrá incendio.
"""

import re
from pathlib import Path

VISTA = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "preparate.js"
SRC_TXT = VISTA.read_text(encoding="utf-8")

CLAVES_ESPERADAS = ["lena", "maquinaria", "quema", "rastrojo", "acceso", "agua", "corral", "vecinos"]
TITULO = "Si vives en una parcela o en el campo"

# Un ítem es una línea «['clave', 'texto', ['fuente', ...]],»; la fuente es el
# último arreglo de la línea y solo puede traer claves del diccionario SRC.
_ITEM = re.compile(r"^\s*\[\s*'(\w+)'\s*,")
_FUENTES_FIN = re.compile(r"\[((?:\s*'[^']*'\s*,?)*)]\s*]?,?\s*$")
_PROHIBIDO = re.compile(r"predicci[oó]n|no habr[aá]\s+(?:un\s+)?incendio|nunca habr[aá]\s+(?:un\s+)?incendio", re.I)


def bloque_rural(src):
    """Líneas con contenido del arreglo RURAL_CHECKLIST."""
    m = re.search(r"const RURAL_CHECKLIST = \[(.*?)];\n", src, re.S)
    assert m, "no se encontró «const RURAL_CHECKLIST = [» en la vista"
    return [linea for linea in m.group(1).splitlines() if linea.strip()]


def claves_del_diccionario(src):
    """Claves definidas en el diccionario SRC de la vista."""
    m = re.search(r"const SRC = \{(.*?)};", src, re.S)
    assert m, "no se encontró el diccionario SRC en la vista"
    return set(re.findall(r"^\s*(\w+):\s*\[", m.group(1), re.M))


def fuentes_de_item(linea):
    m = _FUENTES_FIN.search(linea)
    assert m, f"ítem sin arreglo de fuentes al final: {linea.strip()[:70]}"
    return re.findall(r"'(\w+)'", m.group(1))


def test_rural_checklist_tiene_las_ocho_claves():
    claves = [_ITEM.match(l).group(1) for l in bloque_rural(SRC_TXT) if _ITEM.match(l)]
    assert claves == CLAVES_ESPERADAS, f"claves de RURAL_CHECKLIST: {claves}"


def test_cada_item_trae_fuente_del_diccionario_src():
    validas = claves_del_diccionario(SRC_TXT)
    for linea in bloque_rural(SRC_TXT):
        citadas = fuentes_de_item(linea)
        assert citadas, f"ítem sin fuente: {linea.strip()[:70]}"
        ajenas = [c for c in citadas if c not in validas]
        assert not ajenas, f"fuentes ajenas al diccionario SRC: {ajenas}"


def test_la_vista_pinta_y_engancha_la_lista_parcela():
    assert re.search(r"checklist\('parcela', RURAL_CHECKLIST", SRC_TXT), "falta checklist('parcela', RURAL_CHECKLIST)"
    assert re.search(r"bindChecklist\(container, 'parcela'", SRC_TXT), "falta bindChecklist(container, 'parcela', ...)"


def test_el_titulo_de_la_seccion_esta_en_el_html():
    assert TITULO in SRC_TXT, f"falta el título «{TITULO}»"


def test_ningun_item_promete_ni_predice():
    for linea in bloque_rural(SRC_TXT):
        assert not _PROHIBIDO.search(linea), f"ítem con promesa o predicción: {linea.strip()[:70]}"
