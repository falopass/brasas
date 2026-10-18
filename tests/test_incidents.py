import asyncio
import gzip
from datetime import datetime, timedelta, timezone

from backend import alerts, incidents
from backend.db import Database
from backend.storage import WORK_KEY, Persistence

T0 = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
KM_LAT = 1 / 111.0  # grados de latitud por km


def obs(db: Database, oid: str, lat: float, lon: float, minutes: float = 0, sensor: str = "VIIRS",
        confidence: str = "nominal", resolution_m: int = 375, when: datetime = T0) -> dict:
    row = {"id": oid, "source": "firms", "sensor": sensor, "satellite": "N20", "resolution_m": resolution_m,
           "lat": lat, "lon": lon, "observed_at": (when + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "frp_mw": 12.0, "confidence": confidence, "comuna_code": 13101}
    db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
               "confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
               (oid, "firms", sensor, "N20", resolution_m, lat, lon, row["observed_at"], 12.0, confidence, 13101, row["observed_at"]))
    return row


def test_single_detection_is_an_anomaly_and_a_second_one_makes_it_possible(tmp_path):
    db = Database(tmp_path / "brasa.db")
    first = obs(db, "a", -33.5, -70.8)
    [inc] = incidents.update(db, [first], T0)
    assert inc["status"] == "anomalia" and inc["n_obs"] == 1
    second = obs(db, "b", -33.5 + KM_LAT, -70.8, minutes=40)
    [again] = incidents.update(db, [second], T0 + timedelta(minutes=45))
    assert again["id"] == inc["id"] and again["status"] == "posible" and again["n_obs"] == 2
    assert incidents.incident_of(db, "b")["id"] == inc["id"]


def test_two_sensors_at_the_same_time_make_it_possible(tmp_path):
    db = Database(tmp_path / "brasa.db")
    pts = [obs(db, "v", -33.5, -70.8), obs(db, "g", -33.5, -70.81, sensor="ABI", confidence="alta", resolution_m=2000)]
    [inc] = incidents.update(db, pts, T0)
    assert inc["status"] == "posible" and inc["sensors"] == "ABI,VIIRS"


def test_far_or_old_detections_start_new_incidents(tmp_path):
    db = Database(tmp_path / "brasa.db")
    incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    incidents.update(db, [obs(db, "far", -33.5 - 20 * KM_LAT, -70.8)], T0)
    incidents.update(db, [obs(db, "late", -33.5, -70.8, minutes=7 * 60)], T0 + timedelta(hours=7))
    ids = {incidents.incident_of(db, oid)["id"] for oid in ("a", "far", "late")}
    assert len(ids) == 3


def test_a_detection_between_two_incidents_merges_them_into_the_oldest(tmp_path):
    db = Database(tmp_path / "brasa.db")
    [north] = incidents.update(db, [obs(db, "n", -33.5, -70.8)], T0)
    [south] = incidents.update(db, [obs(db, "s", -33.5 - 4 * KM_LAT, -70.8, minutes=10)], T0)
    assert north["id"] != south["id"]
    [merged] = incidents.update(db, [obs(db, "m", -33.5 - 2 * KM_LAT, -70.8, minutes=20)], T0)
    assert merged["id"] == north["id"] and merged["n_obs"] == 3
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 1


def test_incidents_go_out_after_24_hours_without_detections(tmp_path):
    db = Database(tmp_path / "brasa.db")
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert incidents.expire(db, T0 + timedelta(hours=23)) == 0
    assert incidents.expire(db, T0 + timedelta(hours=25)) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "extinguido"


