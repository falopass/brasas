"""AGUA-03A y AGUA-206: la peor ventana de 3 horas, su isoterma y el texto prudente para el vecino."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from backend import lluvia
from backend.providers import weather
from tests.conftest import json_response


def hourly(precip: list, isoterma: list | None = None) -> dict:
    """Serie horaria sintética desde las 00:00 UTC; la isoterma es baja salvo que se indique."""
    n = len(precip)
    return {
        "time": [f"2026-10-20T{h:02d}:00" for h in range(n)],
        "precipitation": precip,
        "freezing_level_height": isoterma if isoterma is not None else [1800.0] * n,
    }


def test_sin_lluvia_la_senal_queda_en_cero_y_no_intensa():
    s = lluvia.senal(hourly([0.0] * 8))
    assert s == {
        "mm_3h": 0.0,
        "isoterma_m": 1800.0,
        "isoterma_alta": False,
        "intensa": False,
        "ventana": "2026-10-20T00:00",
        "horas_hasta": None,
    }


@pytest.mark.parametrize("precip, isoterma, intensa, mm_3h", [
    ([0.0, 4.0, 5.0, 3.0, 1.0], [2000.0, 2000.0, 2800.0, 2000.0, 2000.0], True, 12.0),
    ([0.0, 2.0, 2.0, 2.0, 0.0], None, False, 6.0),
])
def test_la_ventana_de_tres_horas_mas_lluviosa_decide_el_umbral(precip, isoterma, intensa, mm_3h):
    """12 mm en la ventana 01-04 es intensa; 6 mm no. La isoterma se lee en la hora central."""
    s = lluvia.senal(hourly(precip, isoterma=isoterma))
    assert s["mm_3h"] == mm_3h and s["intensa"] is intensa
    assert s["ventana"] == "2026-10-20T01:00"
    if isoterma:
        assert s["isoterma_m"] == 2800.0
        assert s["isoterma_m"] >= lluvia.ISOTERMA_ALTA_M


def test_series_incompletas_nunca_inventan_una_lectura():
    """Un None en la lluvia anula mm_3h; sin isoterma se informa solo ese hueco."""
    s = lluvia.senal(hourly([1.0, None, 2.0, 2.0, 1.0]))
    assert s == {"mm_3h": None, "isoterma_m": None, "isoterma_alta": None, "intensa": False, "ventana": None, "horas_hasta": None}

    s = lluvia.senal({"time": [f"2026-10-20T{h:02d}:00" for h in range(4)], "precipitation": [2.0, 4.0, 4.0, 2.0]})
    assert s["mm_3h"] == 10.0 and s["intensa"] is True
    assert s["isoterma_m"] is None and s["ventana"] == "2026-10-20T00:00", "la ventana existe aunque la isoterma falte por completo"

    s = lluvia.senal(
        {
            "time": ["2026-10-20T00:00", "2026-10-20T01:00", "2026-10-20T02:00"],
            "precipitation": [9.0, 9.0, 9.0],
            "freezing_level_height": [None, None, 3000.0],
        }
    )
    assert s["isoterma_m"] is None, "la hora central sin dato se reporta, no se estima"


@pytest.mark.parametrize("central, isoterma_m, alta", [
    (2500.0, 2500.0, True),    # el umbral es inclusivo: 2500 m ya es alta
    (2499.0, 2499.0, False),
    (None, None, None),        # la hora central sin dato se reporta, no se estima
])
def test_isoterma_umbral_y_hueco(central, isoterma_m, alta):
    s = lluvia.senal(hourly([0.0] * 5, isoterma=[1800.0, central, 1800.0, 1800.0, 1800.0]))
    assert s["isoterma_m"] == isoterma_m and s["isoterma_alta"] is alta


@pytest.mark.parametrize("now, esperado", [
    ("2026-10-20T01:00", 0),                                # la ventana ya empezó
    ("2026-10-20T05:00", 0),                                # una ventana pasada nunca da negativo
    ("2026-10-19T19:00", 6),                                # horas enteras hasta la ventana
    (datetime(2026, 10, 19, 22, tzinfo=timezone.utc), 3),   # también acepta un datetime con zona
    (None, None),                                           # sin now no hay cuenta
    ("no es una fecha", None),                              # una marca ilegible no se inventa
])
def test_horas_hasta_la_ventana(now, esperado):
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now=now)
    assert s["horas_hasta"] == esperado
    if esperado == 0:
        assert s["ventana"] == "2026-10-20T01:00"


def test_explicacion_seco_no_anuncia_lluvia_intensa():
    texto = lluvia.explicacion(4.0, 1800.0, 120)
    assert "No se espera lluvia intensa sobre el suelo quemado" in texto
    assert "4.0 mm en 3 horas" in texto
    assert "Estimación de BRASA" in texto and "SENAPRED" in texto


@pytest.mark.parametrize("isoterma, estado, cauce", [
    (1800.0, "baja", "no te ubiques en el cauce"),
    (2800.0, "alta", "no te ubiques en su cauce"),
])
def test_explicacion_intenso_segun_la_isoterma(isoterma, estado, cauce):
    texto = lluvia.explicacion(12.0, isoterma, 120)
    assert "Lluvia intensa sobre suelo quemado" in texto
    assert f"isoterma 0 °C está {estado}" in texto
    assert ("está alta" if estado == "baja" else "está baja") not in texto
    assert cauce in texto
    assert "Estimación de BRASA" in texto and "SENAPRED" in texto


def test_explicacion_sin_dato_de_lluvia_no_afirma_riesgo():
    texto = lluvia.explicacion(None, 3000.0, 120)
    assert "No hay pronóstico de lluvia" in texto
    assert "Lluvia intensa" not in texto


def test_explicacion_sin_isoterma_avisa_igual_por_la_lluvia():
    texto = lluvia.explicacion(12.0, None, 120)
    assert "es lluvia intensa" in texto
    assert "No hay dato de la isoterma 0 °C" in texto
    assert "no te ubiques en su cauce" in texto


def test_explicacion_usa_los_mismos_umbrales_que_la_senal():
    """El texto y `senal` comparten el borde: 10 mm y 2500 m inclusive."""
    seco = lluvia.explicacion(lluvia.MM_3H_INTENSA - 0.1, 1800.0, 10)
    justo = lluvia.explicacion(lluvia.MM_3H_INTENSA, 1800.0, 10)
    assert "No se espera lluvia intensa" in seco
    assert "Lluvia intensa sobre suelo quemado" in justo
    baja = lluvia.explicacion(12.0, lluvia.ISOTERMA_ALTA_M - 1, 10)
    alta = lluvia.explicacion(12.0, lluvia.ISOTERMA_ALTA_M, 10)
    assert "está baja" in baja and "está alta" in alta


def test_explicacion_fecha_del_incendio_es_contexto_no_umbral():
    dentro = lluvia.explicacion(12.0, 2800.0, 30)
    despues = lluvia.explicacion(12.0, 2800.0, 800)
    assert "hace 30 días" in dentro and "primer año" in dentro
    assert "hace 800 días" in despues and "más de un año" in despues
    assert "Lluvia intensa" in dentro and "Lluvia intensa" in despues, "la fecha no apaga la señal"
    assert "No consta la fecha del incendio" in lluvia.explicacion(12.0, 2800.0, None)


def test_explicacion_no_inventa_con_entradas_invalidas():
    texto = lluvia.explicacion(True, "alta", -3)
    assert "No hay pronóstico de lluvia" in texto
    assert "No consta la fecha del incendio" in texto
    assert "Estimación de BRASA" in texto and "SENAPRED" in texto


def test_forecast_hourly_suma_las_variables_extra_solo_a_esa_llamada():
    pedidas = []

    def handler(request):
        pedidas.append(request.url.params["hourly"])
        return json_response({"hourly": {}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await weather.forecast_hourly(http, [(-35.4, -71.6)], extra_vars=["precipitation", "freezing_level_height"])
            await weather.forecast_hourly(http, [(-35.4, -71.6)])

    asyncio.run(run())
    assert pedidas[0] == weather.HOURLY_VARS + ",precipitation,freezing_level_height"
    assert pedidas[1] == weather.HOURLY_VARS, "sin extra_vars el lote de las comunas no engorda"


# --- AGUA-09: la señal como dato del pronóstico en /api/climate/lluvia ---


def test_el_endpoint_devuelve_la_senal_del_punto_con_su_fuente(make_client, web):
    """`GET /api/climate/lluvia` sirve la señal ya calculada, con fuente y sin «predicción»."""
    def handler(request):
        assert "precipitation" in request.url.params["hourly"]
        assert "freezing_level_height" in request.url.params["hourly"]
        return json_response({"hourly": {
            "time": [f"2026-10-20T{h:02d}:00" for h in range(8)],
            "precipitation": [0.0, 4.0, 5.0, 3.0, 1.0, 0.0, 0.0, 0.0],
            "freezing_level_height": [1800.0] * 8,
        }})

    web.add(lambda r: "open-meteo" in r.url.host, handler)
    with make_client() as client:
        body = client.get("/api/climate/lluvia?lat=-35.4&lon=-71.6").json()
    s = body["senal"]
    assert s["mm_3h"] == 12.0 and s["intensa"] is True
    assert s["isoterma_m"] == 1800.0 and s["ventana"] == "2026-10-20T01:00"
    assert "Open-Meteo" in body["source"]
    assert "no es un aviso" in body["note"] and "predic" not in body["note"].lower()


def test_el_endpoint_no_inventa_la_senal_cuando_el_proveedor_cae(make_client, web):
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503, text="caído"))
    with make_client() as client:
        body = client.get("/api/climate/lluvia?lat=-35.4&lon=-71.6").json()
    assert body["senal"] is None and body["source"]


def test_el_endpoint_valida_las_coordenadas(make_client):
    with make_client() as client:
        assert client.get("/api/climate/lluvia?lat=91&lon=-71.6").status_code == 422
