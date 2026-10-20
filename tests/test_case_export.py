"""CONT-15: las detecciones de un caso se descargan en CSV (planilla, clase o reportaje)."""

from __future__ import annotations

import csv
import io

from backend.routes import community

COLUMNS = ["observed_at_utc", "observed_at_chile", "lat", "lon", "sensor", "satellite", "confidence", "frp", "source"]


def _rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_case_export_csv_headers_and_goes_rows(make_client):
    with make_client() as client:
        assert client.get("/api/cases/nope/export.csv").status_code == 404

        res = client.get("/api/cases/penco-lirquen-2026/export.csv")
        assert res.status_code == 200
        assert res.headers["content-type"] == "text/csv; charset=utf-8"
        assert res.headers["content-disposition"] == 'attachment; filename="brasa-penco-lirquen-2026.csv"'
        assert res.content.startswith(b"\xef\xbb\xbf")  # BOM: Excel respeta las tildes

        rows = _rows(res)
        assert rows[0] == COLUMNS and len(rows) > 100
        first = rows[1]
        assert first[4] == "ABI" and first[8] == "goes"
        # Hora de Chile con su offset (-03:00 en verano, -04:00 en invierno).
        assert first[1].endswith(("-03:00", "-04:00"))
        # Una fila por detección, en orden cronológico.
        assert all(rows[i][0] <= rows[i + 1][0] for i in range(1, len(rows) - 1))


def test_case_export_csv_includes_polar(make_client):
    with make_client() as client:
        svc = client.app.state.services
        svc.db.cache_set(
            "case-firms:penco-lirquen-2026",
            [
                {
                    "observed_at": "2026-02-07T20:00:00Z",
                    "lat": -36.7,
                    "lon": -72.9,
                    "sensor": "VIIRS",
                    "satellite": "NOAA-20",
                    "confidence": "nominal",
                    "frp_mw": 12.5,
                }
            ],
            3600,
        )
        rows = _rows(client.get("/api/cases/penco-lirquen-2026/export.csv"))
        polar = [r for r in rows[1:] if r[8] == "polar"]
        assert polar and polar[0][4:8] == ["VIIRS", "NOAA-20", "nominal", "12.5"]


def test_case_export_csv_row_limit(make_client, monkeypatch):
    monkeypatch.setattr(community, "EXPORT_MAX_ROWS", 5)
    with make_client() as client:
        res = client.get("/api/cases/penco-lirquen-2026/export.csv")
        assert res.status_code == 413
