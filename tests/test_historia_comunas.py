"""Guarda de la historia de incendios por comuna (OFI-28).

El JSON lo genera scripts/local/build_historia_comunas.py desde el archivo versionado
web/data/incendios-nominados.json (OFI-19) y lo consume web/js/views/riesgo.js.
Ninguna prueba toca la red: el agregado se ejercita sobre los datos reales y sobre
una fixture en memoria.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_historia_comunas as hist  # noqa: E402

SRC = ROOT / "web" / "data" / "incendios-nominados.json"
INDEX = ROOT / "web" / "data" / "comunas-index.json"
DATA = ROOT / "web" / "data" / "historia-comunas.json"
SEASON_RE = re.compile(r"^(\d{4})-(\d{4})$")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _index_names():
    return [c["name"] for c in _load(INDEX)]


def test_archivo_versionado_fresco():
    """El archivo publicado es exactamente lo que produce el script hoy."""
    source = _load(SRC)
    regenerado = hist.dumps(hist.payload(source, _index_names()))
    assert regenerado == DATA.read_text(encoding="utf-8"), (
        "historia-comunas.json quedó atrás: corre scripts/local/build_historia_comunas.py"
    )


def test_determinista():
    """Dos corridas sobre la misma entrada producen bytes idénticos."""
    source = _load(SRC)
    names = _index_names()
    assert hist.dumps(hist.payload(source, names)) == hist.dumps(hist.payload(source, names))


def test_historia_comunas_json():
    source, data = _load(SRC), _load(DATA)
    assert data["source"] == source["source"], "la fuente debe calcar la del origen"
    assert data["note"] and "50" in data["note"], "la nota debe decir qué cuenta y qué no"

    comunas = data["comunas"]
    assert isinstance(comunas, dict) and len(comunas) >= 200, f"solo {len(comunas)} comunas en la historia"
    assert list(comunas) == sorted(comunas), "claves de comuna desordenadas"

    total_ha = 0.0
    for key, c in comunas.items():
        assert set(c) == {"comuna", "total_ha", "total_incendios", "temporadas", "top"}, f"claves inesperadas en {key}: {sorted(c)}"
        assert c["comuna"], f"nombre vacío en {key}"
        assert c["total_incendios"] == sum(t["n"] for t in c["temporadas"]), f"{key}: total_incendios no cuadra con las temporadas"
        assert abs(c["total_ha"] - sum(t["ha"] for t in c["temporadas"])) < 0.1, f"{key}: total_ha no cuadra con las temporadas"
        seasons = [t["season"] for t in c["temporadas"]]
        assert seasons == sorted(seasons), f"{key}: temporadas desordenadas"
        assert all(SEASON_RE.match(s) for s in seasons), f"{key}: temporada inválida"
        assert 1 <= len(c["top"]) <= 3, f"{key}: top debe tener entre 1 y 3 incendios"
        assert c["top"] == sorted(c["top"], key=lambda t: (-t["ha"], t["season"], t["name"])), f"{key}: top no ordenado de mayor a menor"
        total_ha += c["total_ha"]

    # Nada se pierde ni se duplica: el agregado conserva la masa del origen.
    origen_ha = sum(i["ha"] for i in source["items"])
    assert abs(total_ha - origen_ha) <= 0.1, f"la suma agregada ({total_ha}) difiere del origen ({origen_ha})"
    assert sum(c["total_incendios"] for c in comunas.values()) == len(source["items"])


def test_comuna_conocida_con_su_total():
    """Una comuna del origen aparece con sus totales recomputados desde la fuente."""
    source, data = _load(SRC), _load(DATA)
    items = [i for i in source["items"] if i["comuna"] == "Quilpué"]
    assert items, "la fixture cambió: Quilpué ya no está en el origen"
    comuna = data["comunas"]["quilpue"]
    assert comuna["comuna"] == "Quilpué"
    assert comuna["total_incendios"] == len(items)
    assert abs(comuna["total_ha"] - sum(i["ha"] for i in items)) <= 0.1
    assert comuna["top"][0]["ha"] == max(i["ha"] for i in items)


def test_build_agrupa_variantes():
    """La escritura de la capa que no calza el índice queda bajo el nombre territorial."""
    items = [
        {"name": "UNO", "comuna": "Llay-Llay", "season": "2016-2017", "ha": 100.0, "lat": -33, "lon": -71},
        {"name": "DOS", "comuna": "Llaillay", "season": "2017-2018", "ha": 60.0, "lat": -33, "lon": -71},
    ]
    comunas = hist.build(items, ["Llaillay", "Otra"])
    assert list(comunas) == ["llaillay"], f"llay-llay debió mapear a llaillay: {list(comunas)}"
    c = comunas["llaillay"]
    assert c["comuna"] == "Llaillay" and c["total_incendios"] == 2
    assert abs(c["total_ha"] - 160.0) < 0.01
    assert [t["season"] for t in c["temporadas"]] == ["2016-2017", "2017-2018"]
