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

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "fuentes_salud.py"
_spec = importlib.util.spec_from_file_location("fuentes_salud", _SCRIPT)
fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fs)

CONAF_HEADER = (
    "id,temporada,nombre,estado,lat,lon,f_inicio,f_control,f_extincion,"
    "f_deteccion,f_aviso,f_despacho,sup_total,comuna,region,ambito,comb_inicial"
)

NOW = datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)  # día juliano 292


def listado_goes(*keys: str) -> str:
    return "<?xml version='1.0'?><ListBucketResult>" + "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys) + "</ListBucketResult>"


RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>DMC</title>
<item><title>Aviso</title><link>https://archivos.meteochile.gob.cl/cap/1.xml</link></item>
</channel></rss>"""

CAP_12 = """<?xml version="1.0"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>x</identifier><info><event>viento</event></info>
</alert>"""

OPEN_METEO_OK = {
    "hourly": {
        "time": ["2026-10-19T12:00"],
        "temperature_2m": [20.0],
        "relative_humidity_2m": [30],
        "wind_speed_10m": [10.0],
        "wind_gusts_10m": [20.0],
        "wind_direction_10m": [180],
    }
}

OPEN_METEO_JSON = json.dumps(OPEN_METEO_OK)


@pytest.mark.parametrize(
    ("cuerpo", "estado", "detalle"),
    [
        (CONAF_HEADER + "\n1,2026,x,activo,-33,-70,,,,,,,1,c,r,a,c\n", "OK", ""),
        (CONAF_HEADER.replace(",f_despacho", "") + "\n", "FALLA", "f_despacho"),
    ],
    ids=["encabezado-completo", "falta-columna"],
)
def test_veredicto_conaf(cuerpo, estado, detalle):
    estado_real, detalle_real = fs.veredicto_conaf(cuerpo)
    assert estado_real == estado
    if detalle:
        assert detalle in detalle_real


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


@pytest.mark.parametrize(
    ("data", "estado", "detalle"),
    [
        (OPEN_METEO_OK, "OK", ""),
        (
            {**OPEN_METEO_OK, "hourly": {k: v for k, v in OPEN_METEO_OK["hourly"].items() if k != "wind_gusts_10m"}},
            "FALLA",
            "wind_gusts_10m",
        ),
    ],
    ids=["ok", "sin-rafagas"],
)
def test_veredicto_openmeteo(data, estado, detalle):
    estado_real, detalle_real = fs.veredicto_openmeteo(json.dumps(data))
    assert estado_real == estado
    if detalle:
        assert detalle in detalle_real


@pytest.mark.parametrize(
    ("rss", "cap", "estado"),
    [
        (RSS, CAP_12, "OK"),
        (RSS, CAP_12.replace("cap:1.2", "cap:1.1"), "FALLA"),
        ("el feed respondió HTML, no XML <", "", "FALLA"),
    ],
    ids=["ok", "namespace-distinto", "rss-no-xml"],
)
def test_veredicto_dmc(rss, cap, estado):
    assert fs.veredicto_dmc(rss, lambda url: (200, cap))[0] == estado


BOTON_ROJO_JSON = json.dumps(
    {"features": [{"attributes": {"date": "2026-10-19", "com_id": 7301, "horas": 6, "SUM_br_ha": 123.4, "proportion": 0.5}}]}
)

GLM_KEY = "GLM-L2-LCFA/2026/292/12/OR_GLM-L2-LCFA_G19_s2026292121000_e2026292122000_c.nc"
ADPF_KEY = "ABI-L2-ADPF/2026/292/12/OR_ABI-L2-ADPF-M6_G19_s20262921210211_e20262921219511_c.nc"


@pytest.mark.parametrize(
    ("cuerpo", "estado", "detalle"),
    [
        (BOTON_ROJO_JSON, "OK", ""),
        (BOTON_ROJO_JSON.replace('"horas": 6, ', ""), "FALLA", "horas"),
        ('{"features": []}', "OJO", ""),
    ],
    ids=["ok", "campo-cambiado", "sin-comunas"],
)
def test_veredicto_boton_rojo(cuerpo, estado, detalle):
    estado_real, detalle_real = fs.veredicto_boton_rojo(cuerpo)
    assert estado_real == estado
    if detalle:
        assert detalle in detalle_real


def test_boton_rojo_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert fs.check_boton_rojo()[0] == "FALLA"


@pytest.mark.parametrize(
    ("key", "producto", "estado", "detalle"),
    [
        ("ABI-L2-FDCF/2026/292/12/OR_ABI-L2-FDCF-M6_G19_s2026292121000_e.nc", fs.GOES_PRODUCT, "OK", ""),
        (GLM_KEY, fs.GLM_PRODUCT, "OK", ""),
        (ADPF_KEY, fs.ADPF_PRODUCT, "OK", ""),
        ("ABI-L2-FDCF/2026/292/09/OR_ABI-L2-FDCF-M6_G19_s2026292093000_e.nc", fs.GOES_PRODUCT, "OJO", ""),
        ("", fs.GLM_PRODUCT, "OJO", "GLM-L2-LCFA"),
        ("", fs.ADPF_PRODUCT, "OJO", "ABI-L2-ADPF"),
    ],
    ids=["fdcf-reciente", "glm-reciente", "adpf-reciente", "fdcf-antigua", "glm-vacio", "adpf-vacio"],
)
def test_veredicto_goes(key, producto, estado, detalle):
    estado_real, detalle_real = fs.veredicto_goes([listado_goes(key)], NOW, producto)
    assert estado_real == estado
    if detalle:
        assert detalle in detalle_real


@pytest.mark.parametrize("check", [fs.check_goes, fs.check_glm, fs.check_adpf], ids=["goes", "glm", "adpf"])
def test_goes_sin_respuesta(monkeypatch, check):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert check(NOW)[0] == "FALLA"


def test_geprif_encabezado_cambiado(monkeypatch):
    otro = CONAF_HEADER.replace(",comuna", "")
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (200, otro + "\n"))
    estado, detalle = fs.check_geprif()
    assert estado == "FALLA"
    assert "comuna" in detalle


def test_geprif_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (404, "Not Found"))
    assert fs.check_geprif()[0] == "FALLA"


GWIS_XML = """<?xml version="1.0"?>
<WMS_Capabilities version="1.1.1"><Service><Name>WMS</Name></Service>
<Capability><Layer><Name>gwis</Name><Title>GWIS</Title>
<Layer><Name>ecmwf.fwi</Name><Title>FWI ECMWF</Title></Layer>
<Layer><Name>nrt.ba</Name><Title>Área quemada NRT</Title></Layer>
</Layer></Capability></WMS_Capabilities>"""

ONI_TABLA = """  SEAS   YR   TOTAL   ANOM
  DJF   1950   24.72   -1.6
  JFM   1950   24.60   -1.3
