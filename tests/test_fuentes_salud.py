"""Pruebas del verificador semanal de fuentes (.github/scripts/fuentes_salud.py, OPS-02).

Sin red: solo texto de entrada y veredicto de salida. Si una fuente cambia su formato,
estos fixtures rotos son lo que la prueba semanal debe detectar.
"""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "fuentes_salud.py"
_spec = importlib.util.spec_from_file_location("fuentes_salud", _SCRIPT)
fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fs)

CONAF_HEADER = ("id,temporada,nombre,estado,lat,lon,f_inicio,f_control,f_extincion,"
                "f_deteccion,f_aviso,f_despacho,sup_total,comuna,region,ambito,comb_inicial")

NOW = datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)  # día juliano 292


def listado_goes(*keys: str) -> str:
    return ("<?xml version='1.0'?><ListBucketResult>"
            + "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
            + "</ListBucketResult>")


RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>DMC</title>
<item><title>Aviso</title><link>https://archivos.meteochile.gob.cl/cap/1.xml</link></item>
</channel></rss>"""

CAP_12 = """<?xml version="1.0"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>x</identifier><info><event>viento</event></info>
</alert>"""

OPEN_METEO_OK = {"hourly": {"time": ["2026-10-19T12:00"],
                            "temperature_2m": [20.0], "relative_humidity_2m": [30],
                            "wind_speed_10m": [10.0], "wind_gusts_10m": [20.0],
                            "wind_direction_10m": [180]}}

OPEN_METEO_JSON = json.dumps(OPEN_METEO_OK)


def test_conaf_encabezado_completo():
    estado, detalle = fs.veredicto_conaf(CONAF_HEADER + "\n1,2026,x,activo,-33,-70,,,,,,,1,c,r,a,c\n")
    assert estado == "OK"


def test_conaf_falta_columna():
    sin = CONAF_HEADER.replace(",f_despacho", "")
    estado, detalle = fs.veredicto_conaf(sin + "\n")
    assert estado == "FALLA"
    assert "f_despacho" in detalle


def test_goes_clave_reciente():
    key = "ABI-L2-FDCF/2026/292/12/OR_ABI-L2-FDCF-M6_G19_s2026292121000_e.nc"
    estado, _ = fs.veredicto_goes([listado_goes(key), listado_goes()], NOW)
    assert estado == "OK"


def test_goes_clave_antigua():
    key = "ABI-L2-FDCF/2026/292/09/OR_ABI-L2-FDCF-M6_G19_s2026292093000_e.nc"
    estado, _ = fs.veredicto_goes([listado_goes(key)], NOW)
    # El script reporta OJO (warning), no FALLA: igual detiene el run en verde.
    assert estado == "OJO"


def test_goes_listado_vacio():
    estado, _ = fs.veredicto_goes([listado_goes(), listado_goes()], NOW)
    assert estado == "OJO"


def test_firms_sin_clave(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert fs.check_firms()[0] == "OMITIDO"


def test_firms_clave_nunca_en_salida(monkeypatch):
    """Con clave falsa, ni el error HTTP ni una excepción la dejan ver."""
    clave = "CLAVE_FALSA_12345"
    monkeypatch.setenv("FIRMS_MAP_KEY", clave)

    def urlopen_403(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(fs.urllib.request, "urlopen", urlopen_403)
    estado, detalle = fs.check_firms()
    assert estado == "FALLA"
    assert clave not in detalle

    def urlopen_error(req, timeout):
        raise OSError(f"falló {req.full_url}")  # el mensaje sí trae la clave…

    monkeypatch.setattr(fs.urllib.request, "urlopen", urlopen_error)
    estado, detalle = fs.check_firms()
    assert estado == "FALLA"
    assert clave not in detalle  # …pero el veredicto solo usa el tipo de excepción


def test_openmeteo_ok():
    assert fs.veredicto_openmeteo(OPEN_METEO_JSON)[0] == "OK"


def test_openmeteo_sin_rafagas():
    data = {"hourly": {k: v for k, v in OPEN_METEO_OK["hourly"].items() if k != "wind_gusts_10m"}}
    estado, detalle = fs.veredicto_openmeteo(json.dumps(data))
    assert estado == "FALLA"
    assert "wind_gusts_10m" in detalle


def test_dmc_ok():
    assert fs.veredicto_dmc(RSS, lambda url: (200, CAP_12))[0] == "OK"


def test_dmc_cap_namespace_distinto():
    cap_otro = CAP_12.replace("cap:1.2", "cap:1.1")
    estado, detalle = fs.veredicto_dmc(RSS, lambda url: (200, cap_otro))
    assert estado == "FALLA"


def test_dmc_rss_no_xml():
    assert fs.veredicto_dmc("el feed respondió HTML, no XML <", lambda url: (0, ""))[0] == "FALLA"


# --------------------------------------------------------------- fuentes nuevas (OFI-12)

BOTON_ROJO_JSON = json.dumps({"features": [
    {"attributes": {"date": "2026-10-19", "com_id": 7301, "horas": 6,
                    "SUM_br_ha": 123.4, "proportion": 0.5}}]})

GLM_KEY = "GLM-L2-LCFA/2026/292/12/OR_GLM-L2-LCFA_G19_s2026292121000_e2026292122000_c.nc"
ADPF_KEY = "ABI-L2-ADPF/2026/292/12/OR_ABI-L2-ADPF-M6_G19_s20262921210211_e20262921219511_c.nc"


def test_boton_rojo_ok():
    estado, _ = fs.veredicto_boton_rojo(BOTON_ROJO_JSON)
    assert estado == "OK"


def test_boton_rojo_campo_cambiado():
    sin_horas = BOTON_ROJO_JSON.replace('"horas": 6, ', '')
    estado, detalle = fs.veredicto_boton_rojo(sin_horas)
    assert estado == "FALLA"
    assert "horas" in detalle


def test_boton_rojo_sin_comunas():
    assert fs.veredicto_boton_rojo('{"features": []}')[0] == "OJO"


def test_boton_rojo_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert fs.check_boton_rojo()[0] == "FALLA"


def test_glm_clave_reciente():
    estado, _ = fs.veredicto_goes([listado_goes(GLM_KEY)], NOW, fs.GLM_PRODUCT)
    assert estado == "OK"


def test_glm_listado_vacio():
    estado, detalle = fs.veredicto_goes([listado_goes()], NOW, fs.GLM_PRODUCT)
    assert estado == "OJO"
    assert "GLM-L2-LCFA" in detalle


def test_glm_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert fs.check_glm(NOW)[0] == "FALLA"


def test_adpf_clave_reciente():
    estado, _ = fs.veredicto_goes([listado_goes(ADPF_KEY)], NOW, fs.ADPF_PRODUCT)
    assert estado == "OK"


def test_adpf_listado_vacio():
    estado, detalle = fs.veredicto_goes([listado_goes()], NOW, fs.ADPF_PRODUCT)
    assert estado == "OJO"
    assert "ABI-L2-ADPF" in detalle


def test_adpf_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert fs.check_adpf(NOW)[0] == "FALLA"


def test_geprif_ok():
    estado, _ = fs.veredicto_conaf(CONAF_HEADER + "\n1,2026,x,activo,-33,-70,,,,,,,1,c,r,a,c\n")
    assert estado == "OK"


def test_geprif_encabezado_cambiado(monkeypatch):
    otro = CONAF_HEADER.replace(",comuna", "")
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (200, otro + "\n"))
    estado, detalle = fs.check_geprif()
    assert estado == "FALLA"
    assert "comuna" in detalle


def test_geprif_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (404, "Not Found"))
    assert fs.check_geprif()[0] == "FALLA"
