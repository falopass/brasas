import asyncio
from datetime import datetime, timedelta, timezone

from backend import alerts, risk
from backend.db import Database


def utc_hours(start: str, n: int) -> list[str]:
    t0 = datetime.fromisoformat(start)
    return [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]


def test_winter_days_use_utc_minus_4():
    assert risk.local_day("2027-07-15T03:30") == "2027-07-14"  # invierno en Chile


def test_30_30_30_classification():
    hourly = {
        # 03:00 UTC = 00:00 en Chile (horario de verano, UTC-3): 48 horas = 2 días locales completos.
        "time": utc_hours("2027-01-15T03:00", 48),
        "temperature_2m": [33] * 24 + [22] * 24,
        "relative_humidity_2m": [22] * 24 + [60] * 24,
        "wind_speed_10m": [35] * 3 + [12] * 21 + [10] * 24,
        "wind_gusts_10m": [55] * 24 + [20] * 24,
        "wind_direction_10m": [200] * 48,
    }
    result = risk.evaluate(hourly)
    hot, mild = result["days"]
    assert hot["hours_3of3"] == 3 and hot["level"] == "extremo" and hot["tmax"] == 33 and hot["gustmax"] == 55
    assert hot["date"] == "2027-01-15" and mild["date"] == "2027-01-16"
    assert mild["level"] == "bajo" and mild["hours_2of3"] == 0
    assert result["hours"][0]["time"] == "2027-01-15T03:00Z"
    assert result["hours"][0]["n"] == 3 and result["hours"][5]["n"] == 2


def test_hot_dry_without_wind_is_high_not_extreme():
    hourly = {"time": utc_hours("2027-01-15T15:00", 6), "temperature_2m": [34] * 6,
              "relative_humidity_2m": [20] * 6, "wind_speed_10m": [10] * 6}
    day = risk.evaluate(hourly)["days"][0]
    assert day["hours_3of3"] == 0 and day["hours_2of3"] == 6 and day["level"] == "alto"


def make_db(tmp_path):
    db = Database(tmp_path / "t.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('sub-aaaaaaaaaaaaaaaaaaaaaaa', 'x')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
               "VALUES ('p1', 'sub-aaaaaaaaaaaaaaaaaaaaaaa', 'Casa', 'casa', -33.05, -71.50, 10, 5109, 'x')")
    return db


def obs(i, lat, lon, confidence="alta"):
    return {"id": f"o{i}", "lat": lat, "lon": lon, "observed_at": "2027-01-15T20:00:00Z", "source": "GOES19_FDCF",
            "sensor": "ABI", "satellite": "GOES-19", "confidence": confidence, "frp_mw": 120.0, "resolution_m": 2000}


def test_alert_created_deduplicated_and_escalated(tmp_path):
    db = make_db(tmp_path)
    now = datetime(2027, 1, 15, 20, 5, tzinfo=timezone.utc)
    far = obs(1, -33.05, -71.40)  # ~9 km al este
    created = asyncio.run(alerts.evaluate(db, [far, obs(2, -33.055, -71.40)], None, now))
    assert len(created) == 1
    payload = created[0]["payload"]
    assert created[0]["level"] == "aviso" and payload["direction"] == "este" and payload["others"] == 1
    assert "no es una alerta oficial" in payload["footer"]
    # La misma zona con igual nivel no se repite.
    assert asyncio.run(alerts.evaluate(db, [obs(3, -33.05, -71.41)], None, now)) == []

    async def east_wind(lat, lon):
        return {"speed": 25.0, "direction": 90.0}

    escalated = asyncio.run(alerts.evaluate(db, [obs(4, -33.05, -71.41)], east_wind, now))
    assert len(escalated) == 1 and escalated[0]["level"] == "urgente" and escalated[0]["payload"]["upwind"] is True


def test_low_confidence_and_far_detections_do_not_alert(tmp_path):
    db = make_db(tmp_path)
    assert asyncio.run(alerts.evaluate(db, [obs(1, -33.05, -71.45, "baja")], None)) == []
    assert asyncio.run(alerts.evaluate(db, [obs(2, -34.0, -71.5)], None)) == []


