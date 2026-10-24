"""`backend/dataversion.py` y `GET /api/datos-versionados` (AUTO-16).

Fija el contrato: la fecha la declara el propio JSON (`fetched_at`/`generated_at`/`source.date`)
o, si no trae ninguna, la fecha del archivo dicha como tal (`version_fuente: "mtime"`); un archivo
ausente sale `falta` sin fecha inventada. El endpoint publica los 8 datos versionados con su
resumen, sin rutas absolutas del sistema.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend import dataversion
from backend.settings import ROOT

HOY = datetime(2026, 10, 21, tzinfo=timezone.utc)

TABLA = [
    {
        "archivo": "censo_2024.json",
        "nombre": "Censo",
        "fuente": "INE",
        "ventana_dias": 365,
        "que_hacer": "regenera con build_censo.py",
    },
    {
        "archivo": "temporada-2526.json",
        "nombre": "Temporada",
        "fuente": "CONAF",
        "ventana_dias": 30,
        "que_hacer": "regenera con build_temporada_2526.py",
    },
]


def _hace(dias: int) -> str:
    return (HOY - timedelta(days=dias)).isoformat()


def _fila(filas: list[dict], nombre: str) -> dict:
    return {f["archivo"]: f for f in filas}[nombre]


def test_fecha_declarada_al_dia(tmp_path) -> None:
    (tmp_path / "temporada-2526.json").write_text(json.dumps({"fetched_at": _hace(3)}), encoding="utf-8")
    fila = _fila(dataversion.inventario(tmp_path, HOY, TABLA), "temporada-2526.json")
    assert fila["estado"] == "al_dia"
    assert fila["edad_dias"] == 3 and fila["version_fuente"] == "campo"


def test_viejo_pasa_la_ventana_y_trae_que_hacer(tmp_path) -> None:
    (tmp_path / "censo_2024.json").write_text(json.dumps({"fetched_at": _hace(400)}), encoding="utf-8")
    fila = _fila(dataversion.inventario(tmp_path, HOY, TABLA), "censo_2024.json")
    assert fila["estado"] == "viejo" and fila["edad_dias"] == 400
    assert fila["que_hacer"] == "regenera con build_censo.py"


def test_archivo_ausente_es_falta_sin_fecha_inventada(tmp_path) -> None:
    fila = _fila(dataversion.inventario(tmp_path, HOY, TABLA), "censo_2024.json")
    assert fila["estado"] == "falta"
    assert fila["version"] is None and fila["version_fuente"] is None and fila["edad_dias"] is None


def test_sin_campo_de_fecha_usa_mtime_y_lo_dice(tmp_path) -> None:
    path = tmp_path / "temporada-2526.json"
    path.write_text(json.dumps({"datos": []}), encoding="utf-8")
    fila = _fila(dataversion.inventario(tmp_path, HOY, TABLA), "temporada-2526.json")
    assert fila["version_fuente"] == "mtime"
    assert fila["version"] is not None and fila["estado"] in ("al_dia", "viejo")


def test_fecha_dentro_de_source(tmp_path) -> None:
    (tmp_path / "censo_2024.json").write_text(
        json.dumps({"source": {"name": "INE", "date": _hace(10)}}), encoding="utf-8"
    )
    fila = _fila(dataversion.inventario(tmp_path, HOY, TABLA), "censo_2024.json")
    assert fila["estado"] == "al_dia" and fila["version_fuente"] == "campo" and fila["edad_dias"] == 10


def test_endpoint_publica_los_ocho_archivos(make_client) -> None:
    with make_client() as client:
        body = client.get("/api/datos-versionados").json()
    assert body["type"] == "datos-versionados" and body["generated_at"]
    nombres = {f["archivo"] for f in body["archivos"]}
    assert nombres == {e["archivo"] for e in dataversion.DATOS}
    assert len(body["archivos"]) == 8
    for fila in body["archivos"]:
        assert fila["estado"] in ("al_dia", "viejo", "falta")
        assert fila["version_fuente"] in ("campo", "mtime", None)
        # `prioritarias.json` está vacío hoy: sale al_dia o viejo según su fecha, nunca error.
    assert _fila(body["archivos"], "prioritarias.json")["estado"] in ("al_dia", "viejo")
    assert set(body["resumen"]) == {"al_dia", "viejos", "faltan"}
    texto = json.dumps(body)
    assert str(ROOT) not in texto and ":\\" not in texto, "el payload expone una ruta del sistema"


def test_el_inventario_se_cachea_una_hora(make_client, monkeypatch) -> None:
    """La segunda llamada dentro del TTL no relee ni reparsea los JSON de web/data."""
    calls = []
    original = dataversion.inventario

    def spy(data_dir, *args, **kwargs):
        calls.append(data_dir)
        return original(data_dir, *args, **kwargs)

    monkeypatch.setattr(dataversion, "inventario", spy)
    with make_client() as client:
        assert client.get("/api/datos-versionados").status_code == 200
        assert client.get("/api/datos-versionados").status_code == 200
    assert len(calls) == 1
