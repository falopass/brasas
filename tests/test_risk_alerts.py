import asyncio
from datetime import datetime, timezone

from backend import alerts, risk
from backend.db import Database
from backend.geo import angle_diff, bearing_deg, cardinal, haversine_km, is_upwind, territory


def utc_hours(start: str, n: int) -> list[str]:
    from datetime import datetime, timedelta
    t0 = datetime.fromisoformat(start)
    return [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]


def test_days_are_grouped_in_chile_time():
    assert risk.local_day("2027-01-15T02:00") == "2027-01-14"  # 23:00 del 14 en Chile
    assert risk.local_day("2027-07-15T03:30") == "2027-07-14"  # invierno, UTC-4


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


def test_geometry_helpers():
    assert abs(haversine_km(-33.45, -70.66, -33.05, -71.55) - 94) < 3  # Santiago → Viña ≈ 94 km
    assert cardinal(bearing_deg(-33.45, -70.66, -33.05, -71.55)) == "noroeste"
    assert angle_diff(350, 10) == 20
    # Foco al norte (rumbo 0°) con viento DESDE el norte (0°) a 20 km/h: viene hacia el lugar.
    assert is_upwind(0, 10, 20) is True
    assert is_upwind(0, 180, 20) is False
    assert is_upwind(0, 10, 3) is False  # viento débil


def test_territory_locates_real_comunas_and_fixes_coquimbo_gap():
    t = territory()
    assert len(t.comunas) == 345
    assert t.locate(-33.0245, -71.5518).name == "Viña del Mar"
    assert t.locate(-31.6333, -71.1667).name == "Illapel"  # antes no estaba en ninguna zona
    assert t.locate(-35.4264, -71.6554).name == "Talca"
    assert t.locate(-27.12, -109.35).name == "Isla de Pascua"
    assert t.locate(-35.0, -60.0) is None  # Argentina
    zones = t.zones()
    assert "region-4" in zones and zones["region-4"]["label"] == "Coquimbo"


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
