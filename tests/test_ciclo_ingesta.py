"""El ciclo de ingesta de punta a punta, con las cinco fuentes simuladas por `FakeWeb`.

`ingest_cycle` cubre solo la mitad satelital (FIRMS + GOES + GLM); el ciclo que corre el cron de
Cloudflare es `tick`, que además calcula FWI y riesgo (Open-Meteo), baja los avisos de la DMC,
los incendios informados por CONAF y el Botón Rojo. Aquí se verifica el contrato completo:

1. qué se guarda cuando todas las fuentes responden lo esperado;
2. que una fuente caída no corta a las demás;
3. que dos ciclos seguidos con la misma data no duplican nada;
4. que la purga de datos personales corre al final aunque no haya nada que borrar.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend import services
from backend.providers import _retry, conaf, dmc, weather
from tests.conftest import json_response
from tests.test_alert_recovery import place
from tests.test_conaf import CSV_HEAD, ROWS, fire_row
from tests.test_dmc import CAP, FEED
from tests.test_goes import synthetic_fdc
from tests.test_goes_ingest import key_for

CHILE_TZ = ZoneInfo("America/Santiago")


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
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0.0, 0.0))  # los reintentos no esperan
    scan_at = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=10)
    key = key_for(scan_at)
    # La retención del ciclo borra las detecciones de más de 45 días: el barrido debe ser reciente.
    content = synthetic_fdc([(-33.10, -71.50, 10)], at=scan_at.strftime("%Y-%m-%dT%H:%M:%S") + ".0Z")
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


def test_a_second_cycle_with_the_same_data_duplicates_nothing(providers, make_client, monkeypatch):
    """Dos ciclos seguidos: ni observaciones, ni incendios oficiales, ni avisos repetidos."""
    monkeypatch.setattr(services, "FWI_COMUNAS_PER_RUN", 10_000)  # la pasada del FWI cabe en el primer ciclo
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


def test_fwi_y_lluvia_registran_su_corrida(providers, make_client):
    """FWI y lluvia son cálculos propios, pero su corrida queda en `ingest_runs`
    como la de los proveedores: así entran a `errors.by_product` (FWI-01)."""
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        tick(svc)
        runs = {row["product"]: row["ok"] for row in svc.db.query("SELECT product, ok FROM ingest_runs")}
        assert runs["FWI"] == 1 and runs["LLUVIA"] == 1


def test_un_ciclo_cortado_no_deja_el_error_del_ciclo_anterior(make_client):
    """FWI-PROD-01, como en producción: `BRASA_SCHEDULER=0` y el cron llama
    `/api/internal/tick?wait=1`. Si la petición se corta a mitad del ciclo (el contenedor se
    suspende), `/api/status` no puede seguir mostrando el `fwi_error` del ciclo anterior como
    si fuera el de ahora."""
    token = "internal-secret-1234567890"

    async def cortado():
        asyncio.current_task().cancel()  # el Worker corta la petición; el ciclo no alcanza a cerrar
        await asyncio.sleep(0)
        return {}

    with make_client(INTERNAL_TOKEN=token, BRASA_STORAGE_URL="") as client:
        svc = client.app.state.services
        # Como en producción: el último ciclo cerrado es viejo y trae las banderas en `true`.
        svc.db.kv_set("last_cycle", json.dumps({
            "started_at": "2026-10-20T22:30:49Z", "finished_at": "2026-10-20T22:50:28Z",
            "fwi_error": True, "rain_error": True,
        }))
        svc.tick = cortado
        with pytest.raises(RuntimeError):  # Starlette: la petición murió sin respuesta
            client.post("/api/internal/tick?wait=1", headers={"X-Internal-Token": token})
        ciclo = client.get("/api/status").json()["last_cycle"]
        assert ciclo["started_at"] > "2026-10-20T22:50:28Z"
        assert ciclo["running"] is True and ciclo["finished_at"] is None
        assert "fwi_error" not in ciclo and "rain_error" not in ciclo


def test_el_fallo_de_fwi_y_lluvia_se_ve_en_status_con_su_motivo(providers, make_client, monkeypatch):
    """Un cálculo propio que falla deja corrida con `ok = 0` y `/api/status` expone
    la causa recortada y enmascarada en `last_cycle`, no solo `true` (FWI-01)."""

    async def boom(*_args, **_kwargs):
        raise RuntimeError(f"MAP_KEY={'k' * 24} respondió 429: demasiadas ubicaciones")

    monkeypatch.setattr(weather, "fwi_inputs", boom)
    monkeypatch.setattr(weather, "daily_rain", boom)
    with make_client(FIRMS_MAP_KEY="k-123", RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        asyncio.run(svc.tick_and_backup())
        runs = {row["product"]: row for row in svc.db.query("SELECT product, ok, message FROM ingest_runs")}
        assert runs["FWI"]["ok"] == 0 and "429" in runs["FWI"]["message"]
        assert runs["LLUVIA"]["ok"] == 0 and "429" in runs["LLUVIA"]["message"]
        status = client.get("/api/status").json()
        assert status["errors"]["by_product"]["FWI"]["failed"] == 1
        assert status["errors"]["by_product"]["LLUVIA"]["failed"] == 1
        ciclo = status["last_cycle"]
        assert "429" in ciclo["fwi_error"] and "429" in ciclo["rain_error"]
        # El mensaje viaja enmascarado: la clave del error nunca sale por la API.
        assert "MAP_KEY=***" in ciclo["fwi_error"] and "k" * 24 not in ciclo["fwi_error"]
