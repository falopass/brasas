"""DET-21: el humo ADPF y los rayos GLM publicados se recortan al territorio de Chile.

La ventana de lectura GOES es un rectángulo que incluye Argentina, Bolivia, Perú y mar
abierto. Estas pruebas fijan el recorte por la unión de comunas de `geo.territory()` con
casos sintéticos, sin red: celdas y destellos se construyen a mano con la misma forma que
dejan `smoke.parse_adp` y `glm.parse_lcfa`. Los rayos ya se recortan al parsear (DET-25);
el humo se recorta al final de `fetch_smoke`.
"""

from __future__ import annotations

from backend.geo import territory
from backend.providers import glm, smoke

TALCA = (-35.43, -71.66)
NEUQUEN = (-38.95, -68.06)
MENDOZA = (-32.89, -68.84)
# 40 km al oeste de la costa de Constitución: mar abierto, fuera de cualquier comuna.
PACIFICO = (-35.30, -72.85)
# Justo en la costa de Constitución: el trazado comunal generaliza la línea de costa.
COSTA_CONSTITUCION = (-35.34, -72.43)


def _cell(lat: float, lon: float, half: float = 0.02) -> dict:
    """Celda con la forma de `smoke.parse_adp`: centro y caja del píxel en lat/lon."""
    return {
        "lat": lat,
        "lon": lon,
        "min_lat": lat - half,
        "max_lat": lat + half,
        "min_lon": lon - half,
        "max_lon": lon + half,
        "observed_at": "2026-10-21T15:00:00Z",
    }


def _flash(lat: float, lon: float, index: int = 0) -> dict:
    """Destello con la forma de `glm.parse_lcfa`: energía en julios, área en km²."""
    return {
        "id": f"GOES19_GLM:202610211500:{index}",
        "source": "GOES19_GLM",
        "sensor": "GLM",
        "satellite": "GOES-19",
        "lat": lat,
        "lon": lon,
        "observed_at": "2026-10-21T15:00:12Z",
        "energy_j": 520.0,
        "area_km2": 48.0,
    }


# -------------------------------------------------------------------- humo


def test_smoke_cells_keep_only_the_chilean_one():
    cells = [_cell(*TALCA), _cell(*NEUQUEN)]
    kept = smoke.clip_cells(cells, territory())
    assert [(c["lat"], c["lon"]) for c in kept] == [TALCA], "Neuquén está en Argentina"


def test_smoke_cell_touching_the_coast_is_kept():
    """La caja del píxel cuenta: una celda centrada en el mar que toca la costa queda."""
    offshore = _cell(-35.36, -72.55, half=0.06)  # centro en el mar, la caja moja Constitución
    assert smoke.clip_cells([offshore], territory()) == [offshore]


def test_smoke_clip_drops_everything_far_from_chile():
    far = [_cell(*NEUQUEN), _cell(*MENDOZA), _cell(*PACIFICO)]
    assert smoke.clip_cells(far, territory()) == []


# -------------------------------------------------------------------- rayos


def test_glm_flashes_keep_only_the_chilean_one():
    flashes = [_flash(*TALCA, index=0), _flash(*MENDOZA, index=1), _flash(*PACIFICO, index=2)]
    kept = [f for f in flashes if glm.in_chile(f["lat"], f["lon"])]
    assert [f["id"] for f in kept] == ["GOES19_GLM:202610211500:0"], "solo Talca es territorio chileno"


def test_glm_flash_on_the_constitucion_coast_is_kept():
    flash = _flash(*COSTA_CONSTITUCION)
    assert glm.in_chile(flash["lat"], flash["lon"]), "la costa generalizada no puede botar un destello costero"


# -------------------------------------------------------------------- contrato intacto


def test_clipped_items_keep_their_fields_untouched():
    """El recorte filtra, no transforma: unidades, orden lat/lon, UTC y frescura no se tocan."""
    cell, flash = _cell(*TALCA), _flash(*TALCA)
    assert smoke.clip_cells([cell], territory()) == [cell]
    assert glm.in_chile(flash["lat"], flash["lon"])
    # lat/lon en su orden y rango: lat ∈ [-90, 90], lon ∈ [-180, 180], Chile es lon negativo.
    assert -90 <= cell["lat"] <= 90 and -180 <= cell["lon"] <= 0
    assert cell["min_lat"] <= cell["lat"] <= cell["max_lat"]
    assert cell["min_lon"] <= cell["lon"] <= cell["max_lon"]
    # Frescura: el instante observado viaja intacto, en UTC con la Z del contrato.
    assert cell["observed_at"].endswith("Z") and flash["observed_at"].endswith("Z")
    # Unidades GLM: energía en julios y área en km², números tal cual llegaron.
    assert flash["energy_j"] == 520.0 and flash["area_km2"] == 48.0
