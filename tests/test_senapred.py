"""OFI-04: las alertas oficiales vigentes de SENAPRED que nombran el lugar.

El acceso es el mismo que recibe cualquier navegante del portal público (identity pool de
Cognito con rol anónimo de solo lectura + firma SigV4). El calce con el lugar es por el
título formulaico de la alerta («para la comuna de X», «para la Región del Maule»): la API
no trae el territorio poblado. Nada se inventa: fuente caída o sin mención, `alerts` = [].
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from backend.providers import senapred
from tests.conftest import json_response

ALERTA_ANGOL = {"id": "a1", "titulo": "Se declara alerta Amarilla para la comuna de Angol "
                "por evento meteorológico", "fechaHora": "2026-10-22T22:12:30.000-03:00",
                "urlAccess": "se-declara-alerta-amarilla-para-la-comuna-de-angol-por-evento"
                "-meteorologico-2026-10-22-22-13-52", "isActive": True, "isDeleted": False}
ALERTA_MAULE = {"id": "a2", "titulo": "Monitoreo Alerta Temprana Preventiva para la Región "
                "del Maule por evento meteorológico", "fechaHora": "2026-10-23T16:05:00-03:00",
                "urlAccess": "monitoreo-alerta-maule", "isActive": True, "isDeleted": False}
ALERTA_ATP = {"id": "a3", "titulo": "Se declara Alerta Temprana Preventiva para la provincia "
              "de Parinacota y la comuna de Camarones por viento",
              "fechaHora": "2026-10-20T17:56:03-03:00", "urlAccess": "atp-parinacota",
              "isActive": True, "isDeleted": False}
ALERTA_CANCELADA = {"id": "a4", "titulo": "Se cancela alerta para la comuna de Angol",
                    "fechaHora": "2026-10-23T20:49:00-03:00", "urlAccess": "cancela-angol",
                    "isActive": False, "isDeleted": False}
ALERTA_CHILLAN_VIEJO = {"id": "a5", "titulo": "Se declara Alerta Roja para la comuna de "
                        "Chillán Viejo por incendio forestal",
                        "fechaHora": "2026-10-23T10:00:00-03:00", "urlAccess": "cv",
                        "isActive": True, "isDeleted": False}
ALERTA_DOS_COMUNAS = {"id": "a6", "titulo": "Se declara Alerta Temprana Preventiva para las "
                      "comunas de Padre Las Casas y Cunco por evento meteorológico",
                      "fechaHora": "2026-10-23T11:00:00-03:00", "urlAccess": "dos",
                      "isActive": True, "isDeleted": False}
ALERTA_OHIGGINS_LARGA = {"id": "a7", "titulo": "Se declara Alerta Temprana Preventiva para "
                         "la Región del Libertador General Bernardo O'Higgins por calor",
                         "fechaHora": "2026-10-23T12:00:00-03:00", "urlAccess": "ohi",
                         "isActive": True, "isDeleted": False}
ALERTA_COIHAIQUE = {"id": "a8", "titulo": "Se declara Alerta Amarilla para la comuna de "
                    "Coihaique por evento meteorológico",
                    "fechaHora": "2026-10-23T13:00:00-03:00", "urlAccess": "coi",
                    "isActive": True, "isDeleted": False}
ALERTA_CANCELA_ACTIVA = {"id": "a9", "titulo": "Se cancela la Alerta Amarilla para la comuna "
                         "de Angol por evento meteorológico",
                         "fechaHora": "2026-10-23T21:00:00-03:00", "urlAccess": "canc",
                         "isActive": True, "isDeleted": False}


# --- para_lugar: calce por el título oficial ---

def test_para_lugar_calza_por_comuna():
    out = senapred.para_lugar([ALERTA_ANGOL], "Angol", "La Araucanía")
    assert len(out) == 1 and out[0]["scope"] == "comuna"
    assert out[0]["url"].endswith("se-declara-alerta-amarilla-para-la-comuna-de-angol-por-evento"
                                  "-meteorologico-2026-10-22-22-13-52")


def test_para_lugar_calza_por_region_y_pone_comunal_primero():
    out = senapred.para_lugar([ALERTA_MAULE, ALERTA_ANGOL], "Angol", "La Araucanía")
    assert len(out) == 1 and out[0]["scope"] == "comuna"
    out = senapred.para_lugar([ALERTA_MAULE, ALERTA_ANGOL], "Talca", "Maule")
    assert [a["scope"] for a in out] == ["region"]


def test_para_lugar_calza_comuna_dentro_de_lista_y_provincia():
    out = senapred.para_lugar([ALERTA_ATP], "Camarones", "Arica y Parinacota")
    assert len(out) == 1 and out[0]["scope"] == "comuna"


def test_para_lugar_sin_mencion_devuelve_vacio():
    assert senapred.para_lugar([ALERTA_MAULE], "Angol", "La Araucanía") == []
    assert senapred.para_lugar([ALERTA_ANGOL], "San Pedro", "Metropolitana") == []


def test_para_lugar_prefijo_no_calza_comuna_mas_larga():
    """«comuna de Chillán Viejo» nombra a Chillán Viejo, nunca a Chillán (ni San Pedro
    a San Pedro de Atacama/de la Paz): el nombre más largo gana la posición."""
    assert senapred.para_lugar([ALERTA_CHILLAN_VIEJO], "Chillán", "Ñuble") == []
    out = senapred.para_lugar([ALERTA_CHILLAN_VIEJO], "Chillán Viejo", "Ñuble")
    assert [a["scope"] for a in out] == ["comuna"]


def test_para_lugar_lista_de_comunas_nombra_a_cada_una():
    """«comunas de Padre Las Casas y Cunco» nombra a las dos, no solo a la primera."""
    for comuna in ("Padre Las Casas", "Cunco"):
        out = senapred.para_lugar([ALERTA_DOS_COMUNAS], comuna, "La Araucanía")
        assert [a["scope"] for a in out] == ["comuna"], comuna
    assert senapred.para_lugar([ALERTA_DOS_COMUNAS], "Temuco", "La Araucanía") == []


def test_para_lugar_region_forma_larga_y_variante_de_nombre():
    """«Región del Libertador General Bernardo O'Higgins» contiene «O'Higgins»; y SENAPRED
    puede escribir la variante «Coihaique» que el índice tiene como «Coyhaique»."""
    out = senapred.para_lugar([ALERTA_OHIGGINS_LARGA], "Rancagua", "O'Higgins")
    assert [a["scope"] for a in out] == ["region"]
    out = senapred.para_lugar([ALERTA_COIHAIQUE], "Coyhaique", "Aysén")
    assert [a["scope"] for a in out] == ["comuna"]


def test_para_lugar_respeta_el_tope_de_tres():
    muchas = [{**ALERTA_ANGOL, "id": f"a{i}"} for i in range(5)]
    assert len(senapred.para_lugar(muchas, "Angol", "La Araucanía")) == 3


# --- fetch_alerts: cognito anónimo + AppSync firmado, con mockeo ---

def _creds():
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
    return {"AccessKeyId": "ASIA", "SecretKey": "s", "SessionToken": "t", "Expiration": exp}


def _mock_senapred(items):
    def handler(r: httpx.Request) -> httpx.Response:
        if "cognito-identity" in r.url.host:
            if "GetId" in r.headers.get("X-Amz-Target", ""):
                return json_response({"IdentityId": "id"})
            return json_response({"Credentials": _creds()})
        body = json.loads(r.content)
        assert "alertasByDate" in body["query"]
        return json_response({"data": {"alertasByDate": {"items": items, "nextToken": None}}})
    return handler


def test_fetch_alerts_devuelve_vigentes_con_enlace():
    senapred._creds_cache.clear()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                _mock_senapred([ALERTA_ANGOL, ALERTA_CANCELADA]))) as http:
            return await senapred.fetch_alerts(http)

    out = asyncio.run(run())
    assert [a["id"] for a in out] == ["a1"]       # la cancelada no es vigente
    assert out[0]["url"].startswith("https://senapred.cl/alertas/")


def test_fetch_alerts_aviso_de_cancelacion_activo_no_es_alerta():
    """«Se cancela…» con isActive=True no es una alerta vigente: se omite."""
    senapred._creds_cache.clear()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                _mock_senapred([ALERTA_ANGOL, ALERTA_CANCELA_ACTIVA]))) as http:
            return await senapred.fetch_alerts(http)

    assert [a["id"] for a in asyncio.run(run())] == ["a1"]


def test_cognito_sin_credenciales_es_senapred_error_no_500():
    """Un 200 de Cognito sin las claves esperadas degrada a SenapredError, no a KeyError."""
    senapred._creds_cache.clear()

    def handler(r):
        if "GetId" in r.headers.get("X-Amz-Target", ""):
            return json_response({"IdentityId": "id"})
        return json_response({"Credentials": {"AccessKeyId": "ASIA"}})  # faltan claves

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await senapred.fetch_alerts(http)

    import pytest
    with pytest.raises(senapred.SenapredError):
        asyncio.run(run())


def test_fetch_alerts_respuesta_con_errores_graphql_es_error():
    senapred._creds_cache.clear()

    def handler(r):
        if "cognito-identity" in r.url.host:
            if "GetId" in r.headers.get("X-Amz-Target", ""):
                return json_response({"IdentityId": "id"})
            return json_response({"Credentials": _creds()})
        return json_response({"errors": [{"message": "denied"}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await senapred.fetch_alerts(http)

    import pytest
    with pytest.raises(senapred.SenapredError):
        asyncio.run(run())


# --- el endpoint: comuna ubicada por lat/lon + calce por título ---

def test_endpoint_devuelve_alerta_de_la_comuna(make_client, web):
    senapred._creds_cache.clear()
    web.add(lambda r: True, _mock_senapred([ALERTA_ANGOL, ALERTA_MAULE]))
    # centro de Angol (comuna 9201, La Araucanía) según comunas-index.json
    with make_client() as client:
        body = client.get("/api/alerts/official?lat=-37.8024&lon=-72.7934").json()
    assert [a["scope"] for a in body["alerts"]] == ["comuna"]
    assert body["alerts"][0]["title"].startswith("Se declara alerta Amarilla")
    assert "SENAPRED" in body["source"] and "senapred.cl" in body["source_url"]
    assert "BRASA no emite alertas" in body["note"]


def test_endpoint_fuera_de_chile_devuelve_vacio(make_client, web):
    llamadas = []
    web.add(lambda r: True,
            lambda r: (llamadas.append(r), _mock_senapred([ALERTA_ANGOL])(r))[1])
    with make_client() as client:
        body = client.get("/api/alerts/official?lat=-20.0&lon=-30.0").json()
    assert body["alerts"] == [] and not llamadas   # fuera de comuna: ni siquiera consulta


def test_endpoint_fuente_caida_devuelve_vacio(make_client, web):
    senapred._creds_cache.clear()
    web.add(lambda r: True, lambda r: httpx.Response(503))
    with make_client() as client:
        body = client.get("/api/alerts/official?lat=-37.8024&lon=-72.7934").json()
    assert body["alerts"] == [] and body["source"]
