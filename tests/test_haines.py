"""RISK-24: atmósfera del punto (Haines, déficit de vapor, suelo, CAPE) y modelo fijo del pronóstico."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend import incidents, risk
from backend.providers import weather
from backend.risk import CHILE_TZ
from tests.conftest import json_response
from tests.test_incidents import obs

FORECAST_HOST = "api.open-meteo.com"  # no usar `in`: el host del aire también termina así


# --- dewpoint_c ---


def test_dewpoint_con_humedad_100_es_la_temperatura():
    assert risk.dewpoint_c(18.0, 100.0) == pytest.approx(18.0, abs=1e-6)


def test_dewpoint_de_magnus_con_valores_conocidos():
    assert risk.dewpoint_c(20.0, 50.0) == pytest.approx(9.26, abs=0.05)
    assert risk.dewpoint_c(25.0, 30.0) == pytest.approx(6.22, abs=0.05)


@pytest.mark.parametrize(
    "temp, rh",
    [(None, 50.0), (20.0, None), (20.0, 0.0), (20.0, -5.0), (20.0, 100.1), (float("nan"), 50.0), (20.0, float("inf")), ("x", 50.0)],
)
def test_dewpoint_sin_dato_o_fuera_de_rango_es_none(temp, rh):
    assert risk.dewpoint_c(temp, rh) is None


# --- haines_index ---


def test_haines_muy_bajo_variante_media():
    h = risk.haines_index(20.0, 15.0, 80.0)
    assert h["index"] == 2 and h["level"] == "muy_bajo"
    assert h["variant"] == "media" and h["levels_hpa"] == "850-700"
    assert h["stability"] == 1 and h["moisture"] == 1
    assert h["lapse_c"] == 5.0 and h["dewpoint_depression_c"] == pytest.approx(3.6, abs=0.1)


def test_haines_bajo_y_moderado():
    low = risk.haines_index(20.0, 12.0, 50.0)  # A=8 -> 2, B=10,7 -> 2
    assert low["index"] == 4 and low["level"] == "bajo"
    moderate = risk.haines_index(25.0, 13.0, 60.0)  # A=12 -> 3, B=8,3 -> 2
    assert moderate["index"] == 5 and moderate["level"] == "moderado"


def test_haines_alto_variante_media():
    h = risk.haines_index(25.0, 13.0, 30.0)  # A=12 -> 3, B=18,8 -> 3
    assert h["index"] == 6 and h["level"] == "alto"
    assert h["stability"] == 3 and h["moisture"] == 3


def test_la_misma_atmosfera_puntua_distinto_en_altura():
    media = risk.haines_index(25.0, 13.0, 30.0, elevation_m=999.9)
    alta = risk.haines_index(25.0, 13.0, 30.0, elevation_m=1000.0)
    assert media["variant"] == "media" and media["index"] == 6
    # A=12 (<18 -> 1) y B=18,8 (<21 -> 2): los umbrales de 700-500 hPa son más exigentes
    assert alta["variant"] == "alta" and alta["levels_hpa"] == "700-500"
    assert alta["stability"] == 1 and alta["moisture"] == 2 and alta["index"] == 3 and alta["level"] == "muy_bajo"


def test_haines_umbrales_inclusivos_por_arriba():
    # A=6 exacto en la variante media sube a 2; A=18 exacto en la alta también.
    assert risk.haines_index(26.0, 20.0, 100.0)["stability"] == 2
    assert risk.haines_index(25.9, 20.0, 100.0)["stability"] == 1
    assert risk.haines_index(18.0, 0.0, 100.0, elevation_m=1500.0)["stability"] == 2
    assert risk.haines_index(17.9, 0.0, 100.0, elevation_m=1500.0)["stability"] == 1


@pytest.mark.parametrize(
    "args",
    [
        (None, 10.0, 50.0),
        (20.0, None, 50.0),
        (20.0, 10.0, None),
        (20.0, 10.0, 0.0),
        (20.0, 10.0, 120.0),
        (float("nan"), 10.0, 50.0),
        (20.0, float("inf"), 50.0),
    ],
)
def test_haines_con_datos_faltantes_o_invalidos_es_none(args):
    assert risk.haines_index(*args) is None


# --- evaluate_atmosphere ---

# 15-ene-2027 es horario de verano (UTC-3): el día local es 03:00Z del 15 a 03:00Z del 16.
NOW_VERANO = datetime(2027, 1, 15, 15, 0, tzinfo=timezone.utc)


def full_hourly() -> dict:
    return {
        "time": ["2027-01-15T02:00", "2027-01-15T12:00", "2027-01-15T18:00", "2027-01-16T05:00"],
        "vapour_pressure_deficit": [9.0, 1.5, 2.4, 9.9],
        "soil_moisture_0_to_1cm": [0.01, 0.20, 0.15, 0.001],
        "soil_moisture_0_to_7cm": [0.02, 0.25, 0.22, 0.002],
        "cape": [999.0, 100.0, 350.0, 5000.0],
        "temperature_850hPa": [40.0, 25.0, 25.0, 40.0],
        "temperature_700hPa": [20.0, 13.0, 20.0, 20.0],
        "temperature_500hPa": [-10.0, -5.0, -5.0, -10.0],
        "relative_humidity_850hPa": [10.0, 30.0, 30.0, 10.0],
        "relative_humidity_700hPa": [10.0, 30.0, 30.0, 10.0],
    }


def test_atmosfera_completa_usa_solo_el_dia_local_de_chile():
    out = risk.evaluate_atmosphere(full_hourly(), now=NOW_VERANO)
    assert out["vpd_kpa"] == 2.4
    assert out["soil_moisture_0_to_1cm"] == 0.15 and out["soil_moisture_0_to_7cm"] == 0.22
    assert out["cape_j_kg"] == 350.0
    assert out["haines"]["index"] == 6 and out["haines"]["variant"] == "media"
    assert out["observed_at"] == "2027-01-15T12:00:00Z"


def test_atmosfera_de_altura_usa_700_y_500_hpa():
    out = risk.evaluate_atmosphere(full_hourly(), elevation_m=2200.0, now=NOW_VERANO)
    # 12:00Z: A = 13 - (-5) = 18 -> 2, B = 17,2 -> 2 (índice 4); 18:00Z: A = 25 -> 3, B = 18,1 -> 2 (índice 5)
    assert out["haines"]["variant"] == "alta" and out["haines"]["levels_hpa"] == "700-500"
    assert out["haines"]["index"] == 5 and out["observed_at"] == "2027-01-15T18:00:00Z"


def test_atmosfera_respeta_utc_menos_4_en_invierno():
    hourly = {
        "time": ["2027-07-15T03:30", "2027-07-15T04:30"],  # 23:30 del 14 y 00:30 del 15 en Chile
        "vapour_pressure_deficit": [8.0, 0.4],
    }
    now = datetime(2027, 7, 15, 10, 0, tzinfo=timezone.utc)
    out = risk.evaluate_atmosphere(hourly, now=now)
    assert out["vpd_kpa"] == 0.4 and out["observed_at"] == "2027-07-15T04:30:00Z"


def test_atmosfera_sin_horas_del_dia_usa_las_validas_de_la_serie():
    out = risk.evaluate_atmosphere(full_hourly(), now=datetime(2027, 3, 1, tzinfo=timezone.utc))
    assert out["vpd_kpa"] == 9.9 and out["cape_j_kg"] == 5000.0
    assert out["soil_moisture_0_to_1cm"] == 0.001


def test_atmosfera_sin_niveles_de_presion_conserva_la_superficie():
    hourly = {k: v for k, v in full_hourly().items() if "hPa" not in k}
    out = risk.evaluate_atmosphere(hourly, now=NOW_VERANO)
    assert out["haines"] is None
    assert out["vpd_kpa"] == 2.4 and out["cape_j_kg"] == 350.0
    assert out["observed_at"] == "2027-01-15T18:00:00Z"  # la hora del máximo de VPD


def test_atmosfera_con_un_nivel_incompleto_no_inventa_haines():
    hourly = full_hourly() | {"relative_humidity_850hPa": [None, None, None, None]}
    out = risk.evaluate_atmosphere(hourly, now=NOW_VERANO)
    assert out["haines"] is None and out["vpd_kpa"] == 2.4


def test_atmosfera_sin_ninguna_metrica_es_none():
    assert risk.evaluate_atmosphere({}, now=NOW_VERANO) is None
    assert risk.evaluate_atmosphere({"time": ["2027-01-15T12:00"]}, now=NOW_VERANO) is None
    vacio = {"time": ["2027-01-15T12:00"], "vapour_pressure_deficit": [None], "cape": [float("nan")]}
    assert risk.evaluate_atmosphere(vacio, now=NOW_VERANO) is None
    assert risk.evaluate_atmosphere({"time": ["no-es-fecha"], "cape": [10.0]}, now=NOW_VERANO) is None


def test_atmosfera_ignora_valores_no_finitos():
    hourly = {"time": ["2027-01-15T12:00", "2027-01-15T13:00"], "cape": [math.inf, 120.0]}
    assert risk.evaluate_atmosphere(hourly, now=NOW_VERANO)["cape_j_kg"] == 120.0


# --- forecast_hourly y el modelo ---


def run_forecast(points, **kwargs):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        n = request.url.params["latitude"].count(",") + 1
        return json_response([{"hourly": {}} for _ in range(n)])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await weather.forecast_hourly(http, points, **kwargs)

    out = asyncio.run(run())
    return seen, out


def test_forecast_hourly_pide_ecmwf_por_defecto():
    seen, _ = run_forecast([(-35.4, -71.6)])
    assert weather.DEFAULT_MODEL == "ecmwf_ifs025"
    assert seen[0].url.params["models"] == "ecmwf_ifs025"


def test_forecast_hourly_acepta_otro_modelo_y_lo_omite_si_es_vacio():
    seen, _ = run_forecast([(-35.4, -71.6)], models="gfs_seamless")
    assert seen[0].url.params["models"] == "gfs_seamless"
    for empty in (None, ""):
        seen, _ = run_forecast([(-35.4, -71.6)], models=empty)
        assert "models" not in seen[0].url.params


def test_forecast_hourly_con_lotes_envia_el_modelo_en_cada_uno_y_conserva_el_orden():
    points = [(-30.0 - i / 100, -71.0) for i in range(120)]
    seen, out = run_forecast(points)
    assert len(seen) == 3 and len(out) == 120
    assert all(r.url.params["models"] == "ecmwf_ifs025" for r in seen)


def test_las_variables_de_atmosfera_se_suman_a_las_horarias():
    seen, _ = run_forecast([(-35.4, -71.6)], extra_vars=weather.ATMOS_EXTRA_VARS)
    hourly = seen[0].url.params["hourly"].split(",")
    assert hourly[: len(weather.HOURLY_VARS.split(","))] == weather.HOURLY_VARS.split(",")
    assert {"vapour_pressure_deficit", "cape", "temperature_500hPa", "relative_humidity_700hPa"} <= set(hourly)


# --- endpoints ---


def noon_utc() -> str:
    local = datetime.now(CHILE_TZ).replace(hour=12, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def atmos_response(request: httpx.Request) -> httpx.Response:
    return json_response(
        {
            "hourly": {
                "time": [noon_utc()],
                "vapour_pressure_deficit": [2.1],
                "soil_moisture_0_to_1cm": [0.11],
                "soil_moisture_0_to_7cm": [0.14],
                "cape": [240.0],
                "temperature_850hPa": [25.0],
                "temperature_700hPa": [13.0],
                "temperature_500hPa": [-5.0],
                "relative_humidity_850hPa": [30.0],
                "relative_humidity_700hPa": [30.0],
            }
        }
    )


def forecast_requests(web) -> list[httpx.Request]:
    return [r for r in web.requests if r.url.host == FORECAST_HOST]


def test_risk_comuna_publica_la_atmosfera(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client() as client:
        body = client.get("/api/risk/5109").json()
    atmos = body["atmosphere"]
    assert atmos["vpd_kpa"] == 2.1 and atmos["cape_j_kg"] == 240.0
    assert atmos["soil_moisture_0_to_1cm"] == 0.11 and atmos["soil_moisture_0_to_7cm"] == 0.14
    assert atmos["haines"]["index"] == 6
    assert atmos["model"] == "ecmwf_ifs025" and atmos["fetched_at"]
    assert atmos["source"] == {"name": "Open-Meteo · ECMWF IFS", "url": "https://open-meteo.com/en/docs"}
    params = forecast_requests(web)[0].url.params
    assert params["models"] == "ecmwf_ifs025" and "vapour_pressure_deficit" in params["hourly"]
    assert params["forecast_days"] == "2" and params["latitude"].count(",") == 0


def test_la_atmosfera_se_cachea_y_la_ficha_de_comuna_la_lee_sin_red(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client(GOES_ENABLED="0") as client:
        first = client.get("/api/risk/5109").json()["atmosphere"]
        second = client.get("/api/risk/5109").json()["atmosphere"]
        ficha = client.get("/api/comuna/5109").json()["atmosphere"]
    assert len(forecast_requests(web)) == 1 and first == second
    assert ficha == first and ficha["haines"]["index"] == 6


def test_la_ficha_de_comuna_sin_cache_no_sale_a_la_red(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client(GOES_ENABLED="0") as client:
        assert client.get("/api/comuna/5109").json()["atmosphere"] is None
    assert forecast_requests(web) == []


def test_la_ficha_de_comuna_expone_la_atmosfera_guardada(make_client):
    fresh_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    today_cl = datetime.now(CHILE_TZ).date().isoformat()
    saved = {
        "date": today_cl,
        "vpd_kpa": 1.2,
        "haines": None,
        "fetched_at": fresh_at,
        "source": {"name": "Open-Meteo · ECMWF IFS"},
    }
    with make_client(GOES_ENABLED="0") as client:
        client.app.state.services.db.kv_set("atmos:comuna:5109", json.dumps(saved))
        body = client.get("/api/comuna/5109").json()
    assert body["atmosphere"] == saved


def test_la_ficha_de_comuna_descarta_una_atmosfera_vencida(make_client):
    stale_at = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = {"vpd_kpa": 1.2, "haines": None, "fetched_at": stale_at, "source": {"name": "Open-Meteo · ECMWF IFS"}}
    with make_client(GOES_ENABLED="0") as client:
        client.app.state.services.db.kv_set("atmos:comuna:5109", json.dumps(saved))
        assert client.get("/api/comuna/5109").json()["atmosphere"] is None


def test_la_atmosfera_vence_al_cambiar_de_dia_en_chile(make_client, web):
    yesterday_cl = (datetime.now(CHILE_TZ).date() - timedelta(days=1)).isoformat()
    recent_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = {"date": yesterday_cl, "vpd_kpa": 0.4, "haines": None, "fetched_at": recent_at}
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client(GOES_ENABLED="0") as client:
        client.app.state.services.db.kv_set("atmos:comuna:5109", json.dumps(saved))
        assert client.get("/api/comuna/5109").json()["atmosphere"] is None
        fresh = client.get("/api/risk/5109").json()["atmosphere"]
    assert fresh["vpd_kpa"] == 2.1 and fresh["date"] == datetime.now(CHILE_TZ).date().isoformat()
    assert len(forecast_requests(web)) == 1


def test_la_ficha_de_comuna_ignora_una_atmosfera_ilegible(make_client):
    with make_client(GOES_ENABLED="0") as client:
        client.app.state.services.db.kv_set("atmos:comuna:5109", "{no es json")
        assert client.get("/api/comuna/5109").json()["atmosphere"] is None


def test_risk_comuna_degrada_a_none_si_el_proveedor_falla(make_client):
    with make_client() as client:  # sin ruta simulada: Open-Meteo responde 503
        response = client.get("/api/risk/5109")
    assert response.status_code == 200
    assert response.json()["atmosphere"] is None and response.json()["comuna"]["code"] == 5109


def test_un_fallo_no_se_reintenta_en_cada_visita(make_client, web):
    with make_client() as client:
        client.get("/api/risk/5109")
        client.get("/api/risk/5109")
    assert len(forecast_requests(web)) == 1


def test_sin_cupo_de_open_meteo_no_se_consulta_la_atmosfera(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client() as client:
        db = client.app.state.services.db
        today = datetime.now(CHILE_TZ).date().isoformat()
        db.kv_set("open_meteo_day", json.dumps({"date": today, "total": weather.DAILY_LOCATIONS_CAP, "tasks": {}}))
        assert client.get("/api/risk/5109").json()["atmosphere"] is None
    assert forecast_requests(web) == []


def test_el_cupo_de_open_meteo_registra_la_atmosfera(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client() as client:
        client.get("/api/risk/5109")
        day = client.app.state.services.open_meteo_day()
    assert day["tasks"]["atmos"]["today"] == 2


def test_detalle_de_incidente_publica_la_atmosfera(make_client, web):
    web.add(lambda r: r.url.host == FORECAST_HOST, atmos_response)
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8, when=now)], now)
        body = client.get(f"/api/incidents/{inc['id']}").json()
        assert body["atmosphere"]["haines"]["index"] == 6
        assert db.kv_get(f"atmos:inc:{inc['id']}")
    params = forecast_requests(web)[0].url.params
    assert params["latitude"] == f"{inc['lat']:.4f}" and params["longitude"] == f"{inc['lon']:.4f}"


def test_detalle_de_incidente_degrada_a_none_si_el_proveedor_falla(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8, when=now)], now)
        response = client.get(f"/api/incidents/{inc['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["atmosphere"] is None and body["incident"]["id"] == inc["id"]


def test_detalle_de_incidente_inexistente_sigue_siendo_404(make_client):
    with make_client() as client:
        assert client.get("/api/incidents/ffffffffffff").status_code == 404


def test_elevacion_cordillerana_activa_variante_alta_de_haines(make_client, web):
    def high_response(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "elevation": 1850.0,
                "hourly": {
                    "time": [noon_utc()],
                    "vapour_pressure_deficit": [1.8],
                    "temperature_850hPa": [25.0],
                    "temperature_700hPa": [14.0],
                    "temperature_500hPa": [-10.0],
                    "relative_humidity_850hPa": [30.0],
                    "relative_humidity_700hPa": [20.0],
                },
            }
        )

    web.add(lambda r: r.url.host == FORECAST_HOST, high_response)
    with make_client() as client:
        atmos = client.get("/api/risk/5109").json()["atmosphere"]
    assert atmos["haines"]["variant"] == "alta"
    assert atmos["haines"]["levels_hpa"] == "700-500"
    assert atmos["haines"]["index"] == 6

