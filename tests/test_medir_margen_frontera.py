"""QA-75: distancia al territorio y bandas del margen de frontera, con puntos sintéticos.

Talca cae dentro del polígono comunal. Mendoza queda a más de 18 km. El punto de
(-32.89, -69.982) está a ~1 km al este del borde oriental del polígono (lado argentino),
que es el caso que el margen de 0,16° deja entrar; al oeste de ese borde se está dentro de
Chile y la distancia es 0. No hay red: solo se usa ``web/data/comunas.geojson``.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # el script importa backend.geo

spec = importlib.util.spec_from_file_location("medir_margen_frontera", ROOT / "scripts" / "local" / "medir_margen_frontera.py")
medir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(medir)

ROWS = [
    {"source": "GOES19_FDCF", "lat": -35.43, "lon": -71.66, "comuna_code": 7101},  # Talca
    {"source": "VIIRS_NOAA20_NRT", "lat": -32.89, "lon": -68.84, "comuna_code": None},  # Mendoza
    {"source": "MODIS_NRT", "lat": -32.89, "lon": -69.982, "comuna_code": None},  # ~1 km al este
    {"source": "GOES19_FDCF", "lat": -32.89, "lon": -70.01, "comuna_code": None},  # dentro, lado chileno
]


def test_bandas_de_distancia():
    result = medir.measure(ROWS)
    by_source = result["by_source"]
    assert by_source["GOES19_FDCF"]["dentro"] == 2
    assert by_source["VIIRS_*"]["más de 18 km"] == 1
    assert by_source["MODIS_*"]["0–1"] == 1


def test_histograma_suma_el_total_de_filas():
    result = medir.measure(ROWS)
    assert sum(sum(counts.values()) for counts in result["by_source"].values()) == result["total"] == len(ROWS)


def test_fuentes_agrupadas():
    assert medir.source_group("VIIRS_NOAA20_NRT") == "VIIRS_*"
    assert medir.source_group("MODIS_SP") == "MODIS_*"
    assert medir.source_group("GOES19_FDCF") == "GOES19_FDCF"
    assert medir.source_group("GOES16_FDCF") == "GOES16_FDCF"
    assert set(medir.measure(ROWS)["by_source"]) == {"GOES19_FDCF", "VIIRS_*", "MODIS_*"}


def test_limites_de_las_bandas():
    assert medir.band(0.0) == "dentro"
    assert medir.band(0.5) == "0–1"
    assert medir.band(1.0) == "0–1"
    assert medir.band(1.1) == "1–2"
    assert medir.band(18.0) == "10–18"
    assert medir.band(18.1) == "más de 18 km"


def test_top_ordena_por_distancia():
    result = medir.measure(ROWS)
    assert result["top"][0]["source"] == "VIIRS_*"
    assert result["top"][0]["distance_km"] > 18
    assert len(result["top"]) == len(ROWS)


def test_db_y_limit(tmp_path):
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    for i, row in enumerate(ROWS):
        db.execute(
            "INSERT INTO work.observations(id, source, sensor, lat, lon, observed_at, comuna_code, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"o{i}",
                row["source"],
                "test",
                row["lat"],
                row["lon"],
                f"2026-01-0{i + 1}T00:00:00Z",
                row["comuna_code"],
                "2026-01-01T00:00:00Z",
            ),
        )
    rows, demo = medir.load_db(tmp_path / "work.db", limit=2)
    assert len(rows) == 2
    assert not demo
    assert medir.main(["--db", str(tmp_path / "work.db"), "--limit", "2"]) == 0


def test_json_y_limit(tmp_path):
    path = tmp_path / "obs.json"
    path.write_text(json.dumps(ROWS), encoding="utf-8")
    assert len(medir.load_json(path, limit=2)) == 2


def test_markdown_con_tres_recomendaciones(tmp_path, capsys):
    path = tmp_path / "obs.json"
    path.write_text(json.dumps(ROWS), encoding="utf-8")
    md = tmp_path / "INV-28.md"
    assert medir.main(["--json", str(path), "--md", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## Metodología" in text
    assert "| Fuente |" in text
    assert "Dejar la tolerancia" in text
    assert "Bajarla a 0,03" in text
    assert "Separar la tolerancia" in text
    assert "Medido sobre la base de demo" not in text
    assert "Margen de frontera" in capsys.readouterr().out


def test_base_vacia_da_mensaje_y_cero(tmp_path, capsys):
    path = tmp_path / "vacia.json"
    path.write_text("[]", encoding="utf-8")
    assert medir.main(["--json", str(path)]) == 0
    assert "No hay detecciones" in capsys.readouterr().err
