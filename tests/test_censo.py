"""`web/data/censo_2024.json`: archivo publicado, lectura tolerante y caché (CENSO-01, OFI-29).

El archivo lo genera scripts/local/build_censo.py y se versiona con el repo. Una fila
mala se descarta sin tumbar el resto; el índice se cachea por la firma del archivo
(mtime_ns y tamaño), así que regenerarlo hace que la siguiente consulta lo relea.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend import censo

ROOT = Path(__file__).resolve().parents[1]
CENSO = json.loads((ROOT / "web" / "data" / "censo_2024.json").read_text())
INDEX = {c["code"]: c["name"] for c in json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text())}
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


# --- archivo publicado ---


def test_file_documents_source_license_and_totals():
    assert CENSO["source"].startswith("https://")
    assert "INE" in CENSO["license"] and "CC BY-SA" in CENSO["license"]
    assert CENSO["fetched_at"] and CENSO["notes"]
    assert set(CENSO["totals"]) == {"poblacion", "viviendas", "hogares"}


def test_codes_match_the_territory_index_without_duplicates():
    codes = [c["code"] for c in CENSO["comunas"]]
    assert len(codes) == len(set(codes))
    assert set(codes) <= set(INDEX)
    assert all(INDEX[c["code"]] == c["name"] for c in CENSO["comunas"])
    assert all(c["poblacion"] > 0 and c["viviendas"] > 0 and c["hogares"] > 0 for c in CENSO["comunas"])
    assert all(c["source"].startswith("https://") and c["fetched_at"] for c in CENSO["comunas"])
    # Comuna del índice sin dato: permitida solo si queda constancia en las notas.
    missing = set(INDEX) - set(codes)
    assert all(str(code) in " ".join(CENSO["notes"]) for code in missing)


def test_totals_match_the_sum_of_the_rows():
    assert sum(c["poblacion"] for c in CENSO["comunas"]) == CENSO["totals"]["poblacion"]
    assert sum(c["viviendas"] for c in CENSO["comunas"]) == CENSO["totals"]["viviendas"]
    assert sum(c["hogares"] for c in CENSO["comunas"]) == CENSO["totals"]["hogares"]


# --- caché del archivo (CENSO-01) ---


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


def test_archivo_ilegible_deja_exposicion_null_y_problema_con_el_error(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA)])
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert censo.comuna(TALCA) is None
    assert censo.salud()["filas"] == 0
    assert any("no se pudo leer" in p for p in censo.problemas())


# --- lectura tolerante (OFI-29) ---


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
    assert any("poblacion" in p for p in censo.problemas())
    salud = censo.salud()
    assert salud["filas"] == 1 and salud["descartadas"] == 2
    assert salud["problemas"] == censo.problemas()


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
