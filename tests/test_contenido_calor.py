"""AGUA-06: el contenido de salud de web/js/calor.js cumple la regla de
«cero invención»: cada consejo lleva texto, fuente y un enlace https a un
dominio oficial; el módulo declara la fecha de consulta de sus fuentes y
recuerda que BRASA no es una fuente oficial."""
import re
from pathlib import Path
from urllib.parse import urlsplit

CALOR = Path(__file__).resolve().parents[1] / "web" / "js" / "calor.js"
DOMINIOS_OFICIALES = ("who.int", "minsal.cl", "senapred.cl", "samu.cl")

_CONTENIDO = CALOR.read_text(encoding="utf-8")
_BLOQUE = re.search(r"CONSEJOS_CALOR\s*=\s*\[(.*?)\];", _CONTENIDO, re.S)
_CONSEJO = re.compile(r"\{\s*text:\s*'([^']+)',\s*source:\s*'([^']+)',\s*url:\s*'([^']+)'\s*\}")

assert _BLOQUE, "calor.js debe exportar CONSEJOS_CALOR como un arreglo"
CONSEJOS = [{"text": m.group(1), "source": m.group(2), "url": m.group(3)}
            for m in _CONSEJO.finditer(_BLOQUE.group(1))]


def test_hay_entre_dos_y_cinco_consejos():
    """La lista es corta a propósito; crecer es una decisión de contenido (QA-207)."""
    assert 2 <= len(CONSEJOS) <= 5


def test_todo_item_del_arreglo_es_un_consejo_completo():
    """Cada «{» del arreglo abre un consejo con sus tres campos: si falta
    uno, el objeto no calza con el formato y este conteo lo delata."""
    assert _BLOQUE.group(1).count("{") == len(CONSEJOS)


def test_cada_consejo_tiene_texto_fuente_y_url():
    for consejo in CONSEJOS:
        assert consejo["text"].strip(), "consejo sin texto"
        assert consejo["source"].strip(), f"consejo sin fuente: {consejo['text'][:40]}"
        assert consejo["url"].strip(), f"consejo sin url: {consejo['text'][:40]}"


def test_toda_url_es_https_y_de_dominio_oficial():
    for consejo in CONSEJOS:
        url = consejo["url"]
        assert url.startswith("https://"), url
        host = urlsplit(url).hostname or ""
        assert any(host == d or host.endswith(f".{d}") for d in DOMINIOS_OFICIALES), url


def test_declara_fecha_de_consulta_de_las_fuentes():
    m = re.search(r"CONSULTA_FUENTES\s*=\s*'(\d{4}-\d{2}-\d{2})'", _CONTENIDO)
    assert m, "calor.js debe declarar CONSULTA_FUENTES con la fecha de consulta (AAAA-MM-DD)"


def test_recuerda_que_brasa_no_es_fuente_oficial():
    assert "no es una fuente oficial" in _CONTENIDO
