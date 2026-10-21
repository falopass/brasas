"""Caché en memoria del catálogo y de la línea temporal estática de los casos históricos.

El caso grande (3,9 MB) se leía y parseaba en cada `GET /api/cases/{id}`. Estos tests fijan
el contrato: una lectura por archivo, relectura si el archivo cambia, y los mismos `None`
de antes cuando falta el archivo o la versión no calza.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend import cases

VALIDO = {"version": cases.TIMELINE_VERSION, "hours": [{"t": "2024-01-01T00:00:00Z", "n": 1}]}


def _montar(monkeypatch, tmp_path, case_id: str, payload: dict) -> tuple[dict, Path]:
    monkeypatch.setattr(cases, "DATA", tmp_path)
    carpeta = tmp_path / "cases"
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"{case_id}.timeline.json"
    ruta.write_text(json.dumps(payload), encoding="utf-8")
    return {"id": case_id}, ruta


def _contar_lecturas(monkeypatch, ruta: Path) -> list[Path]:
    leidas: list[Path] = []
    original = Path.read_text

    def contando(self, *args, **kwargs):
        if self == ruta:
            leidas.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", contando)
    return leidas


def test_dos_llamadas_leen_el_archivo_una_vez(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "cache-una-vez", VALIDO)
    leidas = _contar_lecturas(monkeypatch, ruta)

    assert cases.static_timeline(case) == VALIDO
    assert cases.static_timeline(case) == VALIDO
    assert len(leidas) == 1


def test_reescribir_el_archivo_invalida_la_cache(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "cache-relee", VALIDO)
    primero = cases.static_timeline(case)

    nuevo = {"version": cases.TIMELINE_VERSION, "hours": [{"t": "2024-01-02T00:00:00Z", "n": 7}]}
    ruta.write_text(json.dumps(nuevo), encoding="utf-8")
    # Fuerza otro mtime: si el rebuild conserva el tamaño, la fecha es la que invalida.
    stat = ruta.stat()
    os.utime(ruta, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert primero != nuevo
    assert cases.static_timeline(case) == nuevo


def test_sin_archivo_devuelve_none_y_no_queda_cacheado(monkeypatch, tmp_path):
    monkeypatch.setattr(cases, "DATA", tmp_path)
    case = {"id": "cache-aparece"}
    assert cases.static_timeline(case) is None

    carpeta = tmp_path / "cases"
    carpeta.mkdir()
    (carpeta / "cache-aparece.timeline.json").write_text(json.dumps(VALIDO), encoding="utf-8")
    assert cases.static_timeline(case) == VALIDO


def test_version_distinta_devuelve_none_y_cachea_solo_el_none(monkeypatch, tmp_path):
    case, ruta = _montar(monkeypatch, tmp_path, "cache-version", {**VALIDO, "version": cases.TIMELINE_VERSION + 1})
    leidas = _contar_lecturas(monkeypatch, ruta)
    assert cases.static_timeline(case) is None
    assert cases.static_timeline(case) is None
    assert len(leidas) == 1  # el None queda cacheado; el JSON de versión vieja no se retiene


def test_catalogo_relee_cuando_cambia_cases_json(monkeypatch, tmp_path):
    """Reconstruir un caso reescribe cases.json: el catálogo no puede quedarse pegado al primero."""
    monkeypatch.setattr(cases, "DATA", tmp_path)
    ruta = tmp_path / "cases.json"
    ruta.write_text(json.dumps({"note": "n", "cases": [{"id": "vina-del-mar-2024"}]}), encoding="utf-8")

    assert [c["id"] for c in cases.catalog()["cases"]] == ["vina-del-mar-2024"]
    assert cases.get_case("vina-del-mar-2024") == {"id": "vina-del-mar-2024"}
    assert cases.get_case("caso-que-no-existe") is None

    ruta.write_text(json.dumps({"note": "n", "cases": [{"id": "vina-del-mar-2024"}, {"id": "caso-nuevo"}]}), encoding="utf-8")
    # Fuerza otro mtime: si el rebuild conserva el tamaño, la fecha es la que invalida.
    stat = ruta.stat()
    os.utime(ruta, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert [c["id"] for c in cases.catalog()["cases"]] == ["vina-del-mar-2024", "caso-nuevo"]
    assert cases.get_case("caso-nuevo") == {"id": "caso-nuevo"}


def test_get_case_encuentra_los_casos_reales():
    ids = [
        "penco-lirquen-2026",
        "vina-del-mar-2024",
        "nuble-biobio-araucania-2023",
        "las-maquinas-2017",
        "valparaiso-2014",
        "torres-del-paine-2011",
    ]
    for case_id in ids:
        assert cases.get_case(case_id)["id"] == case_id
    assert cases.get_case("caso-que-no-existe") is None


def test_reemplazo_con_mismos_metadatos_relee(monkeypatch, tmp_path):
    """Un reemplazo que conserva tamaño y mtime (p. ej. `cp -p`) crea otro inodo: se relee."""
    case, ruta = _montar(monkeypatch, tmp_path, "cache-inodo", VALIDO)
    assert cases.static_timeline(case) == VALIDO
    stat = ruta.stat()

    nuevo = {"version": cases.TIMELINE_VERSION, "hours": [{"t": "2024-01-02T00:00:00Z", "n": 7}]}
    assert len(json.dumps(nuevo)) == len(json.dumps(VALIDO))  # requisito del escenario
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(nuevo), encoding="utf-8")
    os.utime(tmp, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(tmp, ruta)
    assert ruta.stat().st_size == stat.st_size and ruta.stat().st_mtime_ns == stat.st_mtime_ns

    assert cases.static_timeline(case) == nuevo
