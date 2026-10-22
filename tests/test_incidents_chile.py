"""FUEGO-04: el agrupador no abre incidentes con detecciones fuera de Chile.

La regla es la coordenada, no la comuna: un punto chileno del borde costero puede
llegar sin `comuna_code` y aun así debe entrar al agrupador.
"""

from datetime import datetime, timedelta, timezone

from backend import incidents
from backend.db import Database
from backend.geo import territory

T0 = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
KM_LAT = 1 / 111.0


def obs(db: Database, oid: str, lat: float, lon: float, minutes: float = 0, comuna_code: int | None = None) -> dict:
    row = {
        "id": oid,
        "source": "firms",
        "sensor": "ABI",
        "satellite": "G19",
        "resolution_m": 2000,
        "lat": lat,
        "lon": lon,
        "observed_at": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frp_mw": 12.0,
        "confidence": "alta",
        "comuna_code": comuna_code,
    }
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
        "confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (oid, "firms", "ABI", "G19", 2000, lat, lon, row["observed_at"], 12.0, "alta", comuna_code, row["observed_at"]),
    )
    return row


def test_dos_detecciones_en_argentina_no_abren_incidente(tmp_path):
    """San Juan, Argentina: aunque estén contiguas y seguidas en el tiempo, no son de Chile."""
    db = Database(tmp_path / "brasa.db")
    points = [
        obs(db, "ar1", -31.3549, -69.4223),
        obs(db, "ar2", -31.3549 + KM_LAT, -69.4223, minutes=40),
    ]
    assert incidents.update(db, points, T0 + timedelta(minutes=45)) == []
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 0


def test_una_chilena_y_una_argentina_a_3_km_forman_un_incidente_chileno(tmp_path):
    db = Database(tmp_path / "brasa.db")
    curico = territory().locate(-35.5, -70.38)
    assert curico is not None and curico.name == "Curicó"
    # 3 km al este del borde: con la tolerancia costera de FIRMS la detección entra al
    # agrupador, pero el incidente toma la comuna de la detección chilena.
    chile = obs(db, "cl", -35.5, -70.38, comuna_code=curico.code)
    argentina = obs(db, "ar", -35.5, -70.38 + 3 / 90.5, minutes=40)
    [inc] = incidents.update(db, [chile, argentina], T0 + timedelta(minutes=45))
    assert inc["comuna_code"] == curico.code
    assert inc["n_obs"] == 2


def test_una_deteccion_costera_sin_comuna_entra_por_la_tolerancia(tmp_path):
    """Frente a Valparaíso: `locate` sin margen no la ubica, pero sigue siendo Chile."""
    db = Database(tmp_path / "brasa.db")
    lat, lon = -33.03, -71.68
    assert territory().locate(lat, lon) is None
    [inc] = incidents.update(db, [obs(db, "costa", lat, lon)], T0)
    assert inc["comuna_code"] == territory().locate(lat, lon, tolerance_deg=0.16).code
