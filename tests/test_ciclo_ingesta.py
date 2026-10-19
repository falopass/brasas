"""El ciclo de ingesta de punta a punta, con las cinco fuentes simuladas por `FakeWeb`.

`ingest_cycle` cubre solo la mitad satelital (FIRMS + GOES); el ciclo que corre el cron de
Cloudflare es `tick`, que además calcula FWI y riesgo (Open-Meteo), baja los avisos de la DMC,
los incendios informados por CONAF y el Botón Rojo. Aquí se verifica el contrato completo:

1. qué se guarda cuando todas las fuentes responden lo esperado;
2. que una fuente caída no corta a las demás;
3. que dos ciclos seguidos con la misma data no duplican nada;
4. que la purga de datos personales corre al final aunque no haya nada que borrar.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import h5py
import httpx
import numpy as np
import pytest

from backend.providers import conaf, dmc, firms, goes, weather
from tests.conftest import json_response
from tests.test_alert_recovery import place
from tests.test_conaf import CSV_HEAD, ROWS, fire_row
from tests.test_dmc import CAP, FEED
from tests.test_goes_ingest import key_for

CHILE_TZ = ZoneInfo("America/Santiago")
PROJ = goes.Projection(lon0=-75.0, h=35786023.0 + 6378137.0, r_eq=6378137.0, r_pol=6356752.31414)


def fdcf(fires: list[tuple[float, float, int]], at: datetime, size: int = 240) -> bytes:
    """HDF5 mínimo con la estructura real del producto FDCF, cubriendo Chile central.

    Igual que `test_goes.synthetic_fdc`, pero con la hora del barrido como parámetro: la
    retención del ciclo borra las detecciones de más de 45 días, así que el barrido simulado
    tiene que ser reciente para quedar guardado al terminar la prueba.
    """
    x_w, y_s = goes.latlon_to_scan(PROJ, -40.0, -76.0)
    x_e, y_n = goes.latlon_to_scan(PROJ, -28.0, -66.0)
    xs, ys = (x_e - x_w) / (size - 1), -(y_n - y_s) / (size - 1)
    mask = np.full((size, size), 100, dtype="int16")
    for lat, lon, code in fires:
        x, y = goes.latlon_to_scan(PROJ, lat, lon)
        mask[int(round((y - y_n) / ys)), int(round((x - x_w) / xs))] = code
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["time_coverage_start"] = np.bytes_(at.strftime("%Y-%m-%dT%H:%M:%S") + ".0Z")
        gp = f.create_dataset("goes_imager_projection", data=np.int32(0))
        gp.attrs["longitude_of_projection_origin"] = np.array([-75.0])
        gp.attrs["perspective_point_height"] = np.array([35786023.0])
        gp.attrs["semi_major_axis"] = np.array([6378137.0])
        gp.attrs["semi_minor_axis"] = np.array([6356752.31414])
        xd = f.create_dataset("x", data=np.arange(size, dtype="int16"))
        xd.attrs["scale_factor"], xd.attrs["add_offset"] = np.array([xs], "float32"), np.array([x_w], "float32")
        yd = f.create_dataset("y", data=np.arange(size, dtype="int16"))
        yd.attrs["scale_factor"], yd.attrs["add_offset"] = np.array([ys], "float32"), np.array([y_n], "float32")
        f.create_dataset("Mask", data=mask)
    return buf.getvalue()


def hourly(times: list[str], with_rain: bool) -> dict:
    """Serie horaria sintética, con las variables del FWI o las del 30-30-30 según corresponda."""
    data = {"time": times, "temperature_2m": [28.0] * len(times),
            "relative_humidity_2m": [35.0] * len(times), "wind_speed_10m": [18.0] * len(times)}
    if with_rain:
        data["precipitation"] = [0.0] * len(times)
    else:
        data["wind_gusts_10m"] = [30.0] * len(times)
        data["wind_direction_10m"] = [270.0] * len(times)
    return data


def open_meteo(request: httpx.Request) -> httpx.Response:
    """Una sola respuesta sintética para pronóstico, archivo ERA5 y condiciones actuales."""
    params = request.url.params
    if "current" in params:
        return json_response({"current": {"wind_speed_10m": 18.0, "wind_gusts_10m": 30.0,
                                          "wind_direction_10m": 270.0, "time": "2026-10-19T12:00"}})
    local = params.get("timezone") == "America/Santiago"
    base = datetime.now(CHILE_TZ if local else timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(-24, 72)]
    body = hourly(times, "precipitation" in params.get("hourly", ""))
    return json_response([{"hourly": body} for _ in range(len(params["latitude"].split(",")))])


@pytest.fixture
def providers(web, monkeypatch):
    """Las cinco fuentes del ciclo respondiendo lo esperado; sin red real ni esperas."""
    monkeypatch.setattr(weather, "FWI_PAUSE_S", 0)           # ~42 peticiones con pausa de 4 s
    monkeypatch.setattr(firms, "RETRY_DELAYS", (0.0, 0.0))   # los reintentos no esperan
    scan_at = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=10)
    key, content = key_for(scan_at), fdcf([(-33.10, -71.50, 10)], scan_at)
    fire_local = scan_at.astimezone(CHILE_TZ).strftime("%Y-%m-%d %H:%M")

    def s3(request: httpx.Request) -> httpx.Response:
        if "list-type" in request.url.params:
            return httpx.Response(200, text=f"<ListBucketResult><Contents><Key>{key}</Key>"
                                            "</Contents></ListBucketResult>")
        return httpx.Response(200, content=content)

    web.add(lambda r: "firms" in r.url.host,
            lambda r: httpx.Response(200, text="latitude,longitude,bright_ti4,acq_date,acq_time,"
                                     f"frp,confidence,daynight\n-33.05,-71.55,340.0,"
                                     f"{scan_at:%Y-%m-%d},{scan_at:%H%M},10.0,n,N\n"))
    web.add(lambda r: "noaa-goes" in r.url.host, s3)
    web.add(lambda r: "meteochile" in r.url.host and "rss.php" in r.url.path,
            lambda r: httpx.Response(200, text=FEED))
    web.add(lambda r: "meteochile" in r.url.host, lambda r: httpx.Response(200, content=CAP.encode()))
    web.add(lambda r: "githubusercontent" in r.url.host,
            lambda r: httpx.Response(200, text=CSV_HEAD + fire_row("1", "EL BELLOTO", "En combate",
                                                                 fire_local, -33.06, -71.40)))
    web.add(lambda r: "arcgis.com" in r.url.host,
            lambda r: json_response({"features": [{"attributes": row} for row in ROWS]}))
    web.add(lambda r: "open-meteo" in r.url.host, open_meteo)


def tick(svc) -> dict:
    return asyncio.run(svc.tick())


def counts(db) -> dict[str, int]:
    tables = ("observations", "official_fires", "dmc_alerts", "fwi_daily", "alerts", "incidents")
    return {t: db.one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in tables}


def test_the_full_cycle_stores_what_each_source_brought(providers, make_client):
    """Ciclo feliz: cada fuente deja sus filas y `ingest_runs` registra las pasadas."""
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        place(svc.db)
        result = tick(svc)
        assert result["firms_new"] == 2 and result["goes_new"] == 1
        assert result["failed_sources"] == [] and not any(k.endswith("_error") for k in result)
        assert result["official_fires"] == 1 and result["official_new"] == 1
        assert result["dmc_alerts"] == 1 and result["fwi_comunas"] > 0 and result["risk_comunas"] > 0
        db = svc.db
        assert db.one("SELECT COUNT(*) AS n FROM observations")["n"] == 3
        assert db.one("SELECT COUNT(*) AS n FROM official_fires")["n"] == 1
        assert db.one("SELECT COUNT(*) AS n FROM dmc_alerts")["n"] == 1
        assert db.one("SELECT COUNT(*) AS n FROM fwi_daily")["n"] > 0
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1
        runs = {(row["provider"], row["ok"]) for row in db.query("SELECT provider, ok FROM ingest_runs")}
        for provider in ("NASA FIRMS", "NOAA GOES", dmc.SOURCE, conaf.FIRES_SOURCE, conaf.SOURCE):
            assert (provider, 1) in runs


def test_a_source_down_does_not_stop_the_other_sources(providers, make_client, web):
    """FIRMS responde 503: el ciclo sigue y el fallo queda en `ingest_runs` con ok=0."""
    # La ruta feliz de FIRMS ya está registrada: esta va primero para ganarle.
    web.routes.insert(0, (lambda r: "firms" in r.url.host, lambda r: httpx.Response(503)))
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        result = tick(svc)
        assert result["firms_new"] == 0 and result["goes_new"] == 1
        failed = svc.db.one("SELECT ok, message FROM ingest_runs WHERE provider = 'NASA FIRMS'")
        assert failed["ok"] == 0 and failed["message"]
        # CONAF, DMC y Open-Meteo guardaron igual: una caída no corta el ciclo.
        assert svc.db.one("SELECT COUNT(*) AS n FROM observations")["n"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM official_fires")["n"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM dmc_alerts")["n"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM fwi_daily")["n"] > 0


def test_a_second_cycle_with_the_same_data_duplicates_nothing(providers, make_client):
    """Dos ciclos seguidos: ni observaciones, ni incendios oficiales, ni avisos repetidos."""
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        place(svc.db)
        tick(svc)
        before = counts(svc.db)
        second = tick(svc)
        assert second["firms_new"] == 0 and second["goes_new"] == 0
        assert second["official_new"] == 0 and second["official_alerts"] == 0
        assert counts(svc.db) == before


def test_purge_runs_at_the_end_of_the_cycle(providers, make_client):
    """La retención corre dentro del ciclo y no lanza aunque casi no haya nada que borrar."""
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        place(svc.db)
        # Un aviso de más de un año comprueba que la purga corrió de verdad: debe desaparecer.
        svc.db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, "
                       "upwind, lat, lon, observed_at, created_at, payload) VALUES ('p1','vieja','aviso',"
                       "1.0,0,0,-33.05,-71.55,'2025-09-01T00:00:00Z','2025-09-01T00:00:00Z','{}')")
        purges = []
        original = svc.purge_user_data

        async def spy():
            purges.append(await original())

        svc.purge_user_data = spy
        tick(svc)
        assert purges == [{"reports": 0, "alerts": 1, "photos": 0}]
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id = 'vieja'")["n"] == 0
