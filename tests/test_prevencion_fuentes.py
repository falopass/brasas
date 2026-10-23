"""UX-62: cada acción de prevención con fuente oficial real. La suite corta cualquier
enlace inventado: solo dominios oficiales declarados aquí."""
import re
from datetime import date
from pathlib import Path

PREVENCION = Path(__file__).resolve().parents[1] / "web" / "js" / "prevencion.js"
DOMINIOS_OFICIALES = {"senapred.cl", "conaf.cl", "oficinavirtual.conaf.cl", "minsal.cl",
                      "saludresponde.minsal.cl", "degreyd.minsal.cl", "gob.cl"}
ACCION = re.compile(r"\{\s*text:\s*'([^']+)',\s*source:\s*'([^']+)',\s*url:\s*(?:'([^']+)'|([A-Z_]+))\s*\}")
CONSTANTE_URL = re.compile(r"const (\w+) = '([^']+)';")


def test_toda_accion_tiene_texto_fuente_y_url_oficial():
    src = PREVENCION.read_text(encoding="utf-8")
    constantes = {m.group(1): m.group(2) for m in CONSTANTE_URL.finditer(src)}
    acciones = list(ACCION.finditer(src))
    assert acciones, "no se encontraron acciones {text, source, url}"
    for texto, fuente, url_lit, url_const in acciones:
        assert texto.strip(), "acción sin texto"
        assert fuente.strip(), "acción sin fuente"
        url = url_lit or constantes.get(url_const)
        assert url, f"acción sin url: {texto[:40]}"
        assert url.startswith("https://"), url
        dominio = url.split("/")[2].lower()
        assert any(dominio == d or dominio.endswith(f".{d}") for d in DOMINIOS_OFICIALES), f"dominio no oficial: {dominio}"


def test_los_cuatro_niveles_tienen_acciones():
    src = PREVENCION.read_text(encoding="utf-8")
    bloque = src.split("export const ACCIONES", 1)[1].split("const NIVEL_PALABRA", 1)[0]
    for nivel in ("bajo", "moderado", "alto", "extremo"):
        m = re.search(rf"{nivel}:\s*\[(.*?)\]", bloque, re.S)
        assert m, f"falta el nivel {nivel}"
        assert m.group(1).count("text:") >= 1, f"{nivel} sin acciones"


def test_consulta_fuentes_es_fecha_iso():
    src = PREVENCION.read_text(encoding="utf-8")
    m = re.search(r"CONSULTA_FUENTES = '(\d{4}-\d{2}-\d{2})'", src)
    assert m, "falta CONSULTA_FUENTES"
    date.fromisoformat(m.group(1))
