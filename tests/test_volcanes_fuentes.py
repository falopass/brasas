"""Guarda de la lista curada de volcanes (web/data/persistent_hotspots.json).

Cada entrada debe poder auditarse contra la ficha del Smithsonian GVP:
sin número GVP y enlace no se publica un punto (DET-18 / DET-06).
Solo stdlib; los datos no se editan aquí.
"""

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Encuadre amplio de Chile (incluye islas oceánicas), el mismo de test_data_files.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17

# Las tres entradas originales, con su número GVP.
ORIGINALES = {
    "Volcán Villarrica (cráter)": "357120",
    "Volcán Láscar (cráter)": "355100",
    "Volcán Copahue (cráter)": "357090",
}

GVP_RE = re.compile(r"^Smithsonian GVP \d{6}\b")


def _sources():
    with open(DATA / "persistent_hotspots.json", encoding="utf-8") as f:
        return json.load(f)["sources"]


def test_cada_fuente_es_un_volcan_auditable_en_chile():
    sources = _sources()
    assert len(sources) >= 20, f"solo {len(sources)} fuentes fijas"
    names = [s["name"] for s in sources]
    assert len(names) == len(set(names)), f"nombres duplicados: {names}"

    for s in sources:
        for campo in ("name", "kind", "lat", "lon", "radius_km", "source"):
            assert campo in s, f"{s.get('name', '?')}: falta {campo}"
        name = s["name"]
        assert isinstance(name, str) and name, "fuente sin name"
        assert s["kind"] == "volcan", f"{name}: kind inesperado {s['kind']!r}"
        source = s["source"]
        assert isinstance(source, str) and (GVP_RE.match(source) or source.startswith("https://")), (
            f"{name}: source sin número GVP ni URL https: {source!r}"
        )
        assert isinstance(s["lat"], (int, float)) and isinstance(s["lon"], (int, float)), f"{name}: lat/lon no numéricos"
        assert LAT_MIN <= s["lat"] <= LAT_MAX, f"{name}: lat {s['lat']} fuera de Chile"
        assert LON_MIN <= s["lon"] <= LON_MAX, f"{name}: lon {s['lon']} fuera de Chile"
        assert 1 <= s["radius_km"] <= 6, f"{name}: radius_km {s['radius_km']} fuera de 1-6"


def test_siguen_las_tres_originales():
    sources = _sources()
    for nombre, gvp in ORIGINALES.items():
        match = [s for s in sources if s["name"] == nombre]
        assert len(match) == 1, f"falta o está repetida {nombre}"
        assert gvp in match[0]["source"], f"{nombre}: source sin GVP {gvp}: {match[0]['source']!r}"
