"""Lectura tolerante de `web/data/censo_2024.json`: una fila mala no tumba la ficha (OFI-29)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import censo

ROOT = Path(__file__).resolve().parents[1]
TALCA = 7101


@pytest.fixture(autouse=True)
def _limpia_cache():
    censo._index.cache_clear()
    yield
    censo._index.cache_clear()


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


def _escribe(tmp_path, monkeypatch, comunas) -> None:
    ruta = tmp_path / "censo.json"
    ruta.write_text(json.dumps({"license": "CC BY-SA 4.0", "comunas": comunas}), encoding="utf-8")
    monkeypatch.setattr(censo, "CENSO_FILE", ruta)


def test_una_fila_rota_se_descarta_y_el_resto_sigue(tmp_path, monkeypatch):
    sin_hogares = _fila(7202)
    del sin_hogares["hogares"]
    _escribe(tmp_path, monkeypatch, [_fila(TALCA), sin_hogares, _fila(7301, poblacion=None)])

    buena = censo.comuna(TALCA)
    assert buena is not None
    assert set(buena) == {"poblacion", "viviendas", "hogares", "source", "license", "fetched_at"}
    assert buena["poblacion"] == 100 and buena["license"] == "CC BY-SA 4.0"
    assert censo.comuna(7202) is None
    assert censo.comuna(7301) is None
    assert len(censo.problemas()) == 2
    assert "7202" in censo.problemas()[0]


def test_comunas_que_no_es_lista_devuelve_indice_vacio(tmp_path, monkeypatch):
    ruta = tmp_path / "censo.json"
    ruta.write_text(json.dumps({"comunas": "no es una lista"}), encoding="utf-8")
    monkeypatch.setattr(censo, "CENSO_FILE", ruta)

    assert censo._index() == {}
    assert censo.comuna(TALCA) is None


def test_filas_que_no_son_objetos_se_ignoran(tmp_path, monkeypatch):
    _escribe(tmp_path, monkeypatch, ["basura", None, _fila(TALCA)])

    assert censo.comuna(TALCA) is not None
    assert len(censo.problemas()) == 2


def test_conteos_en_texto_se_convierten_y_los_invalidos_se_descartan(tmp_path, monkeypatch):
    _escribe(
        tmp_path,
        monkeypatch,
        [
            _fila(TALCA, poblacion="12345", viviendas=40.0, hogares="30"),
            _fila(7202, poblacion=-1),
            _fila(7301, poblacion=True),
        ],
    )

    buena = censo.comuna(TALCA)
    assert buena is not None
    assert (buena["poblacion"], buena["viviendas"], buena["hogares"]) == (12345, 40, 30)
    assert censo.comuna(7202) is None
    assert censo.comuna(7301) is None
    assert len(censo.problemas()) == 2


def test_source_o_fetched_at_invalidos_descartan_la_fila(tmp_path, monkeypatch):
    _escribe(tmp_path, monkeypatch, [_fila(TALCA, source=" "), _fila(7202, fetched_at=None)])

    assert censo._index() == {}
    assert len(censo.problemas()) == 2


def test_la_ficha_responde_200_con_el_censo_roto(make_client, tmp_path, monkeypatch):
    sin_hogares = _fila(7202)
    del sin_hogares["hogares"]
    _escribe(tmp_path, monkeypatch, [sin_hogares])

    with make_client(GOES_ENABLED="0") as client:
        response = client.get(f"/api/comuna/{TALCA}")

    assert response.status_code == 200
    data = response.json()
    assert data["comuna"]["code"] == TALCA
    assert data["exposicion"] is None
    assert data["risk"]["days"] == [] and data["boton_rojo"]["days"] == []


def test_el_archivo_real_del_repo_no_tiene_problemas():
    comunas = json.loads((ROOT / "web" / "data" / "censo_2024.json").read_text(encoding="utf-8"))["comunas"]

    assert len(censo._index()) == len(comunas)
    assert censo.problemas() == []
