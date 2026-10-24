"""DET-03/DET-23: la marca «hubo rayos cerca del inicio» del incidente.

Sin red: los destellos se siembran directo en la tabla `lightning` de work.db; la capa
pública es la que la llena en producción (`opendata._save_flashes`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import incidents
from backend.db import Database
from backend.providers import glm
from backend.routes import opendata
from tests.test_incidents import KM_LAT, obs

SAMPLE = Path(__file__).parent / "data" / "glm_lcfa_sample.nc"

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


def test_two_glm_files_in_the_same_minute_keep_all_their_flashes(tmp_path):
    """PK + INSERT OR IGNORE: el id lleva el segundo del archivo (PR #712, revisión geo);
    con el minuto, dos LCFA del mismo minuto colapsaban y se perdían destellos."""
    db = Database(tmp_path / "brasa.db")
    key_a = "GLM-L2-LCFA/2025/291/15/OR_GLM-L2-LCFA_G19_s20252911500000_e20252911500200_c20252911500300.nc"
    key_b = key_a.replace("s20252911500000", "s20252911500020")
    flashes = (glm.parse_lcfa(SAMPLE.read_bytes(), "G19", key_a)
               + glm.parse_lcfa(SAMPLE.read_bytes(), "G19", key_b))
    stamp = datetime.now(timezone.utc).strftime(STAMP)  # el fixture es de 2025: la retención lo purgaría
    for f in flashes:
        f["observed_at"] = stamp
    opendata._save_flashes(db, flashes)
    assert db.one("SELECT COUNT(*) AS n FROM lightning")["n"] == len(flashes) == 4


def test_the_mark_survives_the_retention_purge(tmp_path):
    """Marca monotónica: tras la purga un refresh no puede recomputar la ventana, pero una
    marca ya puesta es un hecho histórico — no retrocede a 0 ni por `_refresh` ni por
    `_refresh_fast` (la paridad que pide la revisión)."""
    db = Database(tmp_path / "brasa.db")
    flash(db, "f1", -33.5 + 3 * KM_LAT, -70.8, T0 - timedelta(hours=1))
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["lightning_count"] == 1
    db.execute("DELETE FROM lightning")
    refreshed = incidents._refresh(db, inc["id"], T0 + timedelta(minutes=5))
    assert refreshed["lightning_count"] == 1 and refreshed["lightning_km"] is not None
    [again] = incidents.update(db, [obs(db, "b", -33.5 + KM_LAT, -70.8, minutes=40)], T0 + timedelta(minutes=45))
    assert again["id"] == inc["id"] and again["lightning_count"] == 1
