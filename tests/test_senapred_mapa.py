"""OFI-207 (parte backend): `GET /api/senapred/alertas` sirve todas las alertas oficiales
vigentes para la capa nacional del mapa, con la clase y los códigos BCN de las comunas que
cada título oficial nombra.

El calce es el mismo de `para_lugar` («para la comuna de X», «para las comunas de X e Y»,
«para la Región del Maule») pero en vez de filtrar por un lugar devuelve el territorio que
la alerta nombra, para que la capa pinte el polígono sin geocodificar.
"""
from __future__ import annotations

import httpx
import pytest

from backend.geo import territory
from backend.providers import senapred
from tests.test_senapred import (ALERTA_ANGOL, ALERTA_ATP, ALERTA_CANCELADA, ALERTA_CHILLAN_VIEJO,
                                 ALERTA_COIHAIQUE, ALERTA_DOS_COMUNAS, ALERTA_MAULE,
                                 ALERTA_OHIGGINS_LARGA, _mock_senapred, _n)


# --- tipo / comunas_que_nombra: clase y territorio desde el título oficial ---

@pytest.mark.parametrize("titulo,esperado", [
    ("Se declara Alerta Roja para la comuna de Angol por incendio forestal", "roja"),
    ("Se declara alerta Amarilla para la comuna de Angol por evento meteorológico", "amarilla"),
    ("Monitoreo Alerta Temprana Preventiva para la Región del Maule por viento", "temprana_preventiva"),
    ("Se declara Alerta Temprana Preventiva para la comuna de Camarones por viento", "temprana_preventiva"),
    ("Aviso especial de la autoridad para la comuna de Angol", "otra"),
    ("", "otra"),
])
def test_tipo_segun_el_titulo_oficial(titulo, esperado):
    assert senapred.tipo(titulo) == esperado


def test_comunas_que_nombra_forma_comunal_y_lista():
    """«comuna de Angol» da su código; «comunas de Padre Las Casas y Cunco» da los dos."""
    assert senapred.comunas_que_nombra(ALERTA_ANGOL["titulo"]) == [9201]
    assert senapred.comunas_que_nombra(ALERTA_DOS_COMUNAS["titulo"]) == [9103, 9112]


def test_comunas_que_nombra_forma_regional_expande_la_region():
    """«para la Región del Maule» nombra a las 30 comunas del Maule (BCN, norte a sur)."""
    codes = senapred.comunas_que_nombra(ALERTA_MAULE["titulo"])
    esperado = sorted(c.code for c in territory().comunas if c.region_code == 7)
    assert codes == esperado and len(codes) == 30


def test_comunas_que_nombra_region_en_forma_larga():
    """«Región del Libertador General Bernardo O'Higgins» expande O'Higgins (código 6)."""
    codes = senapred.comunas_que_nombra(ALERTA_OHIGGINS_LARGA["titulo"])
    esperado = sorted(c.code for c in territory().comunas if c.region_code == 6)
    assert codes == esperado and 6101 in codes          # Rancagua


def test_comunas_que_nombra_respeta_maximal_munch_y_variante():
    """«comuna de Chillán Viejo» nombra a Chillán Viejo (16103), nunca a Chillán; y la
    variante «Coihaique» resuelve a Coyhaique (11101)."""
    codes = senapred.comunas_que_nombra(ALERTA_CHILLAN_VIEJO["titulo"])
    assert codes == [16103]
    assert senapred.comunas_que_nombra(ALERTA_COIHAIQUE["titulo"]) == [11101]


def test_comunas_que_nombra_provincia_sin_comuna_da_vacio():
    """«provincia de Parinacota y la comuna de Camarones»: sin mapa provincia→comuna solo
    cuenta la comuna nombrada explícitamente (limitación documentada de `para_lugar`)."""
    assert senapred.comunas_que_nombra(ALERTA_ATP["titulo"]) == [15102]


# --- para_mapa: la vista nacional ---

def test_para_mapa_formato_y_dedup_por_url():
    """Cada alerta lleva id, tipo, título exacto, fecha, enlace y comunas; un «Monitoreo»
    republicado con el mismo slug cuenta una sola vez."""
    vieja = {**_n(ALERTA_ANGOL)[0], "id": "vieja", "issued_at": "2026-10-20T10:00:00-03:00"}
    nueva = {**_n(ALERTA_ANGOL)[0], "id": "nueva", "issued_at": "2026-10-23T10:00:00-03:00"}
    out = senapred.para_mapa([vieja, nueva, *_n(ALERTA_MAULE)])
    assert [a["id"] for a in out] == ["a2", "nueva"]           # más nuevas primero, una por URL
    maule, angol = out
    assert set(angol) == {"id", "tipo", "title", "issued_at", "url", "comunas"}
    assert angol["title"] == ALERTA_ANGOL["titulo"]            # texto oficial exacto
    assert angol["tipo"] == "amarilla" and angol["comunas"] == [9201]
    assert maule["tipo"] == "temprana_preventiva" and len(maule["comunas"]) == 30


def test_para_mapa_cancelada_ya_no_llega_vigente():
    """`fetch_alerts` ya filtra las canceladas; si una llegara con isActive, igual sale
    en la lista (la degradación la decide la fuente) — aquí solo no revienta."""
    out = senapred.para_mapa(_n(ALERTA_CANCELADA))
    assert out[0]["tipo"] == "otra" and out[0]["comunas"] == [9201]


# --- el endpoint ---

def test_endpoint_sirve_las_vigentes_con_su_formato(make_client, web):
    """Público, sin token: clase, título exacto, fecha, enlace, comunas nombradas y
    Cache-Control corto; la misma caché `senapred:alertas` que el resto."""
    senapred._creds_cache.clear()
    web.add(lambda r: True, _mock_senapred([ALERTA_ANGOL, ALERTA_MAULE]))
    with make_client(GOES_ENABLED="0") as client:
        r = client.get("/api/senapred/alertas")
        assert r.status_code == 200
        assert r.headers["Cache-Control"].startswith("public")
        body = r.json()
        assert body["source"] == senapred.SOURCE and body["source_url"] == senapred.SOURCE_URL
        assert "BRASA no emite alertas" in body["note"]
        assert [a["id"] for a in body["alerts"]] == ["a2", "a1"]   # más nuevas primero
        maule, angol = body["alerts"]
        assert maule["tipo"] == "temprana_preventiva" and len(maule["comunas"]) == 30
        assert angol["tipo"] == "amarilla" and angol["comunas"] == [9201]
        assert angol["title"] == ALERTA_ANGOL["titulo"] and angol["url"].endswith(ALERTA_ANGOL["urlAccess"])
        # La misma caché alimenta el endpoint por lugar: segunda lectura sin nueva descarga.
        assert client.get("/api/alerts/official", params={"lat": -37.8, "lon": -72.79}).status_code == 200
        assert len([r for r in web.requests if "appsync" in r.url.host]) == 1


def test_endpoint_fuente_caida_degrada_a_lista_vacia(make_client, web):
    senapred._creds_cache.clear()
    web.add(lambda r: True, lambda r: httpx.Response(503))
    with make_client(GOES_ENABLED="0") as client:
        r = client.get("/api/senapred/alertas")
        assert r.status_code == 200
        body = r.json()
        assert body["alerts"] == [] and body["source_url"] == senapred.SOURCE_URL
