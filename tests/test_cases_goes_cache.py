"""Caché en memoria del archivo GOES de un caso histórico (PERF-142).

`GET /api/cases/{id}` pedía `load_goes` y `goes_scans`, y cada una leía y parseaba el mismo
`*.goes.json` (el caso más grande pesa 1,6 MB). Estos tests fijan el contrato: una lectura
por archivo, relectura si el archivo cambia, y los mismos `[]` de antes cuando falta.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend import cases

GOES = {
    "start_utc": "2023-02-03T00:00:00Z",
    "rows": [[0, -36.6, -72.1, 12.3, 320.1, 2], [10, -36.61, -72.11, 5.0, 310.0, 1]],
    "scans": [{"t": "2023-02-03T00:00:00Z", "ok": 10}],
}


def _montar(monkeypatch, tmp_path, case_id: str, payload: dict) -> tuple[dict, Path]:
    monkeypatch.setattr(cases, "DATA", tmp_path)
    carpeta = tmp_path / "cases"
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"{case_id}.goes.json"
    ruta.write_text(json.dumps(payload), encoding="utf-8")
    return {"id": case_id, "goes": {"satellite": "G19"}}, ruta


def _contar_lecturas(monkeypatch, ruta: Path) -> list[Path]:
    leidas: list[Path] = []
    original = Path.read_text

    def contando(self, *args, **kwargs):
        if self == ruta:
            leidas.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", contando)
    return leidas


def test_load_goes_dos_llamadas_leen_una_vez(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "goes-una-vez", GOES)
    leidas = _contar_lecturas(monkeypatch, ruta)

    obs = cases.load_goes(case)
    assert len(obs) == 2 and obs[0]["satellite"] == "GOES-19"
    assert cases.load_goes(case) == obs
    assert len(leidas) == 1


def test_load_goes_y_scans_comparten_la_lectura(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "goes-compartida", GOES)
    leidas = _contar_lecturas(monkeypatch, ruta)

    assert cases.load_goes(case)
    assert cases.goes_scans(case) == GOES["scans"]
    assert len(leidas) == 1


def test_reescribir_el_archivo_invalida_la_cache(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "goes-relee", GOES)
    assert len(cases.load_goes(case)) == 2

    nuevo = dict(GOES, rows=GOES["rows"] + [[20, -36.62, -72.12, 9.9, 305.0, 0]])
    ruta.write_text(json.dumps(nuevo), encoding="utf-8")
    # Fuerza otro mtime: si el rebuild conserva el tamaño, la fecha es la que invalida.
    stat = ruta.stat()
    os.utime(ruta, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert len(cases.load_goes(case)) == 3
    assert cases.goes_scans(case) == nuevo["scans"]


def test_sin_archivo_devuelve_listas_vacias(monkeypatch, tmp_path):
    monkeypatch.setattr(cases, "DATA", tmp_path)
    case = {"id": "sin-goes"}

    assert cases.load_goes(case) == []
    assert cases.goes_scans(case) == []


def test_archivo_sin_scans_devuelve_lista_vacia(monkeypatch, tmp_path):
    case, _ruta = _montar(monkeypatch, tmp_path, "goes-sin-scans", {"start_utc": "2023-02-03T00:00:00Z", "rows": []})

    assert cases.goes_scans(case) == []
