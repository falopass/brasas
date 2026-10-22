"""«Testigos»: reportes verificados cerca de la ficha del incendio.

GET /api/incidents/{id}/reports expone los avisos ciudadanos verificados a ≤ km del
incidente —los mismos que ya lo marcan «reportado» en `_status`— y GET /api/reports gana
`limit` + `truncated` para que una temporada grande no devuelva miles de filas sin aviso.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from backend import incidents as incidents_mod
from PIL import Image

LAT, LON = -33.05, -71.55


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_incident(svc, lat: float = LAT, lon: float = LON) -> dict:
    """Un incidente real, de una detección de alta confianza (queda en «anomalía»)."""
    stamp = _stamp(datetime.now(timezone.utc))
    ident = f"sat-{lat}-{lon}"
    svc.db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (ident, "goes", "ABI", "GOES-19", 2000, lat, lon, stamp, 25.0, "alta", 13101, stamp),
    )
    point = {"id": ident, "lat": lat, "lon": lon, "observed_at": stamp, "sensor": "ABI", "confidence": "alta", "resolution_m": 2000}
    [incident] = incidents_mod.update(svc.db, [point], datetime.now(timezone.utc))
    return incident


def seed_report(svc, ident: str, lat: float, lon: float, status: str = "verificado", minutes_ago: float = 0, kind: str = "humo") -> str:
    created = _stamp(datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    svc.db.execute(
        "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
        (ident, created, lat, lon, 13101, kind, "Humo en el cerro", status),
    )
    return ident


def test_only_verified_reports_inside_the_radius_and_window_are_listed(make_client):
    with make_client() as client:
        svc = client.app.state.services
        incident = seed_incident(svc)
        seed_report(svc, "cerca-ok", LAT + 0.01, LON + 0.01)  # ~1,4 km
        seed_report(svc, "cerca-sin-verificar", LAT + 0.01, LON - 0.01, status="no_verificado")
        seed_report(svc, "lejos", LAT + 0.5, LON + 0.5)  # ~70 km
        body = client.get(f"/api/incidents/{incident['id']}/reports").json()
        assert [r["id"] for r in body["reports"]] == ["cerca-ok"]
        assert body["radius_km"] == 3 and body["hours"] == 48 and body["truncated"] is False
        assert 0 < body["reports"][0]["distance_km"] < 3

        seed_report(svc, "a-4km", LAT + 0.036, LON)  # ~4 km
        seed_report(svc, "ayer", LAT + 0.01, LON, minutes_ago=3 * 60)
        body = client.get(f"/api/incidents/{incident['id']}/reports?km=5&hours=2").json()
        assert {r["id"] for r in body["reports"]} == {"cerca-ok", "a-4km"}  # «ayer» queda fuera de 2 h
        assert client.get(f"/api/incidents/{incident['id']}/reports?km=300").status_code == 422
        assert client.get(f"/api/incidents/{incident['id']}/reports?hours=0").status_code == 422


def test_at_most_20_reports_and_truncated(make_client):
    with make_client() as client:
        svc = client.app.state.services
        incident = seed_incident(svc)
        for i in range(25):
            seed_report(svc, f"rep-{i:02d}", LAT + 0.005, LON + 0.005, minutes_ago=i)
        body = client.get(f"/api/incidents/{incident['id']}/reports").json()
        assert len(body["reports"]) == 20 and body["truncated"] is True
        assert body["reports"][0]["id"] == "rep-00"  # el más reciente va primero


def test_an_unknown_incident_id_returns_404(make_client):
    with make_client() as client:
        response = client.get("/api/incidents/ffffffffffff/reports")
        assert response.status_code == 404 and response.json()["detail"]


def test_a_merged_incident_id_resolves_to_the_live_one(make_client):
    """Un enlace viejo con el id absorbido abre los reportes del incidente vigente."""
    with make_client() as client:
        svc = client.app.state.services
        incident = seed_incident(svc)
        dead = "deadbeefdead"
        svc.db.execute(
            "INSERT INTO incident_merges(dead_id, live_id, merged_at) VALUES (?,?,?)",
            (dead, incident["id"], _stamp(datetime.now(timezone.utc))),
        )
        seed_report(svc, "vecino", LAT + 0.01, LON)
        body = client.get(f"/api/incidents/{dead}/reports").json()
        assert [r["id"] for r in body["reports"]] == ["vecino"]


def test_reports_respects_limit_and_reports_the_cut(make_client):
    with make_client() as client:
        svc = client.app.state.services
        for i in range(3):
            seed_report(svc, f"pub-{i}", LAT + i * 0.01, LON, minutes_ago=i)
        cut = client.get("/api/reports?limit=2").json()
        assert len(cut["reports"]) == 2 and cut["truncated"] is True
        full = client.get("/api/reports").json()
        assert len(full["reports"]) == 3 and full["truncated"] is False
        assert client.get("/api/reports?limit=5000").status_code == 422


def jpeg_con_gps() -> bytes:
    """Un JPEG como el que sube un vecino desde su casa: GPS exacto en el EXIF."""
    img = Image.new("RGB", (64, 48), (200, 80, 30))
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (35.0, 25.0, 35.0), 3: "W", 4: (71.0, 39.0, 30.0)}  # GPSInfo
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_la_foto_servida_no_lleva_el_gps_del_telefono(make_client):
    """SEC-207: el aviso sale de una casa o una parcela; si el GPS viajara dentro del archivo,
    publicar la foto revelaría la ubicación exacta de una vivienda. `sanitize_photo` re-codifica
    la imagen al subirla y la servida por /api/reports/{id}/photo no conserva el EXIF."""
    with make_client() as client:
        original = jpeg_con_gps()
        assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)  # sube con GPS
        r = client.post(
            "/api/reports",
            data={"lat": str(LAT), "lon": str(LON), "kind": "humo", "description": "Humo detrás de la casa"},
            files={"photo": ("desde-casa.jpg", original, "image/jpeg")},
        )
        assert r.status_code == 201, r.text
        report_id = r.json()["id"]

        svc = client.app.state.services
        svc.db.execute("UPDATE reports SET status = 'verificado' WHERE id = ?", (report_id,))
        served = client.get(f"/api/reports/{report_id}/photo")
        assert served.status_code == 200
        assert served.content != original  # no se sirve el archivo original
        exif = Image.open(io.BytesIO(served.content)).getexif()
        assert exif.get(0x8825) is None and not exif.get_ifd(0x8825)
