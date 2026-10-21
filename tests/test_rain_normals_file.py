"""RAIN-01: el JSON versionado de normales declara qué comunas quedaron sin normal.

Sin servidor: lee `web/data/rain_normals.json` y `web/data/comunas-index.json` del disco,
como `tests/test_interfaz.py`. Vive aparte de `tests/test_rain.py` para no pisar FIX-66.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from backend import rain
from backend.db import Database

ROOT = Path(__file__).resolve().parents[1]
NORMALS = ROOT / "web" / "data" / "rain_normals.json"
INDEX = ROOT / "web" / "data" / "comunas-index.json"

spec = importlib.util.spec_from_file_location("build_rain_normals", ROOT / "scripts" / "local" / "build_rain_normals.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def versioned() -> dict:
    return json.loads(NORMALS.read_text(encoding="utf-8"))


def index_codes() -> set[int]:
    return {row["code"] for row in json.loads(INDEX.read_text(encoding="utf-8"))}


def check_declaration(data: dict) -> None:
    """La guarda: `sin_normal` es exactamente índice − cells y la cobertura cuadra."""
    cells = data["cells"]
    codes = index_codes()
    missing = data["sin_normal"]
    assert len(missing) == len(set(missing)), "sin_normal no puede traer códigos repetidos"
    assert set(missing) <= codes, "sin_normal solo admite códigos del índice"
    assert set(missing) == codes - {int(code) for code in cells}, "sin_normal debe ser exactamente las comunas del índice sin celda"
    assert data["cobertura"]["con_normal"] == len(cells)
    assert data["cobertura"]["total_index"] == len(codes)


def test_versioned_file_declares_which_comunas_lack_a_normal():
    data = versioned()
    assert data["generated_at"] and data["source"] and data["period"] == "1991-2020"
    assert len(data["cells"]) >= 317, "las celdas no pueden bajar del piso de hoy sin que se note"
    check_declaration(data)


def test_load_normals_file_ignores_the_new_keys():
    """`rain.load_normals_file` solo lee generated_at y cells: la semilla FIX-25 no se rompe."""
    pack = rain.load_normals_file(NORMALS)
    assert pack is not None
    assert sorted(pack["cells"]) == sorted(int(code) for code in versioned()["cells"])


def test_export_marks_missing_comunas(tmp_path):
    """Una base con 2 normales exporta `sin_normal` con las otras 343 comunas del índice."""
    db = Database(tmp_path / "brasa.db")
    taken = sorted(index_codes())[:2]
    daily = json.dumps({key: 1.0 for key in rain.DAY_KEYS})
    for code in taken:
        db.execute(
            "INSERT INTO rain_normal(comuna_code, days, daily_normals, computed_at) VALUES (?,?,?,?)",
            (code, 365, daily, "2026-10-20T00:00:00Z"),
        )
    out = tmp_path / "rain_normals.json"
    builder.export_normals(db, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data["cells"]) == {str(code) for code in taken}
    assert data["sin_normal"] == sorted(index_codes() - set(taken))
    assert len(data["sin_normal"]) == 343
    assert data["cobertura"] == {"con_normal": 2, "total_index": 345}


def test_anota_recalculates_without_touching_cells_and_is_idempotent(tmp_path):
    """`--anota` repone la declaración sobre el JSON existente; la segunda pasada no cambia nada."""
    data = versioned()
    data.pop("sin_normal", None)
    data.pop("cobertura", None)
    out = tmp_path / "rain_normals.json"
    out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    builder.annotate_normals(out)
    once = out.read_bytes()
    annotated = json.loads(once)
    check_declaration(annotated)
    assert annotated["generated_at"] == data["generated_at"]
    assert annotated["cells"] == data["cells"]
    builder.annotate_normals(out)
    assert out.read_bytes() == once, "la segunda pasada no puede cambiar ni un byte"


def test_an_invented_sin_normal_fails_the_guard():
    """Un código que sí tiene celda declarado en `sin_normal` rompe la guarda."""
    data = versioned()
    data["sin_normal"] = [int(next(iter(data["cells"])))]
    with pytest.raises(AssertionError):
        check_declaration(data)