def test_very_close_detection_is_urgent(tmp_path):
    db = make_db(tmp_path)
    created = asyncio.run(alerts.evaluate(db, [obs(1, -33.055, -71.505)], None))
    assert created[0]["level"] == "urgente"


def test_older_adult_needs_real_evidence_for_urgent(tmp_path):
    """FIX-08: con una persona mayor en el lugar ya no basta «calor confiable dentro del radio»
    para «urgente»: una quema agrícola abría el modo emergencia. Urgente pide un incidente
    «posible» o más, ≤ 5 km o viento hacia el lugar; el resto queda en «aviso» reforzado."""
    db = make_db(tmp_path)
    db.execute("UPDATE places SET older_adult = 1")
    now = datetime(2027, 1, 15, 20, 5, tzinfo=timezone.utc)

    # Anomalía suelta a ~9 km: «aviso» (antes era «urgente»), con el texto de la persona mayor.
    created = asyncio.run(alerts.evaluate(db, [obs(1, -33.05, -71.40)], None, now))
    assert len(created) == 1 and created[0]["level"] == "aviso"
    assert "persona mayor" in created[0]["payload"]["body"]

    # A la misma lejanía, un incidente ya «posible» sí es urgente.
    db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
               "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, updated_at) "
               "VALUES ('inc-1','posible','2027-01-15T19:00:00Z','2027-01-15T18:00:00Z','2027-01-15T20:00:00Z',"
               "-33.10,-71.45,-33.10,-33.10,-71.45,-71.45,3,3,'VIIRS,ABI',5109,'2027-01-15T20:00:00Z')")
    db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES ('o2','inc-1')")
    created = asyncio.run(alerts.evaluate(db, [obs(2, -33.10, -71.45)], None, now))
    assert len(created) == 1 and created[0]["level"] == "urgente"

    # La cercanía basta: una anomalía a ≤ 5 km es urgente.
    created = asyncio.run(alerts.evaluate(db, [obs(3, -33.05, -71.46)], None, now))
    assert len(created) == 1 and created[0]["level"] == "urgente"

    # Y el viento hacia el lugar, aunque la anomalía esté lejos.
    async def east_wind(lat, lon):
        return {"speed": 25.0, "direction": 90.0}

    created = asyncio.run(alerts.evaluate(db, [obs(4, -33.06, -71.42)], east_wind, now))
    assert len(created) == 1 and created[0]["level"] == "urgente"


def test_reports_of_the_same_fire_send_one_aviso_per_place(tmp_path):
    """REV-03: aprobar en lote varios reportes del mismo incendio no multiplica el aviso.

    Dos reportes verificados a la vez apuntan al mismo hecho: el primero avisa a cada lugar
    cercano y el segundo encuentra el aviso vigente (30 min), así que 3 lugares reciben 3
    avisos y no 6. Pasada la ventana, un reporte nuevo vuelve a avisar.
    """
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1', 'x')")
    for i in range(3):
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                   "VALUES (?, 's1', ?, 'casa', ?, -71.55, 10, 'x')", (f"p{i}", f"Lugar {i}", -33.05 - i * 0.01))
    now = datetime(2027, 1, 15, 20, 5, tzinfo=timezone.utc)
    report = {"created_at": "2027-01-15T19:50:00Z", "lat": -33.05, "lon": -71.52,
              "kind": "humo", "status": "verificado"}
    assert len(alerts.evaluate_report(db, {**report, "id": "r1"}, now=now)) == 3
    assert alerts.evaluate_report(db, {**report, "id": "r2"}, now=now) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 3
    later = now + timedelta(minutes=alerts.REPORT_DEDUPE_MIN + 1)
    assert len(alerts.evaluate_report(db, {**report, "id": "r3"}, now=later)) == 3


def test_day_without_measurements_is_not_classified_as_low():
    """Si el pronóstico de una comuna llega vacío, no debe aparecer como «bajo» (sería falsa tranquilidad)."""
    hourly = {"time": utc_hours("2027-01-15T03:00", 48),
              "temperature_2m": [25] * 24 + [None] * 24,
              "relative_humidity_2m": [50] * 24 + [None] * 24,
              "wind_speed_10m": [10] * 24 + [None] * 24}
    days = risk.evaluate(hourly)["days"]
    assert [d["date"] for d in days] == ["2027-01-15"] and days[0]["level"] == "bajo"
