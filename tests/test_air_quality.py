"""AGUA-05: aire pronosticado (CAMS vía Open-Meteo Air Quality) en la ficha de comuna."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend import risk
from backend.providers import weather
from backend.risk import CHILE_TZ
from backend.routes import public
from tests.conftest import json_response


def local_stamp(day_offset: int, hour: int = 12) -> str:
    """Una hora del día local de Chile (hoy + `day_offset`) expresada en UTC, como la devuelve la API."""
    local = datetime.now(CHILE_TZ).replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def series(*pairs: tuple) -> dict:
    """Serie ya normalizada por `air_quality` ({time, pm25}), para probar `air_daily_max`."""
    return {"time": [t for t, _ in pairs], "pm25": [v for _, v in pairs]}


def air_payload(*pairs: tuple) -> httpx.Response:
    """Respuesta cruda de la API con las variables CAMS que pide `air_quality`."""
    times = [t for t, _ in pairs]
    pm25 = [v for _, v in pairs]
    return json_response({
        "hourly": {
            "time": times,
            "pm2_5": pm25,
            "pm10": [None if v is None else v + 5 for v in pm25],
            "carbon_monoxide": [None if v is None else v * 10 for v in pm25],
            "aerosol_optical_depth": [None if v is None else v / 100 for v in pm25],
            "dust": [None if v is None else v / 2 for v in pm25],
        }
    })


def test_air_quality_pide_variables_cams_global_de_hoy_y_manana_en_utc():
    seen = []

    async def run():
        transport = httpx.MockTransport(
            lambda r: seen.append(r) or json_response({"hourly": {
                "time": ["2026-10-19T12:00"],
                "pm2_5": [12.3], "pm10": [13.3], "carbon_monoxide": [123.0],
                "aerosol_optical_depth": [0.12], "dust": [1.5],
            }}))
        async with httpx.AsyncClient(transport=transport) as http:
            return await weather.air_quality(http, -35.4, -71.6)

    out = asyncio.run(run())
    assert out["pm25"] == [12.3] and out["pm10"] == [13.3] and out["co"] == [123.0]
    assert out["aod"] == [0.12] and out["dust"] == [1.5]
    params = seen[0].url.params
    assert seen[0].url.host == "air-quality-api.open-meteo.com"
    assert params["hourly"] == weather.AIR_VARS and params["forecast_days"] == "2"
    assert params["timezone"] == "GMT" and params["domains"] == "cams_global"


def test_air_daily_max_agrupa_por_dia_local_no_utc():
    # El cruce de medianoche: las 02:30 UTC del 20 de octubre son las 23:30 del 19 en Chile (UTC-3).
    out = weather.air_daily_max(series(
        ("2026-10-19T10:00", 5.0),   # 07:00 Chile del 19
        ("2026-10-20T02:30", 18.0),  # 23:30 Chile del 19: sigue siendo «hoy»
        ("2026-10-20T04:00", 9.5),   # 01:00 Chile del 20
        ("2026-10-20T10:00", None),  # sin dato no mueve el máximo
    ))
    assert out == {"2026-10-19": 18.0, "2026-10-20": 9.5}


def test_air_daily_max_acepta_otra_variable():
    out = weather.air_daily_max({"time": ["2026-10-19T10:00", "2026-10-20T10:00"], "pm10": [7.0, 9.0]}, "pm10")
    assert out == {"2026-10-19": 7.0, "2026-10-20": 9.0}


def test_risk_comuna_publica_el_aire(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host,
            lambda r: air_payload((local_stamp(0, 9), 11.0), (local_stamp(0, 18), 22.5), (local_stamp(1), 8.0)))
    with make_client() as client:
        air = client.get("/api/risk/5109").json()["air"]
    assert air["pm25_today_max"] == 22.5 and air["pm25_tomorrow_max"] == 8.0
    assert air["pm10_today_max"] == 27.5 and air["pm10_tomorrow_max"] == 13.0
    assert air["co_today_max"] == 225.0 and air["co_tomorrow_max"] == 80.0
    assert air["aod_today_max"] == pytest.approx(0.225) and air["aod_tomorrow_max"] == pytest.approx(0.08)
    assert air["dust_today_max"] == 11.25 and air["dust_tomorrow_max"] == 4.0
    assert air["unit"] == "µg/m³"
    assert air["units"] == {"pm25": "µg/m³", "pm10": "µg/m³", "co": "µg/m³", "aod": "adimensional", "dust": "µg/m³"}
    assert air["source"]["name"] == "CAMS vía Open-Meteo" and air["source"]["url"]
    assert air["guideline"]["pm25_24h"] == 15
    assert air["fetched_at"]


def test_risk_comuna_sin_aire_cuando_el_proveedor_falla(make_client, monkeypatch):
    async def boom(client, lat, lon):
        raise weather.WeatherError("sin servicio")

    monkeypatch.setattr(weather, "air_quality", boom)
    with make_client() as client:
        response = client.get("/api/risk/5109")
    assert response.status_code == 200
    assert response.json()["air"] is None


def test_el_aire_se_cachea_tres_horas_por_comuna(make_client, web):
    calls = []
    web.add(lambda r: "air-quality" in r.url.host,
            lambda r: calls.append(r) or air_payload((local_stamp(0), 7.0)))
    with make_client() as client:
        first = client.get("/api/risk/5109").json()["air"]
        second = client.get("/api/risk/5109").json()["air"]
    assert len(calls) == 1 and first == second and first["pm25_today_max"] == 7.0


# --- RISK-25: lotes de aire y señal humo/polvo ---


def run_air_batch(points, handler):
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(wrapped)) as http:
            return await weather.air_quality_batch(http, points)

    return seen, asyncio.run(run())


def echo_latitudes(request: httpx.Request) -> httpx.Response:
    """Un elemento por ubicación pedida, con la latitud como MP2,5 para comprobar el orden."""
    lats = [float(v) for v in request.url.params["latitude"].split(",")]
    items = [{"hourly": {"time": ["2026-10-19T12:00"], "pm2_5": [-lat], "pm10": [1.0], "carbon_monoxide": [2.0],
                         "aerosol_optical_depth": [0.1], "dust": [0.5]}} for lat in lats]
    return json_response(items)


def test_air_quality_batch_parte_en_lotes_de_50_y_conserva_el_orden():
    points = [(-30.0 - i / 100, -71.0) for i in range(120)]
    seen, out = run_air_batch(points, echo_latitudes)
    assert [r.url.params["latitude"].count(",") + 1 for r in seen] == [50, 50, 20]
    assert len(out) == 120
    assert [row["pm25"][0] for row in out] == pytest.approx([30.0 + i / 100 for i in range(120)])
    params = seen[0].url.params
    assert seen[0].url.host == "air-quality-api.open-meteo.com"
    assert params["hourly"] == weather.AIR_VARS and params["forecast_days"] == "2"
    assert params["timezone"] == "GMT" and params["domains"] == "cams_global"
    assert out[0].keys() == {"time", "pm25", "pm10", "co", "aod", "dust"}
    assert out[0]["pm10"] == [1.0] and out[0]["co"] == [2.0] and out[0]["aod"] == [0.1] and out[0]["dust"] == [0.5]


def test_air_quality_batch_con_un_punto_acepta_la_respuesta_como_objeto():
    seen, out = run_air_batch([(-35.4, -71.6)], lambda r: json_response(
        {"hourly": {"time": ["2026-10-19T12:00"], "pm2_5": [12.3], "pm10": [13.3], "carbon_monoxide": [123.0],
                    "aerosol_optical_depth": [0.12], "dust": [1.5]}}))
    assert len(seen) == 1 and seen[0].url.params["latitude"] == "-35.4000" and seen[0].url.params["longitude"] == "-71.6000"
    assert out == [{"time": ["2026-10-19T12:00"], "pm25": [12.3], "pm10": [13.3], "co": [123.0], "aod": [0.12], "dust": [1.5]}]


def test_air_quality_batch_sin_horario_devuelve_series_vacias_y_sin_puntos_no_llama():
    _, out = run_air_batch([(-35.4, -71.6)], lambda r: json_response({}))
    assert out == [{"time": [], "pm25": [], "pm10": [], "co": [], "aod": [], "dust": []}]
    seen, out = run_air_batch([], echo_latitudes)
    assert seen == [] and out == []


def test_air_quality_batch_rechaza_un_numero_inesperado_de_ubicaciones():
    with pytest.raises(weather.WeatherError):
        run_air_batch([(-35.4, -71.6), (-36.0, -72.0)], lambda r: json_response([{"hourly": {}}]))


def test_air_quality_batch_no_devuelve_una_lista_mas_corta_si_un_lote_falla():
    calls = []

    def handler(request):
        calls.append(request)
        return echo_latitudes(request) if len(calls) == 1 else httpx.Response(500, text="falla")

    with pytest.raises(weather.WeatherError):
        run_air_batch([(-30.0 - i / 100, -71.0) for i in range(60)], handler)


@pytest.mark.parametrize(
    "pm25, pm10, co, dust, expected",
    [
        (40.0, 45.0, 120.0, 5.0, "humo"),  # fracción fina dominante
        (30.0, 200.0, 450.0, None, "humo"),  # CO alto aunque el MP10 sea grueso
        (25.0, 40.0, None, 10.0, "humo"),  # 25 µg/m³ exactos y 0,625 de fracción fina
        (30.0, 40.0, 100.0, 60.0, "polvo"),  # con polvo mineral alto no es humo
        (10.0, 100.0, 100.0, 10.0, "polvo"),  # MP10 grueso: 0,1 de fracción fina
        (None, 90.0, None, None, "polvo"),
        (5.0, 20.0, 80.0, 55.0, "polvo"),
        (24.9, 30.0, 500.0, 0.0, None),  # bajo el umbral de MP2,5
        (30.0, 75.0, 100.0, 10.0, None),  # fracción 0,4 sin CO alto no es humo, y el MP10 no llega a 80
        (30.0, None, None, None, None),  # sin MP10 ni CO no hay cómo asegurar humo
        (None, None, None, None, None),
        (float("nan"), float("inf"), float("nan"), float("nan"), None),
    ],
)
def test_classify_air_signal(pm25, pm10, co, dust, expected):
    assert risk.classify_air_signal(pm25, pm10, co, dust) == expected


def test_classify_air_signal_con_pm10_cero_no_divide():
    assert risk.classify_air_signal(30.0, 0.0, None, None) is None
    assert risk.classify_air_signal(30.0, 0.0, 400.0, None) == "humo"


def test_summarize_air_series_agrega_senal_y_conserva_las_claves():
    day = datetime.now(CHILE_TZ).replace(hour=15, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    stamp = day.strftime("%Y-%m-%dT%H:%M")
    out = public.summarize_air_series(
        {"time": [stamp], "pm25": [40.0], "pm10": [45.0], "co": [120.0], "aod": [0.3], "dust": [5.0]}, now=day
    )
    assert out["signal"] == "humo"
    assert out["pm25_today_max"] == 40.0 and out["pm25_tomorrow_max"] is None
    assert {"pm10_today_max", "co_today_max", "aod_today_max", "dust_today_max"} <= set(out)
    assert not any(key.endswith("_tomorrow_max") and key != "pm25_tomorrow_max" for key in out)
    assert {"unit", "units", "source", "guideline", "fetched_at"} <= set(out)
    assert public.summarize_air_series({"time": [stamp], "pm25": [None]}, now=day) is None
    assert public.summarize_air_series({}, now=day) is None


def test_summarize_air_series_usa_el_dia_local_del_now_dado():
    # 03:30Z del 15-jul-2027 es 23:30 del 14 en Chile (UTC-4): para el 14 es «hoy».
    out = public.summarize_air_series(
        {"time": ["2027-07-15T03:30", "2027-07-15T14:00"], "pm25": [10.0, 33.0]},
        now=datetime(2027, 7, 14, 20, 0, tzinfo=timezone.utc),
    )
    assert out["pm25_today_max"] == 10.0 and out["pm25_tomorrow_max"] == 33.0


def custom_air(pm25: float, pm10: float, co: float, dust: float) -> httpx.Response:
    return json_response({"hourly": {
        "time": [local_stamp(0)], "pm2_5": [pm25], "pm10": [pm10], "carbon_monoxide": [co],
        "aerosol_optical_depth": [0.2], "dust": [dust],
    }})


def test_risk_comuna_publica_la_senal_de_humo(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host, lambda r: custom_air(40.0, 45.0, 400.0, 5.0))
    with make_client() as client:
        assert client.get("/api/risk/5109").json()["air"]["signal"] == "humo"


def test_risk_comuna_publica_la_senal_de_polvo(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host, lambda r: custom_air(10.0, 90.0, 100.0, 60.0))
    with make_client() as client:
        assert client.get("/api/risk/5109").json()["air"]["signal"] == "polvo"


def test_risk_comuna_sin_senal_cuando_el_aire_es_limpio(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host, lambda r: custom_air(8.0, 12.0, 90.0, 2.0))
    with make_client() as client:
        air = client.get("/api/risk/5109").json()["air"]
    assert "signal" in air and air["signal"] is None


def stored_air(hours_ago: float, **extra) -> str:
    fetched = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps({"pm25_today_max": 40.0, "pm25_tomorrow_max": None, "pm10_today_max": 45.0,
                       "co_today_max": 410.0, "fetched_at": fetched, **extra})


def test_una_cache_de_aire_anterior_recibe_la_senal(make_client, web):
    with make_client() as client:
        client.app.state.services.db.kv_set("air:5109", stored_air(1))
        air = client.get("/api/risk/5109").json()["air"]
    assert air["signal"] == "humo" and air["units"]["pm25"] == "µg/m³"
    assert [r for r in web.requests if "air-quality" in r.url.host] == []


def test_el_aire_dura_seis_horas_en_cache(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host, lambda r: air_payload((local_stamp(0), 7.0)))
    assert public.AIR_TTL_S == 6 * 3600
    with make_client() as client:
        db = client.app.state.services.db
        db.kv_set("air:5109", stored_air(5.5))
        assert client.get("/api/risk/5109").json()["air"]["pm25_today_max"] == 40.0
        assert [r for r in web.requests if "air-quality" in r.url.host] == []
        db.kv_set("air:5109", stored_air(6.5))
        assert client.get("/api/risk/5109").json()["air"]["pm25_today_max"] == 7.0


def test_air_cycle_refresca_comunas_en_lotes_y_alimenta_cache(make_client, web, monkeypatch):
    """RISK-25: el ciclo en lotes cubre todas las comunas de a 50 y deja `air:{code}` con señal."""
    stamp_now = local_stamp(0)

    def batch_handler(request: httpx.Request) -> httpx.Response:
        n = request.url.params["latitude"].count(",") + 1
        item = {
            "hourly": {
                "time": [stamp_now],
                "pm2_5": [38.0],
                "pm10": [44.0],
                "carbon_monoxide": [450.0],
                "aerosol_optical_depth": [0.6],
                "dust": [4.0],
            }
        }
        return json_response(item if n == 1 else [item for _ in range(n)])

    web.add(lambda r: "air-quality" in r.url.host, batch_handler)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda: 0)
        out = asyncio.run(svc.air_cycle())
        reqs = [r for r in web.requests if "air-quality" in r.url.host]
        assert out["comunas"] > 300
        assert len(reqs) == (out["comunas"] + weather.BATCH_SIZE - 1) // weather.BATCH_SIZE
        assert all(r.url.params["domains"] == "cams_global" for r in reqs)
        assert all(r.url.params["latitude"].count(",") + 1 <= weather.BATCH_SIZE for r in reqs)
        # Verifica orden (lat, lon): todas las latitudes y longitudes caen dentro del territorio chileno.
        lats = [float(v) for r in reqs for v in r.url.params["latitude"].split(",")]
        lons = [float(v) for r in reqs for v in r.url.params["longitude"].split(",")]
        assert all(-56.5 <= la <= -17.0 for la in lats)
        assert all(-110.0 <= lo <= -66.0 for lo in lons)
        assert svc.db.kv_get("air_batch_at")
        assert svc.open_meteo_day()["tasks"]["air_batch"]["today"] == out["comunas"]
        # La ficha sirve desde la caché del lote sin volver a salir a la red.
        air = client.get("/api/risk/5109").json()["air"]
        assert air["pm25_today_max"] == 38.0 and air["signal"] == "humo"
        assert len([r for r in web.requests if "air-quality" in r.url.host]) == len(reqs)


def test_la_cache_de_aire_caduca_al_cambiar_el_dia_de_chile(make_client, web):
    """RISK-25: tras medianoche en Chile no se sirve el resumen de ayer como si fuera hoy."""
    yesterday = (datetime.now(CHILE_TZ).date() - timedelta(days=1)).isoformat()
    web.add(lambda r: "air-quality" in r.url.host, lambda r: air_payload((local_stamp(0), 11.0)))
    with make_client() as client:
        client.app.state.services.db.kv_set("air:5109", stored_air(1.0, date=yesterday))
        air = client.get("/api/risk/5109").json()["air"]
    assert air["pm25_today_max"] == 11.0 and air["date"] == datetime.now(CHILE_TZ).date().isoformat()
    assert len([r for r in web.requests if "air-quality" in r.url.host]) == 1


def test_air_cycle_cede_cuando_el_cupo_no_alcanza(make_client, web):
    """RISK-25: si el cupo restante no cubre las comunas, cede sin hacer llamadas HTTP."""
    web.add(lambda r: "air-quality" in r.url.host, lambda r: custom_air(30.0, 40.0, 400.0, 5.0))
    with make_client() as client:
        svc = client.app.state.services
        today = datetime.now(CHILE_TZ).date().isoformat()
        svc.db.kv_set("open_meteo_day", json.dumps({"date": today, "total": weather.DAILY_LOCATIONS_CAP, "tasks": {}}))
        out = asyncio.run(svc.air_cycle())
    assert out["skipped"] == "cupo"
    assert [r for r in web.requests if "air-quality" in r.url.host] == []