def test_a_verified_neighbor_report_marks_it_reported(tmp_path):
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO reports(id, created_at, lat, lon, kind, description, status) VALUES "
               "('r1', ?, -33.505, -70.8, 'humo', 'Humo en el cerro', 'verificado')", ((T0 - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    assert inc["status"] == "reportado"


def test_volcano_and_recurring_hot_cells_are_fixed_sources(tmp_path):
    db = Database(tmp_path / "brasa.db")
    [volcano] = incidents.update(db, [obs(db, "v", -39.42, -71.94)], T0)  # cráter del Villarrica
    assert volcano["fixed_source"] == 1
    for day in range(9):  # la misma celda arde 9 días distintos: industria o antorcha
        obs(db, f"f{day}", -36.8, -73.0, when=T0 - timedelta(days=day + 1))
    [factory] = incidents.update(db, [obs(db, "today", -36.8, -73.0)], T0)
    assert factory["fixed_source"] == 1
    [fire] = incidents.update(db, [obs(db, "fire", -33.5, -70.8)], T0)
    assert fire["fixed_source"] == 0


def _place(db: Database, lat: float, lon: float) -> None:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1', '2027-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1', 's1', 'Casa', 'casa', ?, ?, 15, '2027-01-01T00:00:00Z')", (lat, lon))


def test_alerts_skip_fixed_sources_and_mention_the_incident(tmp_path):
    db = Database(tmp_path / "brasa.db")
    _place(db, -39.40, -71.94)
    volcano = obs(db, "v", -39.42, -71.94)
    incidents.update(db, [volcano], T0)
    assert asyncio.run(alerts.evaluate(db, [volcano], now=T0)) == []

    db2 = Database(tmp_path / "b2.db", tmp_path / "w2.db")
    _place(db2, -33.45, -70.8)
    pts = [obs(db2, "a", -33.5, -70.8), obs(db2, "b", -33.5 + KM_LAT, -70.8, minutes=70)]
    incidents.update(db2, pts, T0 + timedelta(minutes=75))
    [alert] = asyncio.run(alerts.evaluate(db2, pts, now=T0 + timedelta(minutes=75)))
    payload = alert["payload"]
    assert payload["incident"]["status"] == "posible" and payload["incident"]["n_obs"] == 2
    assert "Posible incendio: 2 detecciones en 1 h." in payload["body"]


class MemoryStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def get(self, key):
        return self.files.get(key)

    async def put(self, key, content, content_type="application/octet-stream"):
        self.files[key] = content


def test_work_db_backup_keeps_incidents_across_restarts(tmp_path):
    db = Database(tmp_path / "a" / "brasa.db")
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    storage = MemoryStorage()
    first = Persistence(db, storage)
    assert asyncio.run(first.restore()) is False  # sin respaldos previos
    assert asyncio.run(first.flush_work()) is True
    assert asyncio.run(first.flush_work()) is False  # ya subió hace menos de una hora
    assert gzip.decompress(storage.files[WORK_KEY]).startswith(b"SQLite format 3")

    fresh = Database(tmp_path / "b" / "brasa.db")
    assert asyncio.run(Persistence(fresh, storage).restore_work()) is True
    assert fresh.one("SELECT id, status FROM incidents") == {"id": inc["id"], "status": "anomalia"}
    assert incidents.incident_of(fresh, "a")["id"] == inc["id"]


def test_a_damaged_work_backup_does_not_block_startup(tmp_path):
    db = Database(tmp_path / "brasa.db")
    storage = MemoryStorage()
    storage.files[WORK_KEY] = gzip.compress(b"no soy sqlite")
    assert asyncio.run(Persistence(db, storage).restore_work()) is False
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 0


def test_incident_api_lists_and_details_with_timeline(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        pts = [obs(db, "a", -33.5, -70.8, when=now - timedelta(hours=2)),
               obs(db, "b", -33.5 + KM_LAT, -70.8, when=now - timedelta(hours=1), sensor="ABI", confidence="alta", resolution_m=2000)]
        [inc] = incidents.update(db, pts, now)
        listing = client.get("/api/incidents").json()
        assert listing["count"] == 1 and listing["incidents"][0]["status"] == "posible"
        assert listing["incidents"][0]["sensors"] == ["ABI", "VIIRS"]
        detail = client.get(f"/api/incidents/{inc['id']}").json()
        assert detail["evidence_total"] == 2 and detail["timeline"]["hours"]
        assert any(e["kind"] == "inicio" for e in detail["timeline"]["events"])
        assert set(detail["latency"]) == {"ABI", "VIIRS"}
        assert client.get("/api/incidents/../../etc").status_code == 404
        assert client.get("/api/incidents/ffffffffffff").status_code == 404
        point = next(p for p in client.get("/api/observations?hours=6").json()["points"] if p["id"] == "a")
        assert point["incident_id"] == inc["id"] and point["incident_status"] == "posible"
        assert client.get("/api/status").json()["incidents_open"] == {"posible": 1}
