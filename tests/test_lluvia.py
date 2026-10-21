"""AGUA-03A: la peor ventana de 3 horas, la isoterma de su hora central y los huecos sin inventar."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

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


def test_isoterma_exactamente_en_el_umbral_es_alta():
    """La isoterma se informa alta desde 2500 m inclusive; se lee en la hora central."""
    s = lluvia.senal(hourly([0.0] * 5, isoterma=[1800.0, 2500.0, 1800.0, 1800.0, 1800.0]))
    assert s["isoterma_m"] == 2500.0 and s["isoterma_alta"] is True


def test_isoterma_un_metro_bajo_el_umbral_no_es_alta():
    s = lluvia.senal(hourly([0.0] * 5, isoterma=[1800.0, 2499.0, 1800.0, 1800.0, 1800.0]))
    assert s["isoterma_alta"] is False


def test_isoterma_alta_es_none_cuando_la_hora_central_no_trae_dato():
    s = lluvia.senal(
        {
            "time": ["2026-10-20T00:00", "2026-10-20T01:00", "2026-10-20T02:00"],
            "precipitation": [9.0, 9.0, 9.0],
            "freezing_level_height": [3000.0, None, 3000.0],
        }
    )
    assert s["isoterma_m"] is None and s["isoterma_alta"] is None


def test_horas_hasta_es_cero_si_la_ventana_ya_empezo():
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now="2026-10-20T01:00")
    assert s["ventana"] == "2026-10-20T01:00" and s["horas_hasta"] == 0
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now="2026-10-20T05:00")
    assert s["horas_hasta"] == 0, "una ventana que empezó antes nunca da negativo"


def test_horas_hasta_cuenta_las_horas_enteras_hasta_la_ventana():
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now="2026-10-19T19:00")
    assert s["horas_hasta"] == 6
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now=datetime(2026, 10, 19, 22, tzinfo=timezone.utc))
    assert s["horas_hasta"] == 3, "también acepta un datetime con zona"


def test_horas_hasta_es_none_sin_now_o_con_marca_ilegible():
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]))
    assert s["horas_hasta"] is None, "sin now no hay cuenta"
    s = lluvia.senal(hourly([0.0, 9.0, 9.0, 9.0, 0.0]), now="no es una fecha")
    assert s["horas_hasta"] is None, "una marca ilegible no se inventa"


def test_las_claves_originales_de_la_senal_no_cambiaron():
    """Regresión: mm_3h, isoterma_m, intensa y ventana conservan su valor."""
    s = lluvia.senal(hourly([0.0, 4.0, 5.0, 3.0, 1.0], isoterma=[2000.0, 2000.0, 2800.0, 2000.0, 2000.0]), now="2026-10-20T01:00")
    viejas = {k: s[k] for k in ("mm_3h", "isoterma_m", "intensa", "ventana")}
    assert viejas == {"mm_3h": 12.0, "isoterma_m": 2800.0, "intensa": True, "ventana": "2026-10-20T01:00"}


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
