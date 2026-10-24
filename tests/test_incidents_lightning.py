"""DET-03/DET-23: la marca «hubo rayos cerca del inicio» del incidente.

Sin red: los destellos se siembran directo en la tabla `lightning` de work.db; la capa
pública es la que la llena en producción (`opendata._save_flashes`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import incidents
from backend.db import Database
from backend.routes import opendata
from tests.test_incidents import KM_LAT, obs

T0 = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def flash(db: Database, fid: str, lat: float, lon: float, when: datetime) -> None:
    db.execute(
        "INSERT OR IGNORE INTO lightning(id, observed_at, lat, lon, energy_j, source) VALUES (?,?,?,?,?,?)",
        (fid, when.strftime(STAMP), lat, lon, 10.0, "GOES19_GLM"),
    )


def test_a_flash_3km_away_an_hour_before_marks_the_incident(tmp_path):
    db = Database(tmp_path / "brasa.db")
    before = T0 - timedelta(hours=1)
    flash(db, "f1", -33.5 + 3 * KM_LAT, -70.8, before)
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 1
    assert abs(inc["lightning_km"] - 3) < 0.2
    assert inc["lightning_last_at"] == before.strftime(STAMP)


def test_a_flash_8km_away_does_not_mark(tmp_path):
    db = Database(tmp_path / "brasa.db")
    flash(db, "f1", -33.5 + 8 * KM_LAT, -70.8, T0 - timedelta(hours=1))
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 0 and inc["lightning_km"] is None


def test_a_flash_3_hours_before_does_not_mark(tmp_path):
    db = Database(tmp_path / "brasa.db")
    flash(db, "f1", -33.5 + 3 * KM_LAT, -70.8, T0 - timedelta(hours=3))
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 0 and inc["lightning_last_at"] is None


def test_an_incident_without_flashes_has_the_mark_empty(tmp_path):
    db = Database(tmp_path / "brasa.db")
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 0
    assert inc["lightning_km"] is None and inc["lightning_last_at"] is None


def test_the_mark_is_recomputed_when_the_incident_grows(tmp_path):
    """La marca se calcula al abrir y al actualizar: un destello guardado después del
    primer refresh entra en el siguiente, sin pedido extra."""
    db = Database(tmp_path / "brasa.db")
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 0
    flash(db, "f1", -33.5 + 4 * KM_LAT, -70.8, T0 - timedelta(hours=1))
    [again] = incidents.update(db, [obs(db, "b", -33.5 + KM_LAT, -70.8, minutes=40)], T0 + timedelta(minutes=45))
    assert again["id"] == inc["id"] and again["lightning_count"] == 1


def test_incidents_geojson_publishes_the_mark(make_client):
    """El campo es aditivo: el conjunto abierto lo publica y el índice lo describe."""
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        flash(db, "f1", -33.5 + 3 * KM_LAT, -70.8, now - timedelta(hours=1))
        [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8, when=now)], now)
        body = client.get("/api/opendata/incidents.geojson").json()
        props = next(f["properties"] for f in body["features"] if f["properties"]["id"] == inc["id"])
        assert props["lightning_count"] == 1 and props["lightning_km"] is not None
        assert props["lightning_last_at"] is not None
        dataset = next(d for d in client.get("/api/opendata").json()["datasets"] if d["id"] == "incidents")
        assert {"lightning_count", "lightning_km", "lightning_last_at"} <= set(dataset["properties"])


def test_save_flashes_is_idempotent_and_purges_old_ones(tmp_path):
    """El lote bajado se guarda una vez por `id`; lo que venció la retención sale en la
    misma escritura."""
    db = Database(tmp_path / "brasa.db")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    batch = [
        {"id": "f1", "observed_at": now.strftime(STAMP), "lat": -33.5, "lon": -70.8,
         "energy_j": 5.0, "source": "GOES19_GLM"},
        {"id": "viejo", "observed_at": (now - timedelta(hours=opendata.LIGHTNING_KEEP_HOURS + 1)).strftime(STAMP),
         "lat": -33.5, "lon": -70.8, "energy_j": None, "source": "GOES19_GLM"},
    ]
    opendata._save_flashes(db, batch)
    opendata._save_flashes(db, batch)  # otra ventana solapada no duplica
    rows = db.query("SELECT id FROM lightning")
    assert [r["id"] for r in rows] == ["f1"]
