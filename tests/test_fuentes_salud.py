"""OPS-02: verificadores del chequeo de fuentes (.github/scripts/fuentes_salud.py), sin red."""
import importlib.util
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "fuentes_salud", Path(__file__).resolve().parents[1] / ".github" / "scripts" / "fuentes_salud.py")
salud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(salud)

ENCABEZADO_CONAF = ("id,temporada,nombre,estado,lat,lon,f_inicio,f_control,f_extincion,"
                    "f_deteccion,f_aviso,f_despacho,sup_total,comuna,region,ambito,comb_inicial")


def test_encabezado_csv_completo():
    assert salud.faltan(salud.encabezado_csv(ENCABEZADO_CONAF + "\n1,2026,x"), salud.CONAF_COLUMNS) == []


def test_encabezado_csv_sin_columna():
    header = ENCABEZADO_CONAF.replace(",f_deteccion", "")
    assert salud.faltan(salud.encabezado_csv(header), salud.CONAF_COLUMNS) == ["f_deteccion"]


def test_encabezado_csv_vacio():
    assert salud.faltan(salud.encabezado_csv(""), salud.CONAF_COLUMNS) == sorted(salud.CONAF_COLUMNS)


def test_goes_momento_clave():
    key = ("ABI-L2-FDCF/2026/292/12/OR_ABI-L2-FDCF-M6_G19_"
           "s20262921230208_e20262921239315_c20262921240008.nc")
    assert salud.goes_momento(key) == datetime(2026, 10, 19, 12, 30, 20, tzinfo=timezone.utc)


def test_goes_momento_sin_fecha():
    assert salud.goes_momento("ABI-L2-FDCF/otra/cosa.nc") is None


def test_openmeteo_faltantes_ok():
    data = {"hourly": {"time": ["2026-10-19T12:00"], "temperature_2m": [20.1],
                       "relative_humidity_2m": [30], "wind_speed_10m": [12.0],
                       "wind_gusts_10m": [40.0], "wind_direction_10m": [270]}}
    assert salud.openmeteo_faltantes(data) == []


def test_openmeteo_faltantes_sin_variable():
    """Las variables de viento que pide weather.py también se exigen."""
    data = {"hourly": {"time": ["2026-10-19T12:00"], "temperature_2m": [20.1],
                       "relative_humidity_2m": [30], "wind_direction_10m": [270]}}
    assert salud.openmeteo_faltantes(data) == ["wind_gusts_10m", "wind_speed_10m"]


def test_openmeteo_sin_hourly():
    assert salud.openmeteo_faltantes({"error": True}) == ["relative_humidity_2m", "temperature_2m",
                                                        "time", "wind_direction_10m", "wind_gusts_10m",
                                                        "wind_speed_10m"]


CAP = ('<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">'
       "<identifier>A567</identifier><info><event>Viento</event></info></alert>")


def test_cap_valido():
    assert salud.cap_valido(CAP)


def test_cap_sin_info_no_es_valido():
    assert not salud.cap_valido('<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"/>')


def test_cap_no_cap_no_es_valido():
    assert not salud.cap_valido("<rss><channel/></rss>")
    assert not salud.cap_valido("no es xml")


def test_rss_items():
    feed = ('<?xml version="1.0"?><rss version="2.0"><channel>'
            "<item><title>Aviso</title><link>https://x/cap.xml</link></item>"
            "<item><title>Otro</title><link>https://x/cap2.xml</link></item>"
            "</channel></rss>")
    assert len(salud.rss_items(feed)) == 2
    assert salud.rss_items('<?xml version="1.0"?><rss><channel/></rss>') == []


def test_rss_items_no_xml():
    with pytest.raises(ET.ParseError):
        salud.rss_items("no es xml")


def test_firms_sin_clave_se_omite(monkeypatch):
    """Sin FIRMS_MAP_KEY el chequeo se omite sin tocar la red."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    estado, detalle = salud.check_firms()
    assert estado == "OMITIDO" and "FIRMS_MAP_KEY" in detalle
