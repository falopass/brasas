"""DET-05: el script de máscara persistente encuentra celdas candidatas y pide revisión humana.

CSV sintéticos de FIRMS SP en tmp_path; el archivo `web/data/persistent_hotspots.json` real
provee los volcanes (Copahue sirve para la exclusión por cercanía).
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "build_persistent_mask", Path(__file__).resolve().parents[1] / "scripts" / "build_persistent_mask.py")
mask = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mask)

LAT, LON = -33.515, -70.815   # zona cualquiera, lejos de los volcanes listados
COPAHUE = (-37.856, -71.183)  # volcán ya listado en persistent_hotspots.json


def write_csv(path: Path, points: list[tuple[float, float, date]], instrument: str = "VIIRS") -> Path:
    """Un FIRMS SP mínimo: VIIRS sin `type`, MODIS con `type` (ambos aceptados)."""
    extra = "0" if instrument == "MODIS" else ""
    header = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,daynight" + (",type" if extra else "")
    lines = [f"{lat},{lon},{day.isoformat()},1200,N20,{instrument},nominal,N" + (f",{extra}" if extra else "")
             for lat, lon, day in points]
    path.write_text(header + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_mask(tmp_path: Path, *csvs: Path, args: list[str] | None = None) -> dict:
    out = tmp_path / "out.json"
    mask.main(["--input", *(str(c) for c in csvs), "--out", str(out), *(args or [])])
    return json.loads(out.read_text(encoding="utf-8"))


def days_from(start: date, offsets: list[int]) -> list[date]:
    return [start + timedelta(days=o) for o in offsets]


def test_cell_with_20_spread_days_and_off_season_is_candidate(tmp_path):
    """20 días distintos, 12 de ellos en abril: supera los dos umbrales del método."""
    days = days_from(date(2021, 4, 1), list(range(12))) + days_from(date(2022, 1, 5), list(range(8)))
    csv = write_csv(tmp_path / "viirs.csv", [(LAT, LON, d) for d in days])
    payload = run_mask(tmp_path, csv)
    [cell] = payload["cells"]
    assert cell["days"] == 20 and cell["off_season_days"] == 12
    assert cell["years"] == [2021, 2022] and cell["sensors"] == ["VIIRS"]
    assert payload["generated_at"] and "revisión humana" in payload["note"]


def test_20_days_all_inside_the_season_are_not_candidate(tmp_path):
    """Un incendio largo de enero no es una fuente fija: faltan días fuera de temporada."""
    days = days_from(date(2023, 1, 10), list(range(20)))
    csv = write_csv(tmp_path / "viirs.csv", [(LAT, LON, d) for d in days])
    assert run_mask(tmp_path, csv)["cells"] == []


def test_cell_within_3km_of_a_known_volcano_is_excluded(tmp_path):
    """El mismo patrón junto al cráter de Copahue no es candidato; a 400 km sí."""
    days = days_from(date(2020, 5, 1), list(range(20)))
    csv = write_csv(tmp_path / "modis.csv",
                    [(COPAHUE[0], COPAHUE[1], d) for d in days] + [(LAT, LON, d) for d in days],
                    instrument="MODIS")
    [cell] = run_mask(tmp_path, csv)["cells"]
    assert cell["days"] == 20 and cell["sensors"] == ["MODIS"]
    assert mask.haversine_km(cell["lat"], cell["lon"], *COPAHUE) > 3


def test_detections_group_into_001_degree_cells(tmp_path):
    """El piso a 0,01° define la celda: dos puntos en la misma cuentan un solo día por fecha."""
    cell = mask.cell_of(LAT, LON)
    assert cell == mask.cell_of(LAT + 0.004, LON + 0.003) == (-33.52, -70.82)
    assert cell != mask.cell_of(LAT - 0.006, LON)          # -33.521 cae en la celda de abajo
    detections = [{"lat": LAT, "lon": LON, "date": date(2024, 6, 1), "sensor": "VIIRS"},
                  {"lat": LAT + 0.004, "lon": LON + 0.003, "date": date(2024, 6, 1), "sensor": "MODIS"}]
    cells = mask.summarize(detections)
    assert len(cells) == 1 and cells[cell]["days"] == {date(2024, 6, 1)}
    assert cells[cell]["sensors"] == {"MODIS", "VIIRS"}    # dos sensores, un solo día


def test_without_valid_input_the_script_fails_clearly(tmp_path):
    """Ni una ruta inexistente ni un CSV sin filas válidas producen una salida vacía silenciosa."""
    with pytest.raises(SystemExit, match="ningún archivo CSV"):
        mask.main(["--input", str(tmp_path / "no-existe"), "--out", str(tmp_path / "o.json")])
    empty = tmp_path / "vacio.csv"
    empty.write_text("latitude,longitude,acq_date\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="detecciones válidas"):
        mask.main(["--input", str(empty), "--out", str(tmp_path / "o.json")])
    assert not (tmp_path / "o.json").exists()
