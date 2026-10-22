"""FIX-03: que la regla de «fuente fija» no silencie un incendio real, y diga por qué marca.

Reglas nuevas (pasos 1, 2 y 4 del backlog):
1. Un incendio informado por CONAF a ≤ 5 km invalida la regla.
2. Los días tienen que repartirse en ≥ 3 semanas distintas, o haber calor fuera de temporada.
4. El incidente guarda y publica la razón por la que se marcó como fuente fija.

DET-15: los puntos curados pueden llevar `valid_from`/`valid_to` (días ISO); fuera de esa
ventana no silencian, para que una instalación apagada no siga tapando calor real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import incidents
from backend.db import Database

NOW = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
LAT, LON = -33.50, -70.80  # fuera de los volcanes conocidos
KM_LAT = 1 / 111.0


def add_days(db: Database, days: list[datetime], lat: float = LAT, lon: float = LON) -> None:
    """Una detección nominal por día, en la misma celda de ~2 km."""
    for index, moment in enumerate(days):
        stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
            "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
            (f"o{index}", "firms", "VIIRS", "N20", 375, lat, lon, stamp, 10.0, "nominal", 13101, stamp),
        )


def days_between(start: datetime, offsets: list[int]) -> list[datetime]:
    return [start + timedelta(days=offset) for offset in offsets]


def test_known_volcanoes_are_fixed_and_say_which(tmp_path):
    """Los puntos curados no traen ventana: sin `valid_from`/`valid_to` valen siempre."""
    db = Database(tmp_path / "brasa.db")
    sources = incidents.known_fixed_sources()
    assert len(sources) >= 3  # DET-18: la lista curada creció a todos los volcanes con ficha GVP
    for source in sources:
        assert "valid_from" not in source and "valid_to" not in source
        reason = incidents.fixed_reason(db, source["lat"], source["lon"], NOW)
        assert reason == f"volcán activo conocido ({source['name']})"
        assert incidents.is_fixed_source(db, source["lat"], source["lon"], NOW) is True


def fake_source(**extra) -> dict:
    """Una fuente curada inventada, justo sobre la celda de prueba (LAT, LON)."""
    return {"name": "Planta de prueba", "kind": "industria", "lat": LAT, "lon": LON, "radius_km": 3, "source": "fuente de prueba", **extra}


def test_a_source_inside_its_window_marks_the_cell(tmp_path, monkeypatch):
    """Una fuente vigente sí silencia y dice qué es, aunque no sea volcán."""
    monkeypatch.setattr(incidents, "known_fixed_sources", lambda: [fake_source(valid_from="2026-01-01")])
    db = Database(tmp_path / "brasa.db")
    assert incidents.fixed_reason(db, LAT, LON, NOW) == "fuente fija conocida (Planta de prueba)"
    # El último día de la ventana también cuenta (valid_to es inclusivo).
    monkeypatch.setattr(incidents, "known_fixed_sources", lambda: [fake_source(valid_from="2026-01-01", valid_to="2027-01-20")])
    assert incidents.is_fixed_source(db, LAT, LON, NOW) is True


def test_an_expired_source_does_not_silence_the_incident(tmp_path, monkeypatch):
    """Una instalación apagada (`valid_to` vencido) ya no es fija: el incidente avisa normal."""
    monkeypatch.setattr(incidents, "known_fixed_sources", lambda: [fake_source(valid_from="2020-01-01", valid_to="2024-11-16")])
    db = Database(tmp_path / "brasa.db")
    assert incidents.fixed_reason(db, LAT, LON, NOW) is None
    stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    point = {"id": "ultima", "lat": LAT, "lon": LON, "observed_at": stamp, "sensor": "VIIRS", "confidence": "nominal", "resolution_m": 375}
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        ("ultima", "firms", "VIIRS", "N20", 375, LAT, LON, stamp, 10.0, "nominal", 13101, stamp),
    )
    [incident] = incidents.update(db, [point], NOW)
    assert incident["fixed_source"] == 0 and incident["fixed_reason"] is None


def test_a_future_source_is_not_fixed_yet(tmp_path, monkeypatch):
    """Una instalación que aún no existe (`valid_from` futuro) tampoco silencia."""
    monkeypatch.setattr(incidents, "known_fixed_sources", lambda: [fake_source(valid_from="2028-01-01")])
    db = Database(tmp_path / "brasa.db")
    assert incidents.fixed_reason(db, LAT, LON, NOW) is None
    assert incidents.is_fixed_source(db, LAT, LON, NOW) is False


def test_eight_days_spread_over_three_weeks_are_fixed(tmp_path):
    db = Database(tmp_path / "brasa.db")
    # Ocho días en cuatro semanas distintas, dentro de la temporada (enero).
    add_days(db, days_between(NOW - timedelta(days=27), [0, 7, 8, 14, 15, 21, 22, 27]))
    reason = incidents.fixed_reason(db, LAT, LON, NOW)
    assert reason and "semanas distintas" in reason


def test_eight_days_in_two_weeks_inside_the_season_are_not_fixed(tmp_path):
    """Un incendio de diez días seguidos no es una antorcha: sin reparto, no se marca."""
    db = Database(tmp_path / "brasa.db")
    add_days(db, days_between(NOW - timedelta(days=9), list(range(10))))
    assert incidents.fixed_reason(db, LAT, LON, NOW) is None


def test_ten_days_crossing_three_iso_weeks_are_not_fixed(tmp_path):
    """La semana ISO es un cubo de calendario: diez días seguidos desde un sábado tocan tres
    semanas sin repartirse de verdad (del 2 al 11 de enero de 2027: semanas 53, 1 y 2)."""
    db = Database(tmp_path / "brasa.db")
    saturday = datetime(2027, 1, 2, 15, 0, tzinfo=timezone.utc)
    add_days(db, days_between(saturday, list(range(10))))
    assert incidents.fixed_reason(db, LAT, LON, saturday + timedelta(days=10)) is None


def test_heat_outside_the_season_is_fixed_even_without_spread(tmp_path):
    """En junio, calor en el mismo punto durante dos semanas es una industria, no un incendio."""
    db = Database(tmp_path / "brasa.db")
    june = datetime(2026, 6, 20, 17, 0, tzinfo=timezone.utc)
    add_days(db, days_between(june - timedelta(days=9), list(range(10))))
    reason = incidents.fixed_reason(db, LAT, LON, june + timedelta(days=1))
    assert reason == "calor fuera de la temporada de incendios"


def add_official(db: Database, ident: str, started: datetime, lat: float, lon: float) -> None:
    """Incendio informado por CONAF, con las columnas reales de `official_fires`."""
    stamp = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ident, "Incendio de prueba", "confirmado", "En combate", stamp, lat, lon, "Viña del Mar", "Valparaíso", stamp, stamp),
    )


def test_an_official_fire_nearby_protects_a_long_lived_fire(tmp_path):
    """El peor error sería silenciar un incendio real largo: CONAF a ≤ 5 km invalida la regla."""
    db = Database(tmp_path / "brasa.db")
    add_days(db, days_between(NOW - timedelta(days=27), [0, 7, 8, 14, 15, 21, 22, 27]))
    assert incidents.fixed_reason(db, LAT, LON, NOW) is not None  # sin CONAF, sería fija
    add_official(db, "conaf-1", NOW - timedelta(days=5), LAT + 3 * KM_LAT, LON)
    assert incidents.fixed_reason(db, LAT, LON, NOW) is None
    assert incidents.is_fixed_source(db, LAT, LON, NOW) is False


def test_an_old_official_fire_does_not_protect_forever(tmp_path):
    """Fuera de la ventana de 30 días, un incendio viejo ya no desactiva la regla."""
    db = Database(tmp_path / "brasa.db")
    add_days(db, days_between(NOW - timedelta(days=27), [0, 7, 8, 14, 15, 21, 22, 27]))
    add_official(db, "conaf-viejo", NOW - timedelta(days=60), LAT, LON)
    assert incidents.fixed_reason(db, LAT, LON, NOW) is not None


def test_a_volcano_does_not_silence_an_official_fire_beside_it(tmp_path):
    """El cráter no puede tapar un incendio real en la ladera: CONAF se mira primero."""
    db = Database(tmp_path / "brasa.db")
    source = incidents.known_fixed_sources()[0]
    lat, lon = source["lat"], source["lon"]
    assert incidents.fixed_reason(db, lat, lon, NOW) is not None  # el volcán sí es fijo
    add_official(db, "conaf-ladera", NOW - timedelta(days=1), lat + 2 / 111.0, lon)
    assert incidents.fixed_reason(db, lat, lon, NOW) is None
    assert incidents.is_fixed_source(db, lat, lon, NOW) is False


def test_linking_an_official_fire_recalculates_the_fixed_flags(tmp_path):
    """El flags se recalculaba solo en _refresh: al llegar un fuego oficial hay que rehacerlo ya."""
    db = Database(tmp_path / "brasa.db")
    # Patrón de industria en la celda, con su incidente abierto.
    add_days(db, days_between(NOW - timedelta(days=27), [0, 7, 8, 14, 15, 21, 22, 27]))
    stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    point = {"id": "ultima", "lat": LAT, "lon": LON, "observed_at": stamp, "sensor": "VIIRS", "confidence": "nominal", "resolution_m": 375}
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        ("ultima", "firms", "VIIRS", "N20", 375, LAT, LON, stamp, 10.0, "nominal", 13101, stamp),
    )
    [incident] = incidents.update(db, [point], NOW)
    assert incident["fixed_source"] == 1 and incident["fixed_reason"]

    fire = {
        "id": "conaf-nuevo",
        "name": "Incendio real",
        "status": "confirmado",
        "status_raw": "En combate",
        "started_at": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "controlled_at": None,
        "extinguished_at": None,
        "area_ha": 12.0,
        "lat": LAT + 1 / 111.0,
        "lon": LON,
        "comuna": "Viña del Mar",
        "region": "Valparaíso",
        "ambito": "CONAF",
        "fuel": "Pastizal",
    }
    # Como en producción: primero se guardan los incendios de CONAF y después se vinculan.
    add_official(db, fire["id"], NOW - timedelta(hours=2), fire["lat"], fire["lon"])
    assert incidents.link_official(db, [fire], now=NOW) == 1

    row = db.one("SELECT fixed_source, fixed_reason, status FROM incidents WHERE id = ?", (incident["id"],))
    assert row["fixed_source"] == 0 and row["fixed_reason"] is None
    assert row["status"] == "confirmado"


def test_an_official_fire_beyond_linking_distance_unsilences(tmp_path):
    """CONAF a 4 km no vincula (exige ~3 km), pero sí invalida la fuente fija (5 km): el flag se
    recalcula en el mismo enlace, no cuando llegue otra detección."""
    db = Database(tmp_path / "brasa.db")
    add_days(db, days_between(NOW - timedelta(days=27), [0, 7, 8, 14, 15, 21, 22, 27]))
    stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    point = {"id": "ultima", "lat": LAT, "lon": LON, "observed_at": stamp, "sensor": "VIIRS", "confidence": "nominal", "resolution_m": 375}
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        ("ultima", "firms", "VIIRS", "N20", 375, LAT, LON, stamp, 10.0, "nominal", 13101, stamp),
    )
    [incident] = incidents.update(db, [point], NOW)
    assert incident["fixed_source"] == 1

    fire = {
        "id": "conaf-4km",
        "name": "Incendio real",
        "status": "confirmado",
        "status_raw": "En combate",
        "started_at": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "controlled_at": None,
        "extinguished_at": None,
        "area_ha": 12.0,
        "lat": LAT + 4 * KM_LAT,
        "lon": LON,
        "comuna": "Viña del Mar",
        "region": "Valparaíso",
        "ambito": "CONAF",
        "fuel": "Pastizal",
    }
    add_official(db, fire["id"], NOW - timedelta(hours=2), fire["lat"], fire["lon"])
    assert incidents.link_official(db, [fire], now=NOW) == 0  # a 4 km no se vincula

    row = db.one("SELECT fixed_source, fixed_reason, status FROM incidents WHERE id = ?", (incident["id"],))
    assert row["fixed_source"] == 0 and row["fixed_reason"] is None
    assert row["status"] != "confirmado"


def test_status_cuenta_las_fuentes_fijas_refrescadas_en_24_horas(make_client):
    """DET-51: el contador de auditoría solo mira incidentes fijos actualizados en la ventana."""
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc)
        rows = [
            ("fijo-hoy", 1, now),
            ("fijo-viejo", 1, now - timedelta(hours=30)),
            ("real-hoy", 0, now),
        ]
        for ident, fixed, moment in rows:
            stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
            db.execute(
                "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
                "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, fixed_source, "
                "fixed_reason, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    "posible",
                    stamp,
                    stamp,
                    stamp,
                    LAT,
                    LON,
                    LAT,
                    LAT,
                    LON,
                    LON,
                    1,
                    1,
                    "VIIRS",
                    13101,
                    fixed,
                    "volcán activo conocido (prueba)" if fixed else None,
                    stamp,
                ),
            )
        body = client.get("/api/status").json()
        assert body["fixed_source_24h"] == 1
