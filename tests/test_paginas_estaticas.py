"""Páginas estáticas de BRASA: la hoja imprimible de emergencia (UX-07) es autocontenida,
sin scripts ni hosts externos, y se sirve en /lista.html."""

import re

from backend.settings import ROOT

LISTA = ROOT / "web" / "lista.html"


def test_lista_existe_sin_scripts_ni_hosts_externos():
    html = LISTA.read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    for ref in re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        assert not re.match(r"(?:https?:)?//", ref), f"referencia a un host externo: {ref}"


def test_lista_tiene_telefonos_y_descargo():
    html = LISTA.read_text(encoding="utf-8")
    for telefono in ("130", "131", "132", "133"):
        assert telefono in html
    assert "no es un sistema oficial" in html


def test_lista_se_sirve_en_raiz(make_client):
    with make_client() as client:
        r = client.get("/lista.html")
        assert r.status_code == 200
        assert "no es un sistema oficial" in r.text


def test_lista_tiene_toggle_letra_grande_sin_js():
    html = LISTA.read_text(encoding="utf-8")
    assert re.search(r'<input[^>]+id="grande"', html)
    assert re.search(r'<label[^>]+for="grande"', html)
    css = (ROOT / "web" / "css" / "lista.css").read_text(encoding="utf-8")
    assert "#grande:checked" in css
    assert re.search(r"@media print[^}]*\.size-toggle", css, re.S)
