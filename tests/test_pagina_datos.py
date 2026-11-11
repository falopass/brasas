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


def test_tabla_de_conjuntos_se_apila_en_el_telefono():
    """MOV-06: bajo 700 px cada conjunto se lee como una ficha — la tabla sigue
    siendo <table> con sus <th scope>, pero cada celda lleva data-label y el CSS
    la apila en pares «etiqueta: valor» en vez de una tabla de 640 px."""
    assert "dataset.label" in JS, "datos.js: las celdas no llevan data-label"
    for rotulo in ("Conjunto", "En palabras simples", "Parámetros", "Geometría", "Propiedades", "Fuente", "Se actualiza"):
        assert f"'{rotulo}'" in JS, f"datos.js: falta la celda «{rotulo}»"
    assert HTML.count('<th scope="col"') == 7, "la tabla debe conservar sus 7 encabezados con scope"
    # display:block le quita la semántica de tabla a varios lectores de pantalla:
    # los roles ARIA explícitos (table > rowgroup > row > cell/columnheader) la conservan.
    for rol in ('role="table"', 'role="rowgroup"', 'role="row"', 'role="columnheader"'):
        assert rol in HTML, f"datos.html: falta {rol} en la tabla"
    assert "'role', 'cell'" in JS and "'role', 'row'" in JS, (
        "datos.js: las filas y celdas generadas deben llevar role explícito"
    )
    css = re.search(r"<style>(.*?)</style>", HTML, re.S)
    assert css, "datos.html: falta el bloque <style>"
    partes = css.group(1).split("@media (max-width: 699px)", 1)
    assert len(partes) == 2, "datos.html: falta el apilado de la tabla bajo 700 px"
    bloque = partes[1]
    assert "display: block" in bloque, "el apilado debe volver bloques tabla, filas y celdas"
    assert "attr(data-label)" in bloque, "falta td::before { content: attr(data-label) }"


def test_enlace_de_ruta_tocable_44px_en_el_telefono():
    """MOV-06: la URL de cada conjunto queda sola en su línea bajo 700 px:
    al menos 44 px de alto tocable, sin cambiar el tamaño de letra."""
    assert "'ruta'" in JS, "datos.js: el enlace de la ruta no lleva la clase .ruta"
    css = re.search(r"<style>(.*?)</style>", HTML, re.S).group(1)
    bloque = css.split("@media (max-width: 699px)", 1)[1]
    regla = re.search(r"\.ruta\s*\{([^}]*)\}", bloque)
    assert regla, "datos.html: falta la regla .ruta en el bloque móvil"
    assert "inline-flex" in regla.group(1), ".ruta debe ser inline-flex para centrar el texto"
    altos = [float(v) for v in re.findall(r"min-height\s*:\s*([0-9.]+)px", regla.group(1))]
    assert altos and altos[-1] >= 44, "datos.html: .ruta bajo 44 px de alto"
