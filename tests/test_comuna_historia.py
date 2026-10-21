"""OFI-29: /api/comuna/{code} — historia CONAF-GEPRIF y temporada 2025-26 en la ficha.

Los dos archivos se copian a un directorio temporal para probar los casos límite sin
tocar los datos reales; los lectores llevan `lru_cache`, así que cada prueba lo limpia.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from backend import historia

ROOT = Path(__file__).resolve().parents[1]
TALCA = 7101  # Talca, Maule
SIN_HISTORIA = 2101  # Antofagasta: no figura en historia-comunas.json ni en temporada-2526.json


@pytest.fixture
def data_files(monkeypatch, tmp_path):
    """Apunta los lectores a copias de los archivos reales dentro de tmp_path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for nombre in ("historia-comunas.json", "temporada-2526.json"):
        shutil.copy(ROOT / "web" / "data" / nombre, data_dir / nombre)
    monkeypatch.setattr(historia, "HISTORIA_FILE", data_dir / "historia-comunas.json")
    monkeypatch.setattr(historia, "TEMPORADA_FILE", data_dir / "temporada-2526.json")
    historia._historia_file.cache_clear()
    historia._temporada_file.cache_clear()
    yield data_dir
    historia._historia_file.cache_clear()
    historia._temporada_file.cache_clear()


def test_talca_devuelve_su_historia_y_su_temporada(make_client, data_files):
    with make_client(GOES_ENABLED="0") as client:
        data = client.get(f"/api/comuna/{TALCA}").json()
    file_h = json.loads((data_files / "historia-comunas.json").read_text(encoding="utf-8"))
    file_t = json.loads((data_files / "temporada-2526.json").read_text(encoding="utf-8"))

    h = data["historia"]
    assert h["total_incendios"] == file_h["comunas"]["talca"]["total_incendios"]
    assert h["total_ha"] == file_h["comunas"]["talca"]["total_ha"]  # hectáreas, no m²
    assert [t["season"] for t in h["temporadas"]] == ["2010-2011", "2014-2015", "2019-2020"]
    assert len(h["top"]) == 3 and h["top"][0]["name"] == "LA BANDERA"
    assert h["source"]["name"] == "CONAF-GEPRIF" and h["source"]["fetched_at"]
    assert h["source"]["url"].startswith("https://")
    assert "CONAF" in h["note"] and "no es una predicción" in h["note"]

    t = data["temporada"]
    assert t["temporada"] == "2025-2026" and t["region"] == "Maule"
    assert t["incendios"] == 29 and t["hectareas"] == 75.58  # hectáreas, no m²
    assert t["puesto_en_region"] == 13  # 12 comunas del Maule quemaron más hectáreas
    assert re.fullmatch(r"20\d\d-\d\d", t["mes_peak"])
    assert t["source"]["url"] == file_t["source"] and t["source"]["fetched_at"] == file_t["fetched_at"]


def test_comuna_fuera_del_archivo_devuelve_nulls_con_nota(make_client, data_files):
    with make_client(GOES_ENABLED="0") as client:
        response = client.get(f"/api/comuna/{SIN_HISTORIA}")
        assert response.status_code == 200
        data = response.json()
    h, t = data["historia"], data["temporada"]
    assert h["total_ha"] is None and h["total_incendios"] is None
    assert h["top"] is None and h["temporadas"] is None
    assert "Antofagasta" in h["note"] and h["source"]["name"] == "CONAF-GEPRIF"
    assert t["incendios"] is None and t["hectareas"] is None and t["puesto_en_region"] is None
    assert "Antofagasta" in t["note"] and t["temporada"] == "2025-2026"


def test_archivo_corrupto_devuelve_null_sin_500(make_client, data_files):
    (data_files / "historia-comunas.json").write_text("{json roto", encoding="utf-8")
    historia._historia_file.cache_clear()
    with make_client(GOES_ENABLED="0") as client:
        response = client.get(f"/api/comuna/{TALCA}")
    assert response.status_code == 200
    data = response.json()
    assert data["historia"] is None
    assert data["temporada"]["temporada"] == "2025-2026"  # el otro archivo sigue sirviendo


def test_el_segundo_pedido_sale_del_cache(make_client, data_files):
    with make_client(GOES_ENABLED="0") as client:
        first = client.get(f"/api/comuna/{TALCA}").json()
        # Aunque el archivo cambie y el lector olvide su caché, la ficha sigue guardada.
        (data_files / "historia-comunas.json").write_text("{}", encoding="utf-8")
        historia._historia_file.cache_clear()
        second = client.get(f"/api/comuna/{TALCA}").json()
    assert second == first and second["historia"]["total_incendios"] is not None
