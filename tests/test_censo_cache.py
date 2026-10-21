"""CENSO-01: el índice y el diagnóstico del censo leen el mismo archivo, una sola vez.

`_estado()` cachea por la firma del archivo (mtime_ns y tamaño): dos consultas seguidas no
releen el JSON, pero regenerarlo con build_censo.py hace que la siguiente consulta vea el
archivo nuevo. Las filas descartadas quedan en `problemas()` y en `salud()`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend import censo

TALCA = 7101


@pytest.fixture(autouse=True)
def _limpia_cache():
    censo._cache = None
    yield
    censo._cache = None


def _fila(code: int, **cambios) -> dict:
    fila = {
        "code": code,
        "poblacion": 100,
        "viviendas": 40,
        "hogares": 30,
        "source": "https://www.ine.gob.cl/",
        "fetched_at": "2026-10-19T13:09:49+00:00",
    }
    fila.update(cambios)
    return fila


def _escribe(tmp_path: Path, monkeypatch, comunas) -> Path:
    ruta = tmp_path / "censo.json"
    ruta.write_text(json.dumps({"license": "CC BY-SA 4.0", "comunas": comunas}), encoding="utf-8")
    monkeypatch.setattr(censo, "CENSO_FILE", ruta)
    return ruta


def test_dos_consultas_seguidas_no_releen_el_archivo(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA)])
    lecturas = []
    original = Path.read_text

    def espia(self, *args, **kwargs):
        if self == ruta:
            lecturas.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", espia)

    assert censo.comuna(TALCA) is not None
    assert censo.comuna(TALCA) is not None
    assert len(censo.problemas()) == 0
    assert len(lecturas) == 1


def test_un_archivo_regenerado_se_relee(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA, poblacion=100)])
    assert censo.comuna(TALCA)["poblacion"] == 100

    ruta.write_text(json.dumps({"license": "CC BY-SA 4.0", "comunas": [_fila(TALCA, poblacion=200)]}), encoding="utf-8")
    os.utime(ruta, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))  # mtime_ns distinto: la firma cambia
    assert censo.comuna(TALCA)["poblacion"] == 200


def test_una_fila_descartada_aparece_en_problemas_y_en_salud(tmp_path, monkeypatch):
    _escribe(tmp_path, monkeypatch, [_fila(TALCA), _fila(7202, poblacion=-1)])

    assert censo.comuna(7202) is None
    problema = next(p for p in censo.problemas() if "7202" in p)
    assert "poblacion" in problema
    salud = censo.salud()
    assert salud["filas"] == 1 and salud["descartadas"] == 1
    assert salud["problemas"] == censo.problemas()


def test_archivo_ilegible_deja_exposicion_null_y_problema_con_el_error(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA)])
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert censo.comuna(TALCA) is None
    assert censo.salud()["filas"] == 0
    assert any("no se pudo leer" in p for p in censo.problemas())
