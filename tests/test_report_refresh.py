"""Recalcular el incidente cuando cambia la verificación de un reporte (FIX-09, hallazgos de revisión).

Tres casos que la revisión marcó:
- Un incidente sigue abierto 24 h aunque no tenga detecciones en las últimas 6: la ventana para
  refrescarlo tiene que ser la de vida del incidente, no la de vinculación.
- Revocar una verificación también cambia la evidencia: el incidente tiene que dejar de decir
  «reportado».
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import incidents as incidents_mod

ADMIN = {"X-Admin-Token": "admin-secret-token-999"}
LAT, LON = -33.05, -71.55


def seed_incident(svc, moment: datetime) -> dict:
    """Una sola detección de alta confianza, para que el incidente quede en «anomalía»."""
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    svc.db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                   "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                   ("sat-1", "goes", "ABI", "GOES-19", 2000, LAT, LON, stamp, 25.0, "alta", 13101, stamp))
    point = {"id": "sat-1", "lat": LAT, "lon": LON, "observed_at": stamp, "sensor": "ABI",
             "confidence": "alta", "resolution_m": 2000}
    [incident] = incidents_mod.update(svc.db, [point], moment)
    return incident


def seed_report(svc, lat: float, lon: float, status: str = "no_verificado") -> str:
    """Reporte sembrado directo en la base: estos casos no prueban el alta, y así no gastan el
    límite de reportes por IP que comparten todas las pruebas de la sesión."""
    ident = f"rep-{status}-{lat:.4f}-{lon:.4f}"
    svc.db.execute("INSERT OR REPLACE INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (ident, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), lat, lon, 13101, "humo",
                    "Columna de humo", status))
    return ident


def verify(client, report_id: str):
    return client.post(f"/api/admin/reports/{report_id}", headers=ADMIN, json={"status": "verificado", "note": "ok"})


def test_an_old_but_open_incident_is_still_refreshed(make_client):
    """Sin detecciones nuevas en 6 h, pero dentro de las 24 h de vida: el reporte lo tiene que tocar."""
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        now = datetime.now(timezone.utc)
        incident = seed_incident(svc, now - timedelta(hours=12))
        report_id = seed_report(svc, LAT + 0.01, LON + 0.01)
        assert verify(client, report_id).json()["incidents_refreshed"] == 1
        assert client.get(f"/api/incidents/{incident['id']}").json()["incident"]["status"] == "reportado"


def test_revoking_a_verification_recalculates_the_incident(make_client):
    """Volver a «sin verificar» quita la evidencia: el incidente no puede seguir «reportado»."""
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        incident = seed_incident(svc, datetime.now(timezone.utc))
        report_id = seed_report(svc, LAT + 0.01, LON + 0.01)
        assert verify(client, report_id).json()["incidents_refreshed"] == 1
        revoked = client.post(f"/api/admin/reports/{report_id}", headers=ADMIN,
                              json={"status": "no_verificado", "note": "No era humo"}).json()
        assert revoked["incidents_refreshed"] == 1
        status = client.get(f"/api/incidents/{incident['id']}").json()["incident"]["status"]
        assert status != "reportado" and status in ("anomalia", "posible")


def test_a_report_that_does_not_change_status_does_not_recalculate(make_client):
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        seed_incident(svc, datetime.now(timezone.utc))
        report_id = seed_report(svc, LAT + 0.01, LON + 0.01, status="descartado")
        again = client.post(f"/api/admin/reports/{report_id}", headers=ADMIN, json={"status": "descartado"}).json()
        assert again["incidents_refreshed"] == 0
