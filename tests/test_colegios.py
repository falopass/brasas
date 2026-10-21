"""Guardas de la clase imprimible para colegios (EDU-01 / CONT-10).

`web/colegios.html` es una hoja A4 autocontenida con una clase de 45 minutos
sobre el incendio Las Máquinas 2017 (Maule): sin scripts ni recursos de hosts
externos, guion en cuatro tramos con sus minutos, cifras copiadas de
`web/data/cases.json` con su fuente, seis preguntas y enlaces solo a sitios
oficiales. La guía del docente vive en `docs/COLEGIOS.md`.
"""

import json
import re
from urllib.parse import urlparse

from backend.settings import ROOT

PAGINA = ROOT / "web" / "colegios.html"
CSS = ROOT / "web" / "css" / "colegios.css"
CASOS = ROOT / "web" / "data" / "cases.json"
GUIA = ROOT / "docs" / "COLEGIOS.md"

# La hoja solo enlaza a las autoridades: ningún medio ni red social.
DOMINIOS_PERMITIDOS = {"senapred.cl", "www.senapred.cl", "conaf.cl", "www.conaf.cl"}
REDES_Y_MEDIOS = ("facebook", "instagram", "tiktok", "twitter", "x.com", "youtube", "whatsapp", "t.me")


def _html() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _caso() -> tuple[dict, str]:
    casos = json.loads(CASOS.read_text(encoding="utf-8"))["cases"]
    caso = next(c for c in casos if c["id"] == "las-maquinas-2017")
    return caso, json.dumps(caso, ensure_ascii=False)


def test_existe_sin_scripts_ni_hosts_externos():
    assert PAGINA.is_file(), "falta web/colegios.html"
    html = _html()
    assert "<script" not in html.lower(), "la página no puede tener scripts"
    for tag, _attr, ref in re.findall(r"<(\w+)[^>]*?\b(src|href|action)\s*=\s*[\"']([^\"']+)", html):
        if tag.lower() == "a":
            continue  # los enlaces los sigue el docente, no los carga el navegador
        assert not re.match(r"(?:https?:)?//", ref), f"recurso de host externo: {ref}"


def test_cifras_coinciden_con_cases_json():
    """Toda cifra con «ha» o «km» de la hoja sale verbatim del caso en cases.json,
    y cada cifra del caso aparece con su fuente tal como está en el archivo."""
    caso, texto = _caso()
    html = _html()
    cifras = re.findall(r"\d[\d.,]*\s*(?:ha|km)\b", html)
    assert cifras, "la hoja no cita ninguna cifra del caso"
    for cifra in cifras:
        assert cifra in texto, f"«{cifra}» no aparece en las-maquinas-2017 de cases.json"
    for figura in caso["figures"]:
        for revision in figura["revisions"]:
            assert revision["value"] in html, f"falta la cifra {revision['value']}"
            assert revision["source"] in html, f"{revision['value']} sin su fuente «{revision['source']}»"


def test_guion_cuatro_tramos_con_sus_minutos():
    """Cuatro tramos de 10 / 15 / 10 / 10 minutos; cada uno dice qué hace el
    docente y qué hace el curso."""
    tramos = re.findall(r'<section class="tramo">(.*?)</section>', _html(), re.S)
    assert len(tramos) == 4, f"se esperan 4 tramos, hay {len(tramos)}"
    minutos = []
    for i, tramo in enumerate(tramos, 1):
        m = re.search(r"(\d+)\s*min\b", tramo)
        assert m, f"tramo {i} sin duración en minutos"
        minutos.append(int(m.group(1)))
        assert "Docente:" in tramo and "Curso:" in tramo, f"tramo {i} sin la acción del docente o del curso"
    assert minutos == [10, 15, 10, 10], f"los tramos duran {minutos}, se espera [10, 15, 10, 10]"


def test_seis_preguntas_tres_de_comprension_y_tres_de_decision():
    bloques = re.findall(r'<ol class="preguntas">(.*?)</ol>', _html(), re.S)
    assert len(bloques) == 2, "se esperan dos bloques de preguntas: comprensión y decisión"
    cantidades = [len(re.findall(r"<li>", bloque)) for bloque in bloques]
    assert all(c >= 3 for c in cantidades), f"cada bloque necesita 3 preguntas: {cantidades}"
    assert sum(cantidades) >= 6, f"se esperan al menos 6 preguntas, hay {sum(cantidades)}"


def test_enlaces_solo_oficiales_en_https():
    enlaces = re.findall(r'<a\b[^>]*?href="([^"]+)"', _html())
    assert enlaces, "la hoja no tiene enlaces"
    externos = []
    for enlace in enlaces:
        assert not enlace.startswith("http://"), f"enlace sin https: {enlace}"
        assert not any(m in enlace.lower() for m in REDES_Y_MEDIOS), f"enlace a red social o medio: {enlace}"
        if enlace.startswith("https://"):
            externos.append(enlace)
            host = urlparse(enlace).hostname or ""
            assert host in DOMINIOS_PERMITIDOS, f"enlace externo que no es oficial: {enlace}"
        else:
            assert enlace.startswith(("/", "#")), f"enlace interno raro: {enlace}"
    assert any("senapred.cl" in e for e in externos), "falta el enlace a SENAPRED"
    assert any("conaf.cl" in e for e in externos), "falta el enlace a CONAF"


def test_nombra_senapred_y_dice_que_brasa_no_es_oficial():
    html = _html()
    assert "SENAPRED" in html
    assert "no es un sistema oficial" in html
    assert "Las Máquinas" in html and "Maule" in html


def test_imprime_en_a4_sin_javascript():
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"@page\s*\{[^}]*size:\s*A4", css), "colegios.css sin @page A4"
    impresion = re.search(r"@media print\s*\{(.*?)\n\}", css, re.S)
    assert impresion, "falta el bloque @media print"
    assert "break-inside: avoid" in impresion.group(1), "@media print sin break-inside: avoid"
    assert re.search(r"\.imprimir\s*\{[^}]*display:\s*none", impresion.group(1)), "el botón de impresión debe desaparecer en el papel"
    assert 'class="imprimir"' in _html(), "falta el botón de impresión"


def test_guia_docente_existe_y_cubre_lo_basico():
    guia = GUIA.read_text(encoding="utf-8")
    assert "#/casos" in guia, "la guía no explica cómo abrir el caso en la app"
    assert "SENAPRED" in guia
    assert "no es un sistema oficial" in guia, "la guía debe responder que BRASA explica, no alerta"
