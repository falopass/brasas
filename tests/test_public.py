"""REV-04: dos señales de la API pública que mentían.

`goes_missing` contaba filas `ok` de `ingest_runs`, así que un barrido re-ingerido por
reintento tapaba un hueco real: ahora se cuentan claves S3 distintas. Y `lightning.geojson`
truncaba en `MAX_FEATURES` sin avisar: ahora la colección trae `truncated`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.providers import glm
from backend.routes import opendata


def key_for(moment: datetime) -> str:
    """Clave S3 FDCF con el formato que entiende `goes.key_start`."""
    doy = moment.timetuple().tm_yday
    return (f"ABI-L2-FDCF/{moment:%Y}/{doy:03d}/{moment:%H}/"
            f"OR_ABI-L2-FDCF-M6_G19_s{moment.year}{doy:03d}{moment:%H%M%S}0_e.nc")


def goes_run(db, sweep_minutes_ago: int) -> None:
    """Un barrido GOES ok: `source_ref` lleva la hora del barrido y `started_at` la de ahora."""
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sweep = datetime.now(timezone.utc) - timedelta(minutes=sweep_minutes_ago)
    db.execute("INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, "
               "message, source_ref) VALUES (?,?,?,?,?,?,?,?,?)",
               ("NOAA GOES", "GOES19_FDCF", at, at, 1, 10, 10, "", key_for(sweep)))


def test_goes_missing_counts_distinct_sweeps_not_runs(make_client):
    """Dos corridas ok del mismo barrido cuentan una sola vez: el hueco real no se tapa."""
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        for minutes_ago in (55, 45, 35, 25, 15, 5):      # la hora completa, un barrido cada 10 min
            goes_run(db, minutes_ago)
        assert client.get("/api/status").json()["goes_missing"] == 0

        db.execute("DELETE FROM ingest_runs")
        goes_run(db, 55)                                # solo 5 barridos distintos…
        goes_run(db, 55)                                # …pero el primero se ingirió dos veces
        for minutes_ago in (45, 35, 25, 15):
            goes_run(db, minutes_ago)
        body = client.get("/api/status").json()
        assert body["goes_missing"] == 1, "el reintento no puede contar como un sexto barrido"


def test_lightning_warns_when_the_collection_is_truncated(make_client, monkeypatch):
    """Más destellos que `MAX_FEATURES`: `count` dice lo devuelto y `truncated` avisa el recorte."""
    monkeypatch.setattr(opendata, "_LIGHTNING_CACHE", {})
    observed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def fake_flashes(client, hours):
        n = opendata.MAX_FEATURES + 1 if hours == 1 else 2
        return [{"id": f"GOES19_GLM:x:{i}", "lat": -33.0, "lon": -71.5, "observed_at": observed,
                 "energy_j": 1.0, "area_km2": 1.0} for i in range(n)]

    monkeypatch.setattr(glm, "fetch_flashes", fake_flashes)
    with make_client() as client:
        body = client.get("/api/opendata/lightning.geojson").json()
        assert body["truncated"] is True
        assert body["count"] == len(body["features"]) == opendata.MAX_FEATURES
        small = client.get("/api/opendata/lightning.geojson?hours=2").json()
        assert small["truncated"] is False and small["count"] == 2
