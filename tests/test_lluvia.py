"""AGUA-03A: la peor ventana de 3 horas, la isoterma de su hora central y los huecos sin inventar."""
from __future__ import annotations

import asyncio

import httpx

from backend import lluvia
from backend.providers import weather
from tests.conftest import json_response


def hourly(precip: list, isoterma: list | None = None) -> dict:
    """Serie horaria sintética desde las 00:00 UTC; la isoterma es baja salvo que se indique."""
    n = len(precip)
    return {"time": [f"2026-10-20T{h:02d}:00" for h in range(n)],
            "precipitation": precip,
            "freezing_level_height": isoterma if isoterma is not None else [1800.0] * n}


def test_sin_lluvia_la_senal_queda_en_cero_y_no_intensa():
    s = lluvia.senal(hourly([0.0] * 8))
    assert s == {"mm_3h": 0.0, "isoterma_m": 1800.0, "intensa": False,
                 "ventana": "2026-10-20T00:00"}


def test_lluvia_intensa_con_isoterma_alta():
    """12 mm en la ventana 01-04 y la isoterma sobre 2500 m en su hora central."""
    precip = [0.0, 4.0, 5.0, 3.0, 1.0]
    s = lluvia.senal(hourly(precip, isoterma=[2000.0, 2000.0, 2800.0, 2000.0, 2000.0]))
    assert s["mm_3h"] == 12.0 and s["intensa"] is True
    assert s["ventana"] == "2026-10-20T01:00"
    assert s["isoterma_m"] == 2800.0, "la isoterma es la de la hora central de la ventana"
    assert s["isoterma_m"] >= lluvia.ISOTERMA_ALTA_M


def test_lluvia_moderada_no_es_intensa():
    s = lluvia.senal(hourly([0.0, 2.0, 2.0, 2.0, 0.0]))
    assert s["mm_3h"] == 6.0 and s["intensa"] is False
    assert s["ventana"] == "2026-10-20T01:00"


def test_series_incompletas_nunca_inventan_una_lectura():
    """Un None en la lluvia anula mm_3h; sin isoterma se informa solo ese hueco."""
    s = lluvia.senal(hourly([1.0, None, 2.0, 2.0, 1.0]))
    assert s == {"mm_3h": None, "isoterma_m": None, "intensa": False, "ventana": None}

    s = lluvia.senal({"time": [f"2026-10-20T{h:02d}:00" for h in range(4)],
                      "precipitation": [2.0, 4.0, 4.0, 2.0]})
    assert s["mm_3h"] == 10.0 and s["intensa"] is True
    assert s["isoterma_m"] is None and s["ventana"] == "2026-10-20T00:00", \
        "la ventana existe aunque la isoterma falte por completo"

    s = lluvia.senal({"time": ["2026-10-20T00:00", "2026-10-20T01:00", "2026-10-20T02:00"],
                      "precipitation": [9.0, 9.0, 9.0],
                      "freezing_level_height": [None, None, 3000.0]})
    assert s["isoterma_m"] is None, "la hora central sin dato se reporta, no se estima"


def test_forecast_hourly_suma_las_variables_extra_solo_a_esa_llamada():
    pedidas = []

    def handler(request):
        pedidas.append(request.url.params["hourly"])
        return json_response({"hourly": {}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await weather.forecast_hourly(http, [(-35.4, -71.6)],
                                          extra_vars=["precipitation", "freezing_level_height"])
            await weather.forecast_hourly(http, [(-35.4, -71.6)])

    asyncio.run(run())
    assert pedidas[0] == weather.HOURLY_VARS + ",precipitation,freezing_level_height"
    assert pedidas[1] == weather.HOURLY_VARS, "sin extra_vars el lote de las comunas no engorda"
