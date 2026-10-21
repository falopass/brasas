"""RISK-05 / UX-15: el resumen de cada lugar no repite las consultas que no dependen del lugar.

«Mi zona» pide el resumen de todos los lugares en paralelo (`web/js/views/zona.js`). Los
incendios oficiales de las últimas 48 h y los avisos DMC por comuna son los mismos para
todos: con tres lugares de Quilpué se consultan una vez por refresco, no una vez por lugar.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.db import Database
from backend.routes import personal as personal_mod
from backend.routes.personal import SUMMARY_SHARED_TTL_S, _summary_cache_key

COMUNA = 5801  # Quilpué
POINTS = [(-33.06, -71.42), (-33.07, -71.41), (-33.08, -71.44)]  # tres lugares de la misma comuna
CHILE_TZ = ZoneInfo("America/Santiago")


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_fires(db: Database) -> None:
    """Dos incendios de CONAF como los del demo: uno dentro del radio y otro a ~16 km."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for fire_id, name, lat, area_ha in [
        ("demo-1", "(DEMO) EL BELLOTO", -33.07, 35.5),
        ("demo-2", "(DEMO) CERRO ARRIBA", -32.92, 12.0),
    ]:
        db.execute(
            "INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, extinguished_at, area_ha, lat, lon, "
            "comuna, region, ambito, fuel, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                fire_id,
                name,
                "confirmado",
                "En combate",
                _stamp(now - timedelta(hours=3)),
                None,
                None,
                area_ha,
                lat,
                -71.41,
                "Quilpué",
                "Valparaíso",
                "CONAF",
                "Pastizal",
                _stamp(now),
                _stamp(now),
            ),
        )


def _seed_dmc(db: Database, comuna: int = COMUNA) -> None:
    """Un aviso DMC de viento vigente, con la forma que deja `ingest_dmc` (ver test_alert_dmc.py)."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, areas, comunas, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "urn:oid:2.49.0.0.152.0.2026.10.20.1",
            "viento",
            "Viento Normal a Moderado",
            "Viento Normal a Moderado en litoral de la región de Valparaíso",
            "Moderate",
            "Expected",
            (now - timedelta(hours=1)).isoformat(),
            (now + timedelta(hours=6)).isoformat(),
            "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
            "[]",
            json.dumps([comuna]),
            now.isoformat(),
        ),
    )


def _places(client, count: int = 3):
    """Un dispositivo con `count` lugares de la misma comuna; devuelve (headers, [place_id])."""
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    ids = [
        client.post("/api/places", json={"name": f"Lugar {i}", "lat": lat, "lon": lon, "radius_km": 10}, headers=headers).json()["id"]
        for i, (lat, lon) in enumerate(POINTS[:count])
    ]
    return headers, ids


def test_tres_lugares_consultan_incendios_y_dmc_una_sola_vez(make_client, monkeypatch):
    """Un refresco de 3 lugares: 1 consulta a `official_fires` y 1 a `dmc_alerts` (no 3)."""
    with make_client() as client:
        db = client.app.state.services.db
        _seed_fires(db)
        _seed_dmc(db)
        headers, place_ids = _places(client)
        assert {db.one("SELECT comuna_code FROM places WHERE id = ?", (pid,))["comuna_code"] for pid in place_ids} == {COMUNA}

        counts = {"official_fires": 0, "dmc_alerts": 0}
        original = Database.query

        def counted(self, sql, params=()):
            for table in counts:
                if f"FROM {table}" in sql:
                    counts[table] += 1
            return original(self, sql, params)

        monkeypatch.setattr(Database, "query", counted)
        for pid in place_ids:
            assert client.get(f"/api/places/{pid}/summary", headers=headers).status_code == 200

    assert counts == {"official_fires": 1, "dmc_alerts": 1}


def test_el_payload_con_tres_lugares_conserva_claves_y_orden(make_client):
    """El contrato no cambia: mismas claves, incendios ordenados por distancia, ha y lat/lon intactos."""
    with make_client() as client:
        db = client.app.state.services.db
        _seed_fires(db)
        _seed_dmc(db)
        headers, place_ids = _places(client)
        bodies = [client.get(f"/api/places/{pid}/summary", headers=headers).json() for pid in place_ids]
        cache_row = db.one("SELECT expires_at FROM cache WHERE key = ?", (_summary_cache_key(),))

    keys = {
        "place",
        "comuna",
        "status",
        "cause",
        "wind",
        "official",
        "official_source",
        "dmc_alerts",
        "dmc_source",
        "nearby",
        "risk_days",
        "risk_point",
        "data_as_of",
    }
    for body in bodies:
        assert set(body) == keys
        assert body["status"] == "urgente"  # un incendio de CONAF activo dentro del radio
        assert body["cause"] == {"satelite": False, "conaf": True, "persona_mayor": False}
        # El incendio de demo aparece en los tres lugares: lat y lon se leen en ese orden.
        assert [f["id"] for f in body["official"]] == ["demo-1", "demo-2"]
        assert [f["distance_km"] for f in body["official"]] == sorted(f["distance_km"] for f in body["official"])
        assert body["official"][0]["inside_radius"] is True and body["official"][1]["inside_radius"] is False
        assert body["official"][0]["area_ha"] == 35.5  # hectáreas, no m²
        assert body["dmc_alerts"] and body["dmc_alerts"][0]["kind"] == "viento"

    # Frescura: lo compartido no vive más de 10 s ni cruza el cambio de día en Chile.
    assert SUMMARY_SHARED_TTL_S <= 10
    assert cache_row is not None and cache_row["expires_at"] - time.time() <= SUMMARY_SHARED_TTL_S
    assert _summary_cache_key().endswith(datetime.now(CHILE_TZ).date().isoformat())


def test_la_clave_del_cache_usa_el_dia_de_chile(monkeypatch):
    """A las 02:30 UTC del 21 todavía es 20 en Chile (UTC-3): la clave no debe adelantarse."""

    class _ChileLateNight(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 20, 23, 30, tzinfo=CHILE_TZ)

    monkeypatch.setattr(personal_mod, "datetime", _ChileLateNight)
    assert _summary_cache_key() == "summary-shared:2026-10-20"
