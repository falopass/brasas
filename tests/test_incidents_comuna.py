"""FIX-73 — un incidente que cae entre polígonos comunales no queda «sin comuna».

Las detecciones reciben su comuna en la ingesta (`locate`, tolerancia ~1 km) y un foco
que cae en un hueco del trazado —precordillera, límites, costa simplificada— queda con
`comuna_code` nulo. Cuando todos los miembros de un incidente están así, `_refresh`
rescata la comuna más cercana al centro con `territory().nearest`: a ≤ 3 km del borde
se asigna; más lejos (extranjero, mar abierto) se queda sin comuna en vez de inventarla.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend import incidents
from backend.db import Database

T0 = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)

TALCA = 7101
CONSTITUCION = 7102
# Dentro del polígono de Talca a ~900 m del borde. Las comunas vecinas teselan sin
# huecos: no hay punto fuera de todo polígono a ~900 m de Talca donde Talca sea la
# más cercana, así que «~900 m del polígono» se mide al borde desde adentro.
CERCA_DE_TALCA = (-35.4535, -71.6355)
ARGENTINA = (-32.85, -69.95)  # Mendoza: ~6 km al este del polígono de Los Andes
MAR_CERCANO = (-35.430, -72.512)  # mar frente a Constitución: fuera del polígono, ~2,1 km del borde
MAR_ABIERTO = (-35.42, -72.60)  # Pacífico frente a Constitución: ~9.7 km de toda comuna


def incidente(db: Database, puntos: list[tuple[float, float, int | None]]) -> dict:
    """Incidente recién recalculado con detecciones ya vinculadas.

    La inserción es directa porque `update` no crea incidentes con detecciones sin
    comuna (FUEGO-12): el estado «miembros sin comuna» solo existe en datos anteriores
    a esa regla — justo lo que este ítem rescata.
    """
    stamp = incidents._stamp(T0)
    iid = f"fix73-{db.one('SELECT COUNT(*) AS n FROM incidents')['n']}"
    lat, lon, _ = puntos[0]
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, "anomalia", stamp, stamp, stamp, lat, lon, lat, lat, lon, lon, stamp),
    )
    for i, (mlat, mlon, comuna) in enumerate(puntos):
        oid = f"{iid}-o{i}"
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
            "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
            (oid, "firms", "VIIRS", "N20", 375, mlat, mlon, stamp, 12.0, "nominal", comuna, stamp),
        )
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (oid, iid))
    return incidents._refresh(db, iid, T0)


def test_miembros_sin_comuna_rescatan_la_mas_cercana(tmp_path):
    """Centro a ~900 m del polígono de Talca y todos los miembros sin comuna → Talca."""
    db = Database(tmp_path / "brasa.db")
    inc = incidente(db, [(*CERCA_DE_TALCA, None), (*CERCA_DE_TALCA, None)])
    assert inc["comuna_code"] == TALCA


def test_centro_en_argentina_queda_sin_comuna(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc = incidente(db, [(*ARGENTINA, None), (-32.86, -69.96, None)])
    assert inc["comuna_code"] is None


def test_la_comuna_de_los_miembros_se_respeta(tmp_path):
    """La moda de los miembros manda aunque el centro quede junto a otra comuna."""
    db = Database(tmp_path / "brasa.db")
    inc = incidente(db, [(*CERCA_DE_TALCA, CONSTITUCION), (*CERCA_DE_TALCA, CONSTITUCION)])
    assert inc["comuna_code"] == CONSTITUCION


def test_centro_mar_afuera_a_menos_de_3_km_rescata_la_costera(tmp_path):
    """Fuera de todo polígono (locate → None) pero a ~2 km del borde → Constitución."""
    db = Database(tmp_path / "brasa.db")
    inc = incidente(db, [(*MAR_CERCANO, None)])
    assert inc["comuna_code"] == CONSTITUCION


def test_mas_de_3_km_de_toda_comuna_queda_sin_comuna(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc = incidente(db, [(*MAR_ABIERTO, None)])
    assert inc["comuna_code"] is None
