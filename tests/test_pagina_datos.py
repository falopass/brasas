"""Guardas de la página pública de datos abiertos (DAT-03/04/05/09).

Sin red: lee ``web/datos.html`` y ``web/js/datos.js`` como texto, y los ids reales del
índice con el cliente de prueba (``GET /api/opendata``).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "datos.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "js" / "datos.js").read_text(encoding="utf-8")


def _plano() -> dict[str, str]:
    """Las entradas `id: {...}` del diccionario PLANO declarado en datos.js."""
    bloque = re.search(r"PLANO\s*=\s*\{(.*?)\n\};", JS, re.S)
    assert bloque, "no se encontró el diccionario PLANO en web/js/datos.js"
    return {m.group(1): m.group(2) for m in re.finditer(r"^  '?([a-z][a-z0-9-]*)'?\s*:\s*\{(.*?)\},", bloque.group(1), re.M | re.S)}


def _ids_del_indice(make_client):
    with make_client() as client:
        body = client.get("/api/opendata").json()
    return [d["id"] for d in body["datasets"]]


def test_html_sin_urls_de_conjuntos_escritas_a_mano():
    """La lista de accesos ya no se mantiene a mano: ninguna URL /api/opendata/<conjunto> en el HTML."""
    encontradas = re.findall(r"/api/opendata/[a-z][a-z0-9._-]*", HTML)
    assert not encontradas, f"URLs de conjuntos escritas a mano en datos.html: {encontradas}"


def test_plano_cubre_todos_los_ids_del_indice(make_client):
    plano = _plano()
    ids = _ids_del_indice(make_client)
    faltan = [i for i in ids if i not in plano]
    assert not faltan, f"PLANO no cubre los conjuntos del índice: {faltan}"


def test_plano_tiene_que_cadencia_y_ojo_en_cada_entrada():
    for ident, cuerpo in _plano().items():
        for campo in ("que:", "cadencia:", "ojo:"):
            assert campo in cuerpo, f"PLANO[{ident}] no declara {campo}"


def test_la_pagina_declara_canonical_y_avisa_que_no_es_oficial():
    assert '<link rel="canonical"' in HTML
    assert "no es un sistema oficial" in HTML
    assert "<script" not in HTML.split('src="/web/js/datos.js"')[0] or 'type="module"' in HTML
