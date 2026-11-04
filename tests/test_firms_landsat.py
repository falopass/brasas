"""DET-07: Landsat 8/9 (OLI, 30 m) como tercera familia polar en NASA FIRMS.

Sin clave, o si esa pasada falla, VIIRS y MODIS siguen. Un FRP vacío o 0 no
borra el punto. Landsat cuenta aparte de VIIRS al confirmar un posible incendio.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from backend.db import Database
from backend import incidents
from backend.providers import firms

MAULE = [-72.85, -36.25, -70.25, -34.65]
WHEN = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)

LANDSAT_CSV = """latitude,longitude,acq_date,acq_time,satellite,confidence,frp,daynight
-35.43,-71.66,2026-10-16,0140,L8,H,,D
-35.44,-71.67,2026-10-16,0142,L9,M,0.0,D
-35.45,-71.68,2026-10-16,0144,L8,L,0,N
-35.46,-71.69,2026-10-16,0146,9,85,1.5,D
"""

VIIRS_CSV = """latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight
-35.43,-71.66,330.1,2026-10-16,0140,21.5,n,N
"""

MODIS_CSV = """latitude,longitude,brightness,acq_date,acq_time,frp,confidence,daynight
-35.42,-71.65,320.0,2026-10-16,0310,40.0,90,D
"""


def test_landsat_normaliza_frp_vacio_o_cero_y_confianza():
    rows = firms.csv_hotspots(LANDSAT_CSV, "LANDSAT_NRT", MAULE)
    assert len(rows) == 4
    assert [row["confidence"] for row in rows] == ["alta", "media", "baja", "alta"]
    assert [row["confidence_raw"] for row in rows] == ["H", "M", "L", "85"]
    assert [row["frp_mw"] for row in rows] == [None, None, None, 1.5]
    assert [row["satellite"] for row in rows] == ["Landsat 8", "Landsat 9", "Landsat 8", "Landsat 9"]
    assert {row["sensor"] for row in rows} == {"LANDSAT"}
    assert {row["instrument"] for row in rows} == {"OLI"}
    assert {row["resolution_m"] for row in rows} == {30}
    assert rows[0]["source"] == "LANDSAT_NRT"


def test_familias_de_landsat_no_se_cuentan_dos_veces():
    assert incidents.satellite_family("LANDSAT") == "LANDSAT"
    assert incidents.satellite_family("OLI") == "LANDSAT"
    assert incidents.satellite_family("L8") == "LANDSAT"
    assert incidents.satellite_family("L9") == "LANDSAT"
    assert incidents.satellite_family("VIIRS") == "VIIRS"
    assert incidents.satellite_family("MODIS") == "MODIS"
    assert incidents.satellite_family("ABI") == "GOES"


def _guardar(db: Database, row: dict, sensor: str | None = None) -> dict:
    sensor = sensor or row["sensor"]
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
        "confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (row["id"], row["source"], sensor, row.get("satellite"), row.get("resolution_m"), row["lat"], row["lon"],
         row["observed_at"], row.get("frp_mw"), row.get("confidence"), 7101, row["observed_at"]),
    )
    return {**row, "sensor": sensor}


def test_viirs_y_landsat_en_el_mismo_momento_hacen_posible(tmp_path):
    db = Database(tmp_path / "brasa.db")
    landsat = firms.csv_hotspots(LANDSAT_CSV, "LANDSAT_NRT", MAULE)[0]
    viirs = firms.csv_hotspots(VIIRS_CSV, "VIIRS_NOAA20_NRT", MAULE)[0]
    guardados = [_guardar(db, viirs), _guardar(db, landsat)]
    [inc] = incidents.update(db, guardados, WHEN)
    assert inc["status"] == "posible" and inc["n_obs"] == 2
    assert inc["sensors"] == "LANDSAT,VIIRS"
    assert inc["max_frp"] == 21.5  # el 0 de Landsat no tapa la medición de VIIRS


def test_l8_y_l9_solos_no_se_confirman_entre_si(tmp_path):
    db = Database(tmp_path / "brasa.db")
    base = firms.csv_hotspots(LANDSAT_CSV, "LANDSAT_NRT", MAULE)[0]
    uno = _guardar(db, {**base, "id": "l8"}, sensor="L8")
    otro = _guardar(db, {**base, "id": "l9", "lat": base["lat"] + 0.01}, sensor="L9")
    [inc] = incidents.update(db, [uno, otro], WHEN)
    assert inc["status"] == "anomalia" and inc["n_obs"] == 2


def test_landsat_con_frp_cero_se_agrupa(tmp_path):
    db = Database(tmp_path / "brasa.db")
    punto = firms.csv_hotspots(LANDSAT_CSV, "LANDSAT_NRT", MAULE)[1]
    assert punto["frp_mw"] is None and punto["confidence"] == "media"
    [inc] = incidents.update(db, [_guardar(db, punto)], WHEN)
    assert inc["status"] == "anomalia" and inc["n_obs"] == 1 and inc["max_frp"] is None


def test_sin_clave_no_pide_landsat_y_deja_viirs_y_modis():
    polar = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
    assert firms.ingest_sources(polar, has_map_key=False) == polar
    con_landsat = firms.ingest_sources((*polar, "LANDSAT_NRT"), has_map_key=False)
    assert con_landsat == polar
    pedido = firms.ingest_sources(polar, has_map_key=True)
    assert pedido[-1] == "LANDSAT_NRT" and pedido.count("LANDSAT_NRT") == 1
    explicito = firms.ingest_sources(("LANDSAT_NRT", "MODIS_NRT"), has_map_key=True)
    assert explicito.count("LANDSAT_NRT") == 1 and "MODIS_NRT" in explicito


def test_un_fallo_de_landsat_no_borra_viirs_ni_modis():
    secreto = "SUPER-SECRET-KEY-123"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "LANDSAT_NRT" in path:
            return httpx.Response(500, text="boom")
        if "MODIS_NRT" in path:
            return httpx.Response(200, text=MODIS_CSV)
        return httpx.Response(200, text=VIIRS_CSV)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots(
                secreto, MAULE, ("VIIRS_NOAA20_NRT", "MODIS_NRT", "LANDSAT_NRT"), client=client,
            )

    points, notices = asyncio.run(run())
    assert {point["sensor"] for point in points} == {"VIIRS", "MODIS"}
    assert len(points) == 2
    assert len(notices) == 1 and "LANDSAT_NRT" in notices[0]
    assert secreto not in " ".join(notices)