"""


@pytest.mark.parametrize(
    ("xml", "estado", "detalle"),
    [
        (GWIS_XML, "OK", ""),
        (GWIS_XML.replace("<Layer><Name>nrt.ba</Name><Title>Área quemada NRT</Title></Layer>", ""), "OJO", "nrt.ba"),
        ("el servidor respondió HTML <", "FALLA", ""),
    ],
    ids=["ok", "capa-renombrada", "no-es-xml"],
)
def test_veredicto_gwis(xml, estado, detalle):
    estado_real, detalle_real = fs.veredicto_gwis(xml)
    assert estado_real == estado
    if detalle:
        assert detalle in detalle_real


def test_gwis_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (0, "timed out"))
    assert fs.check_gwis()[0] == "FALLA"


@pytest.mark.parametrize(
    ("tabla", "estado"),
    [
        (ONI_TABLA, "OK"),
        ("  SEAS   YR   TOTAL   ANOM\n", "OJO"),
        # Si el CPC recorta columnas, ninguna fila de 4 campos calza y el chequeo avisa.
        ("DJF 1950 24.72\nJFM 1950 24.60\n", "OJO"),
    ],
    ids=["ok", "sin-filas", "falta-columna"],
)
def test_veredicto_oni(tabla, estado):
    assert fs.veredicto_oni(tabla)[0] == estado


def test_oni_no_responde(monkeypatch):
    monkeypatch.setattr(fs, "get", lambda url, n=600_000: (404, "Not Found"))
    assert fs.check_noaa_oni()[0] == "FALLA"


def _checks_con(*resultados):
    """CHECKS simulado: cada (estado, detalle) se repite como un chequeo con nombre propio."""
    return [(f"Fuente {i}", (lambda r=r: r)) for i, r in enumerate(resultados)]


@pytest.mark.parametrize(
    ("resultados", "args", "codigo", "marca"),
    [
        ([("OK", "bien"), ("OJO", "demora normal de la NOAA")], [], 0, "::warning::Fuente 1: demora normal de la NOAA"),
        ([("OK", "bien"), ("FALLA", "el encabezado cambió")], [], 1, "::error::Fuente 1"),
        ([("OK", "bien"), ("OJO", "demora normal")], ["--estricto"], 1, ""),
    ],
    ids=["ojo-no-rompe", "falla-rompe", "estricto-rompe-con-ojo"],
)
def test_estado_del_run(monkeypatch, capsys, resultados, args, codigo, marca):
    monkeypatch.setattr(fs, "CHECKS", _checks_con(*resultados))
    assert fs.main(args) == codigo
    if marca:
        assert marca in capsys.readouterr().out


def test_informe_markdown_una_fila_por_chequeo():
    filas = [fs.fila(nombre, "OK", "detalle") for nombre, _ in fs.CHECKS]
    md = fs.informe_markdown(filas)
    lineas = [linea for linea in md.splitlines() if linea.startswith("|")]
    assert len(lineas) == 2 + len(fs.CHECKS)
    assert f"**{len(fs.CHECKS)}/{len(fs.CHECKS)} fuentes OK**" in md


def test_que_hacer_nunca_queda_vacio():
    for nombre, _ in fs.CHECKS:
        assert fs.fila(nombre, "FALLA", "x")["que_hacer"]
    # Una fuente sin acción propia cae en el texto genérico que apunta al documento.
    assert "docs/FUENTES.md" in fs.fila("Fuente nueva", "FALLA", "x")["que_hacer"]


def test_json_imprime_las_filas(monkeypatch, capsys):
    monkeypatch.setattr(fs, "CHECKS", _checks_con(("OK", "bien")))
    assert fs.main(["--json"]) == 0
    filas = json.loads(capsys.readouterr().out)
    assert filas == [{"fuente": "Fuente 0", "estado": "OK", "detalle": "bien", "que_hacer": "revisar `docs/FUENTES.md` · Fuente 0"}]


def test_step_summary_recibe_el_informe(monkeypatch, tmp_path):
    destino = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(destino))
    monkeypatch.setattr(fs, "CHECKS", _checks_con(*[("OK", f"detalle {i}") for i in range(3)]))
    assert fs.main([]) == 0
    md = destino.read_text(encoding="utf-8")
    assert len([linea for linea in md.splitlines() if linea.startswith("|")]) == 2 + 3
    assert "**3/3 fuentes OK**" in md


# ---- AUTO-06: edad del dato por fuente ----

def test_edad_conaf_con_dos_fechas():
    ahora = fs.datetime(2026, 10, 23, 12, tzinfo=fs.timezone.utc)
    csv = "id,f_deteccion\n1,2026-10-23 10:00:00\n2,2026-10-22 08:00:00\n"
    assert fs.edad_conaf(csv, ahora) == 2.0


def test_edad_boton_rojo_ms():
    ahora = fs.datetime(2026, 10, 23, 12, tzinfo=fs.timezone.utc)
    cuerpo = json.dumps({"features": [{"attributes": {"date": 1792670400000}}]})  # 2026-10-22T12:00Z
    assert fs.edad_boton_rojo(cuerpo, ahora) == 24.0


def test_edad_dmc_pubdate():
    ahora = fs.datetime(2026, 10, 23, 12, tzinfo=fs.timezone.utc)
    rss = '<rss><channel><item><pubDate>Wed, 22 Oct 2026 09:00:00 +0000</pubDate></item></channel></rss>'
    assert fs.edad_dmc(rss, ahora) == 27.0


def test_edad_oni_trimestre():
    ahora = fs.datetime(2026, 10, 23, tzinfo=fs.timezone.utc)
    # JAS (jul-ago-sep) termina el 1 de octubre: el 23-10 tiene 22 días.
    assert fs.edad_oni("JJA 2026 26.9 -0.4\nJAS 2026 27.1 -0.5\n", ahora) == 22 * 24


def test_edad_ilegible_da_none():
    ahora = fs.datetime(2026, 10, 23, tzinfo=fs.timezone.utc)
    assert fs.edad_conaf("id,x\n1,\n", ahora) is None
    assert fs.edad_dmc("no es xml", ahora) is None


def test_con_umbral_sube_ojo_si_pasa_y_sin_fecha():
    assert fs.con_umbral("CONAF incendios", "OK", "d", 30.0) == ("OJO", "d; el dato más nuevo tiene 30 h (tope 24 h)")
    assert fs.con_umbral("CONAF incendios", "OK", "d", None) == ("OJO", "d; no se pudo fechar el dato")
    est, det = fs.con_umbral("CONAF incendios", "OK", "d", 5.0)
    assert est == "OK" and "edad 5.0 h" in det
    assert fs.con_umbral("CONAF incendios", "FALLA", "d", None) == ("FALLA", "d")
